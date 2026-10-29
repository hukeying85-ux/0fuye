"""LAN client for the desktop bridge (``Invoke-CgmdBridge.ps1``).

Two transports reach the workstation:

* ``core.hub_mailbox`` - through git, works from anywhere, latency is one poll
  interval (<= 60 s);
* this module - direct HTTP over the LAN, sub-second, needs the desktop to be
  running the bridge and the laptop to be on the same network.

The bridge answers with the same ``cgmd.mailbox.result.v1`` shape, so a caller
can fall back from one to the other without changing how it reads results.

CLI
---
    python3 -m core.desk_bridge ping --host 192.168.1.23
    python3 -m core.desk_bridge status --host 192.168.1.23
    python3 -m core.desk_bridge smoke  --host 192.168.1.23 --timeout 900
    python3 -m core.desk_bridge gmx    --host 192.168.1.23 -- --version
"""

import argparse
import http.client
import json
import socket
import sys
import time
from typing import Any, Dict, List, Optional

DEFAULT_PORT = 8765
SCHEMA_RESULT = "cgmd.mailbox.result.v1"


class BridgeError(RuntimeError):
    pass


def _request(host: str, port: int, method: str, path: str, payload: Optional[Dict[str, Any]] = None,
             token: str = "", timeout: int = 30) -> Dict[str, Any]:
    body = None
    headers = {"Accept": "application/json", "User-Agent": "cgmd-desk-bridge/1"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = str(len(body))
    if token:
        headers["X-CGMD-Token"] = token
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
    except (socket.timeout, OSError) as exc:
        raise BridgeError("cannot reach %s:%d (%s)" % (host, port, exc))
    finally:
        connection.close()
    text = raw.decode("utf-8", "replace")
    try:
        document = json.loads(text) if text.strip() else {}
    except ValueError:
        document = {"status": "error", "summary": text[:400]}
    if response.status >= 400:
        document.setdefault("status", "error")
        document["http_status"] = response.status
    return document


def ping(host: str, port: int = DEFAULT_PORT, token: str = "", timeout: int = 10) -> Dict[str, Any]:
    return _request(host, port, "GET", "/health", token=token, timeout=timeout)


def status(host: str, port: int = DEFAULT_PORT, token: str = "", timeout: int = 20) -> Dict[str, Any]:
    return _request(host, port, "GET", "/status", token=token, timeout=timeout)


def job(host: str, port: int, kind: str, args: Optional[Dict[str, Any]] = None,
        token: str = "", timeout: int = 60) -> Dict[str, Any]:
    payload = {"kind": kind, "args": args or {}}
    return _request(host, port, "POST", "/job", payload=payload, token=token, timeout=timeout)


def smoke(host: str, port: int = DEFAULT_PORT, ps: float = 100, token: str = "",
          timeout: int = 1800) -> Dict[str, Any]:
    return job(host, port, "smoke", {"ps": ps}, token=token, timeout=timeout)


def gmx(host: str, port: int, argv: List[str], token: str = "", timeout: int = 300) -> Dict[str, Any]:
    return job(host, port, "gmx", {"argv": list(argv)}, token=token, timeout=timeout)


def wait_ready(host: str, port: int = DEFAULT_PORT, token: str = "", attempts: int = 5,
               delay: float = 1.0) -> bool:
    for index in range(max(1, attempts)):
        try:
            answer = ping(host, port, token=token, timeout=5)
            if answer.get("status") == "ok":
                return True
        except BridgeError:
            pass
        if index + 1 < attempts:
            time.sleep(delay)
    return False


def _print(document: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m core.desk_bridge",
                                     description="talk to the CGMD desktop over the LAN")
    parser.add_argument("--host", required=True, help="desktop IP or hostname")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--token", default="", help="bridge_token from the desktop config, if set")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("command", choices=["ping", "status", "smoke", "selfcheck", "gmx", "shell"])
    parser.add_argument("rest", nargs=argparse.REMAINDER, help="gmx command line, e.g. -- --version")
    args = parser.parse_args(argv)

    try:
        if args.command == "ping":
            _print(ping(args.host, args.port, token=args.token, timeout=args.timeout))
            return 0
        if args.command == "status":
            _print(status(args.host, args.port, token=args.token, timeout=args.timeout))
            return 0
        if args.command == "smoke":
            document = smoke(args.host, args.port, token=args.token,
                             timeout=max(args.timeout, 900))
        elif args.command == "selfcheck":
            document = job(args.host, args.port, "selfcheck", {}, token=args.token,
                           timeout=max(args.timeout, 600))
        elif args.command == "gmx":
            words = [word for word in args.rest if word != "--"]
            if not words:
                sys.stderr.write("give a gmx command after --, e.g. -- --version\n")
                return 2
            document = gmx(args.host, args.port, words, token=args.token, timeout=args.timeout)
        else:
            words = [word for word in args.rest if word != "--"]
            document = job(args.host, args.port, "shell", {"command": " ".join(words)},
                           token=args.token, timeout=args.timeout)
    except BridgeError as exc:
        _print({"schema": SCHEMA_RESULT, "status": "error", "summary": str(exc)})
        return 3

    _print(document)
    return 0 if document.get("status") == "ok" else 6


if __name__ == "__main__":
    sys.exit(main())
