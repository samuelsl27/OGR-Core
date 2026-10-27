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
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _pyproject_version() -> str:
    return tomllib.loads((_ROOT / "pyproject.toml").read_text(
        encoding="utf-8"))["project"]["version"]


def _package_version() -> str:
    m = re.search(r'^__version__\s*=\s*"([^"]+)"',
                  (_ROOT / "ogr_core" / "__init__.py").read_text(
                      encoding="utf-8"), re.MULTILINE)
    assert m is not None, "no __version__ in ogr_core/__init__.py"
    return m.group(1)


class TestVersionConsistency:
    def test_the_two_places_agree(self):
        assert _pyproject_version() == _package_version(), (
            _pyproject_version(), _package_version())

    def test_the_version_is_a_release_number(self):
        assert re.fullmatch(r"\d+\.\d+\.\d+([abrc.\-+].*)?",
                            _package_version())

    def test_the_changelog_for_this_version_exists(self):
        path = _ROOT / "docs" / "changelog" / f"CHANGELOG_v{_package_version()}.md"
        assert path.exists(), f"missing {path.relative_to(_ROOT)}"
