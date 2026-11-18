# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.0 — the runner puts back, after every file, what a file leaves in
the process for every file after it, and freezes what survives the
collection it makes between files.

Moved from OGR Slip2D's ``test_runner_state_v1373`` with the runner (OGR
Core 0.2.0). The two folders Slip2D's runner gave every run (settings and
bridges) are here whatever folders the repository asks for
(``run_folders``): the core asks for none, a program for its own.

Invariants protected:

1. **``sys.path`` after a file is what it was before it.** In Slip2D 242
   files inserted ``tests/`` at import and nothing took it out: 369 entries
   at the end of the suite. Every ``spawn`` worker of a process pool gets
   that list and walks it with one ``stat`` per entry for each module it
   imports; a pool of 4 cost 0.5–0.7 s with 12 entries and 2.4–3.6 s with
   369, measured A/B in one process (its audit of v0.1.372, §4.3). Inside
   its own file the insert is still seen: that is what the file asked for.
2. **The folders the run gave itself are put back too**, and each run gets
   its own: a file that repoints one does not move it for the next file.
   A repository that asks for none gets none (rule 7: the option decides).
3. **What survives the collection between files is frozen**
   (``gc.freeze``), so the next full collection walks only what was made
   since. Each one cost ~320 ns per live object, 3.4 s per file at the end
   of Slip2D's suite: 13.6 of its 87.6 minutes (audit §3). And the order is
   the program's hook, then collect, then freeze: the previous file's
   garbage is still freed, on the main thread.

How: ``main()`` over two throwaway test files in a temporary folder. The
first inserts a marker into ``sys.path`` at import, keeps 5000 lists alive
and repoints the run's folder in a test; the second writes down what it
sees.

A trap, as in ``test_runner_selection_v10``: the inner ``main()`` runs only
the throwaway folder, never ``tests/``, or this file would run itself.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from ogr_core.testing import runner as _R

_VAR = "OGR_TEST_STATE_FOLDER_V020"

_FIRST = '''
import gc, json, os, sys
OUT = {out!r}
MARK = {mark!r}
VAR = {var!r}
sys.path.insert(0, MARK)
KEEP = [[] for _ in range(5000)]          # alive, tracked: frozen next
with open(OUT + ".a.json", "w") as fh:
    json.dump({{"folder": os.environ.get(VAR),
               "frozen": gc.get_freeze_count()}}, fh)


class TestFirst:
    def test_its_own_insert_is_seen(self):
        assert MARK in sys.path

    def test_repoints_the_folder(self):
        os.environ[VAR] = MARK
'''

_SECOND = '''
import gc, json, os, sys
OUT = {out!r}
MARK = {mark!r}
VAR = {var!r}


class TestSecond:
    def test_writes_what_it_sees(self):
        with open(OUT + ".b.json", "w") as fh:
            json.dump({{"mark": MARK in sys.path,
                       "folder": os.environ.get(VAR),
                       "frozen": gc.get_freeze_count()}}, fh)
'''

_SEEN: dict = {}


def _seen(with_folder: bool = True) -> dict:
    """Run the two throwaway files once, return what they wrote down."""
    if with_folder in _SEEN:
        return _SEEN[with_folder]
    folder = Path(tempfile.mkdtemp(prefix="ogr_test_runner_state_"))
    out = str(folder / "seen")
    mark = str(folder / "not-a-folder-on-the-path")
    (folder / "test_a_leaves.py").write_text(
        _FIRST.format(out=out, mark=mark, var=_VAR), encoding="utf-8")
    (folder / "test_b_records.py").write_text(
        _SECOND.format(out=out, mark=mark, var=_VAR), encoding="utf-8")
    saved_path = list(sys.path)
    saved_env = os.environ.get(_VAR)
    config = {"run_folders": {_VAR: "prefs"}} if with_folder else {}
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            code = _R.main(folder, **config)
        with open(out + ".a.json") as fh:
            a = json.load(fh)
        with open(out + ".b.json") as fh:
            b = json.load(fh)
    finally:
        # Rule 5: the inner main() set the run's folder of its own.
        sys.path[:] = saved_path
        if saved_env is None:
            os.environ.pop(_VAR, None)
        else:
            os.environ[_VAR] = saved_env
        # the modules the inner run imported by their stems
        for stem in ("test_a_leaves", "test_b_records"):
            sys.modules.pop(stem, None)
        shutil.rmtree(folder, ignore_errors=True)
    _SEEN[with_folder] = {"code": code, "text": buf.getvalue(), "a": a,
                          "b": b, "mark": mark}
    return _SEEN[with_folder]


class TestWhatAFileLeavesIsPutBack:
    def test_the_inner_run_passed(self):
        s = _seen()
        assert s["code"] == 0, s["text"]
        assert "Passed: 3" in s["text"], s["text"]

    def test_its_sys_path_insert_does_not_reach_the_next_file(self):
        assert _seen()["b"]["mark"] is False

    def test_the_folder_is_the_runs_again(self):
        s = _seen()
        assert s["a"]["folder"] is not None
        assert Path(s["a"]["folder"]).name.startswith("ogr_test_prefs_")
        assert s["b"]["folder"] == s["a"]["folder"]
        assert s["b"]["folder"] != s["mark"]

    def test_a_repository_that_asks_for_no_folder_gets_none(self):
        s = _seen(with_folder=False)
        assert s["a"]["folder"] is None
        # and then nothing puts the variable back: the file that set it is
        # named, as for any other variable it leaves in the environment
        assert s["code"] == 1, s["text"]
        assert f"✗ [LEAK] env:{_VAR}: (absent) → " in s["text"], s["text"]


class TestWhatSurvivesIsFrozen:
    def test_the_lists_kept_by_the_first_file_are_frozen_before_the_second(self):
        s = _seen()
        # 5000 lists made after the freeze that preceded the first file,
        # still alive: the collection before the second file froze them.
        assert s["b"]["frozen"] >= s["a"]["frozen"] + 5000, (s["a"], s["b"])

    def test_the_loop_frees_on_the_main_thread_collects_then_freezes(self):
        src = Path(_R.__file__).read_text(encoding="utf-8")
        loop = src[src.index("for i_file, f in enumerate(test_files, 1):"):]
        loop = loop[:loop.index('print(f"\\n=== {f.name}')]
        # collected first: the previous file's garbage is still freed
        assert (loop.index("around.hooks.before_file()")
                < loop.index("gc.collect()") < loop.index("gc.freeze()"))
