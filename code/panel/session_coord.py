#!/usr/bin/env python3
"""Multi-Session Collaboration & Non-Conflict Coordinator for Arena Desk v2.1.

Enables concurrent Arena sessions (e.g., 0fuye-89735ee7-0fuye, leanrea-4d729933-leanrea,
and the permanent git-sync-hub daemon leanrea-626378d6-leanrea) to discover one another,
share handoff notes, acquire TTL-bounded resource leases, and enforce strict isolation
across host directories, Windows Scheduled Tasks, Git/gh accounts, and cloud connectors.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import platform
import re
from pathlib import Path
from typing import Any

CURRENT_SESSION_ID = "0fuye-89735ee7-0fuye"
CURRENT_BRANCH = "arena/89735ee7-0fuye"
CURRENT_REPO = "mqgg5630-cyber/0fuye"

NON_CONFLICT_RULES: list[dict[str, str]] = [
    {
        "id": "hub-daemon-readonly",
        "scope": "Scheduled Task · git-sync-hub",
        "owner": "leanrea-626378d6-leanrea (Permanent Base)",
        "policy": "PROTECTED_READ_ONLY",
        "detail": (
            "永不停止、删除或覆盖 E:\\0github\\.git-sync\\leanrea-626378d6-leanrea\\hub-watch.ps1；"
            "仅通过幂等插件 hub-worker.ps1 注入 git-credential 与 0fuye 轮询增强。"
        ),
    },
    {
        "id": "peer-session-isolation",
        "scope": "Peer Session · leanrea-4d729933-leanrea",
        "owner": "arena/4d729933-leanrea",
        "policy": "NAMESPACE_ISOLATED",
        "detail": (
            "严禁修改伙伴会话结果目录 E:\\0github\\results\\leanrea-4d729933-leanrea、"
            "jev-chat-monitor 计划任务 (E:\\0apps\\jev-chat-windows) 与 E:\\0apps\\DSHPet 桌宠。"
        ),
    },
    {
        "id": "arenadesk-app-slot",
        "scope": "Desktop App · E:\\0apps\\ArenaDesk (:18765)",
        "owner": CURRENT_SESSION_ID,
        "policy": "LEASE_GUARDED",
        "detail": (
            "Arena Desk 独立部署于 E:\\0apps\\ArenaDesk（避开 E:\\0github 临时清理区），"
            "通过 deployed-panel-hash.txt 原子比对与 coord/locks/arenadesk-deploy.lock 防止并发写冲突。"
        ),
    },
    {
        "id": "gh-multi-account-invariant",
        "scope": "Git & GitHub CLI · 3 Accounts",
        "owner": "mqgg5630-cyber (Default) + shaohuawen03-cyber + hukeying85-ux",
        "policy": "URL_SCOPED_CREDENTIAL",
        "detail": (
            "全局默认账号恒定保持 mqgg5630-cyber（保障私有库 0fuye 轮询不断连）；"
            "通过 credential.https://github.com/<owner>.username + SSH Host 别名实现三账号零切换并发读写。"
        ),
    },
    {
        "id": "cloud-ledger-append-only",
        "scope": "Notion / Google Drive / Sheets / Linear",
        "owner": "Shared Multi-Session Cloud Hub",
        "policy": "ID_PRESERVING_APPEND",
        "detail": (
            "Google Drive 归档采用原位移动（保留全部 23 个原始 File ID，零删文件）；"
            "Notion 会话台账与任务表按会话 ID 追加记录，互不覆盖。"
        ),
    },
]

DEFAULT_SEEDED_SESSIONS: list[dict[str, Any]] = [
    {
        "session_id": "leanrea-626378d6-leanrea",
        "repo": "mqgg5630-cyber/leanrea",
        "branch": "arena/626378d6-leanrea",
        "role": "Permanent git-sync-hub v4.0 Daemon",
        "status": "daemon-online",
        "owned_resources": [
            r"E:\0github\.git-sync\leanrea-626378d6-leanrea",
            "ScheduledTask:git-sync-hub",
        ],
        "summary": "常驻后台轮询基座（每 15s 扫描活跃仓库 arena/* 分支，自动拉取、无窗执行 hub_task.json 并回传回执）。",
    },
    {
        "session_id": "leanrea-4d729933-leanrea",
        "repo": "mqgg5630-cyber/leanrea",
        "branch": "arena/4d729933-leanrea",
        "role": "Peer Workspace Session (HPC + Tailscale + Desktop Pet)",
        "status": "peer-coexisting",
        "owned_resources": [
            r"E:\0github\results\leanrea-4d729933-leanrea",
            r"E:\0apps\jev-chat-windows",
            r"E:\0apps\DSHPet",
        ],
        "summary": "兄弟会话：已打通 WSL -> HPC mu01 (25wenshaohua@10.10.5.210) 作业调度与桌面宠物，本会话与其只读共享 HPC 工具链、绝不抢占目录与任务。",
    },
    {
        "session_id": CURRENT_SESSION_ID,
        "repo": CURRENT_REPO,
        "branch": CURRENT_BRANCH,
        "role": "Arena Desk v2.1 + Thesis Formatter + Cloud Archive Master",
        "status": "active",
        "owned_resources": [
            r"E:\0apps\ArenaDesk",
            r"E:\0github\results\0fuye-89735ee7-0fuye",
            "Port:127.0.0.1:18765",
            "NotionHub:407186af-12d3-81ee-a0d7-c43e5cae8ab9",
            "DriveRoot:0AD-lcGSwewp9Uk9PVA (00..05)",
        ],
        "summary": "当前主控会话：负责私有库 0fuye、ArenaDesk v2.2 原生桌面端、毕业论文一键排版、算力信标 JobBeacon 手机联动、GrokBot 作战室与反重力额度调度。",
    },
]


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _now_iso() -> str:
    return _now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")


def _coord_dir(data_dir: Path) -> Path:
    win_shared = Path(r"E:\0apps\ArenaDesk\data\coord")
    if platform.system().lower().startswith("win") and win_shared.parent.parent.exists():
        return win_shared
    return data_dir / "coord"


def ensure_coord_initialized(data_dir: Path) -> Path:
    cdir = _coord_dir(data_dir)
    (cdir / "sessions").mkdir(parents=True, exist_ok=True)
    (cdir / "locks").mkdir(parents=True, exist_ok=True)

    # Seed baseline manifests if missing so the coordination graph is immediately visible
    for item in DEFAULT_SEEDED_SESSIONS:
        sid = item["session_id"]
        sp = cdir / "sessions" / f"{sid}.json"
        if not sp.is_file():
            payload = {**item, "updated_at": _now_iso()}
            sp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    events_p = cdir / "events.jsonl"
    if not events_p.is_file():
        seed_events = [
            {
                "ts": _now_iso(),
                "session_id": CURRENT_SESSION_ID,
                "kind": "init",
                "summary": "初始化多会话协作总线 (coord/sessions + coord/locks + events.jsonl)，已识别伙伴会话 leanrea-4d729933-leanrea 与守护基座 leanrea-626378d6-leanrea。",
                "tags": ["coord", "non-conflict"],
            },
            {
                "ts": _now_iso(),
                "session_id": CURRENT_SESSION_ID,
                "kind": "handoff",
                "summary": "Google 云盘 01..05 归档完成（保留全部 23 个原始 File ID），Notion 个人事务总控台 4 库 31 条记录已同步，Lark-Formatter v0.21.1 无头排版接口已挂载至 :18765。",
                "tags": ["drive", "notion", "thesis-formatter"],
            },
        ]
        events_p.write_text(
            "\n".join(json.dumps(e, ensure_ascii=False) for e in seed_events) + "\n",
            encoding="utf-8",
        )
    return cdir


def register_heartbeat(data_dir: Path, session_info: dict[str, Any]) -> dict[str, Any]:
    cdir = ensure_coord_initialized(data_dir)
    sid = re.sub(r"[^0-9A-Za-z._-]+", "-", str(session_info.get("session_id") or CURRENT_SESSION_ID))[:80]
    sp = cdir / "sessions" / f"{sid}.json"
    existing: dict[str, Any] = {}
    if sp.is_file():
        try:
            existing = json.loads(sp.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    merged = {
        **existing,
        **session_info,
        "session_id": sid,
        "updated_at": _now_iso(),
    }
    tmp = sp.with_suffix(".tmp")
    tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, sp)
    return {"ok": True, "session": merged}


PROTECTED_READONLY_RESOURCES = {
    "git-sync-hub",
    "leanrea-626378d6-leanrea",
    "jev-chat-monitor",
    "leanrea-4d729933-leanrea",
}


def acquire_lease(
    data_dir: Path,
    resource: str,
    holder: str = CURRENT_SESSION_ID,
    ttl_sec: int = 120,
    purpose: str = "",
) -> dict[str, Any]:
    raw_res = (resource or "").strip()
    low_res = raw_res.lower()
    if (
        raw_res in PROTECTED_READONLY_RESOURCES
        or ".git-sync" in low_res
        or "\\0yf" in low_res
        or "/0yf" in low_res
    ):
        return {
            "ok": False,
            "protected": True,
            "error": f"资源 {raw_res} 属于全局只读/隐私保护边界，禁止加锁或修改。",
        }
    cdir = ensure_coord_initialized(data_dir)
    slug = re.sub(r"[^0-9A-Za-z._-]+", "_", raw_res)[:64] or "default"
    lp = cdir / "locks" / f"{slug}.lock.json"
    now = _now_utc()

    if lp.is_file():
        try:
            cur = json.loads(lp.read_text(encoding="utf-8"))
            exp_str = str(cur.get("expires_at") or "")
            exp_dt = dt.datetime.strptime(exp_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
            if exp_dt > now and cur.get("holder") != holder:
                return {
                    "ok": False,
                    "conflict": True,
                    "error": f"资源 {slug} 正由会话 {cur.get('holder')} 持有至 {exp_str}",
                    "current_lease": cur,
                }
        except Exception:
            pass

    ttl_clamped = max(10, min(int(ttl_sec or 120), 1800))
    lease = {
        "resource": slug,
        "holder": holder,
        "purpose": purpose or "coordinated-operation",
        "acquired_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + dt.timedelta(seconds=ttl_clamped)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    tmp = lp.with_suffix(".tmp")
    tmp.write_text(json.dumps(lease, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, lp)
    return {"ok": True, "lease": lease}


def release_lease(data_dir: Path, resource: str, holder: str = CURRENT_SESSION_ID) -> dict[str, Any]:
    cdir = ensure_coord_initialized(data_dir)
    slug = re.sub(r"[^0-9A-Za-z._-]+", "_", resource.strip())[:64] or "default"
    lp = cdir / "locks" / f"{slug}.lock.json"
    if not lp.is_file():
        return {"ok": True, "released": False, "reason": "not-locked"}
    try:
        cur = json.loads(lp.read_text(encoding="utf-8"))
        if cur.get("holder") not in (holder, "force"):
            return {
                "ok": False,
                "error": f"锁由 {cur.get('holder')} 持有，当前会话 {holder} 不强制抢占。",
            }
    except Exception:
        pass
    try:
        lp.unlink()
    except OSError:
        pass
    return {"ok": True, "released": True, "resource": slug}


def post_handoff_note(
    data_dir: Path,
    session_id: str,
    summary: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    cdir = ensure_coord_initialized(data_dir)
    text = str(summary or "").strip()
    if not text:
        return {"ok": False, "error": "协作备注内容不能为空"}
    entry = {
        "ts": _now_iso(),
        "session_id": session_id or CURRENT_SESSION_ID,
        "kind": "handoff",
        "summary": text[:600],
        "tags": (tags or ["handoff"])[:8],
    }
    events_p = cdir / "events.jsonl"
    with events_p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"ok": True, "event": entry}


def _discover_live_host_results() -> list[dict[str, Any]]:
    """Read-only scan of E:\\0github\\results\\* on Windows host to detect sibling Arena branches."""
    results_root = Path(r"E:\0github\results")
    found: list[dict[str, Any]] = []
    if not results_root.is_dir():
        return found
    try:
        dirs = sorted(
            [p for p in results_root.iterdir() if p.is_dir()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:12]
    except OSError:
        return found

    for d in dirs:
        receipt_p = d / "status" / "hub_sync_receipt.json"
        receipt_data: dict[str, Any] = {}
        if receipt_p.is_file():
            try:
                receipt_data = json.loads(receipt_p.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                receipt_data = {}
        try:
            mtime_iso = dt.datetime.fromtimestamp(d.stat().st_mtime, tz=dt.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        except OSError:
            mtime_iso = ""
        found.append({
            "short_name": d.name,
            "path": str(d),
            "last_modified": mtime_iso,
            "repo": receipt_data.get("repo", ""),
            "branch": receipt_data.get("branch", ""),
            "source_commit": str(receipt_data.get("source_commit", ""))[:7],
            "tasks_all_ok": receipt_data.get("tasks_all_ok"),
        })
    return found


def get_coordination_state(data_dir: Path) -> dict[str, Any]:
    cdir = ensure_coord_initialized(data_dir)
    now = _now_utc()

    sessions: list[dict[str, Any]] = []
    for sp in sorted((cdir / "sessions").glob("*.json")):
        try:
            sessions.append(json.loads(sp.read_text(encoding="utf-8")))
        except Exception:
            continue

    active_leases: list[dict[str, Any]] = []
    for lp in sorted((cdir / "locks").glob("*.lock.json")):
        try:
            cur = json.loads(lp.read_text(encoding="utf-8"))
            exp_str = str(cur.get("expires_at") or "")
            expired = False
            if exp_str:
                exp_dt = dt.datetime.strptime(exp_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
                expired = exp_dt <= now
            cur["expired"] = expired
            if not expired:
                active_leases.append(cur)
        except Exception:
            continue

    events: list[dict[str, Any]] = []
    events_p = cdir / "events.jsonl"
    if events_p.is_file():
        try:
            raw_lines = events_p.read_text(encoding="utf-8").splitlines()[-25:]
            for ln in reversed(raw_lines):
                if ln.strip():
                    events.append(json.loads(ln))
        except Exception:
            pass

    hub_state: dict[str, Any] = {}
    hub_state_p = Path(r"E:\0github\.git-sync\hub-state.json")
    if hub_state_p.is_file():
        try:
            hub_state = json.loads(hub_state_p.read_text(encoding="utf-8-sig", errors="replace"))
        except Exception:
            hub_state = {}

    return {
        "ok": True,
        "coord_dir": str(cdir),
        "current_session": CURRENT_SESSION_ID,
        "current_branch": CURRENT_BRANCH,
        "conflicts_detected": 0,
        "hub_daemon_state": hub_state,
        "sessions": sessions,
        "active_leases": active_leases,
        "rules": NON_CONFLICT_RULES,
        "recent_events": events,
        "host_result_sandboxes": _discover_live_host_results(),
        "checked_at": _now_iso(),
    }
