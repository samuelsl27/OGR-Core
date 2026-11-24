# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
The models a caller has open, by handle.

A caller never holds a model: it holds a ``project_id``, a handle this
workspace resolves. A handle may hold the model itself or a ``provider``
that returns the window's current one (the live bridge), because a window
replaces its model on New and Open and a stored reference would go on
editing the old one.

* every read or edit of a model happens under that model's lock;
* :meth:`Workspace.mutate` runs an edit as ONE undo step, all or nothing;
  a nested mutation of the same model (an operation called from a script
  inside another) is part of the outer step;
* results are kept per model under a ``result_id``, the oldest evicted;
* :meth:`Workspace.resolve_path` makes a relative path mean the
  ``workdir``, and never writes over a file unless asked.

From OGR Slip2D's ``ogr_api/workspace.py`` (v0.1.486). What v0.2.9 changes,
so that a model need not be the core's limit-equilibrium ``Project``:

* **the undo step is the program's** (``undo_step(description, fn,
  attrs)``, returning a command with ``execute(model)``, ``changed`` and
  ``result``); by default the core's ``SnapshotCommand`` over
  ``LIGHT_ATTRS``, which is what Slip2D used;
* **the hash that says "unsaved"** is the program's too
  (``document_hash(model)``); by default the SHA-256 of
  ``model.to_dict()``, Slip2D's ``ogr_api.snapshot.document_hash``;
* **the operations a hint names** (``WorkspaceNames``) and the options of
  the job manager (``jobs_options``) are arguments;
* its sentences are coded (``ogr_core.api.messages``).

A model is read duck-typed: ``name`` for a listing, and for a window's
model ``file_path`` and ``is_dirty``.

Author: Samuel Sáez López (UPCT)
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ..messages import as_nested
from .errors import Busy, Conflict, InvalidArgument, NotFound, unknown
from .messages import part, say

LOCK_TIMEOUT_S = 30.0


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def default_document_hash(model) -> str:
    """SHA-256 of the WHOLE serialised model (``model.to_dict()``).

    What "unsaved changes" means. Slip2D v0.1.203: a flag set by every
    notification could not answer it, because saving notified too."""
    text = json.dumps(model.to_dict(), sort_keys=True, default=str,
                      ensure_ascii=True)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def default_undo_step(description, fn: Callable, attrs=None):
    """The core's snapshot of the ``Project`` attributes ``attrs`` (by
    default ``LIGHT_ATTRS``) around ``fn``: atomic, and one undo step."""
    from ..project.commands import LIGHT_ATTRS, SnapshotCommand

    return SnapshotCommand(description, fn, attrs=attrs or LIGHT_ATTRS)


@dataclass(frozen=True)
class WorkspaceNames:
    """The operations a workspace's hints tell an agent to call."""
    new_op: str = "project_new"
    open_op: str = "project_open"


class StoredResult:
    """One computation kept for later questions.

    ``summary`` is always in memory; the full result is loaded only when a
    question needs it, from ``loader``.
    """

    def __init__(self, result_id: str, kind: str, project_id: str,
                 model_hash: str, summary: dict,
                 loader: Optional[Callable[[], dict]] = None,
                 payload: Optional[dict] = None,
                 on_evict: Optional[Callable[[], None]] = None) -> None:
        self.id = result_id
        self.kind = kind
        self.project_id = project_id
        self.model_hash = model_hash
        self.summary = summary
        self.created = time.time()
        self._loader = loader
        self._payload = payload
        self._on_evict = on_evict

    def payload(self) -> dict:
        if self._payload is None and self._loader is not None:
            self._payload = self._loader()
        return self._payload or {}

    def evict(self) -> None:
        self._payload = None
        if self._on_evict is not None:
            try:
                self._on_evict()
            except OSError:
                pass


class ProjectHandle:
    """One open model."""

    def __init__(self, handle_id: str, project=None,
                 provider: Optional[Callable] = None,
                 path: Optional[Path] = None,
                 document_hash: Callable = default_document_hash) -> None:
        from ..project.commands import CommandStack

        self.id = handle_id
        self._project = project
        self._provider = provider
        self._path = path
        self._hash = document_hash
        #: The model the provider gave last (Slip2D v0.1.203): when the
        #: window swaps its model, what belonged to the old one goes.
        self._seen = None
        self.lock = threading.RLock()
        self.stack = CommandStack()
        self.results: "OrderedDict[str, StoredResult]" = OrderedDict()
        #: Persistent namespace of a scripting operation for this model.
        self.exec_ns: dict = {}
        #: Hash of the model as last opened or saved, for "unsaved changes".
        self.saved_hash: Optional[str] = None
        self.busy_with = None
        self.busy_since: float = 0.0

    @property
    def project(self):
        if self._provider is None:
            return self._project
        p = self._provider()
        if p is not self._seen:
            # Slip2D v0.1.203 — the window opened or created another model:
            # the results and the script namespace were the old one's.
            if self._seen is not None:
                for res in self.results.values():
                    res.evict()
                self.results.clear()
                self.exec_ns.clear()
            self._seen = p
        return p

    @property
    def path(self):
        """The model's file. For a provider's model (the live window) it
        is the model's own ``file_path``: a path stored at ``add`` would
        outlive the window opening another file, and a save would have
        written the new model over the old file (Slip2D v0.1.203)."""
        if self._provider is not None:
            return getattr(self.project, "file_path", None)
        return self._path

    @path.setter
    def path(self, value) -> None:
        if self._provider is None:
            self._path = value

    def document_hash(self) -> str:
        return self._hash(self.project)

    def unsaved(self) -> bool:
        """Whether the model has changes that are not in its file."""
        if self._provider is not None:
            return bool(getattr(self.project, "is_dirty", False))
        return self.saved_hash != self.document_hash()


class Workspace:
    """Every model a caller has open, plus the job manager.

    ``workdir`` anchors relative paths; without one a relative path is an
    error, because a client such as a desktop chat application starts the
    server in a directory the user never chose.
    """

    def __init__(self, *, workdir: Optional[str | Path] = None,
                 jobs_root: Optional[str | Path] = None,
                 max_concurrent_jobs: int = 1,
                 max_results_per_project: int = 5,
                 jobs_options: Optional[dict] = None,
                 undo_step: Callable = default_undo_step,
                 document_hash: Callable = default_document_hash,
                 names: WorkspaceNames = WorkspaceNames()) -> None:
        self.workdir = Path(workdir).expanduser().resolve() if workdir \
            else None
        self.projects: "OrderedDict[str, ProjectHandle]" = OrderedDict()
        #: The window, when this workspace serves the live bridge: what an
        #: edit must wait for (``busy()``) and what to redraw
        #: (``after_edit()``).
        self.host = None
        self.max_results_per_project = int(max_results_per_project)
        self.undo_step = undo_step
        self.document_hash = document_hash
        self.names = names
        self._jobs_root = jobs_root
        self._max_jobs = int(max_concurrent_jobs)
        self._jobs_options = dict(jobs_options or {})
        self._jobs = None
        self._registry_lock = threading.Lock()
        # Per thread, the handles currently inside a mutation: a nested
        # mutation of the same model (an operation called from a script)
        # is part of the outer undo step.
        self._local = threading.local()

    # ------------------------------------------------------------------
    @property
    def jobs(self):
        if self._jobs is None:
            from .jobs import JobManager
            self._jobs = JobManager(root=self._jobs_root,
                                    max_concurrent=self._max_jobs,
                                    **self._jobs_options)
        return self._jobs

    def shutdown(self) -> None:
        """Kill running jobs and remove their files."""
        if self._jobs is not None:
            self._jobs.shutdown()

    # ------------------------------------------------------------------
    def add(self, project=None, *, provider=None,
            path: Optional[Path] = None) -> ProjectHandle:
        handle = ProjectHandle(_new_id("p"), project=project,
                               provider=provider, path=path,
                               document_hash=self.document_hash)
        with self._registry_lock:
            self.projects[handle.id] = handle
        handle.saved_hash = handle.document_hash() if path else None
        return handle

    def get(self, project_id: Optional[str] = None) -> ProjectHandle:
        """The handle for ``project_id``; with None, the only open model."""
        if project_id is None or project_id == "":
            if len(self.projects) == 1:
                return next(iter(self.projects.values()))
            if not self.projects:
                raise NotFound(say("api.model.none_open"),
                               hint=say("api.model.none_open.hint",
                                        new_op=self.names.new_op,
                                        open_op=self.names.open_op))
            raise InvalidArgument(
                say("api.model.several"),
                hint=say("api.model.several.hint", models=", ".join(
                    f"{h.id} ({getattr(h.project, 'name', '')})"
                    for h in self.projects.values())))
        handle = self.projects.get(project_id)
        if handle is None:
            raise unknown("project_id", project_id, list(self.projects))
        return handle

    def close(self, project_id: str) -> ProjectHandle:
        handle = self.get(project_id)
        with self._registry_lock:
            self.projects.pop(handle.id, None)
        for res in handle.results.values():
            res.evict()
        return handle

    # ------------------------------------------------------------------
    @contextlib.contextmanager
    def _locked(self, handle: ProjectHandle, what):
        if not handle.lock.acquire(timeout=LOCK_TIMEOUT_S):
            since = time.time() - handle.busy_since
            doing = (as_nested(handle.busy_with) if handle.busy_with
                     else part("api.model.another_operation"))
            raise Busy(say("api.model.busy", model=handle.id, what=doing,
                           since=since),
                       hint=say("api.retry"))
        outer = handle.busy_with is None
        if outer:
            handle.busy_with, handle.busy_since = what, time.time()
        try:
            yield handle.project
        finally:
            if outer:
                handle.busy_with = None
            handle.lock.release()

    @contextlib.contextmanager
    def reading(self, project_id: Optional[str], what=None):
        """The model, under its lock, for the duration of the block."""
        handle = self.get(project_id)
        with self._locked(handle, what or say("api.model.read")) as project:
            yield project

    def mutate(self, project_id: Optional[str], description: str,
               fn: Callable, attrs=None):
        """Run ``fn(model)`` as ONE undoable, all-or-nothing edit.

        Returns what ``fn`` returned. An edit that changes nothing leaves no
        undo step. Called from inside another mutation of the same model
        (a script calling an operation), it simply runs: the outer edit is
        the undo step.
        """
        handle = self.get(project_id)
        active = getattr(self._local, "active", None)
        if active is None:
            active = self._local.active = set()
        if self.host is not None and handle.id not in active:
            why = self.host.busy()
            if why:
                raise Busy(why, hint=say("api.retry.window"))
        with self._locked(handle, description) as project:
            if handle.id in active:
                return fn(project)
            active.add(handle.id)
            try:
                cmd = self.undo_step(description, fn, attrs)
                cmd.execute(project)
                if cmd.changed:
                    handle.stack.record(cmd)
                    if self.host is not None:
                        self.host.after_edit()
                return cmd.result
            finally:
                active.discard(handle.id)

    # ------------------------------------------------------------------
    def resolve_path(self, path: str, *, for_write: bool = False,
                     overwrite: bool = False,
                     suffix: Optional[str] = None,
                     own_file: Optional[Path] = None) -> Path:
        """An absolute path, checked for what the caller is about to do.

        Relative paths need a ``workdir``. Writing never replaces an
        existing file unless ``overwrite`` is true — except the model's
        own file, which is what "save" means.
        """
        if not isinstance(path, str) or not path.strip():
            raise InvalidArgument(say("api.path.empty"))
        p = Path(path.strip()).expanduser()
        if suffix and p.suffix.lower() != suffix:
            if p.suffix:
                raise InvalidArgument(say("api.path.suffix", name=p.name,
                                          suffix=suffix))
            p = p.with_suffix(suffix)
        if not p.is_absolute():
            if self.workdir is None:
                raise InvalidArgument(say("api.path.relative", path=path),
                                      hint=say("api.path.relative.hint"))
            p = self.workdir / p
        p = p.resolve()
        if for_write:
            if not p.parent.is_dir():
                raise InvalidArgument(say("api.path.no_folder",
                                          folder=str(p.parent)))
            same = own_file is not None and Path(own_file).resolve() == p
            if p.exists() and not overwrite and not same:
                raise Conflict(say("api.path.exists", path=str(p)),
                               hint=say("api.path.exists.hint"))
        elif not p.exists():
            raise NotFound(say("api.path.missing", path=str(p)))
        return p

    # ------------------------------------------------------------------
    def store_result(self, handle: ProjectHandle, kind: str, summary: dict,
                     *, model_hash: str, loader=None, payload=None,
                     on_evict=None) -> StoredResult:
        """Keep a result under a new ``result_id``, evicting the oldest."""
        res = StoredResult(_new_id("r"), kind, handle.id, model_hash,
                           summary, loader=loader, payload=payload,
                           on_evict=on_evict)
        handle.results[res.id] = res
        while len(handle.results) > self.max_results_per_project:
            _, old = handle.results.popitem(last=False)
            old.evict()
        return res

    def find_result(self, result_id: str) -> tuple[ProjectHandle,
                                                   StoredResult]:
        known = []
        for handle in self.projects.values():
            if result_id in handle.results:
                return handle, handle.results[result_id]
            known.extend(handle.results)
        raise unknown("result_id", result_id, list(known))
