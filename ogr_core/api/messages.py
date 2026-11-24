# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
The messages of the operations framework, each with a stable code
(v0.2.9).

The framework came from OGR Slip2D's ``ogr_api`` (v0.1.486), where its
errors were English sentences with the values pasted in by f-strings. In
the core that breaks rule 2 (the core does not translate: a message leaves
it as a code with an English template, and each program's interface says
it in the reader's language). So every sentence a caller can read is one
entry here, rendered with :func:`ogr_core.messages.coded`: the result IS
the English sentence Slip2D wrote, byte for byte where nothing in it named
the program, and it also carries its code and values.

The names a sentence used to hard-code — the program, a menu path, the
operation an agent should call next — are values here, given by each
program (``BridgeConfig``, ``WorkspaceNames``, ``JobManager``).

Author: Samuel Sáez López (UPCT)
"""
from __future__ import annotations

from ..messages import MessageSpec, as_nested, coded


def _spec(code: str, english: str, group_by=(), **kw) -> MessageSpec:
    return MessageSpec(code, english, group_by=tuple(group_by), **kw)


_ENTRIES = [
    # -- errors.py ------------------------------------------------------
    _spec("api.internal", "{type}: {text}", ("type",)),
    _spec("api.did_you_mean.one", "Did you mean '{name}'?"),
    _spec("api.did_you_mean.many", "Did you mean {names} or '{last}'?"),
    _spec("api.unknown", "Unknown {kind} {word!r}.", ("kind",)),
    _spec("api.unknown.hint", "{suggestion} {known}"),
    _spec("api.known", "Known: {names}."),
    _spec("api.known.more", "Known: {names} (+{more} more)."),
    # -- coerce.py ------------------------------------------------------
    _spec("api.field.empty_path", "An empty {root} path."),
    _spec("api.field.empty_path.hint",
          "Use 'section.field', e.g. '{example}'."),
    _spec("api.field.empty_path.hint.plain", "Use 'section.field'."),
    _spec("api.field.too_deep",
          "'{walked}' is a value, not a section; '{path}' goes too deep."),
    _spec("api.field.retired", "'{path}' is not a {root} any more."),
    _spec("api.field.unknown", "'{name}' is not a field of {where}.",
          ("where",)),
    _spec("api.field.listing", "Fields of {where}: {names}."),
    _spec("api.field.listing.more",
          "Fields of {where}: {names} (+{more} more)."),
    _spec("api.field.listing.more_tool",
          "Fields of {where}: {names} (+{more} more; {tool} lists them)."),
    _spec("api.value.not_one_of", "{where}: {raw!r} is not one of {options}."),
    _spec("api.value.null", "{where} cannot be null."),
    _spec("api.value.not_a", "{where}: {raw!r} is not a {type}."),
    _spec("api.value.list", "{where} must be a list, got {raw!r}."),
    _spec("api.value.object", "{where} must be an object, got {raw!r}."),
    _spec("api.value.bool", "{where} must be true or false, got {raw!r}."),
    _spec("api.value.int", "{where} must be an integer, got {raw!r}."),
    _spec("api.value.number", "{where} must be a number, got {raw!r}."),
    _spec("api.value.finite", "{where} must be finite, got {raw!r}."),
    _spec("api.value.string", "{where} must be a string, got {raw!r}."),
    _spec("api.value.section",
          "{where} is a whole section; set its fields one by one "
          "(e.g. '{where}.<field>')."),
    _spec("api.value.point", "{where} must be [x, y], got {raw!r}."),
    _spec("api.value.points", "{where} must be a list of [x, y] pairs."),
    _spec("api.value.points.few",
          "{where} needs at least {minimum} points, got {count}."),
    # -- jobs -----------------------------------------------------------
    _spec("api.job.busy", "Job {job_id} is still running."),
    _spec("api.job.busy.hint",
          "Wait for it with {wait_op}('{job_id}', wait_seconds=...) or stop "
          "it with {cancel_op}."),
    _spec("api.job.crashed",
          "The analysis process ended without reporting a result."),
    # -- workspace.py ---------------------------------------------------
    _spec("api.model.none_open", "No model is open."),
    _spec("api.model.none_open.hint", "Call {new_op} or {open_op} first."),
    _spec("api.model.several",
          "Several models are open; say which one with project_id."),
    _spec("api.model.several.hint", "Open: {models}"),
    _spec("api.model.busy", "Model {model} is busy with {what} ({since:.0f} s).",
          ("what",)),
    _spec("api.model.another_operation", "another operation"),
    _spec("api.model.read", "a read"),
    _spec("api.retry", "Retry when it finishes."),
    _spec("api.retry.window", "Retry when the window has finished."),
    _spec("api.path.empty", "A path must be a non-empty string."),
    _spec("api.path.suffix", "{name!r} does not end in {suffix}."),
    _spec("api.path.relative",
          "{path!r} is a relative path and no working directory was "
          "configured."),
    _spec("api.path.relative.hint",
          "Pass an absolute path, or start the server with --workdir."),
    _spec("api.path.no_folder", "The folder {folder} does not exist."),
    _spec("api.path.exists", "{path} already exists."),
    _spec("api.path.exists.hint", "Pass overwrite=true to replace it."),
    _spec("api.path.missing", "{path} does not exist."),
    # -- bridge.py ------------------------------------------------------
    _spec("api.bridge.no_pid",
          "No {program} window with pid {pid} has its agent bridge on."),
    _spec("api.bridge.none", "No {program} window has its agent bridge on."),
    _spec("api.bridge.none.hint", "In the window: {menu}."),
    _spec("api.bridge.several",
          "Several {program} windows have their bridge on; say which with "
          "--attach PID."),
    _spec("api.bridge.listing.none", "None is running."),
    _spec("api.bridge.listing", "Running: {windows}",
          seps=(("windows", "; "),)),
    _spec("api.bridge.listing.item", "pid {pid} ({title})"),
    _spec("api.bridge.handshake_refused", "handshake refused"),
    _spec("api.bridge.closed", "The {program} window closed the bridge."),
    _spec("api.bridge.no_window",
          "No {program} window is open with its agent bridge on."),
    _spec("api.bridge.no_window.hint",
          "Open {program} (the bridge starts with it) or turn on {menu}, "
          "then repeat the call."),
    _spec("api.bridge.lost",
          "The {program} window closed while answering this call."),
    _spec("api.bridge.lost.hint",
          "It is not repeated automatically, because whether it ran there "
          "cannot be known: check the model ({summary_op}) and repeat it if "
          "needed."),
    _spec("api.bridge.mode.window_only", "window only"),
    _spec("api.bridge.mode.automatic", "automatic"),
    _spec("api.bridge.next.window", "the open window"),
    _spec("api.bridge.next.nowhere", "nowhere: no window is open"),
    _spec("api.bridge.next.local", "the server's own models"),
    _spec("api.bridge.unauthorized", "Wrong protocol or token."),
    _spec("api.bridge.not_json", "Not a JSON line."),
    _spec("api.bridge.bad_request", "A request is {{'id', 'op', 'kwargs'}}."),
    _spec("api.error", "error"),
]

#: Every message of ``ogr_core.api``, by code.
API_MESSAGES: dict = {s.code: s for s in _ENTRIES}


def say(code: str, **args):
    """The message ``code`` of :data:`API_MESSAGES` with ``args``."""
    return coded(API_MESSAGES, code, **args)


def part(code: str, **args) -> dict:
    """The message ``code`` as the value of another message's field."""
    return as_nested(say(code, **args))
