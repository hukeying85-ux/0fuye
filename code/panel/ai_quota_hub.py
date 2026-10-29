"""Gemini + Google Antigravity (反重力) Quota Zero-Waste Hub & Bio-AI Research Toolkit.

Integrates:
1. Multi-provider AI quota routing (Antigravity, Gemini CLI / AI Studio 1M-2M context,
   OmniRoute quota-aware fallback, Arena multi-session orchestration)
2. Antigravity & Gemini "Expiry Burn Queue" (防额度过期任务池) with 1-click prompt pack generator
3. HPC mu01 Slurm + GROMACS / Metagenomics sbatch generator wired to JobBeacon mobile alerts
4. Pure-Python Antimicrobial Peptide (AMP) physicochemical calculator (MW, Charge@pH7.4, pI, GRAVY, muH)
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import platform
import shutil
import time
from pathlib import Path
from typing import Any

# Standard monoisotopic/average amino acid residue masses (Da) + Kyte-Doolittle + Eisenberg consensus hydrophobicity
AA_TABLE: dict[str, tuple[float, float, float]] = {
    "A": (71.0788, 1.8, 0.62),
    "R": (156.1875, -4.5, -2.53),
    "N": (114.1038, -3.5, -0.78),
    "D": (115.0886, -3.5, -0.90),
    "C": (103.1388, 2.5, 0.29),
    "E": (129.1155, -3.5, -0.74),
    "Q": (128.1307, -3.5, -0.85),
    "G": (57.0519, -0.4, 0.48),
    "H": (137.1411, -3.2, -0.40),
    "I": (113.1594, 4.5, 1.38),
    "L": (113.1594, 3.8, 1.06),
    "K": (128.1741, -3.9, -1.50),
    "M": (131.1926, 1.9, 0.64),
    "F": (147.1766, 2.8, 1.19),
    "P": (97.1167, -1.6, 0.12),
    "S": (87.0782, -0.8, -0.18),
    "T": (101.1051, -0.7, -0.05),
    "W": (186.2132, -0.9, 0.81),
    "Y": (163.1760, -1.3, 0.26),
    "V": (99.1326, 4.2, 1.08),
}

QUOTA_POOLS: tuple[dict[str, Any], ...] = (
    {
        "id": "antigravity",
        "name": "Google Antigravity（反重力 Agent 额度池）",
        "tier": "L2 高阶推理与多文件 Agent 攻坚",
        "reset_cycle": "按滚动窗口 / 每日刷新（不用即清零）",
        "best_for": "多文件工程重构、Nature/Cell 级科研绘图代码生成 (R/Matplotlib/SVG)、英文论文段落深度润色",
        "zero_waste_tip": "每晚刷新前一键导出下方『防过期燃烧任务包』投喂给 Antigravity，将剩余额度转化为论文配图脚本与方法学章节草稿。",
        "cli_or_entry": "Antigravity IDE Workspace -> 打开仓库根目录并粘贴生成的任务包",
    },
    {
        "id": "gemini_long_ctx",
        "name": "Gemini CLI / Google AI Studio（1M–2M 超长上下文池）",
        "tier": "L1 超长文档与全量日志吞吐",
        "reset_cycle": "每日免费请求池 (RPD/TPM) + 学生/开发者额度",
        "best_for": "一次性读入整篇硕士论文（8章 120+ 篇文献前后呼应核查）、20 篇英文 PDF 综述精读、数万行 GROMACS/Slurm 报错定位",
        "zero_waste_tip": "长文档审计优先走 Gemini CLI（`gemini -p`），避免切碎文档消耗其他短上下文模型额度。",
        "cli_or_entry": "npx @google/gemini-cli  (或 npm i -g @google/gemini-cli)",
    },
    {
        "id": "omniroute_gateway",
        "name": "OmniRoute 多模型配额感知网关（自动降级兜底）",
        "tier": "L1.5 统一 OpenAI/Anthropic/Gemini 协议路由",
        "reset_cycle": "实时感知各通道余量 · 429 自动秒切备用源",
        "best_for": "把 Gemini、Antigravity 产出、Claude Code、Codex、OpenCode 与免费公益源统一挂载在同一本地端点，永不断流",
        "zero_waste_tip": "设置优先级：即将刷新重置的日度免费额度 > Gemini 免费层 > 错峰半价 API > 保底主力额度。",
        "cli_or_entry": "OmniRoute 本地网关端点 -> 自动供 Codex / OpenCode / Lark-Formatter 调用",
    },
    {
        "id": "deterministic_local",
        "name": "本地确定性引擎层（JobBeacon + Lark-Formatter）",
        "tier": "L0 零 Token 物理执行层",
        "reset_cycle": "永久免费 · 0 Token 消耗",
        "best_for": "Slurm 队列轮询、GROMACS ns/day 与 ETA 计算、Word 三线表/页眉页脚/Zotero 域一键修订、Git 自动同步",
        "zero_waste_tip": "凡是正则表达式与 AST/XML 能精确解决的排版和监控，绝不浪费一颗大模型 Token！",
        "cli_or_entry": "jb status / format_thesis.py --sample",
    },
)

DEFAULT_BURN_QUEUE: tuple[dict[str, Any], ...] = (
    {
        "id": "burn-fig-amp",
        "target_pool": "Google Antigravity (反重力)",
        "title": "生成第3章『476样本宏基因组组装与AMP筛选流程』可编辑矢量科研图脚本",
        "estimated_saving": "消化约 15% 日度 Agent 额度 · 产出出版级 SVG/PDF 绘图代码",
        "status": "ready",
        "prompt_pack": (
            "请在当前工作区编写一套零阴影、Nature 子刊配色的 Python SVG/PDF 科研流程图生成脚本：\n"
            "主题：AD患者与健康对照肠道宏基因组(n=476)抗菌肽差异挖掘全流程\n"
            "模块：fastp质控 -> Bowtie2去宿主 -> SortMeRNA -> MEGAHIT/metaSPAdes组装 -> MetaBAT2/CheckM分箱 -> Prodigal/CD-HIT -> ESM-2/XAMP预测 -> GROMACS 100ns膜动力学验证。\n"
            "要求：输出高分辨率可编辑矢量 SVG 与 PDF，中英双语标签可切换，附带自检脚本。"
        ),
    },
    {
        "id": "burn-gemini-audit",
        "target_pool": "Gemini 1M 超长上下文",
        "title": "整篇硕士论文『引言八步逻辑闭环 + 120篇参考文献正文引用一致性』全量体检",
        "estimated_saving": "一次长上下文请求替代 15 次分段提问",
        "status": "ready",
        "prompt_pack": (
            "请利用超长上下文一次性通读全文文稿，逐项核查：\n"
            "1) 引言是否严格形成『AD疾病负担→肠脑轴→菌群失调→AMP桥梁→深度学习必要性→476样本组装价值→本研究创新点』闭环；\n"
            "2) 正文所有文献角标与文末 GB/T 7714-2015 文献列表是否一一对应、有无漏引或孤立条目；\n"
            "3) 输出结构化修订清单（章节号+原句+修改建议）。"
        ),
    },
    {
        "id": "burn-md-analysis",
        "target_pool": "Google Antigravity (反重力)",
        "title": "编写 GROMACS 轨迹收敛后一键后处理套件（RMSD / RMSF / Rg / 氢键 / 膜厚度分布）",
        "estimated_saving": "提前备好脚本，Slurm 跑完瞬间出全套组图",
        "status": "ready",
        "prompt_pack": (
            "请编写一套面向 GROMACS (.xtc/.tpr/.edr) 的一键批处理脚本（Shell + Python 绘图）：\n"
            "自动调用 gmx trjconv 去周期性边界条件，依次计算主链 RMSD、残基 RMSF、回旋半径 Rg、肽-脂质氢键数并绘制四联拼图 (300 DPI TIFF + 矢量 PDF)。"
        ),
    },
    {
        "id": "burn-interview-qa",
        "target_pool": "Gemini / Antigravity 闲时余量",
        "title": "0710 生物医药硕士 · 选调/事业编结构化面试与生信研发岗高频追问库生成",
        "estimated_saving": "利用睡前剩余免费额度沉淀个人高分答题卡片",
        "status": "ready",
        "prompt_pack": (
            "围绕『深度学习挖掘肠道微生物组抗菌肽 + 超算分子动力学验证』课题，提炼：\n"
            "1) 3分钟科研亮点自我介绍（医药研发岗版 & 医疗卫健事业编版）；\n"
            "2) 10道高频深度技术追问与标准回答框架；\n"
            "3) 全程使用脱敏占位符，不包含任何个人隐私信息。"
        ),
    },
)

SLURM_TEMPLATES: dict[str, dict[str, str]] = {
    "gromacs_cu_100ns": {
        "title": "HPC mu01 (cu 64核) · GROMACS 100ns 生产动力学 + 手机完工提醒",
        "partition": "cu (64 Cores / 515G RAM)",
        "script": """#!/bin/bash
#SBATCH -J gmx_amp_100ns
#SBATCH -p cu
#SBATCH -N 1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=64
#SBATCH -o gmx_amp_%j.out
#SBATCH -e gmx_amp_%j.err

set -euo pipefail
export OMP_NUM_THREADS=64

echo "[START] Job $SLURM_JOB_ID on $(hostname) at $(date)"
gmx mdrun -deffnm md_0_1 -ntmpi 1 -ntomp 64 -cpi md_0_1.cpt -v

# 任务跑完立即通过出站 HTTPS 向手机 ntfy 推送（无需公网IP，0元秒达）
curl -fsS -H "Title: Slurm GROMACS Done ($SLURM_JOB_ID)" \\
     -H "Tags: white_check_mark" \\
     -d "mu01 节点 $(hostname) 上的 md_0_1 (100ns) 已顺利跑完！" \\
     https://ntfy.sh/arena-research-beacon-demo || true
""",
    },
    "megahit_fat1_1tb": {
        "title": "HPC mu01 (fat1 96核/1TB) · 宏基因组大内存组装分箱 + 手机完工提醒",
        "partition": "fat1 (96 Cores / 1TB RAM)",
        "script": """#!/bin/bash
#SBATCH -J megahit_476s
#SBATCH -p fat1
#SBATCH -N 1
#SBATCH --cpus-per-task=96
#SBATCH --mem=900G
#SBATCH -o megahit_%j.out
#SBATCH -e megahit_%j.err

set -euo pipefail
echo "[STAGE 1] MEGAHIT co-assembly on $(hostname)"
megahit -1 clean_R1.fq.gz -2 clean_R2.fq.gz -t 96 -m 0.85 -o megahit_out

echo "[STAGE 2] MetaBAT2 + CheckM"
checkm lineage_wf -t 64 -x fa metabat_bins/ checkm_out/

curl -fsS -H "Title: Metagenomics Assembly Finished ($SLURM_JOB_ID)" \\
     -d "fat1 大内存节点组装与 CheckM 评估已完成！" \\
     https://ntfy.sh/arena-research-beacon-demo || true
""",
    },
}


def compute_amp_metrics(sequence: str) -> dict[str, Any]:
    """Calculate physicochemical properties of an antimicrobial peptide sequence."""
    cleaned = "".join(ch for ch in (sequence or "").upper() if ch.isalpha())
    valid = "".join(ch for ch in cleaned if ch in AA_TABLE)
    if not valid:
        return {"ok": False, "error": "请输入有效的标准氨基酸单字母序列（如 GIGKFLHSAKKFGKAFVGEIMNS）"}

    n = len(valid)
    mw = sum(AA_TABLE[a][0] for a in valid) + 18.01528  # + H2O termini
    gravy = sum(AA_TABLE[a][1] for a in valid) / n

    # Eisenberg alpha-helical hydrophobic moment (delta = 100 degrees)
    rad = math.radians(100.0)
    sum_sin = sum(AA_TABLE[a][2] * math.sin(i * rad) for i, a in enumerate(valid))
    sum_cos = sum(AA_TABLE[a][2] * math.cos(i * rad) for i, a in enumerate(valid))
    mu_h = math.sqrt(sum_sin**2 + sum_cos**2) / n

    counts = {aa: valid.count(aa) for aa in ("K", "R", "H", "D", "E", "C", "Y")}

    def net_charge_at_ph(ph: float) -> float:
        pos = (
            1.0 / (1.0 + 10.0 ** (ph - 9.69))  # N-term
            + counts["K"] / (1.0 + 10.0 ** (ph - 10.53))
            + counts["R"] / (1.0 + 10.0 ** (ph - 12.48))
            + counts["H"] / (1.0 + 10.0 ** (ph - 6.00))
        )
        neg = (
            1.0 / (1.0 + 10.0 ** (2.34 - ph))  # C-term
            + counts["D"] / (1.0 + 10.0 ** (3.86 - ph))
            + counts["E"] / (1.0 + 10.0 ** (4.25 - ph))
            + counts["C"] / (1.0 + 10.0 ** (8.33 - ph))
            + counts["Y"] / (1.0 + 10.0 ** (10.07 - ph))
        )
        return pos - neg

    charge_74 = net_charge_at_ph(7.4)

    # Bisection for isoelectric point pI in [0.0, 14.0]
    lo, hi = 0.0, 14.0
    for _ in range(40):
        mid = (lo + hi) / 2.0
        if net_charge_at_ph(mid) > 0:
            lo = mid
        else:
            hi = mid
    pi_val = (lo + hi) / 2.0

    cationic_pct = (counts["K"] + counts["R"] + counts["H"]) / n * 100.0
    hint = (
        "典型阳离子两亲性抗菌肽特征（正电荷充足 + 较强两亲疏水矩）"
        if (charge_74 >= 2.0 and mu_h >= 0.25 and 8 <= n <= 60)
        else "建议结合 XAMP / HMD-AMP 模型与溶血毒性阈值进一步评估"
    )

    return {
        "ok": True,
        "sequence": valid,
        "length": n,
        "molecular_weight_da": round(mw, 2),
        "net_charge_ph74": round(charge_74, 2),
        "isoelectric_point_pi": round(pi_val, 2),
        "gravy_hydropathy": round(gravy, 3),
        "hydrophobic_moment_muh": round(mu_h, 3),
        "cationic_ratio_pct": round(cationic_pct, 1),
        "assessment": hint,
    }


def detect_local_ai_stack() -> dict[str, Any]:
    """Detect installed CLI/IDE AI tools without touching or reading any secret key values."""
    gemini_cli = bool(shutil.which("gemini"))
    codex_cli = bool(shutil.which("codex"))
    claude_cli = bool(shutil.which("claude"))
    opencode_cli = bool(shutil.which("opencode"))

    home = Path.home()
    appdata = Path(os.environ.get("APPDATA", str(home)))
    antigravity_detected = any(
        p.exists()
        for p in (
            home / ".antigravity",
            home / ".gemini" / "antigravity",
            appdata / "Antigravity",
            appdata / "Google" / "Antigravity",
        )
    )
    return {
        "gemini_cli": gemini_cli,
        "antigravity_config_dir": antigravity_detected,
        "codex_cli": codex_cli,
        "claude_cli": claude_cli,
        "opencode_cli": opencode_cli,
        "gemini_env_configured": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
    }


def list_burn_queue(data_dir: Path) -> list[dict[str, Any]]:
    f = Path(data_dir) / "quota_burn_queue.json"
    if not f.is_file():
        rows = list(DEFAULT_BURN_QUEUE)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        return rows
    try:
        rows = json.loads(f.read_text(encoding="utf-8"))
        return rows if isinstance(rows, list) else list(DEFAULT_BURN_QUEUE)
    except Exception:
        return list(DEFAULT_BURN_QUEUE)


def add_burn_task(data_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    rows = list_burn_queue(data_dir)
    item = {
        "id": f"burn-{int(time.time() * 1000)}",
        "target_pool": str(payload.get("target_pool") or "Google Antigravity (反重力)")[:60],
        "title": str(payload.get("title") or "自定义防额度过期任务")[:120],
        "estimated_saving": str(payload.get("estimated_saving") or "充分利用当期剩余免费/订阅额度")[:100],
        "status": "ready",
        "prompt_pack": str(payload.get("prompt_pack") or "").strip()[:2000],
    }
    rows.insert(0, item)
    (Path(data_dir) / "quota_burn_queue.json").write_text(
        json.dumps(rows[:30], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return item


def get_ai_quota_snapshot(data_dir: Path) -> dict[str, Any]:
    # Check CST off-peak valley window (00:30 - 08:30 UTC+8)
    now_cst = dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    mins = now_cst.hour * 60 + now_cst.minute
    in_offpeak = 30 <= mins <= 510
    return {
        "cst_time": now_cst.strftime("%H:%M CST"),
        "offpeak_valley_active": in_offpeak,
        "detected_tools": detect_local_ai_stack(),
        "pools": list(QUOTA_POOLS),
        "burn_queue": list_burn_queue(data_dir),
        "slurm_templates": SLURM_TEMPLATES,
        "sample_amp": compute_amp_metrics("GIGKFLHSAKKFGKAFVGEIMNS"),
    }
