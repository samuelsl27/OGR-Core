# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.0 — ``python tests/_runner.py --jobs N``: the selection in N
processes at once, without losing what the serial run catches.

Moved from OGR Slip2D's ``test_runner_jobs_v1375`` with the runner (OGR
Core 0.2.0).

Invariants protected:

1. **The same files, the same tests, the same verdict** as the serial run
   of the same folder, printed in the same order, each file once, with the
   progress counted over the whole run.
2. **Contiguous chunks**: each process runs a piece of the alphabetical
   order (a file keeps its serial neighbours except at the borders), and
   :func:`partition` makes the heaviest piece as light as it can be.
3. **The injected leaks fail the file that leaves them**, inside a chunk as
   in a serial run (``Leaks: 4``, code 1; the file that puts everything
   back is not named).
4. **A chunk that dies is a failure, never a shorter green run**: a file
   that calls ``os._exit(3)`` in its second test fails the run, named with
   its exit code, the file it died in, the file before it and how many of
   its chunk's files did not finish; the other chunks still report.
5. **The run is the run declared**: tests run that the source does not
   declare (a method inherited from a class that is not a ``Test`` class)
   fail it, with the two numbers.
6. **The serial lane**: a file with ``SERIAL_LANE = True`` runs alone,
   after every chunk has ended, in a process of its own; the marker is read
   from the source without running it.
7. **A run with no label keeps nothing on the machine**, and durations are
   merged into what was there.
8. **A chunk enters through the repository's own runner** when the folder
   has one, so that it gets what the repository adds to a run (here, an
   entry of the leak check's allow-list); a folder with none is run by the
   runner module itself, with the suite's list alone.
9. **The temporary folder is settled before the first file**, in every
   chunk as in the run: its first use is not a leak of whichever file made
   it, and a file that moves it is still named.

How: ``main()`` over throwaway files, as ``test_runner_state_v020`` does.
The chunks are real processes running the real runner; what their files
leave stays in them.
"""
from __future__ import annotations

import contextlib
import io
import itertools
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_leaks_v020 import _FILES as _LEAKY  # noqa: E402

from ogr_core.testing import runner as _R  # noqa: E402

_OUT = "OGR_TEST_JOBS_OUT_V020"

_MARK = '''
import json
import os
import time


def _mark(name):
    out = os.environ[{out!r}]
    with open(os.path.join(out, name + ".json"), "w") as fh:
        json.dump({{"pid": os.getpid(), "t": time.time()}}, fh)
'''.format(out=_OUT)

#: Six files, one in the serial lane; "b" has three tests and "e" four, so
#: that the chunks are uneven by file and even by test.
_CLEAN = {
    "test_a_one.py": _MARK + '''

class TestA:
    def test_a1(self):
        _mark("a1")
''',
    "test_b_three.py": _MARK + '''

class TestB:
    def test_b1(self):
        _mark("b1")

    def test_b2(self):
        _mark("b2")

    def test_b3(self):
        _mark("b3")
''',
    "test_c_clock.py": _MARK + '''
SERIAL_LANE = True


class TestC:
    def test_c1(self):
        _mark("c1")
''',
    "test_d_one.py": _MARK + '''

class TestD:
    def test_d1(self):
        _mark("d1")
''',
    "test_e_four.py": _MARK + '''

class TestE:
    def test_e1(self):
        _mark("e1")

    def test_e2(self):
        _mark("e2")

    def test_e3(self):
        _mark("e3")

    def test_e4(self):
        _mark("e4")
''',
    "test_f_one.py": _MARK + '''

class TestF:
    def test_f1(self):
        _mark("f1")
''',
}

#: Weights 1, 2, 1, 1, 5 by test count: two chunks, [a b c d] and [e], and
#: b dies in its second test with c and d still to run in its chunk.
_DYING = {
    "test_a_ok.py": "class TestA:\n    def test_a(self):\n        pass\n",
    "test_b_dies.py": '''
import os


class TestB:
    def test_b1_passes(self):
        pass

    def test_b2_exits(self):
        os._exit(3)
''',
    "test_c_after.py": "class TestC:\n    def test_c(self):\n        pass\n",
    "test_d_after.py": "class TestD:\n    def test_d(self):\n        pass\n",
    "test_e_other.py": "class TestE:\n" + "".join(
        f"    def test_e{i}(self):\n        pass\n\n" for i in range(5)),
}

#: One test the source declares, two that run: ``_Base.test_inherited`` is
#: not in the body of a ``Test`` class, and runs in ``TestA``.
_UNDECLARED = {
    "test_a_inherits.py": '''
class _Base:
    def test_inherited(self):
        pass


class TestA(_Base):
    def test_own(self):
        pass
''',
    "test_b_plain.py": "class TestB:\n    def test_b(self):\n        pass\n",
}

#: A file that leaves a constant of the core changed, and one that does not.
_TOLERANCE = {
    "test_a_tolerance.py": '''
class TestA:
    def test_leaves_a_tolerance(self):
        import ogr_core.fem.mesh as m
        m.DEGENERATE_DET = 0.5
''',
    "test_b_plain.py": "class TestB:\n    def test_b(self):\n        pass\n",
}

#: The first use of the temporary folder in a process, and a file that
#: moves it.
_TEMPORARY = {
    "test_a_first_use.py": '''
import tempfile


class TestA:
    def test_makes_a_temporary_folder(self):
        import os
        os.rmdir(tempfile.mkdtemp(prefix="ogr_test_jobs_first_use_"))
''',
    "test_b_moves_it.py": '''
import os
import tempfile


class TestB:
    def test_moves_the_temporary_folder(self):
        tempfile.tempdir = os.path.dirname(os.path.abspath(__file__))
''',
}

#: A repository's own ``tests/_runner.py``, reduced to what it adds: one
#: entry of the allow-list. Written into the throwaway folder.
_OWN_RUNNER = '''
import sys
from pathlib import Path

sys.path.insert(0, {tree!r})

from ogr_core.testing import leaks, runner

ALLOWED = (leaks.Allow("mod:ogr_core.fem.mesh.DEGENERATE_DET", leaks.ANY,
                       "a synthetic entry of test_runner_jobs_v020"),)

if __name__ == "__main__":
    sys.exit(runner.cli(Path(__file__).resolve().parent, allowed=ALLOWED))
'''

#: The machine files this repository's own runs keep (tests/_runner.py).
_REAL = _R.records_for("ogr-core")


def _bytes(p: Path):
    return p.read_bytes() if p.exists() else None


def _run(files: dict, own_runner: bool = False, **kw) -> dict:
    """``main()`` over ``files`` written to a fresh folder: ``{"code",
    "text", "by_file", "marks"}``. Everything the run sets in this process
    is put back here."""
    folder = Path(tempfile.mkdtemp(prefix="ogr_test_jobs_files_"))
    out = Path(tempfile.mkdtemp(prefix="ogr_test_jobs_marks_"))
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    if own_runner:
        tree = str(Path(_R.__file__).resolve().parents[2])
        (folder / "_runner.py").write_text(_OWN_RUNNER.format(tree=tree),
                                           encoding="utf-8")
    saved_path = list(sys.path)
    saved_out = os.environ.get(_OUT)
    os.environ[_OUT] = str(out)
    real = [_bytes(p) for p in (_REAL.durations, _REAL.test_times,
                                _REAL.serial)]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            code = _R.main(folder, **kw)
        marks = {p.stem: json.loads(p.read_text(encoding="utf-8"))
                 for p in out.glob("*.json")}
    finally:
        sys.path[:] = saved_path
        if saved_out is None:
            os.environ.pop(_OUT, None)
        else:
            os.environ[_OUT] = saved_out
        for name in files:
            sys.modules.pop(name[:-3], None)
        shutil.rmtree(folder, ignore_errors=True)
        shutil.rmtree(out, ignore_errors=True)
    text = buf.getvalue()
    # A chunk that died keeps its logs for whoever reads the message.
    for kept in re.findall(r"\(log: (.+?)[\\/]log_\d+\.txt\)", text):
        shutil.rmtree(kept, ignore_errors=True)
    by_file = dict(re.findall(r"=== (\S+) ===[^\n]*\n(.*?)(?=\n=== |\n=+\n)",
                              text, flags=re.S))
    after = [_bytes(p) for p in (_REAL.durations, _REAL.test_times,
                                 _REAL.serial)]
    return {"code": code, "text": text, "by_file": by_file, "marks": marks,
            "machine_untouched": after == real}


_RUNS: dict = {}


def _once(key: str, files: dict, **kw) -> dict:
    if key not in _RUNS:
        _RUNS[key] = _run(files, **kw)
    return _RUNS[key]


def _serial():
    return _once("serial", _CLEAN)


def _jobs():
    return _once("jobs", _CLEAN, jobs=3)


def _totals(text: str) -> str:
    return next(line for line in text.splitlines()
                if line.startswith("Total:"))


def _leaks_of(run: dict, name: str) -> list:
    return [line.split("[LEAK] ", 1)[1]
            for line in run["by_file"][name].splitlines()
            if "✗ [LEAK]" in line]


class TestTheSameRunAsTheSerialOne:
    def test_both_pass(self):
        assert _serial()["code"] == 0, _serial()["text"]
        assert _jobs()["code"] == 0, _jobs()["text"]

    def test_the_same_totals(self):
        assert _totals(_jobs()["text"]) == _totals(_serial()["text"]) == \
            "Total: 11    Passed: 11    Failed: 0"

    def test_every_file_once_in_order_and_the_lane_last(self):
        heads = re.findall(r"=== (\S+) ===", _jobs()["text"])
        assert heads == ["test_a_one.py", "test_b_three.py", "test_d_one.py",
                         "test_e_four.py", "test_f_one.py", "test_c_clock.py"]

    def test_the_progress_is_counted_over_the_whole_run(self):
        tags = re.findall(r"\[\s*(\d+)/(\d+)\s+\d+%\]", _jobs()["text"])
        assert [int(a) for a, _ in tags] == list(range(1, 12))
        assert {b for _, b in tags} == {"11"}

    def test_it_says_it_ran_in_chunks_after_the_totals(self):
        lines = _jobs()["text"].splitlines()
        at = next(i for i, x in enumerate(lines) if x.startswith("Total:"))
        assert lines[at + 1] == "PARALLEL RUN — 3 chunk(s) + serial lane"

    def test_a_repository_with_no_serial_rule_is_told_nothing_of_one(self):
        # ``serial_every`` is OGR Slip2D's rule; with none set the run does
        # not ask for a serial run nobody decided (test_runner_fast_v020
        # holds the other half: with a number, it does).
        assert "SERIAL RUN" not in _jobs()["text"]
        assert "last full serial run" not in _jobs()["text"]


class TestTheChunks:
    def test_three_processes_each_a_contiguous_piece(self):
        m = _jobs()["marks"]
        order = ["a1", "b1", "b2", "b3", "d1", "e1", "e2", "e3", "e4", "f1"]
        pids = [m[k]["pid"] for k in order]
        runs = [p for p, _ in itertools.groupby(pids)]
        assert len(runs) == len(set(runs)) == 3, pids
        assert os.getpid() not in pids

    def test_the_lane_runs_alone_after_every_chunk(self):
        m = _jobs()["marks"]
        lane = m["c1"]
        others = [v for k, v in m.items() if k != "c1"]
        assert lane["pid"] not in {v["pid"] for v in others}
        assert lane["t"] > max(v["t"] for v in others)

    def test_the_serial_run_is_one_process_this_one(self):
        assert {v["pid"] for v in _serial()["marks"].values()} == {os.getpid()}


class TestPartition:
    def _best(self, weights, n):
        """The lightest heaviest slice, by trying every set of borders."""
        best = None
        for cuts in itertools.combinations(range(1, len(weights)), n - 1):
            edges = (0, *cuts, len(weights))
            heaviest = max(sum(weights[a:b]) for a, b in zip(edges, edges[1:]))
            best = heaviest if best is None else min(best, heaviest)
        return best

    def test_contiguous_covering_and_optimal(self):
        cases = [([5, 1, 1, 1, 1, 1], 2), ([1, 2, 3, 4, 5, 6, 7], 3),
                 ([3, 3, 3, 3], 4), ([9, 1, 9, 1, 9], 3),
                 ([0.4, 7.1, 0.2, 0.2, 3.3, 2.9, 1.0, 5.5], 3)]
        for weights, n in cases:
            parts = _R.partition(weights, n)
            assert parts[0][0] == 0 and parts[-1][1] == len(weights)
            assert all(a < b for a, b in parts)
            assert all(p[1] == q[0] for p, q in zip(parts, parts[1:]))
            heaviest = max(sum(weights[a:b]) for a, b in parts)
            assert abs(heaviest - self._best(weights, n)) < 1e-6, (weights, n)

    def test_as_many_chunks_as_asked_without_a_heavier_one(self):
        # the greedy fill at the best capacity (5) packs these into two
        weights = [1, 3, 1, 4, 1]
        parts = _R.partition(weights, 3)
        assert len(parts) == 3
        assert max(sum(weights[a:b]) for a, b in parts) == 5

    def test_more_processes_than_files(self):
        assert _R.partition([2, 1], 8) == [(0, 1), (1, 2)]
        assert _R.partition([], 4) == []

    def test_a_file_never_timed_costs_its_tests_at_the_median_rate(self):
        files = [Path("test_x.py"), Path("test_y.py"), Path("test_z.py")]
        counts = {"test_x.py": 10, "test_y.py": 4, "test_z.py": 2}
        w = _R.file_weights(files, counts, {"test_x.py": 20.0,
                                            "test_y.py": 4.0})
        # rates 2.0 and 1.0: the median of two is the upper one
        assert w == [20.0, 4.0, 4.0]


class TestTheLaneMarker:
    def test_read_from_the_source_without_running_it(self):
        folder = Path(tempfile.mkdtemp(prefix="ogr_test_jobs_lane_"))
        try:
            cases = {"yes": "SERIAL_LANE = True\nraise SystemExit(9)\n",
                     "no": "SERIAL_LANE = False\n",
                     "computed": "SERIAL_LANE = bool(1)\n",
                     "absent": "X = 1\n",
                     "broken": "SERIAL_LANE = True\ndef (:\n"}
            seen = {}
            for name, text in cases.items():
                p = folder / f"test_{name}.py"
                p.write_text(text, encoding="utf-8")
                seen[name] = _R.serial_lane(p)
            assert seen == {"yes": True, "no": False, "computed": False,
                            "absent": False, "broken": False}
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class TestTheInjectedLeaksFailTheirFileInAChunk:
    def _run(self):
        return _once("leaks", _LEAKY, jobs=2)

    def test_each_leak_under_its_own_file(self):
        run = self._run()
        assert any(x.startswith("cwd: ")
                   for x in _leaks_of(run, "test_a_folder.py"))
        assert any(x.startswith("env:OGR_TEST_INJECTED_LEAK_V020:")
                   for x in _leaks_of(run, "test_b_environment.py"))
        assert any("CONTAINS_TOL: 1e-09 → 1.0" in x
                   for x in _leaks_of(run, "test_c_constant.py"))
        assert any(x.startswith("cls:ogr_core.fem.mesh.Mesh.locate")
                   for x in _leaks_of(run, "test_d_method.py"))
        assert _leaks_of(run, "test_e_puts_back.py") == []

    def test_the_run_fails_as_the_serial_one_does(self):
        run = self._run()
        assert run["code"] == 1
        assert _totals(run["text"]) == \
            "Total: 5    Passed: 5    Failed: 0    Leaks: 4"


class TestAChunkThatDiesFailsTheRun:
    def _run(self):
        return _once("dying", _DYING, jobs=2)

    def test_named_with_its_code_its_file_and_what_did_not_finish(self):
        run = self._run()
        assert run["code"] == 1
        line = next(x for x in run["text"].splitlines()
                    if x.startswith("✗ [CHUNK]"))
        assert "chunk 1/2 died: exit 3 in test_b_dies.py, after " \
               "test_a_ok.py; 3 of its 4 file(s) did not finish" in line

    def test_the_other_chunk_still_reports(self):
        run = self._run()
        assert "test_e_other.py" in run["by_file"]
        assert _totals(run["text"]) == \
            "Total: 6    Passed: 6    Failed: 0    Chunks died: 1"

    def test_the_files_after_it_never_ran(self):
        heads = re.findall(r"=== (\S+) ===", self._run()["text"])
        assert "test_c_after.py" not in heads
        assert "test_d_after.py" not in heads


class TestTheRunIsTheRunDeclared:
    def test_a_test_the_source_does_not_declare_fails_it(self):
        run = _once("undeclared", _UNDECLARED, jobs=2)
        assert run["code"] == 1
        assert "the source declares 2 test(s) and the chunks ran 3" \
            in run["text"]


class TestAChunkEntersThroughTheRepositorysRunner:
    def test_a_folder_with_no_runner_is_checked_with_the_suites_list(self):
        run = _once("bare", _TOLERANCE, jobs=2)
        assert run["code"] == 1, run["text"]
        assert _leaks_of(run, "test_a_tolerance.py") == [
            "mod:ogr_core.fem.mesh.DEGENERATE_DET: 1e-15 → 0.5"]

    def test_with_its_own_runner_the_chunk_gets_what_it_adds(self):
        run = _once("own", _TOLERANCE, own_runner=True, jobs=2)
        assert run["code"] == 0, run["text"]
        assert _leaks_of(run, "test_a_tolerance.py") == []
        assert _totals(run["text"]) == "Total: 2    Passed: 2    Failed: 0"


class TestTheTemporaryFolderIsSettledBeforeTheFirstFile:
    """``tempfile`` works out the temporary folder on its first use in a
    process and keeps it. A chunk is a fresh process: unless the runner
    settles it first, the leak check names it at whichever file happens to
    make the first temporary file (four files of this suite, the first time
    it ran with --jobs 4)."""

    def _run(self):
        # two chunks of one file: each file is the first of its process
        return _once("temporary", _TEMPORARY, jobs=2)

    def test_the_first_use_in_a_chunk_is_not_named(self):
        assert _leaks_of(self._run(), "test_a_first_use.py") == []

    def test_a_file_that_moves_it_is(self):
        run = self._run()
        got = _leaks_of(run, "test_b_moves_it.py")
        assert len(got) == 1 and got[0].startswith("tempfile.tempdir: "), got
        # from the folder the runner settled, not from "not worked out yet"
        assert not got[0].startswith("tempfile.tempdir: None"), got
        assert _totals(run["text"]) == \
            "Total: 2    Passed: 2    Failed: 0    Leaks: 1"


class TestWhatIsKeptOnTheMachine:
    def test_a_run_with_no_label_keeps_nothing(self):
        assert _jobs()["machine_untouched"]
        assert _serial()["machine_untouched"]

    def test_durations_are_merged_into_what_was_there(self):
        folder = Path(tempfile.mkdtemp(prefix="ogr_test_jobs_durations_"))
        try:
            path = folder / "d.json"
            _R.save_durations({"test_a.py": 1.23456}, path)
            _R.save_durations({"test_b.py": 2.0}, path)
            _R.save_durations({"test_a.py": 3.0}, path)
            assert _R.load_durations(path) == {"test_a.py": 3.0,
                                               "test_b.py": 2.0}
            assert _R.load_durations(folder / "absent.json") == {}
            assert _R.load_durations(None) == {}
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_a_label_names_the_three_files(self):
        r = _R.records_for("ogr-slip2d")
        tmp = Path(tempfile.gettempdir())
        # the names OGR Slip2D's own runner used: adopting this one loses
        # none of the times it measured
        assert (r.durations, r.test_times, r.serial) == (
            tmp / "ogr-slip2d-test-durations.json",
            tmp / "ogr-slip2d-test-times.json",
            tmp / "ogr-slip2d-serial-run.json")
