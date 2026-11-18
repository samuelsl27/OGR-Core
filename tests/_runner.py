# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
The test runner of OGR Core: the suite's runner
(:mod:`ogr_core.testing.runner`), pointed at this repository.

    python tests/_runner.py            # everything; what CI runs
    python tests/_runner.py geometry   # files whose name contains it
    python tests/_runner.py -k erfc    # tests whose name contains it
    python tests/_runner.py --list     # show the selection, run nothing
    python tests/_runner.py --jobs 4   # in four processes

Here the core is this repository's OWN package, so it must resolve inside
this tree; there is nothing shared. A program's ``tests/_runner.py`` says
the opposite: ``ogr_core`` is shared, named with its tree, commit and
version, and pinned.

The core adds nothing else to a run: no hooks (it has no Qt), no folders
of its own, no entries of its own in the leak check's allow-list, and no
rule about a serial run (its whole suite is the serial run CI makes).
"""
from __future__ import annotations

import sys
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
# This tree first, before any editable install can answer for it (see
# foreign_packages in the runner).
sys.path.insert(0, str(_TESTS.parent))

from ogr_core.testing import runner  # noqa: E402

#: The packages this repository contains.
OWN = ("ogr_core",)
#: The name this repository's durations are kept under on the machine.
LABEL = "ogr-core"


def config() -> dict:
    return {"own": OWN, "label": LABEL}


def main(patterns=(), k=None, list_only=False, **options) -> int:
    """This repository's run, for a test that wants to drive it."""
    return runner.main(_TESTS, patterns, k, list_only, **config(), **options)


if __name__ == "__main__":
    sys.exit(runner.cli(_TESTS, **config()))
