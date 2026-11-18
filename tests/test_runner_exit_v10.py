# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.1.0 — a test that exits fails, a skip is a skip, and importing the
runner installs nothing.

Moved with the runner from OGR Slip2D's ``test_runner_exit_v1203``
(spec 009, decision P4). The invariants it carried:

* **``SystemExit`` is that test's failure**, not the end of the suite
  (Slip2D v0.1.203: argparse's ``sys.exit`` once ended the whole run with
  no totals);
* **``pytest.skip`` is a third outcome**, neither a pass nor a failure, and
  a test's ``except Exception`` cannot swallow it (v0.1.205);
* **another copy's skip is still a skip**: a second copy of the runner
  module has its own ``Skipped`` class, and the first run of v0.1.205 on
  GitHub ended at 83 % because the running copy only caught its own.

* **an ``async def`` test fails instead of passing empty** (Slip2D
  v0.1.194): calling it returns a coroutine without running a line of its
  body, and until then that return value was ignored, so it counted as a
  pass — a green test that tested nothing. The failure says what to do, the
  body does not run, and the coroutine is closed rather than left to warn
  when it is collected. This one did NOT travel with the runner: in Slip2D
  it lives in a test about something else (``test_rules_moved_v1194``), so
  neither the list of 0.1.0 nor that of 0.2.0 saw it, and the runner's code
  stood here with no test until OGR Slip2D's adoption census found the gap
  (its spec 010).

And one new, from moving the runner into the core's distribution:

* **importing ``ogr_core.testing.runner`` does not install the fake
  ``pytest``** — a module of the core must not mutate ``sys.modules`` on
  import. :func:`main` installs it, and keeps one already installed.
"""
from __future__ import annotations

import asyncio
import contextlib
import gc
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import warnings
from pathlib import Path

from ogr_core.testing import runner as _R

_ROOT = Path(__file__).resolve().parent.parent


def _another_copy():
    """The runner module loaded a second time, by path: another module
    object, with its own ``Skipped`` class.

    Registered in ``sys.modules`` while it executes and removed after (rule
    5): ``dataclasses`` looks the module up there to read the string
    annotations of ``Hooks``, and fails without it."""
    name = "_ogr_runner_another_copy"
    spec = importlib.util.spec_from_file_location(name, _R.__file__)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop(name, None)
    return mod


_OTHER = _another_copy()


#: What the bodies of the async cases below leave behind when they run.
_RAN: list = []


async def _the_async_part():
    _RAN.append("the async part")


class _Cases:
    def test_exits(self):
        sys.exit(2)

    async def test_is_async(self):
        _RAN.append("the body of an async test")

    def test_drives_the_async_part(self):
        asyncio.run(_the_async_part())

    def test_skips(self):
        _R._FakePytest.skip("the bank is not on this machine")

    def test_skips_with_another_copys_pytest(self):
        _OTHER._FakePytest.skip("raised by another copy of the runner")

    def test_swallows_everything(self):
        try:
            _R._FakePytest.skip("still a skip")
        except Exception:                   # noqa: BLE001 - the point
            raise AssertionError("a test's except Exception caught the skip")

    def test_asserts(self):
        assert 1 == 2, "one is not two"

    def test_raises(self):
        raise ValueError("bad value")

    def test_passes(self):
        assert True


class TestATestThatExitsFails:
    def test_system_exit_is_that_tests_failure(self):
        outcome, why, tb = _R.run_test(_Cases, _Cases.test_exits)
        assert (outcome, why) == ("failed", "SystemExit: 2"), (outcome, why)
        assert "sys.exit(2)" in tb

    def test_the_other_outcomes_are_unchanged(self):
        assert _R.run_test(_Cases, _Cases.test_passes) == ("passed", None,
                                                          None)
        outcome, why, _ = _R.run_test(_Cases, _Cases.test_asserts)
        assert (outcome, why) == ("failed", "one is not two"), why
        outcome, why, _ = _R.run_test(_Cases, _Cases.test_raises)
        assert (outcome, why) == ("failed", "ValueError: bad value"), why


class TestASkipIsNeitherAPassNorAFailure:
    def test_it_is_skipped_with_its_reason(self):
        outcome, why, tb = _R.run_test(_Cases, _Cases.test_skips)
        assert (outcome, why, tb) == (
            "skipped", "the bank is not on this machine", None)

    def test_a_tests_except_exception_cannot_swallow_it(self):
        outcome, why, _ = _R.run_test(_Cases, _Cases.test_swallows_everything)
        assert (outcome, why) == ("skipped", "still a skip"), (outcome, why)

    def test_another_copys_skip_is_still_a_skip(self):
        assert _OTHER.Skipped is not _R.Skipped, "not another copy at all"
        try:
            outcome, why, _ = _R.run_test(
                _Cases, _Cases.test_skips_with_another_copys_pytest)
        except BaseException as exc:        # noqa: BLE001 - the defect
            raise AssertionError(
                "the runner let another copy's skip through: %r"
                % (exc,)) from None
        assert (outcome, why) == ("skipped",
                                  "raised by another copy of the runner"), (
            outcome, why)

    def test_the_totals_name_it(self):
        src = Path(_R.__file__).read_text(encoding="utf-8")
        assert 'Skipped: {skipped}' in src

    def test_the_loop_uses_it(self):
        """The run loop goes through ``run_test``: a helper the loop did
        not call would protect nothing."""
        src = Path(_R.__file__).read_text(encoding="utf-8")
        loop = src[src.index("for m_name, m in methods:"):]
        assert "run_test(cls, m)" in loop[:400]
        assert "except Exception" not in loop[:800]


#: One async test and one plain one, for a whole run.
_ASYNC_FILE = '''
import os

MARK = {mark!r}


class TestA:
    async def test_async_one(self):
        open(MARK, "w").close()

    def test_plain(self):
        pass
'''


class TestAnAsyncTestFailsInsteadOfPassingEmpty:
    def test_it_fails_and_says_what_to_do(self):
        outcome, why, tb = _R.run_test(_Cases, _Cases.test_is_async)
        assert outcome == "failed", (outcome, why)
        assert why.startswith("TypeError: test_is_async is `async def`"), why
        assert "asyncio.run" in why, why
        assert tb is not None

    def test_its_body_never_ran(self):
        del _RAN[:]
        _R.run_test(_Cases, _Cases.test_is_async)
        assert _RAN == [], _RAN

    def test_the_coroutine_is_closed_not_left_to_warn(self):
        # A coroutine nobody awaited warns when it is collected ("coroutine
        # ... was never awaited"): after the failure there must be none.
        with warnings.catch_warnings(record=True) as seen:
            warnings.simplefilter("always")
            _R.run_test(_Cases, _Cases.test_is_async)
            gc.collect()
        left = [str(w.message) for w in seen if "never awaited" in str(w.message)]
        assert left == [], left

    def test_a_plain_test_that_drives_the_async_part_passes(self):
        del _RAN[:]
        assert _R.run_test(_Cases, _Cases.test_drives_the_async_part) == (
            "passed", None, None)
        assert _RAN == ["the async part"], _RAN

    def test_in_a_whole_run_it_is_a_failure_and_the_run_is_red(self):
        folder = Path(tempfile.mkdtemp(prefix="ogr_test_async_"))
        mark = folder / "the-async-body-ran"
        (folder / "test_async_synthetic_v020.py").write_text(
            _ASYNC_FILE.format(mark=str(mark)), encoding="utf-8")
        saved_path = list(sys.path)
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                code = _R.main(folder)
            ran = mark.exists()
        finally:
            sys.path[:] = saved_path
            sys.modules.pop("test_async_synthetic_v020", None)
            shutil.rmtree(folder, ignore_errors=True)
        out = buf.getvalue()
        assert code == 1, out
        assert "Total: 2    Passed: 1    Failed: 1" in out, out
        assert "✗ test_async_one: TypeError: test_async_one is `async def`"             in out, out
        assert not ran, "the body of the async test ran"


def _fresh(code: str) -> str:
    """Run ``code`` in a fresh interpreter with this tree first on the path;
    its standard output."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    out = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)], env=env,
        capture_output=True, text=True, timeout=120, cwd=str(_ROOT))
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


class TestTheShimIsInstalledByMainOnly:
    def test_importing_the_runner_installs_nothing(self):
        got = _fresh("""
            import sys
            import ogr_core.testing.runner as r
            print("pytest" in sys.modules)
        """)
        assert got == "False", got

    def test_main_installs_it_and_keeps_the_first(self):
        got = _fresh("""
            import io, sys, tempfile, contextlib
            from pathlib import Path
            import ogr_core.testing.runner as r
            tests = Path(tempfile.mkdtemp()) / "tests"
            tests.mkdir()
            with contextlib.redirect_stdout(io.StringIO()):
                r.main(tests, patterns=["nothing-here"], own=())
            first = sys.modules["pytest"]
            with contextlib.redirect_stdout(io.StringIO()):
                r.main(tests, patterns=["nothing-here"], own=())
            print(getattr(first, "ogr_shim", False),
                  sys.modules["pytest"] is first)
        """)
        assert got == "True True", got
