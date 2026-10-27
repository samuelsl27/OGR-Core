# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.1.0 — the core imports no program and no layer above it, read from the
source.

Moved from OGR Slip2D's ``test_core_layering_v1340`` with the extraction
(spec 009). There the census found, in v0.1.340, twenty imports of the
engine in seven files of the core, all inside functions, which is why
nothing had failed at import time; by v0.1.346 the list was empty. Here it
guards the same boundary from the other side of a repository line: the
core now has programs above it that live elsewhere, and one of them, OGR
FEM2D, is called ``ogr_fem2d`` — the name the seepage package carried in
Slip2D until spec 009 moved it into ``ogr_core.fem``. It stays banned.

The invariants:

* **the census is exact.** Every import in ``ogr_core`` of a program
  (``ogr_slip2d``, ``ogr_fem2d``), of a layer above (``ogr_api``,
  ``ogr_gui``, ``ogr_cli``, ``ogr_mcp``), of Qt or of the MCP SDK, every
  ``importlib`` and every ``__import__`` call — inside functions, classes
  and ``TYPE_CHECKING`` blocks too — is an entry of :data:`ALLOWED`, as
  many times as it is written. A new one fails, and so does an entry that
  no longer matches anything;
* **the census sees what it must**: a module written here with one import
  of each kind is found whole, so an empty census means no import and not
  a blind scanner;
* **it looked at something**: the census reads at least the core's own
  ``__init__`` and the runner, so a moved or empty tree cannot pass it.
"""
from __future__ import annotations

import ast
import tempfile
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

#: The programs and layers above the core, and the two ways around an
#: import statement.
BANNED = frozenset({"ogr_slip2d", "ogr_fem2d", "ogr_api", "ogr_gui",
                    "ogr_cli", "ogr_mcp", "PySide6", "mcp", "importlib"})
DYNAMIC = "__import__"

#: ``(file, enclosing function, module)``: how many times it is written.
#: One entry, and it costs a reason: the suite's test runner loads test
#: files BY PATH (``importlib.util.spec_from_file_location``) and resolves
#: packages without importing them (``find_spec``), which is the whole of
#: its tree check. It is test tooling: no program imports it at run time,
#: and it imports nothing else of the core.
ALLOWED = Counter({("ogr_core/testing/runner.py", "<module>", "importlib"): 1})


def census_of(path: Path, root: Path) -> Counter:
    """The banned imports of one file, by enclosing function."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    rel = path.relative_to(root).as_posix()
    found: Counter = Counter()

    def visit(node, where):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                visit(child, where + [child.name])
                continue
            modules = []
            if isinstance(child, ast.Import):
                modules = [a.name.split(".")[0] for a in child.names]
            elif (isinstance(child, ast.ImportFrom) and child.level == 0
                  and child.module):
                modules = [child.module.split(".")[0]]
            elif (isinstance(child, ast.Call)
                  and isinstance(child.func, ast.Name)
                  and child.func.id == DYNAMIC):
                modules = [DYNAMIC]
            for module in modules:
                if module in BANNED or module == DYNAMIC:
                    found[(rel, ".".join(where) or "<module>", module)] += 1
            visit(child, where)

    visit(tree, [])
    return found


def _core_files() -> list:
    return sorted(p for p in (_ROOT / "ogr_core").rglob("*.py")
                  if "__pycache__" not in p.parts)


def core_census() -> Counter:
    found: Counter = Counter()
    for path in _core_files():
        found.update(census_of(path, _ROOT))
    return found


class TestTheCoreImportsNoLayerAbove:

    def test_the_census_is_the_allowed_list_exactly(self):
        found = core_census()
        new = found - ALLOWED
        gone = ALLOWED - found
        assert not new, ("imports of an upper layer not in the list", new)
        assert not gone, ("entries that match nothing any more: delete "
                          "them", gone)

    def test_the_census_looked_at_the_core(self):
        names = {p.relative_to(_ROOT).as_posix() for p in _core_files()}
        assert "ogr_core/__init__.py" in names, sorted(names)[:5]
        assert "ogr_core/testing/runner.py" in names, sorted(names)[:5]

    def test_the_census_sees_every_kind_of_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pkg = root / "ogr_core" / "x"
            pkg.mkdir(parents=True)
            (pkg / "m.py").write_text(
                "from __future__ import annotations\n"
                "from typing import TYPE_CHECKING\n"
                "import os\n"
                "from . import sibling\n"
                "if TYPE_CHECKING:\n"
                "    from ogr_slip2d.search import SearchResult\n"
                "class K:\n"
                "    def f(self):\n"
                "        import ogr_fem2d.solver as m\n"
                "        return __import__('ogr_api')\n"
                "def g():\n"
                "    import importlib\n"
                "    from PySide6.QtWidgets import QWidget\n",
                encoding="utf-8")
            found = census_of(pkg / "m.py", root)
        assert found == Counter({
            ("ogr_core/x/m.py", "<module>", "ogr_slip2d"): 1,
            ("ogr_core/x/m.py", "K.f", "ogr_fem2d"): 1,
            ("ogr_core/x/m.py", "K.f", DYNAMIC): 1,
            ("ogr_core/x/m.py", "g", "importlib"): 1,
            ("ogr_core/x/m.py", "g", "PySide6"): 1,
        }), found
