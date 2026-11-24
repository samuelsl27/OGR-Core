# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.9 — the files a job's child writes survive a parent that reads them,
and its progress says more than a count without being lost to the
throttle.

Moved from OGR Slip2D's ``test_jobs_file_race_v1198`` and
``test_job_progress_final_v1482`` (v0.1.486), with their limit-equilibrium
job replaced by a target of ``_api_job_targets``. What they found: on
Windows a file cannot be renamed over one another process holds open, and
the parent reads ``progress.json`` while a job runs; the exception left the
progress callback and ended the whole analysis (Slip2D v0.1.198), and later
a final update that met the parent's poll was lost for good (v0.1.482).

Invariants:

* an intermediate update that cannot be written is SKIPPED, at once,
  without raising;
* a final update, and the status file, wait for a reader that lets go;
  a final update whose reader never does returns ``False`` and does not
  raise;
* a job whose ``progress.json`` a reader keeps open for its whole run
  still finishes, with its result;
* new in 0.2.9: the extra fields travel, never overwrite the count, and a
  change in them is written even inside the half-second throttle, which
  still drops repeats of the same fields (rule 7).

On Linux renaming over an open file does not fail, so the hold cases only
discriminate on Windows; there they assert what is true on that platform.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

# test_a_final_write_waits_for_the_reader times a write against the clock
# (< 5 s), and the throttle cases depend on the child not being starved:
# with --jobs this file runs alone, after the chunks.
SERIAL_LANE = True

_WINDOWS = os.name == "nt"
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import _api_job_targets as T  # noqa: E402


def _tmp():
    return Path(tempfile.mkdtemp(prefix="ogr_progress_"))


def _read(folder):
    return json.loads((folder / "progress.json").read_text(encoding="utf-8"))


class _CountingSleep:
    """Stands in for the worker's ``time.sleep``: counts, never sleeps."""

    def __init__(self):
        self.calls = 0

    def __call__(self, _seconds):
        self.calls += 1


def _with_sleep(counter, fn):
    from ogr_core.api.jobs import worker
    real = worker.time.sleep
    # the worker's ``time`` is the global module: patch the attribute it
    # looks up and put it back whatever happens (rule 5)
    worker.time.sleep = counter
    try:
        return fn()
    finally:
        worker.time.sleep = real


def _at_one_of_five():
    from ogr_core.api.jobs.worker import _write_progress
    folder = _tmp()
    assert _write_progress(folder, 1, 5) is True
    return folder


class TestTheWorkerWrites:
    def test_a_progress_update_that_cannot_land_is_skipped(self):
        from ogr_core.api.jobs.worker import _write_progress
        folder = _tmp()
        try:
            dest = folder / "progress.json"
            dest.write_text("{}", encoding="utf-8")
            with open(dest, "r", encoding="utf-8"):
                wrote = _write_progress(folder, 3, 10)     # must not raise
            assert wrote in (True, False)
            assert _write_progress(folder, 4, 10) is True  # once released
            assert json.loads(dest.read_text())["done"] == 4
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_a_final_write_waits_for_the_reader(self):
        from ogr_core.api.jobs.worker import _write_json
        folder = _tmp()
        try:
            dest = folder / "status.json"
            dest.write_text("{}", encoding="utf-8")
            fh = open(dest, "r", encoding="utf-8")
            threading.Timer(0.2, fh.close).start()
            t0 = time.time()
            _write_json(dest, {"state": "done"})
            assert json.loads(dest.read_text()) == {"state": "done"}
            assert time.time() - t0 < 5.0
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class TestTheFinalProgressUpdate:
    def test_it_waits_for_a_reader_that_lets_go(self):
        from ogr_core.api.jobs.worker import _write_progress
        folder = _at_one_of_five()
        opened, release = threading.Event(), threading.Event()

        def reader():
            with open(folder / "progress.json", "r", encoding="utf-8"):
                opened.set()
                release.wait(0.1)    # the poll, holding the file ~100 ms

        t = threading.Thread(target=reader, daemon=True)
        try:
            t.start()
            assert opened.wait(5.0)
            assert _write_progress(folder, 5, 5) is True
            assert _read(folder) == {"done": 5, "total": 5, "fraction": 1.0}
        finally:
            release.set()
            t.join(5.0)
            shutil.rmtree(folder, ignore_errors=True)

    def test_it_gives_up_without_raising(self):
        from ogr_core.api.jobs.worker import _REPLACE_TRIES, _write_progress
        folder = _at_one_of_five()
        sleeps = _CountingSleep()
        try:
            with open(folder / "progress.json", "r", encoding="utf-8"):
                wrote = _with_sleep(sleeps,
                                    lambda: _write_progress(folder, 5, 5))
            if _WINDOWS:
                assert wrote is False
                assert sleeps.calls == _REPLACE_TRIES - 1
                assert _read(folder)["done"] == 1
            else:
                assert wrote is True and sleeps.calls == 0
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class TestAnIntermediateProgressUpdate:
    def test_it_is_dropped_without_waiting(self):
        from ogr_core.api.jobs.worker import _write_progress
        folder = _at_one_of_five()
        sleeps = _CountingSleep()
        try:
            with open(folder / "progress.json", "r", encoding="utf-8"):
                wrote = _with_sleep(sleeps,
                                    lambda: _write_progress(folder, 3, 5))
            assert sleeps.calls == 0
            if _WINDOWS:
                assert wrote is False
                assert _read(folder)["done"] == 1
            else:
                assert wrote is True and _read(folder)["done"] == 3
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class TestTheExtraFields:
    def test_they_travel_and_never_overwrite_the_count(self):
        from ogr_core.api.jobs.worker import _write_progress
        folder = _tmp()
        try:
            assert _write_progress(folder, 2, 4, {"phase": "solve",
                                                  "step": 3, "done": 99})
            assert _read(folder) == {"done": 2, "total": 4, "fraction": 0.5,
                                     "phase": "solve", "step": 3}
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_a_value_json_cannot_hold_is_dropped_not_raised(self):
        from ogr_core.api.jobs.worker import _write_progress
        folder = _tmp()
        try:
            assert _write_progress(folder, 1, 4) is True
            assert _write_progress(folder, 2, 4,
                                   {"residual": float("nan")}) is False
            assert _read(folder)["done"] == 1
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_a_change_of_phase_is_written_inside_the_throttle(self):
        from ogr_core.api.jobs import JobManager
        jm = JobManager(target=T.phases,
                        pythonpath=[_HERE])
        try:
            job = jm.start("phases", None, "p_1", "h", {})
            assert job.wait(120)["state"] == "done"
            seen = [json.loads(t)["phase"] for t in job.summary()["seen"]]
            assert seen == ["mesh", "assemble", "solve", "write"]
        finally:
            jm.shutdown()

    def test_a_repeat_of_the_same_phase_is_throttled(self):
        # rule 7: the same four quick updates, the phase not changing,
        # leave the first one on the file
        from ogr_core.api.jobs import JobManager
        jm = JobManager(target=T.same_phase,
                        pythonpath=[_HERE])
        try:
            job = jm.start("same", None, "p_1", "h", {})
            assert job.wait(120)["state"] == "done"
            done = [json.loads(t)["done"] for t in job.summary()["seen"]]
            assert done == [1, 1, 1, 1]
        finally:
            jm.shutdown()


class TestAJobWithAReaderHoldingItsProgress:
    def test_it_finishes(self):
        from ogr_core.api.jobs import JobManager
        jm = JobManager(target=T.square,
                        pythonpath=[_HERE])
        stop = threading.Event()
        try:
            job = jm.start("square", 5, "p_1", "h", {})
            progress = job.folder / "progress.json"

            def hold():
                # Keep the file open whenever it exists, re-opening as the
                # worker replaces it: the worst a polling client can do.
                while not stop.is_set():
                    try:
                        with open(progress, "r", encoding="utf-8"):
                            time.sleep(0.05)
                    except OSError:
                        time.sleep(0.005)
            reader = threading.Thread(target=hold, daemon=True)
            reader.start()
            out = job.wait(240)
            assert out["state"] == "done", out
            assert job.summary()["value"] == 25
        finally:
            stop.set()
            jm.shutdown()
