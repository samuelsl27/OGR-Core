# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.9 — the workspace of ``ogr_core.api``: models by handle, a lock per
model, an edit as one undo step, whatever the model is.

From OGR Slip2D's ``ogr_api/workspace.py`` (v0.1.486), which was written
for the core's limit-equilibrium ``Project``. Invariants:

* **with the defaults it is Slip2D's**: an edit of a ``Project`` is one
  step of its stack (the core's ``SnapshotCommand``), all or nothing; an
  edit that changes nothing leaves no step; an edit inside another edit of
  the same model is part of the outer step; "unsaved" is the hash of
  ``to_dict()``;
* **each hook moves the outcome** (rule 7): a program's ``undo_step`` is
  the command that runs, its ``document_hash`` what "unsaved" compares, its
  ``WorkspaceNames`` what the hints name, its ``jobs_options`` what the job
  manager gets — on a model that is not a ``Project`` at all;
* a model is found by handle, or alone; several or none say so; a model
  held by another caller answers ``Busy`` after the lock's timeout;
* a window's model (a ``provider``) gives its own file and dirtiness, and
  when the window swaps it, what belonged to the old one goes;
* a relative path needs a ``workdir``; a write never replaces a file
  unless asked, except the model's own.
"""
from __future__ import annotations

import shutil
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path


def _refused(cls, fn):
    try:
        fn()
    except cls as exc:
        return exc
    raise AssertionError(f"{cls.__name__} was not raised")


class TestWithTheDefaults:
    def _ws(self):
        from ogr_core.api import Workspace
        from ogr_core.project import Project
        ws = Workspace()
        return ws, ws.add(Project("A"))

    def test_an_edit_is_one_undo_step(self):
        ws, h = self._ws()

        def rename(p):
            p.name = "B"
            return "renamed"

        assert ws.mutate(h.id, "Rename", rename) == "renamed"
        assert h.project.name == "B" and h.stack.can_undo
        h.stack.undo(h.project)
        assert h.project.name == "A"

    def test_a_failed_edit_leaves_nothing(self):
        ws, h = self._ws()

        def broken(p):
            p.name = "half"
            raise RuntimeError("stop")

        _refused(RuntimeError, lambda: ws.mutate(h.id, "Broken", broken))
        assert h.project.name == "A" and not h.stack.can_undo
        assert h.busy_with is None

    def test_an_edit_that_changes_nothing_leaves_no_step(self):
        ws, h = self._ws()
        assert ws.mutate(h.id, "Nothing", lambda p: 5) == 5
        assert not h.stack.can_undo

    def test_an_edit_inside_an_edit_is_part_of_it(self):
        ws, h = self._ws()

        def outer(p):
            p.name = "B"
            ws.mutate(h.id, "Inner", lambda q: setattr(q, "name", "C"))

        ws.mutate(h.id, "Outer", outer)
        assert h.project.name == "C"
        h.stack.undo(h.project)
        assert h.project.name == "A" and not h.stack.can_undo

    def test_unsaved_is_the_hash_of_to_dict(self):
        from ogr_core.api import Workspace
        from ogr_core.project import Project
        ws = Workspace()
        h = ws.add(Project("A"), path=Path("a.ogr"))
        assert not h.unsaved()
        ws.mutate(h.id, "Rename", lambda p: setattr(p, "name", "B"))
        assert h.unsaved()


@dataclass
class Doc:
    """A model that is not a ``Project``: no ``to_dict``."""
    name: str = "doc"
    values: list = field(default_factory=list)


class _Append:
    """A program's own undo step: append, and pop to undo."""

    log: list = []

    def __init__(self, description, fn, attrs):
        self.description, self.fn = description, fn
        self.result, self.changed = None, False
        _Append.log.append(description)

    def execute(self, doc):
        n = len(doc.values)
        self.result = self.fn(doc)
        self.changed = len(doc.values) != n

    def undo(self, doc):
        doc.values.pop()


class TestTheHooks:
    def test_undo_step_and_document_hash(self):
        from ogr_core.api import Workspace
        _Append.log = []
        ws = Workspace(undo_step=_Append,
                       document_hash=lambda d: repr(d.values))
        h = ws.add(Doc(), path=Path("d.doc"))
        assert not h.unsaved()
        ws.mutate(h.id, "Add one", lambda d: d.values.append(1))
        assert _Append.log == ["Add one"]
        assert h.unsaved() and h.stack.can_undo
        h.stack.undo(h.project)
        assert h.project.values == [] and not h.unsaved()

    def test_without_them_such_a_model_cannot_be_edited(self):
        # rule 7: the default step snapshots ``Project`` attributes, which
        # a ``Doc`` does not have; the hook is what makes it work
        from ogr_core.api import Workspace
        ws = Workspace()
        h = ws.add(Doc())
        _refused(AttributeError,
                 lambda: ws.mutate(h.id, "Add", lambda d: d.values.append(1)))
        _refused(AttributeError, lambda: ws.add(Doc(), path=Path("x")))

    def test_the_names_a_hint_gives(self):
        from ogr_core.api import NotFound, Workspace, WorkspaceNames
        err = _refused(NotFound, lambda: Workspace().get())
        assert err.message == "No model is open."
        assert err.hint == "Call project_new or project_open first."
        ws = Workspace(names=WorkspaceNames("model_new", "model_open"))
        err = _refused(NotFound, lambda: ws.get())
        assert err.hint == "Call model_new or model_open first."

    def test_jobs_options_reach_the_manager(self):
        from ogr_core.api import Workspace
        ws = Workspace(jobs_options={"target": "m:f", "wait_op": "w"})
        try:
            assert ws.jobs.target == "m:f" and ws.jobs.wait_op == "w"
        finally:
            ws.shutdown()
        plain = Workspace()
        try:
            assert plain.jobs.target is None
            assert plain.jobs.wait_op == "job_get"
        finally:
            plain.shutdown()


class TestHandles:
    def test_alone_several_and_unknown(self):
        from ogr_core.api import InvalidArgument, NotFound, Workspace
        ws = Workspace(undo_step=_Append, document_hash=repr)
        a = ws.add(Doc("first"))
        assert ws.get() is a and ws.get("") is a
        b = ws.add(Doc("second"))
        err = _refused(InvalidArgument, lambda: ws.get())
        assert err.message == ("Several models are open; say which one with "
                               "project_id.")
        assert err.hint == f"Open: {a.id} (first), {b.id} (second)"
        err = _refused(NotFound, lambda: ws.get("p_nope"))
        assert err.message == "Unknown project_id 'p_nope'."
        ws.close(a.id)
        assert ws.get() is b

    def test_a_model_held_elsewhere_is_busy(self):
        from ogr_core.api import Busy, Workspace
        from ogr_core.api import workspace as wsmod
        ws = Workspace(undo_step=_Append, document_hash=repr)
        h = ws.add(Doc())
        inside, release = threading.Event(), threading.Event()

        def hold():
            with ws.reading(h.id, "a long read"):
                inside.set()
                release.wait(10)

        t = threading.Thread(target=hold, daemon=True)
        old = wsmod.LOCK_TIMEOUT_S
        wsmod.LOCK_TIMEOUT_S = 0.2
        try:
            t.start()
            assert inside.wait(5)
            err = _refused(Busy, lambda: ws.mutate(
                h.id, "Add", lambda d: d.values.append(1)))
            assert err.message.startswith(
                f"Model {h.id} is busy with a long read (")
            assert err.hint == "Retry when it finishes."
            assert err.message.code == "api.model.busy"
        finally:
            wsmod.LOCK_TIMEOUT_S = old
            release.set()
            t.join(5)

    def test_a_busy_window_refuses_an_edit_and_a_done_one_redraws(self):
        from ogr_core.api import Busy, Workspace
        drawn = []

        class Host:
            why = "The window is computing."

            def busy(self):
                return self.why

            def after_edit(self):
                drawn.append(1)

        ws = Workspace(undo_step=_Append, document_hash=repr)
        ws.host = Host()
        h = ws.add(Doc())
        err = _refused(Busy, lambda: ws.mutate(
            h.id, "Add", lambda d: d.values.append(1)))
        assert str(err) == ("[E_BUSY] The window is computing. Hint: Retry "
                            "when the window has finished.")
        ws.host.why = None
        ws.mutate(h.id, "Add", lambda d: d.values.append(1))
        assert drawn == [1]


class TestAWindowsModel:
    def test_file_dirtiness_and_a_swap(self):
        from ogr_core.api import Workspace

        class WinDoc(Doc):
            pass

        first, second = WinDoc("one"), WinDoc("two")
        first.file_path, first.is_dirty = Path("one.doc"), True
        second.file_path, second.is_dirty = Path("two.doc"), False
        current = [first]
        ws = Workspace(undo_step=_Append, document_hash=repr)
        h = ws.add(provider=lambda: current[0])
        assert h.path == Path("one.doc") and h.unsaved()
        evicted = []
        ws.store_result(h, "calc", {"s": 1}, model_hash="x",
                        payload={"p": 1}, on_evict=lambda: evicted.append(1))
        h.exec_ns["x"] = 1
        current[0] = second
        assert h.project is second
        assert h.path == Path("two.doc") and not h.unsaved()
        assert h.results == {} and h.exec_ns == {} and evicted == [1]
        h.path = Path("elsewhere")          # ignored for a window's model
        assert h.path == Path("two.doc")


class TestResults:
    def test_the_oldest_is_evicted_and_an_unknown_one_named(self):
        from ogr_core.api import NotFound, Workspace
        ws = Workspace(undo_step=_Append, document_hash=repr,
                       max_results_per_project=2)
        h = ws.add(Doc())
        loads = []
        r1 = ws.store_result(h, "c", {}, model_hash="x",
                             loader=lambda: loads.append(1) or {"v": 1})
        assert r1.payload() == {"v": 1} and r1.payload() == {"v": 1}
        assert loads == [1]
        r2 = ws.store_result(h, "c", {}, model_hash="x")
        r3 = ws.store_result(h, "c", {}, model_hash="x")
        assert list(h.results) == [r2.id, r3.id]
        assert ws.find_result(r3.id) == (h, r3)
        err = _refused(NotFound, lambda: ws.find_result(r1.id))
        assert err.message == f"Unknown result_id '{r1.id}'."


class TestPaths:
    def test_relative_needs_a_workdir_and_a_write_never_replaces(self):
        from ogr_core.api import Conflict, InvalidArgument, NotFound, Workspace
        folder = Path(tempfile.mkdtemp(prefix="ogr_ws_paths_"))
        try:
            err = _refused(InvalidArgument,
                           lambda: Workspace().resolve_path("a.doc"))
            assert err.message == ("'a.doc' is a relative path and no "
                                   "working directory was configured.")
            assert err.hint == ("Pass an absolute path, or start the server "
                                "with --workdir.")
            ws = Workspace(workdir=folder)
            target = ws.resolve_path("a", for_write=True, suffix=".doc")
            assert target == (folder / "a.doc").resolve()
            target.write_text("x", encoding="utf-8")
            err = _refused(Conflict, lambda: ws.resolve_path(
                "a.doc", for_write=True))
            assert err.hint == "Pass overwrite=true to replace it."
            assert ws.resolve_path("a.doc", for_write=True,
                                   own_file=target) == target
            assert ws.resolve_path("a.doc", for_write=True,
                                   overwrite=True) == target
            assert ws.resolve_path("a.doc") == target
            _refused(NotFound, lambda: ws.resolve_path("b.doc"))
            err = _refused(InvalidArgument,
                           lambda: ws.resolve_path("a.txt", suffix=".doc"))
            assert err.message == "'a.txt' does not end in .doc."
            _refused(InvalidArgument, lambda: ws.resolve_path("  "))
            _refused(InvalidArgument, lambda: ws.resolve_path(
                "nofolder/a.doc", for_write=True))
        finally:
            shutil.rmtree(folder, ignore_errors=True)
