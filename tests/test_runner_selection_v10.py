# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.1.0 — running part of a suite selects a part, and says so.

Moved with the runner from OGR Slip2D's ``test_runner_selection_v180``
(spec 009, decision P4). There it measured Slip2D's own 400-odd files; the
core's suite is small, so the cases here run on a synthetic ``tests``
directory built for this file, with a known number of files and tests —
which also lets the counts be asserted exactly instead of "more than a
thousand".

Invariants protected:

1. **with no selection the runner runs exactly what it always ran**: the
   file list is ``sorted(glob("test_*.py"))``, unreordered, because that is
   the command CI runs;
2. **a selection that matches nothing exits 2**, names what was asked and
   suggests what was probably meant — otherwise a typo prints ``Total: 0``
   and reads as a suite that passed;
3. counting and listing the selection **execute nothing**: one synthetic
   file raises at import, and it must be counted and listed all the same.

A trap for whoever edits this file: ``main()`` is only called here on the
synthetic tree, never on this repository's ``tests`` — a call that reached
the run loop there would run this file inside itself.
"""
from __future__ import annotations

import contextlib
import io
import tempfile
from pathlib import Path

from ogr_core.testing import runner as _R


def _make_tree() -> Path:
    tests = Path(tempfile.mkdtemp(prefix="ogr_runner_selection_")) / "tests"
    tests.mkdir()
    (tests / "test_alpha_v1.py").write_text(
        "class TestA:\n"
        "    def test_one(self): pass\n"
        "    def test_two(self): pass\n"
        "class TestB:\n"
        "    def test_three(self): pass\n"
        "    def helper(self): pass\n", encoding="utf-8")
    (tests / "test_beta_geometry_v2.py").write_text(
        "class TestGeometry:\n"
        "    def test_matching_ignores_case(self): pass\n", encoding="utf-8")
    # Executing this file at selection time would raise: counting and
    # listing must read it without running it.
    (tests / "test_gamma_v3.py").write_text(
        "raise RuntimeError('executed at selection time')\n"
        "class TestC:\n"
        "    def test_four(self): pass\n", encoding="utf-8")
    (tests / "helper_not_a_test.py").write_text("x = 1\n", encoding="utf-8")
    return tests


_TREE = _make_tree()
_ALPHA = _TREE / "test_alpha_v1.py"


def _quiet_main(**kwargs) -> tuple[int, str]:
    """``main()`` on the synthetic tree with its output captured.

    No own packages: the synthetic tree contains none, and what is under
    test here is the selection, not the tree check."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = _R.main(_TREE, own=(), **kwargs)
    return code, buf.getvalue()


class TestTheCiPathIsUntouched:
    def test_no_patterns_selects_every_file(self):
        expected = sorted(_TREE.glob("test_*.py"))
        assert len(expected) == 3, expected
        assert _R.select_files(_TREE, ()) == expected
        assert _R.select_files(_TREE, []) == expected
        assert _R.select_files(_TREE, None) == expected

    def test_no_patterns_counts_every_test_exactly(self):
        assert _R._count_tests(_R.select_files(_TREE, ())) == 5

    def test_selection_never_reorders(self):
        picked = _R.select_files(_TREE, ["test_"])
        assert picked == sorted(picked)
        assert picked == _R.select_files(_TREE, ())


class TestFileSelection:
    def test_a_pattern_selects_strictly_fewer_files(self):
        """Rule 7: the control has to move the number."""
        picked = _R.select_files(_TREE, ["alpha"])
        assert picked == [_ALPHA]

    def test_several_patterns_are_a_union(self):
        a = set(_R.select_files(_TREE, ["alpha"]))
        b = set(_R.select_files(_TREE, ["geometry"]))
        both = set(_R.select_files(_TREE, ["alpha", "geometry"]))
        assert a and b
        assert both == a | b

    def test_a_file_name_and_a_path_select_the_same_file(self):
        """All three shapes a pattern arrives in must agree, and none of
        them may depend on the current directory."""
        by_fragment = _R.select_files(_TREE, ["alpha"])
        assert by_fragment == _R.select_files(_TREE, [_ALPHA.name])
        assert by_fragment == _R.select_files(_TREE, ["tests/" + _ALPHA.name])
        assert by_fragment == _R.select_files(_TREE, [str(_ALPHA)])

    def test_matching_ignores_case(self):
        assert (_R.select_files(_TREE, ["ALPHA"])
                == _R.select_files(_TREE, ["alpha"]))

    def test_an_empty_pattern_selects_nothing_rather_than_everything(self):
        """An empty substring is inside every name, so the naive rule
        would silently select the whole suite while looking like a
        filter. It has to reach the empty-selection guard instead."""
        assert _R.select_files(_TREE, [""]) == []
        assert _R.select_files(_TREE, ["/"]) == []
        assert _R.select_files(_TREE, [".py"]) == []


class TestNameFilter:
    def test_k_selects_only_matching_methods(self):
        picked = _R._declared_tests([_ALPHA], "two")
        assert [m for _, _, m in picked] == ["test_two"]

    def test_k_matches_the_class_name_too(self):
        picked = _R._declared_tests([_ALPHA], "TestB")
        assert [(c, m) for _, c, m in picked] == [("TestB", "test_three")]

    def test_k_ignores_case(self):
        assert _R.match_test("TestX", "test_foo", "TEST_FOO")
        assert _R.match_test("TestX", "test_foo", "testx.TEST_")
        assert not _R.match_test("TestX", "test_foo", "test_bar")

    def test_no_k_keeps_everything(self):
        assert _R.match_test("TestX", "test_foo", None)
        assert _R.match_test("TestX", "test_foo", "")

    def test_methods_that_are_not_tests_are_not_counted(self):
        names = [m for _, _, m in _R._declared_tests([_ALPHA])]
        assert "helper" not in names and len(names) == 3, names


class TestAnEmptySelectionIsAnError:
    def test_a_file_pattern_matching_nothing_exits_two(self):
        code, out = _quiet_main(patterns=["no-such-file-anywhere"])
        assert code == 2
        assert "no-such-file-anywhere" in out
        assert "Total:" not in out

    def test_a_k_matching_nothing_exits_two(self):
        code, out = _quiet_main(patterns=["alpha"],
                                k="no-such-test-name-anywhere")
        assert code == 2
        assert "no-such-test-name-anywhere" in out

    def test_a_typo_is_told_what_it_probably_meant(self):
        code, out = _quiet_main(patterns=["test_alfa"])
        assert code == 2
        assert "test_alpha_v1" in out, out


class TestListOnly:
    def test_list_only_reports_success_without_running_anything(self):
        """``test_gamma_v3`` raises when executed: listing it is proof that
        nothing was."""
        code, out = _quiet_main(list_only=True)
        assert code == 0, out
        assert "Nothing was run." in out
        assert "test_gamma_v3.py::TestC::test_four" in out
        assert "5 test(s) in 3 file(s) of 3" in out


class TestArgumentParsing:
    def test_no_arguments_means_no_filter(self):
        ns = _R._parse_args([])
        assert ns.patterns == [] and ns.k is None and ns.list_only is False

    def test_patterns_and_k_and_list_are_read(self):
        ns = _R._parse_args(["transient", "seepage", "-k", "erfc", "--list"])
        assert ns.patterns == ["transient", "seepage"]
        assert ns.k == "erfc"
        assert ns.list_only is True
