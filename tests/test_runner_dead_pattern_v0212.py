# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
OGR Core 0.2.12 (D431) — a pattern that matches no file exits 2 even when
other patterns match.

``select_files`` is a union, and the only guard was an empty selection: a
misspelled pattern beside one that matched was dropped, said nowhere.
Measured by OGR Slip2D with 0.2.10: ``--list transient zz_no_casa_d431``
gave exit 0 and «125 test(s) in 5 file(s)», without naming the second
pattern. It bit in its 0.1.439, whose changelog said three areas were
tested that nobody ran, and again in its 0.1.445. The owner's decision:
exit 2, before anything is run.

Invariants:

* a dead pattern beside a live one exits 2, names the dead one as it was
  typed, suggests what it probably meant and runs nothing -- also with
  ``--list`` and with ``--jobs``;
* without the dead pattern the same command exits 0 (rule 7);
* a pattern that normalises to nothing is not a dead pattern; every
  pattern dead still says what it always said.

Like ``test_runner_selection_v10``, ``main()`` runs only on a synthetic
tree, never on this repository's ``tests``.
"""
from __future__ import annotations

import contextlib
import io
import tempfile
from pathlib import Path

from ogr_core.testing import runner as _R


def _make_tree() -> Path:
    tests = Path(tempfile.mkdtemp(prefix="ogr_runner_dead_")) / "tests"
    tests.mkdir()
    (tests / "test_alpha_v1.py").write_text(
        "class TestA:\n"
        "    def test_one(self): pass\n"
        "    def test_two(self): pass\n", encoding="utf-8")
    (tests / "test_beta_geometry_v2.py").write_text(
        "class TestGeometry:\n"
        "    def test_three(self): pass\n", encoding="utf-8")
    # executing this file would raise: a refusal must not reach it
    (tests / "test_gamma_v3.py").write_text(
        "raise RuntimeError('executed')\n"
        "class TestC:\n"
        "    def test_four(self): pass\n", encoding="utf-8")
    return tests


_TREE = _make_tree()
_DEAD = "no-such-file-anywhere"


def _main(**kwargs) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = _R.main(_TREE, own=(), **kwargs)
    return code, buf.getvalue()


class TestUnmatchedPatterns:

    def test_it_names_the_dead_ones_as_typed(self):
        path = "tests/test_zz_v9.py"
        assert _R.unmatched_patterns(
            _TREE, ["alpha", _DEAD, "GEOMETRY", path]) == [_DEAD, path]

    def test_a_live_pattern_is_not_one(self):
        assert _R.unmatched_patterns(_TREE, ["alpha", "beta"]) == []
        assert _R.unmatched_patterns(_TREE, []) == []

    def test_a_pattern_that_normalises_to_nothing_is_not_one(self):
        assert _R.unmatched_patterns(_TREE, ["", "/", ".py"]) == []


class TestADeadPatternBesideALiveOne:

    def test_exits_two_and_names_it(self):
        code, out = _main(patterns=["alpha", _DEAD])
        assert code == 2, out
        assert f"No test file matches ['{_DEAD}']" in out, out
        assert "the other pattern(s) select 1 file(s)" in out, out
        assert "Total:" not in out and "FILTERED RUN" not in out, out

    def test_the_same_command_without_it_exits_zero(self):
        """Rule 7: adding the dead pattern is what moves the exit code."""
        assert _main(patterns=["alpha"], list_only=True)[0] == 0
        assert _main(patterns=["alpha", _DEAD], list_only=True)[0] == 2

    def test_with_list(self):
        code, out = _main(patterns=["alpha", _DEAD], list_only=True)
        assert code == 2, out
        assert _DEAD in out
        assert "Nothing was run." not in out
        assert "::TestA::" not in out, out

    def test_with_jobs(self):
        for list_only in (True, False):
            code, out = _main(patterns=["alpha", "gamma", _DEAD], jobs=2,
                              list_only=list_only)
            assert code == 2, out
            assert "Total:" not in out and "executed" not in out, out

    def test_a_typo_is_told_what_it_probably_meant(self):
        code, out = _main(patterns=["geometry", "test_alfa"])
        assert code == 2
        assert "Did you mean: test_alpha_v1" in out, out

    def test_said_before_a_k_that_matches_nothing(self):
        code, out = _main(patterns=["alpha", _DEAD], k="no-such-test")
        assert code == 2
        assert _DEAD in out and "No test name matches" not in out, out


class TestWhatDoesNotMove:

    def test_an_empty_pattern_beside_a_live_one_runs_the_live_one(self):
        code, out = _main(patterns=["alpha", ""], list_only=True)
        assert code == 0, out
        assert "2 test(s) in 1 file(s) of 3" in out, out

    def test_every_pattern_dead_says_what_it_always_said(self):
        code, out = _main(patterns=[_DEAD, "zz"])
        assert code == 2
        assert f"No test file matches ['{_DEAD}', 'zz'].\n" in out, out
        assert "the other pattern(s)" not in out

    def test_the_empty_pattern_alone_reaches_the_empty_selection(self):
        code, out = _main(patterns=[""])
        assert code == 2
        assert "No test file matches [''].\n" in out, out
