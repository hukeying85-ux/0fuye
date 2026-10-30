#!/usr/bin/env python3
"""Cross-platform 24x7 Zero-Token Node Agent for Arena 3-Machine Federation.

Runs identically on:
  - Laptop (`mqgg5630-cyber`, Windows)
  - Desktop (`hukeying85-ux`, Windows/Linux GPU Coarse-Grained MD Workstation)
  - HPC (`shaohuawen03-cyber`, Linux Slurm `mu01` `cu`/`fat1` All-Atom MD & Bio)

Key capabilities:
1. Continuous 0-Token watching of GROMACS (All-Atom & Martini 3 Coarse-Grained MD),
   AMBER, OpenMM, ORCA logs, or Slurm `squeue` transitions.
2. Instant "Haoleme / JobBeacon" push notification to mobile (`ntfy.sh` encrypted
   topic or custom Webhook) the exact second a job finishes or diverges.
3. Git large-file safety guardrail: blocks `.xtc/.trr/.tpr/.edr/.cpt` > 5 MB from
   polluting Git, directing bulk trajectories over Plan D (ZeroTier LAN `scp`/`rsync`).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
JB_SRC = REPO_ROOT / "projects" / "jobbeacon" / "src"
if JB_SRC.is_dir() and str(JB_SRC) not in sys.path:
    sys.path.insert(0, str(JB_SRC))

from jobbeacon.analyzers import analyze_md_log, analyze_slurm_table  # noqa: E402
from jobbeacon.notifiers import dispatch_alert  # noqa: E402

ROLE_ACCOUNT_MAP: dict[str, dict[str, str]] = {
    "laptop": {
        "gh_account": "mqgg5630-cyber",
        "ssh_alias": "github.com",
        "label": "笔记本总控中枢 (Commander)",
    },
    "hpc": {
        "gh_account": "shaohuawen03-cyber",
        "ssh_alias": "github-shaohua",
        "label": "HPC 超算毕业课题节点 (mu01 · 全原子MD & AMP模型)",
    },
    "desktop": {
        "gh_account": "hukeying85-ux",
        "ssh_alias": "github-hukeying",
        "label": "台式机粗粒化分子动力学节点 (Martini 3 CG-MD GPU)",
    },
}

FORBIDDEN_GIT_EXTS = {".xtc", ".trr", ".tpr", ".edr", ".cpt", ".dcd", ".nc", ".h5", ".pt", ".ckpt"}
MAX_GIT_FILE_BYTES = 5 * 1024 * 1024  # 5 MB hard cap for federation control repo


def utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def audit_git_staging_safety(directory: Path) -> dict[str, Any]:
    """Ensure heavy MD trajectories never bloat or break Git federation sync."""
    blocked: list[dict[str, Any]] = []
    if not directory.exists():
        return {"safe": True, "blocked_files": []}
    for p in directory.rglob("*"):
        if not p.is_file() or ".git" in p.parts:
            continue
        ext = p.suffix.lower()
        size = p.stat().st_size
        if ext in FORBIDDEN_GIT_EXTS or size > MAX_GIT_FILE_BYTES:
            blocked.append(
                {
                    "path": str(p.relative_to(directory)),
                    "size_mb": round(size / (1024 * 1024), 2),
                    "reason": "轨迹/权重文件走方案D ZeroTier内网直传，严禁入Git",
                }
            )
    return {"safe": len(blocked) == 0, "blocked_files": blocked[:25]}


def load_notify_targets(config_path: Path | None = None) -> list[str]:
    """Load configured 'Haoleme / JobBeacon' notification targets from JSON or env."""
    targets: list[str] = []
    env_spec = os.environ.get("JOBBEACON_NOTIFY", "").strip()
    if env_spec:
        targets.extend([x.strip() for x in env_spec.split(",") if x.strip()])

    candidates = [p for p in [config_path] if p is not None]
    if platform.system().lower().startswith("win"):
        candidates.append(Path(r"E:\0apps\ArenaDesk\data\beacon_notify.json"))
    candidates.append(REPO_ROOT / "results" / "federation" / "beacon_notify_local.json")

    for c in candidates:
        if c and c.is_file():
            try:
                cfg = json.loads(c.read_text(encoding="utf-8"))
                if not cfg.get("enabled", True):
                    continue
                topic = str(cfg.get("ntfy_topic", "")).strip()
                server = str(cfg.get("ntfy_server", "https://ntfy.sh")).strip() or "https://ntfy.sh"
                if topic:
                    if server == "https://ntfy.sh":
                        targets.append(f"ntfy:{topic}")
                    else:
                        targets.append(f"{server.rstrip('/')}/{topic}")
                webhook = str(cfg.get("webhook_url", "")).strip()
                if webhook:
                    targets.append(webhook)
            except Exception:
                continue
    # Deduplicate while preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for t in targets:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def dispatch_completion_alert(
    role: str,
    task_title: str,
    state: str,
    summary: str,
    extra: dict[str, Any] | None = None,
    notify_specs: list[str] | None = None,
) -> dict[str, Any]:
    """Fire immediate 'Haoleme / JobBeacon' alert across all configured channels."""
    specs = notify_specs if notify_specs is not None else load_notify_targets()
    role_meta = ROLE_ACCOUNT_MAP.get(role, ROLE_ACCOUNT_MAP["laptop"])
    body = f"{summary}\n节点：{role_meta['label']}"
    if extra and extra.get("remediation"):
        body += f"\n修复建议：{extra['remediation']}"

    res = dispatch_alert(
        specs,
        f"[{role.upper()}] {task_title}",
        state,
        body,
        host=socket.gethostname(),
    )
    deliveries = res.get("deliveries", [])
    return {
        "notified": any(d.get("ok") for d in deliveries),
        "channel_count": len(deliveries),
        "results": deliveries,
        "card": res.get("card", {}),
    }


def write_node_heartbeat(role: str, payload: dict[str, Any], out_dir: Path | None = None) -> Path:
    hb_dir = out_dir or (REPO_ROOT / "results" / "federation" / "heartbeats")
    hb_dir.mkdir(parents=True, exist_ok=True)
    role_meta = ROLE_ACCOUNT_MAP.get(role, ROLE_ACCOUNT_MAP["laptop"])
    doc = {
        "role": role,
        "hostname": socket.gethostname(),
        "os": platform.platform(),
        "gh_account": role_meta["gh_account"],
        "label": role_meta["label"],
        "updated_at": utc_iso(),
        **payload,
    }
    target = hb_dir / f"{role}.json"
    target.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def watch_md_once_or_loop(
    role: str,
    md_log: Path,
    task_title: str,
    interval: int = 30,
    max_rounds: int = 0,
    notify_specs: list[str] | None = None,
) -> dict[str, Any]:
    """Monitor GROMACS (All-Atom or Martini CG-MD) / AMBER log until completion or failure."""
    rounds = 0
    last_state = ""
    while True:
        rounds += 1
        txt = md_log.read_text(encoding="utf-8", errors="replace")[-65536:] if md_log.is_file() else ""
        parsed = analyze_md_log(txt)
        write_node_heartbeat(role, {"task_title": task_title, "md_status": parsed, "log_path": str(md_log)})
        cur_state = parsed.get("state", "idle")
        if cur_state in ("completed", "failed") and cur_state != last_state:
            alert = dispatch_completion_alert(
                role=role,
                task_title=task_title,
                state=cur_state,
                summary=parsed.get("summary", ""),
                extra=parsed,
                notify_specs=notify_specs,
            )
            return {"status": cur_state, "md": parsed, "alert": alert}
        last_state = cur_state
        if max_rounds > 0 and rounds >= max_rounds:
            return {"status": cur_state, "md": parsed, "alert": None}
        time.sleep(max(2, interval))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="node_agent", description="Arena 3-Account x 3-Machine Zero-Token Sentinel")
    ap.add_argument("--role", choices=("laptop", "hpc", "desktop"), default="desktop")
    ap.add_argument("--task-title", default="Martini 3 粗粒化分子动力学筛选")
    ap.add_argument("--md-log", default="", help="Path to GROMACS md.log or AMBER mdout")
    ap.add_argument("--interval", type=int, default=30)
    ap.add_argument("--once", action="store_true", help="Run a single inspection round and exit")
    ap.add_argument("--notify", action="append", default=[], help="ntfy:<topic> or webhook URL")
    ap.add_argument("--test-notify", action="store_true", help="Send an immediate test notification")
    args = ap.parse_args(argv)

    specs = args.notify if args.notify else None
    if args.test_notify:
        res = dispatch_completion_alert(
            role=args.role,
            task_title=args.task_title,
            state="completed",
            summary="『好了吗』跨网通知链路自检成功！后续动力学跑完或报错将毫秒级推送至手机。",
            notify_specs=specs,
        )
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    if args.md_log:
        out = watch_md_once_or_loop(
            role=args.role,
            md_log=Path(args.md_log),
            task_title=args.task_title,
            interval=args.interval,
            max_rounds=1 if args.once else 0,
            notify_specs=specs,
        )
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    hb = write_node_heartbeat(args.role, {"status": "online", "safety": audit_git_staging_safety(REPO_ROOT)})
    print(json.dumps({"ok": True, "heartbeat": str(hb)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
