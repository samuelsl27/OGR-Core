# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
The registry of named operations.

An operation is a plain Python function ``op(ws, **kwargs) -> dict`` with a
stable name, a toolset and a flag saying whether it edits a model. The MCP
server publishes one tool per operation; the live bridge forwards
``(name, kwargs)`` here unchanged. One registry is what keeps the front
ends of a program (its interface, its command line, its MCP server) from
drifting into different programs.

From OGR Slip2D's ``ogr_api/ops/__init__.py`` (v0.1.486), with one change
(v0.2.9): the registry is a :class:`Registry` object, one per program, and
it starts empty. Slip2D's was a module dictionary that imported Slip2D's
operations at the bottom; here two programs (or two tests) in one process
each have their own, and nothing in the core is shared between them.

    from ogr_core.api import Registry

    OPERATIONS = Registry()

    @OPERATIONS.operation("model_new", toolset="model", mutates=True)
    def model_new(ws, name="Model"):
        ...

    OPERATIONS.call(ws, "model_new", name="Demo")

Author: Samuel Sáez López (UPCT)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterator

from .errors import unknown


@dataclass(frozen=True)
class Operation:
    name: str
    func: Callable
    toolset: str
    mutates: bool

    @property
    def summary(self) -> str:
        doc = (self.func.__doc__ or "").strip()
        return doc.splitlines()[0] if doc else ""


class Registry:
    """The named operations of one program."""

    def __init__(self) -> None:
        self._ops: dict[str, Operation] = {}

    def operation(self, name: str, *, toolset: str, mutates: bool = False):
        """Register ``func`` under ``name``."""
        def deco(func):
            if name in self._ops:
                raise ValueError(f"operation {name!r} registered twice")
            self._ops[name] = Operation(name, func, toolset, mutates)
            return func
        return deco

    def call(self, ws, op_name: str, /, **kwargs):
        """Run the operation ``op_name`` on workspace ``ws``.

        Both leading arguments are positional-only, so an operation may take
        a keyword called ``name`` (``project_new(name=...)``).
        """
        op = self._ops.get(op_name)
        if op is None:
            raise unknown("operation", op_name, sorted(self._ops))
        return op.func(ws, **kwargs)

    # -- a read-only mapping ---------------------------------------------
    def get(self, name: str, default=None):
        return self._ops.get(name, default)

    def __getitem__(self, name: str) -> Operation:
        return self._ops[name]

    def __contains__(self, name) -> bool:
        return name in self._ops

    def __iter__(self) -> Iterator[str]:
        return iter(self._ops)

    def __len__(self) -> int:
        return len(self._ops)

    def keys(self):
        return self._ops.keys()

    def values(self):
        return self._ops.values()

    def items(self):
        return self._ops.items()
