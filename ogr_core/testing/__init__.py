# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
The test tooling of the OGR Suite: the runner every repository uses
(:mod:`ogr_core.testing.runner`) and the check of what a test file leaves
in the process (:mod:`ogr_core.testing.leaks`).

No program imports this at run time; only each repository's
``tests/_runner.py`` does, and the tests that use a helper of the leak
check. Nothing here imports the rest of the core, nor Qt.

Author: Samuel Sáez López (UPCT)
"""
