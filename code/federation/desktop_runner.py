#!/usr/bin/env python3
"""WSL-side driver that executes a pending CGMD task on the desktop GPU.

Invoked by ``skills/cgmd-hub/runner/Invoke-CgmdPoll.ps1`` inside WSL2, after
the Windows poller has pulled the branch.  It performs, in order:

1. claim the task (``pending`` -> ``claimed``) and beacon the phone;
2. run the Martini 3 pipeline with the workstation's GROMACS/CUDA build,
   while ``node_agent.py`` tails ``prod.log`` and pushes live progress;
3. shrink the results to ``summary_metrics.json`` + SVG figures and prune any
   heavy trajectory that accidentally landed inside the repository;
4. set ``status`` to ``completed_on_desktop`` (or ``failed_on_desktop``) and
   attach the reduced result block plus a ``result.json`` mirror;
5. print a small JSON document on stdout, which the PowerShell poller parses
   before committing and pushing the branch.

Everything heavy stays in ``--workdir-root`` (default ``~/cgmd-runs``) which
lives *outside* the repository, so ``.xtc``/``.trr``/``.tpr`` files can never
be committed.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_CGMD_ROOT = os.path.join(_REPO_ROOT, "code", "cgmd")
if _CGMD_ROOT not in sys.path:
    sys.path.insert(0, _CGMD_ROOT)

from core import task_contract  # noqa: E402
from core.ntfy_beacon import Beacon  # noqa: E402

HEAVY_PATTERNS = (".xtc", ".trr", ".tpr", ".cpt", ".gro", ".edr", ".h5", ".dcd", ".nc")
SUMMARY_LIMIT_BYTES = 1_000_000


def log(message: str) -> None:
    print("[desktop] {}".format(message), flush=True)


def human_bytes(size: int) -> str:
    for unit in ("B", "kB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return "{:.1f} {}".format(size, unit)
        size /= 1024.0
    return "{} B".format(size)


class Runner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.task_path = os.path.abspath(args.task_file)
        self.repo = os.path.abspath(args.repo)
        self.task = task_contract.load_task(self.task_path, strict=False)
        self.task_id = self.task.get("task_id") or "adhoc"
        self.workdir = os.path.abspath(os.path.join(os.path.expanduser(args.workdir_root), self.task_id))
        self.output_dir = os.path.abspath(os.path.join(self.repo, args.output_root, self.task_id))
        self.beacon = Beacon(
            topic=(self.task.get("outputs") or {}).get("ntfy_topic") or task_contract.DEFAULT_TOPIC,
            dry_run=args.no_notify,
        )
        self.agent: Optional[subprocess.Popen] = None
        self.result: Dict[str, Any] = {}

    # -- helpers ----------------------------------------------------------
    def write_task(self) -> None:
        task_contract.dump_task(self.task, self.task_path)

    def fail(self, message: str, detail: str = "") -> int:
        task_contract.set_status(
            self.task,
            task_contract.STATUS_FAILED,
            note=message[:200],
            strict_transition=False,
        )
        self.task["error"] = {
            "message": message[:1000],
            "detail": detail[-4000:],
            "at": task_contract.beijing_iso(),
            "host": task_contract.local_hostname(),
        }
        self.write_task()
        self.beacon.send_event(
            "error",
            "台式机任务失败：{}".format((self.task.get("peptide") or {}).get("name", self.task_id)),
            [message[:300], "任务: {}".format(self.task_id)],
            title="[CGMD] 任务失败",
        )
        self.result = {"ok": False, "task_id": self.task_id, "status": self.task["status"],
                       "message": message}
        return 2

    def start_agent(self) -> None:
        if self.args.no_notify:
            return
        log_path = os.path.join(self.workdir, "prod.log")
        script = os.path.join(self.repo, "code", "federation", "node_agent.py")
        command = [
            sys.executable if self.args.python else "python3",
            script,
            "watch",
            "--log", log_path,
            "--task", self.task_path,
            "--topic", self.beacon.topic,
            "--progress-every", str(self.args.progress_every),
            "--forever",
        ]
        env = dict(os.environ)
        env.setdefault("PYTHONPATH", self.repo)
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            self.agent = subprocess.Popen(  # noqa: S603 - fixed command list
                command,
                cwd=self.repo,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            log("node_agent started (pid {})".format(self.agent.pid))
        except OSError as exc:
            log("warning: could not start node_agent: {}".format(exc))
            self.agent = None

    def stop_agent(self) -> None:
        if not self.agent:
            return
        try:
            if self.agent.poll() is None:
                os.killpg(os.getpgid(self.agent.pid), signal.SIGTERM)
                try:
                    self.agent.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(os.getpgid(self.agent.pid), signal.SIGKILL)
            log("node_agent stopped")
        except (OSError, ProcessLookupError):
            pass
        self.agent = None

    def prune(self) -> Dict[str, Any]:
        """Delete heavy MD artefacts inside the repository (defensive)."""
        removed: List[str] = []
        freed = 0
        for root, dirs, files in os.walk(self.output_dir):
            dirs[:] = [name for name in dirs if name not in (".git",)]
            for name in files:
                if name.lower().endswith(HEAVY_PATTERNS):
                    path = os.path.join(root, name)
                    try:
                        size = os.path.getsize(path)
                        os.remove(path)
                        freed += size
                        removed.append(os.path.relpath(path, self.repo))
                    except OSError:
                        continue
        if self.args.prune_raw and os.path.isdir(self.workdir):
            for name in os.listdir(self.workdir):
                if name.lower().endswith(HEAVY_PATTERNS):
                    path = os.path.join(self.workdir, name)
                    try:
                        size = os.path.getsize(path)
                        if size > self.args.prune_threshold_mb * 1024 * 1024:
                            os.remove(path)
                            freed += size
                            removed.append(os.path.relpath(path, self.repo))
                    except OSError:
                        continue
        return {"removed": removed, "freed_bytes": freed, "freed_human": human_bytes(freed)}

    def enforce_size(self) -> Dict[str, Any]:
        summary = os.path.join(self.output_dir, "summary_metrics.json")
        size = os.path.getsize(summary) if os.path.exists(summary) else 0
        trimmed = False
        if size > SUMMARY_LIMIT_BYTES:
            with open(summary, "r", encoding="utf-8") as handle:
                metrics = json.load(handle)
            timeseries = metrics.get("timeseries") or {}
            for key in list(timeseries):
                series = timeseries[key]
                if isinstance(series, list) and len(series) > 100:
                    stride = len(series) // 100 + 1
                    timeseries[key] = series[::stride]
            metrics["timeseries"] = timeseries
            metrics.setdefault("notes", []).append("timeseries decimated to keep summary_metrics.json < 1 MB")
            with open(summary, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(metrics, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            size = os.path.getsize(summary)
            trimmed = True
        return {"summary_bytes": size, "trimmed": trimmed, "limit_bytes": SUMMARY_LIMIT_BYTES}

    # -- main -------------------------------------------------------------
    def run(self) -> int:
        if not self.args.force and not task_contract.is_claimable(self.task, stale_seconds=self.args.stale_seconds):
            log("task {} is not claimable (status={})".format(self.task_id, self.task.get("status")))
            self.result = {"ok": True, "skipped": True, "task_id": self.task_id,
                           "status": self.task.get("status"), "message": "nothing to do"}
            return 0

        log("claiming {} ({})".format(self.task_id, task_contract.summarise(self.task)))
        task_contract.claim_task(self.task, owner="cgmd-desktop-hub")
        self.write_task()
        task_contract.set_status(self.task, task_contract.RUNNING, note="pipeline started")
        self.task["started_at"] = task_contract.beijing_iso()
        self.write_task()

        peptide = self.task.get("peptide") or {}
        membrane = self.task.get("membrane") or {}
        self.beacon.send_event(
            "start",
            "台式机已接管任务：{}".format(peptide.get("name", self.task_id)),
            [
                "序列: {}".format(peptide.get("sequence")),
                "膜: {} {}".format(
                    ":".join(membrane.get("lipids", {}).keys()),
                    ":".join(str(int(v)) for v in (membrane.get("lipids") or {}).values()),
                ),
                "生产: {} ns @ GPU {}".format((self.task.get("simulation") or {}).get("production_ns"),
                                              (self.task.get("simulation") or {}).get("gpu_id", 0)),
                "任务: {}".format(self.task_id),
            ],
            title="[CGMD] 台式机开始计算",
        )

        os.makedirs(self.workdir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
        task_snapshot = os.path.join(self.workdir, "task.json")
        with open(task_snapshot, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(self.task, handle, ensure_ascii=False, indent=2)

        started = time.time()
        try:
            from cgmd.config import config_from_task  # noqa: WPS433 - local import by design
            from cgmd.pipeline import Pipeline, PipelineError

            cfg = config_from_task(self.task, self.workdir)
            cfg.max_frames = int(self.args.max_frames)
            cfg.resume = not self.args.no_resume
            if self.args.dry_run:
                cfg.dry_run = True
            if self.args.gpu_id is not None:
                cfg.gpu_id = int(self.args.gpu_id)
            self.start_agent()
            pipeline = Pipeline(cfg, output_dir=self.output_dir, logger=log)
            metrics = pipeline.run()
        except Exception as exc:  # noqa: BLE001 - everything must be reported
            detail = ""
            try:
                detail = str(exc)
            except Exception:  # pragma: no cover
                pass
            self.stop_agent()
            return self.fail("{}: {}".format(type(exc).__name__, detail))
        finally:
            self.stop_agent()

        walltime = time.time() - started
        prune = self.prune()
        size_report = self.enforce_size()

        summary_path = os.path.join(self.output_dir, "summary_metrics.json")
        rel_summary = os.path.relpath(summary_path, self.repo)
        figures = metrics.get("figures") or []
        output_rel = os.path.relpath(self.output_dir, self.repo).replace(os.sep, "/")
        rel_figures = []
        for path in figures:
            if os.path.isabs(path):
                rel_figures.append(os.path.relpath(path, self.repo).replace(os.sep, "/"))
            else:
                rel_figures.append("{}/{}".format(output_rel, path.replace(os.sep, "/")))
        diverged = bool((metrics.get("simulation") or {}).get("diverged"))

        task_contract.set_status(
            self.task,
            task_contract.STATUS_DONE,
            note="diverged during production" if diverged else "finished on desktop",
            strict_transition=False,
        )
        self.task["finished_at"] = task_contract.beijing_iso()
        self.task["walltime_s"] = round(walltime, 1)
        self.task["runtime"] = {
            "host": task_contract.local_hostname(),
            "python": sys.version.split()[0],
            "workdir": self.workdir,
            "pruned": prune,
            "summary": size_report,
        }
        self.task["result"] = task_contract.reduced_result(
            self.task,
            metrics,
            metrics_path=rel_summary,
            figures=rel_figures,
            notes=metrics.get("notes") or [],
        )
        if diverged:
            self.task["result"]["notes"].append("production diverged: {}".format(
                (metrics.get("simulation") or {}).get("divergence_reason")))
        self.write_task()

        result_mirror = os.path.join(self.repo, task_contract.RESULT_PATH)
        os.makedirs(os.path.dirname(result_mirror), exist_ok=True)
        with open(result_mirror, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(self.task["result"], handle, ensure_ascii=False, indent=2)
            handle.write("\n")

        headline = self.task["result"].get("headline", {})
        self.beacon.send_event(
            "done" if not diverged else "error",
            "{}：{}".format("模拟完成" if not diverged else "模拟发散", peptide.get("name", self.task_id)),
            [
                "嵌膜深度: {} nm".format(headline.get("z_distance_nm")),
                "脂序参数: {}".format(headline.get("lipid_order_mean")),
                "水孔: {}".format("形成" if headline.get("pore_formed") else "未形成"),
                "速度: {} ns/day".format(headline.get("ns_per_day")),
                "耗时: {:.1f} min".format(walltime / 60.0),
                "结果: {}".format(rel_summary),
            ],
            title="[CGMD] 台式机完成",
        )

        log("done: {} ({:.1f} min)".format(rel_summary, walltime / 60.0))
        self.result = {
            "ok": True,
            "task_id": self.task_id,
            "status": self.task["status"],
            "summary": rel_summary,
            "figures": rel_figures,
            "headline": headline,
            "walltime_s": round(walltime, 1),
            "pruned": prune,
            "summary_size": size_report,
            "diverged": diverged,
        }
        return 3 if diverged else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="desktop_runner.py",
        description="Execute one CGMD task on the desktop GPU (run inside WSL2)",
    )
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="claim and execute the task in the task file")
    p_run.add_argument("--task-file", dest="task_file", default=task_contract.TASK_PATH)
    p_run.add_argument("--repo", default=_REPO_ROOT)
    p_run.add_argument("--workdir-root", dest="workdir_root", default="~/cgmd-runs")
    p_run.add_argument("--output-root", dest="output_root", default=os.path.join("results", "cgmd"))
    p_run.add_argument("--gpu-id", dest="gpu_id", type=int, default=None)
    p_run.add_argument("--max-frames", dest="max_frames", type=int, default=400)
    p_run.add_argument("--progress-every", dest="progress_every", type=float, default=900.0)
    p_run.add_argument("--stale-seconds", dest="stale_seconds", type=int, default=6 * 3600)
    p_run.add_argument("--prune-raw", dest="prune_raw", action="store_true")
    p_run.add_argument("--prune-threshold-mb", dest="prune_threshold_mb", type=float, default=5.0)
    p_run.add_argument("--no-notify", dest="no_notify", action="store_true")
    p_run.add_argument("--no-resume", dest="no_resume", action="store_true")
    p_run.add_argument("--force", action="store_true", help="run even if the task is not pending")
    p_run.add_argument("--python", default=None, help="python interpreter override")
    p_run.add_argument("--dry-run", dest="dry_run", action="store_true",
                       help="walk the pipeline without GROMACS (smoke test)")
    p_run.set_defaults(func=_cmd_run)

    p_show = sub.add_parser("show", help="print the current task summary")
    p_show.add_argument("--task-file", dest="task_file", default=task_contract.TASK_PATH)
    p_show.set_defaults(func=_cmd_show)

    p_clear = sub.add_parser("reset", help="reset a finished task back to idle")
    p_clear.add_argument("--task-file", dest="task_file", default=task_contract.TASK_PATH)
    p_clear.add_argument("--status", default=task_contract.IDLE)
    p_clear.set_defaults(func=_cmd_reset)
    return parser


def _cmd_run(args: argparse.Namespace) -> int:
    runner = Runner(args)
    try:
        code = runner.run()
    except Exception as exc:  # noqa: BLE001
        runner.result = {"ok": False, "message": "{}: {}".format(type(exc).__name__, exc)}
        code = 2
    print(json.dumps(runner.result, ensure_ascii=False))
    return code


def _cmd_show(args: argparse.Namespace) -> int:
    task = task_contract.load_task(args.task_file, strict=False)
    print(task_contract.summarise(task))
    print(json.dumps(
        {
            "status": task.get("status"),
            "updated_at": task.get("updated_at"),
            "attempts": task.get("attempts"),
            "result": task.get("result", {}).get("headline") if isinstance(task.get("result"), dict) else None,
        },
        ensure_ascii=False, indent=2,
    ))
    return 0


def _cmd_reset(args: argparse.Namespace) -> int:
    task = task_contract.load_task(args.task_file, strict=False)
    task_contract.set_status(task, args.status, note="reset by operator", strict_transition=False)
    task["result"] = None
    task.pop("error", None)
    task_contract.dump_task(task, args.task_file)
    print("reset {} -> {}".format(task.get("task_id"), args.status))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    return int(args.func(args) or 0)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
