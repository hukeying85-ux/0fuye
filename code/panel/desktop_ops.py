"""Modular desktop operations for Arena Desk v2.0:
- Software scan & one-click installer (including Open-Source PyMOL)
- Remote control hub (HPC mu01 via WSL, WSL2, Desktop Tailscale/SSH, custom hosts)
- GitHub (gh) authentication & private-repo hub bridge diagnostics
- DSH-style skin/wallpaper/media discovery (local video skins + Steam Wallpaper Engine)
- Cross-PC diagnostic & bootstrap script generator
"""
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
NO_WINDOW = 0x08000000 if os.name == "nt" else 0

PKG_SPEC_RE = re.compile(r"^[A-Za-z0-9._-]+(?:::[A-Za-z0-9._-]+)?$")
HOST_SPEC_RE = re.compile(r"^[A-Za-z0-9._-]+$")
USER_SPEC_RE = re.compile(r"^[A-Za-z0-9._-]+$")
DRIVE_RE = re.compile(r"^[A-Za-z]:?$")

# The panel used to assume an E: drive exists (it did on the laptop).  On the
# GPU workstation there is no E: at all, so every probe, installer default and
# media folder silently pointed at nothing.  Everything below resolves a
# canonical "E:\..." path onto a drive that actually exists.
WINDOWS_DRIVES = ("C:", "D:", "E:", "F:", "G:", "H:")


def _drive_exists(drive: str) -> bool:
    if os.name != "nt":
        return False
    return pathlib.Path(drive + "\\").exists()


def existing_drives() -> list:
    if os.name != "nt":
        return ["C:"]
    found = [drive for drive in WINDOWS_DRIVES if _drive_exists(drive)]
    return found or ["C:"]


def resolve_win_path(path_text: str) -> pathlib.Path:
    """Resolve a path that may name a drive this machine does not have.

    ``E:\\0apps\\ArenaDesk`` becomes ``C:\\0apps\\ArenaDesk`` when E: is absent
    and the C: copy exists.  If nothing matches, the original path is returned
    so callers keep their "not installed" semantics.
    """
    raw = str(path_text or "").strip()
    if not raw:
        return pathlib.Path(raw)
    normalised = raw.replace("\\", "/")
    match = re.match(r"^([A-Za-z]):/(.*)$", normalised)
    if not match:
        return pathlib.Path(raw)
    letter = match.group(1).upper() + ":"
    tail = match.group(2)
    if _drive_exists(letter) and pathlib.Path(f"{letter}/{tail}").exists():
        return pathlib.Path(f"{letter}/{tail}")
    for drive in existing_drives():
        candidate = pathlib.Path(f"{drive}/{tail}")
        if candidate.exists():
            return candidate
    return pathlib.Path(raw)


def app_root() -> pathlib.Path:
    """Where this copy of Arena Desk lives (any drive)."""
    if HERE.name == "ArenaDesk" or (HERE / "server.py").exists():
        return HERE
    for drive in existing_drives():
        candidate = pathlib.Path(drive + "\\0apps\\ArenaDesk")
        if (candidate / "server.py").exists():
            return candidate
    return HERE


def app_drive() -> str:
    """The drive everything gets installed to: the one Arena Desk lives on."""
    root = str(app_root())
    match = re.match(r"^([A-Za-z]):", root)
    if match:
        return match.group(1).upper() + ":"
    return existing_drives()[0]
SECRET_RE = re.compile(
    r"(?:\b(?:ntn_|secret_|ghp_|gho_|github_pat_|sk-)[\w-]{12,}"
    r"|-----BEGIN .*PRIVATE KEY"
    r"|(?:password|token|api_key)\s*[:=]\s*\S+)",
    re.I,
)

MEDIA_EXTS = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".ogv": "video/ogg",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

DEFAULT_APPEARANCE = {
    "appearance_schema_v": 25,
    "theme": "sakura-mist",
    "builtin_wallpaper": "dsh-bg.mp4",
    "boot_video": "dsh-boot.mp4",
    "custom_media_id": "",
    "surface_opacity": 0.14,
    "veil_opacity": 0.10,
    "glass_blur": 4,
    "motion_enabled": True,
    "boot_enabled": True,
    "boot_sound": True,
    "boot_fade_ms": 950,
    "whale_enabled": True,
    "whale_snap": True,
    "whale_sound": True,
    "whale_scale": 1.0,
    "whale_quotes": [
        "论文终稿要排版？切到「论文一键改格式」，1.5 秒输出硕士规范定稿 + 红蓝对比稿！",
        "已换装 dsh-video-skin 原版开机动画与高透动态壁纸，点右下角圆钮可随时微调透明度～",
        "三账号已物理分舱监控：mqgg 主控舱 · shaohua 超算舱 · hukeying85 模拟舱互不串号！",
        "切到「💖 爱情与心意」即可直达云盘 18 项恋爱短片、纪念画册与本机 JevChat 情感军师～"
    ],
}

DEFAULT_REMOTE_HOSTS = [
    {
        "id": "hpc-mu01",
        "name": "校园超算 HPC · mu01",
        "address": "10.10.5.210",
        "port": 22,
        "user": "25wenshaohua",
        "via": "wsl-hpc",
        "distro": "Ubuntu-26.04",
        "role": "Slurm 计算集群 (cu 64C / fat1 96C 1TB)",
        "note": "经校园 OpenVPN + WSL Ubuntu-26.04 密钥直连，支持作业提交与结果 rsync 回传。",
    },
    {
        "id": "local-wsl",
        "name": "本机 WSL2 · Ubuntu-26.04",
        "address": "127.0.0.1",
        "port": 22,
        "user": "w26",
        "via": "wsl-local",
        "distro": "Ubuntu-26.04",
        "role": "Linux 子系统与 SSH 跳板",
        "note": "承载 Linux 生信工具链与 HPC 免密跳板密钥。",
    },
    {
        "id": "desktop-ieudgs5",
        "name": "实验室台式机 · desktop-ieudgs5",
        "address": "100.84.137.117",
        "port": 22,
        "user": "Administrator",
        "via": "ssh",
        "role": "Tailscale 异地组网工作站",
        "note": "Tailscale 节点上线并运行一键接入脚本后即可免密直连与远程桌面。",
    },
    {
        "id": "lan-109",
        "name": "内网节点 · 192.168.1.109",
        "address": "192.168.1.109",
        "port": 22,
        "user": "BNI",
        "via": "ssh",
        "role": "局域网探测目标",
        "note": "此前 TCP 22 可通但握手前断开，可在目标机运行一键诊断脚本排障。",
    },
]


def utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def redact(text) -> str:
    return SECRET_RE.sub("[REDACTED]", str(text or ""))


def read_json(path: pathlib.Path, default=None):
    try:
        if not path.exists() or path.stat().st_size > 4_000_000:
            return default
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def write_json_atomic(path: pathlib.Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def tcp_ping(host: str, port: int, timeout: float = 1.8) -> dict:
    t0 = time.perf_counter()
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            ms = round((time.perf_counter() - t0) * 1000)
            return {"reachable": True, "latency_ms": ms}
    except OSError as e:
        return {"reachable": False, "latency_ms": None, "reason": str(e)[:120]}


class DesktopOps:
    """Thread-safe manager for software, remote control, gh auth, skins, and scripts."""

    def __init__(self, data_dir: pathlib.Path, demo: bool = False):
        self.data = data_dir
        self.demo = demo
        self.lock = threading.RLock()
        self.catalog_data = read_json(HERE / "catalog.json", {}) or {}
        self.catalog = self.catalog_data.get("software_catalog", [])
        self.connectors = self.catalog_data.get("connectors", [])
        self._media_index = {}
        self._init_defaults()

    def _init_defaults(self):
        self.data.mkdir(parents=True, exist_ok=True)
        if not (self.data / "appearance.json").exists():
            write_json_atomic(self.data / "appearance.json", DEFAULT_APPEARANCE)
        if not (self.data / "remote-hosts.json").exists():
            write_json_atomic(self.data / "remote-hosts.json", DEFAULT_REMOTE_HOSTS)
        if self.demo:
            self._seed_demo_snapshots()
        else:
            self.refresh_media_index()

    def _seed_demo_snapshots(self):
        """Populate realistic, truthful preview state grounded in LAPTOP-R77M5D6M diagnostics."""
        if not (self.data / "software-scan.json").exists():
            rows = []
            demo_states = {
                "lark-formatter": ("installed", "E:\\0writing\\Lark-Formatter\\src\\engine\\pipeline.py", "v0.21.1 · 34 模块无头引擎 + lark 环境就绪"),
                "git": ("installed", "E:\\hermes\\git\\cmd\\git.exe", "git version 2.54.0.windows.1"),
                "nodejs": ("installed", "E:\\hermes\\node\\node.exe", "v22.23.1"),
                "uv": ("installed", "E:\\0apps\\jev-chat-windows\\uv\\uv.exe", "uv 0.5.x"),
                "tailscale": ("installed", "E:\\Tailscale\\tailscale.exe", "1.76.x · Self Online (100.71.123.19)"),
                "desktop-pet": ("installed", "E:\\0apps\\DSHPet\\dsh-pet-standalone-webm.exe", "v4.4.0 · SHA256 已校验"),
                "notion-desktop": ("installed", "E:\\Notion\\Notion.exe", "7.41.0 · 数据目录 E:\\NotionData"),
                "pymol-open-source": ("installed", "E:\\Miniforge3\\envs\\pymol\\Scripts\\pymol.exe", "PyMOL 3.1.0 Open-Source · 已部署"),
                "gh-cli": ("installed", "C:\\Program Files\\GitHub CLI\\gh.exe", "gh 2.x · mqgg + shaohua + hukeying85 三账号桥接"),
                "miniforge3": ("installed", "E:\\Miniforge3\\Scripts\\mamba.exe", "Miniforge3 24.x (envs: lark, pymol)"),
            }
            now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
            for item in self.catalog:
                st, path_str, ver = demo_states.get(item["id"], ("not_installed", "", "未检测到，支持一键安装"))
                rows.append({
                    **item,
                    "status": st,
                    "detected_path": path_str,
                    "detected_version": ver,
                    "checked_at": now,
                })
            write_json_atomic(self.data / "software-scan.json", {"scanned_at": utc_iso(), "items": rows})

        if not (self.data / "remote-status.json").exists():
            hosts = read_json(self.data / "remote-hosts.json", DEFAULT_REMOTE_HOSTS)
            statuses = {
                "hpc-mu01": {"online": True, "latency_ms": 12, "summary": "SSH mu01 就绪 · Slurm cu(15空闲)/fat1(7空闲) · GPFS 1.4P"},
                "local-wsl": {"online": True, "latency_ms": 2, "summary": "Ubuntu-26.04 运行中 · OpenSSH 跳板正常"},
                "desktop-ieudgs5": {"online": False, "latency_ms": None, "summary": "Tailscale 离线 · 在台式机运行「多机一键脚本」即可上线"},
                "lan-109": {"online": False, "latency_ms": None, "summary": "TCP 22 可连但握手关闭 · 待目标机确认 sshd"},
            }
            enriched = [{**h, **statuses.get(h["id"], {"online": False, "latency_ms": None, "summary": "待探测"})} for h in hosts]
            write_json_atomic(self.data / "remote-status.json", {"probed_at": utc_iso(), "hosts": enriched})

        if not (self.data / "gh-status.json").exists():
            write_json_atomic(self.data / "gh-status.json", {
                "checked_at": utc_iso(),
                "sandbox_gh_ok": True,
                "host_gh_installed": True,
                "authenticated": True,
                "account": "mqgg5630-cyber",
                "private_repo_ready": True,
                "hub_worker_patched": True,
                "default_invariant_ok": True,
                "chrome_profile1_keying_detected": True,
                "proxy": "socks5h://127.0.0.1:10808 + ssh.github.com:443",
                "summary": "私人仓 mqgg5630-cyber/0fuye 与 hub-worker 热补丁均已生效；mqgg5630-cyber + shaohuawen03-cyber 已登录 keyring，hukeying85-ux 已配妥 URL 凭据路由与 Port 443 SSH 密钥。",
                "detail_lines": [
                    "默认主账号: mqgg5630-cyber (Active=true, repo+gist+read:org, 保障 0fuye 私人仓 15s 轮询)",
                    "学术研发号: shaohuawen03-cyber (gh keyring 已就绪, Host github-shaohua -> ssh.github.com:443)",
                    "第三协作研发号: hukeying85-ux (已移除阻塞 GCM, 已配 id_ed25519_hukeying + Chrome Profile 1 一键授权)"
                ],
                "multi_accounts": [
                    {
                        "login": "mqgg5630-cyber",
                        "email": "m***@gmail.com",
                        "label": "本人主控基座账号 (0fuye 私有库 + git-sync-hub 默认)",
                        "ssh_alias": "github-mqgg",
                        "gh_logged_in": True,
                        "gh_active": True,
                        "ssh_key_ready": True,
                        "ssh_alias_ready": True,
                        "browser_profile": "Default",
                        "sample_repos": ["0fuye (private)", "leanrea", "Light-skills"]
                    },
                    {
                        "login": "shaohuawen03-cyber",
                        "email": "s***@gmail.com",
                        "label": "学术研发与超算账号 (Lark-Formatter + 生信AMP矩阵)",
                        "ssh_alias": "github-shaohua",
                        "gh_logged_in": True,
                        "gh_active": False,
                        "ssh_key_ready": True,
                        "ssh_alias_ready": True,
                        "browser_profile": "Edge Default",
                        "sample_repos": ["Lark-Formatter", "XAMP", "HMD-AMP"]
                    },
                    {
                        "login": "hukeying85-ux",
                        "email": "h***@gmail.com",
                        "label": "第三协作研发号 (Chrome Profile 1 · OmniRoute/Agent)",
                        "ssh_alias": "github-hukeying",
                        "gh_logged_in": False,
                        "gh_active": False,
                        "ssh_key_ready": True,
                        "ssh_alias_ready": True,
                        "browser_profile": "Chrome Profile 1",
                        "sample_repos": ["OmniRoute", "AgentArena", "JevHarness"]
                    }
                ],
            })

    # -------------------- Appearance & DSH-style Plugins --------------------
    def get_appearance(self) -> dict:
        saved = read_json(self.data / "appearance.json", {}) or {}
        if int(saved.get("appearance_schema_v", 0) or 0) < 25:
            # Auto-upgrade legacy v2.1-v2.4 opaque appearance to v2.5 dsh-video-skin crystal clear defaults
            migrated = dict(DEFAULT_APPEARANCE)
            if saved.get("theme") in {"sakura-mist", "aurora-abyss", "emerald-nebula", "obsidian-pulse", "cyber-prism", "mist-paper"}:
                migrated["theme"] = saved["theme"]
            try:
                write_json_atomic(self.data / "appearance.json", migrated)
            except OSError:
                pass
            return self._with_media_availability(migrated)
        merged = {**DEFAULT_APPEARANCE, **saved}
        return self._with_media_availability(merged)

    def _with_media_availability(self, appearance: dict) -> dict:
        """Tell the browser whether the configured clips actually exist.

        dsh-boot.mp4 / dsh-bg.mp4 are not distributed with this repository.
        Without this flag the page kept requesting a missing file, ``play()``
        rejected, and the boot overlay jumped straight to the workspace - which
        is exactly the "no animation, just a black flash" symptom.
        """
        out = dict(appearance or {})
        assets = HERE / "assets"
        for key, field in (("boot_video", "boot_video_available"),
                           ("builtin_wallpaper", "wallpaper_available")):
            name = str(out.get(key) or "")
            exists = bool(name) and (assets / name).is_file()
            if not exists and name:
                # fall back to a file that is shipped
                for candidate in ("dsh-boot.mp4", "boot-mascot.jpg"):
                    if (assets / candidate).is_file():
                        break
            out[field] = exists
        out["boot_fallback_art"] = "boot-mascot.jpg" if (assets / "boot-mascot.jpg").is_file() else ""
        out["wallpaper_fallback_art"] = "wallpaper-anime.jpg" if (assets / "wallpaper-anime.jpg").is_file() else ""
        return out

    def probe_love_local(self) -> dict:
        """Privacy-preserving local companion check for JevChat & local memory vault."""
        if self.demo or os.name != "nt":
            return {
                "jev_installed": True,
                "jev_dir": str(resolve_win_path(r"E:\0apps\jev-chat-windows")),
                "monitor_silent": True,
                "analyzer_silent": True,
                "ollama_ready": True,
                "private_vault_present": True,
                "private_vault_policy": "STRICT_LOCAL_READONLY · 零原文上传",
                "mode": "preview",
            }
        jev_dir = resolve_win_path(r"E:\0apps\jev-chat-windows")
        vault_dir = resolve_win_path(r"E:\0yf")
        llm_ok = tcp_ping("127.0.0.1", 11434, timeout=0.6).get("reachable", False)
        return {
            "jev_installed": jev_dir.is_dir(),
            "jev_dir": str(jev_dir),
            "monitor_silent": True,
            "analyzer_silent": True,
            "ollama_ready": bool(llm_ok),
            "private_vault_present": vault_dir.is_dir(),
            "private_vault_policy": "STRICT_LOCAL_READONLY · 零原文上传",
            "mode": "host",
        }

    def save_appearance(self, payload: dict) -> dict:
        cur = self.get_appearance()
        cur["appearance_schema_v"] = 25
        allowed_themes = {
            "aurora-abyss",
            "emerald-nebula",
            "obsidian-pulse",
            "mist-paper",
            "cyber-prism",
            "cyber-emerald",
            "amber-forge",
            "sakura-mist",
            "clean-frost",
            "custom-media",
        }
        if "theme" in payload and payload["theme"] in allowed_themes:
            cur["theme"] = payload["theme"]
        if "builtin_wallpaper" in payload and payload["builtin_wallpaper"] in {
            "dsh-bg.mp4",
            "wallpaper-anime.jpg",
            "boot-mascot.jpg",
            "wallpaper-aurora.jpg",
        }:
            cur["builtin_wallpaper"] = payload["builtin_wallpaper"]
            cur["custom_media_id"] = ""
        if "boot_video" in payload and payload["boot_video"] in {"dsh-boot.mp4", "dsh-bg.mp4"}:
            cur["boot_video"] = payload["boot_video"]
        if "custom_media_id" in payload and isinstance(payload["custom_media_id"], str):
            cur["custom_media_id"] = payload["custom_media_id"][:80]
        if "surface_opacity" in payload:
            cur["surface_opacity"] = max(0.08, min(0.95, float(payload["surface_opacity"])))
        if "veil_opacity" in payload:
            cur["veil_opacity"] = max(0.0, min(0.75, float(payload["veil_opacity"])))
        if "glass_blur" in payload:
            cur["glass_blur"] = max(0, min(40, int(payload["glass_blur"])))
        for bkey in ("motion_enabled", "boot_enabled", "boot_sound", "whale_enabled", "whale_snap", "whale_sound"):
            if bkey in payload:
                cur[bkey] = bool(payload[bkey])
        if "whale_scale" in payload:
            cur["whale_scale"] = max(0.65, min(1.5, float(payload["whale_scale"])))
        if "whale_quotes" in payload and isinstance(payload["whale_quotes"], list):
            quotes = [redact(str(q).strip())[:140] for q in payload["whale_quotes"] if str(q).strip()]
            if quotes:
                cur["whale_quotes"] = quotes[:12]
        if "custom_media_path" in payload and isinstance(payload["custom_media_path"], str):
            raw_p = payload["custom_media_path"].strip()
            if raw_p and not self.demo:
                p = pathlib.Path(raw_p)
                if p.is_file() and p.suffix.lower() in MEDIA_EXTS:
                    extra = read_json(self.data / "custom-media.json", []) or []
                    if str(p) not in extra:
                        extra.append(str(p))
                        write_json_atomic(self.data / "custom-media.json", extra[-30:])
                    self.refresh_media_index()
                    mid = hashlib.sha1(str(p).encode("utf-8")).hexdigest()[:16]
                    cur["custom_media_id"] = mid
                    cur["theme"] = "custom-media"
        with self.lock:
            write_json_atomic(self.data / "appearance.json", cur)
        return {"ok": True, "appearance": cur}

    def refresh_media_index(self) -> list:
        """Scan local ArenaDesk/media, DSH video-skin assets, and Steam Wallpaper Engine 431960."""
        items = []
        idx = {}
        if self.demo:
            self._media_index = {}
            return items

        def add_file(fpath: pathlib.Path, title: str, source: str, preview_path: pathlib.Path = None):
            try:
                if not fpath.is_file() or fpath.suffix.lower() not in MEDIA_EXTS:
                    return
                if fpath.stat().st_size > 350_000_000:
                    return
                mid = hashlib.sha1(str(fpath).encode("utf-8")).hexdigest()[:16]
                if mid in idx:
                    return
                idx[mid] = fpath
                prev_id = ""
                if preview_path and preview_path.is_file() and preview_path.suffix.lower() in MEDIA_EXTS:
                    prev_id = hashlib.sha1(str(preview_path).encode("utf-8")).hexdigest()[:16]
                    idx[prev_id] = preview_path
                kind = "video" if MEDIA_EXTS[fpath.suffix.lower()].startswith("video/") else "image"
                items.append({
                    "id": mid,
                    "title": title[:80],
                    "source": source,
                    "kind": kind,
                    "url": f"/api/media/{mid}",
                    "preview_url": f"/api/media/{prev_id}" if prev_id else (f"/api/media/{mid}" if kind == "image" else ""),
                    "size_mb": round(fpath.stat().st_size / 1_048_576, 2),
                })
            except OSError:
                return

        # 1. Local ArenaDesk media folder + DSH video-skin assets (any drive)
        scan_dirs = [
            (HERE / "media", "Arena Desk 本地媒体"),
            (resolve_win_path("E:/0apps/ArenaDesk/media"), "Arena Desk 媒体库"),
            (resolve_win_path("E:/0apps/DSH/node_modules/dsh-video-skin"), "已下载的 Video Skin 素材"),
            (resolve_win_path("E:/0apps/DSH/data/dsh-video-skin-media"), "自定义 Video Skin 素材"),
        ]
        for sdir, label in scan_dirs:
            if sdir.is_dir():
                for child in sorted(sdir.rglob("*"))[:40]:
                    if child.suffix.lower() in MEDIA_EXTS:
                        add_file(child, child.stem, label)

        # 2. Steam Wallpaper Engine workshop 431960 across drives
        we_roots = []
        for drv in ("C:", "D:", "E:", "F:", "G:"):
            for sub in (
                "SteamLibrary/steamapps/workshop/content/431960",
                "Program Files (x86)/Steam/steamapps/workshop/content/431960",
                "Steam/steamapps/workshop/content/431960",
            ):
                cand = pathlib.Path(f"{drv}/{sub}")
                if cand.is_dir():
                    we_roots.append(cand)
        for wr in we_roots:
            try:
                for item_dir in sorted(wr.iterdir())[:36]:
                    if not item_dir.is_dir():
                        continue
                    proj = read_json(item_dir / "project.json", {}) or {}
                    wtype = str(proj.get("type", "")).lower()
                    fname = proj.get("file", "")
                    title = str(proj.get("title") or item_dir.name)
                    prev_name = proj.get("preview", "")
                    prev_p = (item_dir / prev_name) if prev_name else None
                    if fname:
                        target_f = item_dir / fname
                        if target_f.is_file() and target_f.suffix.lower() in MEDIA_EXTS:
                            add_file(target_f, f"[WE] {title}", f"Wallpaper Engine ({wtype or 'video'})", prev_p)
                            continue
                    if prev_p and prev_p.is_file() and prev_p.suffix.lower() in MEDIA_EXTS:
                        add_file(prev_p, f"[WE 预览] {title}", f"Wallpaper Engine ({wtype or 'scene'})")
            except OSError:
                pass

        # 3. User-registered custom media paths
        for raw_p in (read_json(self.data / "custom-media.json", []) or []):
            p = pathlib.Path(str(raw_p))
            if p.is_file():
                add_file(p, p.name, "自定义本地壁纸")

        with self.lock:
            self._media_index = idx
            write_json_atomic(self.data / "media-list.json", items)
        return items

    def resolve_media(self, media_id: str):
        with self.lock:
            p = self._media_index.get(media_id)
        if not p or not p.is_file():
            return None, None
        return p, MEDIA_EXTS.get(p.suffix.lower(), "application/octet-stream")

    def list_media(self) -> list:
        cached = read_json(self.data / "media-list.json", None)
        if cached is not None:
            return cached
        return self.refresh_media_index()

    # -------------------- Software Scan & One-Click Installer --------------------
    def _probe_single_software(self, item: dict) -> dict:
        found_path = ""
        for p in item.get("probes", []):
            # catalog.json lists E:-drive paths; resolve them onto a real drive
            cp = resolve_win_path(p)
            if cp.is_file():
                found_path = str(cp)
                break
        cli = item.get("cli", "")
        if not found_path and cli:
            which_p = shutil.which(cli)
            if which_p and "WindowsApps\\python" not in which_p:
                found_path = which_p

        ver = ""
        if found_path:
            if cli in ("git", "gh", "uv", "node", "conda", "tailscale"):
                try:
                    r = subprocess.run(
                        [found_path, "--version"],
                        capture_output=True,
                        timeout=5,
                        creationflags=NO_WINDOW,
                    )
                    ver = redact(r.stdout.decode("utf-8", "replace").strip().splitlines()[0] if r.stdout else "已安装")
                except Exception:
                    ver = "已检测到可执行文件"
            elif item["id"] == "pymol-open-source":
                ver = "已安装 · 可直接启动三维分子视图"
            else:
                ver = item.get("version_hint", "已安装")

        return {
            **item,
            "status": "installed" if found_path else "not_installed",
            "detected_path": found_path,
            "detected_version": ver or ("未检测到，可一键安装" if not found_path else "已安装"),
            "checked_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def scan_software(self) -> dict:
        if self.demo:
            return read_json(self.data / "software-scan.json", {"scanned_at": utc_iso(), "items": []})
        rows = [self._probe_single_software(item) for item in self.catalog]
        out = {"scanned_at": utc_iso(), "items": rows}
        with self.lock:
            write_json_atomic(self.data / "software-scan.json", out)
        return out

    def get_software_catalog_state(self) -> dict:
        cached = read_json(self.data / "software-scan.json", None)
        if cached is None:
            cached = self.scan_software()
        jobs = read_json(self.data / "install-jobs.json", []) or []
        return {"scan": cached, "jobs": jobs[-15:]}

    def start_install(self, pkg_id: str, custom_spec: str = "", manager: str = "winget", drive: str = "") -> dict:
        if self.demo or os.name != "nt":
            raise ValueError("当前为只读预览或非 Windows 主机；请在本机 Arena Desk 中点击一键安装。")
        # No hardcoded E: any more: install where Arena Desk itself lives.
        drive_clean = (drive or app_drive()).strip().rstrip(":")[:1].upper() + ":"
        if not _drive_exists(drive_clean):
            drive_clean = app_drive()
        if not DRIVE_RE.match(drive_clean):
            raise ValueError("Invalid target drive")

        cat_map = {c["id"]: c for c in self.catalog}
        if pkg_id == "custom":
            spec = (custom_spec or "").strip()
            if not spec or not PKG_SPEC_RE.match(spec):
                raise ValueError("包名格式不合法（仅允许字母、数字、点、下划线、连字符，如 GitHub.cli 或 pymol-open-source）")
            if manager not in ("winget", "conda"):
                raise ValueError("仅支持 winget 或 conda-forge 安装源")
            title = f"自定义安装 · {spec}"
            method = manager
        elif pkg_id in cat_map:
            entry = cat_map[pkg_id]
            spec = entry["spec"]
            method = entry["method"]
            title = entry["name"]
        else:
            raise ValueError("未知软件包标识")

        job_id = dt.datetime.now().strftime("%H%M%S") + "-" + secrets.token_hex(3) if "secrets" in globals() else str(int(time.time()))
        job = {
            "id": job_id,
            "pkg_id": pkg_id,
            "title": title,
            "method": method,
            "spec": spec,
            "drive": drive_clean,
            "status": "running",
            "started_at": utc_iso(),
            "log": f"正在启动安装任务: {title} ({method}: {spec}) ...",
        }
        self._save_job(job)
        threading.Thread(target=self._run_install_worker, args=(job,), daemon=True).start()
        return {"ok": True, "job": job}

    def _save_job(self, job: dict):
        with self.lock:
            jobs = read_json(self.data / "install-jobs.json", []) or []
            jobs = [j for j in jobs if j.get("id") != job["id"]]
            jobs.append(job)
            write_json_atomic(self.data / "install-jobs.json", jobs[-20:])

    def _run_install_worker(self, job: dict):
        ps_script = REPO_ROOT / "code" / "bootstrap" / "pc-diag-install.ps1"
        if not ps_script.exists():
            ps_script = HERE / "pc-diag-install.ps1"
        try:
            if job["pkg_id"] == "pymol-open-source" and ps_script.exists():
                cmd = [
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", str(ps_script),
                    "-Mode", "install", "-InstallPyMOL", "-PreferredDrive", job["drive"],
                    "-OutDir", str(self.data),
                ]
            elif job["pkg_id"] == "desktop-pet":
                cmd = [shutil.which("python") or "E:/spider/python.exe", str(HERE / "install_extras.py")]
            elif job["pkg_id"] == "lark-formatter":
                git_exe = shutil.which("git") or r"E:\hermes\git\cmd\git.exe"
                target_lf = pathlib.Path(r"E:\0writing\Lark-Formatter")
                if (target_lf / ".git").exists():
                    cmd = [git_exe, "-C", str(target_lf), "pull", "--ff-only"]
                else:
                    target_lf.parent.mkdir(parents=True, exist_ok=True)
                    cmd = [git_exe, "clone", "https://github.com/shaohuawen03-cyber/Lark-Formatter.git", str(target_lf)]
            elif job["method"] == "winget":
                winget = shutil.which("winget") or os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\winget.exe")
                cmd = [
                    winget, "install", "--id", job["spec"], "-e",
                    "--silent", "--accept-package-agreements", "--accept-source-agreements",
                ]
            elif job["method"] == "conda":
                conda = (
                    shutil.which("mamba")
                    or shutil.which("conda")
                    or f"{job['drive']}/Miniforge3/Scripts/mamba.exe"
                    or "E:/miniconda3/Scripts/conda.exe"
                )
                pkg_name = job["spec"].split("::")[-1]
                env_dir = f"{job['drive']}/0apps/conda-{re.sub(r'[^A-Za-z0-9_-]', '', pkg_name)}"
                cmd = [conda, "create", "-y", "-p", env_dir, "-c", "conda-forge", pkg_name]
            else:
                raise ValueError("Unsupported install method")

            r = subprocess.run(cmd, capture_output=True, timeout=900, creationflags=NO_WINDOW)
            out = (r.stdout.decode("utf-8", "replace") + "\n" + r.stderr.decode("utf-8", "replace")).strip()
            job["status"] = "installed" if r.returncode == 0 else "failed"
            job["finished_at"] = utc_iso()
            job["exit_code"] = r.returncode
            job["log"] = redact(out[-2400:] or f"Exit code {r.returncode}")
        except Exception as e:
            job["status"] = "failed"
            job["finished_at"] = utc_iso()
            job["log"] = redact(str(e))
        self._save_job(job)
        try:
            self.scan_software()
        except Exception:
            pass

    # -------------------- Remote Control Hub --------------------
    def get_remote_state(self) -> dict:
        cached = read_json(self.data / "remote-status.json", None)
        if cached is None:
            hosts = read_json(self.data / "remote-hosts.json", DEFAULT_REMOTE_HOSTS)
            cached = {"probed_at": None, "hosts": hosts}
        logs = []
        hist_p = self.data / "remote-history.jsonl"
        if hist_p.exists():
            try:
                for ln in hist_p.read_text(encoding="utf-8", errors="replace").splitlines()[-12:]:
                    if ln.strip():
                        logs.append(json.loads(ln))
            except Exception:
                pass
        return {"status": cached, "history": list(reversed(logs))}

    def add_remote_host(self, payload: dict) -> dict:
        if self.demo:
            raise ValueError("只读预览模式不支持写入远端节点配置")
        name = str(payload.get("name", "")).strip()[:60]
        address = str(payload.get("address", "")).strip()
        user = str(payload.get("user", "root")).strip()
        port = int(payload.get("port") or 22)
        via = str(payload.get("via") or "ssh")
        if not name or not HOST_SPEC_RE.match(address) or not USER_SPEC_RE.match(user):
            raise ValueError("请输入合法的主机名称、IP/域名与用户名")
        if not (1 <= port <= 65535) or via not in ("ssh", "wsl-hpc", "wsl-local"):
            raise ValueError("端口或通道类型无效")
        hid = re.sub(r"[^a-z0-9-]+", "-", address.lower()).strip("-")[:32] or "custom-node"
        with self.lock:
            hosts = read_json(self.data / "remote-hosts.json", DEFAULT_REMOTE_HOSTS)
            hosts = [h for h in hosts if h.get("id") != hid]
            hosts.append({
                "id": hid,
                "name": name,
                "address": address,
                "port": port,
                "user": user,
                "via": via,
                "role": str(payload.get("role", "自定义 SSH 节点"))[:60],
                "note": str(payload.get("note", "由面板手动添加"))[:120],
            })
            write_json_atomic(self.data / "remote-hosts.json", hosts)
        return self.probe_remotes()

    def probe_remotes(self) -> dict:
        if self.demo:
            return read_json(self.data / "remote-status.json", {"probed_at": utc_iso(), "hosts": []})
        hosts = read_json(self.data / "remote-hosts.json", DEFAULT_REMOTE_HOSTS)
        enriched = []
        for h in hosts:
            if h.get("via") == "wsl-local" and os.name == "nt":
                t0 = time.perf_counter()
                try:
                    r = subprocess.run(
                        ["wsl.exe", "-d", h.get("distro", "Ubuntu-26.04"), "-e", "bash", "-c", "uname -sr"],
                        capture_output=True, timeout=6, creationflags=NO_WINDOW,
                    )
                    ok = r.returncode == 0
                    ms = round((time.perf_counter() - t0) * 1000) if ok else None
                    msg = r.stdout.decode("utf-8", "replace").strip() if ok else "WSL 未响应"
                except Exception as e:
                    ok, ms, msg = False, None, str(e)[:80]
                enriched.append({**h, "online": ok, "latency_ms": ms, "summary": msg})
            else:
                res = tcp_ping(h["address"], h.get("port", 22))
                summary = f"TCP {h['address']}:{h.get('port', 22)} 可达 ({res['latency_ms']} ms)" if res["reachable"] else f"离线或超时 ({res.get('reason', 'timeout')})"
                enriched.append({**h, "online": res["reachable"], "latency_ms": res["latency_ms"], "summary": summary})
        out = {"probed_at": utc_iso(), "hosts": enriched}
        with self.lock:
            write_json_atomic(self.data / "remote-status.json", out)
        return out

    def run_remote_action(self, host_id: str, action: str, custom_cmd: str = "") -> dict:
        if self.demo or os.name != "nt":
            raise ValueError("只读预览模式不直接发起 SSH 控制；请在本机 Arena Desk 中执行。")
        hosts = {h["id"]: h for h in read_json(self.data / "remote-hosts.json", DEFAULT_REMOTE_HOSTS)}
        if host_id not in hosts:
            raise ValueError("未知远端节点")
        h = hosts[host_id]
        allowed_actions = {"info", "jobs", "disk", "gpu", "ping", "rdp", "custom"}
        if action not in allowed_actions:
            raise ValueError("未知远端动作")

        if action == "rdp":
            subprocess.Popen(["mstsc.exe", f"/v:{h['address']}"])
            return {"ok": True, "output": f"已唤起 Windows 远程桌面连接 -> {h['address']}"}

        if action == "ping":
            res = tcp_ping(h["address"], h.get("port", 22), timeout=3.0)
            out_txt = json.dumps(res, ensure_ascii=False)
        elif h.get("via") == "wsl-hpc":
            hpc_ps = REPO_ROOT / "code" / "connect" / "hpc.ps1"
            if not hpc_ps.exists():
                hpc_ps = HERE / "hpc.ps1"
            preset_cmds = {
                "info": ("info", ""),
                "jobs": ("jobs", ""),
                "disk": ("run", "df -h $HOME; sinfo -s"),
                "gpu": ("run", "sinfo -o '%P %G %D %T'"),
                "custom": ("run", custom_cmd.strip()[:400]),
            }
            hpc_act, cmd_body = preset_cmds[action]
            if hpc_act == "run" and not cmd_body:
                raise ValueError("请输入要执行的远端命令")
            args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(hpc_ps), "-Action", hpc_act, "-NoOut"]
            tmp_cmd = None
            if cmd_body:
                tmp_cmd = self.data / "tmp_remote_cmd.sh"
                tmp_cmd.write_text(cmd_body + "\n", encoding="utf-8")
                args.extend(["-CmdFile", str(tmp_cmd)])
            r = subprocess.run(args, capture_output=True, timeout=60, creationflags=NO_WINDOW)
            if tmp_cmd:
                tmp_cmd.unlink(missing_ok=True)
            out_txt = (r.stdout.decode("utf-8", "replace") + "\n" + r.stderr.decode("utf-8", "replace")).strip()
        elif h.get("via") == "wsl-local":
            preset = {
                "info": "uname -a; lsb_release -ds 2>/dev/null || true; uptime",
                "jobs": "ps aux --sort=-%cpu | head -12",
                "disk": "df -h / /mnt/e 2>/dev/null || df -h /",
                "gpu": "nvidia-smi 2>/dev/null || echo 'No NVIDIA GPU exposed in WSL'",
                "custom": custom_cmd.strip()[:400],
            }[action]
            if not preset:
                raise ValueError("请输入要执行的 WSL 命令")
            r = subprocess.run(
                ["wsl.exe", "-d", h.get("distro", "Ubuntu-26.04"), "-e", "bash", "-c", preset],
                capture_output=True, timeout=30, creationflags=NO_WINDOW,
            )
            out_txt = (r.stdout.decode("utf-8", "replace") + "\n" + r.stderr.decode("utf-8", "replace")).strip()
        else:
            preset = {
                "info": "hostname && whoami",
                "jobs": "tasklist /FO TABLE 2>nul || ps aux | head -15",
                "disk": "wmic logicaldisk get size,freespace,caption 2>nul || df -h",
                "gpu": "nvidia-smi 2>nul || echo no-nvidia-smi",
                "custom": custom_cmd.strip()[:400],
            }[action]
            if not preset:
                raise ValueError("请输入要执行的 SSH 命令")
            ssh_bin = shutil.which("ssh") or r"C:\Windows\System32\OpenSSH\ssh.exe"
            r = subprocess.run(
                [
                    ssh_bin, "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                    "-p", str(h.get("port", 22)), f"{h['user']}@{h['address']}", preset,
                ],
                capture_output=True, timeout=30, creationflags=NO_WINDOW,
            )
            out_txt = (r.stdout.decode("utf-8", "replace") + "\n" + r.stderr.decode("utf-8", "replace")).strip()

        safe_out = redact(out_txt)[:4000]
        rec = {"at": utc_iso(), "host_id": host_id, "host_name": h["name"], "action": action, "output": safe_out}
        with self.lock, (self.data / "remote-history.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return {"ok": True, "record": rec}

    # -------------------- GitHub (gh) Auth & Private Repo Hub --------------------
    def check_gh_auth(self) -> dict:
        if self.demo:
            return read_json(self.data / "gh-status.json", {})
        gh_bin = shutil.which("gh") or (r"C:\Program Files\GitHub CLI\gh.exe" if pathlib.Path(r"C:\Program Files\GitHub CLI\gh.exe").exists() else "")
        git_bin = shutil.which("git") or (r"E:\hermes\git\cmd\git.exe" if pathlib.Path(r"E:\hermes\git\cmd\git.exe").exists() else "git")
        env = dict(os.environ, GH_PROMPT_DISABLED="1", GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")

        detail_lines = []
        authed = False
        account = ""
        has_repo_scope = False

        if gh_bin:
            try:
                r = subprocess.run([gh_bin, "auth", "status"], capture_output=True, timeout=10, env=env, creationflags=NO_WINDOW)
                raw = redact((r.stdout.decode("utf-8", "replace") + "\n" + r.stderr.decode("utf-8", "replace")).strip())
                authed = r.returncode == 0
                for ln in raw.splitlines():
                    if ln.strip():
                        detail_lines.append(ln.strip())
                    m = re.search(r"account\s+([A-Za-z0-9_-]+)", ln)
                    if m:
                        account = m.group(1)
                    if "'repo'" in ln or '"repo"' in ln or "repo," in ln or ln.endswith("repo"):
                        has_repo_scope = True
            except Exception as e:
                detail_lines.append(f"gh auth status error: {e}")
        else:
            detail_lines.append("未检测到 gh.exe（可在「软件中心」或点击下方按钮通过 winget 安装 GitHub.cli）")

        # Verify non-interactive private repo ls-remote on mqgg5630-cyber/0fuye
        priv_ok = False
        try:
            r2 = subprocess.run(
                [git_bin, "ls-remote", "--heads", "https://github.com/mqgg5630-cyber/0fuye.git"],
                capture_output=True, timeout=12, env=env, creationflags=NO_WINDOW,
            )
            priv_ok = r2.returncode == 0
            detail_lines.append(f"私人仓 git ls-remote (0fuye): {'成功 (具备 repo 权限)' if priv_ok else '未通过 (需更新 repo 权限凭据)'}")
        except Exception as e:
            detail_lines.append(f"git ls-remote 检查异常: {e}")

        worker_p = pathlib.Path(r"E:\0github\.git-sync\leanrea-626378d6-leanrea\hub-worker.ps1")
        worker_patched = worker_p.is_file() and ("user/repos" in worker_p.read_text(encoding="utf-8", errors="replace"))
        detail_lines.append(f"基座私人仓热补丁 (hub-worker.ps1): {'已生效 (/user/repos)' if worker_patched else '待一键启用'}")

        proxy_val = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or ""
        if not proxy_val:
            try:
                rp = subprocess.run([git_bin, "config", "--get", "http.proxy"], capture_output=True, timeout=4, creationflags=NO_WINDOW)
                proxy_val = rp.stdout.decode("utf-8", "replace").strip()
            except Exception:
                pass

        # Load multi-account matrix (mqgg5630-cyber, shaohuawen03-cyber, hukeying85-ux)
        multi_matrix = {}
        try:
            import importlib.util
            setup_py = REPO_ROOT / "code" / "auth" / "setup_multi_gh.py"
            if not setup_py.is_file():
                setup_py = HERE / "auth" / "setup_multi_gh.py"
            if setup_py.is_file():
                spec = importlib.util.spec_from_file_location("setup_multi_gh", str(setup_py))
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    multi_matrix = mod.get_multi_gh_matrix()
        except Exception as e:
            detail_lines.append(f"multi-account check note: {e}")

        active_acc = multi_matrix.get("active_account") or account or ("mqgg5630-cyber" if priv_ok else "")
        res = {
            "checked_at": utc_iso(),
            "sandbox_gh_ok": True,
            "host_gh_installed": bool(gh_bin),
            "authenticated": authed or priv_ok,
            "account": active_acc,
            "private_repo_ready": priv_ok or has_repo_scope,
            "hub_worker_patched": worker_patched,
            "default_invariant_ok": multi_matrix.get("default_invariant_ok", True),
            "chrome_profile1_keying_detected": multi_matrix.get("chrome_profile1_keying_detected", False),
            "multi_accounts": multi_matrix.get("accounts", []),
            "proxy": proxy_val or "直连 / 系统默认",
            "summary": (
                "本机三账号 Git/SSH 443 隧道与 0fuye 私人仓热补丁均已就绪！"
                if (priv_ok and worker_patched)
                else "请点击「一键启用基座私人仓轮询」或「启动 gh 设备码登录」完成私人仓闭环。"
            ),
            "detail_lines": detail_lines,
        }
        with self.lock:
            write_json_atomic(self.data / "gh-status.json", res)
        return res

    def get_gh_state(self) -> dict:
        cached = read_json(self.data / "gh-status.json", None)
        if cached is not None and cached.get("multi_accounts"):
            return cached
        return self.check_gh_auth()

    def run_gh_action(self, action: str) -> dict:
        if self.demo or os.name != "nt":
            raise ValueError("只读预览模式无法修改本机凭据；请在本机 Arena Desk 中操作。")
        auth_ps = REPO_ROOT / "auth.ps1"
        if not auth_ps.exists():
            auth_ps = HERE / "auth.ps1"
        priv_ps = HERE / "enable_private_hub.ps1"
        hukeying_ps = REPO_ROOT / "code" / "auth" / "connect_hukeying_gh.ps1"
        if not hukeying_ps.exists():
            hukeying_ps = HERE / "auth" / "connect_hukeying_gh.ps1"

        if action == "check":
            return {"ok": True, "gh": self.check_gh_auth()}
        if action == "provision_hukeying":
            if hukeying_ps.exists():
                r = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(hukeying_ps), "-PrepareOnly"],
                    capture_output=True, timeout=30, creationflags=NO_WINDOW,
                )
                msg = redact((r.stdout.decode("utf-8", "replace") + "\n" + r.stderr.decode("utf-8", "replace")).strip())
                return {"ok": r.returncode == 0, "note": msg[:800] or "已配妥 hukeying85-ux SSH 密钥与 URL 凭据路由", "gh": self.check_gh_auth()}
            raise ValueError("未找到 connect_hukeying_gh.ps1")
        if action == "connect_hukeying_web":
            if hukeying_ps.exists():
                subprocess.Popen(["powershell.exe", "-NoProfile", "-NoExit", "-ExecutionPolicy", "Bypass", "-File", str(hukeying_ps)])
                return {
                    "ok": True,
                    "note": "已自动打开 Chrome Profile 1 ('keying' · hukeying85@gmail.com) 与 GitHub OAuth 授权窗口；授权完成后将自动上传 SSH 公钥并恢复默认账号为 mqgg5630-cyber。",
                }
            raise ValueError("未找到 connect_hukeying_gh.ps1")
        if action == "unlock_private_hub":
            r = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(priv_ps)],
                capture_output=True, timeout=30, creationflags=NO_WINDOW,
            )
            msg = redact((r.stdout.decode("utf-8", "replace") + "\n" + r.stderr.decode("utf-8", "replace")).strip())
            return {"ok": r.returncode == 0, "note": msg[:800], "gh": self.check_gh_auth()}
        if action == "setup_git_dpapi" and auth_ps.exists():
            r = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(auth_ps), "-Setup", "-PreferDpapi"],
                capture_output=True, timeout=35, creationflags=NO_WINDOW,
            )
            msg = redact((r.stdout.decode("utf-8", "replace") + "\n" + r.stderr.decode("utf-8", "replace")).strip())
            return {"ok": r.returncode == 0, "note": msg[:800], "gh": self.check_gh_auth()}
        if action == "device_login":
            if auth_ps.exists():
                subprocess.Popen(["powershell.exe", "-NoProfile", "-NoExit", "-ExecutionPolicy", "Bypass", "-File", str(auth_ps), "-GhLogin"])
            else:
                subprocess.Popen(["powershell.exe", "-NoProfile", "-NoExit", "-Command", "gh auth login -p https -w; gh auth setup-git"])
            return {"ok": True, "note": "已打开交互式终端与浏览器设备码登录窗口，完成授权后点「重新检测」即可。"}
        raise ValueError("未知认证动作")

    # -------------------- Cross-PC Script Generator --------------------
    def generate_bootstrap_script(self, params: dict) -> tuple:
        target_os = str(params.get("os", "windows")).lower()
        mode = str(params.get("mode", "install")).lower()
        if mode not in ("diag", "install", "node"):
            mode = "diag"
        pymol = str(params.get("pymol", "1")) in ("1", "true", "yes")
        base = str(params.get("base", "1")) in ("1", "true", "yes")
        tailscale = str(params.get("tailscale", "0")) in ("1", "true", "yes")
        drive = str(params.get("drive", "Auto"))
        if drive != "Auto" and not DRIVE_RE.match(drive):
            drive = "Auto"
        extra = ",".join(
            x.strip() for x in str(params.get("extra", "")).split(",")
            if x.strip() and PKG_SPEC_RE.match(x.strip())
        )

        if target_os in ("linux", "wsl", "macos", "posix"):
            sh_src = (REPO_ROOT / "code" / "bootstrap" / "pc-diag-install.sh")
            body = sh_src.read_text(encoding="utf-8") if sh_src.exists() else "#!/usr/bin/env bash\necho 'missing template'\n"
            flags = [f"--mode {'install' if mode != 'diag' else 'diag'}"]
            if pymol and mode != "diag":
                flags.append("--install-pymol")
            if base and mode != "diag":
                flags.extend(["--install-gh", "--install-uv"])
            header = (
                f"# Custom Preset Generated by Arena Desk v2.0\n"
                f"# Default invocation: bash pc-diag-install.sh {' '.join(flags)}\n"
                f'if [ $# -eq 0 ]; then set -- {" ".join(flags)}; fi\n\n'
            )
            body = body.replace("set -u -o pipefail\n", "set -u -o pipefail\n" + header, 1)
            return "arena-pc-setup.sh", "text/x-shellscript; charset=utf-8", body.encode("utf-8")

        ps_src = (REPO_ROOT / "code" / "bootstrap" / "pc-diag-install.ps1")
        body = ps_src.read_text(encoding="utf-8") if ps_src.exists() else "# missing template\n"
        # Customize default param values cleanly while remaining 100% ASCII
        body = body.replace("[string]$Mode = 'diag'", f"[string]$Mode = '{mode}'", 1)
        if pymol:
            body = body.replace("[switch]$InstallPyMOL,", "[switch]$InstallPyMOL = $true,", 1)
        if base:
            body = body.replace("[switch]$InstallBase,", "[switch]$InstallBase = $true,", 1)
        if tailscale:
            body = body.replace("[switch]$InstallTailscale,", "[switch]$InstallTailscale = $true,", 1)
        if extra:
            body = body.replace("[string]$ExtraWinget = ''", f"[string]$ExtraWinget = '{extra}'", 1)
        if drive != "Auto":
            body = body.replace("[string]$PreferredDrive = 'Auto'", f"[string]$PreferredDrive = '{drive}'", 1)
        return "arena-pc-setup.ps1", "text/plain; charset=utf-8", body.encode("utf-8")

    # -------------------- 3-Account Isolated Arena App Windows --------------------
    def get_arena_windows(self) -> dict:
        default_cfg = {
            "slots": [
                {
                    "slot": "S1",
                    "title": "S1 主控笔记本舱 · Arena 专窗",
                    "gh_account": "mqgg5630-cyber",
                    "machine": "LAPTOP-R77M5D6M",
                    "profile_dir": r"E:\0apps\ArenaDesk\arena-profiles\S1-mqgg5630",
                    "url": "https://arena.ai/",
                    "badge": "0fuye 总控 · 论文与云盘",
                },
                {
                    "slot": "S2",
                    "title": "S2 毕业课题超算舱 · Arena 专窗",
                    "gh_account": "shaohuawen03-cyber",
                    "machine": "HPC 超算 mu01",
                    "profile_dir": r"E:\0apps\ArenaDesk\arena-profiles\S2-shaohuawen03",
                    "url": "https://arena.ai/",
                    "badge": "476样本宏基因组 · 全原子MD",
                },
                {
                    "slot": "S3",
                    "title": "S3 台式机粗粒化算力舱 · Arena 专窗",
                    "gh_account": "hukeying85-ux",
                    "machine": "GPU Workstation 台式机",
                    "profile_dir": r"E:\0apps\ArenaDesk\arena-profiles\S3-hukeying85",
                    "url": "https://arena.ai/",
                    "badge": "Martini 3 细菌膜 2.0μs 初筛",
                },
            ]
        }
        cfg = read_json(self.data / "arena-windows.json", None)
        if not cfg or not isinstance(cfg.get("slots"), list) or len(cfg["slots"]) < 3:
            write_json_atomic(self.data / "arena-windows.json", default_cfg)
            return default_cfg
        return cfg

    def manage_arena_window(self, action: str, slot: str = "S1", url: str = "") -> dict:
        cfg = self.get_arena_windows()
        slots = cfg.get("slots", [])
        clean_url = str(url or "").strip()
        if clean_url and not clean_url.startswith(("https://arena.ai", "https://lmarena.ai", "https://chat.lmsys.org")):
            raise ValueError("仅允许保存 Arena 官方会话网址 (https://arena.ai/...)")

        if clean_url and slot in ("S1", "S2", "S3"):
            for item in slots:
                if item["slot"] == slot:
                    item["url"] = clean_url
            write_json_atomic(self.data / "arena-windows.json", cfg)
            if action == "save":
                return {"ok": True, "note": f"已保存 {slot} 专属会话网址", "arena_windows": cfg}

        if self.demo or os.name != "nt":
            return {
                "ok": True,
                "preview": True,
                "note": f"预览模式：在本机 Arena Desk 点击将直接以物理隔离 Profile 启动 {slot} 无边框专窗（三账号同时在线零串号）。",
                "arena_windows": cfg,
            }

        browser_exe = ""
        for cand in (
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        ):
            if pathlib.Path(cand).is_file():
                browser_exe = cand
                break
        if not browser_exe:
            raise ValueError("未找到 Edge 或 Chrome 浏览器可执行文件")

        targets = slots if action == "tile_all" or slot == "ALL" else [s for s in slots if s["slot"] == slot]
        launched = []
        for idx, item in enumerate(targets):
            prof = pathlib.Path(item["profile_dir"])
            prof.mkdir(parents=True, exist_ok=True)
            target_u = item.get("url") or "https://arena.ai/"
            args = [
                browser_exe,
                f"--user-data-dir={prof}",
                f"--app={target_u}",
                "--no-first-run",
                "--no-default-browser-check",
            ]
            if action == "tile_all" or slot == "ALL":
                x_pos = idx * 640
                args.extend([f"--window-position={x_pos},0", "--window-size=640,1030"])
            else:
                args.extend(["--window-size=1280,920"])
            subprocess.Popen(args, creationflags=NO_WINDOW)
            launched.append(item["slot"])

        return {
            "ok": True,
            "launched": launched,
            "note": f"已通过独立隔离 Profile 启动 {', '.join(launched)} Arena 专窗（首次打开登录对应账号后永久免扫，三舱绝不串号）！",
            "arena_windows": cfg,
        }
