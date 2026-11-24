# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
v0.2.9 — the live bridge of ``ogr_core.api.bridge``, there and back.

From OGR Slip2D's ``ogr_api/bridge.py`` and the wire part of its
``test_live_bridge_v1203`` (v0.1.486). In Slip2D the answering side lived
in the window (Qt); here it is :class:`BridgeSession`, served by the
stdlib :class:`BridgeServer`, so the round trip is tested without a
screen. Invariants:

* **the bridge is only a change of transport**: an operation called
  through it returns what the registry returns, and an error comes back as
  the same class with the same English and the same message code;
* **only the token opens it**, and only the program's own protocol;
* **discovery**: a stale announcement is removed; another program's
  announcement is neither listed nor removed (two programs may share
  ``OGR_BRIDGE_DIR``); no window, one, several or a pid each give their
  answer, naming the program of the ``BridgeConfig``;
* **the router**: a call naming the server's own model stays with it,
  anything else goes to the window; with no window it falls back, unless
  ``only_window``; a window that closes mid-call is a ``Conflict``, never
  a repeat.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

def _configs():
    from ogr_core.api.bridge import BridgeConfig
    return (BridgeConfig("ogr-test-a-bridge/1", "OGR Test A", ".ogr-test-a"),
            BridgeConfig("ogr-test-b-bridge/1", "OGR Test B", ".ogr-test-b",
                         menu="Herramientas > Puente"))


class _Dir:
    """A private discovery folder for the duration of a test."""

    def __enter__(self):
        from ogr_core.api.bridge import BRIDGE_DIR_ENV
        self.var = BRIDGE_DIR_ENV
        self.path = Path(tempfile.mkdtemp(prefix="ogr_bridges_"))
        self.old = os.environ.get(BRIDGE_DIR_ENV)
        os.environ[BRIDGE_DIR_ENV] = str(self.path)
        return self.path

    def __exit__(self, *exc):
        import shutil
        if self.old is None:
            os.environ.pop(self.var, None)
        else:
            os.environ[self.var] = self.old
        shutil.rmtree(self.path, ignore_errors=True)
        return False


def _registry():
    from ogr_core.api import Conflict, Registry
    r = Registry()

    @r.operation("echo", toolset="t")
    def echo(ws, value=None, name=None, project_id=None):
        return {"value": value, "name": name, "ws": type(ws).__name__}

    @r.operation("fail", toolset="t")
    def fail(ws):
        raise Conflict("no", hint="h", details={"a": 1})

    @r.operation("crash", toolset="t")
    def crash(ws):
        raise KeyError("k")

    @r.operation("unknown_thing", toolset="t")
    def unknown_thing(ws):
        from ogr_core.api import unknown
        raise unknown("result_id", "r_x", ["r_y"])

    @r.operation("project_list", toolset="t")
    def project_list(ws):
        return {"projects": [{"project_id": "p_w", "name": "In the window"}]}

    return r


def _refused(cls, fn):
    try:
        fn()
    except cls as exc:
        return exc
    raise AssertionError(f"{cls.__name__} was not raised")


class TestTheWire:
    def test_bytes_nan_and_errors_travel(self):
        from ogr_core.api import Conflict
        from ogr_core.api.bridge import (decode, encode, error_from_dict,
                                         error_to_dict)
        msg = decode(encode({"png": b"\x89PNG\x00", "x": float("nan"),
                             "l": [1, 2.5]}))
        assert msg == {"png": b"\x89PNG\x00", "x": None, "l": [1, 2.5]}
        err = error_from_dict(error_to_dict(
            Conflict("no", hint="h", details={"a": 1})))
        assert isinstance(err, Conflict) and str(err) == "[E_CONFLICT] no " \
            "Hint: h" and err.details == {"a": 1}

    def test_an_exception_that_is_not_ours_travels_as_internal(self):
        from ogr_core.api.bridge import error_to_dict
        d = error_to_dict(ValueError("v"))
        assert d["code"] == "E_INTERNAL" and d["message"] == "ValueError: v"
        assert d["message_code"] == "api.internal"


class TestDiscovery:
    def test_a_stale_announcement_is_removed_and_a_foreign_one_kept(self):
        import json

        from ogr_core.api.bridge import live_bridges
        a, b = _configs()
        with _Dir() as folder:
            stale = folder / "99999.json"
            stale.write_text(json.dumps({
                "protocol": a.protocol, "port": 1, "token": "t",
                "pid": 99999, "started": 0}), encoding="utf-8")
            foreign = folder / "99998.json"
            foreign.write_text(json.dumps({
                "protocol": b.protocol, "port": 1, "token": "t",
                "pid": 99998, "started": 0}), encoding="utf-8")
            assert live_bridges(a) == []
            assert not stale.exists() and foreign.exists()

    def test_the_folder_is_the_programs_without_the_variable(self):
        from ogr_core.api.bridge import BRIDGE_DIR_ENV, bridge_dir
        a, _ = _configs()
        old = os.environ.pop(BRIDGE_DIR_ENV, None)
        try:
            assert bridge_dir(a) == Path.home() / ".ogr-test-a" / "bridges"
        finally:
            if old is not None:
                os.environ[BRIDGE_DIR_ENV] = old

    def test_none_one_several_and_by_pid(self):
        from ogr_core.api import Conflict, NotFound
        from ogr_core.api.bridge import BridgeServer, find_bridge
        a, b = _configs()
        r = _registry()
        with _Dir():
            err = _refused(NotFound, lambda: find_bridge(b))
            assert err.message == "No OGR Test B window has its agent " \
                "bridge on."
            assert err.hint == "In the window: Herramientas > Puente."
            with BridgeServer(a, lambda op, **kw: r.call(None, op, **kw),
                              title="Window 1") as s1:
                # another program's window does not count
                _refused(NotFound, lambda: find_bridge(b))
                assert find_bridge(a)["port"] == s1.port
                err = _refused(NotFound, lambda: find_bridge(a, pid=1))
                assert err.message == ("No OGR Test A window with pid 1 has "
                                       "its agent bridge on.")
                assert err.hint == f"Running: pid {os.getpid()} (Window 1)"
            # a second announcement of the same pid replaces the first, so
            # "several" is two files written by hand around a live server
            with BridgeServer(a, lambda op, **kw: None, title="W") as s2:
                import json
                folder = Path(os.environ["OGR_BRIDGE_DIR"])
                (folder / "1.json").write_text(json.dumps({
                    "protocol": a.protocol, "port": s2.port, "token": "t",
                    "pid": 1, "title": "Other", "started": 1.0}),
                    encoding="utf-8")
                err = _refused(Conflict, lambda: find_bridge(a))
                assert err.message == ("Several OGR Test A windows have "
                                       "their bridge on; say which with "
                                       "--attach PID.")
                assert err.hint.startswith("Running: pid ")
                assert find_bridge(a, pid=1)["title"] == "Other"


class TestThereAndBack:
    def test_a_call_returns_what_the_registry_returns(self):
        from ogr_core.api.bridge import BridgeClient, BridgeServer
        a, _ = _configs()
        r = _registry()
        with _Dir(), BridgeServer(a, lambda op, **kw: r.call(
                "WS", op, **kw), title="T", version="1.2.3") as srv:
            c = BridgeClient.attach(a)
            try:
                assert c.pid == os.getpid() and c.window == "T"
                assert c.version == "1.2.3"
                assert c.call("echo", value=[1, 2.5], name="n") == {
                    "value": [1, 2.5], "name": "n", "ws": "str"}
                assert c.alive()
            finally:
                c.close()
            assert srv.discovery is not None
        assert srv.discovery is None

    def test_an_error_comes_back_as_itself_with_its_code(self):
        from ogr_core.api import Conflict, NotFound, OgrApiError
        from ogr_core.api.bridge import BridgeClient, BridgeServer
        a, _ = _configs()
        r = _registry()
        with _Dir(), BridgeServer(a, lambda op, **kw: r.call(
                None, op, **kw)):
            c = BridgeClient.attach(a)
            try:
                err = _refused(Conflict, lambda: c.call("fail"))
                assert str(err) == "[E_CONFLICT] no Hint: h"
                assert err.details == {"a": 1}
                err = _refused(NotFound, lambda: c.call("unknown_thing"))
                assert err.message.code == "api.unknown"
                assert err.message.args == {"kind": "result_id",
                                            "word": "r_x"}
                err = _refused(NotFound, lambda: c.call("nope"))
                assert err.message == "Unknown operation 'nope'."
                err = _refused(OgrApiError, lambda: c.call("crash"))
                assert str(err) == "[E_INTERNAL] KeyError: 'k'"
            finally:
                c.close()

    def test_only_the_token_and_the_protocol_open_it(self):
        from ogr_core.api import OgrApiError
        from ogr_core.api.bridge import BridgeClient, BridgeServer
        a, b = _configs()
        with _Dir(), BridgeServer(a, lambda op, **kw: None) as srv:
            err = _refused(OgrApiError,
                           lambda: BridgeClient(a, srv.port, "wrong"))
            assert err.code == "E_UNAUTHORIZED"
            assert err.message == "Wrong protocol or token."
            # the right token under another program's protocol
            err = _refused(OgrApiError,
                           lambda: BridgeClient(b, srv.port, srv.token))
            assert err.code == "E_UNAUTHORIZED"
            BridgeClient(a, srv.port, srv.token).close()

    def test_the_greeting_hands_over_the_workdir(self):
        from ogr_core.api.bridge import BridgeClient, BridgeServer
        a, _ = _configs()
        seen = []
        with _Dir(), BridgeServer(a, lambda op, **kw: None,
                                  on_hello=seen.append) as srv:
            BridgeClient(a, srv.port, srv.token, workdir="C:/w").close()
        assert seen and seen[0]["workdir"] == "C:/w"


class TestTheSession:
    def test_a_bad_line_and_a_bad_request(self):
        from ogr_core.api.bridge import BridgeSession, decode, encode
        a, _ = _configs()
        s = BridgeSession(a, "tok", lambda op, **kw: {"op": op})
        out = decode(s.answer_line(b"not json\n"))
        assert out["ok"] is False and out["error"]["message"] == \
            "Not a JSON line."
        assert s.answer({"hello": a.protocol, "token": "tok"})["ok"]
        out = s.answer({"id": 4, "op": 5})
        assert out["id"] == 4 and out["ok"] is False
        assert out["error"]["message"] == "A request is {'id', 'op', " \
            "'kwargs'}."
        assert decode(s.answer_line(encode({"id": 5, "op": "x"}))) == {
            "id": 5, "ok": True, "result": {"op": "x"}}


class _FakeClient:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail
        self.pid, self.window, self.version = 7, "Fake", "0.0.1"

    def alive(self):
        return True

    def call(self, op, **kw):
        if self.fail:
            raise ConnectionError("gone")
        self.calls.append((op, kw))
        if op == "project_list":
            return {"projects": [{"project_id": "p_w",
                                  "name": "In the window"}]}
        return {"window": op}

    def close(self):
        pass


class TestTheRouter:
    def _ws(self):
        from ogr_core.api import Workspace
        from ogr_core.project import Project
        ws = Workspace()
        h = ws.add(Project("mine"))
        return ws, h

    def test_the_servers_own_stays_and_the_rest_goes_to_the_window(self):
        from ogr_core.api.bridge import WindowRouter
        a, _ = _configs()
        r = _registry()
        ws, h = self._ws()
        fake = _FakeClient()
        router = WindowRouter(a, ws, local_call=r.call,
                              finder=lambda: {"port": 1, "token": "t"},
                              connect=lambda info: fake)
        assert router.call("echo", project_id=h.id)["ws"] == "Workspace"
        assert router.call("echo", value=1) == {"window": "echo"}
        assert fake.calls == [("echo", {"value": 1})]
        fake.calls.clear()
        st = router.status()
        assert st["next_call_goes_to"] == "the open window"
        assert st["mode"] == "automatic" and st["pid"] == 7
        assert router.window_models() == [
            {"project_id": "p_w", "name": "In the window",
             "in_window": True}]

    def test_no_window_falls_back_unless_only_window(self):
        from ogr_core.api import NotConfigured
        from ogr_core.api.bridge import WindowRouter
        _, b = _configs()
        r = _registry()
        ws, _ = self._ws()
        router = WindowRouter(b, ws, local_call=r.call, finder=lambda: None)
        assert router.call("echo", value=2)["ws"] == "Workspace"
        assert router.status()["next_call_goes_to"] == \
            "the server's own models"
        only = WindowRouter(b, only_window=True, finder=lambda: None)
        err = _refused(NotConfigured, lambda: only.call("echo"))
        assert err.message == ("No OGR Test B window is open with its agent "
                               "bridge on.")
        assert err.hint == ("Open OGR Test B (the bridge starts with it) or "
                            "turn on Herramientas > Puente, then repeat the "
                            "call.")
        assert only.status()["next_call_goes_to"] == \
            "nowhere: no window is open"
        assert only.status()["mode"] == "window only"

    def test_a_window_that_closes_mid_call_is_a_conflict_not_a_repeat(self):
        from ogr_core.api import Conflict
        from ogr_core.api.bridge import WindowRouter
        a, _ = _configs()
        r = _registry()
        ws, _ = self._ws()
        fake = _FakeClient(fail=True)
        router = WindowRouter(a, ws, local_call=r.call,
                              finder=lambda: {"port": 1, "token": "t"},
                              connect=lambda info: fake)
        err = _refused(Conflict, lambda: router.call("echo", value=3))
        assert err.message == ("The OGR Test A window closed while answering "
                               "this call.")
        assert "project_summary" in err.hint

    def test_a_router_needs_its_call(self):
        from ogr_core.api.bridge import WindowRouter
        a, _ = _configs()
        ws, _ = self._ws()
        with pytest.raises(ValueError):
            WindowRouter(a, ws)
        with pytest.raises(ValueError):
            WindowRouter(a)
