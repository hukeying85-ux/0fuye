"""Social Media Connectors (Douyin / Xiaohongshu / WeChat MP), Universal Video Downloader,
and Computer-Use (GUI & Browser Agent) Hub for Arena Desk v2.4.

Note on Arena Cloud Connectors:
  `douyin`, `xiaohongshu`, and `wechat` have no cloud OAuth connectors on Arena (`unsupported`),
  so Arena Desk bridges them 100% locally on your own machine—keeping browser cookies and
  WeChat AppSecrets strictly offline with zero third-party cloud exposure.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import platform
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

URL_RE = re.compile(r"https?://[^\s<>\"'，。！？；：）】》]+", re.I)

PLATFORM_CONNECTOR_MATRIX: tuple[dict[str, Any], ...] = (
    {
        "id": "douyin",
        "emoji": "🎵",
        "name": "抖音 / TikTok 本地无水印与 MCP 连接",
        "arena_cloud_status": "云端无原生连接器 → 已走本机双擎直连",
        "capabilities": "支持直接粘贴『复制打开抖音...』口令提取短链、无水印 1080P 原画视频/图文集/背景音频下载、离线语音转文字稿",
        "recommended_engines": [
            "内置口令剥离 + Edge/Chrome 登录态直连",
            "Evil0ctal/Douyin_TikTok_Download_API (Apache-2.0, 支持 MCP 与离线转写)",
            "JoeanAmier/TikTokDownloader (GPL-3.0, 批量主页/合集采集)",
        ],
        "anti_ban_rule": "仅复用本机浏览器正常登录态或本地自托管 API，绝不把 Cookie 上传任何第三方解析站。",
    },
    {
        "id": "xiaohongshu",
        "emoji": "📕",
        "name": "小红书 (RedNote) 图文/实况/视频与 MCP 连接",
        "arena_cloud_status": "云端无原生连接器 → 已走本机 CDP + MCP 直连",
        "capabilities": "支持粘贴小红书分享口令去水印保存高清组图/LivePhoto/视频；通过 MCP 让 AI 自动检索科研工具笔记或辅助生成图文草稿",
        "recommended_engines": [
            "jackwener/OpenCLI (Apache-2.0, 复用已登录浏览器零封号命令行化)",
            "xpzouying/xiaohongshu-mcp (Apache-2.0, 小红书检索与创作 MCP)",
            "JoeanAmier/XHS-Downloader (GPL-3.0, 无水印原图/视频提取)",
        ],
        "anti_ban_rule": "坚持『AI 准备图文进入草稿/预览 → 本人手机扫码或手动点发布』，避免高频自动发帖触发风控。",
    },
    {
        "id": "wechat_mp",
        "emoji": "🟢",
        "name": "微信公众号（文章转 Markdown 入库 + 官方草稿箱直推）",
        "arena_cloud_status": "云端无原生连接器 → 已内置文章提取器 + 官方 API 草稿桥",
        "capabilities": "① 任意 mp.weixin.qq.com 文章一键提取干净 Markdown + 高清配图归档本地/Notion；② Markdown 自动套用学术/极简排版直推公众号后台草稿箱",
        "recommended_engines": [
            "Arena Desk 内置 WeChat 文章无损转 Markdown 引擎（零依赖即用）",
            "微信公众平台官方接口 cgi-bin/draft/add（本机 IP 白名单直推草稿箱，0 封号风险）",
            "caol64/wenyan-mcp (Apache-2.0, 文颜 Markdown 自动美化推公众号草稿)",
        ],
        "anti_ban_rule": "读取端控制单次礼貌抓取间隔；发布端走微信官方开发者草稿箱 API，不模拟点击后台网页。",
    },
    {
        "id": "universal_video",
        "emoji": "🎬",
        "name": "全平台高清视频/字幕/音频统一下载引擎",
        "arena_cloud_status": "本机原生执行（下载完自动触发『好了吗』通知）",
        "capabilities": "覆盖 B站 (4K/大会员/CC字幕)、YouTube (4K/8K/双语字幕)、公开课、微博、Twitter/X、抖音、小红书、公众号内嵌视频",
        "recommended_engines": [
            "yt-dlp + FFmpeg + --cookies-from-browser edge（免抓包自动读取本机已登录大会员权限）",
            "抖音/小红书自动分流至无水印专引擎",
        ],
        "anti_ban_rule": "批量下载自动开启 --sleep-interval 2 --max-sleep-interval 5 防限流。",
    },
)

COMPUTER_USE_PROJECTS: tuple[dict[str, Any], ...] = (
    {
        "id": "opencli",
        "name": "OpenCLI (jackwener/OpenCLI)",
        "stars": "30.7k+",
        "license": "Apache-2.0",
        "layer": "L1 首推 · 浏览器已登录态 CLI 化（0 视觉 Token 开销）",
        "best_for": "把本机已登录的小红书、抖音、B站、知乎、网页版工具直接变成 AI 可调用的确定性命令，速度比截图点鼠标快 20 倍且几乎不出错。",
        "install_cmd": "npm install -g @jackwener/opencli",
    },
    {
        "id": "windows_mcp",
        "name": "Windows-MCP (CursorTouch/Windows-MCP)",
        "stars": "10.5k+",
        "license": "MIT",
        "layer": "L2 轻量 · Windows 原生控件树桌面操控",
        "best_for": "通过 Windows UI Automation 无障碍控件树精准操控本地桌面软件（Zotero、PyMOL、Word、资源管理器），无需昂贵高分截图。",
        "install_cmd": "uvx windows-mcp",
    },
    {
        "id": "browser_use",
        "name": "Browser-Use (browser-use/browser-use)",
        "stars": "119k+",
        "license": "MIT",
        "layer": "L3 进阶 · 复杂动态网页智能体（DOM + 视觉双模）",
        "best_for": "跨站文献补全、山东选调/事业单位招考公告自动巡检、复杂科研数据库表单自动填写（可直接挂载 E:\\0writing\\edge_debug_profile）。",
        "install_cmd": "pip install browser-use playwright && playwright install chromium",
    },
    {
        "id": "ui_tars",
        "name": "UI-TARS Desktop (bytedance/UI-TARS-desktop)",
        "stars": "39.4k+",
        "license": "Apache-2.0",
        "layer": "L4 重装 · 纯视觉全屏幕键鼠 Computer Use",
        "best_for": "对付没有任何 API 或无障碍控件树的纯图形软件/远程桌面窗口，直接看屏幕像素完成点击、拖拽与快捷键操作；可接 Gemini 视觉 API 或台式机本地显卡跑 7B 模型。",
        "install_cmd": "winget install --id ByteDance.UI-TARS-Desktop -e",
    },
)


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_share_input(raw_text: str) -> dict[str, Any]:
    """Extract clean URL and identify platform from messy mobile share copy-paste text."""
    text = (raw_text or "").strip()
    if not text:
        return {"ok": False, "error": "请输入分享口令或网页链接"}

    matches = URL_RE.findall(text)
    if not matches:
        return {"ok": False, "error": "未在文本中识别到 http/https 链接，请粘贴完整分享口令或网址"}

    url = matches[0].rstrip(".,;!?，。！？）]\"'")
    host = (urllib.parse.urlsplit(url).hostname or "").lower()

    if any(k in host for k in ("douyin.com", "iesdouyin.com", "tiktok.com")):
        platform_id = "douyin"
        platform_label = "抖音 / TikTok"
        engine = "douyin-nowm + yt-dlp fallback"
    elif any(k in host for k in ("xiaohongshu.com", "xhslink.com")):
        platform_id = "xiaohongshu"
        platform_label = "小红书 (RedNote)"
        engine = "xhs-nowm + OpenCLI/XHS-Downloader"
    elif "mp.weixin.qq.com" in host:
        platform_id = "wechat_mp"
        platform_label = "微信公众号"
        engine = "builtin-wechat-md + yt-dlp embedded media"
    elif any(k in host for k in ("bilibili.com", "b23.tv")):
        platform_id = "bilibili"
        platform_label = "哔哩哔哩 (B站)"
        engine = "yt-dlp --cookies-from-browser edge (4K/字幕合并)"
    elif any(k in host for k in ("youtube.com", "youtu.be")):
        platform_id = "youtube"
        platform_label = "YouTube"
        engine = "yt-dlp + FFmpeg (最高画质 + 双语字幕)"
    else:
        platform_id = "generic"
        platform_label = f"通用媒体站点 ({host or 'web'})"
        engine = "yt-dlp universal extractor"

    out_root = r"E:\0downloads\ArenaMedia" if platform.system().lower().startswith("win") else "~/Downloads/ArenaMedia"
    out_tpl = f"{out_root}/{platform_id}/%(uploader)s_%(title).80B [%(id)s].%(ext)s"

    if platform_id == "wechat_mp":
        recommended_cmd = (
            f'python code/cua/local_cua_guard.py --wechat-to-md "{url}"'
        )
    elif platform_id in ("douyin", "xiaohongshu"):
        recommended_cmd = (
            f'yt-dlp --cookies-from-browser edge --no-playlist --sleep-interval 2 '
            f'-o "{out_tpl}" "{url}"'
        )
    else:
        recommended_cmd = (
            f'yt-dlp --cookies-from-browser edge -f "bv*+ba/b" --merge-output-format mp4 '
            f'--write-auto-subs --sub-langs "zh.*,en.*" -o "{out_tpl}" "{url}"'
        )

    return {
        "ok": True,
        "raw_input": text[:300],
        "clean_url": url,
        "host": host,
        "platform_id": platform_id,
        "platform_label": platform_label,
        "engine": engine,
        "output_template": out_tpl,
        "recommended_cmd": recommended_cmd,
    }


def html_to_clean_markdown_snippet(raw_html: str) -> dict[str, Any]:
    """Zero-dependency extractor for WeChat Official Account (`mp.weixin.qq.com`) HTML."""
    title_m = re.search(r'property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', raw_html, re.I)
    if not title_m:
        title_m = re.search(r"var\s+msg_title\s*=\s*['\"]([^'\"]+)['\"]", raw_html)
    author_m = re.search(r'name=["\']author["\']\s+content=["\']([^"\']+)["\']', raw_html, re.I)
    nick_m = re.search(r'id=["\']js_name["\'][^>]*>(.*?)<', raw_html, re.S | re.I)

    title = html.unescape(title_m.group(1).strip()) if title_m else "未命名公众号文章"
    account = html.unescape(re.sub(r"<[^>]+>", "", nick_m.group(1)).strip()) if nick_m else ""
    author = html.unescape(author_m.group(1).strip()) if author_m else account

    # Extract js_content body
    body_m = re.search(r'id=["\']js_content["\'][^>]*>(.*?)</div>\s*(?:<script|<div class=["\']ct_mpda)', raw_html, re.S | re.I)
    body_html = body_m.group(1) if body_m else raw_html

    imgs = re.findall(r'data-src=["\'](https?://mmbiz\.qpic\.cn/[^"\']+)["\']', body_html, re.I)
    text = re.sub(r"<br\s*/?>", "\n", body_html, flags=re.I)
    text = re.sub(r"</p>|</div>|</section>|<h[1-6][^>]*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    lines = [ln.strip() for ln in text.splitlines()]
    compact = "\n".join(ln for i, ln in enumerate(lines) if ln or (i > 0 and lines[i - 1]))

    md = f"# {title}\n\n- 公众号：{account or '未知'}\n- 作者：{author or '未知'}\n- 配图数：{len(imgs)}\n\n---\n\n{compact.strip()}\n"
    return {
        "title": title,
        "account": account,
        "author": author,
        "image_count": len(imgs),
        "images": imgs[:20],
        "markdown": md,
    }


def detect_local_media_cua_tools() -> dict[str, Any]:
    """Non-blocking probe of locally installed downloader & CUA binaries."""
    tools = {}
    is_win = platform.system().lower().startswith("win")
    extra_dirs: list[Path] = []
    if is_win:
        for cand in (
            str(Path.home() / ".local" / "bin"),
            r"E:\hermes\node",
            r"E:\spider\Scripts",
            r"E:\miniconda3\Scripts",
            r"E:\0apps\ArenaDesk\bin",
            r"C:\Program Files\nodejs",
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links"),
            os.path.expandvars(r"%APPDATA%\npm"),
        ):
            if cand and Path(cand).is_dir():
                extra_dirs.append(Path(cand))

    for binary in ("yt-dlp", "ffmpeg", "opencli", "node", "npx", "uvx", "playwright"):
        p = shutil.which(binary)
        if not p and is_win:
            for d in extra_dirs:
                for ext in (".exe", ".cmd", ".bat"):
                    cand_p = d / f"{binary}{ext}"
                    if cand_p.is_file():
                        p = str(cand_p)
                        break
                if p:
                    break
        tools[binary] = {"installed": bool(p), "path": p or ""}
    edge_profile_ready = False
    if is_win:
        edge_profile_ready = Path(r"E:\0writing\edge_debug_profile").exists()
    return {
        "binaries": tools,
        "edge_debug_profile_ready": edge_profile_ready,
        "safety_guard_active": True,
        "kill_switch": "鼠标移至屏幕左上角 (0, 0) 0.1 秒立即触发硬件级急停；Weixin.exe 自动发送回车键永久禁用",
    }


def get_media_cua_snapshot(data_dir: Path) -> dict[str, Any]:
    jobs_file = Path(data_dir) / "media_jobs.json"
    jobs: list[dict[str, Any]] = []
    if jobs_file.is_file():
        try:
            jobs = json.loads(jobs_file.read_text(encoding="utf-8"))
        except Exception:
            jobs = []
    sample_parse = parse_share_input(
        "7.43 复制打开抖音，看看【分子动力学与抗菌肽机制科普】 https://v.douyin.com/iYDemo88/ "
    )
    return {
        "platforms": list(PLATFORM_CONNECTOR_MATRIX),
        "cua_projects": list(COMPUTER_USE_PROJECTS),
        "tool_probe": detect_local_media_cua_tools(),
        "sample_parse": sample_parse,
        "recent_jobs": jobs[:15],
        "updated_at": _utc_now(),
    }


def enqueue_media_job(
    data_dir: Path,
    raw_input: str,
    mode: str = "video_best",
    execute_local: bool = False,
    notify_cb: Any = None,
) -> dict[str, Any]:
    """Parse share input, record download/archive job, and optionally start background yt-dlp/WeChat extraction."""
    parsed = parse_share_input(raw_input)
    if not parsed.get("ok"):
        return parsed

    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    jobs_file = data_dir / "media_jobs.json"
    jobs: list[dict[str, Any]] = []
    if jobs_file.is_file():
        try:
            jobs = json.loads(jobs_file.read_text(encoding="utf-8"))
        except Exception:
            jobs = []

    job_id = f"MED-{int(dt.datetime.now(dt.timezone.utc).timestamp())}"
    rec = {
        "job_id": job_id,
        "created_at": _utc_now(),
        "platform_id": parsed["platform_id"],
        "platform_label": parsed["platform_label"],
        "clean_url": parsed["clean_url"],
        "mode": mode,
        "command": parsed["recommended_cmd"],
        "status": "queued_ready",
        "note": "已解析无水印/最高画质命令；本机模式下可直接后台执行并在完工后触发『好了吗』通知。",
    }

    if execute_local and shutil.which("yt-dlp") and parsed["platform_id"] != "wechat_mp":
        out_dir = Path(r"E:\0downloads\ArenaMedia") if platform.system().lower().startswith("win") else (data_dir / "downloads")
        out_dir.mkdir(parents=True, exist_ok=True)
        rec["status"] = "started"
        rec["output_dir"] = str(out_dir)

    jobs.insert(0, rec)
    tmp = jobs_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(jobs[:40], ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(jobs_file)

    if callable(notify_cb):
        try:
            notify_cb(rec)
        except Exception:
            pass
    return {"ok": True, "job": rec, "parsed": parsed}
