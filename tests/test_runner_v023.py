# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.3 — a test file can import another one however the run was started,
and the runner's advice on a core that is not the pinned one names what the
suite does today.

What was found.

1. **A test file could import another only because of how the runner was
   started.** ``python tests/_runner.py`` makes the interpreter put
   ``tests/`` first on ``sys.path``; nothing in the runner did. Started any
   other way the same file failed to load, with ``ModuleNotFoundError``:
   with ``runpy`` (``test_runner_shutdown_v020`` starts it so, and failed
   the day the file it runs began to import another test file), in the
   chunks of ``--jobs`` for a folder with no ``_runner.py`` of its own
   (they are started by the path of the runner module), and in a
   ``main()`` driven by a test over a folder of its own. In OGR Slip2D
   more than a hundred test files import another.
2. **The message of a refused core recommended what the suite stopped
   doing.** ``WRONG SHARED TREE`` ended with "or check out its tag in the
   editable tree". Since v0.2.2 every program's environment has the pinned
   tag installed, so that two programs can pin different versions, and a
   core that is being changed is run with ``PYTHONPATH`` and
   ``--dev-core``. OGR FEM2D asked for the change.

Invariants protected:

1. **The folder of a test file is on ``sys.path`` while that file loads and
   runs**, first, in each of the four ways a run starts: a ``main()`` in
   this process, the chunks of ``--jobs`` of a folder with no runner of its
   own, a runner started with ``runpy``, and ``python <folder>/_runner.py``.
2. **A run started the ordinary way gets nothing added**: the folder is
   there once, where the interpreter and the repository's runner left it.
3. **The path is put back**: after a ``main()`` in this process
   ``sys.path`` is the list it was, entry by entry.
4. **The advice says how to get the pinned version** (install the one
   ``pyproject.toml`` pins) and no longer names the editable tree; and
   ``--dev-core`` stays named only on the line of a package it would help
   with, as since v0.2.0.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ogr_core.testing import runner as _R

_TREE = Path(_R.__file__).resolve().parents[2]
_OUT = "OGR_TEST_V023_OUT"

#: Two test files, the first importing the second: by name, the first is
#: loaded before the runner itself loads the second, so the import has to
#: find it on the path. It writes down where its own folder is on the path.
_FILES = {
    "test_v023_1_user.py": f'''
import json
import os
import sys
from pathlib import Path

from test_v023_2_shared import VALUE


def _same(entry):
    return os.path.normcase(os.path.abspath(entry))


class TestUser:
    def test_it_got_the_value(self):
        assert VALUE == 7
        here = _same(os.path.dirname(__file__))
        at = [i for i, p in enumerate(sys.path) if _same(p) == here]
        Path(os.environ["{_OUT}"], "path.json").write_text(
            json.dumps(at), encoding="utf-8")
''',
    "test_v023_2_shared.py": '''
VALUE = 7


class TestShared:
    def test_it_is_a_test_file_too(self):
        assert VALUE == 7
''',
}

#: A repository's own ``tests/_runner.py``, reduced to what every one does.
_OWN_RUNNER = '''
import sys
from pathlib import Path

sys.path.insert(0, {tree!r})

from ogr_core.testing import runner

if __name__ == "__main__":
    sys.exit(runner.cli(Path(__file__).resolve().parent))
'''


@contextlib.contextmanager
def _folder(own_runner: bool = False):
    """The two files in a fresh folder, and a folder for what they write
    down; both gone afterwards, with what this process learnt of them."""
    folder = Path(tempfile.mkdtemp(prefix="ogr_test_v023_files_"))
    out = Path(tempfile.mkdtemp(prefix="ogr_test_v023_out_"))
    for name, text in _FILES.items():
        (folder / name).write_text(text, encoding="utf-8")
    if own_runner:
        (folder / "_runner.py").write_text(
            _OWN_RUNNER.format(tree=str(_TREE)), encoding="utf-8")
    saved = os.environ.get(_OUT)
    os.environ[_OUT] = str(out)
    try:
        yield folder, out
    finally:
        if saved is None:
            os.environ.pop(_OUT, None)
        else:
            os.environ[_OUT] = saved
        for name in _FILES:
            sys.modules.pop(name[:-3], None)
        shutil.rmtree(folder, ignore_errors=True)
        shutil.rmtree(out, ignore_errors=True)


def _where(out: Path):
    path = out / "path.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() \
        else None


def _in_this_process(**kw) -> dict:
    with _folder() as (folder, out):
        before = list(sys.path)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = _R.main(folder, **kw)
        after = list(sys.path)
        return {"code": code, "text": buf.getvalue(), "at": _where(out),
                "path_kept": after == before}


def _in_its_own_process(code: str) -> dict:
    """``code`` (with ``{runner}`` for the folder's own runner) in a Python
    of its own, started somewhere else, with a temporary folder of its own
    so that it writes none of the machine's files."""
    with _folder(own_runner=True) as (folder, out):
        tmp = tempfile.mkdtemp(prefix="ogr_test_v023_tmp_")
        env = dict(os.environ, TEMP=tmp, TMP=tmp, TMPDIR=tmp)
        env.pop("PYTHONPATH", None)
        runner = str(folder / "_runner.py")
        argv = ([sys.executable, runner] if code is None else
                [sys.executable, "-c", code.replace("{runner}", repr(runner))])
        try:
            run = subprocess.run(
                argv, env=env, cwd=tmp, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                stdin=subprocess.DEVNULL, timeout=300)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return {"code": run.returncode, "text": run.stdout + run.stderr,
                "at": _where(out)}


_RUNPY = ("import runpy, sys; sys.argv = [{runner}]; "
          "runpy.run_path({runner}, run_name='__main__')")

_GREEN = "Total: 2    Passed: 2    Failed: 0"


class TestATestFileImportsAnother:
    def test_in_a_main_driven_from_this_process(self):
        run = _in_this_process()
        assert run["code"] == 0 and _GREEN in run["text"], run["text"]
        assert run["at"] == [0], run["at"]

    def test_in_the_chunks_of_a_folder_with_no_runner_of_its_own(self):
        run = _in_this_process(jobs=2)
        assert run["code"] == 0 and _GREEN in run["text"], run["text"]
        assert "PARALLEL RUN" in run["text"], run["text"]
        assert run["at"] == [0], run["at"]

    def test_in_a_runner_started_with_runpy(self):
        run = _in_its_own_process(_RUNPY)
        assert run["code"] == 0 and _GREEN in run["text"], run["text"]
        assert run["at"] == [0], run["at"]

    def test_and_started_the_ordinary_way_nothing_is_added(self):
        """The interpreter put the folder first and the folder's runner put
        the tree before it: one entry, the second, and no other."""
        run = _in_its_own_process(None)
        assert run["code"] == 0 and _GREEN in run["text"], run["text"]
        assert run["at"] == [1], run["at"]

    def test_no_file_is_said_to_leak_for_it(self):
        for run in (_in_this_process(), _in_this_process(jobs=2)):
            assert "LEAK" not in run["text"], run["text"]


class TestThePathIsPutBack:
    def test_after_a_main_in_this_process(self):
        assert _in_this_process()["path_kept"]
        assert _in_this_process(jobs=2)["path_kept"]

    def test_the_folders_of_the_run_are_not_left_on_it(self):
        with _folder() as (folder, _out):
            with contextlib.redirect_stdout(io.StringIO()):
                _R.main(folder)
            assert not _R._on_path(folder)


class TestWhatIsAlreadyOnThePath:
    def _with(self, entries, check):
        saved = list(sys.path)
        try:
            sys.path[:] = entries
            return check()
        finally:
            sys.path[:] = saved

    def test_however_the_entry_is_written(self):
        here = Path(tempfile.mkdtemp(prefix="ogr_test_v023_path_"))
        cwd = os.getcwd()
        try:
            os.chdir(here)
            inner = here / "tests"
            inner.mkdir()
            assert self._with([str(inner)], lambda: _R._on_path(inner))
            assert self._with(["tests"], lambda: _R._on_path(inner))
            assert self._with([str(inner) + os.sep],
                              lambda: _R._on_path(inner))
            # the empty entry stands for the working directory
            assert self._with([""], lambda: _R._on_path(here))
            assert not self._with([""], lambda: _R._on_path(inner))
            assert not self._with([str(here)], lambda: _R._on_path(inner))
            assert not self._with([], lambda: _R._on_path(inner))
        finally:
            os.chdir(cwd)
            shutil.rmtree(here, ignore_errors=True)


# ----------------------------------------------------------------------
def _refused(version: str = "0.1.1") -> tuple:
    """A run over a core that says ``version`` where 0.1.0 is pinned."""
    repo = Path(tempfile.mkdtemp(prefix="ogr_test_v023_core_"))
    package = repo / "ogr_core"
    package.mkdir()
    (package / "__init__.py").write_text(f'__version__ = "{version}"\n',
                                         encoding="utf-8")
    saved = _R.package_origins
    buf = io.StringIO()
    try:
        _R.package_origins = lambda names: {n: package for n in names}
        with _folder() as (folder, _out), contextlib.redirect_stdout(buf):
            code = _R.main(folder, shared=("ogr_core",),
                           pinned={"ogr_core": "0.1.0"})
    finally:
        _R.package_origins = saved
        shutil.rmtree(repo, ignore_errors=True)
    return code, buf.getvalue()


class TestTheAdviceOnACoreThatIsNotThePinnedOne:
    def test_it_is_still_refused_and_nothing_runs(self):
        code, out = _refused()
        assert code == 2 and "WRONG SHARED TREE" in out, out
        assert "Total:" not in out, out

    def test_it_says_how_to_get_the_pinned_version(self):
        _, out = _refused()
        advice = out.split("this runner lives in", 1)[1]
        for word in ("Install", "pyproject.toml", "--no-deps",
                     "--force-reinstall"):
            assert word in advice, (word, advice)

    def test_the_option_is_named_only_where_it_would_help(self):
        """The invariant of v0.2.0 (``test_runner_dev_core_v020``), which the
        first wording of this advice broke by naming ``--dev-core`` for
        every refusal: a later release or an older core gets no such hint,
        and a development version of a later release gets it on its line."""
        for version in ("0.1.1", "0.0.9", "0.1.0.dev0"):
            _, out = _refused(version)
            assert "--dev-core" not in out, (version, out)
        _, out = _refused("0.2.0.dev0")
        line = [ln for ln in out.splitlines() if "0.2.0.dev0" in ln]
        assert len(line) == 1 and "--dev-core" in line[0], out
        assert "--dev-core" not in out.split("this runner lives in", 1)[1]

    def test_and_not_the_editable_tree(self):
        for version in ("0.1.1", "0.2.0.dev0"):
            _, out = _refused(version)
            assert "editable" not in out.lower(), out
