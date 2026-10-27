# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.1.0 — a program's runner names the core it takes, and refuses one it
does not pin.

New with the extraction (OGR Slip2D, spec 009). Until then every ``ogr_*``
package lived in one tree, and the runner refused any that resolved
outside it. A program now takes ``ogr_core`` from ANOTHER tree on purpose;
refusing it would refuse every run, and ignoring it would bring back the
v0.1.84 failure — a run measuring a tree it does not say. So a shared
package is NAMED (path, commit, version) and its version is checked
against the program's pin.

Invariants protected:

* a version is read from the source without executing it (the synthetic
  ``__init__`` below raises if it is ever run);
* a pin is the version of a git tag reference or of ``==``; a range is not
  a pin; another project whose name starts the same is not this one;
* a shared package that does not resolve, or whose version is not the
  pinned one, stops the run with exit 2, naming both versions and the path,
  and runs nothing; one that matches is named on a ``shared:`` line and the
  run goes on;
* a copy installed inside some other repository's ``.venv`` does not
  borrow that repository's commit;
* the hooks run once the trees are checked, ``before_file`` once per file,
  and neither runs when the run is refused.
"""
from __future__ import annotations

import contextlib
import io
import tempfile
from pathlib import Path

from ogr_core.testing import runner as _R


def _package(version_line: str = '__version__ = "0.1.0"\n',
             git: bool = False) -> Path:
    """A synthetic package directory whose ``__init__`` raises if run."""
    repo = Path(tempfile.mkdtemp(prefix="ogr_runner_shared_"))
    if git:
        (repo / ".git").mkdir()
        (repo / ".git" / "HEAD").write_text(
            "0123456789abcdef0123456789abcdef01234567\n", encoding="utf-8")
    pkg = repo / "ogr_core"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        '"""synthetic"""\n' + version_line +
        "raise RuntimeError('this __init__ was executed')\n",
        encoding="utf-8")
    return pkg


def _pyproject(*deps: str) -> Path:
    path = Path(tempfile.mkdtemp(prefix="ogr_runner_pin_")) / "pyproject.toml"
    body = ", ".join(f'"{d}"' for d in deps)
    path.write_text(f'[project]\nname = "x"\ndependencies = [{body}]\n',
                    encoding="utf-8")
    return path


def _tree_with_one_passing_test() -> Path:
    tests = Path(tempfile.mkdtemp(prefix="ogr_runner_run_")) / "tests"
    tests.mkdir()
    (tests / "test_synthetic_shared_v1.py").write_text(
        "class TestOne:\n    def test_passes(self): assert True\n",
        encoding="utf-8")
    (tests / "test_synthetic_shared_v2.py").write_text(
        "class TestTwo:\n    def test_passes(self): assert True\n",
        encoding="utf-8")
    return tests


def _run(tests: Path, **config) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = _R.main(tests, own=(), **config)
    return code, buf.getvalue()


class TestTheVersionIsReadNotRun:
    def test_it_reads_a_plain_assignment(self):
        assert _R.declared_version(_package()) == "0.1.0"

    def test_it_reads_an_annotated_assignment(self):
        pkg = _package('__version__: str = "0.2.3"\n')
        assert _R.declared_version(pkg) == "0.2.3"

    def test_no_version_no_package_no_init(self):
        assert _R.declared_version(_package("")) is None
        assert _R.declared_version(None) is None
        assert _R.declared_version(Path(tempfile.mkdtemp())) is None

    def test_the_cores_own_version_is_the_one_in_pyproject(self):
        """The two sites of rule 9 of AGENTS.md agree, read the way a
        program's runner reads them."""
        import tomllib
        root = Path(__file__).resolve().parent.parent
        declared = tomllib.loads((root / "pyproject.toml").read_text(
            encoding="utf-8"))["project"]["version"]
        assert _R.declared_version(root / "ogr_core") == declared


class TestWhatCountsAsAPin:
    def test_a_git_tag_reference(self):
        p = _pyproject(
            "ogr-core @ git+https://github.com/samuelsl27/OGR-Core@v0.1.0")
        assert _R.pinned_from_pyproject(p, "ogr-core") == "0.1.0"

    def test_an_exact_version(self):
        assert _R.pinned_from_pyproject(
            _pyproject("ogr-core==0.1.7"), "ogr-core") == "0.1.7"

    def test_spelling_of_the_name_does_not_matter(self):
        assert _R.pinned_from_pyproject(
            _pyproject("OGR_Core==0.1.7"), "ogr-core") == "0.1.7"

    def test_extras_and_markers_are_ignored(self):
        assert _R.pinned_from_pyproject(
            _pyproject("ogr-core[x]==0.1.7; python_version >= '3.11'"),
            "ogr-core") == "0.1.7"

    def test_a_range_is_not_a_pin(self):
        assert _R.pinned_from_pyproject(
            _pyproject("ogr-core>=0.1"), "ogr-core") is None

    def test_a_branch_is_not_a_pin(self):
        assert _R.pinned_from_pyproject(
            _pyproject("ogr-core @ git+https://github.com/samuelsl27/OGR-Core@main"),
            "ogr-core") is None

    def test_another_project_with_a_similar_name_is_not_this_one(self):
        assert _R.pinned_from_pyproject(
            _pyproject("ogr-coreutils==9.9", "numpy>=1.26"), "ogr-core") is None

    def test_a_missing_or_broken_file_is_no_pin(self):
        missing = Path(tempfile.mkdtemp()) / "pyproject.toml"
        assert _R.pinned_from_pyproject(missing, "ogr-core") is None
        broken = Path(tempfile.mkdtemp()) / "pyproject.toml"
        broken.write_text("[project\n", encoding="utf-8")
        assert _R.pinned_from_pyproject(broken, "ogr-core") is None


class TestTheSharedTreeIsChecked:
    def test_a_shared_package_that_does_not_resolve_is_a_problem(self):
        problems = _R.shared_problems({"ogr_core": None}, {})
        assert problems and "ogr_core" in problems[0], problems

    def test_a_version_that_is_not_the_pinned_one_is_a_problem(self):
        pkg = _package('__version__ = "0.1.1"\n')
        problems = _R.shared_problems({"ogr_core": pkg}, {"ogr_core": "0.1.0"})
        assert len(problems) == 1, problems
        assert "0.1.1" in problems[0] and "0.1.0" in problems[0]
        assert str(pkg) in problems[0]

    def test_the_pinned_version_is_no_problem(self):
        assert _R.shared_problems({"ogr_core": _package()},
                                  {"ogr_core": "0.1.0"}) == []

    def test_main_refuses_and_runs_nothing(self):
        saved = _R.package_origins
        pkg = _package('__version__ = "0.1.1"\n')
        try:
            _R.package_origins = lambda names: {n: pkg for n in names}
            code, out = _run(_tree_with_one_passing_test(),
                             shared=("ogr_core",),
                             pinned={"ogr_core": "0.1.0"})
        finally:
            _R.package_origins = saved
        assert code == 2, out
        assert "WRONG SHARED TREE" in out, out
        assert "0.1.1" in out and "0.1.0" in out and str(pkg) in out, out
        assert "Total:" not in out, out


class TestTheSharedTreeIsNamed:
    def test_a_git_tree_gives_its_commit(self):
        pkg = _package(git=True)
        line, = _R.shared_provenance({"ogr_core": pkg})
        assert line.startswith("shared: ogr_core 0.1.0"), line
        assert str(pkg) in line and "@ 0123456" in line, line

    def test_an_installed_copy_does_not_borrow_a_commit(self):
        """``…/OGR-Slip2D/.venv/Lib/site-packages/ogr_core`` sits under a
        git tree, but not directly: it is not that tree's code."""
        pkg = _package()
        repo = pkg.parent
        (repo / ".git").mkdir()
        nested = repo / ".venv" / "site-packages" / "ogr_core"
        nested.mkdir(parents=True)
        (nested / "__init__.py").write_text('__version__ = "0.1.0"\n',
                                            encoding="utf-8")
        line, = _R.shared_provenance({"ogr_core": nested})
        assert "installed" in line and "@" not in line, line

    def test_a_matching_core_is_named_and_the_run_goes_on(self):
        saved = _R.package_origins
        pkg = _package(git=True)
        try:
            _R.package_origins = lambda names: {n: pkg for n in names}
            code, out = _run(_tree_with_one_passing_test(),
                             shared=("ogr_core",),
                             pinned={"ogr_core": "0.1.0"})
        finally:
            _R.package_origins = saved
        assert code == 0, out
        assert "shared: ogr_core 0.1.0" in out, out
        assert "Total: 2" in out, out


class TestTheHooks:
    def _hooks(self, calls: list) -> "_R.Hooks":
        return _R.Hooks(before_run=lambda: calls.append("run"),
                        before_file=lambda: calls.append("file"))

    def test_before_run_once_and_before_file_per_file(self):
        calls: list = []
        code, out = _run(_tree_with_one_passing_test(),
                         hooks=self._hooks(calls))
        assert code == 0, out
        assert calls == ["run", "file", "file"], calls

    def test_no_hook_runs_when_the_run_is_refused(self):
        calls: list = []
        saved = _R.package_origins
        try:
            _R.package_origins = lambda names: {n: None for n in names}
            code, _ = _run(_tree_with_one_passing_test(),
                           shared=("ogr_core",), hooks=self._hooks(calls))
        finally:
            _R.package_origins = saved
        assert code == 2
        assert calls == [], calls
