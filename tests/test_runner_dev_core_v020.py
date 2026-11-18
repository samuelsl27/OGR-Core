# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.0 — a program's suite can be run on purpose against the core as it is
being changed (``--dev-core``), and never by accident against a core it
does not pin.

New in OGR Core 0.2.0, with the way of working of the suite: one core,
changed in short branches, each tested against every program before it is
merged. Between two tags the core's ``main`` says a development version
(``0.3.0.dev0``). A program that pins ``0.2.0`` refuses it — that is the pin
working, and it stays the default — so testing the change needed either
lying about the version or switching the check off. ``--dev-core`` is the
third way: it accepts exactly one thing, says so with the numbers, and its
run is not evidence for a release.

Invariants protected:

1. **Only a ``.devN`` of a plain release number is a development version**:
   not a release, not a release candidate, not a local version, not a
   ``.dev`` without its number.
2. **Only one that leads to a release LATER than the pinned one is
   accepted**: ``0.2.0.dev0`` came before the ``0.2.0`` a program pins and
   is an older core; a shorter or longer number compares by its numbers.
3. **Without the option nothing changes**: a development version is
   refused like any other mismatch, with exit 2, and the message says which
   option runs against it. A wrong release, an older core and a core that
   does not resolve are refused WITH the option too.
4. **With it the run says so**, before and after its totals, with both
   versions; it keeps the durations of what it ran but does not count as
   the serial run a release needs.
5. **The option never does nothing** (rule 7): with every shared package at
   its pin, or with none shared at all, it stops with exit 2 and runs
   nothing.
6. **A chunk of ``--jobs`` accepts what its run accepted**: the option
   travels to every chunk.

How: a synthetic shared package, really importable (its folder is on
``sys.path`` and on ``PYTHONPATH`` for the length of a run, so the chunks of
``--jobs``, which are processes of their own, resolve it too) and whose
``__init__`` raises if executed: the version is read, never run. Not
``ogr_core`` itself, which the chunks need as it is to run at all.
"""
from __future__ import annotations

import contextlib
import importlib
import io
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_runner_fast_v020 import _Own  # noqa: E402

from ogr_core.testing import runner as _R  # noqa: E402

_TWO = {
    "test_dev_one.py": "class TestOne:\n    def test_passes(self):\n"
                       "        pass\n",
    "test_dev_two.py": "class TestTwo:\n    def test_passes(self):\n"
                       "        pass\n",
}


#: The shared package of these runs.
_NAME = "ogr_devshared_v020"


def _package(version: str) -> Path:
    """A folder holding a synthetic ``_NAME`` whose ``__init__`` raises if
    run; the folder, to put on the path."""
    home = Path(tempfile.mkdtemp(prefix="ogr_runner_dev_"))
    pkg = home / _NAME
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        f'"""synthetic"""\n__version__ = "{version}"\n'
        "raise RuntimeError('this __init__ was executed')\n",
        encoding="utf-8")
    return home


def _run(have: str | None, pin: str | None = "0.2.0", folder=None,
         **kw) -> tuple[int, str]:
    """A run of two passing files against a shared package that says
    ``have`` (None: it does not resolve), pinned at ``pin`` (None: nothing
    shared). Everything the run sets in this process is put back here."""
    made = folder is None
    if made:
        folder = Path(tempfile.mkdtemp(prefix="ogr_runner_dev_run_"))
    for name, text in _TWO.items():
        (folder / name).write_text(text, encoding="utf-8")
    home = _package(have) if have else None
    saved_path = list(sys.path)
    saved_env = os.environ.get("PYTHONPATH")
    config = {"shared": (_NAME,), "pinned": {_NAME: pin}} if pin else {}
    buf = io.StringIO()
    try:
        if home is not None:
            sys.path.insert(0, str(home))
            os.environ["PYTHONPATH"] = os.pathsep.join(
                [str(home)] + ([saved_env] if saved_env else []))
        importlib.invalidate_caches()
        with contextlib.redirect_stdout(buf):
            code = _R.main(folder, **config, **kw)
    finally:
        sys.path[:] = saved_path
        if saved_env is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = saved_env
        for name in _TWO:
            sys.modules.pop(name[:-3], None)
        if made:
            shutil.rmtree(folder, ignore_errors=True)
        if home is not None:
            shutil.rmtree(home, ignore_errors=True)
        importlib.invalidate_caches()
    text = buf.getvalue()
    for kept in re.findall(r"\(log: (.+?)[\\/]log_\d+\.txt\)", text):
        shutil.rmtree(kept, ignore_errors=True)
    return code, text


_LINE = (f"DEV CORE — {_NAME} 0.3.0.dev0 runs in place of the pinned 0.2.0 "
         f"— NOT evidence for a release")


class TestWhatADevelopmentVersionIs:
    def test_a_dev_of_a_release_number(self):
        assert _R.dev_base("0.3.0.dev0") == (0, 3, 0)
        assert _R.dev_base("0.3.0.dev12") == (0, 3, 0)
        assert _R.dev_base("1.0.dev3") == (1, 0)

    def test_nothing_else(self):
        for version in ("0.3.0", "0.3.0rc1", "0.3.0.dev", "0.3.0.dev0+local",
                        "0.3.0-dev0", "0.3.0.dev0.post1", "dev0", "", None):
            assert _R.dev_base(version) is None, version


class TestOnlyALaterOneIsAccepted:
    def test_later_than_the_pin(self):
        assert _R._is_dev_of_later("0.3.0.dev0", "0.2.0")
        assert _R._is_dev_of_later("0.2.1.dev0", "0.2.0")
        assert _R._is_dev_of_later("1.0.0.dev0", "0.9.9")

    def test_the_dev_of_the_pinned_release_itself_came_before_it(self):
        assert not _R._is_dev_of_later("0.2.0.dev0", "0.2.0")
        assert not _R._is_dev_of_later("0.2.0.dev99", "0.2.0")

    def test_an_older_one_never(self):
        assert not _R._is_dev_of_later("0.1.9.dev3", "0.2.0")
        assert not _R._is_dev_of_later("0.1.0.dev0", "0.2.0")

    def test_numbers_of_different_lengths_compare_by_their_numbers(self):
        assert _R._is_dev_of_later("0.3.dev1", "0.2.0")
        assert not _R._is_dev_of_later("0.2.dev1", "0.2.0")
        assert _R._is_dev_of_later("0.2.0.1.dev0", "0.2.0")
        # ten is more than nine: numbers, not text
        assert _R._is_dev_of_later("0.10.0.dev0", "0.9.0")

    def test_a_release_is_not_a_development_version(self):
        assert not _R._is_dev_of_later("0.3.0", "0.2.0")
        assert not _R._is_dev_of_later(None, "0.2.0")


class TestWithoutTheOptionNothingChanges:
    def test_a_development_version_is_refused(self):
        code, out = _run("0.3.0.dev0")
        assert code == 2, out
        assert "WRONG SHARED TREE" in out and "Total:" not in out, out
        assert "0.3.0.dev0" in out and "pins 0.2.0" in out, out

    def test_and_the_message_names_the_option(self):
        _, out = _run("0.3.0.dev0")
        assert "--dev-core" in out, out
        # only where the option would help: an older core gets no such hint
        _, out = _run("0.1.0")
        assert "--dev-core" not in out, out

    def test_the_pinned_version_runs_and_says_nothing_of_it(self):
        code, out = _run("0.2.0")
        assert code == 0, out
        assert "DEV CORE" not in out, out
        assert "Total: 2    Passed: 2    Failed: 0" in out, out


class TestWhatTheOptionStillRefuses:
    def test_another_release(self):
        for have in ("0.3.0", "0.2.1", "0.1.0"):
            code, out = _run(have, dev_core=True)
            assert code == 2 and "WRONG SHARED TREE" in out, (have, out)

    def test_an_older_core_in_development(self):
        for have in ("0.2.0.dev0", "0.1.5.dev2"):
            code, out = _run(have, dev_core=True)
            assert code == 2 and "WRONG SHARED TREE" in out, (have, out)
            assert "Total:" not in out, out

    def test_a_core_that_does_not_resolve(self):
        code, out = _run(None, dev_core=True)
        assert code == 2 and "not importable" in out, out


class TestWithItTheRunSaysSo:
    def test_before_and_after_the_totals_with_both_versions(self):
        code, out = _run("0.3.0.dev0", dev_core=True)
        assert code == 0, out
        assert out.count(_LINE) == 2, out
        total_at = out.index("\nTotal: 2    Passed: 2    Failed: 0")
        assert out.index(_LINE) < total_at < out.rindex(_LINE)
        # and the tree is still named, with the version it really has
        assert f"shared: {_NAME} 0.3.0.dev0" in out, out

    def test_in_chunks_too_and_every_chunk_accepts_it(self):
        # The chunks are real processes that check the shared tree
        # themselves: without the option in their command line each would
        # refuse the development version, and the run would be two dead
        # chunks instead of two green files.
        code, out = _run("0.3.0.dev0", dev_core=True, jobs=2)
        assert code == 0, out
        assert "[CHUNK]" not in out, out
        assert out.count(_LINE) == 2, out
        total_at = out.index("\nTotal: 2    Passed: 2    Failed: 0")
        assert out.index(_LINE) < total_at < out.rindex(_LINE)
        assert "PARALLEL RUN — 2 chunk(s)" in out, out

    def test_a_chunk_refuses_what_its_run_was_not_told_to_accept(self):
        # the other half: the chunks do check. A run in chunks without the
        # option stops before starting any.
        code, out = _run("0.3.0.dev0", jobs=2)
        assert code == 2, out
        assert "WRONG SHARED TREE" in out and "PARALLEL RUN" not in out, out

    def test_it_is_not_the_serial_run_a_release_needs(self):
        own = _Own()
        code, out = _run("0.3.0.dev0", folder=own.tests, dev_core=True,
                         records=own.records, serial_every=100)
        assert code == 0, out
        assert "recorded" not in out, out
        assert not own.records.serial.exists()
        # what it measured is kept: the durations are about the machine
        assert set(own.read("durations")) == set(_TWO)
        # the same run against the pinned core IS that serial run
        code, out = _run("0.2.0", folder=own.tests, records=own.records,
                         serial_every=100)
        assert code == 0, out
        assert "full serial run recorded" in out, out
        assert own.records.serial.exists()


class TestTheOptionNeverDoesNothing:
    def test_with_every_shared_package_at_its_pin(self):
        code, out = _run("0.2.0", dev_core=True)
        assert code == 2, out
        assert "--dev-core has nothing to accept" in out, out
        assert "Total:" not in out and "===" not in out, out

    def test_with_nothing_shared(self):
        # the core's own suite: there is no other tree to be in development
        code, out = _run(None, pin=None, dev_core=True)
        assert code == 2, out
        assert "--dev-core has nothing to accept" in out, out

    def test_the_command_line_has_it(self):
        ns = _R._parse_args(["--dev-core"])
        assert ns.dev_core is True
        assert _R._parse_args([]).dev_core is False
