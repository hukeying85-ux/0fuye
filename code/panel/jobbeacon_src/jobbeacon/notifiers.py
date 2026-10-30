"""Zero-cost multi-channel alert dispatcher for JobBeacon.

Supports outbound push without paid subscriptions:
- Local PWA / Web Notification ring-buffer (instant zero-config)
- ntfy (https://ntfy.sh/<topic> or self-hosted, 100% free iOS/Android/Web)
- Bark (iOS APNs gateway)
- ServerChan / PushPlus (WeChat message gateway)
- Generic JSON Webhook (Feishu / DingTalk / Discord / Slack)
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def _utc_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def format_completion_card(
    title: str,
    status: str,
    summary: str,
    elapsed_sec: float | None = None,
    host: str = "",
) -> dict[str, str]:
    """Build concise mobile notification headline and body."""
    badge = {
        "completed": "✅ 已完成",
        "failed": "❌ 异常中断",
        "running": "⚡ 开始运行",
        "pending": "⏳ 排队中",
    }.get(status, f"🔔 {status}")

    dur = ""
    if elapsed_sec is not None and elapsed_sec >= 0:
        mins, sec = divmod(int(round(elapsed_sec)), 60)
        hrs, mins = divmod(mins, 60)
        dur = f"{hrs}h{mins:02d}m" if hrs else f"{mins}m{sec:02d}s"

    head = f"[{badge}] {title}"
    lines = [summary]
    meta = [x for x in (f"耗时 {dur}" if dur else "", f"节点 {host}" if host else "") if x]
    if meta:
        lines.append(" · ".join(meta))
    return {"headline": head, "body": "\n".join(lines), "status": status, "timestamp": _utc_iso()}


def dispatch_alert(
    endpoints: list[str],
    title: str,
    status: str,
    summary: str,
    *,
    elapsed_sec: float | None = None,
    host: str = "",
    store_dir: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Send completion/transition alert to configured free channels and local PWA feed."""
    card = format_completion_card(title, status, summary, elapsed_sec=elapsed_sec, host=host)
    deliveries: list[dict[str, Any]] = []

    if store_dir is not None:
        store_dir.mkdir(parents=True, exist_ok=True)
        feed_file = store_dir / "alerts.jsonl"
        record = {
            "id": f"alrt-{int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)}",
            **card,
        }
        with feed_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        deliveries.append({"channel": "pwa-local-feed", "ok": True})

    for raw_ep in endpoints or []:
        ep = raw_ep.strip()
        if not ep:
            continue
        if dry_run:
            deliveries.append({"channel": ep.split(":", 1)[0], "ok": True, "dry_run": True})
            continue
        deliveries.append(_send_single_endpoint(ep, card["headline"], card["body"], status))

    return {"ok": all(d.get("ok") for d in deliveries), "card": card, "deliveries": deliveries}


def _send_single_endpoint(endpoint: str, headline: str, body: str, status: str) -> dict[str, Any]:
    try:
        if endpoint.startswith("ntfy:") or endpoint.startswith("ntfy://"):
            topic = endpoint.split(":", 1)[1].lstrip("/")
            if topic.startswith("http"):
                base_srv, topic_name = topic.rsplit("/", 1)
            else:
                base_srv, topic_name = "https://ntfy.sh", topic
            payload_bytes = json.dumps(
                {
                    "topic": topic_name,
                    "title": headline,
                    "message": body,
                    "priority": 5 if status in ("completed", "failed") else 4,
                    "tags": ["warning"] if status == "failed" else ["tada", "computer"],
                },
                ensure_ascii=False,
            ).encode("utf-8")
            try:
                req = urllib.request.Request(
                    base_srv.rstrip("/"),
                    data=payload_bytes,
                    method="POST",
                    headers={"Content-Type": "application/json; charset=utf-8"},
                )
                with urllib.request.urlopen(req, timeout=7) as resp:
                    if 200 <= resp.status < 300:
                        return {"channel": "ntfy", "ok": True, "http_status": resp.status, "via": "direct"}
            except Exception as direct_err:
                import os, subprocess
                if os.name == "nt":
                    for proxy_args in ([], ["-x", "socks5h://127.0.0.1:10808"]):
                        try:
                            cp = subprocess.run(
                                ["curl.exe", "-sS", "-m", "8", *proxy_args, "-H", "Content-Type: application/json; charset=utf-8", "--data-binary", "@-", base_srv.rstrip("/")],
                                input=payload_bytes,
                                capture_output=True,
                                timeout=10,
                                creationflags=0x08000000,
                            )
                            if cp.returncode == 0 and b'"id"' in cp.stdout:
                                return {"channel": "ntfy", "ok": True, "http_status": 200, "via": "curl_proxy" if proxy_args else "curl_direct"}
                        except Exception:
                            pass
                return {"channel": "ntfy", "ok": False, "error": str(direct_err)[:160]}

        if endpoint.startswith("bark:") or endpoint.startswith("bark://"):
            key_or_url = endpoint.split(":", 1)[1].lstrip("/")
            base = key_or_url if key_or_url.startswith("http") else f"https://api.day.app/{key_or_url}"
            payload = json.dumps({"title": headline, "body": body, "group": "JobBeacon"}).encode("utf-8")
            req = urllib.request.Request(
                base.rstrip("/"),
                data=payload,
                method="POST",
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                return {"channel": "bark", "ok": 200 <= resp.status < 300, "http_status": resp.status}

        if endpoint.startswith("serverchan:"):
            skey = endpoint.split(":", 1)[1].strip("/")
            url = f"https://sctapi.ftqq.com/{urllib.parse.quote(skey)}.send"
            form = urllib.parse.urlencode({"title": headline[:100], "desp": body}).encode("utf-8")
            req = urllib.request.Request(url, data=form, method="POST")
            with urllib.request.urlopen(req, timeout=8) as resp:
                return {"channel": "serverchan", "ok": 200 <= resp.status < 300, "http_status": resp.status}

        if endpoint.startswith(("http://", "https://", "webhook:")):
            url = endpoint[len("webhook:") :] if endpoint.startswith("webhook:") else endpoint
            payload = json.dumps(
                {
                    "msg_type": "text",
                    "content": {"text": f"{headline}\n{body}"},
                    "text": f"{headline}\n{body}",
                },
                ensure_ascii=False,
            ).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                method="POST",
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                return {"channel": "webhook", "ok": 200 <= resp.status < 300, "http_status": resp.status}

        return {"channel": "unknown", "ok": False, "error": f"Unsupported scheme: {endpoint[:16]}"}
    except Exception as exc:
        return {"channel": endpoint.split(":", 1)[0], "ok": False, "error": str(exc)[:160]}
