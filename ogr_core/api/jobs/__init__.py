# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
Computations in a child process: progress, cancellation, and honest failure.

WHY A PROCESS AND NOT A THREAD. An engine that has no cancellation cannot
be stopped from a thread, and a thread cannot be killed. A run can take an
hour (OGR Slip2D's verification bank has models above 70 minutes), so
"stop" has to be real: the job's whole process tree is killed. A process
also keeps a native crash from taking the server down with it, and keeps
its standard output off an MCP server's wire.

The child is NOT a daemon, so it can still start its own process pool (a
daemonic process cannot have children, and a pool would fall back to
sequential in silence).

The child writes its files into its job folder, each replaced atomically:
``progress.json`` while running; then ``result.pkl`` (the full results),
``summary.json`` (what a caller reads) and ``status.json`` last. A process
that ends without ``status.json`` crashed, and the tail of its
``stderr.log`` says how.

From OGR Slip2D's ``ogr_api/jobs`` (v0.1.486). What v0.2.9 changes, so
that any program can use it:

* **The child's work is an argument**: ``target``, a function of the
  program's, defined at the top level of one of its modules. It travels to
  the child as pickle carries a function -- its module and its name --,
  so the child imports that module of the program by unpickling it: the
  core never names a program, the program hands it over. It is called
  with one :class:`~.worker.JobContext` and returns ``(payload,
  summary)``. Slip2D's worker had its six analyses written in.
* **Hooks** (:class:`JobHooks`) for what a program cleans up when a job
  ends and wraps around loading its result: Slip2D removed its slice
  store's folders and loaded under ``slice_store.arriving()`` there.
* **A cooperative stop before the kill** (``cancel_grace_s``): ``cancel``
  writes a ``stop`` file, which ``JobContext.should_stop()`` reads, and
  kills the tree only if the child has not ended within the grace. With
  0 (the default) it kills at once, as Slip2D did. OGR FEM2D asked for it
  (its spec 006, D9): a stop between phases keeps what was solved.
* **Progress may carry more than a count** (``progress(done, total,
  phase=..., step=...)``), and a change in those extra fields is never
  dropped by the half-second throttle.
* **The child imports the trees the parent uses**: the program's own
  (``pythonpath``) and the folder of the ``ogr_core`` the parent imported,
  ahead of anything else — the lesson of Slip2D's runner provenance check
  (v0.1.89): a stale installed copy answers just as confidently.

Author: Samuel Sáez López (UPCT)
"""
from __future__ import annotations

import json
import os
import pickle
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, ContextManager, Optional, Sequence

from ..errors import Busy, unknown
from ..messages import say

#: States a job can be in.
QUEUED, RUNNING, DONE, FAILED, CANCELLED, CRASHED = (
    "queued", "running", "done", "failed", "cancelled", "crashed")
FINAL = (DONE, FAILED, CANCELLED, CRASHED)

#: The file a cooperative stop is asked with.
STOP_FILE = "stop"


class JobCancelled(Exception):
    """Raised by a target that stopped because ``should_stop()`` said so:
    the job ends as ``cancelled``."""


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def kill_tree(pid: int) -> None:
    """Kill ``pid`` and everything it started."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, check=False)
    else:  # pragma: no cover - exercised on the POSIX runners
        import signal
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


@dataclass(frozen=True)
class JobHooks:
    """What a program adds around a job.

    * ``on_end(job)`` -- once, when the job reaches a final state, in the
      parent; also for a job that was killed and ran no finalizer (Slip2D:
      remove the folders of its slice store, named by ``job.pids()``).
    * ``loading()`` -- a context manager :meth:`Job.load_results` unpickles
      the result inside (Slip2D: ``slice_store.arriving()``).
    * ``provenance`` -- a top-level function the CHILD calls for a dict of
      its own provenance (the program's version), added to the core's.
    """
    on_end: Optional[Callable[["Job"], None]] = None
    loading: Optional[Callable[[], ContextManager]] = None
    provenance: Optional[Callable[[], dict]] = None


class Job:
    """One computation running (or run) in a child process."""

    def __init__(self, job_id: str, kind: str, project_id: str,
                 folder: Path, proc: subprocess.Popen, model_hash: str,
                 params: dict, hooks: Optional[JobHooks] = None,
                 grace_s: float = 0.0) -> None:
        self.id = job_id
        self.kind = kind
        self.project_id = project_id
        self.folder = folder
        self.proc = proc
        self.model_hash = model_hash
        self.params = params
        self.hooks = hooks or JobHooks()
        self.grace_s = max(0.0, float(grace_s))
        self.started = time.time()
        self.ended: Optional[float] = None
        self.cancelled = False
        #: Whether the last cancel had to kill the tree (False: the child
        #: stopped by itself within the grace).
        self.killed = False
        #: Set once the result has been stored under a ``result_id``.
        self.result_id: Optional[str] = None
        self._final: Optional[dict] = None

    # ------------------------------------------------------------------
    def status(self) -> dict:
        """Where the job is; final states are cached once reached."""
        if self._final is not None:
            return dict(self._final)
        out = {"job_id": self.id, "kind": self.kind,
               "project_id": self.project_id,
               "elapsed_s": round(time.time() - self.started, 1)}
        status = _read_json(self.folder / "status.json")
        code = self.proc.poll()
        if status is not None and code is not None:
            out.update(status)
            self._finish(out)
        elif self.cancelled and code is not None:
            out["state"] = CANCELLED
            self._finish(out)
        elif code is not None:
            out["state"] = CRASHED
            out["exit_code"] = code
            out["error"] = say("api.job.crashed")
            out["log_tail"] = self.log_tail()
            self._finish(out)
        else:
            out["state"] = RUNNING
            prog = _read_json(self.folder / "progress.json")
            if prog:
                out["progress"] = prog
        return out

    def _finish(self, out: dict) -> None:
        self.ended = self.ended or time.time()
        out["elapsed_s"] = round(self.ended - self.started, 1)
        self._final = dict(out)
        if self.hooks.on_end is not None:
            self.hooks.on_end(self)

    def pids(self) -> set:
        """The process numbers of this job: the one ``Popen`` knows and the
        one the worker wrote in its folder. Slip2D v0.1.409 (D383): on
        Windows a venv's ``python.exe`` is a launcher that starts the real
        interpreter, so ``Popen`` may know only the launcher's."""
        pids = {self.proc.pid}
        try:
            pids.add(int((self.folder / "pid").read_text(encoding="ascii")))
        except (OSError, ValueError):
            pass
        return pids

    @property
    def done(self) -> bool:
        return self.status()["state"] in FINAL

    def wait(self, timeout: float, poll: float = 0.1) -> dict:
        """Wait up to ``timeout`` seconds for a final state."""
        deadline = time.time() + max(0.0, float(timeout))
        while True:
            st = self.status()
            if st["state"] in FINAL or time.time() >= deadline:
                return st
            time.sleep(poll)

    def log_tail(self, n: int = 2000) -> str:
        try:
            text = (self.folder / "stderr.log").read_text(
                encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return text[-n:]

    def summary(self) -> Optional[dict]:
        return _read_json(self.folder / "summary.json")

    def load_results(self):
        """The full results; only ever the file this job's child wrote."""
        loading = self.hooks.loading or nullcontext
        with open(self.folder / "result.pkl", "rb") as fh, loading():
            return pickle.load(fh)

    def cancel(self, grace_s: Optional[float] = None) -> dict:
        """Stop the job: ask first when there is a grace, then kill.

        ``grace_s`` (default: the job's) is how long the child has to end
        by itself after the ``stop`` file appears; 0 kills at once."""
        grace = self.grace_s if grace_s is None else max(0.0, float(grace_s))
        if self.proc.poll() is None:
            self.cancelled = True
            if grace > 0:
                try:
                    (self.folder / STOP_FILE).write_text("stop",
                                                         encoding="ascii")
                except OSError:
                    pass
                try:
                    self.proc.wait(timeout=grace)
                except subprocess.TimeoutExpired:
                    pass
            if self.proc.poll() is None:
                self.killed = True
                kill_tree(self.proc.pid)
                try:
                    self.proc.wait(timeout=10)
                except subprocess.TimeoutExpired:  # pragma: no cover
                    pass
        return self.status()


def _core_root() -> Optional[str]:
    """The folder holding the ``ogr_core`` this process imported, unless it
    is an installation's ``site-packages``: the child finds that one by
    itself, and putting it on ``PYTHONPATH`` would put every package in it
    ahead of the standard library."""
    root = Path(__file__).resolve().parents[3]
    if root.name.lower() in ("site-packages", "dist-packages"):
        return None
    return str(root)


class JobManager:
    """Starts, tracks and cancels jobs; at most ``max_concurrent`` at once.

    ``target`` is the default function a job runs (a job may name its
    own; see the module's docstring for what it may be), ``pythonpath`` the folders the child must import ahead
    of anything else (the program's source tree), ``hooks`` the program's
    :class:`JobHooks`, and ``wait_op`` and ``cancel_op`` the operations an
    agent is told to call when a second job is refused.
    """

    def __init__(self, root=None, max_concurrent: int = 1, *,
                 target: Optional[Callable] = None,
                 pythonpath: Sequence = (),
                 hooks: Optional[JobHooks] = None,
                 cancel_grace_s: float = 0.0,
                 wait_op: str = "job_get",
                 cancel_op: str = "job_cancel") -> None:
        self._own_root = root is None
        self.root = Path(root) if root else Path(
            tempfile.mkdtemp(prefix="ogr_jobs_"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_concurrent = max(1, int(max_concurrent))
        self.target = target
        self.pythonpath = [str(Path(p).resolve()) for p in pythonpath]
        self.hooks = hooks or JobHooks()
        self.cancel_grace_s = max(0.0, float(cancel_grace_s))
        self.wait_op = wait_op
        self.cancel_op = cancel_op
        self.jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def running(self) -> list[Job]:
        return [j for j in self.jobs.values()
                if j.status()["state"] == RUNNING]

    def start(self, kind: str, data, project_id: str, model_hash: str,
              params: dict, *, target: Optional[Callable] = None) -> Job:
        """Pickle ``data`` (a detached copy of what the child needs) and
        start the worker on ``target`` (default: the manager's).

        A target pickle cannot carry by name (a lambda, a nested function)
        is refused here, before any process starts."""
        target = target or self.target
        if not callable(target):
            raise ValueError(f"a job needs a target function, got "
                             f"{target!r}")
        with self._lock:
            busy = self.running()
            if len(busy) >= self.max_concurrent:
                raise Busy(say("api.job.busy", job_id=busy[0].id),
                           hint=say("api.job.busy.hint", job_id=busy[0].id,
                                    wait_op=self.wait_op,
                                    cancel_op=self.cancel_op))
            job_id = f"j_{uuid.uuid4().hex[:10]}"
            folder = self.root / job_id
            folder.mkdir()
            try:
                blob = pickle.dumps(
                    {"kind": kind, "data": data, "params": params,
                     "target": target, "provenance": self.hooks.provenance},
                    protocol=pickle.HIGHEST_PROTOCOL)
            except (pickle.PicklingError, AttributeError, TypeError):
                shutil.rmtree(folder, ignore_errors=True)
                raise
            (folder / "input.pkl").write_bytes(blob)
            proc = self._spawn(folder)
            job = Job(job_id, kind, project_id, folder, proc, model_hash,
                      params, hooks=self.hooks,
                      grace_s=self.cancel_grace_s)
            self.jobs[job_id] = job
            return job

    def child_pythonpath(self) -> str:
        """The ``PYTHONPATH`` of a child: the program's trees, the core's,
        then whatever this process was given."""
        parts = list(self.pythonpath)
        core = _core_root()
        if core:
            parts.append(core)
        inherited = os.environ.get("PYTHONPATH", "")
        if inherited:
            parts.append(inherited)
        seen, out = set(), []
        for p in os.pathsep.join(parts).split(os.pathsep):
            if p and p not in seen:
                seen.add(p)
                out.append(p)
        return os.pathsep.join(out)

    def _spawn(self, folder: Path) -> subprocess.Popen:
        env = dict(os.environ)
        env["PYTHONPATH"] = self.child_pythonpath()
        env["PYTHONIOENCODING"] = "utf-8"
        kwargs = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                      cwd=str(folder), env=env)
        if sys.platform == "win32":
            kwargs["creationflags"] = (subprocess.CREATE_NEW_PROCESS_GROUP
                                       | 0x08000000)  # CREATE_NO_WINDOW
        else:  # pragma: no cover
            kwargs["start_new_session"] = True
        err = open(folder / "stderr.log", "wb")
        try:
            return subprocess.Popen(
                [sys.executable, "-m", "ogr_core.api.jobs.worker",
                 str(folder)], stderr=err, **kwargs)
        finally:
            err.close()

    def get(self, job_id: str) -> Job:
        job = self.jobs.get(job_id)
        if job is None:
            raise unknown("job_id", job_id, list(self.jobs))
        return job

    def cancel(self, job_id: str, grace_s: Optional[float] = None) -> dict:
        return self.get(job_id).cancel(grace_s)

    def forget(self, job_id: str) -> None:
        """Drop a finished job and its folder."""
        job = self.jobs.pop(job_id, None)
        if job is not None:
            shutil.rmtree(job.folder, ignore_errors=True)

    def shutdown(self) -> None:
        """Kill running jobs (no grace: the server is going) and remove
        their files."""
        for job in list(self.jobs.values()):
            if job.proc.poll() is None:
                job.cancel(0)
        if self._own_root:
            shutil.rmtree(self.root, ignore_errors=True)
