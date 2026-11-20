# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
The test runner of the OGR Suite, for environments without pytest.

Discovers classes starting with 'Test' in tests/*.py, instantiates them,
and runs methods starting with 'test_'. Supports the small subset of
pytest features used in the OGR test suites:

    - pytest.approx()
    - pytest.raises(...)
    - pytest.skip(...)
    - tmp_path fixture (emulated with tempfile)

It lived in OGR Slip2D's ``tests/_runner.py`` until the core was extracted
(OGR Slip2D, spec 009, decision P4). It moved here, whole, so that the core
and every program run their suites with ONE runner: three copies would
drift, and a runner that behaves differently in each repository is a
measurement that means something different in each. Every repository keeps
a thin ``tests/_runner.py`` that says which packages are its OWN, which it
takes SHARED from another tree and at what version, what it adds to a run,
and calls :func:`cli`.

OGR Core 0.2.0 brought it level with Slip2D's runner of v0.1.471, which had
kept growing on its own after 0.1.0 was cut: the leak check after every file
(:mod:`ogr_core.testing.leaks`), the run in chunks, the slow list, and the
exit code that is the verdict. What 0.1.0 had added here (own and shared
packages, the pinned version, the hooks, a worktree's commit) is kept.
From there on it changes here and nowhere else.

Running a part of it
--------------------

    python tests/_runner.py                          # everything
    python tests/_runner.py transient                # by file fragment
    python tests/_runner.py transient seepage        # union of both
    python tests/_runner.py tests/test_mesh_v125.py  # by path
    python tests/_runner.py -k erfc                  # by test name
    python tests/_runner.py --list transient         # show, run nothing

Selection exists because a whole suite takes long and its cost is very
uneven: in OGR Slip2D at v0.1.80 the four slowest files were 42 % of the
time, and the 58 fastest — nearly half of all the tests — added up to under
ten seconds.

Two rules keep the shortcut from becoming a liar, and both are tested:

1. **No arguments behaves exactly as before.** That is what CI runs.
2. **A selection that matches nothing exits non-zero.** Otherwise a typo
   prints ``Total: 0  Passed: 0  Failed: 0`` and reads as success.

Which tree is being measured
----------------------------

Every run opens with a ``tree:`` line naming the directory the repository's
own ``ogr_*`` packages resolve to, and refuses to run if any of them
resolves outside it. That is not defensive tidiness — it is the fix for a
wrong diagnosis that nearly reversed a correct conclusion in OGR Slip2D
v0.1.84, because ``pip install -e .`` registers a finder that resolves every
``ogr_*`` to one hard-coded absolute path. The full mechanism is in
:func:`foreign_packages`.

A SHARED package is different: the core lives in another tree on purpose,
so the runner does not refuse it for being elsewhere. It NAMES it instead —
path, commit and version, one ``shared:`` line each — and refuses when its
version is not the one the repository pins. The property that mattered in
v0.1.84 survives the extraction: no run measures a tree it does not say.

The practical rule that follows: **run diagnostics from inside the tree you
mean to measure**, and check the ``tree:`` and ``shared:`` lines rather than
assuming.

A core that is being changed
----------------------------

    python tests/_runner.py --dev-core               # against X.Y.Z.devN

Between two tags the core's ``main`` says a development version
(``0.3.0.dev0``), and a program that pins ``0.2.0`` is refused against it:
that is the pin working. ``--dev-core`` is how a program's suite is run on
purpose against the core as it is being changed, which is what a change of
the core needs before it is merged. It accepts a shared package only when
its version is a ``.devN`` of a release LATER than the pinned one — never an
older core, never another release — and the run says ``DEV CORE`` before and
after its totals, as a filtered run does: it is not evidence for a release
of the program. With nothing to accept it stops with code 2 (rule 7: an
option that did nothing would read as a check that passed).

For its length, a run that accepted a development version says so in the
environment (``OGR_DEV_CORE=1``, see :data:`DEV_CORE_ENV`), which is how the
tests and the processes they start know it:

* a test asks :func:`dev_core_run`. A program's test of "the core imported
  is the one pinned" is false by construction in such a run; what it checks
  instead is ``shared_problems(origins, pinned, dev_core=dev_core_run())``,
  which is what the run itself was held to;
* a runner started inside the run — a test that relaunches
  ``tests/_runner.py``, which is another process and was not given the
  option — accepts the same development version, and says ``DEV CORE`` too.

The variable accepts nothing the option would not, and unlike the option it
never stops a run: with nothing to accept, the run is an ordinary one
against the pinned core. The run puts the variable back when it ends.

What a file leaves behind
-------------------------

After every file the runner puts back ``sys.path`` and the folders the run
gave itself, and names anything else the file left changed in the process
(``✗ [LEAK] key: before → after``): the file fails the run even if its
tests passed. See :mod:`ogr_core.testing.leaks` for what is looked at and
what is allowed; a program adds its own allow-list through ``allowed``.

Running in chunks
-----------------

    python tests/_runner.py --jobs 4                 # four processes
    python tests/_runner.py --jobs 4 --list          # the plan, run nothing

The selection is cut into contiguous pieces of the alphabetical order,
balanced by how long each file took last time, and each piece runs in a
process of its own with this same loop: the same leak check, the same
progress lines. The output is printed in order, as a serial run would print
it. Files with a module-level ``SERIAL_LANE = True`` (they compare with the
clock) run after the chunks, alone. A chunk that dies cannot leave a green
run behind: the run passes only if every chunk ends with its code, every
selected file reports its end, and the tests run are the tests declared
(see :func:`partition` and ``_run_jobs``). Without ``--jobs`` nothing
changes, and that serial run is what CI executes.

A repository that sets ``serial_every`` (OGR Slip2D: 100, its owner's
decision of v0.1.376) releases with the whole suite in chunks and runs it in
series once every that many commits. A green serial run records its commit
in the temporary folder, and every whole run in chunks ends saying how many
commits ago that was, or ``SERIAL RUN DUE``. Only the serial run keeps the
whole suite in one process, as Slip2D's abort of v0.1.302 needed in order
to show.

Leaving the slow files out
--------------------------

    python tests/_runner.py --fast --jobs 4          # what development runs
    python tests/_runner.py --write-slow-list        # rewrite tests/_slow.txt

``--fast`` leaves out the files listed in ``tests/_slow.txt`` and says so
before and after the totals, as any filtered run does: it is not evidence
for a release. Whole files and not single tests, because a file's tests
share what is expensive: leave out the test that paid for it and the next
one pays (measured in Slip2D v0.1.376: 19.3 min instead of 11). The list is
versioned and written on purpose, from each file's last measured seconds; a
run never rewrites it, so a new slow file stays in ``--fast`` until someone
decides otherwise. A whole run names the files of twice the threshold it
leaves in.

What is kept on the machine
---------------------------

A repository's runner gives the run a ``label`` (``ogr-slip2d``), and the
last seconds of each file and of each test, and the serial record, are kept
under that name in the temporary folder: they describe this machine, not the
code. A run with no label — the throwaway folders the runner's own tests
run — keeps nothing.
"""
from __future__ import annotations

import argparse
import ast
import codecs
import functools
import gc
import importlib.util
import inspect
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional


# --- pytest compatibility shim ----------------------------------------
class _Approx:
    def __init__(self, expected, rel=None, abs_=None):
        self.expected = expected
        self.rel = rel
        self.abs = abs_

    def __eq__(self, other):
        if self.abs is not None:
            return math.isclose(other, self.expected, abs_tol=self.abs)
        tol = self.rel if self.rel is not None else 1e-6
        return math.isclose(other, self.expected, rel_tol=tol, abs_tol=1e-9)

    def __repr__(self):
        return f"approx({self.expected})"


def _approx(expected, rel=None, abs=None):  # noqa: A002
    return _Approx(expected, rel=rel, abs_=abs)


@contextmanager
def _raises(exc_type):
    try:
        yield
    except exc_type:
        return
    except Exception as e:
        raise AssertionError(f"Expected {exc_type.__name__}, got {type(e).__name__}")
    raise AssertionError(f"Expected {exc_type.__name__}, no exception raised")


class Skipped(BaseException):
    """``pytest.skip`` in this runner: the test cannot be measured HERE.

    OGR Slip2D v0.1.205 — the shim had no ``skip``, so a test that called it
    failed with an AttributeError instead: on GitHub, where the verification
    bank does not exist, a test turned the CI red for a reason that was not
    a defect. A ``BaseException``, as pytest's own, so that a test's
    ``except Exception`` cannot swallow it.

    Recognised by the ``ogr_skip`` mark and NOT by its class, on purpose: a
    second copy of this module (one loaded by path) makes a second
    ``Skipped`` class. On GitHub that copy's skip escaped the running
    runner's ``except Skipped`` and ended the suite at 83 % with no totals.
    Any copy's mark is the same mark.
    """
    ogr_skip = True


def _skip(reason: str = ""):
    raise Skipped(reason)


class _FakePytest:
    approx = staticmethod(_approx)
    raises = staticmethod(_raises)
    skip = staticmethod(_skip)
    #: This shim, as opposed to a real pytest.
    ogr_shim = True


def install_pytest_shim() -> None:
    """Make ``import pytest`` give the shim, keeping one already installed.

    In OGR Slip2D this ran at import time of ``tests/_runner.py``. Here it
    runs at the start of :func:`main` instead: this module is part of the
    core's distribution, and importing a module of the core must not put a
    fake ``pytest`` into ``sys.modules`` behind anybody's back. The test
    files only import ``pytest`` once the runner is loading them, so they
    see the shim either way.

    Keeping the first one installed is the Slip2D v0.1.205 rule: replacing
    it left a different shim installed for every file after the one that
    replaced it (rule 5).
    """
    if not getattr(sys.modules.get("pytest"), "ogr_shim", False):
        sys.modules["pytest"] = _FakePytest()  # type: ignore


# --- What a repository adds around a run ------------------------------
@dataclass(frozen=True)
class Hooks:
    """What a program adds to a run.

    ``before_run`` is called by :func:`main` once, after the trees have been
    checked and before anything is selected or loaded: it imports from the
    tree just checked, which is why it cannot run earlier. ``before_file``
    is called before each file, ahead of the runner's own ``gc.collect()``.
    ``after_run`` is called by :func:`cli` — the command line, never an
    inner ``main()`` — once the run has printed everything and the streams
    are empty, just before the process ends.

    OGR Slip2D's interface uses the first two for ``gc_guard`` (v0.1.302:
    cyclic garbage holding Qt objects is freed on the main thread, not by
    whichever thread trips the collector), and the last to delete the
    windows without a parent that the tests left alive, with Python still
    alive (v0.1.422, D370: at the interpreter's shutdown PySide deletes
    every wrapped object one by one, in no order a window's children can
    rely on, and the suite segfaulted on Linux after its totals). The core
    has no Qt and needs none of them, which is why they are hooks and not
    imports: this module cannot import ``ogr_gui`` (``AGENTS.md``, layers).

    In a run with ``--jobs`` every chunk is a process that enters through
    the repository's own ``tests/_runner.py``, so each one gets the hooks.
    """
    before_run: Optional[Callable[[], None]] = None
    before_file: Optional[Callable[[], None]] = None
    after_run: Optional[Callable[[], None]] = None


# --- Which trees ------------------------------------------------------
def package_origins(names: Iterable[str]) -> dict:
    """Where each named package WOULD be imported from.

    ``find_spec`` resolves through the same finders a real import would, so
    this sees exactly what the tests will see — but it executes no
    module-level code, which is the property that lets it run before the
    first test. Importing the packages here to ask them their ``__file__``
    would run the module-level code of half the project before anything is
    measured, which is what rule 5 exists to prevent.

    Returns ``{name: directory or None}``.
    """
    out = {}
    for name in names:
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ValueError, AttributeError):
            spec = None
        origin = getattr(spec, "origin", None) if spec else None
        out[name] = Path(origin).resolve().parent if origin else None
    return out


def foreign_packages(origins: dict, repo_root: Path) -> list:
    """The packages that resolve OUTSIDE ``repo_root``.

    OGR Slip2D v0.1.89 — this exists because of a wrong diagnosis that cost
    two days and nearly reversed a correct conclusion. Diagnosing the
    v0.1.84 fall of ``test_support_increases_fos``, a stand-alone script
    replicating the test line by line reported the SAME result for the
    working tree and for HEAD, when instrumenting inside the runner showed
    10 valid surfaces and a critical 2.1279 against 0 valid. The script was
    not wrong about what it measured; it was measuring the wrong tree, and
    said nothing about it.

    The mechanism, and it is fully deterministic:

    1. ``python C:\\somewhere\\else\\script.py`` puts the SCRIPT's directory
       in ``sys.path[0]`` — not the working directory.
    2. There is no ``ogr_*`` there, so ``PathFinder`` (position 2 of
       ``sys.meta_path``) finds nothing.
    3. ``_EditableFinder`` (position 3), installed by ``pip install -e .``,
       answers instead — and it resolves every ``ogr_*`` to one hard-coded
       absolute path, the tree that was installed.

    So a script stored outside the repository imports the MAIN working tree
    whatever tree you cd into or commit you check out.

    The runner does not have the problem — each ``tests/_runner.py`` puts
    its own repository first on ``sys.path`` — but it cannot detect the
    problem for others either, so what it can do is refuse to run when it is
    itself pointed at another tree, and print where it is looking either
    way. A suite that silently tests a different tree than the one being
    edited is the worst failure available: every result is real and every
    conclusion is wrong.
    """
    bad = []
    for name, where in sorted(origins.items()):
        if where is None:
            bad.append((name, None))
            continue
        try:
            where.relative_to(repo_root)
        except ValueError:
            bad.append((name, where))
    return bad


def _git_dir(repo_root: Path) -> Optional[Path]:
    """The git directory of ``repo_root``: ``.git`` itself, or the one a
    ``.git`` FILE points to (``gitdir: …``), which is what a worktree has."""
    dot = repo_root / ".git"
    if dot.is_dir():
        return dot
    if dot.is_file():
        text = dot.read_text(encoding="utf-8").strip()
        if text.startswith("gitdir:"):
            target = Path(text[len("gitdir:"):].strip())
            return target if target.is_absolute() else (repo_root / target)
    return None


def _ref_sha(git_dir: Path, ref: str) -> str:
    """The commit a ref names, looked up where git keeps it: the worktree's
    own git directory, the common one (``commondir``), or ``packed-refs``."""
    common = git_dir
    pointer = git_dir / "commondir"
    if pointer.is_file():
        target = Path(pointer.read_text(encoding="utf-8").strip())
        common = target if target.is_absolute() else (git_dir / target)
    for base in (git_dir, common):
        if (base / ref).is_file():
            return (base / ref).read_text(encoding="utf-8").strip()
    packed = common / "packed-refs"
    if packed.is_file():
        for line in packed.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == ref:
                return parts[0]
    return ""


def head_sha(repo_root: Path) -> str:
    """The short commit of ``repo_root``, read from git's files directly.

    No subprocess: the banner must not be able to fail. This says which
    commit, not whether the tree is clean — ``git status`` is the reader's
    job, and the PATH above is the part that actually caused the bug.

    Spec 009 of OGR Slip2D did its first phase in a worktree, and there the
    banner said ``@ ?``: a worktree's ``.git`` is a file pointing at the
    repository, and its branch lives in the common git directory. Both are
    followed here, and so are packed refs.
    """
    try:
        git_dir = _git_dir(repo_root)
        if git_dir is None:
            return "?"
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        sha = _ref_sha(git_dir, head[5:].strip()) \
            if head.startswith("ref: ") else head
        return sha[:7] if sha else "?"
    except OSError:
        return "?"


def declared_version(package_dir: Optional[Path]) -> Optional[str]:
    """The ``__version__`` a package's ``__init__.py`` declares, read from
    its source WITHOUT executing it — for the same reason as
    :func:`package_origins`: the check runs before the first test.

    ``None`` when there is no package, no ``__init__.py``, or no plain
    string assigned to ``__version__`` at its top level.
    """
    if package_dir is None:
        return None
    try:
        tree = ast.parse((package_dir / "__init__.py").read_text(
            encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if (any(isinstance(t, ast.Name) and t.id == "__version__"
                for t in targets)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            return node.value.value
    return None


def _canonical(name: str) -> str:
    # PEP 503: ``ogr_core``, ``OGR-Core`` and ``ogr.core`` name one project.
    return re.sub(r"[-_.]+", "-", name).lower()


def pinned_from_pyproject(pyproject: Path, dist: str) -> Optional[str]:
    """The exact version of ``dist`` that ``pyproject.toml`` pins, or None.

    Two forms count as a pin, because they are the two a program can use
    (spec 009, decision P3): a git reference to a tag,
    ``ogr-core @ git+https://github.com/samuelsl27/OGR-Core@v0.1.0``, and
    ``ogr-core==0.1.0``. A range (``>=0.1``) is not a pin and gives None:
    a runner that compared against the lower bound of a range would accept
    trees the program never said it supports.
    """
    import tomllib  # Python ≥ 3.11, the floor of the suite

    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for req in data.get("project", {}).get("dependencies", []):
        m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(.*)$",
                     req)
        if not m or _canonical(m.group(1)) != _canonical(dist):
            continue
        rest = m.group(2).split(";", 1)[0].strip()
        tag = re.match(r"@\s*\S+@v?(\d+(?:\.\d+)*)$", rest)
        if tag:
            return tag.group(1)
        exact = re.match(r"==\s*(\d+(?:\.\d+)*)$", rest)
        if exact:
            return exact.group(1)
        return None
    return None


def dev_base(version: Optional[str]) -> Optional[tuple]:
    """The release a development version leads to, as a tuple of numbers:
    ``(0, 3, 0)`` for ``"0.3.0.dev0"``; None for anything that is not a
    ``.devN`` of a plain release number.

    The only pre-release form the suite uses (PEP 440's development release).
    Nothing else is read as one on purpose: ``0.3.0rc1`` or a local
    ``0.3.0+patched`` would be a core somebody chose to call a release.
    """
    m = re.fullmatch(r"(\d+(?:\.\d+)*)\.dev\d+", version or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def _release(version: str) -> Optional[tuple]:
    if not re.fullmatch(r"\d+(?:\.\d+)*", version or ""):
        return None
    return tuple(int(x) for x in version.split("."))


def _is_dev_of_later(have: Optional[str], want: str) -> bool:
    """Whether ``have`` is a development version of a release after ``want``.

    After, not equal: ``0.2.0.dev0`` came BEFORE the ``0.2.0`` a program
    pins, so it is an older core, and an older core is never accepted.
    """
    base, pinned = dev_base(have), _release(want)
    if base is None or pinned is None:
        return False
    n = max(len(base), len(pinned))
    pad = lambda t: t + (0,) * (n - len(t))  # noqa: E731
    return pad(base) > pad(pinned)


#: v0.2.2 — the environment variable a run that accepted a development
#: version of the core sets to ``"1"`` for its length: what its tests read
#: (:func:`dev_core_run`) and what a runner started inside it inherits.
DEV_CORE_ENV = "OGR_DEV_CORE"


def dev_core_run() -> bool:
    """Whether this process belongs to a run that accepted a development
    version of a shared package (``--dev-core``).

    v0.2.2. The first whole suites run with the option (OGR FEM2D and OGR
    Slip2D against 0.2.1.dev0) each failed a handful of tests that could
    not have passed: the ones that say the imported core is the pinned one,
    and the ones that start the repository's runner again, in a process
    that had not been given the option and so refused the core. A program
    cannot come out green of the run a change of the core asks it for
    unless its tests can tell which run they are in.

    Only ``"1"`` counts: any other value is not this run saying so.
    """
    return os.environ.get(DEV_CORE_ENV) == "1"


def _puts_back_dev_core(fn):
    """``fn`` leaves :data:`DEV_CORE_ENV` as it found it: a run called from
    a test must not turn the rest of that suite into a development run."""
    @functools.wraps(fn)
    def run(*args, **kwargs):
        saved = os.environ.get(DEV_CORE_ENV)
        try:
            return fn(*args, **kwargs)
        finally:
            if saved is None:
                os.environ.pop(DEV_CORE_ENV, None)
            else:
                os.environ[DEV_CORE_ENV] = saved
    return run


def shared_problems(origins: dict, pinned: dict,
                    dev_core: bool = False) -> list:
    """Why the shared packages cannot be measured, as sentences; empty when
    they can.

    A shared package that does not resolve is a problem — the tests are
    about to import it and fail one by one instead. One whose declared
    version is not the pinned one is a problem too: the program would be
    tested against a core it does not say it supports.

    With ``dev_core`` (``--dev-core``), and only then, a development version
    of a release later than the pinned one is not a problem: see
    :func:`shared_dev`, which names the ones a run accepted that way.
    """
    problems = []
    for name, where in sorted(origins.items()):
        if where is None:
            problems.append(f"{name} is not importable at all")
            continue
        want = pinned.get(name)
        if want is None:
            continue
        have = declared_version(where)
        if have == want:
            continue
        later_dev = _is_dev_of_later(have, want)
        if dev_core and later_dev:
            continue
        problems.append(
            f"{name} {have or '(no __version__)'} resolves to {where}, "
            f"but this repository pins {want}"
            + (" (a development version of a later release: --dev-core "
               "runs against it, and that run is not evidence for a release)"
               if later_dev else ""))
    return problems


def shared_dev(origins: dict, pinned: dict) -> list:
    """``[(name, version, pinned)]`` for every shared package that is a
    development version of a release later than its pin: what a run with
    ``--dev-core`` is running against instead of what the repository pins."""
    out = []
    for name, where in sorted(origins.items()):
        want = pinned.get(name)
        if where is None or want is None:
            continue
        have = declared_version(where)
        if have != want and _is_dev_of_later(have, want):
            out.append((name, have, want))
    return out


def provenance(repo_root: Path, origins: dict) -> str:
    """One line saying which tree is about to be measured.

    Each package sits in its OWN directory under the tree, so the thing to
    collapse is their common parent, not the directories themselves. Getting
    that wrong prints five absolute paths on one line, which is the sort of
    banner people learn to skip — and a banner nobody reads protects nothing.
    """
    n = len(origins)
    count = f"({n} ogr package{'' if n == 1 else 's'})"
    parents = {v.parent for v in origins.values() if v is not None}
    if len(parents) == 1:
        return f"tree: {parents.pop()}  @ {head_sha(repo_root)}  {count}"
    if not parents:
        return f"tree: {repo_root}  @ {head_sha(repo_root)}  {count}"
    return "tree: " + ", ".join(
        f"{k}={v}" for k, v in sorted(origins.items()))


def shared_provenance(origins: dict) -> list:
    """One ``shared:`` line per shared package: name, version, path, commit.

    The commit is read only when the package sits directly under a git tree,
    which is how the core's repository is laid out. A copy installed into a
    ``site-packages`` that happens to live inside some other repository's
    ``.venv`` must not borrow that repository's commit: it says
    ``installed`` instead.
    """
    lines = []
    for name, where in sorted(origins.items()):
        if where is None:
            lines.append(f"shared: {name} (not importable)")
            continue
        repo = where.parent if (where.parent / ".git").exists() else None
        at = f"@ {head_sha(repo)}" if repo else "(installed, no git tree)"
        lines.append(f"shared: {name} {declared_version(where) or '?'}  "
                     f"{where}  {at}")
    return lines


# --- Selection --------------------------------------------------------
def _normalise(pattern: str) -> str:
    """Reduce a file pattern to the fragment that is compared against a stem.

    A pattern may arrive in three shapes and all three must work:
    ``transient``, ``test_transient_v130.py`` (shell completion) and
    ``tests/test_transient_v130.py`` (copied from a traceback). Dropping
    the directory part and the extension makes them one case.

    Resolving the pattern as a path instead would tie the result to the
    current directory, so ``tests/test_x.py`` would select from the repo
    root and silently select nothing from anywhere else. A pattern must
    mean the same thing wherever it is typed.
    """
    p = pattern.replace("\\", "/").rstrip("/")
    p = p.rsplit("/", 1)[-1]
    if p.endswith(".py"):
        p = p[:-3]
    return p.lower()


def select_files(tests_dir: Path, patterns) -> list[Path]:
    """The test files to run, in the order the runner has always used.

    With no patterns this is ``sorted(glob("test_*.py"))`` — byte for byte
    what CI executes. With patterns, a file is kept when any normalised
    pattern is a substring of its stem. The order never changes: a run
    that cannot be reproduced in the same order cannot be used to chase a
    state leak, which is the failure rule 5 exists for.
    """
    every = sorted(tests_dir.glob("test_*.py"))
    if not patterns:
        return every
    wanted = [n for n in (_normalise(p) for p in patterns) if n]
    return [f for f in every
            if any(n in f.stem.lower() for n in wanted)]


def match_test(class_name: str, method_name: str, expr: str | None) -> bool:
    """Whether ``Class.method`` is kept by a ``-k`` expression.

    Plain case-insensitive substring against ``"Class.method"``. The
    ``and``/``or``/``not`` grammar of pytest's own ``-k`` is deliberately
    NOT implemented: a boolean parser that mis-reads a ``not`` selects a
    different set than the one the reader believes it selected, and says
    nothing. A documented substring cannot be misread that way.
    """
    if not expr:
        return True
    return expr.lower() in f"{class_name}.{method_name}".lower()


def node_id(path: Path, class_name: str, method_name: str) -> str:
    """``file.py::Class::method``: how ``--list`` and the test times name a
    test."""
    return f"{path.name}::{class_name}::{method_name}"


def _declared_tests(files, expr: str | None = None):
    """Every ``(file, class, method)`` the selection declares, WITHOUT
    importing anything.

    The runner discovers tests as it goes, so it cannot know the total
    until the end. Importing every module up front to count them would
    execute the module-level code of the whole suite before the first
    test runs — exactly the kind of state leak rule 5 exists to prevent.
    Parsing the source answers the question with no execution at all.

    Applying ``expr`` here rather than after the fact is what keeps the
    progress denominator honest under ``-k``.

    Returns ``None`` if anything cannot be parsed, in which case the
    caller falls back to a plain counter. A progress display must never
    be the reason a test run fails.
    """
    found: list[tuple[Path, str, str]] = []
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            return None
        for node in tree.body:
            if not (isinstance(node, ast.ClassDef)
                    and node.name.startswith("Test")):
                continue
            for m in node.body:
                # ``async def`` too: the loop runs it (to fail it, see
                # ``_run_method``), so it is one of the tests declared. Left
                # out, as it was until OGR Core 0.2.1, it did not show in
                # ``--list``, the progress went past 100 % and a run with
                # ``--jobs`` said the chunks ran a test the source did not
                # declare.
                if (isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and m.name.startswith("test_")
                        and match_test(node.name, m.name, expr)):
                    found.append((f, node.name, m.name))
    return found


def _count_tests(files, expr: str | None = None) -> int:
    """Total number of selected test methods, or 0 if the source cannot
    be parsed."""
    declared = _declared_tests(files, expr)
    return len(declared) if declared is not None else 0


def _suggest(every, patterns) -> list[str]:
    """File names close to what was asked, so a typo is visible.

    ``transiant`` shares its first four characters with
    ``test_transient_v130``; printing that beside the error turns a blank
    result into an obvious misspelling.
    """
    out: list[str] = []
    for p in patterns:
        head = _normalise(p)[:4]
        if head:
            out += [f.stem for f in every if head in f.stem.lower()]
    return sorted(set(out))[:8]


# --- Discovery & runner -----------------------------------------------
def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod


def _run_method(instance, method):
    # Bind the unbound function to the instance so `self` is provided
    bound = method.__get__(instance, type(instance))
    sig = inspect.signature(bound)
    kwargs = {}
    if "tmp_path" in sig.parameters:
        tmpdir = tempfile.mkdtemp()
        kwargs["tmp_path"] = Path(tmpdir)
    result = bound(**kwargs)
    # Slip2D v0.1.194 — an ``async def`` test returns a coroutine WITHOUT
    # RUNNING A LINE OF ITS BODY, and until then that return value was
    # ignored, so it counted as a pass: a green test that tested nothing.
    if inspect.iscoroutine(result):
        result.close()
        raise TypeError(
            f"{method.__name__} is `async def`, and this runner does not "
            f"await coroutines, so its body never ran. Make it a plain "
            f"method and drive the async part with asyncio.run(...).")


def run_test(cls, method):
    """Run one test: ``(outcome, why, traceback)``, with ``outcome`` one of
    ``"passed"``, ``"failed"`` and ``"skipped"``.

    Slip2D v0.1.203 — ``SystemExit`` is a failure of that test, like any
    other exception. Code under test that calls ``sys.exit`` (argparse does,
    on an option it does not know) used to escape the run loop and end the
    WHOLE suite there, with no totals: one test's failure cost every file
    after it. ``KeyboardInterrupt`` still stops the run, as it should.

    Slip2D v0.1.205 — ``pytest.skip`` is a third outcome, counted apart:
    neither a pass (it measured nothing) nor a failure (nothing was wrong).
    """
    try:
        _run_method(cls(), method)
        return "passed", None, None
    except AssertionError as e:
        return "failed", f"{e}", traceback.format_exc()
    except (Exception, SystemExit) as e:  # noqa: BLE001
        return "failed", f"{type(e).__name__}: {e}", traceback.format_exc()
    except BaseException as e:
        # By its mark, from whichever copy of this module raised it (see
        # ``Skipped``); anything else — KeyboardInterrupt — goes on up.
        if getattr(e, "ogr_skip", False):
            return "skipped", f"{e}", None
        raise


# --- What is kept on the machine (Slip2D v0.1.375–0.1.376) --------------
@dataclass(frozen=True)
class Records:
    """The files a repository's runs keep in the temporary folder.

    ``durations`` — the last measured seconds of each file, by name, to
    balance the chunks of ``--jobs`` and to write the slow list. In the
    temporary folder and not in the repository: it describes this machine,
    not the code, and a missing or stale entry only makes the chunks less
    even, never the run less complete. ``test_times`` — the same, test by
    test (by :func:`node_id`): which tests make a file slow, for whoever
    studies what the suite costs. ``serial`` — the commit of the last green
    serial run of the whole suite on this machine (see ``serial_every``).
    """
    durations: Path
    test_times: Path
    serial: Path


def records_for(label: str) -> Records:
    """The machine files of the repository that calls its runs ``label``:
    ``ogr-slip2d`` keeps ``ogr-slip2d-test-durations.json`` and its two
    companions, the names Slip2D's own runner used, so that adopting this
    one loses no measured time."""
    tmp = Path(tempfile.gettempdir())
    return Records(durations=tmp / f"{label}-test-durations.json",
                   test_times=tmp / f"{label}-test-times.json",
                   serial=tmp / f"{label}-serial-run.json")


def serial_lane(path: Path) -> bool:
    """Whether a test file asks to run alone, after the chunks: a
    module-level ``SERIAL_LANE = True``, read from the source without
    importing it (nothing of a file runs before its turn). For the files
    that compare with the clock, which a process sharing the cores could
    fail for a reason that is not a defect."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return False
    for node in tree.body:
        if (isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "SERIAL_LANE"
                        for t in node.targets)):
            return (isinstance(node.value, ast.Constant)
                    and node.value.value is True)
    return False


def _read_json(path: Optional[Path]):
    if path is None:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_json(path: Path, data) -> None:
    """Written aside and moved, so that a run reading it never sees half a
    file; a failure to write costs what the file was for, not a run."""
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=0, sort_keys=True),
                       encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        with suppress(OSError):
            tmp.unlink()


def load_durations(path: Optional[Path]) -> dict:
    """``{name: seconds}`` from a durations file; empty when there is none
    (no path, no file, or not what this module writes)."""
    data = _read_json(path)
    if not isinstance(data, dict):
        return {}
    return {k: float(v) for k, v in data.items()
            if isinstance(v, (int, float)) and v >= 0}


def save_durations(times: dict, path: Optional[Path]) -> None:
    """Merge ``times`` into the file: a filtered run updates its own files
    and keeps the rest. Nothing without a path (a run that keeps nothing)."""
    if not times or path is None:
        return
    data = load_durations(path)
    data.update({k: round(v, 3) for k, v in times.items()})
    _write_json(path, data)


# --- The serial run a release needs (Slip2D v0.1.376) -------------------
def _git(repo_root: Path, *args) -> str | None:
    """What ``git <args>`` prints in ``repo_root``, or None when git cannot
    answer (no git, not a repository, a commit it does not know)."""
    try:
        out = subprocess.run(["git", *args], cwd=repo_root, timeout=60,
                             capture_output=True, text=True,
                             stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def record_serial_run(repo_root: Path, tests: int,
                      path: Path) -> str | None:
    """Remember that the whole suite passed in series at HEAD; the commit,
    or None when there is no commit to name (and nothing is written)."""
    sha = _git(repo_root, "rev-parse", "HEAD")
    if not sha:
        return None
    _write_json(path, {"commit": sha, "date": time.strftime("%Y-%m-%d %H:%M"),
                       "tests": tests})
    return sha


def serial_notice(repo_root: Path, path: Optional[Path], every: int,
                  prog: str = "python tests/_runner.py") -> str:
    """How long ago the last green serial run was, or ``SERIAL RUN DUE``.

    Due also when it cannot be told — no record on this machine, a commit
    this history does not have, no git: the doubt costs one serial run, the
    other answer could skip one for good."""
    rec = _read_json(path)
    todo = (f"run `{prog}` with no arguments before the next "
            f"release (AGENTS.md: every {every} commits)")
    if not (isinstance(rec, dict) and isinstance(rec.get("commit"), str)):
        return f"SERIAL RUN DUE — no full serial run recorded on this machine; {todo}"
    sha, date = rec["commit"][:7], rec.get("date", "?")
    count = _git(repo_root, "rev-list", "--count", f"{rec['commit']}..HEAD")
    if count is None or not count.isdigit():
        return (f"SERIAL RUN DUE — the last full serial run ({sha}, {date}) "
                f"is not in this history; {todo}")
    n = int(count)
    if n >= every:
        return (f"SERIAL RUN DUE — {n} commits since the last full serial run "
                f"({sha}, {date}); {todo}")
    return (f"last full serial run: {sha}, {date}, {n} commit(s) ago "
            f"(the next is due at {every})")


# --- The slow files (Slip2D v0.1.376) -----------------------------------
#: The name, in a repository's ``tests/``, of the list of the files
#: ``--fast`` leaves out. Versioned, and written on purpose by
#: ``--write-slow-list``: a run that rewrote it would drop each new slow
#: file from development runs without anyone deciding so.
#:
#: Files, not tests. Slip2D's first list named the 174 tests of 10 s or
#: more, and ``--fast --jobs 4`` took 19.3 min where its chunks were planned
#: at 11: a file's tests share what is expensive (a module-level search, a
#: mesh, a solved model), the test that ran first paid for it in the whole
#: run, and once it was left out the next one paid instead — 0.0 s to 275 s
#: for one of them. Rewriting the list from those times would not settle it
#: either: the next whole run gives the cost back to the first test.
SLOW_LIST_NAME = "_slow.txt"
#: What ``--write-slow-list`` writes by default: the files of this many
#: seconds or more in their last whole run, which in Slip2D is a run with
#: --jobs 4 (each test takes about twice what it takes alone). A whole run
#: names the files of twice this that the list leaves in; twice, so that a
#: file near the line does not come and go each run.
SLOW_SECONDS = 45.0


def load_slow_list(path: Path) -> frozenset:
    """The file names in the list; ``#`` starts a comment."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return frozenset()
    return frozenset(line.split("#", 1)[0].strip()
                     for line in text.splitlines()
                     if line.split("#", 1)[0].strip())


def write_slow_list(tests_dir: Path, seconds: float,
                    durations_path: Optional[Path], path: Path,
                    prog: str = "python tests/_runner.py") -> int:
    """Write the list from each file's last whole-file time on this machine:
    the test files in the folder today that took ``seconds`` or more, in
    their order."""
    durations = load_durations(durations_path)
    files = [f.name for f in sorted(tests_dir.glob("test_*.py"))]
    timed = [f for f in files if f in durations]
    if not timed:
        print("No test file has a time on this machine yet: run the whole "
              "suite first (`--jobs 4` is enough), then write the list.")
        return 2
    slow = [f for f in timed if durations[f] >= seconds]
    counts: dict = {}
    for f, _cls, _m in (_declared_tests(sorted(tests_dir.glob("test_*.py")))
                        or ()):
        counts[f.name] = counts.get(f.name, 0) + 1
    # The licence lines are this file's own first two, not a copy of them in
    # a string: the licence test reads every identifier written in the
    # sources, quotes included.
    licence = Path(__file__).read_text(encoding="utf-8").splitlines(True)[:2]
    head = (
        "".join(licence) +
        "#\n"
        f"# The test files `{prog} --fast` leaves out. Written by\n"
        f"# `{prog} --write-slow-list {seconds:g}` on "
        f"{time.strftime('%Y-%m-%d')}:\n"
        f"# the files that took {seconds:g} s or more in their last whole run "
        "on the\n"
        "# development machine (seconds and tests after each). Written on "
        "purpose, never\n"
        "# by a run; a whole run, which a release needs, runs every one of "
        "them.\n")
    path.write_text(head + "".join(
        f"{f}  # {durations[f]:.0f} s, {counts.get(f, 0)} tests\n"
        for f in slow), encoding="utf-8", newline="\n")
    print(f"{len(slow)} file(s) of {seconds:g} s or more written to {path}, "
          f"with {sum(counts.get(f, 0) for f in slow)} of the "
          f"{sum(counts.values())} tests: "
          f"{sum(durations[f] for f in slow) / 60:.1f} of the "
          f"{sum(durations[f] for f in timed) / 60:.1f} min timed. "
          f"{len(files) - len(timed)} of the {len(files)} file(s) have no "
          f"time yet, and stay in --fast.")
    return 0


def slow_unlisted(times: dict, listed, seconds: float) -> list:
    """``[(name, seconds)]``, slowest first: the files of ``seconds`` or
    more that the slow list leaves in ``--fast``."""
    return sorted(((i, s) for i, s in times.items()
                   if s >= seconds and i not in listed),
                  key=lambda x: (-x[1], x[0]))


def _print_slow_unlisted(times: dict, slow_list: Path,
                         slow_seconds: float) -> None:
    seconds = 2 * slow_seconds
    found = slow_unlisted(times, load_slow_list(slow_list), seconds)
    if not found:
        return
    print(f"SLOW, NOT IN tests/{slow_list.name} — {len(found)} file(s) took "
          f"{seconds:g} s or more and --fast still runs them:")
    for i, s in found[:10]:
        print(f"  {i}  {s:.1f} s")
    if len(found) > 10:
        print(f"  … and {len(found) - 10} more")
    print("  (make it cheaper, or write the list again with "
          "--write-slow-list)")


# --- Running in chunks (Slip2D v0.1.375) --------------------------------
def file_weights(files, counts: dict, durations: dict) -> list:
    """What each file is expected to cost: its last duration; for a file
    never timed, its tests at the median seconds per test of the files that
    were (one second per test when none was)."""
    rates = sorted(durations[f.name] / counts[f.name] for f in files
                   if f.name in durations and counts.get(f.name))
    rate = rates[len(rates) // 2] if rates else 1.0
    return [max(durations.get(f.name, rate * max(counts.get(f.name, 0), 1)),
                1e-3)
            for f in files]


def partition(weights, n: int) -> list:
    """``[(start, end), ...]``: at most ``n`` contiguous slices that cover
    ``weights`` in order, with the heaviest slice as light as it can be.

    Contiguous on purpose. Each chunk is a piece of the alphabetical order,
    so a file keeps the neighbours it has in the serial run except at the
    n - 1 borders, and a run can be repeated as it was. A queue that hands
    out files as processes come free would end sooner, and would give files
    different neighbours in every run: a leak a neighbour depends on would
    show or hide by chance.

    The heaviest slice is minimised exactly (the linear partition problem):
    the smallest capacity that a greedy fill packs into ``n`` slices, found
    by bisection, and the greedy fill at that capacity. That fill can use
    fewer slices than ``n``; the heaviest slice of two files or more is then
    split where its halves are most even, which never raises the heaviest,
    until there are ``n``: whoever asks for four processes gets four.
    """
    weights = list(weights)
    if not weights:
        return []
    n = max(1, min(n, len(weights)))

    def fill(cap):
        out, start, acc = [], 0, 0.0
        for i, w in enumerate(weights):
            if i > start and acc + w > cap:
                out.append((start, i))
                start, acc = i, 0.0
            acc += w
        out.append((start, len(weights)))
        return out

    lo, hi = max(weights), sum(weights)
    for _ in range(200):
        if hi - lo <= 1e-9 * hi:
            break
        mid = (lo + hi) / 2
        if len(fill(mid)) <= n:
            hi = mid
        else:
            lo = mid
    parts = fill(hi)
    while len(parts) < n:
        a, b = max((p for p in parts if p[1] - p[0] > 1),
                   key=lambda p: sum(weights[p[0]:p[1]]))
        cut = min(range(a + 1, b), key=lambda c: max(sum(weights[a:c]),
                                                     sum(weights[c:b])))
        i = parts.index((a, b))
        parts[i:i + 1] = [(a, cut), (cut, b)]
    return parts


class _Tally:
    """What a run has counted, and the progress tag of its next test. A
    chunk counts from its place in the whole run, so that its lines read
    as the same lines of a serial run."""

    def __init__(self, total: int, offset: int = 0):
        self.passed = self.failed = self.skipped = 0
        self.leaked = 0     # files, not tests: see _run_files
        self.fail_details: list[tuple[str, str]] = []
        self.total, self.offset = total, offset
        # Fixed width, so the pass/fail marks stay in one column and the
        # output is still readable when it scrolls.
        self.w = len(str(total)) if total else 4

    def tag(self) -> str:
        done = self.offset + self.passed + self.failed + self.skipped
        if not self.total:
            return f"[{done:>{self.w}}]"
        return (f"[{done:>{self.w}}/{self.total} "
                f"{100.0 * done / self.total:3.0f}%]")


def _totals_line(passed, failed, skipped, leaked, died=0) -> str:
    # A skip is counted apart and named: it is neither a pass (it measured
    # nothing) nor a failure (nothing was wrong). Absent when there is none,
    # so a run without skips prints exactly what it always printed. So are
    # the files that leaked (Slip2D v0.1.374): their tests passed, the file
    # did not; and the chunks of --jobs that died (v0.1.375).
    return (f"Total: {passed + failed + skipped}    Passed: {passed}    "
            f"Failed: {failed}" + (f"    Skipped: {skipped}" if skipped else "")
            + (f"    Leaks: {leaked}" if leaked else "")
            + (f"    Chunks died: {died}" if died else ""))


@dataclass(frozen=True)
class _Around:
    """What surrounds every file of a run: the program's hooks, the folders
    the run gave itself (environment variable → the key their files are
    compared under), and the whole allow-list of the leak check."""
    hooks: Hooks
    folders: Mapping[str, str]
    allowed: tuple


def _run_files(test_files, k, tally: _Tally, around: _Around, *,
               file_offset: int = 0, n_files: int | None = None,
               on_file=None) -> None:
    """Run ``test_files`` in order, counting into ``tally``.

    ``on_file(f, record)`` is called for every file that reached its end
    (not for one an interrupt cut short) with what it counted, its leaks,
    its failure details, its seconds and each test's: what a chunk reports
    to the run that started it, and what a serial run keeps as its durations.
    """
    from . import leaks

    n_files = n_files or len(test_files)
    for i_file, f in enumerate(test_files, 1):
        # Slip2D v0.1.302 (D310) — what the previous file left as cyclic
        # garbage is freed here, on the main thread, and not later by
        # whichever thread trips the collector (see Hooks for the program's
        # own part of it).
        if around.hooks.before_file is not None:
            around.hooks.before_file()
        gc.collect()
        # Slip2D v0.1.373 — and what survives is frozen, so the next
        # collections (this one, and the automatic ones on any thread) walk
        # only what was made since. Each full collection cost ~320 ns per
        # live object: 0.4 s per file at the start of Slip2D's suite, 3.4 s
        # at the end, 13.6 of 87.6 minutes (its audit of v0.1.372, §3).
        # Collected first, frozen after: the previous file's garbage is
        # still freed.
        gc.freeze()
        print(f"\n=== {f.name} ===  ({file_offset + i_file}/{n_files})")
        # Slip2D v0.1.373 — sys.path and the run's own folders are put back
        # after each file. There 242 files inserted tests/, which is already
        # sys.path[0], and nothing took it out: 369 entries at the end,
        # walked with one stat each by every import of every spawn worker (a
        # pool of 4 went from 0.5 s to 2.4-3.6 s, audit §4.3). Two runner
        # self-tests repoint the folders through a second main() (audit D-d).
        saved_path = list(sys.path)
        saved_folders = {v: os.environ.get(v) for v in around.folders}
        start = (tally.passed, tally.failed, tally.skipped,
                 len(tally.fail_details))
        before = leaks.snapshot(around.folders)
        test_times: dict = {}
        t0 = time.perf_counter()
        finished = False
        try:
            try:
                mod = _load_module(f)
            except Exception as e:  # noqa: BLE001
                print(f"  [LOAD ERROR] {e}")
                tally.fail_details.append((f.name, traceback.format_exc()))
                tally.failed += 1
                finished = True
                continue

            for name, cls in inspect.getmembers(mod, inspect.isclass):
                if not name.startswith("Test"):
                    continue
                if cls.__module__ != mod.__name__:
                    continue
                methods = [(m_name, m)
                           for m_name, m in inspect.getmembers(cls, inspect.isfunction)
                           if m_name.startswith("test_")
                           and match_test(name, m_name, k)]
                if not methods:
                    continue
                print(f"  {name}:")
                for m_name, m in methods:
                    t1 = time.perf_counter()
                    outcome, why, tb = run_test(cls, m)
                    test_times[node_id(f, name, m_name)] = round(
                        time.perf_counter() - t1, 3)
                    if outcome == "passed":
                        tally.passed += 1
                        print(f"    {tally.tag()} ✓ {m_name}")
                    elif outcome == "skipped":
                        tally.skipped += 1
                        print(f"    {tally.tag()} ○ {m_name} — skipped: {why}")
                    else:
                        tally.failed += 1
                        print(f"    {tally.tag()} ✗ {m_name}: {why}")
                        tally.fail_details.append((f"{name}.{m_name}", tb))
            finished = True
        finally:
            seconds = time.perf_counter() - t0
            # In place: whoever holds the sys.path list keeps the same one.
            sys.path[:] = saved_path
            for var, value in saved_folders.items():
                if value is None:
                    os.environ.pop(var, None)
                else:
                    os.environ[var] = value
            # Slip2D v0.1.374 — anything else the file left in the process
            # is named here, at the file that left it, and fails the run
            # (rule 5). Before, a leak showed only if a later test happened
            # to depend on it, and only in the full run. What is looked at
            # and what is allowed: ogr_core/testing/leaks.py.
            found = leaks.diff(before, leaks.snapshot(around.folders),
                               around.allowed)
            lines = [leaks.describe(*leak) for leak in found]
            if found:
                tally.leaked += 1
                for line in lines:
                    print(f"  ✗ [LEAK] {line}")
                tally.fail_details.append((f"{f.name} [LEAK]", "\n".join(lines)))
            if finished and on_file is not None:
                on_file(f, {"file": f.name,
                            "passed": tally.passed - start[0],
                            "failed": tally.failed - start[1],
                            "skipped": tally.skipped - start[2],
                            "leaks": lines,
                            "details": tally.fail_details[start[3]:],
                            "seconds": round(seconds, 3),
                            "tests": test_times})


def _run_chunk(spec_path: Path, around: _Around) -> int:
    """One chunk of ``--jobs`` (``--child SPEC``): the files of the spec, in
    its order, each written to the report as it ends. A chunk that dies
    leaves behind the files it finished, so the run that started it can say
    where it died; a chunk that ends writes ``{"end": true}`` last."""
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    tally = _Tally(spec["total"], spec["test_offset"])
    with open(spec["report"], "a", encoding="utf-8") as report:
        def on_file(_f, record):
            report.write(json.dumps(record) + "\n")
            report.flush()

        _run_files([Path(p) for p in spec["files"]], spec.get("k"), tally,
                   around, file_offset=spec["file_offset"],
                   n_files=spec["n_files"], on_file=on_file)
        report.write(json.dumps({"end": True}) + "\n")
    return 0 if tally.failed == 0 and tally.leaked == 0 else 1


def _follow(log: Path, proc) -> None:
    """Copy a chunk's output here as it is written, until the chunk ends.
    Bytes, decoded incrementally: a read can stop inside a character."""
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    with open(log, "rb") as fh:
        while True:
            data = fh.read(1 << 16)
            if data:
                sys.stdout.write(decoder.decode(data))
                sys.stdout.flush()
                continue
            if proc.poll() is not None:
                sys.stdout.write(decoder.decode(fh.read(), final=True))
                sys.stdout.flush()
                return
            time.sleep(0.2)


def _exit_code(code) -> str:
    # Windows gives an NTSTATUS as a large unsigned number: 3221226505 is
    # 0xC0000409, what abort() leaves.
    if code is None:
        return "none"
    if code < 0 or code > 255:
        return f"{code} (0x{code & 0xFFFFFFFF:08X})"
    return str(code)


def _jobs_plan(test_files, declared, jobs: int, durations: dict):
    """``(chunks, lane, weights, timed, counts)``: the contiguous chunks of
    the files not in the serial lane, the lane, each file's expected seconds
    by name, whether those come from measured durations, and each file's
    declared tests by name."""
    counts: dict = {}
    for f, _cls, _m in (declared or ()):
        counts[f.name] = counts.get(f.name, 0) + 1
    lane = [f for f in test_files if serial_lane(f)]
    rest = [f for f in test_files if f not in lane]
    weights = file_weights(rest, counts, durations)
    chunks = [rest[a:b] for a, b in partition(weights, jobs)]
    timed = any(f.name in durations for f in rest)
    return chunks, lane, dict(zip((f.name for f in rest), weights)), timed, counts


def _print_plan(chunks, lane, weights, timed, counts) -> None:
    n = len(chunks)
    print(f"PARALLEL RUN — {n} chunk(s) at once"
          + (f", then {len(lane)} file(s) alone (SERIAL_LANE)" if lane else ""))
    for i, chunk in enumerate(chunks, 1):
        tests = sum(counts.get(f.name, 0) for f in chunk)
        # Minutes only when they were measured; balanced by test count
        # otherwise, and a count is not a duration.
        cost = (f", ~{sum(weights[f.name] for f in chunk) / 60:.1f} min by "
                f"the last durations" if timed else ", balanced by test count")
        span = (chunk[0].stem if len(chunk) == 1
                else f"{chunk[0].stem} … {chunk[-1].stem}")
        print(f"  chunk {i}/{n}: {span}  ({len(chunk)} file(s), "
              f"{tests} tests{cost})")
    if lane:
        print("  alone:     " + ", ".join(f.stem for f in lane))


@dataclass(frozen=True)
class _Kept:
    """What a run keeps and says about the machine, resolved once."""
    records: Optional[Records]
    slow_list: Path
    slow_seconds: float
    serial_every: Optional[int]
    prog: str


def _run_jobs(tests_dir: Path, test_files, k, jobs: int, declared,
              banners, kept: _Kept, entry: Path, child_args: list,
              child_config: dict) -> int:
    """The selection in ``jobs`` processes at once, then the serial lane.

    The verdict is 0 only when every test passed, no file leaked, and the
    run is complete: every chunk wrote the end of every one of its files
    and its own end, exited with the code its results call for, and the
    tests run add up to the tests the source declares. A chunk that dies —
    an ``os._exit``, an abort, a crash in Qt — is a failure named with its
    exit code and the file it died in, never a shorter green run.

    ``banners`` are the lines a run that is not evidence for a release
    carries before and after its totals (``FILTERED RUN``, ``DEV CORE``).
    """
    records = kept.records
    durations = load_durations(records.durations if records else None)
    chunks, lane, weights, timed, counts = _jobs_plan(test_files, declared,
                                                      jobs, durations)
    total = len(declared) if declared is not None else 0
    plan = [(f"{i}/{len(chunks)}", c) for i, c in enumerate(chunks, 1)]
    if lane:
        plan.append(("serial lane", lane))
    for line in banners:
        print(line)
    _print_plan(chunks, lane, weights, timed, counts)

    work = Path(tempfile.mkdtemp(prefix="ogr_test_jobs_"))
    procs: list = []
    test_offset = file_offset = 0
    for i, (label, files) in enumerate(plan):
        spec = {"files": [str(f.resolve()) for f in files], "k": k,
                "total": total, "test_offset": test_offset,
                "file_offset": file_offset, "n_files": len(test_files),
                "report": str(work / f"report_{i}.jsonl"),
                # Read only by this module run as a script (a folder with no
                # runner of its own); a repository's runner has its own.
                "tests_dir": str(tests_dir.resolve()),
                "config": child_config}
        (work / f"spec_{i}.json").write_text(json.dumps(spec), encoding="utf-8")
        test_offset += sum(counts.get(f.name, 0) for f in files)
        file_offset += len(files)

    def start(i):
        # The console is inherited on purpose: without one a program may
        # send its own pools to pythonw.exe (OGR Slip2D does), and a chunk
        # would test something the serial run does not.
        with open(work / f"log_{i}.txt", "wb") as out:
            return subprocess.Popen(
                [sys.executable, "-u", str(entry), "--child",
                 str(work / f"spec_{i}.json"), *child_args],
                stdout=out, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL)

    n_parallel = len(chunks)
    try:
        procs = [start(i) for i in range(n_parallel)]
        for i in range(len(plan)):
            if i == n_parallel:
                # The lane starts once every chunk has ended: following them
                # in order, the last one followed was the last to matter.
                procs.append(start(i))
            _follow(work / f"log_{i}.txt", procs[i])
    except BaseException:
        for p in procs:
            if p.poll() is None:
                p.kill()
        raise

    passed = failed = skipped = leaked = 0
    details: list = []
    died: list = []
    times: dict = {}
    test_times: dict = {}
    for i, ((label, files), proc) in enumerate(zip(plan, procs)):
        try:
            records_read = [json.loads(line) for line in
                            (work / f"report_{i}.jsonl").read_text(
                                encoding="utf-8").splitlines() if line.strip()]
        except (OSError, ValueError):
            records_read = []
        done = [r for r in records_read if "file" in r]
        for r in done:
            passed += r["passed"]
            failed += r["failed"]
            skipped += r["skipped"]
            leaked += bool(r["leaks"])
            details += [tuple(d) for d in r["details"]]
            times[r["file"]] = r["seconds"]
            test_times.update(r.get("tests", {}))
        names = [f.name for f in files]
        names_done = [r["file"] for r in done]
        ended = any(r.get("end") for r in records_read)
        bad = any(r["failed"] or r["leaks"] for r in done)
        if not ended or names_done != names:
            where = (names[len(names_done)] if len(names_done) < len(names)
                     else "its end")
            after = names_done[-1] if names_done else "no file"
            died.append(f"chunk {label} died: exit {_exit_code(proc.returncode)}"
                        f" in {where}, after {after}; "
                        f"{len(names) - len(names_done)} of its {len(names)}"
                        f" file(s) did not finish (log: {work / f'log_{i}.txt'})")
        elif proc.returncode != (1 if bad else 0):
            died.append(f"chunk {label} ran its {len(names)} file(s) but "
                        f"exited {_exit_code(proc.returncode)} "
                        f"(log: {work / f'log_{i}.txt'})")
    ran = passed + failed + skipped
    if total and not died and ran != total:
        died.append(f"the source declares {total} test(s) and the chunks "
                    f"ran {ran}")

    print("\n" + "=" * 60)
    for line in died:
        print(f"✗ [CHUNK] {line}")
    print(_totals_line(passed, failed, skipped, leaked, len(died)))
    print(f"PARALLEL RUN — {len(chunks)} chunk(s)"
          + (" + serial lane" if lane else ""))
    for line in banners:
        print(line)
    if not banners:
        # Slip2D v0.1.376 — a whole run in chunks is what a release needs,
        # and once every ``serial_every`` commits the serial run too: said
        # with the numbers, where the release check reads them.
        if records is not None:
            _print_slow_unlisted(times, kept.slow_list, kept.slow_seconds)
        if kept.serial_every:
            print(serial_notice(tests_dir.parent,
                                records.serial if records else None,
                                kept.serial_every, kept.prog))
    if details or died:
        print("\n--- FAILURE DETAILS ---")
        for line in died:
            print(f"\n[CHUNK]\n{line}")
        for name, tb in details[:10]:
            print(f"\n[{name}]\n{tb}")

    if records is not None:
        if not k:
            save_durations(times, records.durations)
        save_durations(test_times, records.test_times)
    if not died:
        shutil.rmtree(work, ignore_errors=True)
    return 0 if failed == 0 and leaked == 0 and not died else 1


@_puts_back_dev_core
def main(tests_dir: Path, patterns=(), k: str | None = None,
         list_only: bool = False, *, jobs: int = 1,
         child: str | None = None, fast: bool = False,
         write_slow: float | None = None, dev_core: bool = False,
         own: Iterable[str] = (), shared: Iterable[str] = (),
         pinned: Optional[dict] = None, hooks: Optional[Hooks] = None,
         allowed: Iterable = (),
         run_folders: Optional[Mapping[str, str]] = None,
         label: Optional[str] = None, records: Optional[Records] = None,
         serial_every: Optional[int] = None,
         slow_list: Optional[Path] = None,
         slow_seconds: float = SLOW_SECONDS,
         entry: Optional[Path] = None,
         prog: str = "python tests/_runner.py") -> int:
    """Run the suite in ``tests_dir``; the exit code is the result.

    The selection: ``patterns``, ``k``, ``list_only``, ``fast``, and
    ``jobs`` processes at once. ``write_slow`` rewrites the slow list and
    runs nothing. ``child`` is how a run with ``jobs`` starts each chunk.

    What the repository says of itself, in its ``tests/_runner.py``:

    ``own`` are the packages it contains: each must resolve inside
    ``tests_dir.parent``. ``shared`` are the packages it takes from another
    tree (the core, for a program), and ``pinned`` maps each to the version
    it pins (:func:`pinned_from_pyproject`); ``dev_core`` accepts a
    development version of a later release instead (``--dev-core``), and so
    does a run started inside one that did (:func:`dev_core_run`).

    ``hooks`` — see :class:`Hooks`. ``allowed`` — the program's own entries
    of the leak check's allow-list, added to the suite's
    (:data:`ogr_core.testing.leaks.ALLOWED`). ``run_folders`` — the folders
    every run gives itself, as ``{environment variable: key}``: each is a
    fresh temporary folder, put back after every file, whose files are part
    of the leak check under that key. OGR Slip2D gives its runs a settings
    folder and a bridge folder this way, so that no test reads the user's
    preferences or finds the user's open window.

    ``label`` — the name the run's machine files are kept under
    (:func:`records_for`), or ``records`` to say the files themselves; with
    neither, nothing is kept. ``serial_every`` — the number of commits
    after which a whole run in chunks says ``SERIAL RUN DUE``; None for a
    repository with no such rule. ``slow_list`` — the list ``--fast`` reads,
    ``tests/_slow.txt`` by default, and ``slow_seconds`` its threshold.

    ``entry`` — the script each chunk of ``jobs`` is started with:
    ``tests_dir/_runner.py`` by default, so that every chunk gets the
    repository's own configuration, hooks included; this module itself for
    a folder that has no runner of its own.

    Exit 2 means nothing was run: a wrong tree, a wrong shared version, an
    option with nothing to do, or a selection that matches nothing.
    """
    # The ✓/✗ marks below are not printable in the console codepage Windows
    # picks when stdout is redirected (cp1252), and the UnicodeEncodeError
    # lands *inside* the except branch that reports a failure — so a single
    # unprintable character turns a full run into a traceback. Widening the
    # encoding here keeps `python tests/_runner.py > log.txt` usable.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # non-reconfigurable stream
        pass
    install_pytest_shim()
    # The temporary folder is settled here, before the first file, in the
    # run and in every chunk: ``tempfile`` works it out on its first use and
    # keeps the answer, and the leak check would name that at whichever file
    # happened to be first to make a temporary file (it did, in the chunks of
    # this repository's own suite). Slip2D's runner settled it without
    # meaning to, by naming its machine files at import. Settled first, a
    # file that MOVES it is still named.
    tempfile.gettempdir()
    hooks = hooks or Hooks()
    folders = dict(run_folders or {})
    pinned = dict(pinned or {})

    # Slip2D v0.1.207 and v0.1.289 (D290) — the folders a program's code
    # would otherwise find in the user's home (the discovery folder of an
    # open window, the saved language and theme) are, for the whole run and
    # its children, empty folders of its own.
    for var, key in folders.items():
        os.environ[var] = tempfile.mkdtemp(prefix=f"ogr_test_{key}_")

    # Before anything else: which trees is this about to measure? See
    # foreign_packages() for why a run that answers this wrongly is worse
    # than a run that fails.
    repo_root = tests_dir.parent
    origins = package_origins(own)
    strangers = foreign_packages(origins, repo_root)
    if strangers:
        print("WRONG TREE — this suite would not test the code you are "
              "editing.")
        for name, where in strangers:
            print(f"  {name} resolves to "
                  f"{where if where else '(not importable)'}")
        print(f"  this runner lives in {repo_root}")
        print("An ogr_* package resolving outside the runner's own "
              "repository usually means an editable install is answering "
              "the import. Put the tree first on sys.path, or reinstall, "
              "then run again.")
        return 2
    shared_origins = package_origins(shared)
    # v0.2.2 — a run started inside one that accepted a development version
    # accepts it too: it is a process of that run, started by one of its
    # tests, and nobody typed its command line.
    asked = dev_core
    dev_core = asked or dev_core_run()
    problems = shared_problems(shared_origins, pinned, dev_core)
    if problems:
        print("WRONG SHARED TREE — this suite would not test against the "
              "version it pins.")
        for p in problems:
            print(f"  {p}")
        print(f"  this runner lives in {repo_root}")
        print("Install the pinned version, or check out its tag in the "
              "editable tree, then run again.")
        return 2
    dev = shared_dev(shared_origins, pinned) if dev_core else []
    if asked and not dev:
        # Rule 7: an option that did nothing would read as a check passed.
        # Only the option: the variable is inherited, not typed, and a run
        # it finds nothing for is an ordinary run against the pinned core
        # (a test that runs a folder of its own inside a development run).
        print("--dev-core has nothing to accept: no shared package is at a "
              "development version of a release later than its pin.")
        return 2
    if dev:
        os.environ[DEV_CORE_ENV] = "1"
    dev_banner = [
        f"DEV CORE — {name} {have} runs in place of the pinned {want} — "
        f"NOT evidence for a release" for name, have, want in dev]
    if child is None:
        # A chunk of --jobs says nothing of its own: the run that started it
        # printed these lines, and prints the totals.
        print(provenance(repo_root, origins))
        for line in shared_provenance(shared_origins):
            print(line)
    if hooks.before_run is not None:
        hooks.before_run()

    from . import leaks
    around = _Around(hooks=hooks, folders=folders,
                     allowed=tuple(leaks.ALLOWED) + tuple(allowed))
    if child is not None:
        return _run_chunk(Path(child), around)

    if records is None and label:
        records = records_for(label)
    slow_list = slow_list or (tests_dir / SLOW_LIST_NAME)
    kept = _Kept(records=records, slow_list=slow_list,
                 slow_seconds=slow_seconds, serial_every=serial_every,
                 prog=prog)
    if jobs < 1:
        print(f"--jobs takes a number of processes, 1 or more; got {jobs}.")
        return 2
    if write_slow is not None:
        if patterns or k or fast:
            print("--write-slow-list writes the list of the whole folder; "
                  "it takes no patterns, -k or --fast.")
            return 2
        return write_slow_list(tests_dir, write_slow,
                               records.durations if records else None,
                               slow_list, prog)
    slow = frozenset()
    if fast:
        slow = load_slow_list(slow_list)
        if not slow:
            # Rule 7: a --fast that left nothing out would be a whole run
            # under a FILTERED banner, and a list that went missing would
            # never be noticed.
            print(f"--fast has nothing to leave out: tests/{slow_list.name} "
                  "is missing or empty. Write it with --write-slow-list "
                  "after a whole run.")
            return 2

    patterns = list(patterns)
    every = sorted(tests_dir.glob("test_*.py"))
    test_files = select_files(tests_dir, patterns)
    filtered = bool(patterns) or bool(k) or fast
    left_out = [f for f in test_files if f.name in slow]
    if fast:
        if test_files and len(left_out) == len(test_files):
            print(f"Every selected file is in tests/{slow_list.name}: "
                  "--fast leaves nothing to run.")
            return 2
        test_files = [f for f in test_files if f.name not in slow]

    def _banner() -> str:
        bits = []
        if patterns:
            bits.append(f"patterns: {patterns}")
        if k:
            bits.append(f"-k {k!r}")
        if fast:
            bits.append(f"--fast: {len(left_out)} slow file(s) left out "
                        f"(tests/{slow_list.name})")
        return (f"FILTERED RUN — {len(test_files)} of {len(every)} files"
                f", {', '.join(bits)} — NOT the full suite")

    if not test_files:
        print(f"No test file matches {patterns}.")
        near = _suggest(every, patterns)
        if near:
            print("Did you mean: " + ", ".join(near))
        print(f"{len(every)} files available — "
              f"`{prog} --list` shows them all.")
        return 2

    declared = _declared_tests(test_files, k)
    if k and declared is not None and not declared:
        print(f"No test name matches -k {k!r} "
              f"in the {len(test_files)} selected file(s):")
        for f in test_files:
            print(f"  {f.name}")
        print("`--list` without -k shows the test names available.")
        return 2

    if list_only:
        if declared is None:
            # Silence here would read as "this selection has no tests",
            # when what happened is that the source could not be parsed.
            print(f"Cannot list: one of the {len(test_files)} selected "
                  f"file(s) does not parse. Run them to see the error.")
            return 2
        for f, cls, m_name in declared:
            print(f"{f.name}::{cls}::{m_name}")
        print(f"\n{len(declared)} test(s) in {len(test_files)} file(s)"
              f" of {len(every)}. Nothing was run.")
        if jobs > 1:
            print()
            _print_plan(*_jobs_plan(
                test_files, declared, jobs,
                load_durations(records.durations if records else None)))
        return 0

    # The lines a run that is not evidence for a release carries before and
    # after its totals. Repeated after them on purpose: a green partial run
    # pasted into a changelog or a release check is indistinguishable from a
    # green full suite unless the line travels with the numbers.
    banners = ([_banner()] if filtered else []) + dev_banner

    if jobs > 1:
        if entry is None:
            own_runner = tests_dir / "_runner.py"
            entry = own_runner if own_runner.is_file() else Path(__file__)
        return _run_jobs(
            tests_dir, test_files, k, jobs, declared, banners, kept,
            Path(entry).resolve(), ["--dev-core"] if dev else [],
            {"own": list(own), "shared": list(shared), "pinned": pinned,
             "run_folders": folders})

    tally = _Tally(len(declared) if declared is not None else 0)
    for line in banners:
        print(line)
    times: dict = {}
    test_times: dict = {}

    def on_file(f, record):
        times[f.name] = record["seconds"]
        test_times.update(record["tests"])

    _run_files(test_files, k, tally, around, on_file=on_file)

    print("\n" + "=" * 60)
    print(_totals_line(tally.passed, tally.failed, tally.skipped,
                       tally.leaked))
    for line in banners:
        print(line)
    code = 0 if tally.failed == 0 and tally.leaked == 0 else 1
    if records is not None and not banners:
        _print_slow_unlisted(times, slow_list, slow_seconds)
        # Slip2D v0.1.376 — the serial run a release needs every
        # ``serial_every`` commits is remembered only when it is the whole
        # suite, against the pinned core, and green.
        sha = (record_serial_run(repo_root, tally.passed + tally.skipped,
                                 records.serial)
               if code == 0 and serial_every else None)
        if sha:
            print(f"full serial run recorded: {sha[:7]}; the next is due in "
                  f"{serial_every} commits")

    if tally.fail_details:
        print("\n--- FAILURE DETAILS ---")
        for name, tb in tally.fail_details[:10]:
            print(f"\n[{name}]\n{tb}")

    # Slip2D v0.1.375 — what each file took, for the chunks of a later
    # --jobs; not under -k (part of a file), nor for a run that keeps
    # nothing (the self-tests' throwaway files). Each test's own seconds are
    # right under any filter (v0.1.376).
    if records is not None:
        if not k:
            save_durations(times, records.durations)
        save_durations(test_times, records.test_times)
    return code


def _parse_args(argv, prog: str = "python tests/_runner.py"):
    p = argparse.ArgumentParser(
        prog=prog,
        description="Run the OGR test suite, or a selected part of it.",
        epilog="With no arguments it runs everything, which is what CI does.")
    p.add_argument(
        "patterns", nargs="*", metavar="PATTERN",
        help="run only files whose name contains this (case-insensitive). "
             "A path or a file name works too: `transient`, "
             "`test_transient_v130.py` and `tests/test_transient_v130.py` "
             "all select the same file.")
    p.add_argument(
        "-k", metavar="SUBSTRING", default=None,
        help="run only tests whose 'Class.method' contains this "
             "(case-insensitive substring; no and/or/not grammar).")
    p.add_argument(
        "--list", dest="list_only", action="store_true",
        help="print the selected tests and exit without running them "
             "(with --jobs, also the chunks it would run).")
    p.add_argument(
        "--jobs", "-j", type=int, default=1, metavar="N",
        help="run in N processes at once: contiguous chunks of the "
             "alphabetical order, balanced by the last durations, then the "
             "files marked SERIAL_LANE alone. A chunk that dies fails the "
             "run. Without it the run is serial, as in CI.")
    p.add_argument(
        "--fast", action="store_true",
        help=f"leave out the files listed in tests/{SLOW_LIST_NAME}; a "
             "filtered run, not evidence for a release.")
    p.add_argument(
        "--write-slow-list", dest="write_slow", type=float, nargs="?",
        const=SLOW_SECONDS, default=None, metavar="SECONDS",
        help=f"rewrite tests/{SLOW_LIST_NAME} with the test files that took "
             f"SECONDS or more (default {SLOW_SECONDS:g}) in their last "
             "whole run on this machine, and run nothing.")
    p.add_argument(
        "--dev-core", dest="dev_core", action="store_true",
        help="run against a shared package that is a development version "
             "(X.Y.Z.devN) of a release later than the pinned one; not "
             "evidence for a release, and the run says so. Its tests and "
             f"the runs they start see {DEV_CORE_ENV}=1.")
    # How a run with --jobs starts each chunk; not for typing.
    p.add_argument("--child", metavar="SPEC", default=None,
                   help=argparse.SUPPRESS)
    return p.parse_args(argv)


def cli(tests_dir: Path, argv=None, **config) -> int:
    """The command line of a repository's ``tests/_runner.py``.

    ``config`` is passed to :func:`main` as is: what the repository says of
    itself (``own``, ``shared``, ``pinned``, ``hooks``, ``allowed``,
    ``run_folders``, ``label``, ``serial_every``, ``prog``). The caller ends
    the process with what this returns: ``sys.exit(runner.cli(...))``.
    """
    ns = _parse_args(sys.argv[1:] if argv is None else argv,
                     config.get("prog", "python tests/_runner.py"))
    code = main(tests_dir, patterns=ns.patterns, k=ns.k,
                list_only=ns.list_only, jobs=ns.jobs, child=ns.child,
                fast=ns.fast, write_slow=ns.write_slow,
                dev_core=ns.dev_core, **config)
    # Slip2D v0.1.377 — everything a run leaves (totals, durations, the
    # serial record, a chunk's report) is written inside main(); only the
    # streams remain, and they are emptied here so that no ending can lose
    # them.
    sys.stdout.flush()
    sys.stderr.flush()
    # Slip2D v0.1.422 (D370) — what the program must undo with Python still
    # alive goes first (see Hooks), and the process then ends through the
    # interpreter's own shutdown on every platform, so a crash in it shows.
    # From v0.1.377 to v0.1.421 the runner hid that crash off Windows with
    # os._exit; its owner's decision of 2026-11-04 took that out, once the
    # cause was gone. This runner never ends the process itself.
    after = getattr(config.get("hooks"), "after_run", None)
    if after is not None:
        after()
    return code


def _child_of_a_bare_folder(argv) -> int:
    """A chunk of ``--jobs`` for a folder with no runner of its own: the
    spec names the folder and the plain part of its configuration."""
    ns = _parse_args(argv)
    if ns.child is None:
        print("This module is the suite's test runner, and is run through "
              "a repository's own script: `python tests/_runner.py`.")
        return 2
    spec = json.loads(Path(ns.child).read_text(encoding="utf-8"))
    return cli(Path(spec["tests_dir"]), argv, **spec.get("config", {}))


if __name__ == "__main__":
    # Started by path by _run_jobs: sys.path[0] is this folder, whose
    # modules would then answer to ``runner`` and ``leaks`` for any test
    # that imports those names. The tree this file belongs to goes there
    # instead, and the chunk runs in the module imported by its real name —
    # the same one the run that started it uses.
    sys.path[0] = str(Path(__file__).resolve().parents[2])
    from ogr_core.testing import runner as _runner
    sys.exit(_runner._child_of_a_bare_folder(sys.argv[1:]))
