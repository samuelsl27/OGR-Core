# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
What the CI of OGR Core does with the programs that use it (v0.2.3).

    python .github/scripts/program_suite.py pins "OGR FEM2D=<dir>" "OGR Slip2D=<dir>"
    python .github/scripts/program_suite.py run "OGR FEM2D" <dir>

``<dir>`` is a checkout of the program (for ``pins``, its ``pyproject.toml``
is enough). The programs, the tag each one pins and the command of its whole
suite are read from ``docs/consumidores.md``: nothing of that is repeated in
the workflow.

``pins``: every program of the table pins, in its own ``pyproject.toml``,
the tag the table says. A program of the table that is not given is a
failure too: a list nobody reads is true on the day it is written.

``run``: the whole suite of one program, with the command of the table,
against the core of THIS tree, put ahead of the one the program installed
(``PYTHONPATH``). The program's runner refuses a core that is not its pin,
so what is asked of it depends on what this tree says it is
(:func:`mode`):

* a development version of a later release (``main`` and every PR between
  two tags): ``--dev-core``;
* the pinned release itself (the tagged commit, once the program pins it):
  nothing, it is the core the program asks for;
* a release the program does not pin yet (the commit that is about to be
  tagged, and the tag): the runner would refuse it with or without
  ``--dev-core``, so the suite runs against a COPY of ``ogr_core`` whose
  only difference is the version string, ``X.Y.Z.dev0``
  (:func:`as_development`). The code of the commit that gets the tag is
  measured by the programs; the log says it was measured that way.

Anything else (a core older than the pin) stops the job: there is nothing
to learn from a program run against a core behind the one it supports.

Author: Samuel Sáez López (UPCT)
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# The core and the reader of the table are the ones of THIS tree, whatever
# is installed in the interpreter that runs the script.
for _path in (ROOT / "tests", ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from ogr_core.testing import runner as _R  # noqa: E402
from test_consumers_v022 import consumers, filters  # noqa: E402

if ROOT not in Path(_R.__file__).resolve().parents:
    raise SystemExit(f"ogr_core comes from {_R.__file__}, not from {ROOT}: "
                     f"this script reads the core of its own tree")

TABLE = ROOT / "docs" / "consumidores.md"
DIST = "ogr-core"
PACKAGE = "ogr_core"


def the_row(name: str, table: str) -> dict:
    """The row of ``name`` in the table; ``ValueError`` if it has none."""
    rows = {c["name"]: c for c in consumers(table)}
    if name not in rows:
        raise ValueError(f"{name!r} is not a program of docs/consumidores.md "
                         f"(it has {sorted(rows)})")
    return rows[name]


def pin_problems(table: str, pyprojects: dict) -> list:
    """Why the table and the programs do not say the same, as sentences;
    empty when they do. ``pyprojects`` is ``{program: path of its
    pyproject.toml}``; every program of the table has to be in it, and
    nothing that is not in the table."""
    rows = consumers(table)
    problems = []
    for row in rows:
        name, said = row["name"], row["pin"]
        path = pyprojects.get(name)
        if path is None:
            problems.append(f"{name}: in the table, and no pyproject.toml "
                            f"was given to compare it with")
            continue
        if not Path(path).is_file():
            problems.append(f"{name}: {path} is not there")
            continue
        pinned = _R.pinned_from_pyproject(Path(path), DIST)
        if pinned is None:
            problems.append(f"{name}: its pyproject.toml does not pin "
                            f"{DIST} to a version")
        elif f"v{pinned}" != said:
            problems.append(
                f"{name}: the table says {said} and its pyproject.toml pins "
                f"v{pinned} — correct the row of docs/consumidores.md")
    for name in sorted(set(pyprojects) - {r["name"] for r in rows}):
        problems.append(f"{name}: given, and not a program of the table")
    return problems


def _numbers(version: str):
    if not re.fullmatch(r"\d+(?:\.\d+)*", version or ""):
        return None
    return tuple(int(x) for x in version.split("."))


def _padded(a: tuple, b: tuple) -> tuple:
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)), b + (0,) * (n - len(b))


def mode(core: str, pin: str) -> str:
    """What to ask of a program that pins ``pin`` (``vX.Y.Z``) when this
    tree says ``core``: ``"dev"``, ``"pinned"`` or ``"release"`` (see the
    module). ``ValueError`` for a core the program cannot be run against."""
    pinned = _numbers(pin[1:] if pin.startswith("v") else pin)
    if pinned is None:
        raise ValueError(f"{pin!r} is not a pinned release")
    base, release = _R.dev_base(core), _numbers(core)
    if base is not None:
        base, pinned = _padded(base, pinned)
        if base > pinned:
            return "dev"
        raise ValueError(
            f"this core is {core}, on its way to a release the program "
            f"already pins or has left behind ({pin}): an older core")
    if release is None:
        raise ValueError(f"{core!r} is neither X.Y.Z nor X.Y.Z.devN")
    release, pinned = _padded(release, pinned)
    if release == pinned:
        return "pinned"
    if release > pinned:
        return "release"
    raise ValueError(f"this core is {core}, older than the {pin} the "
                     f"program pins")


def as_development(package: Path, into: Path) -> Path:
    """A copy of the package ``package`` under ``into`` that says
    ``X.Y.Z.dev0`` where the original says ``X.Y.Z``, and is otherwise the
    same, file by file. Returns the directory to put on ``PYTHONPATH``."""
    version = _R.declared_version(package)
    if _numbers(version) is None:
        raise ValueError(f"{package} says {version!r}: not a release "
                         f"to be run as its development version")
    target = Path(into) / package.name
    shutil.copytree(package, target,
                    ignore=shutil.ignore_patterns("__pycache__"))
    init = target / "__init__.py"
    source = init.read_bytes()
    old = f'__version__ = "{version}"'.encode("utf-8")
    if source.count(old) != 1:
        raise ValueError(f"{init}: expected one line {old.decode()!r}")
    init.write_bytes(source.replace(
        old, f'__version__ = "{version}.dev0"'.encode("utf-8")))
    if _R.declared_version(target) != f"{version}.dev0":
        raise ValueError(f"{init}: the copy does not say {version}.dev0")
    return Path(into)


def invocation(suite: str, dev: bool, python: str = sys.executable):
    """``(environment, argv)`` for the command of a whole suite as the
    table writes it (``NAME=value … python tests/_runner.py …``): the
    variables it sets, and the words to run, with this interpreter for
    ``python`` and ``--dev-core`` at the end when ``dev``."""
    found = filters(suite)
    if found:
        raise ValueError(f"{suite!r} is not a whole suite: {found}")
    words = shlex.split(suite)
    env = {}
    while words and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[0]):
        key, _, value = words.pop(0).partition("=")
        env[key] = value
    if not words or words[0] != "python":
        raise ValueError(f"{suite!r}: expected `python tests/_runner.py …` "
                         f"after the variables")
    argv = [python] + words[1:]
    if dev:
        if "--dev-core" in argv:
            raise ValueError(f"{suite!r} already says --dev-core")
        argv.append("--dev-core")
    return env, argv


def _resolved_core(python: str, cwd: Path, env: dict):
    """Where ``ogr_core`` comes from for ``python`` started in ``cwd``."""
    out = subprocess.run(
        [python, "-c",
         f"import {PACKAGE}, pathlib; "
         f"print(pathlib.Path({PACKAGE}.__file__).resolve().parent)"],
        cwd=cwd, env=env, capture_output=True, text=True)
    return Path(out.stdout.strip()) if out.returncode == 0 else None


def run(name: str, program: Path, core_root: Path = ROOT,
        table: str | None = None, python: str = sys.executable) -> int:
    """The whole suite of ``name``, checked out in ``program``, against the
    core of ``core_root``. Returns the exit code for the job."""
    program = Path(program).resolve()
    if table is None:
        table = TABLE.read_text(encoding="utf-8")
    row = the_row(name, table)
    problems = [p for p in pin_problems(
        table, {name: program / "pyproject.toml"}) if p.startswith(name + ":")]
    if problems:
        for problem in problems:
            print(f"::error::{problem}")
        return 1

    package = Path(core_root) / PACKAGE
    version = _R.declared_version(package)
    how = mode(version or "", row["pin"])
    scratch = None
    try:
        if how == "release":
            scratch = tempfile.mkdtemp(prefix="ogr_core_as_dev_")
            ahead = as_development(package, Path(scratch))
            print(f"::notice::{name} pins {row['pin']} and this core says "
                  f"{version}: its runner refuses a release that is not its "
                  f"pin, so the suite runs against a copy of {PACKAGE} that "
                  f"differs in the version string only ({version}.dev0).")
        else:
            ahead = Path(core_root)
        extra, argv = invocation(row["suite"], dev=how != "pinned",
                                 python=python)
        env = dict(os.environ)
        env.update(extra)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(ahead)] + [p for p in env.get("PYTHONPATH", "").split(
                os.pathsep) if p])

        got = _resolved_core(python, program, env)
        want = (ahead / PACKAGE).resolve()
        if got != want:
            print(f"::error::{name}: {PACKAGE} resolves to {got}, not to "
                  f"the core of this run ({want})")
            return 1

        print(f"program: {name} ({row['repository']}), pins {row['pin']}")
        print(f"core:    {version} from {package} -> mode {how}")
        shown = [f"{k}={v}" for k, v in extra.items()] + ["python"] + argv[1:]
        print(f"command: {' '.join(shown)}", flush=True)
        return subprocess.run(argv, cwd=program, env=env).returncode
    finally:
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) >= 2 and args[0] == "pins":
        given = {}
        for item in args[1:]:
            name, sep, where = item.partition("=")
            if not sep or not name or not where:
                print(f"expected NAME=DIR, got {item!r}")
                return 2
            given[name] = Path(where) / "pyproject.toml"
        problems = pin_problems(TABLE.read_text(encoding="utf-8"), given)
        for problem in problems:
            print(f"::error::{problem}")
        if not problems:
            for row in consumers(TABLE.read_text(encoding="utf-8")):
                print(f"{row['name']}: pins {row['pin']}, as the table says")
        return 1 if problems else 0
    if len(args) == 3 and args[0] == "run":
        try:
            return run(args[1], Path(args[2]))
        except ValueError as exc:
            print(f"::error::{exc}")
            return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
