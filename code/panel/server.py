"""Arena Desk v2.1 — Local, credential-free desktop control plane.
The permanent git-sync-hub is strictly read-only and never stoppable here.
Includes:
  - DSH-style native video skins, glass presets, boot animation showcase (#boot), whale widget
  - One-click Thesis Formatting (Lark-Formatter v0.21.1 headless 34-module bridge)
  - Multi-Session Collaboration & Non-Conflict Lease Coordinator
  - Career / Civil-Service Exam / Redacted Identity / Commemoration & Google Drive Archive Hub
  - Multi-Account GitHub CLI & SSH 443 Bridge (mqgg5630 + shaohuawen03 + hukeying85-ux)
"""
import argparse
import datetime as dt
import http.server
import json
import os
import pathlib
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
for _jb_cand in (
    HERE / "jobbeacon_src",
    HERE.parent.parent / "projects" / "jobbeacon" / "src",
):
    if _jb_cand.is_dir() and str(_jb_cand) not in sys.path:
        sys.path.insert(0, str(_jb_cand))

import ai_quota_hub  # noqa: E402
from desktop_ops import DesktopOps  # noqa: E402
import federation_hub  # noqa: E402
from jobbeacon.ledger import BeaconLedger  # noqa: E402
from jobbeacon.tunnels import verify_pairing_token  # noqa: E402
import media_cua_hub  # noqa: E402
import qr_svg  # noqa: E402
import session_coord  # noqa: E402
import thesis_ops  # noqa: E402
import tri_account_console  # noqa: E402
import war_room  # noqa: E402

PANEL_VERSION = "2.8.0"
ALLOWED = {"arena-desktop-pet", "arena-desk-open", "arena-desk-boot-demo", "arena-dsh-web"}
NOTION = "https://app.notion.com/p/407186af12d381cf97eeebf4ec37f0c9"
SECRET = re.compile(
    r"(?:\b(?:ntn_|secret_|ghp_|gho_|github_pat_|sk-)[\w-]{12,}"
    r"|-----BEGIN .*PRIVATE KEY"
    r"|(?:password|token|api_key)\s*[:=]\s*\S+)",
    re.I,
)

ASSET_MIMES = {
    "icon.svg": "image/svg+xml",
    "whale.svg": "image/svg+xml",
    "icon-256.png": "image/png",
    "icon-64.png": "image/png",
    "ArenaDesk.ico": "image/x-icon",
    "wallpaper-aurora.jpg": "image/jpeg",
    "wallpaper-anime.jpg": "image/jpeg",
    "boot-mascot.jpg": "image/jpeg",
    "dsh-boot.mp4": "video/mp4",
    "dsh-bg.mp4": "video/mp4",
}


def read_json(path, default=None):
    try:
        if path.stat().st_size > 2_000_000:
            return default
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def redact(text):
    return SECRET.sub("[REDACTED]", str(text))


def receipt_status(r):
    if not r:
        return "no_receipt"
    if r.get("tasks_all_ok") is False:
        return "failed"
    if r.get("tasks_all_ok") is True:
        return "completed"
    return "unknown"


class Store:
    def __init__(self, data, results, hub, demo=False):
        self.data, self.results, self.hub, self.demo = data, results, hub, demo
        data.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.tasks = []
        self.sampled = None
        self.error = "Waiting for first sample"
        self.sample_preview_cache = {}
        self.ops = DesktopOps(data, demo=demo)
        self.beacon = BeaconLedger(data / "jobbeacon", seed_demo=True)
        self.federation = federation_hub.FederationHub(data)
        session_coord.ensure_coord_initialized(data)
        self.lan_bridge_port = 18766
        self.lan_bridge_active = False
        self.tunnel_proc = None
        self.tunnel_url = ""
        self.tunnel_status = "idle"
        if demo:
            self._seed_demo_state()

    def _seed_demo_state(self):
        self.tasks = [
            {"name": "git-sync-hub", "state": "Running", "last_result": 0, "protected": True},
            {"name": "arena-desk-panel", "state": "Running", "last_result": 0, "protected": True},
            {"name": "arena-desk-boot-demo", "state": "Ready", "last_result": 0, "protected": False},
            {"name": "arena-desktop-pet", "state": "Running", "last_result": 0, "protected": False},
            {"name": "jev-chat-monitor", "state": "Ready", "last_result": 0, "protected": True},
            {"name": "jev-chat-analyze", "state": "Running", "last_result": 0, "protected": True},
        ]
        self.sampled = stamp()
        self.error = ""
        if not self.results.exists():
            self.results.mkdir(parents=True, exist_ok=True)
            demo_sessions = [
                (
                    "0fuye-89735ee7-0fuye",
                    {
                        "repo": "0fuye",
                        "branch": "arena/89735ee7-0fuye",
                        "host": "LAPTOP-R77M5D6M",
                        "synced_at_utc": stamp(),
                        "tasks_all_ok": True,
                        "tasks_executed": [
                            {"step": "ArenaDesk v2.1 + Boot Animation Showcase", "exit_code": 0, "elapsed_ms": 910},
                            {"step": "Lark-Formatter v0.21.1 Headless Bridge (116 changes)", "exit_code": 0, "elapsed_ms": 1520},
                            {"step": "Multi-Account gh + SSH 443 + Session Coord", "exit_code": 0, "elapsed_ms": 640},
                        ],
                    },
                    {
                        "title": "Arena Desk v2.5 全域工作台：DSH视频开机动画 · 三账号分舱 · 爱情模块 · 手机扫码装App",
                        "user_prompt": "集成算力信标 JobBeacon (Slurm/分子动力学跑完推手机 + 手机伴侣 App)、免付费手机直连、GrokBot 多会话作战室、Gemini 与反重力额度防浪费中枢及硕士学位论文一键改格式。",
                    },
                ),
                (
                    "leanrea-4d729933-leanrea",
                    {
                        "repo": "leanrea",
                        "branch": "arena/4d729933-leanrea",
                        "host": "LAPTOP-R77M5D6M",
                        "synced_at_utc": "2026-10-28T01:44:29Z",
                        "tasks_all_ok": True,
                        "tasks_executed": [
                            {"step": "deploy.ps1", "exit_code": 0, "elapsed_ms": 4200},
                            {"step": "hpc_smoke.sh (mu01 Slurm)", "exit_code": 0, "elapsed_ms": 9600},
                        ],
                    },
                    {
                        "title": "伙伴会话（零冲突并存）：基座桌面面板 v1 与 HPC 跨机器打通",
                        "user_prompt": "将打通基座做成桌面面板；验证 HPC mu01 端到端作业提交与回传；Notion 实例台账归档。",
                    },
                ),
            ]
            for name, rcpt, man in demo_sessions:
                sdir = self.results / name / "status"
                sdir.mkdir(parents=True, exist_ok=True)
                (sdir / "hub_sync_receipt.json").write_text(json.dumps(rcpt, ensure_ascii=False, indent=2), encoding="utf-8")
                (sdir / "session_manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")
        if not (self.hub / "hub-state.json").exists():
            self.hub.mkdir(parents=True, exist_ok=True)
            (self.hub / "hub-state.json").write_text(
                json.dumps(
                    {
                        "updated_at": stamp(),
                        "host": "LAPTOP-R77M5D6M",
                        "task_name": "git-sync-hub",
                        "mode": "auto-poll-exec-and-sync-zero-window-v4.0",
                        "poll_interval_sec": 15,
                        "result_projects": 65,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        if self.demo or os.name == "nt":
            try:
                tri_account_console.sync_hukeying_repo_on_host(self.data, self.results)
            except Exception:
                pass

    def detect_lan_ip(self) -> str:
        candidates = []
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.3)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127.") and not ip.startswith("169.254."):
                candidates.append(ip)
        except Exception:
            pass
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = info[4][0]
                if ip and not ip.startswith("127.") and not ip.startswith("169.254.") and ip not in candidates:
                    candidates.append(ip)
        except Exception:
            pass
        # Prefer standard Wi-Fi/LAN RFC1918 over virtual adapters
        for pfx in ("192.168.", "10.", "172."):
            for ip in candidates:
                if ip.startswith(pfx) and not ip.startswith("198.18."):
                    return ip
        return candidates[0] if candidates else "127.0.0.1"

    def start_cloudflared_tunnel(self) -> dict:
        if self.demo:
            return {"ok": False, "error": "预览沙盒请直接扫右侧实时预览二维码，或在本机点击启动 Cloudflare 免费隧道。"}
        if self.tunnel_url and self.tunnel_proc and self.tunnel_proc.poll() is None:
            return {"ok": True, "url": self.tunnel_url, "status": "running"}
        saved_tun = self.data / "active-android-tunnel.txt"
        if os.name == "nt" and saved_tun.is_file():
            try:
                existing_url = saved_tun.read_text(encoding="utf-8").strip()
                if existing_url.startswith("https://") and ".trycloudflare.com" in existing_url:
                    tl = subprocess.run(
                        ["tasklist", "/FI", "IMAGENAME eq cloudflared.exe", "/NH"],
                        capture_output=True,
                        text=True,
                        timeout=4,
                        creationflags=0x08000000,
                    )
                    if "cloudflared.exe" in (tl.stdout or ""):
                        self.tunnel_url = existing_url
                        self.tunnel_status = "running"
                        return {"ok": True, "url": self.tunnel_url, "status": "adopted_running"}
            except Exception:
                pass
        cf_bin = shutil.which("cloudflared")
        if not cf_bin and os.name == "nt":
            for cand in (
                str(HERE / "bin" / "cloudflared.exe"),
                r"E:\0apps\ArenaDesk\bin\cloudflared.exe",
                r"E:\0apps\cloudflared\cloudflared.exe",
                r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
                r"C:\Program Files\cloudflared\cloudflared.exe",
                str(pathlib.Path.home() / "AppData/Local/Microsoft/WinGet/Links/cloudflared.exe"),
            ):
                if pathlib.Path(cand).is_file():
                    cf_bin = cand
                    break
        if not cf_bin:
            return {
                "ok": False,
                "status": "missing_binary",
                "error": "本机尚未安装 cloudflared（可在『软件与安装』一键安装 Cloudflare.cloudflared，或直接用同 Wi-Fi 局域网二维码秒装！）",
            }
        target_port = self.lan_bridge_port if self.lan_bridge_active else 18765
        log_file = self.data / "cloudflared-quick.log"

        def _try_spawn(use_proxy: bool) -> str:
            env = dict(os.environ)
            if not use_proxy:
                for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
                    env.pop(k, None)
            else:
                for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
                    if k in env and env[k].startswith("socks5h://"):
                        env[k] = "socks5://" + env[k][len("socks5h://") :]
                if not env.get("HTTPS_PROXY") and not env.get("ALL_PROXY"):
                    env["HTTPS_PROXY"] = "socks5://127.0.0.1:10808"
                    env["HTTP_PROXY"] = "socks5://127.0.0.1:10808"
            if self.tunnel_proc and self.tunnel_proc.poll() is None:
                try:
                    self.tunnel_proc.terminate()
                except Exception:
                    pass
            lf = log_file.open("w", encoding="utf-8")
            self.tunnel_proc = subprocess.Popen(
                [cf_bin, "tunnel", "--url", f"http://127.0.0.1:{target_port}", "--protocol", "http2", "--no-autoupdate"],
                stdout=lf,
                stderr=subprocess.STDOUT,
                env=env,
                creationflags=0x08000000 if os.name == "nt" else 0,
            )
            self.tunnel_status = "starting"
            for _ in range(22):
                time.sleep(0.45)
                txt = log_file.read_text(encoding="utf-8", errors="ignore") if log_file.is_file() else ""
                m = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", txt)
                if m:
                    return m.group(0) + "/mobile"
                if self.tunnel_proc.poll() is not None:
                    break
            return ""

        try:
            found_url = _try_spawn(use_proxy=False) or _try_spawn(use_proxy=True)
            if found_url:
                self.tunnel_url = found_url
                self.tunnel_status = "running"
                try:
                    (self.data / "active-android-tunnel.txt").write_text(found_url, encoding="utf-8")
                except OSError:
                    pass
                return {"ok": True, "url": self.tunnel_url, "status": "running"}
            return {"ok": True, "url": "", "status": "starting", "note": "隧道正在握手，请 3 秒后点刷新二维码"}
        except Exception as e:
            self.tunnel_status = "error"
            return {"ok": False, "error": str(e)[:160]}

    def get_mobile_qr_bundle(self, origin_hint: str = "") -> dict:
        lan_ip = self.detect_lan_ip()
        lan_port = self.lan_bridge_port if self.lan_bridge_active else 18765
        lan_url = f"http://{lan_ip}:{lan_port}/mobile"
        if self.demo and origin_hint:
            lan_url = f"{origin_hint.rstrip('/')}/mobile"

        # Refresh cloudflared log if starting
        if not self.tunnel_url and (self.data / "cloudflared-quick.log").is_file():
            try:
                txt = (self.data / "cloudflared-quick.log").read_text(encoding="utf-8", errors="ignore")
                m = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", txt)
                if m:
                    self.tunnel_url = m.group(0) + "/mobile"
                    self.tunnel_status = "running"
            except OSError:
                pass

        pub_url = self.tunnel_url or (f"{origin_hint.rstrip('/')}/mobile" if origin_hint and "e2b.app" in origin_hint else "")
        ntfy_cfg = self.federation.get_notify_config()
        ntfy_topic = ntfy_cfg.get("ntfy_topic") or "arena-research-beacon-demo"
        ntfy_url = f"https://ntfy.sh/{ntfy_topic}"

        primary_url = pub_url or lan_url
        return {
            "lan_ip": lan_ip,
            "lan_port": lan_port,
            "lan_bridge_active": self.lan_bridge_active or self.demo,
            "lan_url": lan_url,
            "lan_qr_svg": qr_svg.render_qr_svg(lan_url, 176),
            "public_url": pub_url,
            "public_qr_svg": qr_svg.render_qr_svg(pub_url, 176) if pub_url else "",
            "tunnel_status": self.tunnel_status,
            "ntfy_topic": ntfy_topic,
            "ntfy_url": ntfy_url,
            "ntfy_qr_svg": qr_svg.render_qr_svg(ntfy_url, 156),
            "primary_url": primary_url,
        }

    def run_ephemeral_sample_thesis(self, profile_id="academic_master_2026"):
        """Safe, stateless sample thesis run in a disposable temp folder (works in both Live Preview and local mode)."""
        tmp_dir = pathlib.Path(tempfile.mkdtemp(prefix="arenadesk-sample-run-"))
        try:
            res = thesis_ops.run_thesis_format(
                tmp_dir,
                {
                    "profile_id": profile_id or "academic_master_2026",
                    "use_sample": True,
                },
                ephemeral=False,
            )
            if res.get("ok") and isinstance(res.get("job"), dict):
                job = res["job"]
                jid = job["job_id"]
                files_blob = {}
                kind_specs = (
                    ("final", ("final", "output", "new_docx", "docx"), "_new.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                    ("compare", ("compare", "compare_docx"), "_对比稿.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                    ("report_md", ("report_md", "report"), "_报告.md", "text/markdown; charset=utf-8"),
                    ("report_json", ("report_json", "json"), "_报告.json", "application/json; charset=utf-8"),
                )
                for canonical, aliases, default_ext, mime in kind_specs:
                    p, dl_name = thesis_ops.resolve_job_artifact(tmp_dir, jid, canonical)
                    if p and p.is_file():
                        blob_entry = {
                            "filename": dl_name or p.name or f"master_sample{default_ext}",
                            "mime": mime,
                            "bytes": p.read_bytes(),
                        }
                        for alias in aliases:
                            files_blob[alias] = blob_entry
                csl_p, csl_name = thesis_ops.resolve_job_artifact(tmp_dir, jid, "csl")
                if csl_p and csl_p.is_file():
                    files_blob["csl"] = {
                        "filename": csl_name or csl_p.name,
                        "mime": "application/xml; charset=utf-8",
                        "bytes": csl_p.read_bytes(),
                    }
                with self.lock:
                    self.sample_preview_cache = {
                        "created_at": time.time(),
                        "result": res,
                        "blobs": files_blob,
                    }
            return res
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def audit(self, event):
        with self.lock, (self.data / "audit.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": stamp(), **event}, ensure_ascii=False) + "\n")

    def sessions(self):
        notes = read_json(self.data / "sessions.json", {}) or {}
        watcher = tri_account_console.get_watcher_state(self.data)
        slot_states = watcher.get("sessions", {})
        global_on = bool(watcher.get("global_enabled", True))
        rows = []
        if self.results.exists():
            for folder in self.results.iterdir():
                if not folder.is_dir() or folder.is_symlink():
                    continue
                r = read_json(folder / "status/hub_sync_receipt.json", {}) or {}
                manifest = read_json(folder / "status/session_manifest.json", {}) or {}
                note = notes.get(folder.name, {})
                prompt = note.get("prompt") or manifest.get("user_prompt") or ""
                repo_str = str(r.get("repo", ""))
                slot = "S1"
                if "hukeying" in folder.name or "hukeying" in repo_str or "32cd826e" in str(r.get("branch", "")):
                    slot = "S3"
                elif "shaohua" in folder.name or "shaohua" in repo_str or "mu01" in str(r.get("host", "")):
                    slot = "S2"
                watch_on = global_on and bool(slot_states.get(slot, {}).get("enabled", True))
                rows.append(
                    dict(
                        id=folder.name,
                        repo=repo_str,
                        branch=r.get("branch", ""),
                        host=r.get("host", ""),
                        at=r.get("synced_at_utc", ""),
                        status=receipt_status(r) if watch_on else "paused",
                        watch_enabled=watch_on,
                        account_slot=slot,
                        source=r.get("source_commit", ""),
                        result_dir=str(folder),
                        sync_mode="results + deliverable" if r else "unverified",
                        steps=[
                            {"name": x.get("step", ""), "exit": x.get("exit_code"), "elapsed": x.get("elapsed_ms")}
                            for x in r.get("tasks_executed", [])
                            if isinstance(x, dict)
                        ],
                        title=note.get("title") or manifest.get("title") or folder.name,
                        prompt=redact(str(prompt)[:12000]),
                        prompt_source="manual" if note.get("prompt") else ("manifest" if prompt else "unrecorded"),
                    )
                )
        return sorted(rows, key=lambda r: r["at"], reverse=True)

    def record(self, payload):
        sid = payload.get("id", "")
        title = payload.get("title", "")
        prompt = payload.get("prompt", "")
        if not all(isinstance(x, str) for x in (sid, title, prompt)):
            raise ValueError("Text fields required")
        if sid not in {s["id"] for s in self.sessions()}:
            raise ValueError("Unknown session")
        if len(prompt) > 12000 or len(title) > 160:
            raise ValueError("Text too long")
        if SECRET.search(prompt):
            raise ValueError("Possible credential detected; remove secrets before saving")
        with self.lock:
            path = self.data / "sessions.json"
            notes = read_json(path, {}) or {}
            if sid in notes:
                with (self.data / "prompt-history.jsonl").open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"id": sid, **notes[sid]}, ensure_ascii=False) + "\n")
            notes[sid] = {"title": title, "prompt": prompt, "saved_at": stamp()}
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
            self.audit({"event": "prompt_saved", "session": sid})
        return {"ok": True}

    def control(self, name, action):
        if name not in ALLOWED or action not in {"start", "stop", "hide", "show", "open"}:
            raise ValueError("Protected or unknown action")
        if action == "open" and name != "arena-dsh-web":
            raise ValueError("Only DSH can be opened")
        if action in {"hide", "show"} and name != "arena-desktop-pet":
            raise ValueError("Only desktop pet can be hidden")
        if self.demo or os.name != "nt":
            raise ValueError("Preview is read-only; no Windows task changes")
        with self.lock:
            r = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(HERE / "control.ps1"),
                    "-Action",
                    action,
                    "-Name",
                    name,
                ],
                capture_output=True,
                timeout=35,
                creationflags=0x08000000,
            )
            self.audit({"event": "control", "name": name, "action": action, "exit": r.returncode})
        if r.returncode:
            raise ValueError(redact(r.stderr.decode("utf-8", "replace"))[:600])
        return {"ok": True, "note": "Command completed; wait for refreshed scheduler state"}

    def poll(self):
        tick = 0
        while True:
            try:
                if os.name == "nt" and not self.demo:
                    r = subprocess.run(
                        [
                            "powershell.exe",
                            "-NoProfile",
                            "-ExecutionPolicy",
                            "Bypass",
                            "-File",
                            str(HERE / "control.ps1"),
                            "-Action",
                            "snapshot",
                        ],
                        capture_output=True,
                        timeout=20,
                        creationflags=0x08000000,
                    )
                    if r.returncode:
                        raise ValueError("Windows scheduler query failed")
                    rows = json.loads(r.stdout.decode("utf-8-sig"))
                    self.tasks = rows if isinstance(rows, list) else [rows]
                    self.error = ""
                    wst = tri_account_console.get_watcher_state(self.data)
                    if wst.get("global_enabled", True):
                        hub_stopped = any(
                            isinstance(t, dict)
                            and (t.get("TaskName") == "git-sync-hub" or t.get("name") == "git-sync-hub")
                            and str(t.get("State") or t.get("state") or "") not in ("Running", "4")
                            for t in self.tasks
                        )
                        hub_stale = False
                        try:
                            hs = read_json(self.hub / "hub-state.json", {}) or {}
                            if hs.get("updated_at"):
                                h_age = time.time() - dt.datetime.fromisoformat(hs["updated_at"].replace("Z", "+00:00")).timestamp()
                                hub_stale = h_age > 180
                        except Exception:
                            pass
                        if hub_stopped or hub_stale:
                            subprocess.run(
                                ["schtasks.exe", "/Run", "/TN", "git-sync-hub"],
                                capture_output=True,
                                timeout=8,
                                creationflags=0x08000000,
                            )
                    if tick % 2 == 0:
                        if wst.get("global_enabled", True) and wst.get("sessions", {}).get("S3", {}).get("enabled", True):
                            tri_account_console.probe_and_sync_desktop_hub(self.data, self.results)
                    tick += 1
                elif self.demo:
                    self.error = ""
                else:
                    self.error = "Read-only preview: Windows scheduler is not available here"
                self.sampled = stamp()
            except Exception as e:
                self.error = str(e)
            time.sleep(30)

    def snapshot(self, origin_hint: str = ""):
        hub = read_json(self.hub / "hub-state.json", {}) or {}
        age = None
        try:
            age = max(0, round(time.time() - dt.datetime.fromisoformat(hub["updated_at"].replace("Z", "+00:00")).timestamp()))
        except (ValueError, KeyError):
            pass
        sessions = self.sessions()
        installs = (read_json(HERE / "software-registry.json", []) or []) + (read_json(self.data / "install-state.json", []) or [])
        latest = {}
        for item in installs:
            if isinstance(item, dict) and item.get("name") not in {"installer", "dsh-help", "dsh-plugin-help"}:
                latest[item.get("name", "")] = item
        return {
            "at": stamp(),
            "version": PANEL_VERSION,
            "demo": self.demo,
            "notion": NOTION,
            "repo_info": {
                "owner": "mqgg5630-cyber",
                "repo": "0fuye",
                "private": True,
                "branch": "arena/89735ee7-0fuye",
                "migrated_from": "mqgg5630-cyber/leanrea@arena/4d729933-leanrea",
            },
            "hub": hub,
            "heartbeat_age": age,
            "tasks": self.tasks,
            "tasks_sampled": self.sampled,
            "tasks_error": self.error,
            "sessions": sessions,
            "software": list(latest.values()),
            "software_catalog": self.ops.get_software_catalog_state(),
            "remote": self.ops.get_remote_state(),
            "gh_auth": self.ops.get_gh_state(),
            "connectors": self.ops.connectors,
            "appearance": self.ops.get_appearance(),
            "media_wallpapers": self.ops.list_media(),
            "thesis": thesis_ops.get_thesis_status(self.data),
            "coord": session_coord.get_coordination_state(self.data),
            "beacon": self.beacon.snapshot(preview_origin=origin_hint),
            "war_room": war_room.get_war_room_snapshot(self.data),
            "quota": ai_quota_hub.get_ai_quota_snapshot(self.data),
            "federation": self.federation.snapshot(),
            "tri_chat": tri_account_console.get_tri_chat_state(self.data),
            "autoheal_4step": read_json(self.data / "four-step-autoheal.json", {}) or {},
            "arena_windows": self.ops.get_arena_windows(),
            "media_cua": media_cua_hub.get_media_cua_snapshot(self.data),
            "personal_hub": read_json(HERE / "personal_hub.json", {}) or {},
            "love_local": self.ops.probe_love_local(),
            "mobile_qr": self.get_mobile_qr_bundle(origin_hint),
            "sync": {
                "policy": "results + deliverable; runtime code exists only for execution",
                "notion": "on-demand snapshots, not continuous synchronization",
            },
            "notion_snapshot": read_json(HERE / "notion-links.json", {}),
        }


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def host_ok(self):
        if getattr(self.server, "mobile_lan_only", False):
            return True
        host = self.headers.get("Host", "")
        return host in self.server.hosts or (
            self.server.store.demo and re.fullmatch(r"[a-zA-Z0-9.-]+(?::\d+)?", host) is not None
        )

    def _security_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        ancestors = "" if self.server.store.demo else "; frame-ancestors 'self'"
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            f"connect-src 'self'; img-src 'self' data: blob:; media-src 'self' data: blob:{ancestors}",
        )

    @staticmethod
    def _scrub_school_text(txt: str) -> str:
        for old, new in (
            ("鲁东大学学术硕士学位论文", "学术型硕士学位论文"),
            ("鲁东大学硕士学位论文", "学术型硕士学位论文"),
            ("鲁东大学硕士论文", "学术型硕士学位论文"),
            ("鲁东大学毕业课题", "硕士毕业课题"),
            ("鲁东大学", "高校"),
            ("鲁东", ""),
            ("ludong_master_2026", "academic_master_2026"),
            ("ludong_sample_thesis", "master_sample_thesis"),
            ("ldu-beacon-", "arena-beacon-"),
            ("Ludong University", "Graduate School"),
            ("Ludong", "Academic"),
            ("ludong", "academic"),
        ):
            txt = txt.replace(old, new)
        return txt

    def send(self, code, data, kind="application/json; charset=utf-8", extra_headers=None):
        if isinstance(data, (dict, list)):
            body = self._scrub_school_text(json.dumps(data, ensure_ascii=False)).encode("utf-8")
        else:
            body = data
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if getattr(self, "command", "GET") != "HEAD":
            self.wfile.write(body)

    def send_media_file(self, path: pathlib.Path, mime: str):
        total = path.stat().st_size
        rng = self.headers.get("Range", "")
        m = re.match(r"bytes=(\d+)-(\d*)", rng)
        try:
            if m:
                start = min(int(m.group(1)), max(0, total - 1))
                end = min(int(m.group(2)), total - 1) if m.group(2) else min(start + 4 * 1024 * 1024 - 1, total - 1)
                length = max(0, end - start + 1)
                with path.open("rb") as f:
                    f.seek(start)
                    chunk = f.read(length)
                self.send_response(206)
                self.send_header("Content-Type", mime)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
                self.send_header("Content-Length", str(len(chunk)))
                self.send_header("Cache-Control", "public, max-age=3600")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(chunk)
                return
            body = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_HEAD(self):
        return self.do_GET()

    def do_GET(self):
        if not self.host_ok():
            return self.send(403, {"error": "Host rejected"})
        parsed = urllib.parse.urlsplit(self.path)
        route = parsed.path

        if getattr(self.server, "mobile_lan_only", False):
            allowed_lan = (
                route in {
                    "/",
                    "/mobile",
                    "/mobile/",
                    "/mobile/mobile.css",
                    "/mobile/mobile.js",
                    "/mobile/manifest.webmanifest",
                    "/mobile/sw.js",
                    "/mobile/icon-192.png",
                    "/mobile/icon-512.png",
                    "/mobile/icon-maskable-512.png",
                    "/mobile/apple-touch-icon.png",
                    "/mobile/screen-narrow.png",
                    "/mobile/screen-wide.png",
                    "/favicon.ico",
                    "/api/mobile/state",
                    "/api/mobile/qr",
                    "/api/bootstrap",
                }
                or route.startswith("/assets/")
            )
            if not allowed_lan:
                return self.send(403, {"error": "LAN companion port serves mobile app only"})
            if route == "/":
                self.send_response(302)
                self.send_header("Location", "/mobile")
                self.end_headers()
                return

        if route == "/api/mobile/qr":
            req_host = self.headers.get("Host", "")
            scheme = "https" if req_host.endswith(".app") or req_host.endswith(".com") else "http"
            origin_hint = f"{scheme}://{req_host}" if req_host else ""
            return self.send(200, self.server.store.get_mobile_qr_bundle(origin_hint))
        if route == "/api/state":
            req_host = self.headers.get("Host", "")
            scheme = "https" if req_host.endswith(".app") or req_host.endswith(".com") else "http"
            origin_hint = f"{scheme}://{req_host}" if req_host else ""
            return self.send(200, self.server.store.snapshot(origin_hint))
        if route == "/api/bootstrap":
            return self.send(200, {"csrf": self.server.csrf, "readonly": self.server.store.demo, "version": PANEL_VERSION})
        if route == "/api/boot-ack":
            qs = dict(urllib.parse.parse_qsl(parsed.query))
            rec = {
                "ok": True,
                "dismissed_at": stamp(),
                "mode": str(qs.get("mode", "direct"))[:40],
                "active_tab": str(qs.get("tab", "overview"))[:40],
                "overlay_hidden": qs.get("hidden") == "1",
            }
            try:
                (self.server.store.data / "boot-ack.json").write_text(
                    json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except OSError:
                pass
            return self.send(200, rec)
        if route == "/api/coord/state":
            return self.send(200, session_coord.get_coordination_state(self.server.store.data))
        if route == "/api/war-room":
            return self.send(200, war_room.get_war_room_snapshot(self.server.store.data))
        if route == "/api/quota":
            return self.send(200, ai_quota_hub.get_ai_quota_snapshot(self.server.store.data))
        if route == "/api/quota/amp-calc":
            qs = dict(urllib.parse.parse_qsl(parsed.query))
            res = ai_quota_hub.compute_amp_metrics(qs.get("seq", ""))
            return self.send(200 if res.get("ok") else 400, res)
        if route == "/api/federation":
            return self.send(200, self.server.store.federation.snapshot())
        if route == "/api/media-cua":
            return self.send(200, media_cua_hub.get_media_cua_snapshot(self.server.store.data))
        if route == "/api/media-cua/parse":
            qs = dict(urllib.parse.parse_qsl(parsed.query))
            res = media_cua_hub.parse_share_input(qs.get("q", ""))
            return self.send(200 if res.get("ok") else 400, res)
        if route == "/api/federation/cgmd":
            qs = dict(urllib.parse.parse_qsl(parsed.query))
            topic = qs.get("topic") or self.server.store.federation.get_notify_config().get("ntfy_topic", "")
            bundle = federation_hub.generate_martini_cgmd_bundle(
                peptide_name=qs.get("name", "AMP_Cand01"),
                sequence=qs.get("seq", "GIGKFLHSAKKFGKAFVGEIMNS"),
                membrane_type=qs.get("membrane", "bacterial_inner"),
                sim_us=float(qs.get("us", "2.0") or 2.0),
                ntfy_topic=topic,
            )
            return self.send(200, {"ok": True, "bundle": bundle})
        if route == "/api/mobile/state":
            req_host = self.headers.get("Host", "")
            scheme = "https" if req_host.endswith(".app") or req_host.endswith(".com") else "http"
            origin_hint = f"{scheme}://{req_host}" if req_host else ""
            ph_data = read_json(HERE / "personal_hub.json", {}) or {}
            love_data = ph_data.get("love_hub") or {}
            return self.send(
                200,
                {
                    "host": os.environ.get("COMPUTERNAME") or pathlib.Path.home().name or "ArenaHost",
                    "version": PANEL_VERSION,
                    "beacon": self.server.store.beacon.snapshot(
                        port=self.server.server_port,
                        preview_origin=origin_hint,
                    ),
                    "gh_auth": self.server.store.ops.get_gh_state(),
                    "love_hub": {
                        "headline": love_data.get("headline", "💖 爱情与纪念空间"),
                        "subtitle": love_data.get("subtitle", ""),
                        "drive_root_url": love_data.get("drive_root_url", ""),
                        "media_bundle_url": love_data.get("media_bundle_url", ""),
                        "collections_count": len(love_data.get("collections") or []),
                        "items_count": sum(len(c.get("items") or []) for c in (love_data.get("collections") or [])),
                        "collections": love_data.get("collections") or [],
                        "playbooks": love_data.get("playbooks") or [],
                    },
                    "drive_folders": ph_data.get("drive_folders") or [],
                    "love_local": self.server.store.ops.probe_love_local(),
                    "mobile_qr": self.server.store.get_mobile_qr_bundle(origin_hint),
                    "war_room": war_room.get_war_room_snapshot(self.server.store.data),
                    "quota": ai_quota_hub.get_ai_quota_snapshot(self.server.store.data),
                    "federation": self.server.store.federation.snapshot(),
                },
            )
        if route == "/api/personal-hub":
            return self.send(200, read_json(HERE / "personal_hub.json", {}) or {})
        if route == "/api/thesis/status":
            return self.send(200, thesis_ops.get_thesis_status(self.server.store.data))
        if route == "/api/thesis/sample-run":
            qs = dict(urllib.parse.parse_qsl(parsed.query))
            res = self.server.store.run_ephemeral_sample_thesis(qs.get("profile_id") or qs.get("mode") or "academic_master_2026")
            return self.send(200 if res.get("ok") else 400, res)
        if route.startswith("/api/thesis/sample-download/"):
            kind = route.split("/api/thesis/sample-download/", 1)[1]
            if kind == "csl":
                csl_p, csl_name = thesis_ops.resolve_job_artifact(self.server.store.data, "csl", "csl")
                if csl_p and csl_p.is_file():
                    disp = urllib.parse.quote(csl_name or csl_p.name)
                    return self.send(
                        200,
                        csl_p.read_bytes(),
                        "application/xml; charset=utf-8",
                        {"Content-Disposition": f"attachment; filename*=UTF-8''{disp}"},
                    )
            cache = self.server.store.sample_preview_cache
            blob = (cache.get("blobs") or {}).get(kind)
            if blob:
                disp = urllib.parse.quote(blob["filename"])
                return self.send(
                    200,
                    blob["bytes"],
                    blob["mime"],
                    {"Content-Disposition": f"attachment; filename*=UTF-8''{disp}"},
                )
            return self.send(404, {"error": "Sample artifact not generated yet; run sample preview first"})
        if route.startswith("/api/thesis/download/"):
            rest = route.split("/api/thesis/download/", 1)[1]
            parts = rest.split("/", 1)
            if len(parts) == 2:
                raw_kind = parts[1]
                kind_alias = {
                    "final": "final",
                    "output": "final",
                    "new_docx": "final",
                    "docx": "final",
                    "compare": "compare",
                    "compare_docx": "compare",
                    "report": "report_md",
                    "report_md": "report_md",
                    "json": "report_json",
                    "report_json": "report_json",
                    "csl": "csl",
                }.get(raw_kind, raw_kind)
                mime_map = {
                    "final": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "compare": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "report_md": "text/markdown; charset=utf-8",
                    "report_json": "application/json; charset=utf-8",
                    "csl": "application/xml; charset=utf-8",
                }
                fpath, dl_name = thesis_ops.resolve_job_artifact(self.server.store.data, parts[0], kind_alias)
                if fpath and fpath.is_file():
                    disp = urllib.parse.quote(dl_name or fpath.name)
                    return self.send(
                        200,
                        fpath.read_bytes(),
                        mime_map.get(kind_alias, "application/octet-stream"),
                        {"Content-Disposition": f"attachment; filename*=UTF-8''{disp}"},
                    )
            return self.send(404, {"error": "Thesis artifact not found"})
        if route == "/api/script":
            qs = dict(urllib.parse.parse_qsl(parsed.query))
            fname, mime, body = self.server.store.ops.generate_bootstrap_script(qs)
            return self.send(200, body, mime, {"Content-Disposition": f'attachment; filename="{fname}"'})
        if route.startswith("/api/media/"):
            mid = route.split("/api/media/", 1)[1]
            if re.fullmatch(r"[0-9a-f]{16}", mid):
                mpath, mmime = self.server.store.ops.resolve_media(mid)
                if mpath:
                    return self.send_media_file(mpath, mmime)
            return self.send(404, {"error": "Media not found"})
        if route == "/favicon.ico":
            ico_p = HERE / "assets" / "ArenaDesk.ico"
            if ico_p.is_file():
                return self.send(200, ico_p.read_bytes(), "image/x-icon")
        if route.startswith("/assets/"):
            aname = route.split("/assets/", 1)[1]
            apath = HERE / "assets" / aname
            if aname in ASSET_MIMES and apath.is_file():
                mime = ASSET_MIMES[aname]
                if mime.startswith("video/"):
                    return self.send_media_file(apath, mime)
                return self.send(200, apath.read_bytes(), mime)
            return self.send(404, {"error": "Asset not found"})

        pwa_dir = HERE / "jobbeacon_src" / "jobbeacon" / "pwa"
        if not pwa_dir.is_dir():
            pwa_dir = HERE.parent.parent / "projects" / "jobbeacon" / "src" / "jobbeacon" / "pwa"

        if route in {
            "/mobile/icon-192.png",
            "/mobile/icon-512.png",
            "/mobile/icon-maskable-512.png",
            "/mobile/apple-touch-icon.png",
            "/mobile/screen-narrow.png",
            "/mobile/screen-wide.png",
        }:
            pwa_icon = pwa_dir / route.split("/mobile/", 1)[1]
            if pwa_icon.is_file():
                return self.send(200, pwa_icon.read_bytes(), "image/png", {"Cache-Control": "public, max-age=3600"})
            png_p = HERE / "assets" / "icon-256.png"
            if png_p.is_file():
                return self.send(200, png_p.read_bytes(), "image/png", {"Cache-Control": "public, max-age=3600"})

        files = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
        if route in files:
            mime = {
                "/": "text/html; charset=utf-8",
                "/app.js": "text/javascript; charset=utf-8",
                "/style.css": "text/css; charset=utf-8",
            }
            return self.send(200, (HERE / files[route]).read_bytes(), mime[route])

        pwa_routes = {
            "/mobile": ("mobile.html", "text/html; charset=utf-8"),
            "/mobile/": ("mobile.html", "text/html; charset=utf-8"),
            "/mobile/mobile.css": ("mobile.css", "text/css; charset=utf-8"),
            "/mobile/mobile.js": ("mobile.js", "text/javascript; charset=utf-8"),
            "/mobile/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json; charset=utf-8"),
            "/mobile/sw.js": ("sw.js", "text/javascript; charset=utf-8"),
        }
        if route in pwa_routes and pwa_dir.is_dir():
            fname, fmime = pwa_routes[route]
            fp = pwa_dir / fname
            if fp.is_file():
                return self.send(200, fp.read_bytes(), fmime)

        return self.send(404, {"error": "Not found"})

    def do_POST(self):
        if getattr(self.server, "mobile_lan_only", False):
            return self.send(403, {"error": "Read-only LAN mobile bridge"})
        if not self.host_ok():
            return self.send(403, {"error": "Host rejected"})
        origin = self.headers.get("Origin", "")
        demo_safe_post = self.server.store.demo and self.path in {"/api/watcher/toggle", "/api/tri-chat/send", "/api/system/auto-heal-4step"}
        origin_allowed = (origin in self.server.origins) or (demo_safe_post and origin.startswith(("http://", "https://")))
        if not origin_allowed or not secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), self.server.csrf):
            return self.send(403, {"error": "Origin/CSRF rejected"})
        if self.server.store.demo and not demo_safe_post:
            return self.send(403, {"error": "Read-only preview"})
        try:
            max_body = 20_000_000 if self.path == "/api/thesis/format" else 65536
            n = int(self.headers.get("Content-Length", "0"))
            if n <= 0 or n > max_body:
                raise ValueError("Invalid body length")
            if self.headers.get_content_type() != "application/json":
                raise ValueError("JSON required")
            data = json.loads(self.rfile.read(n))
            if not isinstance(data, dict):
                raise ValueError("Object required")

            ops = self.server.store.ops
            sdata = self.server.store.data
            if self.path == "/api/session":
                result = self.server.store.record(data)
            elif self.path == "/api/control":
                result = self.server.store.control(data.get("name"), data.get("action"))
            elif self.path == "/api/appearance":
                result = ops.save_appearance(data)
            elif self.path == "/api/media/scan":
                result = {"ok": True, "media": ops.refresh_media_index()}
            elif self.path == "/api/software/scan":
                result = {"ok": True, "scan": ops.scan_software()}
            elif self.path == "/api/software/install":
                result = ops.start_install(
                    str(data.get("pkg_id", "")),
                    str(data.get("custom_spec", "")),
                    str(data.get("manager", "winget")),
                    str(data.get("drive", "E:")),
                )
            elif self.path == "/api/remote/probe":
                result = {"ok": True, "status": ops.probe_remotes()}
            elif self.path == "/api/remote/host":
                result = {"ok": True, "status": ops.add_remote_host(data)}
            elif self.path == "/api/remote/action":
                result = ops.run_remote_action(str(data.get("host_id", "")), str(data.get("action", "")), str(data.get("cmd", "")))
            elif self.path == "/api/gh/action":
                result = ops.run_gh_action(str(data.get("action", "check")))
            elif self.path == "/api/thesis/format":
                lease = session_coord.acquire_lease(sdata, "thesis-formatter", ttl_sec=180, purpose="Lark-Formatter thesis run")
                if not lease.get("ok"):
                    raise ValueError(lease.get("error", "Thesis formatter busy"))
                try:
                    norm_payload = {
                        "profile_id": str(data.get("profile_id") or data.get("mode") or "academic_master_2026"),
                        "doc_path": str(data.get("doc_path") or data.get("source_path") or ""),
                        "filename": str(data.get("filename") or data.get("upload_name") or ""),
                        "data_base64": str(data.get("data_base64") or data.get("upload_b64") or ""),
                        "use_sample": bool(data.get("use_sample", False)),
                        "template_docx_path": str(data.get("template_docx_path") or data.get("template_path") or ""),
                        "options": data.get("options") if isinstance(data.get("options"), dict) else None,
                    }
                    result = thesis_ops.run_thesis_format(sdata, norm_payload, ephemeral=False)
                    if (
                        result.get("ok")
                        and bool(data.get("save_alongside"))
                        and norm_payload["doc_path"]
                        and pathlib.Path(norm_payload["doc_path"]).is_file()
                    ):
                        src_p = pathlib.Path(norm_payload["doc_path"])
                        out_final = ((result.get("job") or {}).get("output_paths") or {}).get("final") or ""
                        if out_final and pathlib.Path(out_final).is_file():
                            alongside_p = src_p.with_name(f"{src_p.stem}_formatted.docx")
                            shutil.copy2(out_final, alongside_p)
                            result["job"]["saved_alongside"] = str(alongside_p)
                finally:
                    session_coord.release_lease(sdata, "thesis-formatter")
            elif self.path == "/api/thesis/open-dir":
                if os.name != "nt":
                    raise ValueError("仅在 Windows 本机桌面端支持打开资源管理器")
                jid = str(data.get("job_id", ""))
                fpath, _ = thesis_ops.resolve_job_artifact(sdata, jid, "final")
                if not fpath:
                    raise ValueError("未找到对应排版产物目录")
                subprocess.Popen(["explorer.exe", str(fpath.parent)])
                result = {"ok": True, "opened": str(fpath.parent)}
            elif self.path == "/api/coord/heartbeat":
                result = session_coord.register_heartbeat(sdata, data)
            elif self.path == "/api/coord/lease":
                result = session_coord.acquire_lease(
                    sdata,
                    str(data.get("resource", "shared")),
                    str(data.get("holder") or session_coord.CURRENT_SESSION_ID),
                    int(data.get("ttl_sec", 120)),
                    str(data.get("purpose", "")),
                )
            elif self.path == "/api/coord/release":
                result = session_coord.release_lease(
                    sdata,
                    str(data.get("resource", "shared")),
                    str(data.get("holder") or session_coord.CURRENT_SESSION_ID),
                )
            elif self.path == "/api/coord/note":
                result = session_coord.post_handoff_note(
                    sdata,
                    str(data.get("session_id") or session_coord.CURRENT_SESSION_ID),
                    str(data.get("summary", "")),
                    data.get("tags") if isinstance(data.get("tags"), list) else None,
                )
            elif self.path == "/api/mobile/quick-cmd":
                result = self.server.store.beacon.execute_quick_command(
                    str(data.get("cmd_id", "")),
                    gate_queue_cb=lambda g: war_room.enqueue_gate(sdata, g),
                )
            elif self.path == "/api/beacon/watch":
                result = {"ok": True, "watch": self.server.store.beacon.upsert_watch(data)}
            elif self.path == "/api/beacon/notify-config":
                result = {"ok": True, "config": self.server.store.beacon.save_notify_config(data)}
            elif self.path == "/api/war-room/handoff":
                result = {"ok": True, "handoff": war_room.post_bot_handoff(sdata, data)}
            elif self.path == "/api/war-room/gate":
                result = war_room.decide_gate(
                    sdata,
                    str(data.get("gate_id", "")),
                    str(data.get("decision", "reject")),
                )
            elif self.path == "/api/quota/burn":
                result = {"ok": True, "item": ai_quota_hub.add_burn_task(sdata, data)}
            elif self.path == "/api/federation/dispatch":
                result = self.server.store.federation.create_dispatch(
                    target_node=str(data.get("target_node", "desktop_hukeying")),
                    title=str(data.get("title", "")),
                    objective=str(data.get("objective", "")),
                    peptide_seq=str(data.get("peptide_seq", "")),
                )
            elif self.path == "/api/federation/session-bind":
                result = self.server.store.federation.update_session_binding(
                    session_slot=str(data.get("session_slot", "")),
                    branch_or_repo=str(data.get("branch_or_repo", "")),
                    status=str(data.get("status", "active")),
                )
            elif self.path == "/api/federation/notify-config":
                result = {"ok": True, "config": self.server.store.federation.update_notify_config(data)}
            elif self.path == "/api/federation/notify-test":
                result = self.server.store.federation.send_test_notification(str(data.get("message", "")))
            elif self.path == "/api/federation/arena-window":
                result = ops.manage_arena_window(
                    action=str(data.get("action", "open")),
                    slot=str(data.get("slot", "S1")),
                    url=str(data.get("url", "")),
                )
            elif self.path == "/api/watcher/toggle":
                result = tri_account_console.toggle_watcher(
                    sdata,
                    target=str(data.get("target", "ALL")),
                    enabled=bool(data.get("enabled", True)),
                )
            elif self.path == "/api/tri-chat/send":
                result = tri_account_console.handle_tri_chat_message(
                    sdata,
                    self.server.store.results,
                    slot=str(data.get("slot", "S1")),
                    message=str(data.get("message", "")),
                    demo=self.server.store.demo,
                )
            elif self.path == "/api/desktop/sync-hub":
                result = tri_account_console.probe_and_sync_desktop_hub(
                    sdata,
                    self.server.store.results,
                )
            elif self.path == "/api/system/auto-heal-4step":
                result = tri_account_console.run_four_step_autoheal(
                    sdata,
                    self.server.store.results,
                    demo=self.server.store.demo,
                )
            elif self.path == "/api/mobile/start-tunnel":
                result = self.server.store.start_cloudflared_tunnel()
                result["qr"] = self.server.store.get_mobile_qr_bundle()
            elif self.path == "/api/media-cua/job":
                result = media_cua_hub.enqueue_media_job(
                    sdata,
                    raw_input=str(data.get("input", "")),
                    mode=str(data.get("mode", "video_best")),
                    execute_local=(not self.server.store.demo),
                )
            else:
                return self.send(404, {"error": "Not found"})
            self.send(200 if result.get("ok", True) else 400, result)
        except (ValueError, TypeError, subprocess.TimeoutExpired) as e:
            self.send(400, {"error": str(e)})
        except Exception:
            self.send(500, {"error": "Operation failed; see local diagnostics"})


def make_server(bind, port, store, extra_hosts=(), mobile_lan_only=False):
    s = http.server.ThreadingHTTPServer((bind, port), Handler)
    s.store = store
    s.csrf = secrets.token_urlsafe(32)
    s.mobile_lan_only = mobile_lan_only
    p = s.server_port
    s.hosts = {f"127.0.0.1:{p}", f"localhost:{p}", *extra_hosts}
    s.origins = {f"{scheme}://{h}" for h in s.hosts for scheme in ("http", "https")}
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=18765)
    ap.add_argument("--lan-mobile-port", type=int, default=18766)
    ap.add_argument("--data", default=str(HERE / "data"))
    ap.add_argument("--results", default="E:/0github/results")
    ap.add_argument("--hub", default=str(pathlib.Path.home() / ".git-sync-hub"))
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--allow-host", action="append", default=[])
    a = ap.parse_args()
    if not a.demo and a.bind not in ("127.0.0.1", "localhost"):
        raise SystemExit("Writable control plane must remain loopback-only")
    store = Store(pathlib.Path(a.data), pathlib.Path(a.results), pathlib.Path(a.hub), a.demo)
    server = make_server(a.bind, a.port, store, a.allow_host)
    if not a.demo and a.lan_mobile_port > 0:
        try:
            lan_srv = make_server("0.0.0.0", a.lan_mobile_port, store, mobile_lan_only=True)
            store.lan_bridge_port = lan_srv.server_port
            store.lan_bridge_active = True
            threading.Thread(target=lan_srv.serve_forever, daemon=True).start()
        except OSError:
            store.lan_bridge_active = False
    if not a.demo and os.name == "nt":
        threading.Thread(target=store.start_cloudflared_tunnel, daemon=True).start()
    threading.Thread(target=store.poll, daemon=True).start()
    print(
        "Arena Desk v%s listening on %s:%s (%s)" % (PANEL_VERSION, a.bind, a.port, "read-only preview" if a.demo else "local control"),
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
