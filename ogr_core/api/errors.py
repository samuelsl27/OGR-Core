# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
Errors an operation raises on purpose, each with a stable code.

The reader of these messages is very often a language model, and the one
thing that lets it recover is being told WHAT was wrong and WHAT to do
instead. So every error carries a ``hint`` where one exists, and every
"unknown name" carries the closest known names (:func:`did_you_mean`).

Codes are stable strings; the wording of ``message`` is not.

From OGR Slip2D's ``ogr_api/errors.py`` (v0.1.486), with one change
(v0.2.9): a message or hint may be a :class:`~ogr_core.messages.Coded`
sentence, and the ones this framework writes always are (rule 2: the core
does not translate). :meth:`OgrApiError.to_dict` then carries the message's
code and values next to its English (``message_code``, ``message_args``,
``hint_code``, ``hint_args``), and :func:`from_dict` gives them back, so a
window across the bridge can translate an error it did not raise.

Author: Samuel Sáez López (UPCT)
"""
from __future__ import annotations

import difflib
from typing import Iterable, Optional

from ..messages import Coded, Joined, args_from_json, as_nested, json_args
from .messages import say


class OgrApiError(Exception):
    """Base class: ``[CODE] message Hint: hint``."""

    code = "E_INTERNAL"

    def __init__(self, message: str, *, hint: Optional[str] = None,
                 details: Optional[dict] = None,
                 code: Optional[str] = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.details = details or {}
        if code is not None:
            self.code = code

    def __str__(self) -> str:
        text = f"[{self.code}] {self.message}"
        if self.hint:
            text += f" Hint: {self.hint}"
        return text

    def to_dict(self) -> dict:
        out = {"code": self.code, "message": str(self.message)}
        _put_code(out, "message", self.message)
        if self.hint:
            out["hint"] = str(self.hint)
            _put_code(out, "hint", self.hint)
        if self.details:
            out["details"] = self.details
        return out


def _put_code(out: dict, field: str, text) -> None:
    code = getattr(text, "code", "")
    if code:
        out[f"{field}_code"] = code
        out[f"{field}_args"] = json_args(getattr(text, "args", None))


def _get_coded(d: dict, field: str):
    text = d.get(field)
    code = d.get(f"{field}_code")
    if text is None or not code:
        return text
    return Coded(str(text), code, args_from_json(d.get(f"{field}_args")))


class NotFound(OgrApiError):
    """A handle, id or name that does not exist."""

    code = "E_NOT_FOUND"


class InvalidArgument(OgrApiError):
    """A value of the wrong type, out of range, or not one of the choices."""

    code = "E_INVALID_ARGUMENT"


class Conflict(OgrApiError):
    """A valid request the current model does not allow."""

    code = "E_CONFLICT"


class NotConfigured(OgrApiError):
    """The model cannot be computed as configured; ``details['problems']``
    lists every reason."""

    code = "E_NOT_CONFIGURED"


class Busy(OgrApiError):
    """Another operation holds the model, or a job is already running."""

    code = "E_BUSY"


class JobFailed(OgrApiError):
    """A background job ended in failure; the message carries its error."""

    code = "E_JOB_FAILED"


#: The error classes by code, for :func:`from_dict`.
ERRORS = {cls.code: cls for cls in (NotFound, InvalidArgument, Conflict,
                                    NotConfigured, Busy, JobFailed)}


def from_dict(d: dict) -> OgrApiError:
    """An error object (:meth:`OgrApiError.to_dict`) as the ``OgrApiError``
    it was, with its message's code when it had one."""
    cls = ERRORS.get(d.get("code"), OgrApiError)
    message = _get_coded(d, "message")
    exc = cls(message if message is not None else say("api.error"),
              hint=_get_coded(d, "hint"), details=d.get("details"))
    if cls is OgrApiError:
        exc.code = d.get("code", "E_INTERNAL")
    return exc


def internal_error(exc: BaseException) -> OgrApiError:
    """An exception no operation turned into an ``OgrApiError``, as the
    ``[E_INTERNAL]`` the agent reads, with its type and its text.

    Slip2D v0.1.438 (D422) -- the one wording of the bridge to a window and
    of the MCP server without one: the same file gave «[E_INTERNAL]
    PermissionError: …» through the first and «PermissionError: …» through
    the second."""
    return OgrApiError(say("api.internal", type=type(exc).__name__,
                           text=str(exc)))


def did_you_mean(word: str, options: Iterable[str], n: int = 3) -> str:
    """``"Did you mean 'a' or 'b'?"``, or an empty string.

    The cut-off is difflib's default similarity (0.6) lowered a little,
    because setting names are long and share prefixes, and a suggestion
    that is merely plausible still beats a bare "unknown".
    """
    opts = [str(o) for o in options]
    close = difflib.get_close_matches(str(word), opts, n=n, cutoff=0.55)
    if not close:
        lowered = {o.lower(): o for o in opts}
        close = [lowered[c] for c in difflib.get_close_matches(
            str(word).lower(), list(lowered), n=n, cutoff=0.55)]
    if not close:
        return ""
    if len(close) == 1:
        return say("api.did_you_mean.one", name=close[0])
    return say("api.did_you_mean.many",
               names=Joined(close[:-1], quote="'"), last=close[-1])


#: How many known names :func:`unknown` lists.
KNOWN_LISTED = 40


def known(options: list, limit: int = KNOWN_LISTED) -> str:
    """``"Known: 'a', 'b'."``, with how many more past ``limit``."""
    names = ", ".join(repr(o) for o in options[:limit])
    if len(options) <= limit:
        return say("api.known", names=names)
    return say("api.known.more", names=names, more=len(options) - limit)


def unknown(kind: str, word, options: Iterable[str]) -> NotFound:
    """A :class:`NotFound` for ``word`` among ``options``, with suggestions."""
    options = list(options)
    suggestion = did_you_mean(str(word), options)
    listing = known(options)
    hint = (say("api.unknown.hint", suggestion=as_nested(suggestion),
                known=as_nested(listing)) if suggestion else listing)
    return NotFound(say("api.unknown", kind=kind, word=word), hint=hint)
