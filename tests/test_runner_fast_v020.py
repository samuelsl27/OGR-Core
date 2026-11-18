# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.0 — what a release needs and what development runs: ``--fast``, the
slow list, each test's time, and the serial run every N commits.

Moved from OGR Slip2D's ``test_runner_fast_v1376`` with the runner (OGR
Core 0.2.0). There the runner's machine files, its slow list and the
owner's number (100 commits) were constants of the one runner; here they
are what each repository says of itself (``records`` or ``label``,
``slow_list``, ``serial_every``), and this file also holds that each of
them decides something.

Invariants protected:

1. **``--fast`` leaves out exactly the listed files** of the selection, in
   series and in chunks, with the same result in both, and says so before
   and after the totals as any filtered run does. Whole files: their tests
   share what is expensive, and leaving out one test moved its cost to the
   next (Slip2D's first list went by test, and took 19.3 min instead of 11).
2. **``--fast`` never does nothing** (rule 7): with no list, or with every
   selected file in it, it stops with code 2 instead of running the whole
   selection under a FILTERED banner. This repository has no slow list, and
   its own runner says so.
3. **The list is written on purpose, from measured times**: the files of the
   folder that took the threshold or more, in order, with the licence lines,
   read back as written; never a file the folder no longer has; nothing when
   there are no times, nor from a filtered command.
4. **Times are kept only for a run that says where**: each test's under any
   filter, each file's without ``-k``; a whole run names the slow files the
   list leaves in.
5. **The serial run is remembered only when it is the whole suite and
   green**, by the commit it ran at, and only by a repository that has the
   rule (``serial_every``); a whole run in chunks then ends saying how many
   commits ago that was, and ``SERIAL RUN DUE`` from its number on, or when
   it cannot be told. Without the rule nothing is recorded and nothing is
   said (rule 7: the option decides).
6. **A test of the runner never writes the machine's own files**
   (durations, times, serial record, slow list).

How: ``main()`` over throwaway files, as ``test_runner_jobs_v020`` does.
For invariants 3 to 5 the folder is the ``tests/`` of a throwaway git
repository, and the run is told to keep its files there.
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest  # noqa: E402  (the runner's own)

from test_runner_jobs_v020 import (  # noqa: E402
    _CLEAN, _OUT, _REAL, _bytes, _totals,
)

from ogr_core.testing import runner as _R  # noqa: E402

_TESTS = Path(__file__).resolve().parent
#: The project's two licence lines, as this file opens with them: the licence
#: test reads every identifier quoted in the sources, so they are not quoted.
_LICENCE = Path(__file__).read_text(encoding="utf-8").splitlines()[:2]
_MACHINE = [_REAL.durations, _REAL.test_times, _REAL.serial,
            _TESTS / _R.SLOW_LIST_NAME]

#: Two of the six files of ``_CLEAN`` (seven of its eleven tests), and one
#: file that is not there.
_SLOW = ("test_b_three.py\n"
         "test_e_four.py  # 52 s, 4 tests\n"
         "# a comment line\n"
         "\n"
         "test_zz_gone.py\n")

#: One file that takes a measurable while, for the times and the list.
_TIMED = {
    "test_a_quick.py": "class TestA:\n    def test_a1(self):\n        pass\n\n"
                       "    def test_a2(self):\n        pass\n",
    "test_b_sleeps.py": '''
import time


class TestB:
    def test_b_quick(self):
        pass

    def test_b_sleeps(self):
        time.sleep(0.6)
''',
}


def _main(folder: Path, files: dict, **kw) -> dict:
    """``main(folder)`` over ``files`` written into ``folder``: ``{"code",
    "text", "marks"}``. Everything the run sets in this process is put back
    here."""
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    out = Path(tempfile.mkdtemp(prefix="ogr_test_fast_marks_"))
    saved_path = list(sys.path)
    saved_out = os.environ.get(_OUT)
    os.environ[_OUT] = str(out)
    real = [_bytes(p) for p in _MACHINE]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            code = _R.main(folder, **kw)
        marks = {p.stem for p in out.glob("*.json")}
    finally:
        sys.path[:] = saved_path
        if saved_out is None:
            os.environ.pop(_OUT, None)
        else:
            os.environ[_OUT] = saved_out
        for name in files:
            sys.modules.pop(name[:-3], None)
        shutil.rmtree(out, ignore_errors=True)
    text = buf.getvalue()
    for kept in re.findall(r"\(log: (.+?)[\\/]log_\d+\.txt\)", text):
        shutil.rmtree(kept, ignore_errors=True)
    assert [_bytes(p) for p in _MACHINE] == real, "a machine file was written"
    return {"code": code, "text": text, "marks": marks}


def _throwaway(files: dict, **kw) -> dict:
    """A run over a fresh folder that keeps nothing."""
    folder = Path(tempfile.mkdtemp(prefix="ogr_test_fast_files_"))
    try:
        return _main(folder, files, **kw)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _git(cwd: Path, *args) -> str:
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    try:
        out = subprocess.run(["git", "-c", "commit.gpgsign=false", *args],
                             cwd=cwd, env=env, capture_output=True, text=True,
                             stdin=subprocess.DEVNULL, timeout=60)
    except OSError:
        pytest.skip("no git on this system")
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def _repo(commits: int) -> tuple[Path, list]:
    """A throwaway git repository with ``commits`` empty commits, and their
    hashes, oldest first."""
    root = Path(tempfile.mkdtemp(prefix="ogr_test_fast_repo_")).resolve()
    _git(root, "init", "-q")
    shas = []
    for i in range(commits):
        _git(root, "commit", "-q", "--allow-empty", "-m", f"c{i}")
        shas.append(_git(root, "rev-parse", "HEAD"))
    return root, shas


class _Own:
    """The ``tests/`` of a throwaway repository whose runs keep their
    machine files in the repository itself, with the serial rule or not."""

    def __init__(self, serial_every=100):
        self.root, self.shas = _repo(1)
        self.tests = self.root / "tests"
        self.tests.mkdir()
        self.records = _R.Records(durations=self.root / "durations.json",
                                  test_times=self.root / "times.json",
                                  serial=self.root / "serial.json")
        self.serial_every = serial_every

    def run(self, files: dict, **kw) -> dict:
        # A whole run names the files of twice this: 0.3 s, which the file
        # that sleeps 0.6 s passes and a file of two empty tests does not.
        return _main(self.tests, files, records=self.records,
                     slow_seconds=0.15, serial_every=self.serial_every, **kw)

    def read(self, which: str) -> dict:
        return _R.load_durations(getattr(self.records, which))

    def bytes(self) -> dict:
        return {k: _bytes(getattr(self.records, k))
                for k in ("durations", "test_times", "serial")}


_RUNS: dict = {}


def _once(key, make):
    if key not in _RUNS:
        _RUNS[key] = make()
    return _RUNS[key]


def _chain() -> dict:
    """In one repository: a whole serial run, the list written from its
    times, then a --fast run with that list."""
    def make():
        own = _Own()
        out = {"own": own, "whole": own.run(_TIMED)}
        out["write"] = own.run({}, write_slow=0.3)
        out["list"] = (own.tests / "_slow.txt").read_text(encoding="utf-8")
        out["after_whole"] = own.bytes()
        out["times_whole"] = own.read("test_times")
        out["durations_whole"] = own.read("durations")
        # Gone before the --fast run, to see what it writes back: an empty
        # test can time 0.000 s twice, and equal bytes would prove nothing.
        own.records.test_times.unlink()
        own.records.durations.unlink()
        out["fast"] = own.run({}, fast=True)
        out["after_fast"] = own.bytes()
        return out
    return _once("chain", make)


def _slow_list_file() -> Path:
    def make():
        p = Path(tempfile.mkdtemp(prefix="ogr_test_fast_list_")) / "_slow.txt"
        p.write_text(_SLOW, encoding="utf-8")
        return p
    return _once("list", make)


def _fast(jobs: int) -> dict:
    return _once(f"fast{jobs}", lambda: _throwaway(
        _CLEAN, slow_list=_slow_list_file(), fast=True, jobs=jobs))


class TestFastLeavesOutTheListedFiles:
    def test_in_series(self):
        run = _fast(1)
        assert run["code"] == 0, run["text"]
        assert _totals(run["text"]) == "Total: 4    Passed: 4    Failed: 0"
        assert run["marks"] == {"a1", "c1", "d1", "f1"}

    def test_in_chunks_as_in_series(self):
        run = _fast(3)
        assert run["code"] == 0, run["text"]
        assert "[CHUNK]" not in run["text"]
        assert _totals(run["text"]) == "Total: 4    Passed: 4    Failed: 0"
        assert run["marks"] == _fast(1)["marks"]

    def test_only_the_files_left_run(self):
        for jobs in (1, 3):
            heads = re.findall(r"=== (\S+) ===", _fast(jobs)["text"])
            assert sorted(heads) == ["test_a_one.py", "test_c_clock.py",
                                     "test_d_one.py", "test_f_one.py"]

    def test_said_before_and_after_the_totals(self):
        for jobs in (1, 3):
            text = _fast(jobs)["text"]
            lines = [x for x in text.splitlines()
                     if x.startswith("FILTERED RUN")]
            assert len(lines) == 2, text
            # two of the selection: the entry of a file not there is not one
            assert lines[0].startswith("FILTERED RUN — 4 of 6 files, --fast: "
                                       "2 slow file(s) left out "
                                       "(tests/_slow.txt)"), lines[0]
            total_at = text.index("\nTotal:")
            assert text.index(lines[0]) < total_at < text.rindex(lines[1])

    def test_listed_without_them(self):
        run = _throwaway(_CLEAN, slow_list=_slow_list_file(),
                         fast=True, list_only=True)
        assert run["code"] == 0
        listed = re.findall(r"^(test_[^:\s]+)::", run["text"], flags=re.M)
        assert sorted(set(listed)) == ["test_a_one.py", "test_c_clock.py",
                                       "test_d_one.py", "test_f_one.py"]


class TestFastNeverDoesNothing:
    def test_without_a_list(self):
        absent = Path(tempfile.gettempdir()) / "ogr_test_fast_no_such_list.txt"
        run = _throwaway(_CLEAN, slow_list=absent, fast=True)
        assert run["code"] == 2
        assert "--fast has nothing to leave out" in run["text"]
        assert "Total:" not in run["text"]

    def test_the_list_is_the_folders_own_when_none_is_named(self):
        # a fresh folder has no tests/_slow.txt: the same refusal
        run = _throwaway(_CLEAN, fast=True)
        assert run["code"] == 2
        assert "--fast has nothing to leave out: tests/_slow.txt" in run["text"]

    def test_with_every_selected_file_in_it(self):
        run = _throwaway(_CLEAN, slow_list=_slow_list_file(),
                         patterns=["test_b_three", "test_d_one"], fast=True)
        assert run["code"] == 0, run["text"]
        assert _totals(run["text"]) == "Total: 1    Passed: 1    Failed: 0"
        run = _throwaway(_CLEAN, slow_list=_slow_list_file(),
                         patterns=["test_b_three", "test_e_four"], fast=True)
        assert run["code"] == 2
        assert "--fast leaves nothing to run" in run["text"]
        assert "Total:" not in run["text"]

    def test_this_repository_has_no_slow_list_and_its_runner_says_so(self):
        # The core's suite is seconds long; if it ever grows a list, this
        # is the test to rewrite, with the list's own check (every file it
        # names exists) as OGR Slip2D has it.
        assert not (_TESTS / _R.SLOW_LIST_NAME).exists()
        sys.path.insert(0, str(_TESTS))
        import _runner as own_runner
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            # One cheap test selected, so that if the refusal ever went
            # missing this would run that one test and fail here, not run
            # the whole suite — this file included — inside itself (it did,
            # with that error put in on purpose, until its 15 min timeout).
            code = own_runner.main(patterns=["test_license_v10"],
                                   k="test_copyright_line_present", fast=True)
        assert code == 2, buf.getvalue()
        assert "--fast has nothing to leave out" in buf.getvalue()
        assert "===" not in buf.getvalue()      # no file was run


class TestTheList:
    def test_written_from_the_times(self):
        c = _chain()
        assert c["write"]["code"] == 0, c["write"]["text"]
        listed = [line.split("#", 1)[0].strip()
                  for line in c["list"].splitlines()
                  if line.split("#", 1)[0].strip()]
        assert listed == ["test_b_sleeps.py"]
        assert re.search(r"^test_b_sleeps\.py  # \d+ s, 2 tests$",
                         c["list"], flags=re.M)
        assert "1 file(s) of 0.3 s or more written to" in c["write"]["text"]

    def test_with_its_licence_and_what_it_is(self):
        head = _chain()["list"].splitlines()
        assert head[:2] == _LICENCE
        assert any("--write-slow-list 0.3" in x for x in head)

    def test_read_back_as_written(self):
        own = _chain()["own"]
        assert _R.load_slow_list(own.tests / "_slow.txt") == {
            "test_b_sleeps.py"}
        assert _R.load_slow_list(_slow_list_file()) == {
            "test_b_three.py", "test_e_four.py", "test_zz_gone.py"}

    def test_never_a_file_the_folder_does_not_have(self):
        folder = Path(tempfile.mkdtemp(prefix="ogr_test_fast_write_"))
        try:
            (folder / "test_x.py").write_text(
                "class TestX:\n    def test_kept(self):\n        pass\n",
                encoding="utf-8")
            (folder / "test_y.py").write_text(
                "class TestY:\n    def test_y(self):\n        pass\n",
                encoding="utf-8")
            durations = folder / "durations.json"
            _R.save_durations({"test_x.py": 50.0, "test_y.py": 44.9,
                               "test_gone.py": 90.0}, durations)
            out = folder / "_slow.txt"
            with contextlib.redirect_stdout(io.StringIO()):
                assert _R.write_slow_list(folder, 45.0, durations, out) == 0
            assert _R.load_slow_list(out) == {"test_x.py"}
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_nothing_without_times(self):
        folder = Path(tempfile.mkdtemp(prefix="ogr_test_fast_write_"))
        try:
            (folder / "test_x.py").write_text(
                "class TestX:\n    def test_x(self):\n        pass\n",
                encoding="utf-8")
            for durations in (folder / "none.json", None):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    code = _R.write_slow_list(folder, 45.0, durations,
                                              folder / "_slow.txt")
                assert code == 2
                assert "run the whole suite first" in buf.getvalue()
                assert not (folder / "_slow.txt").exists()
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_written_for_the_whole_folder_only(self):
        run = _throwaway(_CLEAN, patterns=["test_a"], write_slow=45.0)
        assert run["code"] == 2
        assert "takes no patterns" in run["text"]


class TestTheTimes:
    def test_each_test_of_a_whole_run(self):
        c = _chain()
        assert c["whole"]["code"] == 0, c["whole"]["text"]
        times = c["times_whole"]
        assert set(times) == {"test_a_quick.py::TestA::test_a1",
                              "test_a_quick.py::TestA::test_a2",
                              "test_b_sleeps.py::TestB::test_b_quick",
                              "test_b_sleeps.py::TestB::test_b_sleeps"}
        assert times["test_b_sleeps.py::TestB::test_b_sleeps"] >= 0.59

    def test_and_each_file(self):
        assert set(_chain()["durations_whole"]) == {
            "test_a_quick.py", "test_b_sleeps.py"}

    def test_a_fast_run_writes_both_for_what_it_ran(self):
        c = _chain()
        assert c["fast"]["code"] == 0, c["fast"]["text"]
        assert _totals(c["fast"]["text"]) == \
            "Total: 2    Passed: 2    Failed: 0"
        assert set(c["own"].read("test_times")) == {
            "test_a_quick.py::TestA::test_a1",
            "test_a_quick.py::TestA::test_a2"}
        assert set(c["own"].read("durations")) == {"test_a_quick.py"}

    def test_under_k_each_tests_time_is_kept_and_no_files(self):
        def make():
            own = _Own()
            return own, own.run(_TIMED, k="test_a1")
        own, run = _once("under_k", make)
        assert run["code"] == 0, run["text"]
        assert set(own.read("test_times")) == {
            "test_a_quick.py::TestA::test_a1"}
        assert own.read("durations") == {}

    def test_a_whole_run_names_the_slow_files_the_list_leaves_in(self):
        text = _chain()["whole"]["text"]
        assert ("SLOW, NOT IN tests/_slow.txt — 1 file(s) took 0.3 s or more "
                "and --fast still runs them:") in text
        assert re.search(r"^  test_b_sleeps\.py  \d+\.\d s$", text,
                         flags=re.M)

    def test_a_run_that_keeps_nothing_names_none(self):
        # in series and in chunks: the two ends of a run are two pieces of
        # code, and the second was the one no test looked at
        for jobs in (1, 2):
            run = _once(f"timed_throwaway{jobs}", lambda: _throwaway(
                _TIMED, slow_seconds=0.15, jobs=jobs))
            assert run["code"] == 0, run["text"]
            assert "Total: 4    Passed: 4    Failed: 0" in run["text"]
            assert "SLOW, NOT IN" not in run["text"], run["text"]

    def test_a_whole_run_in_chunks_names_them_too(self):
        def make():
            own = _Own()
            return own.run(_TIMED, jobs=2)
        run = _once("timed_own_jobs", make)
        assert run["code"] == 0, run["text"]
        assert ("SLOW, NOT IN tests/_slow.txt — 1 file(s) took 0.3 s or more "
                "and --fast still runs them:") in run["text"], run["text"]

    def test_slowest_first_and_only_the_unlisted(self):
        times = {"a": 120.0, "b": 30.0, "c": 200.0, "d": 150.0}
        assert _R.slow_unlisted(times, {"c"}, 90.0) == [("d", 150.0),
                                                       ("a", 120.0)]


class TestTheSerialRecord:
    def test_a_whole_green_serial_run_records_its_commit(self):
        c = _chain()
        rec = _R._read_json(c["own"].records.serial)
        assert rec["commit"] == c["own"].shas[-1]
        assert rec["tests"] == 4
        assert (f"full serial run recorded: {c['own'].shas[-1][:7]}; the next "
                f"is due in 100 commits") in c["whole"]["text"]

    def test_a_filtered_run_does_not(self):
        c = _chain()
        assert c["after_fast"]["serial"] == c["after_whole"]["serial"]
        assert "recorded" not in c["fast"]["text"]

    def test_a_red_run_does_not(self):
        def make():
            own = _Own()
            run = own.run({"test_a_fails.py": "class TestA:\n    def test_a(self)"
                           ":\n        assert False\n"})
            return own, run
        own, run = _once("red", make)
        assert run["code"] == 1
        assert not own.records.serial.exists()
        assert "recorded" not in run["text"]

    def test_a_repository_without_the_rule_records_nothing(self):
        def make():
            own = _Own(serial_every=None)
            return own, own.run(_TIMED)
        own, run = _once("no_rule", make)
        assert run["code"] == 0, run["text"]
        assert not own.records.serial.exists()
        assert "recorded" not in run["text"]
        # the rest of what a whole run keeps is still kept
        assert set(own.read("durations")) == {"test_a_quick.py",
                                              "test_b_sleeps.py"}


class TestTheSerialNotice:
    def _repo(self):
        return _once("repo3", lambda: _repo(3))

    def _notice(self, record, every=100) -> str:
        root, _shas = self._repo()
        path = root / "record.json"
        if record is None:
            path.unlink(missing_ok=True)
        else:
            _R._write_json(path, record)
        return _R.serial_notice(root, path, every)

    def test_none_recorded_is_due(self):
        assert self._notice(None).startswith(
            "SERIAL RUN DUE — no full serial run recorded on this machine; "
            "run `python tests/_runner.py` with no arguments")
        root, _shas = self._repo()
        assert _R.serial_notice(root, None, 100).startswith(
            "SERIAL RUN DUE — no full serial run recorded")

    def test_counted_from_the_commit_it_ran_at(self):
        _root, shas = self._repo()
        text = self._notice({"commit": shas[-1], "date": "2026-10-28 12:00"})
        assert text == (f"last full serial run: {shas[-1][:7]}, 2026-10-28 "
                        f"12:00, 0 commit(s) ago (the next is due at 100)")
        text = self._notice({"commit": shas[0], "date": "d"})
        assert ", 2 commit(s) ago" in text

    def test_due_from_the_number_on(self):
        _root, shas = self._repo()
        assert self._notice({"commit": shas[0], "date": "d"}, every=2) \
            .startswith(f"SERIAL RUN DUE — 2 commits since the last full "
                        f"serial run ({shas[0][:7]}, d)")
        assert not self._notice({"commit": shas[1], "date": "d"}, every=2) \
            .startswith("SERIAL RUN DUE")

    def test_due_when_the_commit_is_not_in_this_history(self):
        assert "is not in this history" in self._notice(
            {"commit": "0" * 40, "date": "d"})
        assert self._notice({"date": "d"}).startswith(
            "SERIAL RUN DUE — no full serial run recorded")

    def test_a_whole_run_in_chunks_ends_with_it(self):
        run = _once("jobs", lambda: _throwaway(_CLEAN, jobs=2,
                                               serial_every=100))
        assert run["code"] == 0, run["text"]
        lines = run["text"].splitlines()
        at = next(i for i, x in enumerate(lines) if x.startswith("Total:"))
        assert lines[at + 1] == "PARALLEL RUN — 2 chunk(s) + serial lane"
        assert lines[at + 2].startswith(
            "SERIAL RUN DUE — no full serial run recorded on this machine")

    def test_a_filtered_run_in_chunks_does_not_say_it(self):
        run = _once("fast_rule", lambda: _throwaway(
            _CLEAN, slow_list=_slow_list_file(), fast=True, jobs=3,
            serial_every=100))
        assert run["code"] == 0, run["text"]
        assert "SERIAL RUN" not in run["text"]
