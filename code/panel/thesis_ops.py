#!/usr/bin/env python3
"""Headless One-Click Graduate Thesis Formatter Bridge for Arena Desk v2.1.

Integrates E:\\0writing\\Lark-Formatter (v0.21.1 pure-Python rules pipeline:
page_setup, style_manager, heading_detect, heading_numbering, toc_format,
caption_format, table_format [three-line table], section_format, header_footer,
md_cleanup, whitespace_normalize, citation_link, zotero_fields [GB/T 7714-2015],
chem_typography, compare.docx + audit report JSON/MD) AND E:\\0writing\\*
academic skill modules, bypassing Win11 build 26200 PySide6 DLL crashes.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
BUNDLED_SAMPLE_DOCX = HERE / "samples" / "master_sample_thesis.docx"

BUILT_IN_PROFILES: list[dict[str, Any]] = [
    {
        "id": "academic_master_2026",
        "name": "学术型硕士学位论文标准规范 (2026 定稿版)",
        "badge": "默认推荐 · 0710 硕士",
        "description": (
            "A4 页边距上下 3.8cm / 左右 3.2cm（或模板克隆覆盖）、章标题黑体三号居中、"
            "正文宋体/Times New Roman 小四 20pt 固定行距、三线表自动规整、奇偶页眉页脚、"
            "Zotero 9 活动引用域修复 + GB/T 7714-2015 顺序编码。"
        ),
        "options": {
            "enable_zotero": True,
            "enable_chem": True,
            "enable_whitespace": True,
            "enable_md_cleanup": True,
            "three_line_table": True,
        },
        "template_glob": "*标准定稿*.docx",
    },
    {
        "id": "zotero_active_gbt7714",
        "name": "Zotero 9 活动引用保护 + GB/T 7714-2015 专项修订",
        "badge": "Zotero 联动",
        "description": (
            "排版同时自动补全 Zotero 9 citationItem.uris 与文档首选项，"
            "确保排版后在 Word 点击 Zotero -> Refresh 不报错。"
        ),
        "options": {
            "enable_zotero": True,
            "enable_chem": False,
            "enable_whitespace": True,
            "enable_md_cleanup": False,
            "three_line_table": True,
        },
        "template_glob": "*Zotero*.docx",
    },
    {
        "id": "blind_review_clean",
        "name": "硕士学位论文外审盲审洁净版 (Markdown/混排清洗 + 化学式角标)",
        "badge": "盲审送检",
        "description": (
            "开启 Markdown 残留清洗、全半角中英文标点智能转换、"
            "化学式/分子式上下角标自动恢复（适配生物化学/抗菌肽/分子模拟论文）与三线表统一。"
        ),
        "options": {
            "enable_zotero": True,
            "enable_chem": True,
            "enable_whitespace": True,
            "enable_md_cleanup": True,
            "three_line_table": True,
        },
        "template_glob": "",
    },
]

WRITING_SKILLS_ECOSYSTEM: list[dict[str, str]] = [
    {
        "id": "lark-formatter",
        "name": "Lark-Formatter v0.21.1 (无头排版核心)",
        "win_path": r"E:\0writing\Lark-Formatter",
        "sandbox_path": "/tmp/lark-formatter",
        "role": "Word (.docx) / Markdown (.md) 毕业论文 16 步规则流水线 + Zotero 9 引用修复 + 对比稿与审计报告",
    },
    {
        "id": "light-typesetting",
        "name": "Light-skills · Stage 11 light-typesetting",
        "win_path": r"E:\0writing\Light-skills\skills\light-typesetting",
        "sandbox_path": "",
        "role": "LaTeX / XeLaTeX / BibTeX 提交前预检、字数页数与匿名双盲合规检查、可复现 PDF 构建清单",
    },
    {
        "id": "cnki-skills",
        "name": "CNKI Scholar Assistant & Zotero 桥接",
        "win_path": r"E:\0writing\cnki-skills",
        "sandbox_path": "",
        "role": "知网文献自动综述生成、CNKI -> Zotero 题录导入 (cnki_to_zotero.py) 与 AD/牙周炎综述库",
    },
    {
        "id": "auto-figure-diagram",
        "name": "AutoFigure-Edit & Scientific-Figure-Shapes",
        "win_path": r"E:\0writing\AutoFigure-Edit",
        "sandbox_path": "",
        "role": "科研机制图、多肽筛选流程图 SVG/高 DPI 矢量插图生成与论文插图规范校验",
    },
    {
        "id": "auto-empirical",
        "name": "Auto-Empirical-Research-Skills",
        "win_path": r"E:\0writing\Auto-Empirical-Research-Skills",
        "sandbox_path": "",
        "role": "实证统计图表、三线表显著性标注与可复现实验数据分析技能集",
    },
]

CANDIDATE_MANUSCRIPTS_WIN: list[dict[str, str]] = [
    {"label": "中期报告定稿 (E:\\0zhongqi\\中期.docx)", "path": r"E:\0zhongqi\中期.docx"},
    {"label": "学位论文大纲终版 (E:\\1dagang\\终版.docx)", "path": r"E:\1dagang\终版.docx"},
    {"label": "学位论文 Markdown 正文 (E:\\1dagang\\正文.md)", "path": r"E:\1dagang\正文.md"},
    {"label": "抗菌肽模型思路稿 (E:\\0writing\\思路抗菌肽模型.docx)", "path": r"E:\0writing\思路抗菌肽模型.docx"},
]


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def detect_lark_root() -> Path | None:
    env_p = os.environ.get("ARENA_LARK_FORMATTER_ROOT", "").strip()
    candidates = []
    if env_p:
        candidates.append(Path(env_p))
    candidates.extend([
        Path(r"E:\0writing\Lark-Formatter"),
        Path(r"D:\0writing\Lark-Formatter"),
        Path("/tmp/lark-formatter"),
        HERE.parent.parent / "vendor" / "Lark-Formatter",
    ])
    for c in candidates:
        try:
            if (c / "src" / "engine" / "pipeline.py").is_file():
                return c
        except OSError:
            continue
    return None


def _python_has_docx(py_exe: str) -> bool:
    try:
        proc = subprocess.run(
            [py_exe, "-c", "import docx, lxml; print('OK')"],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        return proc.returncode == 0 and "OK" in (proc.stdout or "")
    except Exception:
        return False


_CACHED_PYTHON: str | None = None


def detect_lark_python() -> str | None:
    global _CACHED_PYTHON
    if _CACHED_PYTHON and Path(_CACHED_PYTHON).exists():
        return _CACHED_PYTHON

    env_py = os.environ.get("ARENA_LARK_PYTHON", "").strip()
    candidates: list[str] = []
    if env_py:
        candidates.append(env_py)
    candidates.extend([
        "/tmp/venv-lark/bin/python",
        r"E:\Miniforge3\envs\lark\python.exe",
        r"E:\conda-envs\lark\python.exe",
        r"C:\Users\Administrator\.conda\envs\lark\python.exe",
        r"C:\ProgramData\miniconda3\envs\lark\python.exe",
        sys.executable,
        r"E:\Miniforge3\python.exe",
    ])
    seen: set[str] = set()
    for cand in candidates:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        if Path(cand).is_file() and _python_has_docx(cand):
            _CACHED_PYTHON = cand
            return cand
    return None


def _jobs_index_path(data_dir: Path) -> Path:
    return data_dir / "thesis_jobs.json"


def _load_jobs(data_dir: Path) -> list[dict[str, Any]]:
    p = _jobs_index_path(data_dir)
    if not p.is_file():
        return []
    try:
        items = json.loads(p.read_text(encoding="utf-8"))
        return items if isinstance(items, list) else []
    except Exception:
        return []


def _save_jobs(data_dir: Path, jobs: list[dict[str, Any]]) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    p = _jobs_index_path(data_dir)
    p.write_text(json.dumps(jobs[:30], ensure_ascii=False, indent=2), encoding="utf-8")


def get_thesis_status(data_dir: Path) -> dict[str, Any]:
    lark_root = detect_lark_root()
    lark_py = detect_lark_python()
    is_win = platform.system().lower().startswith("win")

    skills_found: list[dict[str, Any]] = []
    for item in WRITING_SKILLS_ECOSYSTEM:
        target = item["win_path"] if is_win else (item["sandbox_path"] or item["win_path"])
        exists = False
        try:
            exists = Path(target).exists()
        except OSError:
            exists = False
        skills_found.append({
            **item,
            "active_path": target,
            "installed": exists,
        })

    manuscripts: list[dict[str, Any]] = []
    if BUNDLED_SAMPLE_DOCX.is_file():
        manuscripts.append({
            "label": "硕士学位论文内置实测样稿 (samples/master_sample_thesis.docx)",
            "path": str(BUNDLED_SAMPLE_DOCX),
            "exists": True,
            "size_kb": round(BUNDLED_SAMPLE_DOCX.stat().st_size / 1024, 1),
            "bundled": True,
        })
    for m in CANDIDATE_MANUSCRIPTS_WIN:
        p = Path(m["path"])
        exists = False
        size_kb = 0.0
        try:
            if p.is_file():
                exists = True
                size_kb = round(p.stat().st_size / 1024, 1)
        except OSError:
            pass
        manuscripts.append({
            "label": m["label"],
            "path": m["path"],
            "exists": exists,
            "size_kb": size_kb,
            "bundled": False,
        })

    csl_exists = bool(lark_root and (lark_root / "china-national-standard-gb-t-7714-2015-numeric.csl").is_file())
    return {
        "ok": True,
        "engine_ready": bool(lark_root and lark_py),
        "engine_version": "0.21.1-headless",
        "lark_root": str(lark_root) if lark_root else "",
        "lark_python": lark_py or "",
        "bundled_sample_ready": BUNDLED_SAMPLE_DOCX.is_file(),
        "bundled_sample_path": str(BUNDLED_SAMPLE_DOCX),
        "gbt7714_csl_ready": csl_exists,
        "profiles": BUILT_IN_PROFILES,
        "skills_ecosystem": skills_found,
        "manuscripts": manuscripts,
        "recent_jobs": _load_jobs(data_dir)[:10],
        "checked_at": _now_iso(),
    }


_RUNNER_SNIPPET = r"""
import json, os, sys, time
from pathlib import Path

os.environ["DOCX_DISABLE_FIELD_REFRESH"] = "1"
cfg_payload = json.loads(sys.argv[1])
lark_root = Path(cfg_payload["lark_root"])
sys.path.insert(0, str(lark_root))

from src.scene import manager
from src.engine.pipeline import Pipeline
from src.docx_io.style_clone import clone_scene_style_from_docx
from src.converter.md_to_docx import convert_md_to_docx

t0 = time.time()
scene = manager.load_default_scene()
opts = cfg_payload.get("options") or {}
if hasattr(scene, "zotero"):
    scene.zotero.enabled = bool(opts.get("enable_zotero", True))
if hasattr(scene, "chem_typography"):
    scene.chem_typography.enabled = bool(opts.get("enable_chem", True))
if hasattr(scene, "whitespace_normalize"):
    scene.whitespace_normalize.enabled = bool(opts.get("enable_whitespace", True))
if hasattr(scene, "md_cleanup"):
    scene.md_cleanup.enabled = bool(opts.get("enable_md_cleanup", True))
if opts.get("three_line_table", True):
    scene.normal_table_border_mode = "three_line"

tpl_path = cfg_payload.get("template_docx_path") or ""
clone_summary = None
if tpl_path and Path(tpl_path).is_file():
    clone_summary = clone_scene_style_from_docx(scene, tpl_path)

input_path = Path(cfg_payload["input_path"])
work_docx = input_path
md_convert_info = None
if input_path.suffix.lower() in (".md", ".markdown"):
    work_docx = input_path.with_suffix(".docx")
    md_convert_info = convert_md_to_docx(str(input_path), str(work_docx), scene)

pipe = Pipeline(scene)
res = pipe.run(str(work_docx))
elapsed = round(time.time() - t0, 2)

out_paths = {k: str(v) for k, v in (res.output_paths or {}).items() if v}
report_json_data = {}
rj = out_paths.get("report_json")
if rj and Path(rj).is_file():
    try:
        report_json_data = json.loads(Path(rj).read_text(encoding="utf-8"))
    except Exception:
        report_json_data = {}

report_md_text = ""
rm = out_paths.get("report_md")
if rm and Path(rm).is_file():
    try:
        report_md_text = Path(rm).read_text(encoding="utf-8")[:12000]
    except Exception:
        report_md_text = ""

summary = {
    "success": bool(res.success),
    "status": str(res.status),
    "error": str(res.error or ""),
    "failed_items": list(res.failed_items or []),
    "elapsed_sec": elapsed,
    "output_paths": out_paths,
    "clone_summary": clone_summary,
    "md_convert_info": md_convert_info,
    "total_changes": len(report_json_data.get("changes", [])) if isinstance(report_json_data, dict) else 0,
    "section_stats": report_json_data.get("summary", {}) if isinstance(report_json_data, dict) else {},
    "report_md_excerpt": report_md_text,
}
print(json.dumps(summary, ensure_ascii=True))
"""


def _sanitize_stem(name: str) -> str:
    stem = Path(name).stem
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", stem).strip(" ._")
    return (cleaned or "thesis")[:64]


def run_thesis_format(
    data_dir: Path,
    payload: dict[str, Any],
    *,
    ephemeral: bool = False,
) -> dict[str, Any]:
    lark_root = detect_lark_root()
    lark_py = detect_lark_python()
    if not lark_root or not lark_py:
        return {
            "ok": False,
            "error": (
                "未检测到 Lark-Formatter 引擎或 python-docx 运行环境。"
                f" (lark_root={lark_root}, lark_python={lark_py})"
            ),
        }

    profile_id = str(payload.get("profile_id") or "academic_master_2026").strip()
    profile = next((p for p in BUILT_IN_PROFILES if p["id"] == profile_id), BUILT_IN_PROFILES[0])
    merged_opts = dict(profile["options"])
    user_opts = payload.get("options")
    if isinstance(user_opts, dict):
        for k in ("enable_zotero", "enable_chem", "enable_whitespace", "enable_md_cleanup", "three_line_table"):
            if k in user_opts:
                merged_opts[k] = bool(user_opts[k])

    job_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + hashlib.sha1(
        os.urandom(8)
    ).hexdigest()[:6]

    if ephemeral:
        job_dir = Path(tempfile.mkdtemp(prefix=f"arenadesk-thesis-{job_id}-"))
    else:
        job_dir = data_dir / "thesis_jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

    # Resolve input source: upload base64, explicit local path, or bundled sample
    use_sample = bool(payload.get("use_sample"))
    b64_data = str(payload.get("data_base64") or "").strip()
    upload_name = str(payload.get("filename") or "").strip()
    doc_path_raw = str(payload.get("doc_path") or "").strip()

    source_label = ""
    if b64_data and upload_name:
        ext = Path(upload_name).suffix.lower()
        if ext not in (".docx", ".md", ".markdown"):
            return {"ok": False, "error": f"仅支持 .docx 或 .md 论文稿，收到：{ext or '无后缀'}"}
        raw_bytes = base64.b64decode(b64_data)
        if len(raw_bytes) > 40 * 1024 * 1024:
            return {"ok": False, "error": "上传稿件超过 40 MB 限制，请直接使用本地路径模式。"}
        safe_name = f"{_sanitize_stem(upload_name)}{ext}"
        staged_input = job_dir / safe_name
        staged_input.write_bytes(raw_bytes)
        source_label = f"上传稿件:{upload_name}"
    elif use_sample or not doc_path_raw:
        if not BUNDLED_SAMPLE_DOCX.is_file():
            return {"ok": False, "error": "内置硕士学位论文示例样稿不存在。"}
        staged_input = job_dir / "硕士学位论文_标准示例样稿.docx"
        shutil.copy2(BUNDLED_SAMPLE_DOCX, staged_input)
        source_label = "内置样稿:master_sample_thesis.docx"
    else:
        src_p = Path(doc_path_raw)
        if not src_p.is_file():
            return {"ok": False, "error": f"找不到指定的本地论文文件：{doc_path_raw}"}
        ext = src_p.suffix.lower()
        if ext not in (".docx", ".md", ".markdown"):
            return {"ok": False, "error": f"仅支持 .docx 或 .md 文件：{src_p.name}"}
        staged_input = job_dir / f"{_sanitize_stem(src_p.name)}{ext}"
        shutil.copy2(src_p, staged_input)
        source_label = str(src_p)

    tpl_path = str(payload.get("template_docx_path") or "").strip()
    if not tpl_path and profile.get("template_glob") and lark_root:
        try:
            matches = sorted(lark_root.glob(profile["template_glob"]))
            if matches and matches[0].is_file():
                tpl_path = str(matches[0])
        except OSError:
            pass

    runner_cfg = {
        "lark_root": str(lark_root),
        "input_path": str(staged_input),
        "template_docx_path": tpl_path,
        "options": merged_opts,
    }

    try:
        env = dict(os.environ)
        env["DOCX_DISABLE_FIELD_REFRESH"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run(
            [lark_py, "-c", _RUNNER_SNIPPET, json.dumps(runner_cfg, ensure_ascii=True)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=90,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "论文排版流水线执行超时 (>90s)。"}
    except Exception as exc:
        return {"ok": False, "error": f"启动排版进程失败：{exc}"}

    if proc.returncode != 0:
        err_tail = (proc.stderr or proc.stdout or "").strip()[-800:]
        return {"ok": False, "error": f"排版引擎返回非零状态 ({proc.returncode})：{err_tail}"}

    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    if not lines:
        return {"ok": False, "error": "排版引擎未返回有效 JSON 结果。"}

    try:
        result_data = json.loads(lines[-1])
    except Exception as exc:
        return {"ok": False, "error": f"解析排版结果失败：{exc}"}

    out_paths = result_data.get("output_paths") or {}
    final_path = out_paths.get("final") or ""
    compare_path = out_paths.get("compare") or ""
    report_md_path = out_paths.get("report_md") or ""
    report_json_path = out_paths.get("report_json") or ""

    # Count actual changes from report_md if report_json structure differs
    total_changes = int(result_data.get("total_changes") or 0)
    excerpt = str(result_data.get("report_md_excerpt") or "")
    if total_changes == 0 and excerpt:
        m = re.search(r"共记录\s*(\d+)\s*项", excerpt) or re.search(r"变更总数[：:]\s*(\d+)", excerpt)
        if m:
            total_changes = int(m.group(1))
        else:
            total_changes = max(0, excerpt.count("\n- ") + excerpt.count("\n| ") - 2)

    record: dict[str, Any] = {
        "job_id": job_id,
        "created_at": _now_iso(),
        "ephemeral": ephemeral,
        "profile_id": profile["id"],
        "profile_name": profile["name"],
        "source_label": source_label,
        "options": merged_opts,
        "success": bool(result_data.get("success")),
        "status": result_data.get("status", ""),
        "elapsed_sec": result_data.get("elapsed_sec", 0),
        "total_changes": total_changes,
        "failed_items": result_data.get("failed_items") or [],
        "output_paths": out_paths,
        "artifacts": {
            "final_docx": Path(final_path).name if final_path and Path(final_path).is_file() else "",
            "compare_docx": Path(compare_path).name if compare_path and Path(compare_path).is_file() else "",
            "report_md": Path(report_md_path).name if report_md_path and Path(report_md_path).is_file() else "",
            "report_json": Path(report_json_path).name if report_json_path and Path(report_json_path).is_file() else "",
        },
        "report_md_excerpt": excerpt[:6000],
    }

    if ephemeral:
        # Store in-memory map for ephemeral preview downloads (bounded to 8 entries)
        _EPHEMERAL_JOBS[job_id] = record
        while len(_EPHEMERAL_JOBS) > 8:
            oldest = next(iter(_EPHEMERAL_JOBS))
            old_rec = _EPHEMERAL_JOBS.pop(oldest, None)
            if old_rec:
                try:
                    shutil.rmtree(Path(staged_input).parent, ignore_errors=True)
                except Exception:
                    pass
    else:
        jobs = _load_jobs(data_dir)
        jobs.insert(0, record)
        _save_jobs(data_dir, jobs)

    return {"ok": True, "job": record}


_EPHEMERAL_JOBS: dict[str, dict[str, Any]] = {}


def resolve_job_artifact(data_dir: Path, job_id: str, kind: str) -> tuple[Path | None, str]:
    """Return (file_path, download_filename) for a completed formatting job or CSL export."""
    if kind == "csl":
        lark_root = detect_lark_root()
        if lark_root:
            csl = lark_root / "china-national-standard-gb-t-7714-2015-numeric.csl"
            if csl.is_file():
                return csl, csl.name
        bundled_csl = HERE / "samples" / "china-national-standard-gb-t-7714-2015-numeric.csl"
        if bundled_csl.is_file():
            return bundled_csl, bundled_csl.name
        return None, ""

    if not re.match(r"^[0-9A-Za-z_-]{6,40}$", job_id or ""):
        return None, ""

    rec = _EPHEMERAL_JOBS.get(job_id)
    if not rec:
        for item in _load_jobs(data_dir):
            if item.get("job_id") == job_id:
                rec = item
                break
    if not rec:
        return None, ""

    key_map = {
        "final": "final",
        "compare": "compare",
        "report_md": "report_md",
        "report_json": "report_json",
    }
    target_key = key_map.get(kind)
    if not target_key:
        return None, ""

    raw_p = (rec.get("output_paths") or {}).get(target_key) or ""
    if not raw_p:
        return None, ""
    p = Path(raw_p).resolve()
    if not p.is_file():
        return None, ""
    return p, p.name
