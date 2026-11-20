# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.3 — the tests that read every source of the project read the hidden
folders that hold code too, and no hidden folder with code goes undecided.

What was found. Three tests go over "every ``.py`` of the repository": the
licence headers (``test_license_v10``), the syntax of the oldest Python the
project claims (``test_python_floor_v10``) and the commercial product names
(``test_no_vendor_names_v10``). The first two looked for them with
``glob("**/*.py", recursive=True)``, which does not enter a folder whose
name begins with a dot; the third named two folders, ``ogr_core`` and
``tests``. None of the three saw ``.github/scripts/program_suite.py``, the
first Python file of this repository in a hidden folder (the script of the
CI, v0.2.3): it carried its header, and no test would have failed without
it. Measured on that commit: 169 files with the pattern of the tests, 170
with the hidden folders.

Asking ``glob`` for the hidden ones (``include_hidden``) is not the answer:
it enters every one of them, and an environment somebody makes inside the
tree (``.venv``, as the programs of the suite have) is thousands of files
that are nobody's here, with no header. Asking git which files are the
project's is not either: it does not see a file until it is added, which is
the very case the licence test is for. So the hidden folders are a declared
list, and what keeps the list honest is that a hidden folder with Python in
it has to be in one of its two halves.

Invariants protected:

1. **A hidden folder that holds code of the project is read**
   (:data:`HIDDEN_WITH_CODE`), by the three tests: each of them takes its
   files from :func:`python_files`, and this file checks that each one sees
   the script of the CI.
2. **No hidden folder with a Python file in it is left undecided**, at any
   depth: it is read, or it is in :data:`HIDDEN_NOT_OURS` with its reason.
   A new one fails here until somebody decides.
3. **What is not hidden is read as before**: every ``.py`` under the root,
   except ``__pycache__``.

Nothing here imports anything outside the standard library: the licence job
of the CI imports ``test_license_v10`` on a bare Python.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

#: Hidden folders that hold code of this project, as paths from the root:
#: the tests that read every source enter them.
HIDDEN_WITH_CODE = (".github",)

#: Hidden folders that may hold Python files and are not sources of this
#: project, each with why. Nothing under them is read.
HIDDEN_NOT_OURS = {
    ".git": "git's own folder, or a worktree's: no source of the project",
    ".venv": "an environment made inside the tree, as the programs of the "
             "suite have: other projects' packages, under their licences",
}


def _is_hidden(name: str) -> bool:
    return name.startswith(".")


def python_files(root: Path = _ROOT, with_code=HIDDEN_WITH_CODE) -> list:
    """Every ``.py`` of the project under ``root``, sorted: all of them,
    except what is in a ``__pycache__`` or under a hidden folder that
    ``with_code`` does not name (by its path from ``root``)."""
    root = Path(root)
    out = []
    for folder, dirs, files in os.walk(root):
        here = Path(folder)
        rel = here.relative_to(root)
        dirs[:] = sorted(
            d for d in dirs if d != "__pycache__"
            and (not _is_hidden(d) or (rel / d).as_posix() in with_code))
        out.extend(here / f for f in files if f.endswith(".py"))
    return sorted(out)


def _holds_python(folder: Path) -> bool:
    for _, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        if any(f.endswith(".py") for f in files):
            return True
    return False


def undecided(root: Path = _ROOT, with_code=HIDDEN_WITH_CODE,
              not_ours=HIDDEN_NOT_OURS) -> list:
    """The hidden folders under ``root`` that hold a ``.py`` and are in
    neither list, as paths from ``root``."""
    root = Path(root)
    out = []
    for folder, dirs, _ in os.walk(root):
        here = Path(folder)
        rel = here.relative_to(root)
        enter = []
        for d in sorted(dirs):
            path = (rel / d).as_posix()
            if d == "__pycache__" or path in not_ours:
                continue
            if _is_hidden(d) and path not in with_code:
                if _holds_python(here / d):
                    out.append(path)
                continue
            enter.append(d)
        dirs[:] = enter
    return sorted(out)


_SCRIPT = _ROOT / ".github" / "scripts" / "program_suite.py"


class TestTheSourcesOfThisRepository:
    def test_the_script_of_the_ci_is_one_of_them(self):
        found = set(python_files())
        assert _SCRIPT.is_file()
        for path in (_SCRIPT, Path(__file__).resolve(),
                     _ROOT / "ogr_core" / "__init__.py",
                     _ROOT / "tests" / "_runner.py"):
            assert path in found, path

    def test_no_hidden_folder_with_code_is_undecided(self):
        left = undecided()
        assert left == [], (
            f"hidden folders with Python files that are neither read "
            f"(HIDDEN_WITH_CODE) nor excused (HIDDEN_NOT_OURS): {left}")

    def test_the_two_lists_do_not_overlap_and_every_excuse_says_why(self):
        assert not set(HIDDEN_WITH_CODE) & set(HIDDEN_NOT_OURS)
        for name, why in HIDDEN_NOT_OURS.items():
            assert why.strip(), name

    def test_the_three_tests_that_read_every_source_see_it(self):
        """The reason for this file: each of them, asked for its own list."""
        import test_license_v10
        import test_no_vendor_names_v10
        import test_python_floor_v10
        for module in (test_license_v10, test_python_floor_v10,
                       test_no_vendor_names_v10):
            seen = {Path(p).resolve() for p in module._sources()}
            assert _SCRIPT.resolve() in seen, module.__name__
            assert Path(module.__file__).resolve() in seen, module.__name__


# ----------------------------------------------------------------------
# In two halves: whole, the licence test would read this line as a header
# of this file with something after the identifier.
_HEADER = "# SPDX-License-" + "Identifier: AGPL-3.0-or-later\n"


def _tree(files: dict) -> Path:
    root = Path(tempfile.mkdtemp(prefix="ogr_test_sources_"))
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


_INVENTED = {
    "pkg/__init__.py": _HEADER,
    "pkg/deep/a.py": _HEADER,
    "pkg/__pycache__/a.cpython-311.py": "",
    "pkg/notes.txt": "",
    ".hidden_file.py": _HEADER,
    ".github/scripts/s.py": "print('no header')\n",
    ".github/workflows/w.yml": "",
    ".github/.cache/c.py": "",
    ".venv/lib/z.py": "",
    ".git/hooks/h.py": "",
    ".tools/t.py": "",
    ".editor/settings.json": "{}",
    "docs/.drafts/deep/d.py": "",
}


class TestWhatIsRead:
    def _names(self, root, **kwargs):
        return [p.relative_to(root).as_posix()
                for p in python_files(root, **kwargs)]

    def test_the_hidden_folders_with_code_and_nothing_else_hidden(self):
        root = _tree(_INVENTED)
        try:
            assert self._names(root) == [
                ".github/scripts/s.py", ".hidden_file.py",
                "pkg/__init__.py", "pkg/deep/a.py"]
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_with_no_hidden_folder_declared_it_is_the_old_blind_spot(self):
        """What the tests did before: the script is not there."""
        root = _tree(_INVENTED)
        try:
            assert ".github/scripts/s.py" not in self._names(
                root, with_code=())
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_a_hidden_folder_is_named_by_its_path(self):
        root = _tree(_INVENTED)
        try:
            names = self._names(root, with_code=(
                ".github", ".github/.cache", "docs/.drafts"))
            assert ".github/.cache/c.py" in names
            assert "docs/.drafts/deep/d.py" in names
            # the name alone, somewhere else, is not that folder
            assert self._names(root, with_code=(".cache", ".drafts")) == [
                ".hidden_file.py", "pkg/__init__.py", "pkg/deep/a.py"]
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestWhatIsLeftUndecided:
    def test_every_hidden_folder_with_python_in_neither_list(self):
        root = _tree(_INVENTED)
        try:
            # .editor has no Python; .git and .venv are excused; .github is
            # read, and the hidden folder inside it is one more to decide
            assert undecided(root) == [
                ".github/.cache", ".tools", "docs/.drafts"]
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_deciding_it_either_way_settles_it(self):
        root = _tree(_INVENTED)
        try:
            assert undecided(
                root, with_code=(".github", ".tools"),
                not_ours={**HIDDEN_NOT_OURS, ".github/.cache": "why",
                          "docs/.drafts": "why"}) == []
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_an_environment_nobody_excused_is_reported(self):
        root = _tree(_INVENTED)
        try:
            assert ".venv" in undecided(root, not_ours={})
            assert ".git" in undecided(root, not_ours={})
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestTheLicenceTestOnAHiddenFile:
    def test_a_file_with_no_header_in_a_hidden_folder_is_caught(self):
        """The case that started this: a script of the CI without its
        header. The licence test's own check, on an invented tree."""
        import test_license_v10 as licence
        root = _tree(_INVENTED)
        try:
            missing = licence._without_header(python_files(root), root)
            assert missing == [".github/scripts/s.py"], missing
        finally:
            shutil.rmtree(root, ignore_errors=True)
