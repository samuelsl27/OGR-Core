# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Samuel Sáez López — Universidad Politécnica de Cartagena
"""
The live bridge's wire format, discovery, client and answering side.

A program's window can serve its own model to an agent: it starts a TCP
server on 127.0.0.1 inside the window, and the program's MCP server
forwards every tool call to it as ``(operation, kwargs)`` — the same
registry the headless server calls, so the bridge is only a change of
transport.

Why loopback TCP with a token, and not a named pipe: the client below is
plain ``socket`` on every system; nothing leaves the machine; and a token
is required on every connection. The token is in the discovery file,
readable by the user alone.

Wire format: one JSON object per line, UTF-8. Bytes (a PNG) travel as
``{"__bytes__": base64}``.

* client → server, first line: ``{"hello": PROTOCOL, "token": ...}``,
  optionally with ``"workdir"`` (the folder the MCP server was given, so a
  relative path means the same in the window); answer
  ``{"hello": PROTOCOL, "ok": true, "window": title, "pid": n,
  "version": v}``.
* then ``{"id": n, "op": name, "kwargs": {...}}``; answer
  ``{"id": n, "ok": true, "result": ...}`` or
  ``{"id": n, "ok": false, "error": {"code", "message", "hint",
  "details"}}``, which the client raises as the same ``OgrApiError``.

From OGR Slip2D's ``ogr_api/bridge.py`` (v0.1.486). What v0.2.9 changes:

* **What named Slip2D is a** :class:`BridgeConfig`: the protocol string,
  the program's name, the folder under the user's home where its windows
  announce themselves, the menu path that turns the bridge on, and the
  operations the router calls. Discovery only lists the bridges of its own
  protocol, so two programs sharing ``OGR_BRIDGE_DIR`` never attach to
  each other's window.
* **The answering side is here too** (:class:`BridgeSession`), without
  Qt: the handshake with its token and the dispatch to the registry, which
  in Slip2D lived in the window (``ogr_gui.agent_bridge``). A window feeds
  it the lines its own socket reads; :class:`BridgeServer` is a plain
  threaded server for a process without an event loop (and the tests).
* The router takes the program's ``call``.

Only the standard library: ``ogr_core`` imports neither Qt nor ``mcp``.

Author: Samuel Sáez López (UPCT)
"""
from __future__ import annotations

import base64
import hmac
import json
import math
import os
import secrets
import select
import socket
import socketserver
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ..messages import as_nested
from .errors import (Conflict, InvalidArgument, NotConfigured, NotFound,
                     OgrApiError, from_dict, internal_error)
from .messages import say

#: Longest line either side accepts (a large PNG, base64, fits well).
MAX_LINE = 64 * 1024 * 1024

#: The environment variable that moves every program's discovery folder
#: (the tests point it at a temporary one).
BRIDGE_DIR_ENV = "OGR_BRIDGE_DIR"


@dataclass(frozen=True)
class BridgeConfig:
    """What one program's bridge is called and where it is announced.

    Slip2D's would be ``BridgeConfig("ogr-slip2d-bridge/1", "OGR Slip2D",
    ".ogr-slip2d")``: a window of an older version answers only to the
    protocol string it always used.
    """
    protocol: str
    program: str
    home_dir: str
    menu: str = "Tools > Agent bridge (MCP)"
    #: The operation an agent is told to check the model with, after a
    #: window closed mid-call.
    summary_op: str = "project_summary"
    #: The operation that lists a window's open models.
    list_op: str = "project_list"


# ----------------------------------------------------------------------
# Encoding
# ----------------------------------------------------------------------
def _to_wire(obj):
    if isinstance(obj, (bytes, bytearray)):
        return {"__bytes__": base64.b64encode(bytes(obj)).decode("ascii")}
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {str(k): _to_wire(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_wire(v) for v in obj]
    return obj


def _from_wire(obj):
    if isinstance(obj, dict):
        if set(obj) == {"__bytes__"}:
            return base64.b64decode(obj["__bytes__"])
        return {k: _from_wire(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_from_wire(v) for v in obj]
    return obj


def encode(message: dict) -> bytes:
    """One message as a UTF-8 JSON line."""
    return (json.dumps(_to_wire(message), ensure_ascii=False,
                       allow_nan=False, default=str) + "\n").encode("utf-8")


def decode(line: bytes) -> dict:
    """One JSON line back into a message."""
    return _from_wire(json.loads(line.decode("utf-8")))


def error_to_dict(exc: BaseException) -> dict:
    """An exception as the wire's error object."""
    if isinstance(exc, OgrApiError):
        return exc.to_dict()
    # Slip2D v0.1.438 (D422) -- the wording the MCP server gives without a
    # window
    return internal_error(exc).to_dict()


def error_from_dict(d: dict) -> OgrApiError:
    """The wire's error object as the ``OgrApiError`` it was."""
    return from_dict(d)


# ----------------------------------------------------------------------
# Discovery
# ----------------------------------------------------------------------
def bridge_dir(config: BridgeConfig) -> Path:
    """Where a running window announces its bridge (one file per pid)."""
    override = os.environ.get(BRIDGE_DIR_ENV)
    return Path(override) if override else \
        Path.home() / config.home_dir / "bridges"


def write_discovery(config: BridgeConfig, port: int, token: str,
                    title: str, version: Optional[str] = None) -> Path:
    """Announce this process's bridge; the file is the user's alone."""
    folder = bridge_dir(config)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{os.getpid()}.json"
    data = {"protocol": config.protocol, "port": int(port), "token": token,
            "pid": os.getpid(), "title": title, "started": time.time()}
    if version:
        data["version"] = str(version)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:  # pragma: no cover - Windows keeps the home private
        pass
    os.replace(tmp, path)
    return path


def remove_discovery(config: BridgeConfig,
                     path: Optional[Path] = None) -> None:
    target = path or (bridge_dir(config) / f"{os.getpid()}.json")
    try:
        target.unlink()
    except OSError:
        pass


def _answers(port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout):
            return True
    except OSError:
        return False


def live_bridges(config: BridgeConfig) -> list:
    """The windows of this protocol whose bridge answers, newest first. A
    file whose port no longer answers is a window that closed without
    saying so; it is removed. Another protocol's file is left alone."""
    out = []
    folder = bridge_dir(config)
    if not folder.is_dir():
        return out
    for f in folder.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("protocol") != config.protocol:
            continue
        if _answers(data.get("port", 0)):
            out.append(data)
        else:
            remove_discovery(config, f)
    out.sort(key=lambda d: -float(d.get("started", 0)))
    return out


def find_bridge(config: BridgeConfig, pid: Optional[int] = None) -> dict:
    """The bridge to attach to: ``pid``'s, or the only one running."""
    bridges = live_bridges(config)
    if pid is not None:
        for b in bridges:
            if int(b.get("pid", -1)) == int(pid):
                return b
        raise NotFound(say("api.bridge.no_pid", program=config.program,
                           pid=pid), hint=_listing(bridges))
    if not bridges:
        raise NotFound(say("api.bridge.none", program=config.program),
                       hint=say("api.bridge.none.hint", menu=config.menu))
    if len(bridges) > 1:
        raise Conflict(say("api.bridge.several", program=config.program),
                       hint=_listing(bridges))
    return bridges[0]


def _listing(bridges) -> str:
    if not bridges:
        return say("api.bridge.listing.none")
    return say("api.bridge.listing", windows=[
        as_nested(say("api.bridge.listing.item", pid=b["pid"],
                      title=b.get("title", ""))) for b in bridges])


# ----------------------------------------------------------------------
# Client
# ----------------------------------------------------------------------
class BridgeClient:
    """A connection to one window's bridge; ``call`` is thread-safe."""

    def __init__(self, config: BridgeConfig, port: int, token: str, *,
                 timeout: float = 600.0, workdir=None) -> None:
        self.config = config
        self._sock = socket.create_connection(("127.0.0.1", int(port)),
                                              timeout=10.0)
        self._sock.settimeout(timeout)
        self._file = self._sock.makefile("rwb")
        self._lock = threading.Lock()
        self._next = 0
        greeting = {"hello": config.protocol, "token": token}
        if workdir:
            greeting["workdir"] = str(workdir)
        hello = self._exchange(greeting)
        if not hello.get("ok"):
            self.close()
            raise error_from_dict(hello.get("error") or {
                "code": "E_INTERNAL",
                "message": say("api.bridge.handshake_refused")})
        self.window = hello.get("window", "")
        self.pid = hello.get("pid")
        # Slip2D v0.1.300 (D296) -- None from a window that does not say it
        self.version = hello.get("version")

    @classmethod
    def attach(cls, config: BridgeConfig,
               pid: Optional[int] = None) -> "BridgeClient":
        info = find_bridge(config, pid)
        return cls(config, info["port"], info["token"])

    def _exchange(self, message: dict) -> dict:
        self._file.write(encode(message))
        self._file.flush()
        line = self._file.readline(MAX_LINE)
        if not line:
            raise ConnectionError(str(say("api.bridge.closed",
                                          program=self.config.program)))
        return decode(line)

    def call(self, op: str, /, **kwargs):
        """Run ``op`` in the window; raises the operation's own error."""
        with self._lock:
            self._next += 1
            answer = self._exchange({"id": self._next, "op": op,
                                     "kwargs": kwargs})
        if answer.get("ok"):
            return answer.get("result")
        raise error_from_dict(answer.get("error") or {})

    def alive(self) -> bool:
        """Whether the window is still there, asked WITHOUT sending
        anything (Slip2D v0.1.207). Between calls nothing is owed to this
        socket, so anything readable means the window hung up: a closed
        window is found before the next call, not by failing it."""
        try:
            readable, _, _ = select.select([self._sock], [], [], 0)
            if not readable:
                return True
            return self._sock.recv(1, socket.MSG_PEEK) != b""
        except (OSError, ValueError):
            return False

    def close(self) -> None:
        for thing in (self._file, self._sock):
            try:
                thing.close()
            except OSError:
                pass


# ----------------------------------------------------------------------
# The answering side
# ----------------------------------------------------------------------
class BridgeSession:
    """One connection's state on the answering side: the handshake, then
    one answer per request.

    ``call(op, **kwargs)`` runs an operation (the program's registry on
    the window's workspace); ``on_hello(message)`` sees an accepted
    greeting (Slip2D set the workspace's ``workdir`` from it);
    ``window`` and ``version`` are what the greeting answers.
    """

    def __init__(self, config: BridgeConfig, token: str, call: Callable,
                 *, window: Callable[[], str] = lambda: "",
                 version: Optional[str] = None,
                 on_hello: Optional[Callable[[dict], None]] = None) -> None:
        self.config = config
        self._token = token
        self._call = call
        self._window = window
        self._version = version
        self._on_hello = on_hello
        self.authed = False

    def answer_line(self, line: bytes) -> bytes:
        """The encoded answer to one encoded line."""
        try:
            message = decode(line)
        except ValueError:
            return encode({"ok": False, "error": InvalidArgument(
                say("api.bridge.not_json")).to_dict()})
        return encode(self.answer(message))

    def answer(self, message: dict) -> dict:
        if not self.authed:
            token = str(message.get("token", ""))
            if (message.get("hello") != self.config.protocol
                    or not hmac.compare_digest(token.encode("utf-8"),
                                               self._token.encode("utf-8"))):
                err = OgrApiError(say("api.bridge.unauthorized"),
                                  code="E_UNAUTHORIZED")
                return {"hello": self.config.protocol, "ok": False,
                        "error": err.to_dict()}
            self.authed = True
            if self._on_hello is not None:
                self._on_hello(message)
            out = {"hello": self.config.protocol, "ok": True,
                   "window": self._window(), "pid": os.getpid()}
            if self._version:
                out["version"] = self._version
            return out
        mid = message.get("id")
        try:
            op = message.get("op")
            kwargs = message.get("kwargs") or {}
            if not isinstance(op, str) or not isinstance(kwargs, dict):
                raise InvalidArgument(say("api.bridge.bad_request"))
            return {"id": mid, "ok": True, "result": self._call(op, **kwargs)}
        except Exception as exc:  # noqa: BLE001 - reported, with its type
            return {"id": mid, "ok": False, "error": error_to_dict(exc)}


class BridgeServer:
    """A bridge on 127.0.0.1 served by threads, for a process without an
    event loop (a window serves its own from its loop with a
    :class:`BridgeSession` per connection). ``start`` announces it;
    ``stop`` withdraws the announcement and closes it."""

    def __init__(self, config: BridgeConfig, call: Callable, *,
                 title: str = "", version: Optional[str] = None,
                 on_hello: Optional[Callable[[dict], None]] = None) -> None:
        self.config = config
        self.token = secrets.token_urlsafe(24)
        self.title = title
        self.version = version
        self.discovery: Optional[Path] = None
        outer = self

        class _Handler(socketserver.StreamRequestHandler):
            def handle(self):
                session = BridgeSession(config, outer.token, call,
                                        window=lambda: outer.title,
                                        version=version, on_hello=on_hello)
                while True:
                    line = self.rfile.readline(MAX_LINE)
                    if not line:
                        return
                    self.wfile.write(session.answer_line(line))
                    self.wfile.flush()
                    if not session.authed:
                        return

        class _Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
            daemon_threads = True
            allow_reuse_address = False

        self._server = _Server(("127.0.0.1", 0), _Handler)
        self._thread: Optional[threading.Thread] = None

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    def start(self) -> "BridgeServer":
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        daemon=True)
        self._thread.start()
        self.discovery = write_discovery(self.config, self.port, self.token,
                                         self.title, self.version)
        return self

    def stop(self) -> None:
        if self.discovery is not None:
            remove_discovery(self.config, self.discovery)
            self.discovery = None
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
        return False


# ----------------------------------------------------------------------
# Routing: the window when there is one (Slip2D v0.1.207)
# ----------------------------------------------------------------------
class WindowRouter:
    """Where each call goes: the open window, or the server's own model.

    Slip2D v0.1.207 — the owner's rule: whatever client asks, if the
    program is open the work is done ON THE WINDOW, where it is seen,
    undone with Edit > Undo and computed into the results panel; if it is
    not, the server keeps working on its own models. Nothing to configure.

    * A call that names something of the server's own — a ``project_id``,
      ``job_id`` or ``result_id`` it holds — stays with it, so a model
      begun before the window was open is not lost when one appears.
    * Anything else goes to the window if one answers (the newest, when
      several do), and otherwise to the server's own workspace.
    * The connection is made when first needed and remade after the window
      closes, so the order in which the program and the client are opened
      does not matter.
    * ``only_window`` (``--attach``) never falls back: with no window it
      says what to open.

    A call the window was answering when it closed is NOT repeated here:
    whether it ran there cannot be known, and an edit applied twice is
    worse than an error.

    ``local_call(ws, op, **kwargs)`` is the program's registry call.
    """

    def __init__(self, config: BridgeConfig, ws=None, *,
                 local_call: Optional[Callable] = None,
                 pid: Optional[int] = None,
                 only_window: bool = False, workdir=None,
                 finder=None, connect=None) -> None:
        if ws is None and not only_window:
            raise ValueError("a router without a workspace must be "
                             "only_window")
        if ws is not None and local_call is None:
            raise ValueError("a router with a workspace needs local_call")
        self.config = config
        self.ws = ws
        self._local_call = local_call
        self.pid_wanted = pid
        self.only_window = only_window
        self.workdir = str(workdir) if workdir else (
            str(ws.workdir) if ws is not None and ws.workdir else None)
        self._finder = finder or self._find
        self._connect = connect or (
            lambda info: BridgeClient(config, info["port"], info["token"],
                                      workdir=self.workdir))
        self._client: Optional[BridgeClient] = None
        self._lock = threading.Lock()

    # -- which window ---------------------------------------------------
    def _find(self) -> Optional[dict]:
        if self.pid_wanted is not None:
            try:
                return find_bridge(self.config, self.pid_wanted)
            except NotFound:
                return None
        bridges = live_bridges(self.config)
        return bridges[0] if bridges else None

    def _window(self) -> Optional["BridgeClient"]:
        with self._lock:
            if self._client is not None and not self._client.alive():
                # The window closed since the last call: found now, before
                # anything is sent, so this call can go where it should.
                self._client.close()
                self._client = None
            if self._client is None:
                info = self._finder()
                if info is None:
                    return None
                try:
                    self._client = self._connect(info)
                except (OSError, OgrApiError):
                    return None
            return self._client

    def _drop(self) -> None:
        with self._lock:
            if self._client is not None:
                self._client.close()
            self._client = None

    # -- whose is it ----------------------------------------------------
    def _is_local(self, kwargs: dict) -> bool:
        ws = self.ws
        if ws is None:
            return False
        pid = kwargs.get("project_id")
        if pid is not None and pid in ws.projects:
            return True
        job = kwargs.get("job_id")
        if job is not None and job in ws.jobs.jobs:
            return True
        res = kwargs.get("result_id")
        if res is not None and any(res in h.results
                                   for h in ws.projects.values()):
            return True
        return False

    # -- the call -------------------------------------------------------
    def call(self, op: str, /, **kwargs):
        if self._is_local(kwargs):
            return self._local_call(self.ws, op, **kwargs)
        client = self._window()
        if client is None:
            if self.only_window:
                raise NotConfigured(
                    say("api.bridge.no_window", program=self.config.program),
                    hint=say("api.bridge.no_window.hint",
                             program=self.config.program,
                             menu=self.config.menu))
            return self._local_call(self.ws, op, **kwargs)
        try:
            return client.call(op, **kwargs)
        except (ConnectionError, OSError):
            self._drop()
            raise Conflict(
                say("api.bridge.lost", program=self.config.program),
                hint=say("api.bridge.lost.hint",
                         summary_op=self.config.summary_op)) from None

    # -- for server_info ------------------------------------------------
    @property
    def pid(self):
        c = self._client
        return c.pid if c is not None else None

    @property
    def window(self):
        c = self._client
        return c.window if c is not None else None

    def status(self) -> dict:
        """Where the next call without an id of the server's own goes."""
        client = self._window()
        if client is not None:
            nxt = say("api.bridge.next.window")
        elif self.only_window:
            nxt = say("api.bridge.next.nowhere")
        else:
            nxt = say("api.bridge.next.local")
        return {"mode": say("api.bridge.mode.window_only"
                            if self.only_window
                            else "api.bridge.mode.automatic"),
                "window_open": client is not None,
                "pid": client.pid if client is not None else None,
                "window": client.window if client is not None else None,
                # Slip2D v0.1.300 (D296): server_info compares it with its
                # own
                "version": (getattr(client, "version", None)
                            if client is not None else None),
                "next_call_goes_to": nxt}

    def window_models(self) -> list:
        client = self._window()
        if client is None:
            return []
        try:
            return [{"project_id": m["project_id"], "name": m["name"],
                     "in_window": True}
                    for m in client.call(self.config.list_op)["projects"]]
        except (ConnectionError, OSError):
            self._drop()
            return []

    def close(self) -> None:
        self._drop()


__all__ = ["BridgeConfig", "BridgeClient", "BridgeSession", "BridgeServer",
           "WindowRouter", "MAX_LINE", "BRIDGE_DIR_ENV", "encode", "decode",
           "error_to_dict", "error_from_dict", "bridge_dir",
           "write_discovery", "remove_discovery", "live_bridges",
           "find_bridge"]
