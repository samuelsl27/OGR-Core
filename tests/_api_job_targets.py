# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
Job targets for the tests of ``ogr_core.api.jobs`` (v0.2.9).

Not a test file: the tests hand these functions to a ``JobManager``, and
the child process of a job imports this module when it unpickles one, with
this folder on its ``PYTHONPATH`` (the manager's ``pythonpath``). Each
target takes the ``JobContext`` and returns ``(payload, summary)``.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

#: The modules a job's child must never have imported (the core's rule of
#: layers, checked in the child too).
BANNED = ("ogr_slip2d", "ogr_fem2d", "ogr_api", "ogr_gui", "ogr_cli",
          "ogr_mcp", "PySide6", "mcp")


def square(ctx):
    """``data ** 2``, with three progress updates and the extra fields."""
    n = 3
    for i in range(n + 1):
        ctx.progress(i, n, phase="square", step=i)
    banned = sorted(m for m in sys.modules
                    if m.split(".")[0] in BANNED)
    return ({"value": ctx.data ** 2, "kind": ctx.kind},
            {"value": ctx.data ** 2, "params": ctx.params,
             "banned_in_child": banned})


def phases(ctx):
    """Four quick updates of the same count, the phase changing at each:
    none may be lost to the throttle."""
    seen = []
    for name in ("mesh", "assemble", "solve", "write"):
        ctx.progress(0, 10, phase=name)
        with open(ctx.folder / "progress.json", encoding="utf-8") as fh:
            seen.append(fh.read())
    return ({}, {"seen": seen})


def same_phase(ctx):
    """Four quick updates of the same count and the same phase: all but
    the first fall inside the throttle."""
    seen = []
    for done in (1, 2, 3, 4):
        ctx.progress(done, 10, phase="solve")
        with open(ctx.folder / "progress.json", encoding="utf-8") as fh:
            seen.append(fh.read())
    return ({}, {"seen": seen})


def boom(ctx):
    raise RuntimeError("no such thing as " + str(ctx.data))


def die(ctx):
    """A native crash: the process ends without a word."""
    os._exit(3)


def sleep_with_child(ctx):
    """Start a grandchild that sleeps, write its pid, and sleep: what a
    cancel must kill whole."""
    kid = subprocess.Popen([sys.executable, "-c",
                            "import time; time.sleep(120)"])
    (ctx.folder / "grandchild").write_text(str(kid.pid), encoding="ascii")
    time.sleep(120)
    return ({}, {})


def cooperative(ctx):
    """Sleep in short phases and stop when asked, as a staged solver."""
    from ogr_core.api.jobs import JobCancelled

    (ctx.folder / "started").write_text("1", encoding="ascii")
    for _ in range(1200):
        if ctx.should_stop():
            (ctx.folder / "stopped_by_itself").write_text(
                "1", encoding="ascii")
            raise JobCancelled()
        time.sleep(0.05)
    return ({}, {})


def stubborn(ctx):
    """Never looks at ``should_stop``."""
    (ctx.folder / "started").write_text("1", encoding="ascii")
    time.sleep(120)
    return ({}, {})


def provenance():
    return {"program": "tests", "program_version": "9.9.9"}
