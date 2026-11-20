# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.0 — the runner names what a test file leaves in the process, at the
file that leaves it, and the run fails (``ogr_core/testing/leaks.py``).

Moved from OGR Slip2D's ``test_leaks_v1374`` with the leak check itself
(OGR Core 0.2.0). There the four injected leaks were the interface's
language, an environment variable, a constant of the engine and a method of
one of its classes; here they are the core's own kind of the same four,
because this suite has no interface and no engine to leak into.

Invariants protected:

1. **Four leaks fail the file that leaves them**, each under its own key:
   the working folder, an environment variable, a constant of a core module
   and a method of one of its classes. A file that changes the same four
   and puts them back is not named. The run exits 1 and its totals say
   ``Leaks: 4`` while ``Failed`` stays 0: the tests passed, the files did
   not.
2. **What the suite's rules allow, and only that**, on synthetic snapshots:
   a library may move what its first import moves, in the file that imports
   it and no other; a value from a test file is a leak even on a key never
   seen; a builtin static member put back by attribute access is the same
   member, while a Python function put back bare where its staticmethod was
   is not; the application object is made once and never unmade; a table
   filled once from empty is not one that grew.
3. **A program's list adds to the suite's, and does not replace it**: a
   change only the program can explain is a leak with the suite's list
   alone and none with the program's entry added, in :func:`diff` and in a
   run; with the program's entry added, what numpy does on import is still
   allowed, and a change neither list explains is still a leak.
4. **The run's own folders are compared by what is in them**, under the key
   the runner was given: an INI file whose keys were all removed again is
   the same as none, and a folder nobody named is not looked at.
5. **A module attribute's value at import** is known only when the source
   assigns it once, to a literal.
6. **Every entry of the suite's list says why**, names a kind of key the
   snapshot takes, and names no program: what ``ogr_gui`` keeps is OGR
   Slip2D's to explain, in its own list.
7. **The locale Qt adopts, and nothing else of the locale** (OGR Core
   0.2.1). On Unix the first QApplication makes the process adopt the
   environment's locale (``setlocale(LC_ALL, "")``), and from OGR Slip2D
   v0.1.377 every Linux run of its CI named that as a leak of the first
   file that builds one. It is allowed in that file and for that change
   only: the same change in any other file, any other locale in that file,
   or a start that is not the interpreter's own, are leaks. The two values
   are measured in a fresh interpreter, never worked out from how a
   platform spells a locale; here they are both the ones of Slip2D's CI,
   as literals, and the ones of whatever machine runs this.

How: ``main()`` over throwaway files, as ``test_runner_state_v020`` does.
The inner run shares this process, so its leaks are this file's too: each
is put back before this file ends — or the outer runner names THIS file,
which is the check working.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import types
from pathlib import Path

import pytest  # the runner's own

from ogr_core.testing import leaks as _leaks
from ogr_core.testing import runner as _R

_VAR = "OGR_TEST_INJECTED_LEAK_V020"

_FILES = {
    # Its own folder, and not ``tempfile.gettempdir()``: the first call of
    # that in a process sets ``tempfile.tempdir``, which the check names too
    # (it did, in a chunk of --jobs, the first time these files ran in one).
    "test_a_folder.py": '''
import os


class TestA:
    def test_leaves_the_working_folder(self):
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
''',
    "test_b_environment.py": f'''
import os


class TestB:
    def test_leaves_a_variable(self):
        os.environ[{_VAR!r}] = "1"
''',
    "test_c_constant.py": '''
class TestC:
    def test_leaves_a_constant(self):
        import ogr_core.fem.mesh as m
        m.CONTAINS_TOL = 1.0
''',
    "test_d_method.py": '''
class TestD:
    def test_leaves_a_method(self):
        from ogr_core.fem.mesh import Mesh
        Mesh.locate = lambda self, x, y: None
''',
    "test_e_puts_back.py": f'''
import os


class TestE:
    def test_changes_all_and_puts_back(self):
        import ogr_core.fem.mesh as m
        from ogr_core.fem.mesh import Mesh
        folder, constant = os.getcwd(), m.CONTAINS_TOL
        method = Mesh.__dict__["locate"]
        try:
            os.chdir(os.path.dirname(os.path.abspath(__file__)))
            os.environ[{_VAR!r} + "_E"] = "1"
            m.CONTAINS_TOL = 2.0
            Mesh.locate = lambda self, x, y: None
        finally:
            os.chdir(folder)
            os.environ.pop({_VAR!r} + "_E", None)
            m.CONTAINS_TOL = constant
            Mesh.locate = method
''',
}


def _run_files(files: dict, **config) -> dict:
    """``main()`` over ``files`` in a fresh folder; what the throwaway files
    leave in this process is put back here (see the docstring)."""
    import ogr_core.fem.mesh as mesh

    folder = Path(tempfile.mkdtemp(prefix="ogr_test_leaks_"))
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    saved_path = list(sys.path)
    cwd = os.getcwd()
    constant = mesh.CONTAINS_TOL
    method = mesh.Mesh.__dict__["locate"]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            code = _R.main(folder, **config)
    finally:
        os.chdir(cwd)
        os.environ.pop(_VAR, None)
        mesh.CONTAINS_TOL = constant
        mesh.Mesh.locate = method
        sys.path[:] = saved_path
        for name in files:
            sys.modules.pop(name[:-3], None)
        shutil.rmtree(folder, ignore_errors=True)
    text = buf.getvalue()
    by_file = dict(re.findall(r"=== (\S+) ===[^\n]*\n(.*?)(?=\n=== |\n=+\n)",
                              text, flags=re.S))
    return {"code": code, "text": text, "by_file": by_file}


_SEEN: dict = {}


def _seen() -> dict:
    """Run the throwaway files once; their output, cut by file."""
    if not _SEEN:
        _SEEN.update(_run_files(_FILES))
    return _SEEN


def _leaks_in(run: dict, name: str) -> list:
    return [line.split("[LEAK] ", 1)[1]
            for line in run["by_file"][name].splitlines()
            if "✗ [LEAK]" in line]


def _leaks_of(name: str) -> list:
    return _leaks_in(_seen(), name)


class TestTheInjectedLeaksFailTheirFile:
    def test_the_working_folder(self):
        got = _leaks_of("test_a_folder.py")
        assert len(got) == 1 and got[0].startswith("cwd: "), got
        assert " → " in got[0], got

    def test_an_environment_variable(self):
        got = _leaks_of("test_b_environment.py")
        assert got == [f"env:{_VAR}: (absent) → 1"], got

    def test_a_constant_of_the_core(self):
        got = _leaks_of("test_c_constant.py")
        assert got == ["mod:ogr_core.fem.mesh.CONTAINS_TOL: 1e-09 → 1.0"], got

    def test_a_method_of_one_of_its_classes(self):
        got = _leaks_of("test_d_method.py")
        assert len(got) == 1, got
        assert got[0].startswith("cls:ogr_core.fem.mesh.Mesh.locate:")
        # named as coming from a test file
        assert got[0].endswith(_leaks.FROM_A_TEST), got

    def test_a_file_that_puts_everything_back_is_not_named(self):
        assert _leaks_of("test_e_puts_back.py") == []

    def test_the_run_fails_and_says_how_many_files_leaked(self):
        s = _seen()
        assert s["code"] == 1, s["text"]
        assert "Total: 5    Passed: 5    Failed: 0    Leaks: 4" in s["text"], s["text"]


def _snap(modules=(), **values):
    s = dict(values)
    s["__modules__"] = frozenset(modules)
    return s


class TestTheRules:
    def test_a_first_import_moves_what_it_moves_in_its_own_file_only(self):
        before = _snap(["random"], **{"random.state": "#1"})
        assert _leaks.diff(before, _snap(["random", "rich", "rich.style"],
                                         **{"random.state": "#2"})) == []
        assert _leaks.diff(before, _snap(["random"],
                                         **{"random.state": "#2"})) != []

    def test_warning_filters_may_only_be_added_by_a_first_import(self):
        before = _snap(["warnings"], **{"warnings.filters": ("a",)})
        added = _snap(["warnings", "numpy"], **{"warnings.filters": ("a", "b")})
        removed = _snap(["warnings", "numpy"], **{"warnings.filters": ("b",)})
        assert _leaks.diff(before, added) == []
        assert _leaks.diff(before, removed) != []

    def test_a_value_from_a_test_file_is_a_leak_on_a_new_key(self):
        key = "qt.QFileDialog.getOpenFileName"
        assert _leaks.diff(_snap(), _snap(**{key: "function@1!test"})) != []
        assert _leaks.diff(_snap(), _snap(**{key: "builtin@1"})) == []

    def test_a_new_environment_variable_is_a_leak(self):
        assert _leaks.diff(_snap(), _snap(**{"env:X": "1"})) != []

    def test_a_key_that_disappears_is_a_leak(self):
        assert _leaks.diff(_snap(**{"env:X": "1"}), _snap()) != []

    def test_a_builtin_put_back_by_attribute_access_is_the_same(self):
        assert _leaks.value_of(staticmethod(len)) == _leaks.value_of(len)

    def test_a_python_function_put_back_bare_is_not(self):
        def f():
            pass
        assert _leaks.value_of(staticmethod(f)) == _leaks.value_of(staticmethod(f))
        assert _leaks.value_of(staticmethod(f)) != _leaks.value_of(f)

    def test_the_automatic_backend_is_settled_once(self):
        assert _leaks.diff(_snap(**{"mpl.backend": "auto"}),
                           _snap(**{"mpl.backend": "'QtAgg'"})) == []
        assert _leaks.diff(_snap(**{"mpl.backend": "'QtAgg'"}),
                           _snap(**{"mpl.backend": "'Agg'"})) != []

    def test_a_table_filled_once_from_empty(self):
        key = "mod:ogr_core.report.report_generator._FONTS"
        assert _leaks.diff(_snap(**{key: "dict@7:len=0#1"}),
                           _snap(**{key: "dict@7:len=4"})) == []
        assert _leaks.diff(_snap(**{key: "dict@7:len=4"}),
                           _snap(**{key: "dict@7:len=5"})) != []
        assert _leaks.diff(_snap(**{key: "dict@7:len=0#1"}),
                           _snap(**{key: "dict@8:len=4"})) != []

    def test_the_application_is_made_once_and_never_unmade(self):
        key = "builtins.qApp"
        assert _leaks.diff(_snap(**{key: "None"}),
                           _snap(**{key: "QApplication@1"})) == []
        assert _leaks.diff(_snap(**{key: "QApplication@1"}),
                           _snap(**{key: "None"})) != []


#: What only a program can explain: its interface installs a guard in the
#: application, once (the entry is OGR Slip2D's, word for word).
_PROGRAMS = (
    _leaks.Allow("mod:ogr_gui.wheel_guard._guard", _leaks.INSTALLED,
                 "the wheel guard, installed in the application by the "
                 "first window"),
)
_GUARD = "mod:ogr_gui.wheel_guard._guard"

#: One change only the program's entry explains (a tolerance left changed)
#: and one only the suite's does (the epoch of the mesh indexes, which
#: ``invalidate_mesh_indexes`` moves on purpose): a run is clean only when
#: it is checked against the two lists together.
_LEAVES_A_MARK = {
    "test_a_marks.py": '''
class TestA:
    def test_leaves_a_tolerance_and_moves_the_epoch(self):
        import ogr_core.fem.mesh as m
        m.DEGENERATE_DET = 0.5
        m.invalidate_mesh_indexes()
''',
}


class TestAProgramsListAddsToTheSuites:
    def test_with_the_suites_alone_the_programs_change_is_a_leak(self):
        before, after = _snap(**{_GUARD: "None"}), _snap(**{_GUARD: "WheelGuard@1"})
        assert _leaks.diff(before, after) != []
        assert _leaks.diff(before, after, _leaks.ALLOWED) != []

    def test_with_its_entry_added_it_is_not(self):
        both = _leaks.ALLOWED + _PROGRAMS
        assert _leaks.diff(_snap(**{_GUARD: "None"}),
                           _snap(**{_GUARD: "WheelGuard@1"}), both) == []
        # installed again is still allowed, removed is still a leak: the
        # entry's own rule decides, not its mere presence
        assert _leaks.diff(_snap(**{_GUARD: "WheelGuard@1"}),
                           _snap(**{_GUARD: "WheelGuard@2"}), both) == []
        assert _leaks.diff(_snap(**{_GUARD: "WheelGuard@1"}),
                           _snap(**{_GUARD: "None"}), both) != []

    def test_the_suites_entries_still_hold_with_it(self):
        both = _leaks.ALLOWED + _PROGRAMS
        before = _snap(["warnings"], **{"warnings.filters": ("a",)})
        added = _snap(["warnings", "numpy"], **{"warnings.filters": ("a", "b")})
        assert _leaks.diff(before, added, both) == []
        # and the program's list alone would name what numpy does on import
        assert _leaks.diff(before, added, _PROGRAMS) != []

    def test_a_change_neither_explains_is_still_a_leak(self):
        both = _leaks.ALLOWED + _PROGRAMS
        assert _leaks.diff(_snap(**{"env:X": "1"}),
                           _snap(**{"env:X": "2"}), both) != []

    def test_in_a_run_the_entry_reaches_the_check(self):
        key = "mod:ogr_core.fem.mesh.DEGENERATE_DET"
        import ogr_core.fem.mesh as mesh
        value = mesh.DEGENERATE_DET
        try:
            named = _run_files(_LEAVES_A_MARK)
            mesh.DEGENERATE_DET = value
            allowed = _run_files(_LEAVES_A_MARK, allowed=(
                _leaks.Allow(key, _leaks.ANY,
                             "a synthetic entry of this test's own"),))
        finally:
            mesh.DEGENERATE_DET = value
        assert named["code"] == 1, named["text"]
        assert _leaks_in(named, "test_a_marks.py") == [f"{key}: 1e-15 → 0.5"]
        # clean only with BOTH lists: the program's entry for the tolerance,
        # the suite's for the epoch
        assert allowed["code"] == 0, allowed["text"]
        assert _leaks_in(allowed, "test_a_marks.py") == []


#: The two values of OGR Slip2D's CI (ubuntu, Python 3.11 to 3.13), whole:
#: what glibc answers as the interpreter starts, and once Qt has made the
#: process adopt the environment's locale.
_LINUX_STARTUP = ("LC_CTYPE=C.UTF-8;LC_NUMERIC=C;LC_TIME=C;LC_COLLATE=C;"
                  "LC_MONETARY=C;LC_MESSAGES=C;LC_PAPER=C;LC_NAME=C;"
                  "LC_ADDRESS=C;LC_TELEPHONE=C;LC_MEASUREMENT=C;"
                  "LC_IDENTIFICATION=C")
_LINUX_ADOPTED = "C.UTF-8"
_APP = "__application__"

#: What a fresh interpreter does to see the real thing (see the test).
_ADOPTS = """
    import json, locale
    from ogr_core.testing import leaks

    def named(found):
        return [list(f) for f in found if f[0] == "locale"]

    before = leaks.snapshot()
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error as exc:
        print(json.dumps({"error": str(exc)}))
        raise SystemExit(0)
    after = leaks.snapshot()
    made = dict(after, __application__=True)
    locale.setlocale(locale.LC_ALL, "C")
    other = dict(leaks.snapshot(), __application__=True)
    print(json.dumps({
        "startup": before["locale"], "adopted": after["locale"],
        "measured": leaks.environment_locale(),
        "with_the_application": named(leaks.diff(before, made)),
        "without_it": named(leaks.diff(before, after)),
        "another_locale": named(leaks.diff(before, other))}))
"""


@contextlib.contextmanager
def _measuring(answer):
    """The check, told what a fresh interpreter would measure."""
    saved = _leaks.environment_locale
    _leaks.environment_locale = lambda: answer
    try:
        yield
    finally:
        _leaks.environment_locale = saved


class TestTheLocaleQtAdopts:
    def _diff(self, was, now, app_before=False, app_after=True):
        before = _snap(locale=was)
        after = _snap(locale=now)
        if app_before:
            before[_APP] = True
        if app_after:
            after[_APP] = True
        with _measuring((_LINUX_STARTUP, _LINUX_ADOPTED)):
            return _leaks.diff(before, after)

    def test_in_the_file_that_makes_the_first_application_it_is_not_a_leak(self):
        assert self._diff(_LINUX_STARTUP, _LINUX_ADOPTED) == []

    def test_the_same_change_in_any_other_file_is(self):
        # the application was there already: a later file
        got = self._diff(_LINUX_STARTUP, _LINUX_ADOPTED, app_before=True)
        assert got == [("locale", _LINUX_STARTUP, _LINUX_ADOPTED)], got
        # and a file in a process with no application at all
        assert self._diff(_LINUX_STARTUP, _LINUX_ADOPTED,
                          app_after=False) != []

    def test_another_locale_in_that_file_is(self):
        assert self._diff(_LINUX_STARTUP, "es_ES.UTF-8") != []
        # one category moved after adopting is another locale too
        moved = _LINUX_STARTUP.replace("LC_NUMERIC=C", "LC_NUMERIC=es_ES.UTF-8")
        assert self._diff(_LINUX_STARTUP, moved) != []

    def test_a_start_that_is_not_the_interpreters_is(self):
        assert self._diff("es_ES.UTF-8", _LINUX_ADOPTED) != []

    def test_it_is_a_leak_when_it_cannot_be_measured(self):
        before = _snap(locale=_LINUX_STARTUP)
        after = _snap(locale=_LINUX_ADOPTED, **{_APP: True})
        with _measuring(None):
            assert _leaks.diff(before, after) != []

    def test_making_the_application_is_what_the_rule_is_told(self):
        seen = []

        def probe(was, now, new):
            seen.append(_leaks.FIRST_APPLICATION in new)
            return True

        entry = (_leaks.Allow("locale", probe, "a probe of this test's own, "
                              "to see what a rule is told"),)
        a, b = _snap(locale="x"), _snap(locale="y")
        _leaks.diff(a, dict(b, **{_APP: True}), entry)        # made here
        _leaks.diff(dict(a, **{_APP: True}), dict(b, **{_APP: True}), entry)
        _leaks.diff(a, b, entry)                              # never made
        assert seen == [True, False, False], seen

    def test_the_mark_is_not_itself_compared(self):
        assert _leaks.diff(_snap(), _snap(**{_APP: True})) == []
        assert _leaks.diff(_snap(**{_APP: True}), _snap()) == []

    def test_on_this_machine_with_its_own_locale(self):
        """The real thing, end to end, with no literal: a fresh interpreter
        takes a snapshot, adopts the environment's locale as Qt does, and
        takes another. With the application made in between it is no leak;
        without it, or with another locale, it is."""
        tree = str(Path(_R.__file__).resolve().parents[2])
        env = dict(os.environ)
        env["PYTHONPATH"] = tree + os.pathsep + env.get("PYTHONPATH", "")
        out = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(_ADOPTS)], env=env,
            capture_output=True, text=True, timeout=180,
            stdin=subprocess.DEVNULL)
        assert out.returncode == 0, out.stderr
        got = json.loads(out.stdout.strip().splitlines()[-1])
        if "error" in got:
            pytest.skip(f"this environment's locale cannot be set: "
                        f"{got['error']}")
        if got["startup"] == got["adopted"]:
            pytest.skip("on this machine the environment's locale is the one "
                        f"the interpreter starts with ({got['startup']!r}): "
                        "there is no change to allow")
        assert got["measured"] == [got["startup"], got["adopted"]], got
        assert got["with_the_application"] == [], got
        assert got["without_it"] == [["locale", got["startup"],
                                      got["adopted"]]], got
        assert got["another_locale"] != [], got


class TestTheRunsOwnFolders:
    def test_an_ini_with_its_keys_removed_is_the_same_as_none(self):
        folder = Path(tempfile.mkdtemp(prefix="ogr_test_leaks_ini_"))
        try:
            assert _leaks._folder_files(str(folder)) == ()
            ini = folder / "ogr-slip2d.ini"
            ini.write_text("[General]\ntheme=dark\n", encoding="utf-8")
            assert _leaks._folder_files(str(folder)) == (
                "ogr-slip2d.ini: [General] theme=dark",)
            ini.write_text("[General]\n", encoding="utf-8")
            assert _leaks._folder_files(str(folder)) == ()
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_a_named_folder_is_read_under_its_key_and_no_other_is(self):
        var = "OGR_TEST_LEAKS_FOLDER_V020"
        folder = Path(tempfile.mkdtemp(prefix="ogr_test_leaks_dir_"))
        (folder / "left.txt").write_text("x", encoding="utf-8")
        saved = os.environ.get(var)
        os.environ[var] = str(folder)
        try:
            assert _leaks.snapshot({var: "prefs"})["prefs"] == ("left.txt",)
            assert "prefs" not in _leaks.snapshot()
            assert "settings" not in _leaks.snapshot()
        finally:
            if saved is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = saved
            shutil.rmtree(folder, ignore_errors=True)


class TestTheValueAtImport:
    def test_assigned_once_to_a_literal(self):
        import ogr_core.fem.mesh  # noqa: F401
        assert _leaks.import_default("ogr_core.fem.mesh",
                                     "CONTAINS_TOL") == "1e-09"

    def test_assigned_twice_or_computed_is_unknown(self):
        folder = Path(tempfile.mkdtemp(prefix="ogr_test_leaks_mod_"))
        try:
            path = folder / "synthetic.py"
            path.write_text(
                'ONCE = 3\n'
                'TWICE = "unknown"\n'
                'TWICE = "0.2.0"\n'
                'COMPUTED = len("abc")\n'
                'try:\n    IN_A_BLOCK = 1\nexcept Exception:\n    pass\n',
                encoding="utf-8")
            mod = types.ModuleType("synthetic")
            mod.__file__ = str(path)
            table = _leaks._literal_table(mod)
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        assert table == {"ONCE": "3", "IN_A_BLOCK": "1"}, table


class TestTheAllowList:
    def test_every_entry_says_why(self):
        assert len(_leaks.ALLOWED) >= 10
        for a in _leaks.ALLOWED:
            assert len(a.why) >= 20, a

    def test_every_entry_names_a_kind_of_key_the_snapshot_takes(self):
        kinds = ("mod:", "cls:", "env:", "qt.", "sys.", "warnings.",
                 "random.", "mpl.", "mp.", "builtins.", "locale")
        for a in _leaks.ALLOWED:
            assert a.key.startswith(kinds), a.key

    def test_no_entry_is_about_a_programs_own_package(self):
        programs = ("ogr_gui", "ogr_api", "ogr_cli", "ogr_mcp", "ogr_slip2d",
                    "ogr_fem2d")
        for a in _leaks.ALLOWED:
            assert not any(p in a.key for p in programs), a.key
            if a.key.startswith(("mod:", "cls:")):
                assert a.key.split(":", 1)[1].startswith("ogr_core."), a.key
