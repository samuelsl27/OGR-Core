# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.9 — the registry of operations and the coded errors of
``ogr_core.api``.

From OGR Slip2D's ``ogr_api`` (v0.1.486), where the registry was one module
dictionary filled with Slip2D's operations, and the errors English
sentences built by f-strings. Invariants:

* **a registry per program, empty at birth**: two registries share
  nothing; a name registers once; ``call`` leaves the keyword ``name`` to
  the operation; an unknown operation is a ``NotFound`` with the closest
  names;
* **the English did not move**: the sentences Slip2D's agents read are the
  same, byte for byte, where they named nothing of Slip2D (the expected
  strings below are copied from Slip2D's source, not from this code's
  output);
* **rule 2 in this package**: every message an ``OgrApiError`` of
  ``ogr_core.api`` carries is coded — no raise passes a literal or an
  f-string —, every code used is in ``API_MESSAGES`` and every entry of
  ``API_MESSAGES`` is used;
* **the code survives the wire**: ``to_dict`` and ``from_dict`` give back
  the same class, the same English and the same code with its values.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_API = Path(__file__).resolve().parent.parent / "ogr_core" / "api"


def _refused(cls, fn):
    try:
        fn()
    except cls as exc:
        return exc
    raise AssertionError(f"{cls.__name__} was not raised")


class TestTheRegistry:
    def test_two_registries_share_nothing_and_start_empty(self):
        from ogr_core.api import Registry
        a, b = Registry(), Registry()
        assert len(a) == 0 and list(a) == []

        @a.operation("ping", toolset="info")
        def ping(ws):
            """Answer pong.

            More text."""
            return {"pong": True}

        assert "ping" in a and "ping" not in b
        assert a["ping"].summary == "Answer pong."
        assert a["ping"].toolset == "info" and a["ping"].mutates is False
        assert a.call(None, "ping") == {"pong": True}

    def test_a_name_registers_once(self):
        from ogr_core.api import Registry
        r = Registry()
        r.operation("x", toolset="t")(lambda ws: None)
        with pytest.raises(ValueError):
            r.operation("x", toolset="t")(lambda ws: None)

    def test_an_operation_may_take_a_keyword_called_name(self):
        from ogr_core.api import Registry
        r = Registry()

        @r.operation("project_new", toolset="project", mutates=True)
        def project_new(ws, name="Model"):
            return {"ws": ws, "name": name}

        assert r.call("W", "project_new", name="Demo") == {"ws": "W",
                                                           "name": "Demo"}
        assert r["project_new"].mutates is True

    def test_an_unknown_operation_names_the_closest(self):
        from ogr_core.api import NotFound, Registry
        r = Registry()
        for n in ("project_new", "project_open", "model_define"):
            r.operation(n, toolset="t")(lambda ws: None)
        err = _refused(NotFound, lambda: r.call(None, "prject_new"))
        # Slip2D's wording: f"Unknown {kind} {word!r}." and the hint of
        # ``unknown`` (did_you_mean, then the sorted listing)
        assert str(err) == (
            "[E_NOT_FOUND] Unknown operation 'prject_new'. Hint: Did you "
            "mean 'project_new' or 'project_open'? Known: 'model_define', "
            "'project_new', 'project_open'.")
        assert err.message.code == "api.unknown"
        assert err.message.args == {"kind": "operation",
                                    "word": "prject_new"}


class TestTheEnglishDidNotMove:
    def test_did_you_mean(self):
        from ogr_core.api import did_you_mean
        assert did_you_mean("cohesio", ["cohesion", "friction"]) == \
            "Did you mean 'cohesion'?"
        assert did_you_mean("Cohesion", ["cohesion"]) == \
            "Did you mean 'cohesion'?"
        # difflib's order (best first, ties by reverse name), as Slip2D's
        assert did_you_mean("abc", ["abd", "abe", "abf"]) == \
            "Did you mean 'abf', 'abe' or 'abd'?"
        assert did_you_mean("zzz", ["cohesion"]) == ""

    def test_unknown_without_a_suggestion_lists_forty(self):
        from ogr_core.api import unknown
        names = [f"n{i:02d}" for i in range(45)]
        err = unknown("job_id", "j_zz", names)
        listing = ", ".join(repr(n) for n in names[:40])
        assert err.hint == f"Known: {listing} (+5 more)."
        assert err.hint.code == "api.known.more"

    def test_internal_error(self):
        from ogr_core.api.errors import internal_error
        err = internal_error(PermissionError("denied"))
        assert str(err) == "[E_INTERNAL] PermissionError: denied"
        assert err.message.code == "api.internal"


class TestTheCodeSurvivesTheWire:
    def test_class_english_code_and_values(self):
        from ogr_core.api import Conflict, unknown
        from ogr_core.api.errors import from_dict
        err = unknown("result_id", "r_1", ["r_2"])
        back = from_dict(err.to_dict())
        assert type(back) is type(err)
        assert str(back) == str(err)
        assert back.message.code == "api.unknown"
        assert back.message.args == {"kind": "result_id", "word": "r_1"}
        assert back.hint.code == err.hint.code
        plain = from_dict(Conflict("no", hint="h",
                                   details={"a": 1}).to_dict())
        assert isinstance(plain, Conflict) and str(plain) == \
            "[E_CONFLICT] no Hint: h" and plain.details == {"a": 1}
        assert not getattr(plain.message, "code", "")

    def test_an_unknown_code_keeps_its_code(self):
        from ogr_core.api import OgrApiError
        from ogr_core.api.errors import from_dict
        back = from_dict({"code": "E_UNAUTHORIZED", "message": "x"})
        assert type(back) is OgrApiError and back.code == "E_UNAUTHORIZED"

    def test_a_program_translates_it_by_its_code(self):
        from ogr_core.api import API_MESSAGES, unknown
        from ogr_core.api.errors import from_dict
        from ogr_core.messages import render
        d = unknown("operation", "x", ["y"]).to_dict()
        back = from_dict(d)
        es = {"Unknown {kind} {word!r}.": "{kind} {word!r} desconocido."}
        assert render(API_MESSAGES, back.message.code, back.message.args,
                      str(back.message), translate=lambda t: es.get(t, t)) \
            == "operation 'x' desconocido."


def _sources():
    return sorted(p for p in _API.rglob("*.py")
                  if "__pycache__" not in p.parts)


_ERRORS = {"OgrApiError", "NotFound", "InvalidArgument", "Conflict",
           "NotConfigured", "Busy", "JobFailed"}


class TestRuleTwoInThisPackage:
    def test_no_error_is_raised_with_a_literal_or_an_f_string(self):
        bad = []
        for path in _sources():
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id in _ERRORS):
                    continue
                texts = list(node.args[:1]) + [k.value for k in node.keywords
                                               if k.arg == "hint"]
                for t in texts:
                    if isinstance(t, (ast.JoinedStr, ast.Constant,
                                      ast.BinOp)):
                        bad.append(f"{path.name}:{node.lineno}")
        assert bad == [], bad

    def test_every_code_used_exists_and_every_entry_is_used(self):
        from ogr_core.api import API_MESSAGES
        used = set()
        pattern = re.compile(r"""(?:say|part)\(\s*["']([a-z_.]+)["']""")
        cond = re.compile(r"""["'](api\.[a-z_.]+)["']""")
        for path in _sources():
            if path.name == "messages.py":
                continue
            text = path.read_text(encoding="utf-8")
            used |= set(pattern.findall(text))
            used |= set(cond.findall(text))
        assert used - set(API_MESSAGES) == set()
        assert set(API_MESSAGES) - used == set()

    def test_every_entry_renders_its_english(self):
        from ogr_core.api import API_MESSAGES
        from ogr_core.messages import english
        for code, spec in API_MESSAGES.items():
            fields = set(re.findall(r"(?<!\{)\{(\w+)", spec.english))
            args = {f: 1.0 if f == "since" else f"<{f}>" for f in fields}
            assert english(API_MESSAGES, code, args), code
