# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.1.0 — the runner says which tree it is measuring, and refuses a foreign
one.

Moved with the runner from OGR Slip2D's ``test_runner_provenance_v189``
(spec 009, decision P4). Its reason is unchanged: diagnosing a fall in
Slip2D v0.1.84, a script kept outside the repository measured the
installed tree instead of the one being edited, because ``pip install -e``
resolves every ``ogr_*`` to one hard-coded path — and said nothing.

Invariants protected:

* this repository's own package resolves inside it, and nothing here is a
  stranger;
* a package outside the root, one that does not resolve, and one in a
  sibling tree whose name starts the same are all flagged;
* the refusal names the offender and this tree, exits 2, and runs nothing;
* resolving executes nothing (``find_spec``, never an import);
* the banner is one line naming the tree, and lists every package when the
  tree is split.

The shared packages a program takes from the core are in
``test_runner_shared_v10``.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
from pathlib import Path

from ogr_core.testing import runner as _R

_TESTS = Path(__file__).resolve().parent
_ROOT = _TESTS.parent
_OWN = ("ogr_core",)


def _elsewhere(name: str) -> Path:
    base = Path("C:/some/other/tree") if sys.platform == "win32" \
        else Path("/some/other/tree")
    return base / name


class TestThisTreeIsTheOneMeasured:
    def test_the_own_package_resolves_inside_the_repository(self):
        origins = _R.package_origins(_OWN)
        assert set(origins) == set(_OWN), origins
        for name, where in origins.items():
            assert where is not None, f"{name} is not importable at all"
            where.relative_to(_ROOT)

    def test_no_strangers_here(self):
        assert _R.foreign_packages(_R.package_origins(_OWN), _ROOT) == []

    def test_each_package_is_its_own_directory_under_the_root(self):
        """Guards the banner: it collapses the paths into one by taking
        their common PARENT, which is only right if each package really is
        a directory directly under the tree."""
        for name, where in _R.package_origins(_OWN).items():
            assert where.name == name, (name, where)
            assert where.parent == _ROOT, (name, where.parent)


class TestAForeignPackageIsRefused:
    """Synthetic cases: real ones cannot be built without breaking the
    interpreter this suite runs in, so the check is a pure function of
    ``(origins, root)`` precisely so it can be tested with data."""

    def test_a_package_outside_the_root_is_flagged(self):
        origins = {"ogr_core": _ROOT / "ogr_core",
                   "ogr_slip2d": _elsewhere("ogr_slip2d")}
        bad = _R.foreign_packages(origins, _ROOT)
        assert [n for n, _ in bad] == ["ogr_slip2d"], bad

    def test_a_package_that_does_not_resolve_is_flagged(self):
        bad = _R.foreign_packages({"ogr_core": None}, _ROOT)
        assert [n for n, _ in bad] == ["ogr_core"], bad

    def test_a_sibling_tree_is_not_mistaken_for_this_one(self):
        """``OGR-Core-copy`` starts with the same characters as
        ``OGR-Core``. A prefix comparison on strings would accept it;
        ``relative_to`` on paths does not."""
        sibling = _ROOT.parent / (_ROOT.name + "-copy") / "ogr_core"
        bad = _R.foreign_packages({"ogr_core": sibling}, _ROOT)
        assert [n for n, _ in bad] == ["ogr_core"], bad

    def test_the_message_names_the_offender_and_this_tree(self):
        buf = io.StringIO()
        saved = _R.package_origins
        try:
            _R.package_origins = lambda names: {
                n: _elsewhere(n) for n in names}
            with contextlib.redirect_stdout(buf):
                code = _R.main(_TESTS, own=_OWN)
        finally:
            _R.package_origins = saved
        text = buf.getvalue()
        assert code == 2, code
        assert "WRONG TREE" in text, text
        assert "ogr_core" in text, text
        assert str(_ROOT) in text, text
        assert "Total:" not in text, text


class TestResolutionExecutesNothing:
    def test_find_spec_does_not_execute_the_module(self):
        # A stdlib module this suite has no reason to have imported. If a
        # future dependency imports it, pick another rather than deleting it
        # from sys.modules: that would create a second copy with its own
        # globals, which is the very failure being guarded against.
        victim = next((n for n in ("colorsys", "wave", "mailbox", "netrc")
                       if n not in sys.modules), None)
        if victim is None:
            return          # nothing left to prove it with; not a failure
        spec = importlib.util.find_spec(victim)
        assert spec is not None and spec.origin, victim
        assert victim not in sys.modules, \
            f"find_spec executed {victim}; the guard would leak state"

    def test_package_origins_is_written_that_way(self):
        """Source-level, because the property above is only preserved as
        long as nobody 'simplifies' this into an import."""
        src = Path(_R.__file__).read_text(encoding="utf-8")
        body = src.split("def package_origins")[1].split("\ndef ")[0]
        assert "find_spec" in body, body
        for forbidden in ("import_module", "__import__"):
            assert forbidden not in body, forbidden


class TestTheBannerSaysSomethingUseful:
    def test_it_is_one_line_naming_the_tree(self):
        line = _R.provenance(_ROOT, _R.package_origins(_OWN))
        assert "\n" not in line, line
        assert str(_ROOT) in line, line
        assert line.startswith("tree: "), line
        assert "(1 ogr package)" in line, line

    def test_it_falls_back_to_listing_when_the_tree_is_not_single(self):
        origins = {"ogr_core": _ROOT / "ogr_core",
                   "ogr_gui": _elsewhere("ogr_gui")}
        line = _R.provenance(_ROOT, origins)
        assert "ogr_core=" in line and "ogr_gui=" in line, line

    def test_with_no_own_package_it_still_names_the_tree(self):
        line = _R.provenance(_ROOT, {})
        assert line.startswith(f"tree: {_ROOT}"), line

    def test_head_sha_never_raises_and_looks_like_a_sha(self):
        sha = _R.head_sha(_ROOT)
        assert sha == "?" or (len(sha) == 7
                              and all(c in "0123456789abcdef" for c in sha)), \
            sha

    def test_head_sha_on_a_directory_without_git(self):
        """The banner must not be able to fail. A missing .git is a '?',
        not a traceback that stops the suite before it starts."""
        assert _R.head_sha(Path(tempfile.mkdtemp())) == "?"


_SHA = "0123456789abcdef0123456789abcdef01234567"


class TestTheCommitOfAWorktree:
    """Spec 009 of OGR Slip2D ran its first phase in a worktree, and the
    banner said ``@ ?``. Built here as git lays it out: the worktree's
    ``.git`` is a file, its HEAD is in ``.git/worktrees/<name>``, and the
    branch it names lives in the common directory, loose or packed."""

    def _layout(self, packed: bool) -> Path:
        base = Path(tempfile.mkdtemp(prefix="ogr_worktree_"))
        common = base / "main" / ".git"
        wt_git = common / "worktrees" / "f1"
        wt_git.mkdir(parents=True)
        (wt_git / "HEAD").write_text("ref: refs/heads/dev/x\n", encoding="utf-8")
        (wt_git / "commondir").write_text("../..\n", encoding="utf-8")
        if packed:
            (common / "packed-refs").write_text(
                "# pack-refs with: peeled fully-peeled sorted\n"
                f"{_SHA} refs/heads/dev/x\n", encoding="utf-8")
        else:
            (common / "refs" / "heads" / "dev").mkdir(parents=True)
            (common / "refs" / "heads" / "dev" / "x").write_text(
                _SHA + "\n", encoding="utf-8")
        tree = base / "f1"
        tree.mkdir()
        (tree / ".git").write_text(f"gitdir: {wt_git}\n", encoding="utf-8")
        return tree

    def test_a_loose_branch(self):
        assert _R.head_sha(self._layout(packed=False)) == _SHA[:7]

    def test_a_packed_branch(self):
        assert _R.head_sha(self._layout(packed=True)) == _SHA[:7]

    def test_a_detached_head_in_an_ordinary_repository(self):
        repo = Path(tempfile.mkdtemp(prefix="ogr_detached_"))
        (repo / ".git").mkdir()
        (repo / ".git" / "HEAD").write_text(_SHA + "\n", encoding="utf-8")
        assert _R.head_sha(repo) == _SHA[:7]


class TestTheGuardDidNotBreakTheSelection:
    def test_a_pattern_matching_nothing_still_exits_two(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = _R.main(_TESTS, patterns=["definitivamente-no-existe"],
                           own=_OWN)
        assert code == 2, code
        assert "tree: " in buf.getvalue()

    def test_list_only_still_reports_success(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = _R.main(_TESTS, patterns=["runner_provenance"],
                           list_only=True, own=_OWN)
        assert code == 0, code
        assert "Nothing was run." in buf.getvalue()
