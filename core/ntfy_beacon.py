"""Zero-token push beacon for the Xiaomi phone via ``https://ntfy.sh``.

The phone already subscribes to the topic ``arena-beacon-95bc796a66``.  This
module owns *all* outbound notification logic so that behaviour is identical
whether the message is sent from WSL2 (``node_agent.py``), from the Windows
poller (translates to ``Invoke-RestMethod``) or from the CGMD pipeline.

Guarantees
----------
* no API key, no account, no LLM call -> exactly zero token cost;
* UTF-8 JSON body posted to ``https://ntfy.sh`` (the documented "JSON publish"
  endpoint), ``priority: 5`` (max) so the Xiaomi device vibrates and pops up;
* a Beijing (``Asia/Shanghai``) timestamp is always part of the message text;
* network problems never raise: the caller gets ``False`` and may retry later.

Example
-------
>>> from core.ntfy_beacon import Beacon
>>> Beacon(topic="arena-beacon-95bc796a66").send("CGMD ready", "desktop online")
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from .task_contract import beijing_iso, beijing_now

__all__ = ["DEFAULT_SERVER", "DEFAULT_TOPIC", "Beacon", "format_message"]

DEFAULT_SERVER = "https://ntfy.sh"
DEFAULT_TOPIC = os.environ.get("CGMD_NTFY_TOPIC", "arena-beacon-95bc796a66")
DEFAULT_PRIORITY = 5

TAGS_BY_EVENT = {
    "start": ["rocket"],
    "progress": ["hourglass_flowing_sand"],
    "done": ["white_check_mark", "tada"],
    "error": ["rotating_light", "warning"],
    "pore": ["droplet"],
    "hub": ["desktop_computer"],
    "test": ["bell"],
}


def format_message(
    headline: str,
    lines: Optional[List[str]] = None,
    event: str = "info",
    moment: Optional[str] = None,
) -> str:
    """Compose the notification body: headline, ASCII/UTF-8 lines, BJ time."""
    stamp = moment or beijing_iso(beijing_now())
    body = [headline.strip()] if headline else []
    for line in lines or []:
        if line is None:
            continue
        text = str(line).rstrip()
        if text:
            body.append(text)
    body.append("北京时间 {}".format(stamp))
    return "\n".join(body)


class Beacon:
    """Minimal ntfy publisher (stdlib only, safe to call from any thread)."""

    def __init__(
        self,
        topic: str = DEFAULT_TOPIC,
        server: str = DEFAULT_SERVER,
        timeout: float = 8.0,
        retries: int = 2,
        priority: int = DEFAULT_PRIORITY,
        dry_run: bool = False,
        user_agent: str = "cgmd-engine/1.0 (+github.com/hukeying85-ux/0fuye)",
    ) -> None:
        self.topic = (topic or DEFAULT_TOPIC).strip()
        self.server = (server or DEFAULT_SERVER).rstrip("/")
        self.timeout = float(timeout)
        self.retries = max(0, int(retries))
        self.priority = int(priority)
        self.dry_run = bool(dry_run)
        self.user_agent = user_agent
        self.history: List[Dict[str, Any]] = []

    # -- payload ----------------------------------------------------------
    def build_payload(
        self,
        title: str,
        message: str,
        event: str = "info",
        tags: Optional[List[str]] = None,
        click: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "topic": self.topic,
            "title": (title or "CGMD")[:120],
            "message": message or "",
            "priority": self.priority,
            "tags": list(tags if tags is not None else TAGS_BY_EVENT.get(event, [])),
        }
        if click:
            payload["click"] = click
        for key, value in (extra or {}).items():
            if value is not None:
                payload[key] = value
        return payload

    # -- transport --------------------------------------------------------
    def send_payload(self, payload: Dict[str, Any]) -> bool:
        """POST a prepared payload to ntfy; returns True on HTTP 200/2xx."""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        record = {
            "at": beijing_iso(),
            "topic": payload.get("topic"),
            "title": payload.get("title"),
            "bytes": len(body),
            "ok": False,
        }
        if self.dry_run:
            record["ok"] = True
            record["dry_run"] = True
            self.history.append(record)
            print("[ntfy:dry-run] {} | {}".format(payload.get("title"), payload.get("message")), file=sys.stderr)
            return True

        last_error = ""
        for attempt in range(self.retries + 1):
            request = urllib.request.Request(
                self.server,
                data=body,
                method="POST",
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "User-Agent": self.user_agent,
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    status = getattr(response, "status", 200)
                    response.read(2048)
                if 200 <= int(status) < 300:
                    record["ok"] = True
                    record["status"] = int(status)
                    self.history.append(record)
                    return True
                last_error = "HTTP {}".format(status)
            except urllib.error.HTTPError as exc:
                last_error = "HTTP {}: {}".format(exc.code, exc.reason)
                if exc.code in (400, 401, 403, 404):
                    break  # config problem: retrying will not help
            except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
                last_error = "network: {}".format(exc)
            if attempt < self.retries:
                time.sleep(min(2.0 * (attempt + 1), 5.0))
        record["error"] = last_error
        self.history.append(record)
        return False

    def send(
        self,
        title: str,
        message: str,
        event: str = "info",
        tags: Optional[List[str]] = None,
        click: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> bool:
        payload = self.build_payload(title, message, event=event, tags=tags, click=click, extra=extra)
        return self.send_payload(payload)

    # -- convenience ------------------------------------------------------
    def send_event(
        self,
        event: str,
        headline: str,
        lines: Optional[List[str]] = None,
        title: Optional[str] = None,
        click: Optional[str] = None,
    ) -> bool:
        message = format_message(headline, lines, event=event)
        return self.send(title or "[CGMD] {}".format(event), message, event=event, click=click)

    def ping(self) -> bool:
        """Self-test: send a tiny heartbeat to the phone topic."""
        return self.send_event(
            "test",
            "链路自检：台式机守护已就绪",
            ["如果你在小米手机上看到这条，说明 ntfy 推送链路通畅。"],
            title="[CGMD] 链路自检",
        )


def main(argv: Optional[List[str]] = None) -> int:  # pragma: no cover - cli helper
    import argparse

    parser = argparse.ArgumentParser(description="Send a test beacon to the phone")
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--server", default=DEFAULT_SERVER)
    parser.add_argument("--message", default="CGMD-Engine beacon test")
    parser.add_argument("--title", default="[CGMD] test")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    beacon = Beacon(topic=args.topic, server=args.server, dry_run=args.dry_run)
    ok = beacon.send(args.title, format_message(args.message, ["来自 core.ntfy_beacon 的自检"]), event="test")
    print("sent" if ok else "failed")
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
