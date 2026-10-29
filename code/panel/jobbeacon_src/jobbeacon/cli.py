"""Command-line entry point (`jb`) for JobBeacon.

Examples:
    jb status
    jb run --title "GROMACS 100ns Production" --notify ntfy:my-lab -- gmx mdrun -deffnm md_0_1
    jb watch-md ./md_0_1.log --notify ntfy:my-lab
    jb pair --port 18765
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

from .analyzers import analyze_dl_or_bio_log, analyze_md_log
from .ledger import BeaconLedger
from .notifiers import dispatch_alert


def _default_store() -> Path:
    env = os.environ.get("JOBBEACON_HOME", "").strip()
    if env:
        return Path(env)
    if platform.system().lower().startswith("win"):
        win_dir = Path(r"E:\0apps\ArenaDesk\data\jobbeacon")
        if win_dir.parent.parent.exists():
            return win_dir
    return Path.home() / ".jobbeacon"


def _cmd_run(args: argparse.Namespace, ledger: BeaconLedger) -> int:
    cmd = list(args.command)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("Error: missing command after `jb run`", file=sys.stderr)
        return 2

    title = args.title or " ".join(cmd)[:72]
    watch_id = f"jb-{int(time.time() * 1000)}"
    t0 = time.monotonic()
    ring: deque[str] = deque(maxlen=60)

    ledger.upsert_watch(
        {
            "id": watch_id,
            "title": title,
            "kind": args.kind,
            "target": f"{platform.node()} · {' '.join(cmd[:3])}",
            "state": "running",
            "percent": 0.0,
            "eta_human": "启动中",
            "summary": f"已启动命令：{' '.join(cmd)}",
            "log_tail": "",
        }
    )

    last_flush = t0
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=0x08000000 if os.name == "nt" else 0,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        ring.append(line.rstrip("\r\n"))
        now = time.monotonic()
        if now - last_flush >= 2.0:
            last_flush = now
            tail_str = "\n".join(ring)
            ledger.upsert_watch(
                {
                    "id": watch_id,
                    "title": title,
                    "kind": args.kind,
                    "state": "running",
                    "log_tail": tail_str,
                }
            )

    rc = proc.wait()
    elapsed = time.monotonic() - t0
    final_state = "completed" if rc == 0 else "failed"
    tail_str = "\n".join(ring)
    parsed = analyze_md_log(tail_str) if args.kind == "md" else analyze_dl_or_bio_log(tail_str)
    summary = (
        parsed.get("summary")
        if args.kind == "md"
        else f"退出码 {rc} · {parsed.get('stage') or '执行完毕'}"
    )
    ledger.upsert_watch(
        {
            "id": watch_id,
            "title": title,
            "kind": args.kind,
            "state": final_state,
            "percent": 100.0 if rc == 0 else parsed.get("percent", 0.0),
            "eta_human": "已完成" if rc == 0 else f"失败 (exit={rc})",
            "summary": summary,
            "log_tail": tail_str,
        }
    )

    endpoints = list(args.notify or ledger.get_notify_config().get("endpoints", []))
    dispatch_alert(
        endpoints,
        title,
        final_state,
        str(summary),
        elapsed_sec=elapsed,
        host=platform.node(),
        store_dir=ledger.store_dir,
        dry_run=args.dry_notify,
    )
    return rc


def _cmd_watch_md(args: argparse.Namespace, ledger: BeaconLedger) -> int:
    log_path = Path(args.log_file)
    if not log_path.is_file():
        print(f"Error: MD log file not found: {log_path}", file=sys.stderr)
        return 1
    content = log_path.read_text(encoding="utf-8", errors="replace")[-32000:]
    info = analyze_md_log(content)
    item = ledger.upsert_watch(
        {
            "id": f"md-{log_path.stem}",
            "title": args.title or f"{info['engine']} 动力学监控 · {log_path.name}",
            "kind": "md",
            "target": str(log_path),
            "state": info["state"],
            "percent": info["percent"],
            "eta_human": info["eta_human"],
            "speed_badge": f"{info.get('speed_ns_day', 0)} ns/day",
            "summary": info["summary"],
            "log_tail": content[-1800:],
        }
    )
    print(json.dumps({"ok": True, "analysis": info, "watch": item}, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jb",
        description="JobBeacon (算力信标) — Slurm / Molecular Dynamics / Long-Task Mobile Watcher",
    )
    parser.add_argument("--store", default="", help="Custom state directory")
    sub = parser.add_subparsers(dest="subcmd")

    sub.add_parser("status", help="Print JSON snapshot of watched jobs, alerts, and mobile connectivity")

    p_pair = sub.add_parser("pair", help="Generate HMAC mobile pairing URL & PIN")
    p_pair.add_argument("--port", type=int, default=18765)

    p_md = sub.add_parser("watch-md", help="Inspect a GROMACS/AMBER/OpenMM/ORCA log file")
    p_md.add_argument("log_file", help="Path to md.log / mdout")
    p_md.add_argument("--title", default="")

    p_run = sub.add_parser("run", help="Wrap any command and send mobile push on completion")
    p_run.add_argument("--title", default="")
    p_run.add_argument("--kind", choices=["cmd", "md", "slurm", "bio-dl"], default="cmd")
    p_run.add_argument("--notify", action="append", default=[], help="Notification target (e.g. ntfy:topic)")
    p_run.add_argument("--dry-notify", action="store_true", help="Record alert locally without external HTTP")
    p_run.add_argument("command", nargs=argparse.REMAINDER)

    args = parser.parse_args(argv)
    store_dir = Path(args.store) if args.store else _default_store()
    ledger = BeaconLedger(store_dir, seed_demo=False)

    if args.subcmd == "run":
        return _cmd_run(args, ledger)
    if args.subcmd == "watch-md":
        return _cmd_watch_md(args, ledger)
    if args.subcmd == "pair":
        snap = ledger.snapshot(port=args.port)
        print(json.dumps(snap["connectivity"]["pairing"], ensure_ascii=False, indent=2))
        return 0

    print(json.dumps(ledger.snapshot(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
