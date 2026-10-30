"""Domain-specific scientific log & cluster queue analyzers for JobBeacon.

100% original clean-room parsers for:
- Molecular Dynamics & Quantum Chemistry: GROMACS, AMBER, OpenMM, ORCA
- HPC Workload Managers: Slurm (squeue / sacct)
- Deep Learning & Bioinformatics pipelines: Epoch/Loss + Metagenomics stages
"""

from __future__ import annotations

import re
from typing import Any

SLURM_STATUS_LABELS: dict[str, tuple[str, str]] = {
    "PD": ("排队等待", "pending"),
    "PENDING": ("排队等待", "pending"),
    "R": ("正在运行", "running"),
    "RUNNING": ("正在运行", "running"),
    "CG": ("收尾写出", "running"),
    "COMPLETING": ("收尾写出", "running"),
    "CD": ("运行完成", "completed"),
    "COMPLETED": ("运行完成", "completed"),
    "F": ("异常失败", "failed"),
    "FAILED": ("异常失败", "failed"),
    "TO": ("超时终止", "failed"),
    "TIMEOUT": ("超时终止", "failed"),
    "CA": ("手动取消", "cancelled"),
    "CANCELLED": ("手动取消", "cancelled"),
    "OOM": ("内存溢出", "failed"),
    "OUT_OF_MEMORY": ("内存溢出", "failed"),
    "NF": ("节点故障", "failed"),
}

BIO_PIPELINE_STAGES: tuple[tuple[str, str, int], ...] = (
    (r"\bfastp\b", "质控过滤 (fastp)", 15),
    (r"\bbowtie2\b", "去宿主比对 (Bowtie2)", 30),
    (r"\bsortmerna\b", "去rRNA富集 (SortMeRNA)", 42),
    (r"\b(?:megahit|metaspades)\b", "宏基因组组装 (MEGAHIT/SPAdes)", 60),
    (r"\b(?:metabat2|checkm)\b", "分箱与完整度评估 (MetaBAT2/CheckM)", 76),
    (r"\b(?:prodigal|cd-hit)\b", "基因预测与去冗余 (Prodigal/CD-HIT)", 88),
    (r"\b(?:xamp|hmd-amp|esm-?2|amp_predict)\b", "抗菌肽深度学习筛查 (AMP-DL)", 95),
)


def format_eta_human(seconds: float | None) -> str:
    """Convert remaining seconds into concise Chinese duration text."""
    if seconds is None or seconds < 0:
        return "计算中"
    sec = int(round(seconds))
    if sec == 0:
        return "已完成"
    if sec < 60:
        return f"{sec}秒"
    mins, s = divmod(sec, 60)
    if mins < 60:
        return f"{mins}分{s:02d}秒"
    hrs, m = divmod(mins, 60)
    if hrs < 48:
        return f"{hrs}小时{m:02d}分"
    days, h = divmod(hrs, 24)
    return f"{days}天{h}小时"


def analyze_md_log(log_text: str) -> dict[str, Any]:
    """Extract trajectory progress, ns/day speed, and ETA from MD / QM logs."""
    if not log_text or not log_text.strip():
        return {
            "engine": "unknown",
            "state": "idle",
            "percent": 0.0,
            "sim_ns": 0.0,
            "target_ns": 0.0,
            "speed_ns_day": 0.0,
            "eta_seconds": None,
            "eta_human": "等待输出",
            "summary": "尚未读取到动力学日志数据",
        }

    # 1. Detect engine
    low = log_text.lower()
    if "gromacs" in low or "gmx mdrun" in low or re.search(r"^\s*Step\s+Time\b", log_text, re.M):
        return _parse_gromacs(log_text)
    if "nstep =" in low and "time(ps)" in low:
        return _parse_amber(log_text)
    if "orca" in low and ("scf converged" in low or "geometry optimization cycle" in low or "orca terminated" in low):
        return _parse_orca(log_text)
    if "ns/day" in low or "progress (%)" in low:
        return _parse_openmm_generic(log_text)

    return {
        "engine": "generic-md",
        "state": "running",
        "percent": 0.0,
        "sim_ns": 0.0,
        "target_ns": 0.0,
        "speed_ns_day": 0.0,
        "eta_seconds": None,
        "eta_human": "运行中",
        "summary": log_text.strip().splitlines()[-1][:120],
    }


def _parse_gromacs(text: str) -> dict[str, Any]:
    nsteps_m = re.search(r"\bnsteps\s*=\s*(\d+)", text)
    dt_m = re.search(r"\bdt\s*=\s*([0-9.]+)", text)
    nsteps = int(nsteps_m.group(1)) if nsteps_m else 0
    dt_ps = float(dt_m.group(1)) if dt_m else 0.002  # standard 2 fs

    step_pairs = re.findall(
        r"^\s*Step\s+Time\s*\r?\n\s*(\d+)\s+([0-9.Ee+-]+)",
        text,
        flags=re.M,
    )
    cur_step = int(step_pairs[-1][0]) if step_pairs else 0
    cur_ps = float(step_pairs[-1][1]) if step_pairs else (cur_step * dt_ps)

    # Also support GROMACS terminal stderr style: "step 34200000, will finish ... remaining wall clock time: 29845 s"
    inline_steps = re.findall(r"\bstep\s+(\d+)\b", text, flags=re.I)
    if inline_steps:
        last_inline = int(inline_steps[-1])
        if last_inline > cur_step:
            cur_step = last_inline
            cur_ps = cur_step * dt_ps

    perf_matches = re.findall(r"Performance:\s*([0-9.]+)\s+([0-9.]+)", text)
    speed_ns_day = float(perf_matches[-1][0]) if perf_matches else 0.0

    # Inline GROMACS speed / remaining seconds if present
    rem_matches = re.findall(r"remaining(?:\s+wall\s+clock)?\s+time:\s*(\d+)\s*s", text, flags=re.I)
    explicit_eta = float(rem_matches[-1]) if rem_matches else None

    temp_matches = re.findall(r"Temperature\s*\r?\n\s*([0-9.Ee+-]+)", text)
    temperature_k = float(temp_matches[-1]) if temp_matches else None

    is_cg = bool(
        dt_ps >= 0.010
        or re.search(r"\bmartini\b|\binsane\.py\b|\bmartinize2?\b|\bcgmd\b|\bcoarse[-_\s]?grain", text, flags=re.I)
    )
    engine_label = "GROMACS (Martini CG-MD)" if is_cg else "GROMACS"

    finished = bool(re.search(r"Finished mdrun on rank\s+\d+|GROMACS reminds you:", text))
    cg_diverged = bool(
        re.search(
            r"pressure scaling more than \d+%|bond length .* deviates more than|atom \d+ moved more than the distance",
            text,
            flags=re.I,
        )
    )
    failed = bool(
        cg_diverged or re.search(r"Fatal error:|LINCS WARNING.*too many|Segmentation fault", text)
    )

    target_ps = nsteps * dt_ps if nsteps > 0 else 0.0
    sim_ns = round(cur_ps / 1000.0, 3)
    target_ns = round(target_ps / 1000.0, 3)
    sim_us = round(sim_ns / 1000.0, 4)
    target_us = round(target_ns / 1000.0, 4)
    speed_us_day = round(speed_ns_day / 1000.0, 3) if speed_ns_day > 0 else 0.0

    if finished:
        pct = 100.0
        if target_ns > sim_ns:
            sim_ns = target_ns
            sim_us = round(sim_ns / 1000.0, 4)
        eta_sec: float | None = 0.0
        state = "completed"
    elif failed:
        pct = round((cur_step / nsteps * 100.0), 2) if nsteps > 0 else 0.0
        eta_sec = None
        state = "failed"
    else:
        pct = round(min(99.9, (cur_step / nsteps * 100.0)), 2) if nsteps > 0 else 0.0
        if explicit_eta is not None:
            eta_sec = explicit_eta
        elif speed_ns_day > 0 and target_ns > sim_ns:
            eta_sec = ((target_ns - sim_ns) / speed_ns_day) * 86400.0
        else:
            eta_sec = None
        state = "running"

    eta_str = format_eta_human(eta_sec)
    if target_ns >= 1000.0 or is_cg:
        prog_txt = (
            f"{sim_us:g}/{target_us or '?'} us ({pct:.1f}%)"
            if target_ns >= 500.0
            else f"{sim_ns:g}/{target_ns or '?'} ns ({pct:.1f}%)"
        )
    else:
        prog_txt = f"{sim_ns:g}/{target_ns or '?'} ns ({pct:.1f}%)"

    parts = [f"{engine_label} {prog_txt}"]
    if speed_ns_day > 0:
        if speed_ns_day >= 500.0 or is_cg:
            parts.append(f"{speed_ns_day:.0f} ns/day ({speed_us_day:.2f} us/day)")
        else:
            parts.append(f"{speed_ns_day:.1f} ns/day")

    remediation = ""
    if cg_diverged and is_cg:
        remediation = "粗粒化体系压强/键长震荡：建议先用 dt=0.010 ps + Berendsen 恒压预平衡 20 ns 再切回 dt=0.020 ps Parrinello-Rahman"

    if finished:
        parts.append("已完成")
    elif failed:
        parts.append("体系发散报警" if cg_diverged else "异常中断")
    else:
        parts.append(f"预计剩余 {eta_str}" if eta_sec is not None else state)

    return {
        "engine": engine_label,
        "coarse_grained": is_cg,
        "dt_ps": dt_ps,
        "state": state,
        "current_step": cur_step,
        "total_steps": nsteps,
        "percent": pct,
        "sim_ns": sim_ns,
        "target_ns": target_ns,
        "sim_us": sim_us,
        "target_us": target_us,
        "speed_ns_day": round(speed_ns_day, 2),
        "speed_us_day": speed_us_day,
        "temperature_k": temperature_k,
        "eta_seconds": round(eta_sec, 1) if eta_sec is not None else None,
        "eta_human": eta_str,
        "remediation": remediation,
        "summary": " · ".join(parts),
    }


def _parse_amber(text: str) -> dict[str, Any]:
    nstlim_m = re.search(r"\bnstlim\s*=\s*(\d+)", text, flags=re.I)
    dt_m = re.search(r"\bdt\s*=\s*([0-9.]+)", text, flags=re.I)
    total_steps = int(nstlim_m.group(1)) if nstlim_m else 0
    dt_ps = float(dt_m.group(1)) if dt_m else 0.002

    frames = re.findall(
        r"NSTEP\s*=\s*(\d+)\s+TIME\(PS\)\s*=\s*([0-9.]+)\s+TEMP\(K\)\s*=\s*([0-9.]+)",
        text,
        flags=re.I,
    )
    cur_step = int(frames[-1][0]) if frames else 0
    cur_ps = float(frames[-1][1]) if frames else 0.0
    temp_k = float(frames[-1][2]) if frames else None

    speeds = re.findall(r"ns/day\s*=\s*([0-9.]+)", text, flags=re.I)
    speed_ns_day = float(speeds[-1]) if speeds else 0.0

    finished = "5.  TIMINGS" in text or "Master Total wall time" in text
    target_ns = round((total_steps * dt_ps) / 1000.0, 3) if total_steps > 0 else 0.0
    sim_ns = round((cur_step * dt_ps) / 1000.0, 3) if total_steps > 0 else round(cur_ps / 1000.0, 3)
    pct = 100.0 if finished else (round(min(99.9, cur_step / total_steps * 100.0), 2) if total_steps else 0.0)
    eta_sec = 0.0 if finished else (
        ((target_ns - sim_ns) / speed_ns_day) * 86400.0 if speed_ns_day > 0 and target_ns > sim_ns else None
    )
    eta_str = format_eta_human(eta_sec)

    return {
        "engine": "AMBER",
        "state": "completed" if finished else "running",
        "current_step": cur_step,
        "total_steps": total_steps,
        "percent": pct,
        "sim_ns": sim_ns,
        "target_ns": target_ns,
        "speed_ns_day": round(speed_ns_day, 2),
        "temperature_k": temp_k,
        "eta_seconds": round(eta_sec, 1) if eta_sec is not None else None,
        "eta_human": eta_str,
        "summary": f"AMBER {sim_ns:g}/{target_ns or '?'} ns ({pct:.1f}%) · {speed_ns_day:.1f} ns/day · {eta_str}",
    }


def _parse_orca(text: str) -> dict[str, Any]:
    cycles = [int(x) for x in re.findall(r"GEOMETRY OPTIMIZATION CYCLE\s+(\d+)", text)]
    scf_ok = len(re.findall(r"SCF CONVERGED AFTER\s+\d+\s+CYCLES", text))
    done = "****ORCA TERMINATED NORMALLY****" in text
    failed = "ORCA finished by error termination" in text
    cur_cycle = cycles[-1] if cycles else scf_ok
    pct = 100.0 if done else min(95.0, float(cur_cycle * 8))
    state = "completed" if done else ("failed" if failed else "running")
    return {
        "engine": "ORCA",
        "state": state,
        "current_step": cur_cycle,
        "total_steps": 0,
        "percent": pct,
        "sim_ns": 0.0,
        "target_ns": 0.0,
        "speed_ns_day": 0.0,
        "eta_seconds": 0.0 if done else None,
        "eta_human": "已完成" if done else ("异常终止" if failed else f"第 {cur_cycle} 轮优化中"),
        "summary": f"ORCA 量化计算 · 优化轮次 {cur_cycle} · SCF收敛 {scf_ok} 次 · {'正常结束' if done else state}",
    }


def _parse_openmm_generic(text: str) -> dict[str, Any]:
    pcts = [float(x) for x in re.findall(r"([0-9]+(?:\.[0-9]+)?)%", text)]
    speeds = [float(x) for x in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*ns/day", text, flags=re.I)]
    pct = pcts[-1] if pcts else 0.0
    spd = speeds[-1] if speeds else 0.0
    state = "completed" if pct >= 100.0 else "running"
    return {
        "engine": "OpenMM",
        "state": state,
        "percent": round(min(100.0, pct), 2),
        "sim_ns": 0.0,
        "target_ns": 0.0,
        "speed_ns_day": round(spd, 2),
        "eta_seconds": 0.0 if pct >= 100.0 else None,
        "eta_human": "已完成" if pct >= 100.0 else "运行中",
        "summary": f"OpenMM 动力学 ({pct:.1f}%) · {spd:.1f} ns/day",
    }


def analyze_slurm_table(
    raw_output: str,
    previous_states: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Parse Slurm squeue or sacct output and generate transition notifications."""
    prev = dict(previous_states or {})
    jobs: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []

    for raw_line in (raw_output or "").splitlines():
        line = raw_line.strip()
        if not line or line.upper().startswith(("JOBID", "---")):
            continue

        # Pipe-delimited sacct -P: JobID|Partition|JobName|State|Elapsed|NodeList
        if "|" in line:
            cols = [c.strip() for c in line.split("|")]
            if len(cols) < 4 or "." in cols[0]:  # skip .batch/.extern sub-steps
                continue
            jid, part, name, raw_st = cols[0], cols[1], cols[2], cols[3].split()[0].upper()
            elapsed = cols[4] if len(cols) > 4 else ""
            nodelist = cols[5] if len(cols) > 5 else ""
            nodes = "1"
        else:
            cols = line.split()
            if len(cols) < 5 or not re.match(r"^\d+(?:_\d+)?$", cols[0]):
                continue
            # Standard squeue: JOBID PARTITION NAME USER ST TIME NODES NODELIST(REASON)
            jid, part, name = cols[0], cols[1], cols[2]
            raw_st = cols[4].upper()
            elapsed = cols[5] if len(cols) > 5 else ""
            nodes = cols[6] if len(cols) > 6 else "1"
            nodelist = " ".join(cols[7:]) if len(cols) > 7 else ""

        label_cn, norm_state = SLURM_STATUS_LABELS.get(raw_st, (raw_st, "running"))
        row = {
            "job_id": jid,
            "partition": part,
            "name": name,
            "raw_state": raw_st,
            "state": norm_state,
            "state_label": label_cn,
            "elapsed": elapsed,
            "nodes": nodes,
            "nodelist": nodelist,
        }
        jobs.append(row)

        old_st = prev.get(jid)
        if old_st and old_st != norm_state:
            transitions.append(
                {
                    "job_id": jid,
                    "name": name,
                    "partition": part,
                    "from_state": old_st,
                    "to_state": norm_state,
                    "headline": f"Slurm #{jid} ({name}) 状态变更：{old_st} -> {label_cn}",
                }
            )

    counts = {"running": 0, "pending": 0, "completed": 0, "failed": 0}
    for j in jobs:
        st = j["state"]
        if st in counts:
            counts[st] += 1

    return {
        "jobs": jobs,
        "counts": counts,
        "transitions": transitions,
        "state_map": {j["job_id"]: j["state"] for j in jobs},
    }


def analyze_dl_or_bio_log(text: str) -> dict[str, Any]:
    """Detect deep-learning epoch/loss or metagenomics pipeline stages from stdout."""
    if not text or not text.strip():
        return {"kind": "generic", "percent": 0.0, "stage": "等待输出", "metrics": {}}

    epochs = re.findall(r"epoch\s*[:=\[]?\s*(\d+)\s*/\s*(\d+)", text, flags=re.I)
    losses = re.findall(r"\bloss\s*[:=]\s*([0-9.]+(?:e[+-]?\d+)?)", text, flags=re.I)
    if epochs:
        cur_e, tot_e = int(epochs[-1][0]), max(1, int(epochs[-1][1]))
        pct = round(min(100.0, cur_e / tot_e * 100.0), 1)
        loss_val = float(losses[-1]) if losses else None
        return {
            "kind": "deep-learning",
            "percent": pct,
            "stage": f"Epoch {cur_e}/{tot_e}" + (f" · loss={loss_val:.4f}" if loss_val is not None else ""),
            "metrics": {"epoch": cur_e, "total_epochs": tot_e, "loss": loss_val},
        }

    matched_stage = ""
    matched_pct = 0
    for pat, label, pct in BIO_PIPELINE_STAGES:
        if re.search(pat, text, flags=re.I):
            matched_stage = label
            matched_pct = pct
    if matched_stage:
        return {
            "kind": "bioinformatics",
            "percent": float(matched_pct),
            "stage": matched_stage,
            "metrics": {},
        }

    pcts = [float(x) for x in re.findall(r"\b(\d{1,3}(?:\.\d+)?)%", text)]
    last_pct = min(100.0, pcts[-1]) if pcts else 0.0
    return {
        "kind": "generic",
        "percent": round(last_pct, 1),
        "stage": text.strip().splitlines()[-1][:90],
        "metrics": {},
    }
