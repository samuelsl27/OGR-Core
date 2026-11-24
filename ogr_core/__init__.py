# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
OGR Core — domain model and numerical primitives.

This package is deliberately GUI-agnostic. It can be imported and used
from scripts, Jupyter notebooks, tests, or any other Python context
without pulling in Qt.

Extracted from OGR Slip2D at commit 2d68c29 (its spec 009, phase F1), where
this package carried the program's version up to 0.1.370. Its own series
starts there, at 0.1.0 (decision P2): a report that quotes an ``ogr_core``
version should also say which program and version it came with.

0.2.0 is the core of OGR Slip2D again, as it stood in that program at
commit d48e2b3 (v0.1.471), with its mesh generator and seepage solvers
inside ``ogr_core.fem``: Slip2D had kept developing its own copy after
0.1.0 was cut, and from 0.2.0 on there is one core for every program of the
suite. ``docs/changelog/CHANGELOG_v0.2.0.md`` says where each part comes
from.

Author: Samuel Sáez López — PhD Student, UPCT
"""
__version__ = "0.2.9"
__author__ = "Samuel Sáez López"
__institution__ = "Universidad Politécnica de Cartagena (UPCT)"
