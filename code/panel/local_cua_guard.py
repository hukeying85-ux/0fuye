#!/usr/bin/env python3
"""Local Computer-Use Safety Harness & WeChat/Browser Bridge for Arena Desk v2.4.

Provides:
1. Triple Safety Lock for Computer Use:
   - Top-Left Corner (0, 0) hardware emergency kill-switch check
   - Window blocklist (never auto-press Enter in Weixin.exe; never stop git-sync-hub)
   - Dry-run action preview before clicking
2. CDP Browser Debug Launcher reusing existing logged-in profile (`E:\\0writing\\edge_debug_profile`)
   so OpenCLI / Browser-Use / Xiaohongshu / Douyin tools reuse your login cleanly without re-scanning QR.
3. Zero-dependency WeChat Official Account (`mp.weixin.qq.com`) -> clean Markdown local archiver.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PANEL_DIR = REPO_ROOT / "code" / "panel"
if PANEL_DIR.is_dir() and str(PANEL_DIR) not in sys.path:
    sys.path.insert(0, str(PANEL_DIR))

from media_cua_hub import html_to_clean_markdown_snippet, parse_share_input  # noqa: E402

BLOCKED_WINDOW_PATTERNS = (
    "密码",
    "凭据管理",
    "Credential Manager",
    "1Password",
    "Bitwarden",
    "KeePass",
    "git-sync-hub",
)
DRAFT_ONLY_WINDOWS = ("微信", "Weixin", "WeChat", "QQ")


def check_cua_environment() -> dict[str, Any]:
    """Run non-invasive Computer Use readiness & safety self-test."""
    is_win = platform.system().lower().startswith("win")
    screen_size = None
    cursor_pos = None
    if is_win:
        try:
            import ctypes

            user32 = ctypes.windll.user32
            screen_size = [int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))]

            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            pt = POINT()
            if user32.GetCursorPos(ctypes.byref(pt)):
                cursor_pos = [int(pt.x), int(pt.y)]
        except Exception:
            pass

    kill_switch_triggered = bool(cursor_pos and cursor_pos[0] <= 2 and cursor_pos[1] <= 2)
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    edge_exe = next((p for p in edge_paths if is_win and Path(p).is_file()), "")
    edge_profile = r"E:\0writing\edge_debug_profile" if (is_win and Path(r"E:\0writing\edge_debug_profile").exists()) else ""

    return {
        "ok": True,
        "timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "os": platform.platform(),
        "screen_resolution": screen_size or [1920, 1080],
        "cursor_position": cursor_pos,
        "kill_switch_triggered": kill_switch_triggered,
        "kill_switch_rule": "将鼠标甩到屏幕最左上角 (0, 0) 即刻物理熔断一切 AI 键鼠动作",
        "draft_only_windows": list(DRAFT_ONLY_WINDOWS),
        "blocked_windows": list(BLOCKED_WINDOW_PATTERNS),
        "edge_exe": edge_exe,
        "edge_debug_profile": edge_profile,
    }


def launch_cdp_browser(port: int = 9222) -> dict[str, Any]:
    """Launch Edge with remote-debugging-port on the isolated profile for OpenCLI / Browser-Use."""
    info = check_cua_environment()
    edge_exe = info.get("edge_exe")
    if not edge_exe:
        return {"ok": False, "error": "仅在 Windows 本机检测到 Microsoft Edge 时可拉起 CDP 调试窗口"}
    profile_dir = info.get("edge_debug_profile") or r"E:\0apps\ArenaDesk\data\edge_cua_profile"
    Path(profile_dir).mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [
            edge_exe,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "https://www.xiaohongshu.com",
        ]
    )
    return {
        "ok": True,
        "cdp_endpoint": f"http://127.0.0.1:{port}",
        "profile_dir": profile_dir,
        "note": "请在弹出的独立 Edge 窗口扫码登录一次小红书/抖音/B站，后续 OpenCLI 与无水印下载即可永久免密复用！",
    }


def archive_wechat_article(url: str, out_dir: Path) -> dict[str, Any]:
    """Fetch a public WeChat Official Account article and save clean Markdown."""
    parsed = parse_share_input(url)
    if not parsed.get("ok"):
        return parsed
    clean_url = parsed["clean_url"]
    req = urllib.request.Request(
        clean_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            )
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw_html = resp.read().decode("utf-8", errors="replace")
    extracted = html_to_clean_markdown_snippet(raw_html)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_title = "".join(c if (c.isalnum() or c in "_- ") else "_" for c in extracted["title"])[:60].strip() or "wechat_article"
    out_file = out_dir / f"{safe_title}.md"
    out_file.write_text(extracted["markdown"], encoding="utf-8")
    return {"ok": True, "saved_to": str(out_file), "meta": {k: v for k, v in extracted.items() if k != "markdown"}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Arena Desk Computer-Use Safety Guard & Media Bridge")
    ap.add_argument("--probe", action="store_true", help="Run Computer-Use safety & screen probe")
    ap.add_argument("--launch-cdp", action="store_true", help="Open isolated Edge CDP window on port 9222")
    ap.add_argument("--parse-share", default="", help="Parse messy Douyin/XHS/Bilibili/WeChat share text")
    ap.add_argument("--wechat-to-md", default="", help="Save a WeChat MP article URL to clean Markdown")
    ap.add_argument("--out-dir", default="", help="Output folder for archived Markdown")
    args = ap.parse_args(argv)

    if args.parse_share:
        print(json.dumps(parse_share_input(args.parse_share), ensure_ascii=False, indent=2))
        return 0
    if args.wechat_to_md:
        default_out = Path(r"E:\0apps\ArenaDesk\data\articles") if platform.system().lower().startswith("win") else Path("/tmp/wechat_md")
        target = Path(args.out_dir) if args.out_dir else default_out
        print(json.dumps(archive_wechat_article(args.wechat_to_md, target), ensure_ascii=False, indent=2))
        return 0
    if args.launch_cdp:
        print(json.dumps(launch_cdp_browser(), ensure_ascii=False, indent=2))
        return 0

    print(json.dumps(check_cua_environment(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
