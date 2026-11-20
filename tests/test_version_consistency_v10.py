# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.1.0 — the core says one version, and that version has its changelog.

Rule 9 of ``AGENTS.md``: the number lives in two places, ``pyproject.toml``
and ``ogr_core/__init__.py``. In OGR Slip2D the same check
(``test_version_consistency_v176``) exists because three packages had sat
at 0.1.59 for sixteen releases while the distribution moved on, and nothing
failed: a version that was true a year ago is worse than none. Here a
program pins the core's version, so a disagreement would make a program
believe it measures a core it does not.

v0.2.2 — between two tags the number is a development version. Until then
``main`` kept the number of its last tag (0.2.1 after ``v0.2.1``), and the
runner of a program compares numbers: a core changed after the tag, and not
tagged, would have answered for the tagged one with nothing said. So the
number is one of two forms and no other:

* ``X.Y.Z``, a release: it has its changelog, and no changelog is of a later
  release (a tree that says 0.2.2 next to ``CHANGELOG_v0.2.3.md`` is saying
  an old number);
* ``X.Y.Z.devN``, the core on its way to ``X.Y.Z``: what
  ``ogr_core.testing.runner.dev_base`` reads, and what ``--dev-core``
  accepts in a program that pins an earlier release. It has no changelog of
  its own, and no changelog is of a release after the one it leads to. The
  one it leads to may be there already: it is written while the version is.

A release candidate, a local version or a bare ``.dev`` is neither: a
program's runner would refuse it with or without ``--dev-core``, so a core
that said one could be tested by nobody.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

from ogr_core.testing import runner as _R

_ROOT = Path(__file__).resolve().parent.parent
_CHANGELOGS = _ROOT / "docs" / "changelog"


def _pyproject_version() -> str:
    return tomllib.loads((_ROOT / "pyproject.toml").read_text(
        encoding="utf-8"))["project"]["version"]


def _package_version() -> str:
    m = re.search(r'^__version__\s*=\s*"([^"]+)"',
                  (_ROOT / "ogr_core" / "__init__.py").read_text(
                      encoding="utf-8"), re.MULTILINE)
    assert m is not None, "no __version__ in ogr_core/__init__.py"
    return m.group(1)


def _kind(version: str):
    """``"release"`` for ``X.Y.Z``, ``"dev"`` for ``X.Y.Z.devN``, None for
    anything else."""
    if re.fullmatch(r"\d+\.\d+\.\d+", version or ""):
        return "release"
    base = _R.dev_base(version)
    return "dev" if base is not None and len(base) == 3 else None


def _written() -> list:
    """The releases that have a changelog, as tuples of numbers."""
    out = []
    for path in sorted(_CHANGELOGS.glob("CHANGELOG_v*.md")):
        m = re.fullmatch(r"CHANGELOG_v(\d+)\.(\d+)\.(\d+)\.md", path.name)
        assert m is not None, f"{path.name}: not CHANGELOG_vX.Y.Z.md"
        out.append(tuple(int(x) for x in m.groups()))
    return out


def _later_changelogs(version: str, written) -> list:
    """The changelogs of ``written`` that are of a release after the one
    ``version`` is, or leads to."""
    base = _R.dev_base(version) or tuple(int(x) for x in version.split("."))
    return sorted(w for w in written if w > base)


class TestVersionConsistency:
    def test_the_two_places_agree(self):
        assert _pyproject_version() == _package_version(), (
            _pyproject_version(), _package_version())

    def test_the_version_is_a_release_or_a_development_version(self):
        assert _kind(_package_version()) in ("release", "dev"), (
            _package_version())

    def test_what_counts_as_each(self):
        for version in ("0.2.2", "1.0.0", "0.10.3"):
            assert _kind(version) == "release", version
        for version in ("0.2.2.dev0", "0.3.0.dev12"):
            assert _kind(version) == "dev", version
        for version in ("0.2", "0.2.2.1", "0.2.2rc1", "0.2.2.dev",
                        "0.2.2.dev0+local", "0.2.2-dev0", "0.2.2.post1",
                        "0.2.2a1", "v0.2.2", ""):
            assert _kind(version) is None, version

    def test_a_release_has_its_changelog(self):
        version = _package_version()
        if _kind(version) != "release":
            # a development version: the next test is the one about it
            return
        path = _CHANGELOGS / f"CHANGELOG_v{version}.md"
        assert path.exists(), f"missing {path.relative_to(_ROOT)}"

    def test_a_development_version_has_no_changelog_of_its_own(self):
        version = _package_version()
        if _kind(version) != "dev":
            return
        path = _CHANGELOGS / f"CHANGELOG_v{version}.md"
        assert not path.exists(), (
            f"{path.relative_to(_ROOT)}: the changelog is of the release "
            f"this version leads to")

    def test_no_changelog_is_of_a_later_release(self):
        assert _later_changelogs(_package_version(), _written()) == []

    def test_the_census_of_changelogs_looked_at_something(self):
        # an empty folder would make the test above pass on nothing
        assert (0, 1, 0) in _written() and (0, 2, 1) in _written()

    def test_what_a_later_changelog_is(self):
        written = [(0, 1, 0), (0, 2, 0), (0, 2, 1), (0, 2, 2)]
        # a release: its own is the last one
        assert _later_changelogs("0.2.2", written) == []
        assert _later_changelogs("0.2.1", written) == [(0, 2, 2)]
        # a development version: the one it leads to may be there
        assert _later_changelogs("0.2.2.dev0", written) == []
        assert _later_changelogs("0.2.3.dev0", written) == []
        assert _later_changelogs("0.2.1.dev4", written) == [(0, 2, 2)]
        # numbers, not text
        assert _later_changelogs("0.10.0", written + [(0, 9, 0)]) == []
