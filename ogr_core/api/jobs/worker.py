# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
The child process of a job: ``python -m ogr_core.api.jobs.worker <folder>``.

Everything happens under the ``__main__`` guard. On Windows a process pool
started inside the job starts its workers by re-importing the parent's main
module (here, this file as ``__mp_main__``); a module that did work at
import time would run the whole computation again in every pool worker.

The job's ``target`` (a top-level function of the program, which the
unpickling of ``input.pkl`` imports) is called with one
:class:`JobContext` and returns ``(payload, summary)``: the payload goes to
``result.pkl``, the summary (JSON) to ``summary.json``. Raising
:class:`JobCancelled` (after ``should_stop()`` said so) ends the job as
``cancelled``; any other exception, as ``failed`` with its traceback.

From OGR Slip2D's ``ogr_api/jobs/worker.py`` (v0.1.486), without its six
analyses (they are Slip2D's targets now) and with the context object, the
cooperative stop and the extra progress fields of v0.2.9.

Author: Samuel Sáez López (UPCT)
"""
from __future__ import annotations

import json
import os
import pickle
import sys
import time
import traceback
from pathlib import Path

from ...messages import json_args
from ..messages import say
# JobCancelled lives in the package, not here: run as ``-m``, this file
# is ``__main__``, and a class of its own would not be the one a target
# raises (found by test_api_jobs_v029)
from . import STOP_FILE, JobCancelled  # noqa: F401

#: Slip2D v0.1.198 — Windows refuses to rename a file over one another
#: process holds open (``PermissionError``, WinError 5), and the parent
#: READS ``progress.json`` and ``status.json`` while a job runs. Measured in
#: a full suite run: a job died with "PermissionError: [WinError 5]" on the
#: progress file, the moment a poll caught it open. A read takes
#: milliseconds, so a rename that waits a little always gets through.
_REPLACE_TRIES = 40
_REPLACE_WAIT_S = 0.025

#: The shortest time between two progress writes with the same extra
#: fields (a change in them, or the final update, is always written).
PROGRESS_INTERVAL_S = 0.5



def _replace(tmp: Path, path: Path, tries: int = _REPLACE_TRIES) -> None:
    for attempt in range(tries):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == tries - 1:
                raise
            time.sleep(_REPLACE_WAIT_S)


def _write_json(path: Path, data: dict,
                tries: int = _REPLACE_TRIES) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, allow_nan=False), encoding="utf-8")
    _replace(tmp, path, tries)


def _write_pickle(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        pickle.dump(data, fh, protocol=pickle.HIGHEST_PROTOCOL)
    _replace(tmp, path)


def _write_progress(folder: Path, done: int, total: int,
                    extra: dict | None = None) -> bool:
    """Report progress; False when this update had to be skipped.

    Progress is advisory: an intermediate update that cannot be written
    (the parent holding the file open for its poll) is dropped, never
    retried and never raised — it used to propagate out of the progress
    callback and kill the whole analysis (Slip2D v0.1.198).

    The final update (``done >= total``) waits for the reader like the
    status file does, and is still dropped without raising if the reader
    never lets go (Slip2D v0.1.482, D371): with one try, a final update
    that met the parent's poll was lost for good, and the job ended with
    its folder saying it was half way.
    """
    tries = _REPLACE_TRIES if done >= total else 1
    data = {"done": int(done), "total": int(total),
            "fraction": (float(done) / total) if total else None}
    for key, value in (extra or {}).items():
        if key not in data:
            data[key] = value
    try:
        _write_json(folder / "progress.json", data, tries=tries)
        return True
    except (OSError, ValueError, TypeError):
        return False


def _provenance(hook) -> dict:
    import ogr_core
    out = {"ogr_core": str(Path(ogr_core.__file__).resolve().parent),
           "ogr_core_version": ogr_core.__version__,
           "python": sys.version.split()[0]}
    if hook is not None:
        out.update(hook())
    return out


class JobContext:
    """What a job's target receives."""

    def __init__(self, folder: Path, kind: str, data, params: dict) -> None:
        self.folder = Path(folder)
        self.kind = kind
        #: The detached copy of what the parent passed (the model).
        self.data = data
        self.params = dict(params or {})
        self._last = 0.0
        self._last_extra = None

    def progress(self, done, total, **extra) -> None:
        """Report ``done`` of ``total``, with any extra JSON fields (a
        phase, a step, an iteration). Throttled to one write every
        :data:`PROGRESS_INTERVAL_S`, except the final one and any whose
        extra fields changed."""
        now = time.time()
        changed = extra != self._last_extra
        if (not changed and done < total
                and now - self._last < PROGRESS_INTERVAL_S):
            return
        if _write_progress(self.folder, done, total, extra):
            self._last = now
            self._last_extra = extra

    def should_stop(self) -> bool:
        """Whether the parent asked this job to stop (``Job.cancel`` with
        a grace). A target that honours it raises :class:`JobCancelled`
        (or returns what it has, which ends the job as ``done``)."""
        return (self.folder / STOP_FILE).exists()


def _run(folder: Path) -> None:
    started = time.time()
    with open(folder / "input.pkl", "rb") as fh:
        job = pickle.load(fh)
    ctx = JobContext(folder, job["kind"], job["data"], job["params"])
    payload, summary = job["target"](ctx)
    _write_pickle(folder / "result.pkl", payload)
    _write_json(folder / "summary.json", summary)
    _write_json(folder / "status.json",
                {"state": "done", "run_s": round(time.time() - started, 2),
                 "provenance": _provenance(job.get("provenance"))})


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    folder = Path(argv[0])
    # Slip2D v0.1.409 (D383) — this interpreter's own number: the parent's
    # ``Popen`` may know only a launcher's (a venv's python.exe on Windows
    # starts the real one), and a program's ``on_end`` hook may clean up
    # what this process leaves by its number (``Job.pids``)
    try:
        (folder / "pid").write_text(str(os.getpid()), encoding="ascii")
    except OSError:
        pass
    try:
        _run(folder)
        return 0
    except JobCancelled:
        _write_json(folder / "status.json", {"state": "cancelled"})
        return 0
    except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
        problems = getattr(exc, "problems", None)
        error = say("api.internal", type=type(exc).__name__, text=str(exc))
        _write_json(folder / "status.json", {
            "state": "failed",
            "error": str(error),
            "error_code": error.code,
            "error_args": json_args(error.args),
            "problems": list(problems) if problems else None,
            "traceback": traceback.format_exc()[-4000:],
        })
        return 1


if __name__ == "__main__":
    sys.exit(main())
