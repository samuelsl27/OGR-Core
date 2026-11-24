# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.9 — a job of ``ogr_core.api.jobs`` is isolated, stoppable and honest,
whatever program it runs for.

Moved from OGR Slip2D's ``test_api_jobs_v1194`` (v0.1.486) without its
limit-equilibrium model: the child runs the small targets of
``_api_job_targets`` instead of a slope search. Invariants:

* **a job that ends reports its summary, its result and its provenance**,
  and the ``ogr_core`` its child imported is this tree's (Slip2D v0.1.89:
  a stale installed copy answers just as confidently);
* **failure is never mistaken for a result**: a target that raises reports
  ``failed`` with its error, coded; a child that dies without a word,
  ``crashed`` with its log;
* **cancel is real**: neither the child nor what it started is alive
  after it;
* **one at a time**: a second job while one runs is refused (``Busy``),
  naming the job and the operations the program gave;
* **each option moves the outcome** (rule 7): the grace lets a target that
  looks at ``should_stop`` end by itself, and without it the same target
  is killed; a target that does not look is killed after the grace; the
  hooks run; ``pythonpath`` is what lets the child import the target;
* **the child imports no program and no layer above the core**.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_HERE))
import _api_job_targets as T  # noqa: E402


def _manager(**kw):
    from ogr_core.api.jobs import JobManager
    kw.setdefault("pythonpath", [_HERE])
    return JobManager(**kw)


def _refused(cls, fn):
    """The ``cls`` that ``fn`` raises (the runner's ``pytest.raises`` does
    not hand it over)."""
    try:
        fn()
    except cls as exc:
        return exc
    raise AssertionError(f"{cls.__name__} was not raised")


def _alive(pid: int) -> bool:
    if sys.platform == "win32":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                             capture_output=True, text=True).stdout
        return str(pid) in out.split()
    try:
        with open(f"/proc/{pid}/stat") as fh:
            return fh.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


def _wait_for(path: Path, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while not path.exists():
        assert time.time() < deadline, f"{path.name} never appeared"
        time.sleep(0.05)


def _gone(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while _alive(pid):
        if time.time() >= deadline:
            return False
        time.sleep(0.1)
    return True


class TestAJobThatEnds:
    def test_summary_result_progress_and_provenance(self):
        jm = _manager(target=T.square)
        try:
            job = jm.start("square", 7, "p_1", "h", {"a": 1})
            st = job.wait(120)
            assert st["state"] == "done", st
            assert job.summary()["value"] == 49
            assert job.summary()["params"] == {"a": 1}
            assert job.load_results() == {"value": 49, "kind": "square"}
            prog = st.get("progress") or __import__("json").loads(
                (job.folder / "progress.json").read_text(encoding="utf-8"))
            assert prog["done"] == prog["total"] == 3
            assert prog["fraction"] == 1.0 and prog["phase"] == "square"
            assert prog["step"] == 3
            prov = st["provenance"]
            assert Path(prov["ogr_core"]) == _ROOT / "ogr_core"
            import ogr_core
            assert prov["ogr_core_version"] == ogr_core.__version__
        finally:
            jm.shutdown()

    def test_the_child_imports_no_program_and_no_layer_above(self):
        jm = _manager(target=T.square)
        try:
            job = jm.start("square", 2, "p_1", "h", {})
            assert job.wait(120)["state"] == "done"
            assert job.summary()["banned_in_child"] == []
        finally:
            jm.shutdown()

    def test_a_job_may_name_its_own_target(self):
        jm = _manager(target=T.boom)
        try:
            job = jm.start("square", 3, "p_1", "h", {}, target=T.square)
            assert job.wait(120)["state"] == "done"
            assert job.summary()["value"] == 9
        finally:
            jm.shutdown()

    def test_without_a_target_nothing_starts(self):
        jm = _manager()
        try:
            with pytest.raises(ValueError):
                jm.start("square", 3, "p_1", "h", {})
            assert jm.jobs == {}
        finally:
            jm.shutdown()

    def test_a_target_pickle_cannot_name_is_refused_before_a_process(self):
        import pickle
        jm = _manager()
        try:
            with pytest.raises((pickle.PicklingError, AttributeError,
                                TypeError)):
                jm.start("x", 3, "p_1", "h", {}, target=lambda ctx: None)
            assert jm.jobs == {} and list(jm.root.iterdir()) == []
        finally:
            jm.shutdown()


class TestFailure:
    def test_a_target_that_raises_reports_its_error(self):
        jm = _manager(target=T.boom)
        try:
            job = jm.start("boom", "a unicorn", "p_1", "h", {})
            st = job.wait(120)
            assert st["state"] == "failed", st
            assert st["error"] == "RuntimeError: no such thing as a unicorn"
            assert st["error_code"] == "api.internal"
            assert st["error_args"] == {"type": "RuntimeError",
                                        "text": "no such thing as a unicorn"}
            assert "Traceback" in st["traceback"]
            assert not (job.folder / "result.pkl").exists()
        finally:
            jm.shutdown()

    def test_a_child_that_dies_is_reported_as_crashed(self):
        jm = _manager(target=T.die)
        try:
            job = jm.start("die", None, "p_1", "h", {})
            st = job.wait(120)
            assert st["state"] == "crashed", st
            assert st["exit_code"] == 3
            assert st["error"] == ("The analysis process ended without "
                                   "reporting a result.")
            assert st["error"].code == "api.job.crashed"
        finally:
            jm.shutdown()

    def test_a_child_killed_from_outside_is_crashed_not_cancelled(self):
        from ogr_core.api.jobs import kill_tree
        jm = _manager(target=T.stubborn)
        try:
            job = jm.start("stubborn", None, "p_1", "h", {})
            _wait_for(job.folder / "started")
            kill_tree(job.proc.pid)         # NOT cancel: a crash
            job.proc.wait(timeout=10)
            assert job.status()["state"] == "crashed"
        finally:
            jm.shutdown()

    def test_without_its_pythonpath_the_child_cannot_import_the_target(self):
        # rule 7: ``pythonpath`` is what puts the program's tree in the
        # child. The runner's own PYTHONPATH (when it has one) may not hold
        # the tests folder; take it out of the child's environment.
        jm = _manager(target=T.square, pythonpath=[])
        old = os.environ.get("PYTHONPATH")
        os.environ["PYTHONPATH"] = ""
        try:
            job = jm.start("square", 2, "p_1", "h", {})
            st = job.wait(120)
            assert st["state"] == "failed", st
            assert "ModuleNotFoundError" in st["error"]
        finally:
            if old is None:
                os.environ.pop("PYTHONPATH", None)
            else:
                os.environ["PYTHONPATH"] = old
            jm.shutdown()


class TestCancel:
    def test_cancel_kills_the_child_and_everything_it_started(self):
        jm = _manager(target=T.sleep_with_child)
        try:
            job = jm.start("sleep", None, "p_1", "h", {})
            _wait_for(job.folder / "grandchild")
            kid = int((job.folder / "grandchild").read_text())
            assert _alive(kid) and job.status()["state"] == "running"
            out = jm.cancel(job.id)
            assert out["state"] == "cancelled", out
            assert job.killed
            assert not _alive(job.proc.pid)
            # Slip2D v0.1.205: delivery of the kill to the group is
            # asynchronous on POSIX; an orphan outside it never dies
            assert _gone(kid), f"orphaned process {kid}"
        finally:
            jm.shutdown()

    def test_with_a_grace_a_cooperative_target_stops_by_itself(self):
        jm = _manager(target=T.cooperative, cancel_grace_s=30.0)
        try:
            job = jm.start("coop", None, "p_1", "h", {})
            _wait_for(job.folder / "started")
            out = job.cancel()
            assert out["state"] == "cancelled", out
            assert not job.killed
            assert (job.folder / "stopped_by_itself").exists()
        finally:
            jm.shutdown()

    def test_without_a_grace_the_same_target_is_killed(self):
        # rule 7: the grace is what lets it stop by itself
        jm = _manager(target=T.cooperative)
        try:
            job = jm.start("coop", None, "p_1", "h", {})
            _wait_for(job.folder / "started")
            out = job.cancel()
            assert out["state"] == "cancelled", out
            assert job.killed
            assert not (job.folder / "stopped_by_itself").exists()
        finally:
            jm.shutdown()

    def test_a_target_that_does_not_look_is_killed_after_the_grace(self):
        jm = _manager(target=T.stubborn)
        try:
            job = jm.start("stub", None, "p_1", "h", {})
            _wait_for(job.folder / "started")
            t0 = time.time()
            out = job.cancel(grace_s=1.0)
            assert out["state"] == "cancelled", out
            assert job.killed
            assert time.time() - t0 >= 1.0
            assert not _alive(job.proc.pid)
        finally:
            jm.shutdown()


class TestOneAtATime:
    def test_a_second_job_is_refused_while_one_runs(self):
        from ogr_core.api import Busy
        jm = _manager(target=T.stubborn, wait_op="calc_get",
                      cancel_op="calc_stop")
        try:
            first = jm.start("stub", None, "p_1", "h", {})
            err = _refused(Busy, lambda: jm.start("stub", None, "p_1", "h",
                                                  {}))
            assert err.message == f"Job {first.id} is still running."
            assert err.hint == (f"Wait for it with calc_get('{first.id}', "
                                f"wait_seconds=...) or stop it with "
                                f"calc_stop.")
            assert err.message.code == "api.job.busy"
            assert len(jm.jobs) == 1
        finally:
            jm.shutdown()

    def test_the_default_names_are_slip2ds(self):
        from ogr_core.api import Busy
        jm = _manager(target=T.stubborn)
        try:
            first = jm.start("stub", None, "p_1", "h", {})
            err = _refused(Busy, lambda: jm.start("stub", None, "p_1", "h",
                                                  {}))
            assert err.hint == (
                f"Wait for it with job_get('{first.id}', wait_seconds=...) "
                f"or stop it with job_cancel.")
        finally:
            jm.shutdown()


class TestHooks:
    def test_on_end_runs_once_with_the_pids_and_loading_wraps_the_load(self):
        import contextlib

        from ogr_core.api.jobs import JobHooks
        ended, loads = [], []

        @contextlib.contextmanager
        def loading():
            loads.append("in")
            yield
            loads.append("out")

        jm = _manager(target=T.square,
                      hooks=JobHooks(on_end=lambda j: ended.append(j.pids()),
                                     loading=loading,
                                     provenance=T.provenance))
        try:
            job = jm.start("square", 4, "p_1", "h", {})
            st = job.wait(120)
            job.status()
            assert st["state"] == "done"
            assert len(ended) == 1 and job.proc.pid in ended[0]
            # the worker's own number, which may differ from Popen's (a
            # venv launcher on Windows)
            own = int((job.folder / "pid").read_text())
            assert own in ended[0]
            assert job.load_results()["value"] == 16
            assert loads == ["in", "out"]
            assert st["provenance"]["program_version"] == "9.9.9"
            assert "ogr_core" in st["provenance"]
        finally:
            jm.shutdown()

    def test_on_end_runs_for_a_killed_job(self):
        from ogr_core.api.jobs import JobHooks
        ended = []
        jm = _manager(target=T.stubborn,
                      hooks=JobHooks(on_end=lambda j: ended.append(j.id)))
        try:
            job = jm.start("stub", None, "p_1", "h", {})
            _wait_for(job.folder / "started")
            job.cancel()
            assert ended == [job.id]
        finally:
            jm.shutdown()


class TestTheFolders:
    def test_forget_and_shutdown_remove_them(self):
        jm = _manager(target=T.square)
        root = jm.root
        job = jm.start("square", 1, "p_1", "h", {})
        job.wait(120)
        jm.forget(job.id)
        assert not job.folder.exists() and job.id not in jm.jobs
        jm.shutdown()
        assert not root.exists()

    def test_a_root_given_is_kept(self):
        root = Path(tempfile.mkdtemp(prefix="ogr_jobs_given_"))
        try:
            jm = _manager(root=root, target=T.square)
            jm.start("square", 1, "p_1", "h", {}).wait(120)
            jm.shutdown()
            assert root.is_dir()
        finally:
            shutil.rmtree(root, ignore_errors=True)
