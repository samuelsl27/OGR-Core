# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.0 — the runner never ends the process itself: its totals are written
out in full, what the program must undo is undone with Python alive, and
the interpreter's own shutdown then runs, so that a crash in it shows.

Moved from OGR Slip2D's ``test_runner_shutdown_v1377`` with the runner (OGR
Core 0.2.0), in the form it has there since v0.1.422.

The history, because it explains every line of the ending. From Slip2D
v0.1.276 every CI run on Linux ended with exit 139: all tests passed, the
totals were printed, and then the interpreter, tearing down what the suite
left alive, segfaulted inside Qt. v0.1.377 hid that off Windows by ending
the process with ``os._exit`` after the totals (not on Windows, where
``os._exit`` goes through ``ExitProcess`` and two chunks of four died with
0xC0000005: measured A/B). v0.1.422 found the cause — windows without a
parent that the tests left alive, deleted one by one, in no order, by
PySide's own exit hook — and removed it by deleting them first, with Python
alive; and by the owner's decision of 2026-11-04 the ``os._exit`` went, so
that a crash at shutdown is seen again on every platform. Here the deleting
is the program's ``after_run`` hook (the core has no windows), and what this
file holds is the frame around it.

Invariants protected:

1. **A crash at the interpreter's shutdown is seen**: a green run whose
   shutdown crashes exits with the crash's code, not 0, on every platform.
2. **The totals are written out in full before it**: the streams are
   emptied before the end. The same crash without the runner loses what was
   still buffered (the injected crash is real).
3. **``after_run`` is called once, by the command line and only by it**,
   after everything was printed, whatever the verdict; an inner ``main()``
   — a test driving the runner — never calls it.

How: for 1 and 2, this repository's runner as ``__main__`` (``runpy``), in
a process of its own with a crash registered with ``atexit`` before it
starts: only a process of its own can show how a process ends. Its temporary
folder is one of the test's own, so that it writes none of the machine's
files. For 3, :func:`cli` over a throwaway folder, in this process.
"""
from __future__ import annotations

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ogr_core.testing import runner as _R

_TESTS = Path(__file__).resolve().parent
_RUNNER = _TESTS / "_runner.py"

#: What the interpreter's shutdown did in Slip2D's CI from v0.1.276, as far
#: as the exit code goes: atexit handlers run at shutdown, so this one ends
#: the process with 139 there and only there.
_CRASH_AT_SHUTDOWN = "import atexit, os; atexit.register(os._exit, 139); "


def _run(code: str) -> subprocess.CompletedProcess:
    tmp = tempfile.mkdtemp(prefix="ogr_test_shutdown_")
    env = dict(os.environ, TEMP=tmp, TMP=tmp, TMPDIR=tmp)
    # Buffered, as a redirected stdout is by default: unbuffered (a CI may
    # set PYTHONUNBUFFERED) nothing would be left to lose, and the flush
    # before the end would go untested.
    env.pop("PYTHONUNBUFFERED", None)
    try:
        return subprocess.run([sys.executable, "-c", code], env=env,
                              cwd=str(_TESTS.parent), capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              stdin=subprocess.DEVNULL, timeout=300)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _runner_with_crash(*args: str) -> subprocess.CompletedProcess:
    # v0.2.3 -- ``runpy`` does not put the folder of the script on the path,
    # as the interpreter does for ``python tests/_runner.py``. The file this
    # run uses, ``test_license_v10``, imports another test file since then,
    # and here it did not load (``ModuleNotFoundError``): one test of this
    # file failed. The runner now puts each file's folder there itself, so
    # nothing is done about it here, and this run is one more proof of it.
    return _run(_CRASH_AT_SHUTDOWN
                + "import runpy, sys; "
                + f"sys.argv = [{str(_RUNNER)!r}, *{list(args)!r}]; "
                + f"runpy.run_path({str(_RUNNER)!r}, run_name='__main__')")


_RUNS: dict = {}


def _once(key, make):
    if key not in _RUNS:
        _RUNS[key] = make()
    return _RUNS[key]


def _green():
    # One real test, cheap: it only reads the sources.
    return _once("green", lambda: _runner_with_crash(
        "test_license_v10", "-k", "test_copyright_line_present"))


class TestACrashAtShutdownIsSeen:
    def test_a_green_run_ends_with_the_crash_not_with_zero(self):
        run = _green()
        assert run.returncode == 139, (run.returncode, run.stdout[-2000:],
                                       run.stderr[-2000:])

    def test_with_its_totals_written_out(self):
        out = _green().stdout
        assert "Total: 1    Passed: 1    Failed: 0" in out
        # the banner after the totals is the last thing main() prints
        assert out.rstrip().splitlines()[-1].startswith("FILTERED RUN")

    def test_the_crash_is_real_without_the_runner(self):
        run = _run(_CRASH_AT_SHUTDOWN + "print('done')")
        assert run.returncode == 139
        # And what was still in the buffer is lost with it: why the runner
        # flushes before its own end, and why its totals are there above.
        assert run.stdout == ""

    def test_the_runner_has_no_ending_of_its_own(self):
        # ``os._exit`` appears in the module only as history, in comments
        # and docstrings: never called.
        import ast
        tree = ast.parse(Path(_R.__file__).read_text(encoding="utf-8"))
        calls = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Attribute) and n.attr == "_exit"]
        assert calls == []


def _cli(files: dict, argv, **config) -> tuple[int, str]:
    folder = Path(tempfile.mkdtemp(prefix="ogr_test_shutdown_files_"))
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    saved_path = list(sys.path)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            code = _R.cli(folder, argv, **config)
    finally:
        sys.path[:] = saved_path
        for name in files:
            sys.modules.pop(name[:-3], None)
        shutil.rmtree(folder, ignore_errors=True)
    return code, buf.getvalue()


_PASSES = {"test_a.py": "class TestA:\n    def test_a(self):\n        pass\n"}
_FAILS = {"test_a.py": "class TestA:\n    def test_a(self):\n"
                       "        assert False\n"}


class TestAfterRunIsTheCommandLines:
    def test_called_once_after_everything_was_printed(self):
        seen: list = []
        buf_at_call: list = []

        def after():
            seen.append("after")
            buf_at_call.append(sys.stdout.getvalue())

        code, out = _cli(_PASSES, [], hooks=_R.Hooks(after_run=after))
        assert code == 0, out
        assert seen == ["after"]
        assert "Total: 1    Passed: 1    Failed: 0" in buf_at_call[0]

    def test_called_whatever_the_verdict(self):
        seen: list = []
        hooks = _R.Hooks(after_run=lambda: seen.append("after"))
        code, out = _cli(_FAILS, [], hooks=hooks)
        assert code == 1, out
        code, out = _cli(_PASSES, ["no_such_file_v020"], hooks=hooks)
        assert code == 2, out
        assert seen == ["after", "after"]

    def test_an_inner_main_never_calls_it(self):
        seen: list = []
        folder = Path(tempfile.mkdtemp(prefix="ogr_test_shutdown_inner_"))
        (folder / "test_a.py").write_text(_PASSES["test_a.py"],
                                          encoding="utf-8")
        saved_path = list(sys.path)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                code = _R.main(folder, hooks=_R.Hooks(
                    after_run=lambda: seen.append("after")))
        finally:
            sys.path[:] = saved_path
            sys.modules.pop("test_a", None)
            shutil.rmtree(folder, ignore_errors=True)
        assert code == 0
        assert seen == []
