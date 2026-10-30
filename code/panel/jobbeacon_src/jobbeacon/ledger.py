"""Persistent job, Slurm, and Molecular Dynamics watch ledger for JobBeacon.

Thread-safe JSON + JSONL state store with allowlisted mobile quick-commands.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import platform
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from .analyzers import analyze_dl_or_bio_log, analyze_md_log, analyze_slurm_table
from .notifiers import dispatch_alert
from .tunnels import build_connectivity_plan

QUICK_COMMAND_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "host_health",
        "label": "📊 本机算力与磁盘余量快照",
        "category": "system",
        "requires_gate": False,
        "description": "读取当前主机 CPU 核心、负载与工作盘剩余空间（零副作用只读）",
    },
    {
        "id": "slurm_queue_snapshot",
        "label": "🖥️ 查询 HPC (mu01) Slurm 队列状态",
        "category": "slurm",
        "requires_gate": False,
        "description": "通过 WSL SSH 非阻塞轮询 mu01 节点 squeue 状态并解析排队/运行进度",
    },
    {
        "id": "md_speed_check",
        "label": "🧬 解析分子动力学最新 ns/day 与剩余时间",
        "category": "md",
        "requires_gate": False,
        "description": "扫描最近 GROMACS / AMBER 日志尾部，重算轨迹百分比与预计完工时间",
    },
    {
        "id": "test_mobile_alert",
        "label": "🔔 发送一条「任务好了！」测试提醒",
        "category": "notify",
        "requires_gate": False,
        "description": "向手机 PWA 通知栏及已配置的 ntfy / Bark / Webhook 通道发送完工测试卡片",
    },
    {
        "id": "scancel_stuck_job",
        "label": "🛑 终止异常卡死的远程长任务（需过人工闸门）",
        "category": "slurm",
        "requires_gate": True,
        "description": "高风险操作演示：不会直接杀任务，而是进入『人工审批闸门』待您确认后才执行",
    },
)


def _utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class BeaconLedger:
    """Clean-room task & cluster watch state manager."""

    def __init__(self, store_dir: Path, *, seed_demo: bool = True) -> None:
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.watches_file = self.store_dir / "watches.json"
        self.config_file = self.store_dir / "notify_config.json"
        self.alerts_file = self.store_dir / "alerts.jsonl"
        self.cmd_log_file = self.store_dir / "quick_cmd_history.json"
        if seed_demo and not self.watches_file.is_file():
            self._seed_initial_watches()

    def _seed_initial_watches(self) -> None:
        sample_gmx = (
            "Input Parameters:\n"
            "   nsteps = 50000000\n"
            "   dt = 0.002\n"
            "           Step           Time\n"
            "       34200000    68400.00000\n"
            "   Energies (kJ/mol)\n"
            "   Temperature\n"
            "    310.15\n"
            "Performance:       91.200       0.263\n"
        )
        sample_cg = (
            "GROMACS - Martini 3 Coarse-Grained Membrane System (POPE:POPG 3:1)\n"
            "   nsteps = 100000000\n"
            "   dt = 0.020\n"
            "           Step           Time\n"
            "       72500000  1450000.00000\n"
            "   Temperature\n"
            "    310.00\n"
            "Performance:      1480.000       0.016\n"
        )
        cg_parsed = analyze_md_log(sample_cg)
        gmx_parsed = analyze_md_log(sample_gmx)
        now = _utc_iso()
        watches = [
            {
                "id": "watch-cgmd-desktop-2us",
                "title": "[台式机·hukeying85] Martini 3 粗粒化细菌膜打孔 2.0 μs 初筛",
                "kind": "cg-md",
                "target": "台式机 GPU Workstation (hukeying85-ux) · prod_pope_popg.log",
                "state": cg_parsed["state"],
                "percent": cg_parsed["percent"],
                "eta_human": cg_parsed["eta_human"],
                "speed_badge": f"{cg_parsed['speed_us_day']} μs/day",
                "summary": cg_parsed["summary"],
                "log_tail": sample_cg.strip(),
                "updated_at": now,
                "notify_on_finish": True,
            },
            {
                "id": "watch-md-amp100ns",
                "title": "[超算·shaohuawen03] GROMACS 全原子精细动力学 100 ns",
                "kind": "md",
                "target": "mu01 (cu46 · shaohuawen03-cyber) · md_amp_charmm36m.log",
                "state": gmx_parsed["state"],
                "percent": gmx_parsed["percent"],
                "eta_human": gmx_parsed["eta_human"],
                "speed_badge": f"{gmx_parsed['speed_ns_day']} ns/day",
                "summary": gmx_parsed["summary"],
                "log_tail": sample_gmx.strip(),
                "updated_at": now,
                "notify_on_finish": True,
            },
            {
                "id": "watch-slurm-92421",
                "title": "[超算·shaohuawen03] Slurm #92421 · 476样本肠道宏基因组与XAMP筛选",
                "kind": "slurm",
                "target": "mu01 (fat1 · 96核 / 1TB RAM · shaohuawen03-cyber)",
                "state": "running",
                "percent": 76.0,
                "eta_human": "约 1小时45分",
                "speed_badge": "MetaBAT2/XAMP",
                "summary": "Slurm #92421 (fat1) · 正在运行 04:18:22 · 筛出候选抗菌肽将派发台式机跑粗粒化 MD",
                "log_tail": "[INFO] MetaBAT2 binning finished 184 bins -> XAMP/HMD-AMP top candidates queued for Desktop CG-MD",
                "updated_at": now,
                "notify_on_finish": True,
            },
            {
                "id": "watch-thesis-master",
                "title": "[笔记本·mqgg5630] 硕士学位论文格式一键规整 (Lark-Formatter)",
                "kind": "thesis",
                "target": "LAPTOP-R77M5D6M (mqgg5630-cyber) · 无头引擎",
                "state": "completed",
                "percent": 100.0,
                "eta_human": "已完成",
                "speed_badge": "116 处修订",
                "summary": "1.5 秒完成三线表、奇偶页眉、中英混排字号与 Zotero 9 活动引用域修复",
                "log_tail": "[OK] Output written: _new.docx + _对比稿.docx + _报告.md (116 style normalizations)",
                "updated_at": now,
                "notify_on_finish": True,
            },
        ]
        self.watches_file.write_text(json.dumps(watches, ensure_ascii=False, indent=2), encoding="utf-8")
        dispatch_alert(
            [],
            "ESM-2 / XAMP 候选抗菌肽活性筛查",
            "completed",
            "任务已跑完：共筛出 37 条高活性候选肽段，结果已归档。",
            elapsed_sec=1122,
            host=platform.node(),
            store_dir=self.store_dir,
        )

    def get_notify_config(self) -> dict[str, Any]:
        if self.config_file.is_file():
            try:
                return json.loads(self.config_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "endpoints": ["ntfy:arena-research-beacon-demo"],
            "quiet_hours": "01:00-07:00",
            "signal_only": True,
            "notify_on_slurm_start": True,
            "notify_on_finish": True,
        }

    def save_notify_config(self, cfg: dict[str, Any]) -> dict[str, Any]:
        cur = self.get_notify_config()
        if "endpoints" in cfg and isinstance(cfg["endpoints"], list):
            cur["endpoints"] = [str(x).strip() for x in cfg["endpoints"] if str(x).strip()][:8]
        for k in ("quiet_hours", "signal_only", "notify_on_slurm_start", "notify_on_finish"):
            if k in cfg:
                cur[k] = cfg[k]
        with self._lock:
            self.config_file.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
        return cur

    def list_watches(self) -> list[dict[str, Any]]:
        if not self.watches_file.is_file():
            return []
        try:
            data = json.loads(self.watches_file.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def upsert_watch(self, item: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            items = self.list_watches()
            wid = str(item.get("id") or f"watch-{int(time.time() * 1000)}")
            item["id"] = wid
            item["updated_at"] = _utc_iso()

            # Auto-enrich if raw log_tail provided
            tail = str(item.get("log_tail") or "")
            kind = str(item.get("kind") or "cmd")
            if tail and kind == "md":
                md = analyze_md_log(tail)
                item.setdefault("state", md["state"])
                item["percent"] = md["percent"]
                item["eta_human"] = md["eta_human"]
                item["speed_badge"] = f"{md['speed_ns_day']} ns/day" if md.get("speed_ns_day") else md["engine"]
                item["summary"] = md["summary"]
            elif tail and kind in ("bio-dl", "cmd"):
                dl = analyze_dl_or_bio_log(tail)
                item.setdefault("percent", dl["percent"])
                item.setdefault("summary", dl["stage"])

            prev_state = None
            replaced = False
            for idx, existing in enumerate(items):
                if existing.get("id") == wid:
                    prev_state = existing.get("state")
                    items[idx] = {**existing, **item}
                    item = items[idx]
                    replaced = True
                    break
            if not replaced:
                items.insert(0, item)

            self.watches_file.write_text(json.dumps(items[:50], ensure_ascii=False, indent=2), encoding="utf-8")

        new_state = item.get("state")
        if new_state in ("completed", "failed") and prev_state != new_state:
            cfg = self.get_notify_config()
            dispatch_alert(
                cfg.get("endpoints", []),
                str(item.get("title") or wid),
                str(new_state),
                str(item.get("summary") or ""),
                host=platform.node(),
                store_dir=self.store_dir,
                dry_run=True,  # avoid blocking network unless user triggers live send
            )
        return item

    def list_alerts(self, limit: int = 25) -> list[dict[str, Any]]:
        if not self.alerts_file.is_file():
            return []
        rows: list[dict[str, Any]] = []
        for ln in self.alerts_file.read_text(encoding="utf-8", errors="replace").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                rows.append(json.loads(ln))
            except Exception:
                continue
        return list(reversed(rows[-limit:]))

    def list_command_history(self, limit: int = 15) -> list[dict[str, Any]]:
        if not self.cmd_log_file.is_file():
            return []
        try:
            rows = json.loads(self.cmd_log_file.read_text(encoding="utf-8"))
            return rows[:limit] if isinstance(rows, list) else []
        except Exception:
            return []

    def execute_quick_command(self, cmd_id: str, *, gate_queue_cb: Any = None) -> dict[str, Any]:
        """Execute a strictly allowlisted diagnostic command or route risky ops to Human Gate."""
        spec = next((c for c in QUICK_COMMAND_CATALOG if c["id"] == cmd_id), None)
        if spec is None:
            return {"ok": False, "error": f"Unknown quick command: {cmd_id}"}

        if spec["requires_gate"]:
            gate_item = {
                "gate_id": f"gate-{int(time.time())}",
                "command_id": cmd_id,
                "title": spec["label"],
                "status": "pending_human_approval",
                "requested_at": _utc_iso(),
                "reason": "涉及终止远程 Slurm 长作业，已按 GrokBot 人工闸门规范拦截，待您手动确认后放行。",
            }
            if callable(gate_queue_cb):
                gate_queue_cb(gate_item)
            self._append_cmd_history(cmd_id, spec["label"], "gated", gate_item["reason"])
            return {"ok": True, "gated": True, "gate": gate_item}

        output = ""
        if cmd_id == "host_health":
            usage = shutil.disk_usage(self.store_dir)
            free_gb = round(usage.free / (1024**3), 2)
            total_gb = round(usage.total / (1024**3), 2)
            cpus = os.cpu_count() or 1
            output = (
                f"主机: {platform.node()} ({platform.system()} {platform.release()})\n"
                f"逻辑核心: {cpus} Threads\n"
                f"数据分区可用空间: {free_gb} GB / {total_gb} GB"
            )
        elif cmd_id == "slurm_queue_snapshot":
            output = self._probe_slurm_safe()
        elif cmd_id == "md_speed_check":
            md_watches = [w for w in self.list_watches() if w.get("kind") == "md"]
            if md_watches:
                w = md_watches[0]
                output = f"{w['title']}\n进度: {w['percent']}% | 速度: {w.get('speed_badge')} | 预计剩余: {w.get('eta_human')}\n{w.get('summary')}"
            else:
                output = "当前暂无活动分子动力学日志盯梢项。"
        elif cmd_id == "test_mobile_alert":
            cfg = self.get_notify_config()
            res = dispatch_alert(
                cfg.get("endpoints", []),
                "JobBeacon 手机端连通性自检",
                "completed",
                "恭喜！当您的 Slurm 作业或 GROMACS 分子动力学跑完时，手机会立即收到此消息提醒。",
                elapsed_sec=1.2,
                host=platform.node(),
                store_dir=self.store_dir,
                dry_run=True,
            )
            output = f"已写入实时通知流：{res['card']['headline']}\n{res['card']['body']}"

        record = self._append_cmd_history(cmd_id, spec["label"], "completed", output)
        return {"ok": True, "gated": False, "record": record}

    def _probe_slurm_safe(self) -> str:
        if platform.system().lower().startswith("win"):
            try:
                proc = subprocess.run(
                    ["wsl.exe", "-d", "Ubuntu-26.04", "-e", "ssh", "-o", "ConnectTimeout=4", "mu01", "squeue -me"],
                    capture_output=True,
                    text=True,
                    timeout=7,
                    creationflags=0x08000000 if os.name == "nt" else 0,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    parsed = analyze_slurm_table(proc.stdout)
                    return f"[mu01 实时队列 · 运行 {parsed['counts']['running']} / 排队 {parsed['counts']['pending']}]\n{proc.stdout.strip()[:800]}"
            except Exception:
                pass
        slurm_w = [w for w in self.list_watches() if w.get("kind") in ("slurm", "md")]
        lines = [f"• {w['title']} -> {w['percent']}% ({w['eta_human']})" for w in slurm_w]
        return "HPC mu01 盯梢缓存摘要:\n" + ("\n".join(lines) if lines else "当前无排队作业")

    def _append_cmd_history(self, cmd_id: str, label: str, status: str, output: str) -> dict[str, Any]:
        rec = {
            "id": f"cmd-{int(time.time() * 1000)}",
            "command_id": cmd_id,
            "label": label,
            "status": status,
            "output": output,
            "executed_at": _utc_iso(),
        }
        with self._lock:
            hist = self.list_command_history(limit=30)
            hist.insert(0, rec)
            self.cmd_log_file.write_text(json.dumps(hist[:30], ensure_ascii=False, indent=2), encoding="utf-8")
        return rec

    def snapshot(self, *, port: int = 18765, preview_origin: str = "") -> dict[str, Any]:
        watches = self.list_watches()
        running_n = sum(1 for w in watches if w.get("state") == "running")
        done_n = sum(1 for w in watches if w.get("state") == "completed")
        failed_n = sum(1 for w in watches if w.get("state") == "failed")
        return {
            "version": "0.2.0",
            "license": "Apache-2.0",
            "counts": {
                "total": len(watches),
                "running": running_n,
                "completed": done_n,
                "failed": failed_n,
            },
            "watches": watches,
            "alerts": self.list_alerts(limit=20),
            "quick_commands": list(QUICK_COMMAND_CATALOG),
            "command_history": self.list_command_history(limit=12),
            "notify_config": self.get_notify_config(),
            "connectivity": build_connectivity_plan(self.store_dir, port=port, preview_origin=preview_origin),
        }
