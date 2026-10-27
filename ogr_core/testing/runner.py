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
takes SHARED from another tree and at what version, and calls :func:`cli`.

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
"""
from __future__ import annotations

import argparse
import ast
import gc
import importlib.util
import inspect
import math
import re
import sys
import tempfile
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional


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
    """What a program adds to a run, called by :func:`main`.

    ``before_run`` is called once, after the trees have been checked and
    before anything is selected or loaded: it imports from the tree just
    checked, which is why it cannot run earlier. ``before_file`` is called
    before each file, ahead of the runner's own ``gc.collect()``.

    OGR Slip2D's interface uses both for ``gc_guard`` (v0.1.302: cyclic
    garbage holding Qt objects is freed on the main thread, not by whichever
    thread trips the collector), and ``before_run`` also gives the run its
    own bridge and settings folders. The core has no Qt and needs neither,
    which is why they are hooks and not imports: this module cannot import
    ``ogr_gui`` (``AGENTS.md``, layers).
    """
    before_run: Optional[Callable[[], None]] = None
    before_file: Optional[Callable[[], None]] = None


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


def shared_problems(origins: dict, pinned: dict) -> list:
    """Why the shared packages cannot be measured, as sentences; empty when
    they can.

    A shared package that does not resolve is a problem — the tests are
    about to import it and fail one by one instead. One whose declared
    version is not the pinned one is a problem too: the program would be
    tested against a core it does not say it supports.
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
        if have != want:
            problems.append(
                f"{name} {have or '(no __version__)'} resolves to {where}, "
                f"but this repository pins {want}")
    return problems


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
                if (isinstance(m, ast.FunctionDef)
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


def main(tests_dir: Path, patterns=(), k: str | None = None,
         list_only: bool = False, *, own: Iterable[str] = (),
         shared: Iterable[str] = (), pinned: Optional[dict] = None,
         hooks: Optional[Hooks] = None,
         prog: str = "python tests/_runner.py") -> int:
    """Run the suite in ``tests_dir``; the exit code is the result.

    ``own`` are the packages this repository contains: each must resolve
    inside ``tests_dir.parent``. ``shared`` are the packages it takes from
    another tree (the core, for a program), and ``pinned`` maps each to the
    version the repository pins (:func:`pinned_from_pyproject`). Exit 2
    means nothing was run: a wrong tree, a wrong shared version, or a
    selection that matches nothing.
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
    hooks = hooks or Hooks()

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
    problems = shared_problems(shared_origins, pinned or {})
    if problems:
        print("WRONG SHARED TREE — this suite would not test against the "
              "version it pins.")
        for p in problems:
            print(f"  {p}")
        print(f"  this runner lives in {repo_root}")
        print("Install the pinned version, or check out its tag in the "
              "editable tree, then run again.")
        return 2
    print(provenance(repo_root, origins))
    for line in shared_provenance(shared_origins):
        print(line)
    if hooks.before_run is not None:
        hooks.before_run()

    patterns = list(patterns)
    every = sorted(tests_dir.glob("test_*.py"))
    test_files = select_files(tests_dir, patterns)
    filtered = bool(patterns) or bool(k)

    def _banner() -> str:
        bits = []
        if patterns:
            bits.append(f"patterns: {patterns}")
        if k:
            bits.append(f"-k {k!r}")
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
        return 0

    passed = 0
    failed = 0
    skipped = 0
    fail_details: list[tuple[str, str]] = []

    total_tests = len(declared) if declared is not None else 0
    n_files = len(test_files)
    # Fixed width, so the pass/fail marks stay in one column and the
    # output is still readable when it scrolls.
    w = len(str(total_tests)) if total_tests else 4

    def _tag() -> str:
        done = passed + failed + skipped
        if not total_tests:
            return f"[{done:>{w}}]"
        return f"[{done:>{w}}/{total_tests} {100.0 * done / total_tests:3.0f}%]"

    if filtered:
        print(_banner())

    for i_file, f in enumerate(test_files, 1):
        # What the previous file left as cyclic garbage is freed here, on
        # the main thread (see Hooks for the program's own part of it).
        if hooks.before_file is not None:
            hooks.before_file()
        gc.collect()
        print(f"\n=== {f.name} ===  ({i_file}/{n_files})")
        try:
            mod = _load_module(f)
        except Exception as e:  # noqa: BLE001
            print(f"  [LOAD ERROR] {e}")
            fail_details.append((f.name, traceback.format_exc()))
            failed += 1
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
                outcome, why, tb = run_test(cls, m)
                if outcome == "passed":
                    passed += 1
                    print(f"    {_tag()} ✓ {m_name}")
                elif outcome == "skipped":
                    skipped += 1
                    print(f"    {_tag()} ○ {m_name} — skipped: {why}")
                else:
                    failed += 1
                    print(f"    {_tag()} ✗ {m_name}: {why}")
                    fail_details.append((f"{name}.{m_name}", tb))

    print("\n" + "=" * 60)
    # A skip is counted apart and named: it is neither a pass (it measured
    # nothing) nor a failure (nothing was wrong). Absent when there is none,
    # so a run without skips prints exactly what it always printed.
    print(f"Total: {passed + failed + skipped}    Passed: {passed}    "
          f"Failed: {failed}" + (f"    Skipped: {skipped}" if skipped else ""))
    # Repeated after the totals on purpose: a green partial run pasted
    # into a changelog or a release check is indistinguishable from a
    # green full suite unless the line travels with the numbers.
    if filtered:
        print(_banner())

    if fail_details:
        print("\n--- FAILURE DETAILS ---")
        for name, tb in fail_details[:10]:
            print(f"\n[{name}]\n{tb}")

    return 0 if failed == 0 else 1


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
        help="print the selected tests and exit without running them.")
    return p.parse_args(argv)


def cli(tests_dir: Path, argv=None, **config) -> int:
    """The command line of a repository's ``tests/_runner.py``.

    ``config`` is passed to :func:`main` as is (``own``, ``shared``,
    ``pinned``, ``hooks``, ``prog``).
    """
    ns = _parse_args(sys.argv[1:] if argv is None else argv,
                     config.get("prog", "python tests/_runner.py"))
    return main(tests_dir, patterns=ns.patterns, k=ns.k,
                list_only=ns.list_only, **config)
