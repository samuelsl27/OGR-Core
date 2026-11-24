# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
The framework of a program's operations layer, without Qt and without the
MCP SDK (v0.2.9).

Each program of the suite exposes what it can do to a model as named
operations with typed arguments and JSON-safe answers, which its interface,
its command line and its MCP server call without knowing who calls. This
package is what those layers have in common, and nothing of any one
program:

* :mod:`.registry` -- :class:`Registry`, one per program, which starts
  empty;
* :mod:`.errors` -- :class:`OgrApiError` and its subclasses, each with a
  stable code, and :func:`did_you_mean`;
* :mod:`.coerce` -- a JSON value to the type a dataclass declares,
  refusing anything that would need a guess;
* :mod:`.jobs` -- computations in a child process that can be cancelled
  for real, with each program's ``target`` and hooks;
* :mod:`.bridge` -- the live bridge between an MCP server and the
  program's open window: wire, discovery, client, answering side, router;
* :mod:`.workspace` -- models by handle, a lock per model, an edit as one
  undo step;
* :mod:`.messages` -- every sentence of the above as a code with its
  English template (rule 2).

It comes from OGR Slip2D's ``ogr_api`` (v0.1.486), which had it mixed with
its operations; ``docs/changelog/CHANGELOG_v0.2.9.md`` says what changed in
the move. It imports only the standard library and the core.

Author: Samuel Sáez López (UPCT)
"""
from .errors import (  # noqa: F401
    Busy,
    Conflict,
    InvalidArgument,
    JobFailed,
    NotConfigured,
    NotFound,
    OgrApiError,
    did_you_mean,
    unknown,
)
from .messages import API_MESSAGES  # noqa: F401
from .registry import Operation, Registry  # noqa: F401
from .workspace import Workspace, WorkspaceNames  # noqa: F401

__all__ = [
    "API_MESSAGES",
    "Busy",
    "Conflict",
    "InvalidArgument",
    "JobFailed",
    "NotConfigured",
    "NotFound",
    "OgrApiError",
    "Operation",
    "Registry",
    "Workspace",
    "WorkspaceNames",
    "did_you_mean",
    "unknown",
]
