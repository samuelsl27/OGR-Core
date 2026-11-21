# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.3 — the CI of this repository runs the suite of each program that uses
the core, against the core of the commit, and compares what each program
pins with what ``docs/consumidores.md`` says.

What was found. Rule 8 (a change here is tested in the programs too) was
kept by hand: before v0.2.2 was tagged, somebody had to remember to run two
suites in two other folders, with the right command and the right
environment. And the table of who pins what was checked for its shape only
(``test_consumers_v022``): OGR FEM2D moved to ``v0.2.2`` and the table went
on saying ``v0.2.0`` with every test green, because the truth is in another
repository. Both are now a job of the CI, written in
``.github/scripts/program_suite.py``; this file is what holds that script
and the workflow to what they are for.

Invariants protected:

1. **Every program of the table has its job, or a stated reason not to have
   it yet** (:data:`NOT_YET`), and a reason does not outlive its cause: a
   program with a job cannot keep one. A third program added to the table
   fails here until the CI runs it.
2. **The job takes the command from the table**: it calls the script with
   the program's name, and does not run ``tests/_runner.py`` nor say
   ``--dev-core`` itself. A copy of the command in the workflow would be a
   second list.
3. **The comparison of pins covers every program**, the ones of
   :data:`NOT_YET` included: reading a ``pyproject.toml`` does not depend on
   the program's suite being green anywhere.
4. **What is asked of the program's runner is what that runner accepts**
   (:func:`program_suite.mode`): ``--dev-core`` for a development version of
   a later release, nothing for the pinned release, and for a release the
   program does not pin yet -- which the runner refuses either way -- a copy
   that differs in the version string only. Checked against
   ``runner.shared_problems`` itself, on invented cores, so the two cannot
   drift apart.
5. **That copy changes the version string and nothing else**, file by file.
6. **A run does what it says**: the command of the table, with its
   variables, this core ahead of the installed one, the exit code of the
   suite; and a program whose pin is not the table's does not run at all.

Teeth: every check of the workflow is a function of an invented text, fed
here with the workflows that must fail.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from ogr_core.testing import runner as _R
from test_consumers_v022 import HEADER, consumers

_ROOT = Path(__file__).resolve().parent.parent
_WORKFLOW = _ROOT / ".github" / "workflows" / "tests.yml"
_TABLE = _ROOT / "docs" / "consumidores.md"
_SCRIPT = _ROOT / ".github" / "scripts" / "program_suite.py"

#: Programs of the table whose suite the CI does not run yet, and why. An
#: entry leaves when its cause does; with a job in the workflow it fails.
#: Empty since v0.2.4. OGR Slip2D was here through v0.2.3, for five tests
#: parked in its own CI (a job that is red for a known reason teaches
#: everybody to ignore it); its v0.1.476 left its suite green on Linux, and
#: it has its job.
NOT_YET = {}


def _script():
    spec = importlib.util.spec_from_file_location("program_suite", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


S = _script()


def jobs(text: str) -> dict:
    """``{job: its text}`` of a workflow, without the comment lines: a
    comment that names a program or an option is not the job doing it."""
    lines = text.splitlines()
    if "jobs:" not in lines:
        raise ValueError("no `jobs:` in the workflow")
    out, name = {}, None
    for line in lines[lines.index("jobs:") + 1:]:
        if line.strip().startswith("#"):
            continue
        m = re.fullmatch(r"  ([A-Za-z_][\w-]*):\s*", line)
        if m:
            name = m.group(1)
            out[name] = []
        elif name is not None:
            out[name].append(line)
    return {k: "\n".join(v) for k, v in out.items()}


def workflow_problems(rows: list, text: str, not_yet: dict) -> list:
    """Why the workflow ``text`` does not do, for the programs ``rows`` of
    the table, what this file says it does; empty when it does."""
    found = jobs(text)
    problems = []
    names = {r["name"] for r in rows}
    for name in sorted(set(not_yet) - names):
        problems.append(f"{name}: excused, and not a program of the table")
    for name, why in sorted(not_yet.items()):
        if not str(why).strip():
            problems.append(f"{name}: excused with no reason")

    pins = [j for j in found.values() if "program_suite.py pins" in j]
    if len(pins) != 1:
        problems.append(f"expected one job comparing the pins, "
                        f"found {len(pins)}")
    for row in rows:
        name, repo = row["name"], row["repository"]
        for job in pins:
            if (f"repository: {repo}\n" not in job + "\n"
                    or f'"{name}=' not in job):
                problems.append(f"{name}: the job of the pins does not "
                                f"compare it")
        mine = {k: j for k, j in found.items()
                if f'program_suite.py run "{name}"' in j}
        if name in not_yet:
            if mine:
                problems.append(f"{name}: has a job ({sorted(mine)}) and is "
                                f"still excused")
            continue
        if len(mine) != 1:
            problems.append(f"{name}: expected one job running its suite, "
                            f"found {len(mine)}")
            continue
        (job,) = mine.values()
        if f"repository: {repo}\n" not in job + "\n":
            problems.append(f"{name}: its job does not check out {repo}")
        if "_runner.py" in job or "--dev-core" in job:
            problems.append(f"{name}: its job runs the suite itself instead "
                            f"of asking the table")
    return problems


def _rows(*programs) -> list:
    return [{"name": n, "repository": r, "pin": "v0.2.2", "since": "",
             "suite": "python tests/_runner.py"} for n, r in programs]


_A, _B = ("A", "o/a"), ("B", "o/b")
_GOOD = """\
name: tests
jobs:
  test:
    steps:
      - run: python tests/_runner.py
  pins:
    steps:
      - uses: actions/checkout@v7
        with:
          repository: o/a
      - uses: actions/checkout@v7
        with:
          repository: o/b
      - run: python core/.github/scripts/program_suite.py pins "A=a" "B=b"
  # B runs with --dev-core through the script: python tests/_runner.py
  a:
    steps:
      - uses: actions/checkout@v7
        with:
          repository: o/a
      - run: python core/.github/scripts/program_suite.py run "A" program
"""


class TestTheWorkflowOfThisRepository:
    def test_the_scan_sees_the_jobs(self):
        """A scan that finds nothing would pass everything below."""
        found = jobs(_WORKFLOW.read_text(encoding="utf-8"))
        assert {"test", "licence", "pins", "fem2d", "slip2d"} <= set(found), \
            sorted(found)
        assert all(found.values()), sorted(found)

    def test_every_program_has_its_job_or_a_reason(self):
        rows = consumers(_TABLE.read_text(encoding="utf-8"))
        problems = workflow_problems(
            rows, _WORKFLOW.read_text(encoding="utf-8"), NOT_YET)
        assert problems == [], problems

    def test_the_script_is_the_one_the_jobs_call(self):
        text = _WORKFLOW.read_text(encoding="utf-8")
        assert _SCRIPT.is_file()
        assert "core/.github/scripts/program_suite.py" in text
        assert "path: core" in text


class TestWhatAWorkflowMustDo:
    def test_the_good_one(self):
        assert workflow_problems(_rows(_A, _B), _GOOD, {"B": "why"}) == []

    def _one(self, rows, text, not_yet, why):
        problems = workflow_problems(rows, text, not_yet)
        assert len(problems) == 1 and why in problems[0], (why, problems)

    def test_a_program_with_no_job_and_no_reason(self):
        self._one(_rows(_A, _B), _GOOD, {}, "B: expected one job running")

    def test_a_third_program_in_the_table(self):
        problems = workflow_problems(
            _rows(_A, _B, ("C", "o/c")), _GOOD, {"B": "why"})
        assert problems == [
            "C: the job of the pins does not compare it",
            "C: expected one job running its suite, found 0"], problems

    def test_a_reason_that_outlived_its_cause(self):
        self._one(_rows(_A, _B), _GOOD, {"A": "why", "B": "why"},
                  "A: has a job")

    def test_a_reason_for_a_program_that_is_not_there(self):
        self._one(_rows(_A, _B), _GOOD, {"B": "why", "Z": "why"},
                  "Z: excused, and not a program")

    def test_an_empty_reason(self):
        self._one(_rows(_A, _B), _GOOD, {"B": " "}, "B: excused with no")

    def test_a_job_that_runs_the_suite_itself(self):
        for extra in ("      - run: python tests/_runner.py --dev-core\n",
                      "      - run: echo --dev-core\n"):
            self._one(_rows(_A, _B), _GOOD + extra, {"B": "why"},
                      "A: its job runs the suite itself")

    def test_a_job_that_checks_out_another_repository(self):
        text = _GOOD.replace(
            '          repository: o/a\n      - run: python core/.github/'
            'scripts/program_suite.py run',
            '          repository: o/b\n      - run: python core/.github/'
            'scripts/program_suite.py run')
        assert text != _GOOD
        self._one(_rows(_A, _B), text, {"B": "why"},
                  "A: its job does not check out o/a")

    def test_the_pins_that_leave_a_program_out(self):
        self._one(_rows(_A, _B), _GOOD.replace(' "B=b"', ""), {"B": "why"},
                  "B: the job of the pins does not compare it")
        text = _GOOD.replace("          repository: o/b\n", "")
        self._one(_rows(_A, _B), text, {"B": "why"},
                  "B: the job of the pins does not compare it")

    def test_no_job_of_the_pins(self):
        text = _GOOD.replace("program_suite.py pins", "program_suite.py")
        problems = workflow_problems(_rows(_A, _B), text, {"B": "why"})
        assert problems == ["expected one job comparing the pins, found 0"]

    def test_a_comment_is_not_a_job(self):
        """The comment of ``_GOOD`` names the runner and the option, and a
        job only named in a comment does not count."""
        text = _GOOD.replace("  a:\n", "  # a:\n").replace(
            '      - run: python core/.github/scripts/program_suite.py run',
            '      # - run: python core/.github/scripts/program_suite.py run')
        self._one(_rows(_A, _B), text, {"B": "why"},
                  "A: expected one job running")


# ----------------------------------------------------------------------
@contextlib.contextmanager
def _folder():
    path = Path(tempfile.mkdtemp(prefix="ogr_test_ci_programs_"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _package(root: Path, version: str) -> Path:
    """An invented ``ogr_core`` under ``root`` that says ``version``."""
    package = root / "ogr_core"
    (package / "fem").mkdir(parents=True)
    (package / "__init__.py").write_text(
        f'"""An invented core."""\n__version__ = "{version}"\n'
        f'__author__ = "nobody"\n', encoding="utf-8")
    (package / "fem" / "__init__.py").write_bytes(b"X = 1\r\n")
    (package / "data.bin").write_bytes(bytes(range(256)))
    return package


def _accepted(version: str, pin: str, dev_core: bool) -> bool:
    """Whether the runner of a program that pins ``pin`` takes a core that
    says ``version``: the runner's own answer."""
    with _folder() as root:
        package = _package(root, version)
        return _R.shared_problems({"ogr_core": package},
                                  {"ogr_core": pin}, dev_core=dev_core) == []


class TestWhatIsAskedOfTheProgram:
    def test_the_three_modes(self):
        assert S.mode("0.2.3.dev0", "v0.2.2") == "dev"
        assert S.mode("0.3.0.dev4", "v0.2.2") == "dev"
        assert S.mode("0.2.2", "v0.2.2") == "pinned"
        assert S.mode("0.2.3", "v0.2.2") == "release"
        assert S.mode("0.3.0", "v0.2.9") == "release"

    def test_an_older_core_or_an_unreadable_one_stops_the_job(self):
        for core in ("0.2.2.dev0", "0.2.1.dev3", "0.2.1", "0.1.0",
                     "0.2.3rc1", "0.2.3.dev0+local", "0.2.3.dev", "", "main"):
            try:
                S.mode(core, "v0.2.2")
            except ValueError:
                continue
            raise AssertionError(f"{core!r} was given a mode")

    def test_and_a_pin_that_is_not_a_release(self):
        for pin in ("main", "v0.2.2.dev0", ""):
            try:
                S.mode("0.2.3.dev0", pin)
            except ValueError:
                continue
            raise AssertionError(f"{pin!r} was taken as a pin")

    def test_each_mode_is_what_the_runner_accepts(self):
        """The reason for each mode, asked of ``shared_problems``."""
        # dev: only with --dev-core
        assert not _accepted("0.2.3.dev0", "0.2.2", dev_core=False)
        assert _accepted("0.2.3.dev0", "0.2.2", dev_core=True)
        # pinned: as it is
        assert _accepted("0.2.2", "0.2.2", dev_core=False)
        # release: refused either way, and taken as its development version
        assert not _accepted("0.2.3", "0.2.2", dev_core=False)
        assert not _accepted("0.2.3", "0.2.2", dev_core=True)
        assert _accepted("0.2.3.dev0", "0.2.2", dev_core=True)
        # what `mode` refuses, the runner refuses with the option too
        for core in ("0.2.2.dev0", "0.2.1", "0.2.3rc1"):
            assert not _accepted(core, "0.2.2", dev_core=True), core


class TestAReleaseRunsAsItsDevelopmentVersion:
    def test_the_copy_differs_in_the_version_string_only(self):
        with _folder() as root:
            original = _package(root / "tree", "0.2.3")
            (original / "__pycache__").mkdir()
            (original / "__pycache__" / "x.pyc").write_bytes(b"x")
            before = {p.relative_to(original): p.read_bytes()
                      for p in original.rglob("*") if p.is_file()}
            ahead = S.as_development(original, root / "copy")
            copy = ahead / "ogr_core"
            assert _R.declared_version(copy) == "0.2.3.dev0"
            assert _R.declared_version(original) == "0.2.3"
            after = {p.relative_to(copy): p.read_bytes()
                     for p in copy.rglob("*") if p.is_file()}
            before.pop(Path("__pycache__") / "x.pyc")
            assert set(after) == set(before)
            init = Path("__init__.py")
            for name in before:
                if name != init:
                    assert after[name] == before[name], name
            assert after[init] == before[init].replace(
                b'"0.2.3"', b'"0.2.3.dev0"')
            assert after[init] != before[init]
            # the original is as it was
            assert {p.relative_to(original): p.read_bytes()
                    for p in original.rglob("*") if p.is_file()
                    and "__pycache__" not in p.parts} == before

    def test_it_refuses_what_is_not_a_release(self):
        for version in ("0.2.3.dev0", "0.2.3rc1"):
            with _folder() as root:
                package = _package(root / "tree", version)
                try:
                    S.as_development(package, root / "copy")
                except ValueError:
                    continue
                raise AssertionError(f"{version} was copied")

    def test_and_a_version_it_cannot_change_in_one_place(self):
        with _folder() as root:
            package = _package(root / "tree", "0.2.3")
            init = package / "__init__.py"
            init.write_text(init.read_text(encoding="utf-8")
                            + '# __version__ = "0.2.3"\n', encoding="utf-8")
            try:
                S.as_development(package, root / "copy")
            except ValueError as exc:
                assert "expected one line" in str(exc)
            else:
                raise AssertionError("copied with the version twice")


# ----------------------------------------------------------------------
_PY = "PY"


class TestTheCommandOfTheTable:
    def test_a_plain_one(self):
        assert S.invocation("python tests/_runner.py", True, _PY) == (
            {}, [_PY, "tests/_runner.py", "--dev-core"])
        assert S.invocation("python tests/_runner.py", False, _PY) == (
            {}, [_PY, "tests/_runner.py"])

    def test_one_with_variables_and_jobs(self):
        suite = "QT_QPA_PLATFORM=offscreen A=b=c python tests/_runner.py --jobs 4"
        assert S.invocation(suite, True, _PY) == (
            {"QT_QPA_PLATFORM": "offscreen", "A": "b=c"},
            [_PY, "tests/_runner.py", "--jobs", "4", "--dev-core"])

    def test_every_command_of_the_table_can_be_run(self):
        for row in consumers(_TABLE.read_text(encoding="utf-8")):
            env, argv = S.invocation(row["suite"], True, _PY)
            assert argv[:2] == [_PY, "tests/_runner.py"], row
            assert argv[-1] == "--dev-core"

    def test_what_it_refuses(self):
        for suite in ("python tests/_runner.py --fast",
                      "python tests/_runner.py geometry",
                      ".venv/Scripts/python tests/_runner.py",
                      "X=1 bash run.sh tests/_runner.py",
                      ""):
            try:
                S.invocation(suite, True, _PY)
            except ValueError:
                continue
            raise AssertionError(f"{suite!r} was turned into a command")


# ----------------------------------------------------------------------
def _table(*rows) -> str:
    lines = ["| " + " | ".join(HEADER) + " |", "|---|---|---|---|---|"]
    for name, pin, suite in rows:
        lines.append(f"| {name} | `o/{name.lower()}` | `{pin}` | su v1 "
                     f"| `{suite}` |")
    return "\n".join(lines) + "\n"


def _pyproject(folder: Path, requirement: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "pyproject.toml"
    path.write_text('[project]\nname = "p"\nversion = "1"\n'
                    f'dependencies = ["numpy", "{requirement}"]\n',
                    encoding="utf-8")
    return path


_TAG = "ogr-core @ git+https://github.com/samuelsl27/OGR-Core@v{}"
_TWO = _table(("A", "v0.2.2", "python tests/_runner.py"),
              ("B", "v0.2.1", "python tests/_runner.py"))


class TestThePinsOfTheTable:
    def test_a_table_that_says_what_the_programs_pin(self):
        with _folder() as root:
            given = {"A": _pyproject(root / "a", _TAG.format("0.2.2")),
                     "B": _pyproject(root / "b", "ogr-core==0.2.1")}
            assert S.pin_problems(_TWO, given) == []

    def _one(self, given, why):
        problems = S.pin_problems(_TWO, given)
        assert len(problems) == 1 and why in problems[0], (why, problems)

    def test_a_program_that_moved_its_pin(self):
        with _folder() as root:
            self._one({"A": _pyproject(root / "a", _TAG.format("0.2.2")),
                       "B": _pyproject(root / "b", _TAG.format("0.2.2"))},
                      "B: the table says v0.2.1 and its pyproject.toml pins "
                      "v0.2.2")

    def test_a_program_that_pins_nothing(self):
        with _folder() as root:
            self._one({"A": _pyproject(root / "a", "ogr-core>=0.2"),
                       "B": _pyproject(root / "b", _TAG.format("0.2.1"))},
                      "A: its pyproject.toml does not pin")

    def test_a_program_of_the_table_nobody_gave(self):
        with _folder() as root:
            self._one({"A": _pyproject(root / "a", _TAG.format("0.2.2"))},
                      "B: in the table, and no pyproject.toml")

    def test_a_pyproject_that_is_not_there(self):
        with _folder() as root:
            self._one({"A": _pyproject(root / "a", _TAG.format("0.2.2")),
                       "B": root / "b" / "pyproject.toml"},
                      "is not there")

    def test_a_program_that_is_not_of_the_table(self):
        with _folder() as root:
            self._one({"A": _pyproject(root / "a", _TAG.format("0.2.2")),
                       "B": _pyproject(root / "b", _TAG.format("0.2.1")),
                       "C": _pyproject(root / "c", _TAG.format("0.2.1"))},
                      "C: given, and not a program of the table")


# ----------------------------------------------------------------------
#: The ``tests/_runner.py`` of an invented program: it writes down what it
#: was run with and against, and ends with the code it is told to.
_FAKE_RUNNER = '''\
import json, os, pathlib, sys
import ogr_core
pathlib.Path("seen.json").write_text(json.dumps({
    "argv": sys.argv[1:],
    "version": ogr_core.__version__,
    "core": str(pathlib.Path(ogr_core.__file__).resolve().parent),
    "marker": os.environ.get("OGR_TEST_MARKER"),
}), encoding="utf-8")
sys.exit(int(pathlib.Path("exit.txt").read_text()))
'''

_SUITE = "OGR_TEST_MARKER=seen python tests/_runner.py --jobs 4"


class _Run:
    """One run of the script on an invented program and an invented core."""

    def __init__(self, root: Path, core: str, pinned: str = "0.2.2",
                 said: str = "v0.2.2", code: int = 0,
                 own_copy: bool = False) -> None:
        self.core = _package(root / "core", core)
        self.program = root / "program"
        _pyproject(self.program, _TAG.format(pinned))
        if own_copy:
            _package(self.program, core)
        (self.program / "tests").mkdir()
        (self.program / "tests" / "_runner.py").write_text(
            _FAKE_RUNNER, encoding="utf-8")
        (self.program / "exit.txt").write_text(str(code), encoding="utf-8")
        out = io.StringIO()
        # another core already on the path, as the one a program installed
        # is: the core of the run has to come ahead of it
        other = _package(root / "other", "9.9.9").parent
        saved = os.environ.get("PYTHONPATH")
        os.environ["PYTHONPATH"] = str(other)
        try:
            # the output has `::error::` lines, which a CI would take for
            # commands of its own if this suite let them through
            with contextlib.redirect_stdout(out):
                self.code = S.run("P", self.program, core_root=root / "core",
                                  table=_table(("P", said, _SUITE)))
        finally:
            if saved is None:
                os.environ.pop("PYTHONPATH", None)
            else:
                os.environ["PYTHONPATH"] = saved
        self.said = out.getvalue()
        seen = self.program / "seen.json"
        self.seen = (json.loads(seen.read_text(encoding="utf-8"))
                     if seen.exists() else None)


class TestARun:
    def test_a_development_core(self):
        with _folder() as root:
            run = _Run(root, "0.2.3.dev0")
            assert run.code == 0, run.said
            assert run.seen == {
                "argv": ["--jobs", "4", "--dev-core"],
                "version": "0.2.3.dev0",
                "core": str(run.core.resolve()), "marker": "seen"}, run.seen
            assert "::notice::" not in run.said

    def test_the_exit_code_is_the_suites(self):
        with _folder() as root:
            assert _Run(root, "0.2.3.dev0", code=3).code == 3

    def test_the_pinned_release_runs_as_it_is(self):
        with _folder() as root:
            run = _Run(root, "0.2.2")
            assert run.code == 0, run.said
            assert run.seen["argv"] == ["--jobs", "4"], run.seen
            assert run.seen["version"] == "0.2.2"
            assert run.seen["core"] == str(run.core.resolve())

    def test_a_release_nobody_pins_yet_runs_as_its_development_version(self):
        with _folder() as root:
            run = _Run(root, "0.2.3")
            assert run.code == 0, run.said
            assert run.seen["argv"] == ["--jobs", "4", "--dev-core"]
            assert run.seen["version"] == "0.2.3.dev0", run.seen
            # a copy, said out loud and gone afterwards
            assert run.seen["core"] != str(run.core.resolve())
            assert not Path(run.seen["core"]).exists()
            assert "::notice::" in run.said and "0.2.3.dev0" in run.said
            assert _R.declared_version(run.core) == "0.2.3"

    def test_a_program_whose_pin_is_not_the_tables_does_not_run(self):
        with _folder() as root:
            run = _Run(root, "0.2.3.dev0", pinned="0.2.1")
            assert run.code == 1
            assert run.seen is None
            assert "::error::P: the table says v0.2.2" in run.said, run.said

    def test_a_core_that_is_not_the_one_of_the_run_does_not_run(self):
        """The script looks at where ``ogr_core`` comes from before the
        suite starts. Here the program carries a core of its own in its
        folder, with the same number: nothing else would tell them apart."""
        with _folder() as root:
            run = _Run(root, "0.2.3.dev0", own_copy=True)
            assert run.code == 1, run.said
            assert run.seen is None
            assert "not to the core of this run" in run.said, run.said

    def test_an_older_core_stops_before_the_suite(self):
        with _folder() as root:
            try:
                _Run(root, "0.2.2.dev0")
            except ValueError as exc:
                assert "older core" in str(exc)
            else:
                raise AssertionError("ran against an older core")
            assert not (root / "program" / "seen.json").exists()

    def test_a_program_that_is_not_of_the_table(self):
        try:
            S.the_row("Q", _table(("P", "v0.2.2", _SUITE)))
        except ValueError as exc:
            assert "'Q' is not a program" in str(exc)
        else:
            raise AssertionError("found a row for a program not in the table")
