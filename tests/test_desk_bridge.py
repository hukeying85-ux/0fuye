"""The LAN bridge: one small HTTP contract shared with the PowerShell server.

The PowerShell side cannot be executed here, so the tests pin the wire format
(request shape, token header, result schema) against a Python stub that mimics
`Invoke-CgmdBridge.ps1`, plus static checks that the script keeps its promises
(ASCII only, no admin-only APIs, loopback/LAN filtering, refusal by default).
"""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import desk_bridge  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIDGE = os.path.join(ROOT, "skills", "cgmd-hub", "runner", "Invoke-CgmdBridge.ps1")


class _Handler(BaseHTTPRequestHandler):
    server_version = "cgmd-stub/1"
    seen = []

    def log_message(self, *args):  # keep pytest output clean
        pass

    def _answer(self, document, status=200):
        payload = json.dumps(document).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        _Handler.seen.append(("GET", self.path, self.headers.get("X-CGMD-Token")))
        if self.path == "/health":
            self._answer({"schema": desk_bridge.SCHEMA_RESULT, "kind": "health", "status": "ok",
                          "summary": "DESK alive, gmx 2025.1",
                          "detail": {"host": "DESK", "version": "2025.1", "port": 8765}})
            return
        if self.path == "/status":
            self._answer({"schema": desk_bridge.SCHEMA_RESULT, "kind": "status", "status": "ok",
                          "summary": "smoke ok: 100 ps, gpu"})
            return
        self._answer({"status": "error", "summary": "not found"}, status=404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        request = json.loads(body.decode("utf-8")) if body else {}
        _Handler.seen.append(("POST", self.path, self.headers.get("X-CGMD-Token"), request))
        if self.path != "/job":
            self._answer({"status": "error", "summary": "not found"}, status=404)
            return
        kind = request.get("kind")
        if kind == "smoke":
            self._answer({"schema": desk_bridge.SCHEMA_RESULT, "kind": "smoke", "status": "ok",
                          "summary": "gmx 2025.1: 100 ps on gpu", "detail": {"exit_code": 0}})
            return
        if kind == "gmx":
            self._answer({"schema": desk_bridge.SCHEMA_RESULT, "kind": "gmx", "status": "ok",
                          "summary": "gmx %s exit 0" % " ".join(request["args"]["argv"]),
                          "logs_tail": ["GROMACS version:    2025.1"]})
            return
        self._answer({"status": "unsupported", "summary": "unknown kind: %s" % kind}, status=200)


@pytest.fixture()
def bridge():
    _Handler.seen = []
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_ping_reads_the_health_document(bridge):
    answer = desk_bridge.ping("127.0.0.1", bridge)
    assert answer["status"] == "ok"
    assert answer["detail"]["version"] == "2025.1"
    assert ("GET", "/health", None) in _Handler.seen


def test_smoke_posts_a_job_and_returns_the_shared_schema(bridge):
    answer = desk_bridge.smoke("127.0.0.1", bridge, timeout=30)
    assert answer["schema"] == desk_bridge.SCHEMA_RESULT
    assert answer["status"] == "ok"
    assert "100 ps" in answer["summary"]
    method, path, token, request = _Handler.seen[-1]
    assert (method, path) == ("POST", "/job")
    assert request == {"kind": "smoke", "args": {"ps": 100}}


def test_gmx_arguments_are_forwarded_verbatim(bridge):
    answer = desk_bridge.gmx("127.0.0.1", bridge, ["--version"])
    assert answer["status"] == "ok"
    assert "--version" in answer["summary"]
    assert _Handler.seen[-1][3]["args"]["argv"] == ["--version"]


def test_token_is_sent_when_configured(bridge):
    desk_bridge.ping("127.0.0.1", bridge, token="s3cret")
    assert _Handler.seen[-1][2] == "s3cret"


def test_unreachable_desk_is_an_error_not_a_traceback():
    answer = None
    try:
        desk_bridge.ping("127.0.0.1", 1, timeout=2)
    except desk_bridge.BridgeError as exc:
        answer = str(exc)
    assert answer and "cannot reach" in answer


def test_cli_exit_codes(bridge, capsys):
    code = desk_bridge.main(["--host", "127.0.0.1", "--port", str(bridge), "ping"])
    assert code == 0
    out = capsys.readouterr().out
    assert json.loads(out)["status"] == "ok"

    code = desk_bridge.main(["--host", "127.0.0.1", "--port", "1", "--timeout", "2", "ping"])
    assert code == 3


def test_bridge_script_keeps_its_promises():
    with open(BRIDGE, "rb") as handle:
        raw = handle.read()
    source = raw.decode("ascii")                     # pure ASCII, no console flashes
    assert "TcpListener" in source                   # no admin-only HTTP.sys/urlacl
    assert "HttpListener" not in source
    assert "IsLoopback" in source and "192" in source and "172" in source
    assert "X-CGMD-Token" in source or "x-cgmd-token" in source
    assert "-AllowShell" in source and "shell is disabled" in source
    assert "netsh advfirewall" in source             # documented, opt-in
    for kind in ("ping", "status", "smoke", "selfcheck", "gmx"):
        assert "'%s'" % kind in source, kind
    assert "cgmd.mailbox.result.v1" in source
