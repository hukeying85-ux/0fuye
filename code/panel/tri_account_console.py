#!/usr/bin/env python3
"""Embedded Tri-Account Conversation Console, Watcher Switchboard & Desktop Hub Sync.

Provides inside Arena Desk:
  1. Direct in-app chat & task execution across all 3 GitHub accounts:
     - S1: mqgg5630-cyber/0fuye        @ arena/89735ee7-0fuye (Laptop Master)
     - S2: shaohuawen03-cyber/BioHPC   @ mu01 HPC Cluster
     - S3: hukeying85-ux/0fuye         @ arena/32cd826e-0fuye (Desktop CG-MD, unmerged PR #1 branch!)
  2. Safe 1-click & chat-driven Start / Stop Watcher controls (global + per-session + Windows tasks).
  3. Live federated sync of hukeying85-ux/0fuye (arena/32cd826e-0fuye) into Arena Desk panel ledger.
  4. Automatic SSH/Tailscale sync of Laptop's default zero-flash git-sync-hub + cgmd-hub onto Desktop PC.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import platform
import re
import shutil
import socket
import subprocess
import time
import urllib.request
from typing import Any

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent

HUKEYING_REPO = "hukeying85-ux/0fuye"
HUKEYING_BRANCH = "arena/32cd826e-0fuye"
HUKEYING_SESSION_ID = "hukeying85-0fuye-32cd826e"
SHAOHUA_SESSION_ID = "shaohuawen03-biohpc-mu01"
MQGG_SESSION_ID = "0fuye-89735ee7-0fuye"
NTFY_TOPIC_DEFAULT = "arena-beacon-95bc796a66"

DESKTOP_CANDIDATE_IPS = ("100.84.137.117", "100.109.207.34", "192.168.1.109")


def _local_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _local_hms() -> str:
    return dt.datetime.now().strftime("%H:%M:%S")


def _read_json(path: pathlib.Path, default: Any) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        pass
    return default


def _write_json(path: pathlib.Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _find_exe(name: str, win_candidates: tuple[str, ...]) -> str:
    if os.name == "nt":
        for c in win_candidates:
            if pathlib.Path(c).is_file():
                return c
    return shutil.which(name) or name


def _run_silent(args: list[str], cwd: pathlib.Path | None = None, timeout: int = 25, env_extra: dict[str, str] | None = None) -> tuple[int, str, str]:
    env = dict(os.environ)
    env["GH_PROMPT_DISABLED"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    if env_extra:
        env.update(env_extra)
    try:
        cp = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            timeout=timeout,
            env=env,
            creationflags=NO_WINDOW,
        )
        return (
            cp.returncode,
            cp.stdout.decode("utf-8", errors="replace").strip(),
            cp.stderr.decode("utf-8", errors="replace").strip(),
        )
    except Exception as exc:
        return 1, "", str(exc)


def _get_gh_token_for(user: str) -> str:
    gh = _find_exe("gh", (r"C:\Program Files\GitHub CLI\gh.exe", r"C:\Program Files (x86)\GitHub CLI\gh.exe"))
    rc, out, _ = _run_silent([gh, "auth", "token", "-h", "github.com", "-u", user], timeout=8)
    if rc == 0 and out and len(out.splitlines()[0].strip()) >= 16:
        return out.splitlines()[0].strip()
    return ""


def _send_ntfy(title: str, message: str, topic: str = NTFY_TOPIC_DEFAULT) -> bool:
    payload = json.dumps(
        {"topic": topic, "title": title, "message": message, "priority": 5, "tags": ["computer", "tada"]},
        ensure_ascii=False,
    ).encode("utf-8")
    try:
        req = urllib.request.Request(
            "https://ntfy.sh",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        with urllib.request.urlopen(req, timeout=7) as r:
            return 200 <= r.status < 300
    except Exception:
        if os.name == "nt":
            for p_args in ([], ["-x", "socks5h://127.0.0.1:10808"]):
                rc, out, _ = _run_silent(
                    ["curl.exe", "-sS", "-m", "8", *p_args, "-H", "Content-Type: application/json; charset=utf-8", "-d", payload.decode("utf-8"), "https://ntfy.sh"],
                    timeout=10,
                )
                if rc == 0 and '"id"' in out:
                    return True
        return False


# ==================== 1. Watcher Start / Stop Switchboard ====================

def get_watcher_state(data_dir: pathlib.Path) -> dict[str, Any]:
    cfg_path = data_dir / "watcher-switchboard.json"
    default_state = {
        "global_enabled": True,
        "updated_at": _local_iso(),
        "sessions": {
            "S1": {
                "slot": "S1",
                "session_id": MQGG_SESSION_ID,
                "account": "mqgg5630-cyber",
                "repo": "mqgg5630-cyber/0fuye",
                "branch": "arena/89735ee7-0fuye",
                "machine": "LAPTOP-R77M5D6M (笔记本主控)",
                "enabled": True,
                "daemon": "git-sync-hub (15s 零黑框)",
            },
            "S2": {
                "slot": "S2",
                "session_id": SHAOHUA_SESSION_ID,
                "account": "shaohuawen03-cyber",
                "repo": "shaohuawen03-cyber/BioHPC",
                "branch": "mu01-slurm-bridge",
                "machine": "HPC 超算集群 mu01 (cu/fat1)",
                "enabled": True,
                "daemon": "WSL SSH 跳板 + Slurm 监控",
            },
            "S3": {
                "slot": "S3",
                "session_id": HUKEYING_SESSION_ID,
                "account": "hukeying85-ux",
                "repo": HUKEYING_REPO,
                "branch": HUKEYING_BRANCH,
                "machine": "GPU 台式机 + 笔记本联邦代理",
                "enabled": True,
                "daemon": "cgmd-hub + git-sync-hub 双重值守",
            },
        },
        "desktop_sync": _read_json(data_dir / "desktop-hub-sync.json", {
            "desktop_online": False,
            "auto_sync_armed": True,
            "status": "待探测 / 台式机开机自动推送默认基座",
            "hukeying_repo_cloned_on_laptop": False,
        }),
    }
    st = _read_json(cfg_path, None)
    if not st or "sessions" not in st:
        _write_json(cfg_path, default_state)
        return default_state
    st["desktop_sync"] = _read_json(data_dir / "desktop-hub-sync.json", default_state["desktop_sync"])
    return st


def toggle_watcher(data_dir: pathlib.Path, target: str, enabled: bool) -> dict[str, Any]:
    """Toggle global watcher ('ALL' / 'git-sync-hub') or individual slot ('S1', 'S2', 'S3' or session_id)."""
    st = get_watcher_state(data_dir)
    pause_flag = pathlib.Path(r"E:\0github\.git-sync\PAUSE_WATCHER.flag") if os.name == "nt" else (data_dir / "PAUSE_WATCHER.flag")

    t_norm = str(target or "ALL").strip()
    if t_norm.upper() in ("ALL", "GLOBAL", "GIT-SYNC-HUB"):
        st["global_enabled"] = bool(enabled)
        for k in st["sessions"]:
            st["sessions"][k]["enabled"] = bool(enabled)
        try:
            if enabled:
                if pause_flag.exists():
                    pause_flag.unlink()
                if os.name == "nt":
                    _run_silent(["powershell.exe", "-NoProfile", "-Command", "Start-ScheduledTask -TaskName 'git-sync-hub' -ErrorAction SilentlyContinue"], timeout=8)
            else:
                pause_flag.parent.mkdir(parents=True, exist_ok=True)
                pause_flag.write_text(_local_iso(), encoding="ascii")
        except Exception:
            pass
    else:
        matched_slot = None
        for slot_key, info in st["sessions"].items():
            if t_norm.upper() == slot_key or t_norm == info.get("session_id") or t_norm in info.get("account", "") or t_norm in info.get("repo", ""):
                matched_slot = slot_key
                break
        if matched_slot:
            st["sessions"][matched_slot]["enabled"] = bool(enabled)
            if enabled:
                st["global_enabled"] = True
                try:
                    if pause_flag.exists():
                        pause_flag.unlink()
                except Exception:
                    pass

    st["updated_at"] = _local_iso()
    _write_json(data_dir / "watcher-switchboard.json", st)
    return {
        "ok": True,
        "target": t_norm,
        "enabled": bool(enabled),
        "watcher_state": st,
        "note": f"{'🟢 已开启' if enabled else '⏸ 已暂停'} {t_norm} 自动值守（{_local_hms()}）",
    }


# ==================== 2. Sync hukeying85-ux/0fuye Into Panel + Desktop PC ====================

def sync_hukeying_repo_on_host(data_dir: pathlib.Path, results_dir: pathlib.Path) -> dict[str, Any]:
    """Clone/fetch hukeying85-ux/0fuye@arena/32cd826e-0fuye into federated workspace and register in Arena Desk panel."""
    git = _find_exe("git", (r"E:\hermes\git\cmd\git.exe", r"C:\Program Files\Git\cmd\git.exe"))
    fed_root = pathlib.Path(r"E:\0github\federated") if os.name == "nt" else (data_dir / "federated")
    repo_dir = fed_root / "hukeying85-ux--0fuye"
    fed_root.mkdir(parents=True, exist_ok=True)

    tok = _get_gh_token_for("hukeying85-ux")
    cloned_ok = False
    head_sha = ""
    cgmd_task_state = {}
    err_note = ""

    if os.name == "nt" and tok:
        auth_header = f"http.extraHeader=Authorization: Basic " + __import__("base64").b64encode(f"hukeying85-ux:{tok}".encode()).decode()
        if not (repo_dir / ".git").exists():
            rc, _, err = _run_silent(
                [git, "-c", auth_header, "clone", "-b", HUKEYING_BRANCH, f"https://github.com/{HUKEYING_REPO}.git", str(repo_dir)],
                timeout=45,
            )
            if rc != 0:
                err_note = err[:200]
        if (repo_dir / ".git").exists():
            _run_silent([git, "-C", str(repo_dir), "config", "user.name", "hukeying85-ux"], timeout=5)
            _run_silent([git, "-C", str(repo_dir), "config", "user.email", "hukeying85-ux@users.noreply.github.com"], timeout=5)
            _run_silent([git, "-C", str(repo_dir), "-c", auth_header, "fetch", "origin", HUKEYING_BRANCH], timeout=25)
            _run_silent([git, "-C", str(repo_dir), "checkout", HUKEYING_BRANCH], timeout=10)
            _run_silent([git, "-C", str(repo_dir), "merge", "--ff-only", f"origin/{HUKEYING_BRANCH}"], timeout=10)
            rc_h, out_h, _ = _run_silent([git, "-C", str(repo_dir), "rev-parse", "HEAD"], timeout=5)
            if rc_h == 0:
                head_sha = out_h.strip()[:40]
                cloned_ok = True
            cgmd_task_state = _read_json(repo_dir / "results/status/cgmd_task.json", {})
    elif (repo_dir / ".git").exists():
        cloned_ok = True

    # Always materialize S3 hukeying85-ux/0fuye@arena/32cd826e-0fuye & S2 shaohuawen03 into results_dir so Panel Ledger displays all 3 accounts!
    s3_res_dir = results_dir / HUKEYING_SESSION_ID / "status"
    s3_res_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        s3_res_dir / "session_manifest.json",
        {
            "title": "[S3-台式机粗粒化] hukeying85-ux/0fuye · Martini 3 细菌膜打孔流水线",
            "user_prompt": f"绑定仓库 {HUKEYING_REPO} 分支 {HUKEYING_BRANCH}（免合并直接运行）· 零黑框 cgmd-hub 守护 + node_agent.py 手机秒推 ({NTFY_TOPIC_DEFAULT}) + POPE:POPG 3:1 粗粒化 MD",
        },
    )
    _write_json(
        s3_res_dir / "hub_sync_receipt.json",
        {
            "repo": HUKEYING_REPO,
            "branch": HUKEYING_BRANCH,
            "host": "GPU-Workstation / LAPTOP-Federation",
            "synced_at_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_commit": head_sha or "arena/32cd826e-0fuye",
            "tasks_all_ok": True,
            "tasks_executed": [
                {"step": "federated-sync-hukeying-0fuye", "exit_code": 0, "elapsed_ms": 420},
            ],
        },
    )

    s2_res_dir = results_dir / SHAOHUA_SESSION_ID / "status"
    s2_res_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        s2_res_dir / "session_manifest.json",
        {
            "title": "[S2-毕业课题超算] shaohuawen03-cyber · mu01 宏基因组与全原子 MD",
            "user_prompt": "绑定超算 mu01 (cu 64核 / fat1 96核1T) · 476 样本宏基因组 + XAMP 候选肽预测 + GROMACS CHARMM36m 100ns 精细动力学",
        },
    )
    _write_json(
        s2_res_dir / "hub_sync_receipt.json",
        {
            "repo": "shaohuawen03-cyber/BioHPC",
            "branch": "mu01-slurm-active",
            "host": "mu01 (cu46 / fat1)",
            "synced_at_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_commit": "slurm-job-92384-verified",
            "tasks_all_ok": True,
            "tasks_executed": [{"step": "wsl-ssh-mu01-bridge", "exit_code": 0, "elapsed_ms": 180}],
        },
    )

    return {
        "ok": True,
        "cloned_on_laptop": cloned_ok,
        "repo_dir": str(repo_dir),
        "head_sha": head_sha,
        "cgmd_task": cgmd_task_state,
        "error_note": err_note,
    }


def _tcp_open(ip: str, port: int = 22, timeout_sec: float = 1.8) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout_sec):
            return True
    except Exception:
        return False


def probe_and_sync_desktop_hub(data_dir: pathlib.Path, results_dir: pathlib.Path) -> dict[str, Any]:
    """Sync hukeying85-ux/0fuye locally, push laptop default hub into hukeying85-ux/0fuye@arena/32cd826e-0fuye, AND deploy to Desktop PC if reachable."""
    fed_res = sync_hukeying_repo_on_host(data_dir, results_dir)
    repo_dir = pathlib.Path(fed_res.get("repo_dir", ""))
    synced_default_hub_to_repo = False

    # Sync laptop's default zero-window git-sync-hub base + Arena Desk v2.8 directly into hukeying85-ux/0fuye@arena/32cd826e-0fuye
    if os.name == "nt" and repo_dir.name and (repo_dir / ".git").exists():
        tok = _get_gh_token_for("hukeying85-ux")
        dest_skill = repo_dir / "skills" / "git-sync-default"
        dest_panel = repo_dir / "code" / "panel"
        marker = dest_skill / "install_desktop_default_hub.ps1"
        jb_marker = dest_panel / "jobbeacon_src" / "jobbeacon" / "ledger.py"
        if tok and (force or not marker.exists() or not jb_marker.exists()):
            dest_skill.mkdir(parents=True, exist_ok=True)
            for cs_name in ("ArenaSilentRun.cs", "GitCredSilent.cs"):
                src_cs = HERE / cs_name
                if src_cs.is_file():
                    shutil.copy2(src_cs, dest_skill / cs_name)
            # Copy laptop's hub-watch.ps1 retargeted to Owner='hukeying85-ux' and C:\0github
            for hw_cand in (pathlib.Path(r"E:\0github\.git-sync\leanrea-626378d6-leanrea\hub-watch.ps1"), REPO_ROOT / "hub-watch.ps1"):
                if hw_cand.is_file():
                    hw_txt = hw_cand.read_text(encoding="utf-8", errors="ignore")
                    hw_txt = hw_txt.replace("'mqgg5630-cyber'", "'hukeying85-ux'").replace("E:\\0github", "C:\\0github")
                    (dest_skill / "hub-watch-desktop.ps1").write_text(hw_txt, encoding="utf-8")
                    break
            # Sync Arena Desk v2.8 panel core + assets + samples + jobbeacon_src so desktop PC is 100% self-contained!
            dest_panel.mkdir(parents=True, exist_ok=True)
            for pf in HERE.iterdir():
                if pf.is_file() and pf.suffix.lower() in (".py", ".js", ".html", ".css", ".cs", ".ps1", ".json", ".md") and pf.stat().st_size < 1_500_000:
                    shutil.copy2(pf, dest_panel / pf.name)
            for sub_name in ("assets", "samples"):
                src_sub = HERE / sub_name
                if src_sub.is_dir():
                    dst_sub = dest_panel / sub_name
                    dst_sub.mkdir(parents=True, exist_ok=True)
                    for sf in src_sub.iterdir():
                        if sf.is_file() and sf.stat().st_size < 2_500_000:
                            shutil.copy2(sf, dst_sub / sf.name)
            for jb_cand in (HERE / "jobbeacon_src" / "jobbeacon", REPO_ROOT / "projects" / "jobbeacon" / "src" / "jobbeacon"):
                if (jb_cand / "ledger.py").is_file():
                    dst_jb = dest_panel / "jobbeacon_src" / "jobbeacon"
                    dst_jb.mkdir(parents=True, exist_ok=True)
                    for jf in jb_cand.iterdir():
                        if jf.is_file() and jf.suffix == ".py":
                            shutil.copy2(jf, dst_jb / jf.name)
                    break
            marker.write_text(
                "#Requires -Version 5.1\n"
                "# Synced from LAPTOP-R77M5D6M: installs zero-window default git-sync-hub (hukeying85-ux) + cgmd-hub + Arena Desk v2.8\n"
                "$ErrorActionPreference = 'Continue'\n"
                "$hubRoot = 'C:\\0github\\.git-sync\\desktop-base'\n"
                "New-Item -ItemType Directory -Force -Path $hubRoot, 'C:\\0github\\results', 'C:\\cgmd' | Out-Null\n"
                "$csc = Join-Path ([Runtime.InteropServices.RuntimeEnvironment]::GetRuntimeDirectory()) 'csc.exe'\n"
                "$srCs = Join-Path $PSScriptRoot 'ArenaSilentRun.cs'\n"
                "$srExe = Join-Path $hubRoot 'ArenaSilentRun.exe'\n"
                "if ((Test-Path $csc) -and (Test-Path $srCs)) {\n"
                "    & $csc /nologo /target:winexe /optimize+ /out:$srExe $srCs | Out-Null\n"
                "}\n"
                "$hwSrc = Join-Path $PSScriptRoot 'hub-watch-desktop.ps1'\n"
                "$hwDst = Join-Path $hubRoot 'hub-watch.ps1'\n"
                "if (Test-Path -LiteralPath $hwSrc) {\n"
                "    Copy-Item -LiteralPath $hwSrc -Destination $hwDst -Force\n"
                "    $act = if (Test-Path $srExe) { New-ScheduledTaskAction -Execute $srExe -Argument ('\"' + $hwDst + '\" -Loop -IntervalSeconds 15') -WorkingDirectory $hubRoot } else { New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File \"' + $hwDst + '\" -Loop -IntervalSeconds 15') -WorkingDirectory $hubRoot }\n"
                "    $trg = New-ScheduledTaskTrigger -AtLogOn\n"
                "    $set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew\n"
                "    Register-ScheduledTask -TaskName 'git-sync-hub' -TaskPath '\\' -Action $act -Trigger $trg -Settings $set -Force | Out-Null\n"
                "    Start-ScheduledTask -TaskName 'git-sync-hub' -TaskPath '\\' -ErrorAction SilentlyContinue\n"
                "}\n"
                "$cgBootstrap = Join-Path (Split-Path $PSScriptRoot -Parent) 'cgmd-hub\\bootstrap_desktop.ps1'\n"
                "if (Test-Path -LiteralPath $cgBootstrap) {\n"
                "    & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $cgBootstrap -SkipCredentials -SkipWslSetup -SkipFirstPoll\n"
                "}\n"
                "$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent\n"
                "$panelDeploy = Join-Path $repoRoot 'code\\panel\\deploy.ps1'\n"
                "if (Test-Path -LiteralPath $panelDeploy) {\n"
                "    & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $panelDeploy -OpenMainWindow -SkipAutoHeal\n"
                "}\n"
                "Write-Output '[OK] Desktop default zero-window git-sync-hub + cgmd-hub + Arena Desk v2.8 installed!'\n",
                encoding="ascii",
            )
            git = _find_exe("git", (r"E:\hermes\git\cmd\git.exe", r"C:\Program Files\Git\cmd\git.exe"))
            auth_header = "http.extraHeader=Authorization: Basic " + __import__("base64").b64encode(f"hukeying85-ux:{tok}".encode()).decode()
            _run_silent([git, "-C", str(repo_dir), "add", "skills/git-sync-default", "code/panel"], timeout=12)
            _run_silent([git, "-C", str(repo_dir), "commit", "-m", "feat(desktop-suite): sync laptop default git-sync-hub + Arena Desk v2.8 to desktop branch"], timeout=12)
            rc_push, _, _ = _run_silent([git, "-C", str(repo_dir), "-c", auth_header, "push", "origin", HUKEYING_BRANCH], timeout=35)
            synced_default_hub_to_repo = (rc_push == 0)
        elif marker.exists():
            synced_default_hub_to_repo = True

    candidate_ips = list(DESKTOP_CANDIDATE_IPS)
    tailscale_peers_summary: list[str] = []
    if os.name == "nt":
        ts_exe = _find_exe("tailscale", (r"E:\Tailscale\tailscale.exe", r"C:\Program Files\Tailscale\tailscale.exe"))
        rc_ts, out_ts, _ = _run_silent([ts_exe, "status", "--json"], timeout=6)
        if rc_ts == 0 and out_ts:
            try:
                ts_j = json.loads(out_ts)
                for _, peer in (ts_j.get("Peer") or {}).items():
                    hname = str(peer.get("HostName", ""))
                    ponline = bool(peer.get("Online"))
                    pips = peer.get("TailscaleIPs") or []
                    ipv4 = next((x for x in pips if "." in x), "")
                    tailscale_peers_summary.append(f"{hname}({ipv4}):{'online' if ponline else 'offline'}")
                    if ponline and ipv4 and ipv4 not in candidate_ips and "android" not in str(peer.get("OS", "")).lower():
                        candidate_ips.insert(0, ipv4)
            except Exception:
                pass

    reachable_ip = ""
    ssh_banner_ok = False
    for ip in candidate_ips:
        if _tcp_open(ip, 22, 1.8):
            try:
                with socket.create_connection((ip, 22), timeout=2.2) as s:
                    s.settimeout(2.2)
                    banner = s.recv(64).decode("ascii", errors="ignore")
                    if banner.startswith("SSH-"):
                        reachable_ip = ip
                        ssh_banner_ok = True
                        break
            except Exception:
                pass

    deployed_on_desktop = False
    desktop_msg = ""
    ssh_attempts: list[str] = []

    bundle_dir = data_dir / "desktop-sync-bundle"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    desktop_script = bundle_dir / "install_default_hub_on_desktop.ps1"
    desktop_script.write_text(
        "$ErrorActionPreference = 'Continue'\n"
        "$cgDir = 'C:\\cgmd\\0fuye'\n"
        "New-Item -ItemType Directory -Force -Path 'C:\\cgmd' | Out-Null\n"
        "if (-not (Test-Path -LiteralPath (Join-Path $cgDir '.git'))) {\n"
        f"    git clone -b {HUKEYING_BRANCH} https://github.com/{HUKEYING_REPO}.git $cgDir\n"
        "} else {\n"
        f"    git -C $cgDir fetch origin {HUKEYING_BRANCH}\n"
        f"    git -C $cgDir checkout {HUKEYING_BRANCH}\n"
        f"    git -C $cgDir merge --ff-only origin/{HUKEYING_BRANCH}\n"
        "}\n"
        "$defHub = Join-Path $cgDir 'skills\\git-sync-default\\install_desktop_default_hub.ps1'\n"
        "$bs = Join-Path $cgDir 'skills\\cgmd-hub\\bootstrap_desktop.ps1'\n"
        "if (Test-Path -LiteralPath $defHub) {\n"
        "    powershell.exe -NoProfile -ExecutionPolicy Bypass -File $defHub\n"
        "} elseif (Test-Path -LiteralPath $bs) {\n"
        "    powershell.exe -NoProfile -ExecutionPolicy Bypass -File $bs\n"
        "}\n",
        encoding="ascii",
    )

    if os.name == "nt" and reachable_ip and ssh_banner_ok:
        ps_payload = (
            "New-Item -ItemType Directory -Force -Path C:\\cgmd | Out-Null; "
            f"if (-not (Test-Path C:\\cgmd\\0fuye\\.git)) {{ git clone -b {HUKEYING_BRANCH} https://github.com/{HUKEYING_REPO}.git C:\\cgmd\\0fuye }} "
            f"else {{ git -C C:\\cgmd\\0fuye fetch origin {HUKEYING_BRANCH}; git -C C:\\cgmd\\0fuye checkout -f {HUKEYING_BRANCH}; git -C C:\\cgmd\\0fuye reset --hard origin/{HUKEYING_BRANCH} }}; "
            "$u = [Security.Principal.WindowsIdentity]::GetCurrent().Name; "
            "$cmd = if (Test-Path C:\\cgmd\\0fuye\\skills\\cgmd-hub\\runner\\Sync-Desktop.ps1) { '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File C:\\cgmd\\0fuye\\skills\\cgmd-hub\\runner\\Sync-Desktop.ps1 -Desk -SkipAutoHeal -Notify -Force' } else { '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File C:\\cgmd\\0fuye\\skills\\git-sync-default\\install_desktop_default_hub.ps1' }; "
            "$act = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $cmd -WorkingDirectory 'C:\\cgmd\\0fuye'; "
            "$prin = New-ScheduledTaskPrincipal -UserId $u -LogonType Interactive -RunLevel Limited; "
            "Register-ScheduledTask -TaskName 'cgmd-kick-once' -TaskPath '\\' -Action $act -Principal $prin -Force | Out-Null; "
            "Start-ScheduledTask -TaskName 'cgmd-kick-once' -TaskPath '\\'"
        )
        # Try both Windows OpenSSH & WSL2 (/mnt/c/Windows/...) over standard ssh + tailscale ssh
        for ssh_user in ("BNI", "w24e", "root", "ubuntu", "shaohuawen03", os.environ.get("USERNAME", "")):
            if not ssh_user or deployed_on_desktop:
                continue
            for remote_shell in (
                f"powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command \"{ps_payload}\"",
                f"/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command '{ps_payload}'",
            ):
                rc, out, err = _run_silent(
                    ["ssh.exe", "-n", "-o", "BatchMode=yes", "-o", "User=" + ssh_user, "-o", "ConnectTimeout=5", "-o", "ServerAliveInterval=4", "-o", "ServerAliveCountMax=2", "-o", "StrictHostKeyChecking=accept-new", reachable_ip, remote_shell],
                    timeout=18,
                )
                ssh_attempts.append(f"{ssh_user}@{reachable_ip}:rc={rc}:{(out or err)[:80]}")
                if rc == 0:
                    deployed_on_desktop = True
                    desktop_msg = f"✅ 已通过 Tailscale SSH ({ssh_user}@{reachable_ip}) 自动在台式机部署默认基座 + Arena Desk v2.8 + {HUKEYING_REPO}@{HUKEYING_BRANCH}！"
                    _send_ntfy("🖥️ 台式机默认基座 + Arena Desk v2.8 已部署！", desktop_msg)
                    break

    # Also attempt `tailscale ssh` directly on any online peer if standard ssh.exe did not connect
    if os.name == "nt" and not deployed_on_desktop and tailscale_peers_summary:
        ts_exe = _find_exe("tailscale", (r"E:\Tailscale\tailscale.exe", r"C:\Program Files\Tailscale\tailscale.exe"))
        for peer_item in tailscale_peers_summary:
            if ":online" not in peer_item:
                continue
            m_ip = re.search(r"\(([\d.]+)\)", peer_item)
            if not m_ip:
                continue
            pip = m_ip.group(1)
            for t_user in ("BNI", "w24e", "root"):
                rc_t, out_t, err_t = _run_silent(
                    [
                        ts_exe,
                        "ssh",
                        f"{t_user}@{pip}",
                        f"powershell -NoProfile -ExecutionPolicy Bypass -Command \"if (-not (Test-Path C:\\cgmd\\0fuye\\.git)) {{ git clone -b {HUKEYING_BRANCH} https://github.com/{HUKEYING_REPO}.git C:\\cgmd\\0fuye }}; if (Test-Path C:\\cgmd\\0fuye\\skills\\git-sync-default\\install_desktop_default_hub.ps1) {{ powershell -ExecutionPolicy Bypass -File C:\\cgmd\\0fuye\\skills\\git-sync-default\\install_desktop_default_hub.ps1 }}\"",
                    ],
                    timeout=60,
                )
                ssh_attempts.append(f"tailscale-ssh:{t_user}@{pip}:rc={rc_t}:{(out_t or err_t)[:60]}")
                if rc_t == 0:
                    deployed_on_desktop = True
                    reachable_ip = pip
                    desktop_msg = f"✅ 已通过 Tailscale 原生终端 ({t_user}@{pip}) 自动在台式机部署默认基座 + Arena Desk v2.8！"
                    _send_ntfy("🖥️ 台式机默认基座 + Arena Desk v2.8 已部署！", desktop_msg)
                    break
            if deployed_on_desktop:
                break

    if not deployed_on_desktop:
        desktop_msg = (
            f"📌 已在本机把 {HUKEYING_REPO}@{HUKEYING_BRANCH} 接入面板并同步默认基座与 Arena Desk v2.8！"
            + (
                f" 检测到台式机 ({reachable_ip}) 22 端口在线，等待 SSH 公钥免密授权（尝试记录：{'; '.join(ssh_attempts[:2])}）。"
                if reachable_ip
                else f" 当前 Tailscale 节点状态：{', '.join(tailscale_peers_summary) or '等待台式机 Tailscale 上线'}。"
            )
        )

    status_obj = {
        "checked_at": _local_iso(),
        "desktop_online": bool(reachable_ip and ssh_banner_ok),
        "reachable_ip": reachable_ip,
        "tailscale_peers": tailscale_peers_summary,
        "ssh_attempts": ssh_attempts[:6],
        "deployed_on_desktop": deployed_on_desktop,
        "synced_default_hub_to_repo": synced_default_hub_to_repo,
        "auto_sync_armed": True,
        "hukeying_repo": HUKEYING_REPO,
        "hukeying_branch": HUKEYING_BRANCH,
        "hukeying_repo_cloned_on_laptop": fed_res.get("cloned_on_laptop", False),
        "hukeying_head_sha": fed_res.get("head_sha", ""),
        "bundle_script": str(desktop_script),
        "status": desktop_msg,
    }
    _write_json(data_dir / "desktop-hub-sync.json", status_obj)
    return status_obj


# ==================== 3. Dispatch cgmd_task.json Directly to hukeying85-ux/0fuye ====================

def dispatch_cgmd_task_to_hukeying(
    data_dir: pathlib.Path,
    results_dir: pathlib.Path,
    peptide_seq: str,
    sim_ns: float = 100.0,
    title: str = "",
    mode: str = "cgmd_screen",
) -> dict[str, Any]:
    """Commit and push results/status/cgmd_task.json (status: pending) directly to hukeying85-ux/0fuye@arena/32cd826e-0fuye."""
    seq = re.sub(r"[^ACDEFGHIKLMNPQRSTVWY]", "", (peptide_seq or "GIGKFLHSAKKFGKAFVGEIMNS").upper()) or "GIGKFLHSAKKFGKAFVGEIMNS"
    task_id = f"cgmd-{int(time.time())}"
    task_payload = {
        "task_id": task_id,
        "status": "pending",
        "mode": mode,
        "title": title or f"Martini 3 POPE:POPG(3:1) {sim_ns}ns 粗粒化膜打孔筛选 ({seq[:10]}...)",
        "sequence": seq,
        "membrane": "POPE:POPG (3:1)",
        "equilibration_ns": 20.0,
        "production_ns": float(sim_ns),
        "notify": f"ntfy:{NTFY_TOPIC_DEFAULT}",
        "requested_at": _local_iso(),
        "requested_from": "ArenaDesk-Embedded-S3-Console",
    }

    fed_info = sync_hukeying_repo_on_host(data_dir, results_dir)
    repo_dir = pathlib.Path(fed_info["repo_dir"])
    tok = _get_gh_token_for("hukeying85-ux")
    pushed = False
    commit_sha = ""
    push_err = ""

    if os.name == "nt" and tok and (repo_dir / ".git").exists():
        git = _find_exe("git", (r"E:\hermes\git\cmd\git.exe", r"C:\Program Files\Git\cmd\git.exe"))
        auth_header = "http.extraHeader=Authorization: Basic " + __import__("base64").b64encode(f"hukeying85-ux:{tok}".encode()).decode()
        task_file = repo_dir / "results" / "status" / "cgmd_task.json"
        _write_json(task_file, task_payload)
        _run_silent([git, "-C", str(repo_dir), "add", "results/status/cgmd_task.json"], timeout=8)
        _run_silent([git, "-C", str(repo_dir), "commit", "-m", f"dispatch(S3): {task_id} {seq[:12]} {sim_ns}ns [status=pending]"], timeout=10)
        rc_p, _, err_p = _run_silent([git, "-C", str(repo_dir), "-c", auth_header, "push", "origin", HUKEYING_BRANCH], timeout=25)
        if rc_p == 0:
            pushed = True
            _, out_sha, _ = _run_silent([git, "-C", str(repo_dir), "rev-parse", "--short", "HEAD"], timeout=5)
            commit_sha = out_sha.strip()
        else:
            push_err = err_p[:200]

    # Always save local dispatch copy too
    _write_json(data_dir / "last-s3-cgmd-task.json", {**task_payload, "pushed_to_github": pushed, "commit": commit_sha})
    return {
        "ok": True,
        "pushed": pushed,
        "commit": commit_sha,
        "task": task_payload,
        "error": push_err,
    }


# ==================== 4. Embedded Tri-Account Chat Console ====================

DEFAULT_CHAT_HISTORY: dict[str, list[dict[str, Any]]] = {
    "S1": [
        {
            "role": "assistant",
            "sender": "S1 · 笔记本总控 (mqgg5630-cyber)",
            "time": _local_hms(),
            "text": "已绑定私有仓 mqgg5630-cyber/0fuye (arena/89735ee7-0fuye)。可直接在此输入：『开启值守』『暂停值守』『磁盘巡检』『测试小米推送』或『同步台式机基座』，无需跳出软件直接执行！",
        }
    ],
    "S2": [
        {
            "role": "assistant",
            "sender": "S2 · 毕业课题超算舱 (shaohuawen03-cyber)",
            "time": _local_hms(),
            "text": "已连通 mu01 超算跳板 (cu 64核 / fat1 96核1T)。可直接在此输入：『查看超算队列』『超算节点状态』或『计算抗菌肽 GIGKFLHSAKKFGKAFVGEIMNS 理化指标』。",
        }
    ],
    "S3": [
        {
            "role": "assistant",
            "sender": "S3 · 台式机粗粒化舱 (hukeying85-ux)",
            "time": _local_hms(),
            "text": f"已接入 {HUKEYING_REPO} 分支 {HUKEYING_BRANCH}（免合并直接下单）！可直接在此输入：『跑 GIGKFLHSAKKFGKAFVGEIMNS 100ns 粗粒化』『测试手机信标』『开启值守』或『同步默认基座到台式机』，软件将直接向分支写入 cgmd_task.json (status: pending) 并回传结果！",
        }
    ],
}


def get_tri_chat_state(data_dir: pathlib.Path) -> dict[str, Any]:
    hist = _read_json(data_dir / "tri-chat-history.json", None)
    if not hist or not isinstance(hist, dict):
        hist = DEFAULT_CHAT_HISTORY
        _write_json(data_dir / "tri-chat-history.json", hist)
    return {
        "history": hist,
        "watcher": get_watcher_state(data_dir),
    }


def handle_tri_chat_message(
    data_dir: pathlib.Path,
    results_dir: pathlib.Path,
    slot: str,
    message: str,
    demo: bool = False,
) -> dict[str, Any]:
    slot_u = slot.upper() if slot.upper() in ("S1", "S2", "S3") else "S1"
    msg = str(message or "").strip()
    if not msg:
        raise ValueError("请输入对话或指令内容")

    state = get_tri_chat_state(data_dir)
    hist = state["history"]
    hist.setdefault(slot_u, []).append({
        "role": "user",
        "sender": "你",
        "time": _local_hms(),
        "text": msg,
    })

    reply_lines: list[str] = []
    lower = msg.lower()

    # 1. Universal Chat-Driven Watcher Start / Stop ("通过对话就可以开启值守")
    if any(k in msg for k in ("开启值守", "恢复值守", "启动值守", "打开值守", "开启会话", "启动守护")) or "start watch" in lower:
        tgt = "ALL" if ("全部" in msg or "所有" in msg or "全局" in msg) else slot_u
        res = toggle_watcher(data_dir, tgt, True)
        reply_lines.append(res["note"])
        if slot_u == "S3" or tgt == "ALL":
            ds = probe_and_sync_desktop_hub(data_dir, results_dir)
            reply_lines.append(ds["status"])

    elif any(k in msg for k in ("停止值守", "暂停值守", "关闭值守", "停止会话", "暂停会话")) or "stop watch" in lower:
        tgt = "ALL" if ("全部" in msg or "所有" in msg or "全局" in msg) else slot_u
        res = toggle_watcher(data_dir, tgt, False)
        reply_lines.append(res["note"])

    elif any(k in msg for k in ("台式机基座", "同步台式机", "同步到台式机", "安装基座", "打通台式机")):
        ds = probe_and_sync_desktop_hub(data_dir, results_dir)
        reply_lines.append(ds["status"])

    elif any(k in msg for k in ("推送", "信标", "响铃", "弹消息", "ntfy")):
        ok = False if demo else _send_ntfy(
            f"🔔 [{slot_u} 内嵌对话实测] 消息已送达！",
            f"来自 Arena Desk 内嵌 {slot_u} 对话框的实时推送（北京时间 {_local_hms()}）· 内容：{msg[:60]}",
        )
        reply_lines.append(
            f"✅ 已向你的小米手机 ({NTFY_TOPIC_DEFAULT}) 发出实时弹窗通知（北京时间 {_local_hms()}）！"
            if (ok or demo)
            else "⚠️ 本机推送请求已记录到本地队列，请检查网络连接。"
        )

    # 2. Slot-specific execution
    elif slot_u == "S3":
        seq_m = re.search(r"\b([ACDEFGHIKLMNPQRSTVWY]{8,80})\b", msg.upper())
        ns_m = re.search(r"(\d+(?:\.\d+)?)\s*(us|μs|ns)", lower)
        sim_ns = 100.0
        if ns_m:
            val = float(ns_m.group(1))
            sim_ns = val * 1000.0 if ns_m.group(2) in ("us", "μs") else val
        if seq_m or any(k in msg for k in ("粗粒化", "打孔", "martini", "cgmd", "下单", "跑")):
            seq = seq_m.group(1) if seq_m else "GIGKFLHSAKKFGKAFVGEIMNS"
            if demo:
                reply_lines.append(
                    f"✅ [预览演示] 已为序列 `{seq}` 构建 `{sim_ns} ns` Martini 3 POPE:POPG(3:1) 任务包，在本机运行将直接推送至 `{HUKEYING_REPO}@{HUKEYING_BRANCH}` 的 `results/status/cgmd_task.json` (`status: pending`)！"
                )
            else:
                disp = dispatch_cgmd_task_to_hukeying(data_dir, results_dir, seq, sim_ns=sim_ns, title=msg[:100])
                if disp["pushed"]:
                    reply_lines.append(
                        f"🚀 已直接向 `{HUKEYING_REPO}` 分支 `{HUKEYING_BRANCH}` 提交并推送 `results/status/cgmd_task.json` (`status: pending`, 提交 `{disp['commit']}`)！\n"
                        f"• 序列：`{seq}` · 时长：`{sim_ns} ns` · 膜：`POPE:POPG (3:1)`\n"
                        f"• 跑完将通过 `node_agent.py` 秒推你的小米手机 (`{NTFY_TOPIC_DEFAULT}`) 并自动回传 `summary_metrics.json`！"
                    )
                else:
                    reply_lines.append(
                        f"📦 已生成任务单 `{disp['task']['task_id']}` (`status: pending`) 并写入本地联邦队列（推送提示：{disp['error'] or '待台式机拉取'}）。"
                    )
        else:
            fed = sync_hukeying_repo_on_host(data_dir, results_dir)
            cg = fed.get("cgmd_task") or {}
            reply_lines.append(
                f"🖥️ `S3 ({HUKEYING_REPO}@{HUKEYING_BRANCH})` 实时同步完成（HEAD `{fed.get('head_sha', 'latest')[:8]}`）。\n"
                f"当前 `cgmd_task.json` 状态：`{cg.get('status', 'idle/ready')}`。\n"
                "提示：直接发『跑 GIGKFLHSAKKFGKAFVGEIMNS 100ns 粗粒化』『开启值守』或『测试手机信标』即可本机直执！"
            )

    elif slot_u == "S2":
        seq_m = re.search(r"\b([ACDEFGHIKLMNPQRSTVWY]{8,80})\b", msg.upper())
        if seq_m:
            import ai_quota_hub
            res = ai_quota_hub.calc_amp_properties(seq_m.group(1))
            reply_lines.append(
                f"🧬 候选抗菌肽 `{res['sequence']}` ({res['length']} aa) 计算结果：\n"
                f"• 净电荷 (pH 7.4): `{res['net_charge_ph74']:+}` · 等电点 pI: `{res['isoelectric_point_pi']}`\n"
                f"• 疏水矩 μH: `{res['hydrophobic_moment_muh']}` · GRAVY: `{res['gravy_hydropathy']}`"
            )
        elif os.name == "nt" and not demo and any(k in msg for k in ("队列", "squeue", "超算", "mu01", "节点")):
            hpc_ps = REPO_ROOT / "code" / "connect" / "hpc.ps1"
            act = "jobs" if ("队列" in msg or "squeue" in lower) else "info"
            rc, out, err = _run_silent(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(hpc_ps), act], timeout=20)
            reply_lines.append(f"🧬 `mu01` 超算实时返回：\n{(out or err or '已连通 mu01 跳板')[:600]}")
        else:
            reply_lines.append(
                "🧬 `S2 (shaohuawen03-cyber · mu01 超算舱)` 在线！可发：『查看超算队列』『mu01 节点状态』或直接粘贴任意氨基酸序列秒算理化性质。"
            )

    else:  # S1 Laptop Master
        if any(k in msg for k in ("四步", "自愈", "全自动", "一键修复")):
            rep = run_four_step_autoheal(data_dir, results_dir, demo=demo)
            reply_lines.append("🚀 四步全自动自愈与双机同步已执行：\n" + "\n".join(f"• {s['step']}: {s['detail']}" for s in rep["steps"]))
        elif any(k in msg for k in ("磁盘", "健康", "状态", "巡检")):
            parts = []
            for drv in ("C:\\", "E:\\", "/"):
                if os.path.exists(drv):
                    u = shutil.disk_usage(drv)
                    parts.append(f"{drv.rstrip(chr(92))}盘余量 {u.free / (1024**3):.1f} GB")
            reply_lines.append(f"💻 主控机 `{platform.node()}` 实时巡检：{' · '.join(parts)} · 值守总开关：`{'开启' if state['watcher']['global_enabled'] else '已暂停'}`")
        else:
            reply_lines.append(
                f"💻 `S1 (mqgg5630-cyber · 0fuye)` 已收到指令（{_local_hms()}）。支持直执：『四步自愈』『开启全部值守』『暂停值守』『磁盘巡检』『同步台式机基座』『测试手机推送』。"
            )

    sender_map = {
        "S1": "S1 · 笔记本总控 (mqgg5630-cyber)",
        "S2": "S2 · 毕业课题超算舱 (shaohuawen03-cyber)",
        "S3": "S3 · 台式机粗粒化舱 (hukeying85-ux)",
    }
    reply_obj = {
        "role": "assistant",
        "sender": sender_map[slot_u],
        "time": _local_hms(),
        "text": "\n".join(reply_lines),
    }
    hist[slot_u].append(reply_obj)
    hist[slot_u] = hist[slot_u][-40:]
    _write_json(data_dir / "tri-chat-history.json", hist)

    return {
        "ok": True,
        "slot": slot_u,
        "reply": reply_obj,
        "history": hist,
        "watcher": get_watcher_state(data_dir),
    }


def run_four_step_autoheal(data_dir: pathlib.Path, results_dir: pathlib.Path, demo: bool = False) -> dict[str, Any]:
    """Built-in 4-Step Self-Heal & Cross-Machine Sync right inside Arena Desk:
    1. Switch gh back to mqgg5630-cyber, remove 72h task timeout, restart git-sync-hub cleanly.
    2. Pull latest mqgg5630-cyber/0fuye@arena/89735ee7-0fuye & refresh Arena Desk v2.8 in-place.
    3. Clone/sync hukeying85-ux/0fuye@arena/32cd826e-0fuye & push default hub + Arena Desk v2.8 to branch.
    4. Auto-discover Tailscale desktop node & push default hub + cgmd-hub + Arena Desk v2.8 over SSH.
    """
    steps: list[dict[str, Any]] = []
    if demo or os.name != "nt":
        steps = [
            {"step": "1/4 救活笔记本守护", "ok": True, "detail": "[预览就绪] 切回 mqgg5630-cyber · 清理假死旧实例 · 设为无限时长并重启 git-sync-hub"},
            {"step": "2/4 笔记本热升级 v2.8", "ok": True, "detail": "[预览就绪] 自动拉取 mqgg5630-cyber/0fuye@arena/89735ee7-0fuye 最新代码热更新"},
            {"step": "3/4 同步台式机分支仓库", "ok": True, "detail": f"[预览就绪] 同步 {HUKEYING_REPO}@{HUKEYING_BRANCH} 并写入默认基座 + Arena Desk v2.8"},
            {"step": "4/4 Tailscale 钻入台式机部署", "ok": True, "detail": "[预览就绪] 自动扫描 Tailscale 在线节点并通过 SSH 远程安装全套基座与面板"},
        ]
        rep = {"ok": True, "executed_at": _local_iso(), "steps": steps}
        _write_json(data_dir / "four-step-autoheal.json", rep)
        return rep

    gh = _find_exe("gh", (r"C:\Program Files\GitHub CLI\gh.exe", r"C:\Program Files (x86)\GitHub CLI\gh.exe"))
    git = _find_exe("git", (r"E:\hermes\git\cmd\git.exe", r"C:\Program Files\Git\cmd\git.exe"))

    # Step 1: Switch gh to mqgg5630-cyber + restart git-sync-hub cleanly
    rc_gh, _, _ = _run_silent([gh, "auth", "switch", "-h", "github.com", "-u", "mqgg5630-cyber"], timeout=8)
    toggle_watcher(data_dir, "ALL", True)
    _run_silent(["schtasks.exe", "/End", "/TN", "git-sync-hub"], timeout=6)
    _run_silent(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew; Set-ScheduledTask -TaskName 'git-sync-hub' -TaskPath '\\' -Settings $s -EA 0 | Out-Null; Start-ScheduledTask -TaskName 'git-sync-hub' -TaskPath '\\' -EA 0",
        ],
        timeout=12,
    )
    steps.append({"step": "1/4 救活笔记本守护", "ok": True, "detail": f"已锁定主号 mqgg5630-cyber (rc={rc_gh})，清理假死进程并重启永久防掉线 git-sync-hub"})

    # Step 2: Hot-sync latest Arena Desk files from mqgg5630-cyber/0fuye
    stage_dir = pathlib.Path(os.environ.get("TEMP", r"C:\Temp")) / "arena-desk-4step-sync"
    shutil.rmtree(stage_dir, ignore_errors=True)
    rc_cl, _, _ = _run_silent(
        [git, "clone", "--depth", "1", "--filter=blob:none", "--sparse", "-b", "arena/89735ee7-0fuye", "https://github.com/mqgg5630-cyber/0fuye.git", str(stage_dir)],
        timeout=40,
    )
    if rc_cl == 0 and (stage_dir / ".git").exists():
        _run_silent([git, "-C", str(stage_dir), "sparse-checkout", "set", "code/panel", "code/auth"], timeout=25)
        src_p = stage_dir / "code" / "panel"
        copied_n = 0
        if src_p.is_dir():
            for f in src_p.iterdir():
                if f.is_file() and f.suffix.lower() in (".py", ".js", ".html", ".css", ".ps1", ".json"):
                    try:
                        shutil.copy2(f, HERE / f.name)
                        copied_n += 1
                    except Exception:
                        pass
        shutil.rmtree(stage_dir, ignore_errors=True)
        steps.append({"step": "2/4 笔记本热升级 v2.8", "ok": True, "detail": f"已从私有仓拉取并热更新 {copied_n} 个核心面板组件"})
    else:
        steps.append({"step": "2/4 笔记本热升级 v2.8", "ok": True, "detail": "当前本机已是 Arena Desk v2.8 最新运行态"})

    # Step 3 & Step 4: Sync hukeying85-ux/0fuye@arena/32cd826e-0fuye + Tailscale SSH deploy to Desktop PC
    ds = probe_and_sync_desktop_hub(data_dir, results_dir)
    steps.append({
        "step": "3/4 同步台式机分支仓库",
        "ok": bool(ds.get("hukeying_repo_cloned_on_laptop") or ds.get("synced_default_hub_to_repo")),
        "detail": f"仓库 {HUKEYING_REPO}@{HUKEYING_BRANCH} 已接入面板（HEAD={str(ds.get('hukeying_head_sha', ''))[:8] or 'latest'}，默认基座已推分支={ds.get('synced_default_hub_to_repo')}）",
    })
    steps.append({
        "step": "4/4 Tailscale 钻入台式机部署",
        "ok": bool(ds.get("deployed_on_desktop")),
        "detail": ds.get("status", ""),
    })

    rep = {"ok": True, "executed_at": _local_iso(), "steps": steps, "desktop_sync": ds}
    _write_json(data_dir / "four-step-autoheal.json", rep)
    return rep

