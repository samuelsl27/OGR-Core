# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.2 — ``docs/consumidores.md`` says which programs use this core and
which version each one pins, in a table that can be read by a program.

What was found. The suite's registry of programs (``suite.toml``, in the
suite's own repository) was written when OGR FEM2D pinned ``v0.1.0`` and
OGR Slip2D carried its own copy of the core; two days after both had moved
it still said so, and nothing failed. A list kept by hand, with nothing
reading it, is true on the day it is written. So the list of this
repository is a table with a fixed shape, and what can be checked of it
here is checked here.

Invariants protected:

1. **The table is there and names the programs of the suite**, each with
   its repository, the tag it pins and the command of its whole suite.
2. **A pinned version is a release this core has made**: it has its
   changelog, and it is not later than what this tree says it is (for a
   development version, earlier than the release it leads to). A typing
   slip in the tag, or a pin to a version that does not exist yet, fails
   here.
3. **The command of a whole suite filters nothing** (rule 8): it runs
   ``tests/_runner.py`` with no ``--fast``, no ``-k`` and no pattern.
   ``--jobs`` is not a filter.
4. **The reader refuses a table it cannot read**, rather than returning
   fewer programs: no table, a missing column, a row with the wrong number
   of cells, a pin that is not a tag, a repository that is not
   ``owner/name``, the same program twice.

Not checked here, because it lives in another repository: that the pin of
the table IS the one in the program's ``pyproject.toml``. That is for the
CI job that runs each program's suite, which imports :func:`consumers`
from this file.
"""
from __future__ import annotations

import re
import shlex
from pathlib import Path

from ogr_core.testing import runner as _R

_ROOT = Path(__file__).resolve().parent.parent
_DOC = _ROOT / "docs" / "consumidores.md"

#: The header of the table, cell by cell: the shape the reader holds to.
HEADER = ("Programa", "Repositorio", "Núcleo que fija", "Desde",
          "Suite entera")


def _cells(line: str) -> list:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _plain(cell: str) -> str:
    """A cell without the backticks of its code span."""
    return cell.strip().strip("`").strip()


def consumers(text: str) -> list:
    """The programs of the table headed by :data:`HEADER`, as dicts with
    ``name``, ``repository`` (``owner/name``), ``pin`` (``vX.Y.Z``),
    ``since`` and ``suite``. Raises ``ValueError`` on a table it cannot
    read: fewer programs returned would look like fewer programs."""
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines)
              if line.lstrip().startswith("|") and tuple(_cells(line)) == HEADER]
    if len(starts) != 1:
        raise ValueError(f"expected one table headed {HEADER}, "
                         f"found {len(starts)}")
    rows = []
    for line in lines[starts[0] + 2:]:
        if not line.lstrip().startswith("|"):
            break
        rows.append(_cells(line))
    if not rows:
        raise ValueError("the table has no rows")
    out = []
    for row in rows:
        if len(row) != len(HEADER):
            raise ValueError(f"a row with {len(row)} cells: {row}")
        name, repo, pin, since, suite = (
            row[0], _plain(row[1]), _plain(row[2]), row[3], _plain(row[4]))
        if not name:
            raise ValueError(f"a row with no program: {row}")
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
            raise ValueError(f"{name}: {repo!r} is not owner/name")
        if not re.fullmatch(r"v\d+\.\d+\.\d+", pin):
            raise ValueError(f"{name}: {pin!r} is not a tag vX.Y.Z")
        if not suite:
            raise ValueError(f"{name}: no command for its whole suite")
        out.append({"name": name, "repository": repo, "pin": pin,
                    "since": since, "suite": suite})
    names = [c["name"] for c in out]
    if len(set(names)) != len(names):
        raise ValueError(f"a program twice: {names}")
    return out


def filters(command: str) -> list:
    """What makes ``command`` a filtered run of ``tests/_runner.py``: the
    options and the patterns that select part of the suite."""
    words = shlex.split(command)
    at = [i for i, w in enumerate(words) if w.endswith("tests/_runner.py")]
    if not at:
        return ["(it does not run tests/_runner.py)"]
    found, rest = [], words[at[0] + 1:]
    takes_value = {"--jobs", "-j"}
    i = 0
    while i < len(rest):
        word = rest[i]
        if word in takes_value:
            i += 2
            continue
        if word.startswith("--jobs=") or re.fullmatch(r"-j\d+", word):
            i += 1
            continue
        # --fast, -k and its value, --list, a pattern: all of them select
        found.append(word)
        i += 1
    return found


def _tree_version() -> tuple:
    import ogr_core
    version = ogr_core.__version__
    return _R.dev_base(version) or tuple(int(x) for x in version.split("."))


def _is_dev() -> bool:
    import ogr_core
    return _R.dev_base(ogr_core.__version__) is not None


_ROW = "| {} | `{}` | `{}` | su v1 | `{}` |"
_GOOD = "\n".join([
    "texto", "",
    "| " + " | ".join(HEADER) + " |", "|---|---|---|---|---|",
    _ROW.format("A", "o/a", "v0.2.0", "python tests/_runner.py"),
    _ROW.format("B", "o/b", "v0.2.1", "X=1 python tests/_runner.py --jobs 4"),
    "", "más texto", "",
    "| Otra | tabla |", "|---|---|", "| x | y |"])


class TestTheTableOfThisRepository:
    def test_it_names_the_programs_of_the_suite(self):
        found = {c["name"]: c for c in consumers(
            _DOC.read_text(encoding="utf-8"))}
        assert set(found) == {"OGR Slip2D", "OGR FEM2D"}, sorted(found)
        assert found["OGR Slip2D"]["repository"] == "samuelsl27/OGR-Slip2D"
        assert found["OGR FEM2D"]["repository"] == "samuelsl27/OGR-FEM2D"

    def test_every_pin_is_a_release_this_core_has_made(self):
        tree, dev = _tree_version(), _is_dev()
        for c in consumers(_DOC.read_text(encoding="utf-8")):
            log = (_ROOT / "docs" / "changelog"
                   / f"CHANGELOG_{c['pin']}.md")
            assert log.exists(), f"{c['name']} pins {c['pin']}: no changelog"
            pin = tuple(int(x) for x in c["pin"][1:].split("."))
            # a development version leads to a release nobody can pin yet
            assert (pin < tree) if dev else (pin <= tree), (c, tree, dev)

    def test_no_whole_suite_is_filtered(self):
        for c in consumers(_DOC.read_text(encoding="utf-8")):
            assert filters(c["suite"]) == [], (c["name"], c["suite"])


class TestTheReader:
    def test_it_reads_a_table_among_other_text_and_other_tables(self):
        found = consumers(_GOOD)
        assert [c["name"] for c in found] == ["A", "B"]
        assert found[1] == {
            "name": "B", "repository": "o/b", "pin": "v0.2.1",
            "since": "su v1", "suite": "X=1 python tests/_runner.py --jobs 4"}

    def _refused(self, text: str, why: str) -> None:
        try:
            consumers(text)
        except ValueError as exc:
            assert why in str(exc), (why, str(exc))
        else:
            raise AssertionError(f"read without complaint: {why}")

    def test_it_refuses_a_text_with_no_table(self):
        self._refused("nada\n| Otra | tabla |\n|---|---|\n| x | y |\n",
                      "found 0")

    def test_and_two_of_them(self):
        self._refused(_GOOD + "\n\n" + _GOOD, "found 2")

    def test_and_a_table_with_no_rows(self):
        self._refused("| " + " | ".join(HEADER) + " |\n|---|---|---|---|---|\n",
                      "no rows")

    def test_and_a_row_with_a_cell_missing(self):
        self._refused(_GOOD.replace(" | su v1 | `python", " | `python"),
                      "4 cells")

    def test_and_a_pin_that_is_not_a_tag(self):
        for bad in ("0.2.0", "v0.2", "main", "v0.2.0.dev0", ""):
            self._refused(_GOOD.replace("`v0.2.0`", f"`{bad}`"),
                          "is not a tag")

    def test_and_a_repository_that_is_not_owner_and_name(self):
        for bad in ("a", "https://github.com/o/a", ""):
            self._refused(_GOOD.replace("`o/a`", f"`{bad}`"),
                          "is not owner/name")

    def test_and_a_row_with_no_command(self):
        self._refused(_GOOD.replace("`python tests/_runner.py`", "``"),
                      "no command")

    def test_and_the_same_program_twice(self):
        self._refused(_GOOD.replace("| B |", "| A |"), "twice")


class TestWhatAFilterIs:
    def test_the_whole_suite(self):
        for command in ("python tests/_runner.py",
                        ".venv/Scripts/python tests/_runner.py",
                        "QT_QPA_PLATFORM=offscreen python tests/_runner.py "
                        "--jobs 4",
                        "python tests/_runner.py -j 4",
                        "python tests/_runner.py --jobs=4",
                        "python tests/_runner.py -j4"):
            assert filters(command) == [], command

    def test_what_selects_part_of_it(self):
        assert filters("python tests/_runner.py --fast --jobs 4") == ["--fast"]
        assert filters("python tests/_runner.py -k erfc") == ["-k", "erfc"]
        assert filters("python tests/_runner.py geometry") == ["geometry"]
        assert filters("python tests/_runner.py --jobs 4 seepage") == [
            "seepage"]
        assert filters("python tests/_runner.py --list") == ["--list"]

    def test_a_command_that_runs_something_else(self):
        assert filters("python -m pytest") != []
        assert filters("") != []
