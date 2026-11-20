# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.2 — a run that accepted a development version of the core
(``--dev-core``) says so to its tests and to the runs they start.

What was found. The first two whole suites run with the option, for OGR
Core 0.2.1 (rule 8), could not come out green: OGR FEM2D failed three tests
and OGR Slip2D four, all by construction. Some compare the imported core
with the pinned one, which in such a run it is not. Others start the
repository's runner again in another process, and that process — which
nobody gave the option to — refused the core: ``WRONG SHARED TREE``. A
program had no way to tell which run its tests were in, so the only run a
change of the core can ask a program for always ended red, and a red that
is always there hides the next one.

Since v0.2.2 the run says it in the environment, ``OGR_DEV_CORE=1``
(:data:`ogr_core.testing.runner.DEV_CORE_ENV`), for its length.

Invariants protected:

1. **For its length, and no longer.** A test of a run that accepted a
   development version reads ``dev_core_run()`` as true, and so does every
   chunk of ``--jobs``; when the run ends the variable is what it was
   before, absent or not. Otherwise one run driven from a test would turn
   the rest of that suite into a development run.
2. **Only a run that accepted one.** Against the pinned core the variable
   is not set, and a refused run leaves nothing behind either.
3. **A run started inside it accepts the same core without the option**,
   and says ``DEV CORE`` before and after its totals like the run that
   started it: in the same process, and in a process of its own, which is
   the real case (a test that relaunches ``tests/_runner.py``).
4. **The variable accepts nothing the option would not**: another release,
   an older core in development and a core that does not resolve are
   refused under it too.
5. **The variable never stops a run, and the option still does.** With
   nothing to accept, a run under the variable is an ordinary run against
   the pinned core — green, with no ``DEV CORE`` line, and it counts as the
   serial run a release needs — because a test inside a development run may
   run a folder of its own that shares nothing. Its chunks are not handed
   the option either: they would stop with it.
6. **Only ``"1"`` is the run saying so**: ``0``, an empty value or ``true``
   are not.

How: the synthetic shared package of ``test_runner_dev_core_v020`` (really
importable, never executed), runs of throwaway files that assert what they
see, and one throwaway repository runner started as a process.
"""
from __future__ import annotations

import contextlib
import importlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_runner_dev_core_v020 import _NAME, _package  # noqa: E402
from test_runner_fast_v020 import _Own  # noqa: E402

from ogr_core.testing import runner as _R  # noqa: E402

_VAR = _R.DEV_CORE_ENV

#: A file whose only test passes when the run it is in says it is a
#: development run, and one that passes when it does not.
_SEES = ("from ogr_core.testing import runner\n\n\n"
         "class TestSees:\n    def test_it_is_a_development_run(self):\n"
         "        assert runner.dev_core_run()\n")
_SEES_NOT = ("from ogr_core.testing import runner\n\n\n"
             "class TestSeesNot:\n    def test_it_is_an_ordinary_run(self):\n"
             "        assert not runner.dev_core_run()\n")

_LINE = (f"DEV CORE — {_NAME} 0.3.0.dev0 runs in place of the pinned 0.2.0 "
         f"— NOT evidence for a release")

#: The tree ``ogr_core`` is imported from: what a process of its own needs
#: on its path to import the runner at all.
_TREE = str(Path(_R.__file__).resolve().parents[2])


def _run(files: dict, have: str | None, pin: str | None = "0.2.0", *,
         before: str | None = None, folder=None, **kw):
    """A run of ``files`` against a shared package that says ``have``,
    pinned at ``pin``, started with the variable at ``before`` (None:
    absent). Returns ``(code, output, after)``: ``after`` is the variable
    when the run has ended. Everything set here is put back."""
    made = folder is None
    if made:
        folder = Path(tempfile.mkdtemp(prefix="ogr_runner_dev22_"))
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    home = _package(have) if have else None
    saved_path = list(sys.path)
    saved = {v: os.environ.get(v) for v in ("PYTHONPATH", _VAR)}
    config = {"shared": (_NAME,), "pinned": {_NAME: pin}} if pin else {}
    buf = io.StringIO()
    try:
        if home is not None:
            sys.path.insert(0, str(home))
            os.environ["PYTHONPATH"] = os.pathsep.join(
                [str(home)] + ([saved["PYTHONPATH"]]
                               if saved["PYTHONPATH"] else []))
        if before is None:
            os.environ.pop(_VAR, None)
        else:
            os.environ[_VAR] = before
        importlib.invalidate_caches()
        with contextlib.redirect_stdout(buf):
            code = _R.main(folder, **config, **kw)
        after = os.environ.get(_VAR)
    finally:
        sys.path[:] = saved_path
        for var, value in saved.items():
            if value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = value
        for name in files:
            sys.modules.pop(name[:-3], None)
        if made:
            shutil.rmtree(folder, ignore_errors=True)
        if home is not None:
            shutil.rmtree(home, ignore_errors=True)
        importlib.invalidate_caches()
    text = buf.getvalue()
    for kept in re.findall(r"\(log: (.+?)[\\/]log_\d+\.txt\)", text):
        shutil.rmtree(kept, ignore_errors=True)
    return code, text, after


class TestForItsLengthAndNoLonger:
    def test_a_test_of_the_run_sees_it(self):
        code, out, _ = _run({"test_v022_sees.py": _SEES}, "0.3.0.dev0",
                            dev_core=True)
        assert code == 0, out
        assert "Total: 1    Passed: 1    Failed: 0" in out, out

    def test_and_so_does_every_chunk(self):
        files = {"test_v022_sees_a.py": _SEES, "test_v022_sees_b.py": _SEES}
        code, out, _ = _run(files, "0.3.0.dev0", dev_core=True, jobs=2)
        assert code == 0, out
        assert "PARALLEL RUN — 2 chunk(s)" in out, out
        assert "Total: 2    Passed: 2    Failed: 0" in out, out

    def test_the_run_puts_it_back_when_it_was_absent(self):
        code, out, after = _run({"test_v022_sees.py": _SEES}, "0.3.0.dev0",
                                dev_core=True)
        assert code == 0, out
        assert after is None, after

    def test_and_when_it_said_something_else(self):
        # "0" is not a development run (see the last class), so the option
        # is what accepts here; the run sets "1" and gives "0" back.
        code, out, after = _run({"test_v022_sees.py": _SEES}, "0.3.0.dev0",
                                before="0", dev_core=True)
        assert code == 0, out
        assert after == "0", after


class TestOnlyARunThatAcceptedOne:
    def test_against_the_pinned_core_nothing_is_set(self):
        code, out, after = _run({"test_v022_not.py": _SEES_NOT}, "0.2.0")
        assert code == 0, out
        assert "Total: 1    Passed: 1    Failed: 0" in out, out
        assert after is None, after

    def test_a_refused_run_leaves_nothing_behind(self):
        code, out, after = _run({"test_v022_not.py": _SEES_NOT},
                                "0.3.0.dev0")
        assert code == 2 and "WRONG SHARED TREE" in out, out
        assert after is None, after
        # nor does the option when it has nothing to accept
        code, out, after = _run({"test_v022_not.py": _SEES_NOT}, "0.2.0",
                                dev_core=True)
        assert code == 2 and "nothing to accept" in out, out
        assert after is None, after


class TestARunStartedInsideAcceptsTheSameCore:
    def test_without_the_option_and_it_says_so(self):
        code, out, after = _run({"test_v022_sees.py": _SEES}, "0.3.0.dev0",
                                before="1")
        assert code == 0, out
        assert out.count(_LINE) == 2, out
        total_at = out.index("\nTotal: 1    Passed: 1    Failed: 0")
        assert out.index(_LINE) < total_at < out.rindex(_LINE)
        # it was there before the run: it is still there after it
        assert after == "1", after

    def test_in_chunks_too(self):
        files = {"test_v022_sees_a.py": _SEES, "test_v022_sees_b.py": _SEES}
        code, out, _ = _run(files, "0.3.0.dev0", before="1", jobs=2)
        assert code == 0, out
        assert "[CHUNK]" not in out, out
        assert out.count(_LINE) == 2, out

    def _repository(self) -> tuple[Path, Path]:
        """A throwaway repository runner that shares the synthetic package
        at 0.3.0.dev0 and pins 0.2.0, and the folder that package is in."""
        folder = Path(tempfile.mkdtemp(prefix="ogr_runner_dev22_repo_"))
        (folder / "_runner.py").write_text(
            "import sys\nfrom pathlib import Path\n"
            "from ogr_core.testing import runner\n"
            f"sys.exit(runner.cli(Path(__file__).parent, shared=({_NAME!r},),"
            f" pinned={{{_NAME!r}: '0.2.0'}}))\n", encoding="utf-8")
        (folder / "test_v022_started.py").write_text(_SEES, encoding="utf-8")
        return folder, _package("0.3.0.dev0")

    def _start(self, folder: Path, home: Path, value: str | None):
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([str(home), _TREE])
        env.pop(_VAR, None)
        if value is not None:
            env[_VAR] = value
        return subprocess.run(
            [sys.executable, str(folder / "_runner.py")], env=env,
            cwd=folder, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=300)

    def test_a_process_of_its_own_which_nobody_gave_the_option(self):
        folder, home = self._repository()
        try:
            inside = self._start(folder, home, "1")
            outside = self._start(folder, home, None)
        finally:
            shutil.rmtree(folder, ignore_errors=True)
            shutil.rmtree(home, ignore_errors=True)
        assert inside.returncode == 0, (inside.stdout, inside.stderr)
        assert inside.stdout.count(_LINE) == 2, inside.stdout
        assert "Total: 1    Passed: 1    Failed: 0" in inside.stdout
        # the other half: the same process outside such a run is refused,
        # so it is the variable that let it through
        assert outside.returncode == 2, (outside.stdout, outside.stderr)
        assert "WRONG SHARED TREE" in outside.stdout, outside.stdout

    def test_end_to_end_a_test_of_the_run_relaunches_the_runner(self):
        # The case that failed in OGR Slip2D: the run is given the option,
        # one of its tests starts the repository's runner again, with the
        # environment it has and no option, and expects it to end with 0.
        folder, home = self._repository()
        relaunch = (
            "import subprocess\nimport sys\n\n\n"
            "class TestRelaunch:\n    def test_the_runner_ends_with_zero(self):\n"
            "        done = subprocess.run(\n"
            f"            [sys.executable, {str(folder / '_runner.py')!r}],\n"
            f"            cwd={str(folder)!r}, capture_output=True, text=True,\n"
            "            encoding='utf-8', errors='replace', timeout=300)\n"
            "        assert done.returncode == 0, (done.stdout, done.stderr)\n"
            "        assert 'DEV CORE' in done.stdout, done.stdout\n")
        saved = os.environ.get("PYTHONPATH")
        try:
            # the tree of the runner, for the process the test starts; the
            # run adds the synthetic package's folder in front of it
            os.environ["PYTHONPATH"] = os.pathsep.join(
                [str(home), _TREE] + ([saved] if saved else []))
            code, out, after = _run({"test_v022_relaunch.py": relaunch},
                                    "0.3.0.dev0", dev_core=True)
            # and without the option the same test cannot pass, because the
            # run itself is refused before it starts
            refused, _, _ = _run({"test_v022_relaunch.py": relaunch},
                                 "0.3.0.dev0")
        finally:
            if saved is None:
                os.environ.pop("PYTHONPATH", None)
            else:
                os.environ["PYTHONPATH"] = saved
            shutil.rmtree(folder, ignore_errors=True)
            shutil.rmtree(home, ignore_errors=True)
        assert code == 0, out
        assert "Total: 1    Passed: 1    Failed: 0" in out, out
        assert after is None, after
        assert refused == 2


class TestTheVariableAcceptsNothingTheOptionWouldNot:
    def test_another_release(self):
        for have in ("0.3.0", "0.2.1", "0.1.0"):
            code, out, _ = _run({"test_v022_sees.py": _SEES}, have,
                                before="1")
            assert code == 2 and "WRONG SHARED TREE" in out, (have, out)

    def test_an_older_core_in_development(self):
        for have in ("0.2.0.dev0", "0.1.5.dev2"):
            code, out, _ = _run({"test_v022_sees.py": _SEES}, have,
                                before="1")
            assert code == 2 and "WRONG SHARED TREE" in out, (have, out)
            assert "Total:" not in out, out

    def test_a_core_that_does_not_resolve(self):
        code, out, _ = _run({"test_v022_sees.py": _SEES}, None, before="1")
        assert code == 2 and "not importable" in out, out


class TestTheVariableNeverStopsARun:
    #: Under the variable with nothing to accept, the test of the run still
    #: reads the variable as set: it was set by whoever started the run.
    def test_with_the_core_at_its_pin_the_run_is_an_ordinary_one(self):
        code, out, after = _run({"test_v022_sees.py": _SEES}, "0.2.0",
                                before="1")
        assert code == 0, out
        assert "DEV CORE" not in out and "nothing to accept" not in out, out
        assert "Total: 1    Passed: 1    Failed: 0" in out, out
        assert after == "1", after

    def test_with_nothing_shared_too(self):
        # a test inside a development run that runs a folder of its own
        code, out, _ = _run({"test_v022_sees.py": _SEES}, None, pin=None,
                            before="1")
        assert code == 0, out
        assert "DEV CORE" not in out and "nothing to accept" not in out, out

    def test_and_its_chunks_are_not_handed_the_option(self):
        # with it each chunk would stop: "nothing to accept", exit 2
        files = {"test_v022_sees_a.py": _SEES, "test_v022_sees_b.py": _SEES}
        code, out, _ = _run(files, "0.2.0", before="1", jobs=2)
        assert code == 0, out
        assert "[CHUNK]" not in out, out
        assert "Total: 2    Passed: 2    Failed: 0" in out, out

    def test_it_counts_as_the_serial_run_a_release_needs(self):
        own = _Own()
        code, out, _ = _run({"test_v022_sees.py": _SEES}, "0.2.0",
                            before="1", folder=own.tests,
                            records=own.records, serial_every=100)
        assert code == 0, out
        assert "full serial run recorded" in out, out
        assert own.records.serial.exists()

    def test_the_option_still_stops(self):
        code, out, _ = _run({"test_v022_sees.py": _SEES}, "0.2.0",
                            before="1", dev_core=True)
        assert code == 2, out
        assert "--dev-core has nothing to accept" in out, out
        assert "Total:" not in out, out


class TestOnlyOneIsTheRunSayingSo:
    def test_the_question(self):
        saved = os.environ.get(_VAR)
        try:
            for value, expected in (("1", True), ("0", False), ("", False),
                                    ("true", False), ("yes", False),
                                    (" 1", False)):
                os.environ[_VAR] = value
                assert _R.dev_core_run() is expected, repr(value)
            os.environ.pop(_VAR, None)
            assert _R.dev_core_run() is False
        finally:
            if saved is None:
                os.environ.pop(_VAR, None)
            else:
                os.environ[_VAR] = saved

    def test_another_value_does_not_let_a_development_version_through(self):
        for value in ("0", "", "true"):
            code, out, after = _run({"test_v022_not.py": _SEES_NOT},
                                    "0.3.0.dev0", before=value)
            assert code == 2 and "WRONG SHARED TREE" in out, (value, out)
            assert after == value, (value, after)

    def test_the_name_is_the_one_documented(self):
        # programs and their CI write it by hand
        assert _VAR == "OGR_DEV_CORE"
