"""Command line entry point of the CGMD pipeline.

Examples
--------
Dry run (no GPU, prints the full command plan)::

    python -m cgmd.cli run --sequence GIGKFLHSAKKFGKAFVGEIMNS --dry-run

Real run driven by a task document from the hub::

    python -m cgmd.cli run --task results/status/cgmd_task.json \
        --workdir /data/cgmd-runs/cgmd-20261028-120000-ab12 \
        --output results/cgmd/cgmd-20261028-120000-ab12

Environment self-check (used by ``bootstrap_desktop.ps1``)::

    python -m cgmd.cli env-check --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core import task_contract  # noqa: E402
from core.ntfy_beacon import Beacon  # noqa: E402

from .config import Config, config_from_task, resolve_martini3_dir  # noqa: E402
from .engine import probe_environment  # noqa: E402
from .pipeline import Pipeline, PipelineError  # noqa: E402


def _configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _beacon(topic: str, dry_run: bool) -> Beacon:
    return Beacon(topic=topic or task_contract.DEFAULT_TOPIC, dry_run=dry_run)


def _notifier(beacon: Beacon):
    def notify(event: str, headline: str, lines: Optional[List[str]] = None) -> None:
        beacon.send_event(event, headline, lines)

    return notify


def build_config(args: argparse.Namespace) -> tuple:
    """Return ``(cfg, task, output_dir)`` from CLI arguments."""
    if args.task:
        task = task_contract.load_task(args.task, strict=False)
        task_id = task.get("task_id") or "adhoc"
        workdir = args.workdir or os.path.join(os.path.expanduser("~"), "cgmd-runs", task_id)
        output = args.output or os.path.join("results", "cgmd", task_id)
        cfg = config_from_task(task, workdir)
    else:
        sequence = task_contract.validate_sequence(args.sequence or "")
        task = task_contract.new_task(
            sequence=sequence,
            name=args.name or "adhoc-{}aa".format(len(sequence)),
            production_ns=args.production_ns,
            equilibration_ns=args.equilibration_ns,
            created_by="cli",
            gpu_id=args.gpu_id,
        )
        task_id = task["task_id"]
        workdir = args.workdir or os.path.join(os.path.expanduser("~"), "cgmd-runs", task_id)
        output = args.output or os.path.join("results", "cgmd", task_id)
        cfg = config_from_task(task, workdir)

    cfg.dry_run = bool(args.dry_run)
    cfg.resume = not bool(args.no_resume)
    cfg.max_frames = int(args.max_frames)
    if args.gpu_id is not None:
        cfg.gpu_id = args.gpu_id
    if args.ntomp is not None:
        cfg.ntomp = args.ntomp
    if args.martini3_dir:
        cfg.martini3_dir = args.martini3_dir
    if args.production_ns is not None:
        cfg.production_ns = float(args.production_ns)
    if args.equilibration_ns is not None:
        cfg.equilibration_ns = float(args.equilibration_ns)
    if getattr(args, "gmx", None):
        cfg.gmx_binary = args.gmx
    if getattr(args, "martinize", None):
        cfg.martinize_binary = args.martinize
    if getattr(args, "insane", None):
        cfg.insane_binary = args.insane
    if getattr(args, "lipids", None):
        cfg.lipids = _parse_lipids(args.lipids)
    if getattr(args, "box_xy_nm", None) is not None:
        cfg.box_xy_nm = float(args.box_xy_nm)
    if getattr(args, "box_z_nm", None) is not None:
        cfg.box_z_nm = float(args.box_z_nm)
    if getattr(args, "salt_m", None) is not None:
        cfg.salt_m = float(args.salt_m)
    if getattr(args, "temperature_k", None) is not None:
        cfg.temperature_k = float(args.temperature_k)
    if getattr(args, "maxh", None) is not None:
        cfg.maxh_hours = float(args.maxh)
    if getattr(args, "segment_ns", None) is not None:
        cfg.segment_ns = float(args.segment_ns)
    if getattr(args, "no_fetch_ff", False):
        cfg.fetch_forcefield = False
    cfg.task_id = cfg.task_id or task_id
    return cfg, task, output


def cmd_run(args: argparse.Namespace) -> int:
    cfg, task, output = build_config(args)
    os.makedirs(output, exist_ok=True)
    beacon = _beacon(cfg.ntfy_topic, dry_run=cfg.dry_run or bool(args.no_notify))
    notify = _notifier(beacon)

    pipeline = Pipeline(cfg, output_dir=os.path.abspath(output), notify=notify)
    notify(
        "start",
        "粗粒化流水线启动：{}".format(cfg.peptide_name),
        [
            "肽长: {} aa".format(len(cfg.sequence)),
            "体系: {} 比 {}".format(":".join(cfg.lipids), ":".join(_num(v) for v in cfg.lipids.values())),
            "生产: {} ns @ GPU {}".format(cfg.production_ns, cfg.gpu_id),
            "任务: {}".format(cfg.task_id),
        ],
    )
    try:
        metrics = pipeline.run()
    except PipelineError as exc:
        notify("error", "流水线失败", [str(exc)[:400], "任务: {}".format(cfg.task_id)])
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - report and fail loudly
        notify("error", "流水线异常", ["{}: {}".format(type(exc).__name__, str(exc)[:300]),
                                       "任务: {}".format(cfg.task_id)])
        raise

    summary_path = os.path.join(output, "summary_metrics.json")
    simulation = metrics.get("simulation", {})
    insertion = metrics.get("membrane_insertion", {})
    pore = metrics.get("pore", {})
    headline = "模拟完成：{}".format(cfg.peptide_name)
    if simulation.get("diverged"):
        headline = "模拟发散：{}".format(cfg.peptide_name)
    notify(
        "done" if not simulation.get("diverged") else "error",
        headline,
        [
            "嵌膜深度: {} nm".format(insertion.get("z_distance_mean_nm")),
            "脂序参数: {}".format(metrics.get("lipid_order", {}).get("mean")),
            "水孔: {}".format("形成" if pore.get("pore_formed") else "未形成"),
            "速度: {} ns/day".format(simulation.get("ns_per_day")),
            "结果: {}".format(os.path.relpath(summary_path)),
        ],
    )
    print("summary: {}".format(summary_path))
    return 3 if simulation.get("diverged") else 0


def cmd_env(args: argparse.Namespace) -> int:
    report = probe_environment()
    try:
        report["martini3_dir"] = resolve_martini3_dir(args.martini3_dir)
    except Exception as exc:  # noqa: BLE001
        report["martini3_dir"] = None
        report["martini3_error"] = str(exc)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("python       : {}".format(report.get("python")))
        print("gromacs      : {}".format(report.get("tools", {}).get("gromacs")))
        print("gromacs info : {}".format(report.get("gromacs")))
        print("martinize2   : {}".format(report.get("tools", {}).get("martinize2")))
        print("insane       : {}".format(report.get("tools", {}).get("insane")))
        print("martini3 dir : {}".format(report.get("martini3_dir")))
        for device in report.get("gpu", {}).get("devices", []):
            print("gpu {index}       : {name} ({memory_mb} MB)".format(**device))
    ok = bool(report.get("tools", {}).get("gromacs")) and bool(report.get("martini3_dir"))
    return 0 if ok else 1


def cmd_plan(args: argparse.Namespace) -> int:
    cfg, task, output = build_config(args)
    cfg.dry_run = True
    pipeline = Pipeline(cfg, output_dir=os.path.abspath(output), logger=lambda message: None)
    metrics = pipeline.run()
    print(json.dumps({"task": task.get("task_id"), "output": output,
                      "metrics": metrics.get("simulation", {}),
                      "notes": metrics.get("notes")}, ensure_ascii=False, indent=2))
    return 0


def cmd_describe(args: argparse.Namespace) -> int:
    from . import peptide

    print(json.dumps(peptide.describe(args.sequence), ensure_ascii=False, indent=2))
    return 0


def _num(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(number)) if number.is_integer() else str(number)


def _parse_lipids(text: str) -> Dict[str, float]:
    """``"POPE:3,POPG:1"`` -> ``{"POPE": 3.0, "POPG": 1.0}``."""
    lipids: Dict[str, float] = {}
    for item in str(text or "").replace(";", ",").split(","):
        item = item.strip()
        if not item:
            continue
        name, _, ratio = item.partition(":")
        if not name.strip():
            continue
        lipids[name.strip()] = float(ratio) if ratio.strip() else 1.0
    if not lipids:
        raise SystemExit("--lipids needs at least one LIPID:RATIO pair, e.g. POPE:3,POPG:1")
    return lipids


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m cgmd.cli",
        description="Martini 3 coarse-grained antimicrobial peptide pipeline (CGMD-Engine)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def _common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--task", default=None, help="task JSON (results/status/cgmd_task.json)")
        p.add_argument("--sequence", default=None, help="ad-hoc one-letter peptide sequence")
        p.add_argument("--name", default=None, help="peptide name")
        p.add_argument("--workdir", default=None, help="scratch directory for trajectories")
        p.add_argument("--output", default=None, help="results directory (git tracked)")
        p.add_argument("--production-ns", dest="production_ns", type=float, default=None)
        p.add_argument("--equilibration-ns", dest="equilibration_ns", type=float, default=None)
        p.add_argument("--gpu-id", dest="gpu_id", type=int, default=None)
        p.add_argument("--ntomp", type=int, default=None)
        p.add_argument("--martini3-dir", dest="martini3_dir", default=None)
        p.add_argument("--fetch-forcefield", dest="fetch_forcefield", action="store_true", default=None,
                       help="shallow-clone marrink-lab/martini-forcefields when nothing is found")
        p.add_argument("--no-fetch-ff", dest="no_fetch_ff", action="store_true",
                       help="never touch the network for force-field files")
        p.add_argument("--gmx", dest="gmx", default=None, help="explicit gmx/gmx.exe path")
        p.add_argument("--martinize", dest="martinize", default=None,
                       help="explicit martinize2 executable (e.g. <python>\\Scripts\\martinize2.exe)")
        p.add_argument("--insane", dest="insane", default=None,
                       help="explicit insane executable")
        p.add_argument("--lipids", dest="lipids", default=None,
                       help='lipid mix, e.g. "POPE:3,POPG:1"')
        p.add_argument("--box-xy-nm", dest="box_xy_nm", type=float, default=None)
        p.add_argument("--box-z-nm", dest="box_z_nm", type=float, default=None)
        p.add_argument("--salt-m", dest="salt_m", type=float, default=None)
        p.add_argument("--temperature-k", dest="temperature_k", type=float, default=None)
        p.add_argument("--maxh", dest="maxh", type=float, default=None,
                       help="wall-clock ceiling per mdrun call in hours (0 = unlimited)")
        p.add_argument("--segment-ns", dest="segment_ns", type=float, default=None,
                       help="longest single mdrun segment in ns (0 = whole production)")
        p.add_argument("--max-frames", dest="max_frames", type=int, default=400)
        p.add_argument("--dry-run", dest="dry_run", action="store_true", help="print the plan, touch no GPU")
        p.add_argument("--no-resume", dest="no_resume", action="store_true")
        p.add_argument("--no-notify", dest="no_notify", action="store_true")

    p_run = sub.add_parser("run", help="run the full pipeline")
    _common(p_run)
    p_run.set_defaults(func=cmd_run)

    p_plan = sub.add_parser("plan", help="dry-run plan of commands (no GPU needed)")
    _common(p_plan)
    p_plan.set_defaults(func=cmd_plan)

    p_env = sub.add_parser("env-check", help="probe GPU / GROMACS / Martini 3")
    p_env.add_argument("--json", action="store_true")
    p_env.add_argument("--martini3-dir", dest="martini3_dir", default=None)
    p_env.set_defaults(func=cmd_env)

    p_desc = sub.add_parser("describe", help="physico-chemical descriptor of a peptide")
    p_desc.add_argument("sequence")
    p_desc.set_defaults(func=cmd_describe)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _configure_stdout()
    args = build_parser().parse_args(argv)
    if args.command in ("run", "plan") and not args.task and not args.sequence:
        print("either --task or --sequence is required", file=sys.stderr)
        return 2
    return int(args.func(args) or 0)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
