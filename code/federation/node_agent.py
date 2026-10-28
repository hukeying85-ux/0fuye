#!/usr/bin/env python3
"""Zero-token local watchdog that pushes live GROMACS progress to the phone.

This is the bridge between the GPU workstation and the already configured
Xiaomi push channel:

    ntfy.sh topic  : arena-beacon-95bc796a66
    transport      : HTTPS POST (JSON body), priority 5 -> popup + vibration
    payload        : UTF-8 JSON, Beijing time (Asia/Shanghai) in every message
    cost           : zero tokens, zero API keys -- no LLM is involved

What it watches
---------------
* ``prod.log`` (GROMACS): ``ns/day`` speed, completed step percentage,
  remaining ETA, LINCS warnings and blow-up / NaN divergence detection;
* ``cgmd_task.json`` (hub contract): start / completion / failure transitions.

Modes
-----
``watch``   follow a running ``prod.log`` and beacon every milestone
``task``    follow the task file written by the desktop hub poller
``once``    parse a finished log and push a single report
``test``    send a self-test notification (use this to verify the phone)
``demo``    offline, simulated 1 us run -- no GROMACS needed

Examples
--------
Verify the phone link::

    python3 code/federation/node_agent.py test

Follow a production run (this is what the desktop hub starts for you)::

    python3 code/federation/node_agent.py watch \
        --log /data/cgmd-runs/<task>/prod.log \
        --task results/status/cgmd_task.json \
        --progress-every 900

Run forever, picking up whatever the desktop hub is currently executing::

    python3 code/federation/node_agent.py task --poll 5
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from typing import Any, Dict, List, Optional

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core import gmx_log, task_contract  # noqa: E402
from core.ntfy_beacon import Beacon, format_message  # noqa: E402

DEFAULT_TOPIC = os.environ.get("CGMD_NTFY_TOPIC", "arena-beacon-95bc796a66")
DEFAULT_STATE = os.path.join(_REPO_ROOT, "skills", "cgmd-hub", "state", "beacon_state.json")

EXIT_HEALTHY = 0
EXIT_DIVERGED = 3


def _log(message: str) -> None:
    stamp = time.strftime("%H:%M:%S")
    print("[{}] {}".format(stamp, message), flush=True)


def load_state(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def save_state(path: str, state: Dict[str, Any]) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, path)


def _task_context(task_path: Optional[str]) -> Dict[str, Any]:
    """Pull the peptide/system description out of a task document."""
    if not task_path:
        return {}
    try:
        task = task_contract.load_task(task_path, strict=False)
    except Exception as exc:  # noqa: BLE001 - never break the watchdog
        _log("task context unavailable: {}".format(exc))
        return {}
    peptide = task.get("peptide") or {}
    membrane = task.get("membrane") or {}
    return {
        "task_id": task.get("task_id"),
        "peptide": peptide.get("name"),
        "sequence": peptide.get("sequence"),
        "lipids": ":".join(membrane.get("lipids", {}).keys()),
        "ratio": ":".join(str(int(v)) for v in (membrane.get("lipids") or {}).values()),
        "production_ns": (task.get("simulation") or {}).get("production_ns"),
    }


def context_lines(context: Dict[str, Any]) -> List[str]:
    if not context:
        return []
    lines = []
    if context.get("peptide"):
        lines.append("肽: {} ({} aa)".format(context["peptide"], len(context.get("sequence") or "")))
    if context.get("lipids"):
        lines.append("膜: {} {}".format(context["lipids"], context.get("ratio") or ""))
    if context.get("production_ns"):
        lines.append("计划: {} ns".format(context["production_ns"]))
    if context.get("task_id"):
        lines.append("任务: {}".format(context["task_id"]))
    return lines


def progress_lines(state: gmx_log.LogState) -> List[str]:
    progress = state.progress
    percent = "{:.1f}%".format(progress * 100.0) if progress is not None else "?"
    speed = "{:.2f} ns/day".format(state.ns_per_day) if state.ns_per_day else "n/a"
    eta = gmx_log.format_hours(state.eta_seconds) or "n/a"
    lines = [
        "进度: {} ({} / {} ns)".format(percent, round(state.simulated_ns, 2), state.total_ns_resolved or "?"),
        "速度: {}".format(speed),
        "剩余: {}".format(eta),
    ]
    if state.lincs_warnings:
        lines.append("LINCS 警告: {}".format(state.lincs_warnings))
    return lines


class Watchdog:
    """Translates log/task transitions into phone notifications."""

    def __init__(
        self,
        beacon: Beacon,
        task_path: Optional[str] = None,
        state_path: Optional[str] = None,
        progress_every: float = 900.0,
        min_interval: float = 1.0,
        milestone_percent: float = 10.0,
    ) -> None:
        self.beacon = beacon
        self.state_path = state_path or DEFAULT_STATE
        self.state = load_state(str(self.state_path))
        self.progress_every = float(progress_every)
        self.min_interval = float(min_interval)
        self.milestone_percent = float(milestone_percent)
        self.context = _task_context(task_path)
        self.last_sent = 0.0
        self.last_status = self.state.get("last_status")
        self.last_milestone = float(self.state.get("last_milestone") or 0.0)
        self.started = False
        self.finished = False
        self.diverged = False

    # -- helpers ----------------------------------------------------------
    def _remember(self, status: str) -> None:
        self.state.update(
            {
                "last_status": status,
                "last_sent_at": task_contract.beijing_iso(),
                "peptide": self.context.get("peptide"),
                "task_id": self.context.get("task_id"),
            }
        )
        save_state(str(self.state_path), self.state)

    def _push(self, event: str, title: str, headline: str, lines: Optional[List[str]] = None) -> bool:
        body = format_message(headline, (lines or []) + context_lines(self.context), event=event)
        ok = self.beacon.send(title, body, event=event)
        self.last_sent = time.time()
        self._remember(event)
        _log("ntfy {} -> {} | {}".format("ok" if ok else "FAILED", title, headline))
        return ok

    # -- events -----------------------------------------------------------
    def on_started(self, state: gmx_log.LogState) -> None:
        self.started = True
        self._push(
            "start",
            "[CGMD] 模拟启动",
            "台式机 GPU 生产模拟已启动",
            progress_lines(state),
        )

    def on_progress(self, state: gmx_log.LogState) -> None:
        self._push(
            "progress",
            "[CGMD] 进度 {:.0f}%".format((state.progress or 0.0) * 100.0),
            "生产模拟进行中",
            progress_lines(state),
        )

    def on_finished(self, state: gmx_log.LogState) -> None:
        self.finished = True
        self._push(
            "done",
            "[CGMD] 模拟完成",
            "生产模拟正常结束",
            progress_lines(state),
        )

    def on_diverged(self, state: gmx_log.LogState) -> None:
        self.diverged = True
        lines = progress_lines(state)
        lines.append("异常: {}".format(state.divergence or "unknown"))
        if state.errors:
            lines.append("日志: {}".format(state.errors[-1][:120]))
        if state.warnings:
            lines.append("LINCS: {}".format(state.warnings[-1][:120]))
        self._push("error", "[CGMD] 模拟发散", "体系爆炸 / LINCS 失败，已停止等待", lines)

    # -- main loop --------------------------------------------------------
    def poll(self, log_path: str) -> None:
        watcher = gmx_log.LogWatcher(log_path)
        while True:
            state = watcher.poll()
            now = time.time()
            if state.is_diverged and not self.diverged:
                self.on_diverged(state)
                return
            if state.finished and self.started and not self.finished:
                self.on_finished(state)
                self.finished = True
                return
            if state.started and not self.started and (state.step > 0 or state.time_ps > 0):
                self.on_started(state)
            elif self.started and not state.finished:
                progress = (state.progress or 0.0) * 100.0
                if progress >= self.last_milestone + self.milestone_percent:
                    self.last_milestone = progress - (progress % self.milestone_percent)
                    self.state["last_milestone"] = self.last_milestone
                    self.on_progress(state)
                elif now - self.last_sent >= self.progress_every:
                    self.on_progress(state)
            time.sleep(1.0)


# ---------------------------------------------------------------------------
# modes
# ---------------------------------------------------------------------------
def mode_watch(args: argparse.Namespace) -> int:
    beacon = Beacon(topic=args.topic, server=args.server, dry_run=args.dry_run)
    log_path = args.log
    watchdog = Watchdog(
        beacon,
        task_path=args.task,
        state_path=args.state,
        progress_every=args.progress_every,
        milestone_percent=args.milestone,
    )
    _log("watching {} (topic {})".format(log_path, args.topic))
    deadline = time.time() + args.timeout if args.timeout else None
    watcher = gmx_log.LogWatcher(log_path)
    while True:
        state = watcher.poll()
        if state.is_diverged and not watchdog.diverged:
            watchdog.on_diverged(state)
            return EXIT_DIVERGED
        if state.finished and watchdog.started and not watchdog.finished:
            watchdog.on_finished(state)
            return EXIT_HEALTHY
        if state.started and not watchdog.started and (state.step > 0 or state.time_ps > 0):
            watchdog.on_started(state)
        elif watchdog.started and not state.finished:
            progress = (state.progress or 0.0) * 100.0
            if progress >= watchdog.last_milestone + watchdog.milestone_percent:
                watchdog.last_milestone = progress - (progress % watchdog.milestone_percent)
                watchdog.state["last_milestone"] = watchdog.last_milestone
                watchdog.on_progress(state)
            elif time.time() - watchdog.last_sent >= watchdog.progress_every:
                watchdog.on_progress(state)
        if deadline and time.time() > deadline:
            _log("timeout reached ({} s)".format(args.timeout))
            return EXIT_HEALTHY
        if not os.path.exists(log_path) and deadline is None and not args.forever:
            _log("log disappears; exiting")
            return EXIT_HEALTHY
        time.sleep(1.0)


def mode_task(args: argparse.Namespace) -> int:
    """Follow the hub task file and mirror status transitions to the phone."""
    beacon = Beacon(topic=args.topic, server=args.server, dry_run=args.dry_run)
    seen: Dict[str, str] = {}
    _log("following task file {} every {} s".format(args.task_file, args.poll))
    while True:
        try:
            task = task_contract.load_task(args.task_file, strict=False)
        except Exception as exc:  # noqa: BLE001
            _log("cannot read task file: {}".format(exc))
            time.sleep(args.poll)
            continue
        status = str(task.get("status"))
        task_id = str(task.get("task_id"))
        if seen.get(task_id) != status:
            seen[task_id] = status
            peptide = (task.get("peptide") or {}).get("name", "?")
            if status == task_contract.RUNNING:
                beacon.send_event("start", "任务开始执行：{}".format(peptide),
                                  [task_contract.summarise(task)], title="[CGMD] 任务开始")
            elif status == task_contract.STATUS_DONE:
                result = task.get("result") or {}
                headline = result.get("headline") or {}
                beacon.send_event("done", "任务完成：{}".format(peptide), [
                    "嵌膜深度: {} nm".format(headline.get("z_distance_nm")),
                    "脂序参数: {}".format(headline.get("lipid_order_mean")),
                    "水孔: {}".format("形成" if headline.get("pore_formed") else "未形成"),
                    "速度: {} ns/day".format(headline.get("ns_per_day")),
                ], title="[CGMD] 任务完成")
            elif status == task_contract.STATUS_FAILED:
                beacon.send_event("error", "任务失败：{}".format(peptide), [
                    (task.get("error") or {}).get("message", "")[:300],
                ], title="[CGMD] 任务失败")
        if not args.forever:
            time.sleep(args.poll)
            continue
        time.sleep(args.poll)
    return EXIT_HEALTHY


def mode_once(args: argparse.Namespace) -> int:
    beacon = Beacon(topic=args.topic, server=args.server, dry_run=args.dry_run)
    try:
        with open(args.log, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError as exc:
        _log("cannot read log: {}".format(exc))
        return EXIT_HEALTHY
    state = gmx_log.parse_log_text(text, source=args.log)
    context = _task_context(args.task)
    lines = progress_lines(state) + context_lines(context)
    event = "error" if state.is_diverged else "done"
    headline = "日志报告：{}".format("发散" if state.is_diverged else "正常/未知")
    ok = beacon.send("[CGMD] log report", format_message(headline, lines, event=event), event=event)
    print(json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
    return EXIT_HEALTHY if ok else 1


def mode_test(args: argparse.Namespace) -> int:
    beacon = Beacon(topic=args.topic, server=args.server, dry_run=args.dry_run)
    ok = beacon.ping()
    return EXIT_HEALTHY if ok else 1


def mode_demo(args: argparse.Namespace) -> int:
    """Offline demo: replay a synthetic 200 ns run into the beacon."""
    beacon = Beacon(topic=args.topic, server=args.server, dry_run=args.dry_run)
    _log("demo: simulating a run (no GROMACS required)")
    state = gmx_log.LogState(source="demo", total_ns=200.0, dt_ps=0.02, total_steps=10_000_000)
    state.started = True
    clock = [
        "Started mdrun on rank 0",
        "   nsteps = 10000000",
        "   dt = 0.02",
        "Step           Time",
        "       0        0.00000",
        "  100000     2000.00000",
        "Performance:       1200.000        0.072",
    ]
    for line in clock:
        gmx_log.parse_line(line, state)
    Watchdog(beacon, state_path=args.state).on_started(state)
    state.step, state.time_ps = 6_000_000, 120_000.0
    state.ns_per_day = 1250.0
    Watchdog(beacon, state_path=args.state).on_progress(state)
    if args.diverge:
        state.divergence = "lincs"
        state.warnings.append("Step 6123456: LINCS WARNING relative constraint deviation 0.53")
        Watchdog(beacon, state_path=args.state).on_diverged(state)
        return EXIT_DIVERGED
    state.step, state.time_ps, state.finished = 10_000_000, 200_000.0, True
    Watchdog(beacon, state_path=args.state).on_finished(state)
    return EXIT_HEALTHY


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="node_agent.py",
        description="Zero-token GROMACS -> phone beacon for the CGMD desktop hub",
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    def common(p: argparse.ArgumentParser, with_log: bool = False) -> None:
        p.add_argument("--topic", default=DEFAULT_TOPIC)
        p.add_argument("--server", default="https://ntfy.sh")
        p.add_argument("--dry-run", action="store_true", help="print instead of pushing")
        p.add_argument("--task", default=None, help="task JSON for context")
        p.add_argument("--state", default=DEFAULT_STATE)
        if with_log:
            p.add_argument("--log", default=None, help="path to prod.log")

    p_watch = sub.add_parser("watch", help="follow a running prod.log")
    common(p_watch, with_log=True)
    p_watch.add_argument("--progress-every", dest="progress_every", type=float, default=900.0,
                         help="seconds between progress pushes")
    p_watch.add_argument("--milestone", type=float, default=10.0, help="percent step for milestone pushes")
    p_watch.add_argument("--timeout", type=float, default=0.0, help="stop after N seconds (0 = never)")
    p_watch.add_argument("--forever", action="store_true")
    p_watch.set_defaults(func=mode_watch)

    p_task = sub.add_parser("task", help="follow the hub task file")
    common(p_task)
    p_task.add_argument("--task-file", dest="task_file", default=task_contract.TASK_PATH)
    p_task.add_argument("--poll", type=float, default=5.0)
    p_task.add_argument("--forever", action="store_true")
    p_task.set_defaults(func=mode_task)

    p_once = sub.add_parser("once", help="parse a finished log and push one report")
    common(p_once, with_log=True)
    p_once.set_defaults(func=mode_once)

    p_test = sub.add_parser("test", help="send a self-test notification")
    common(p_test)
    p_test.set_defaults(func=mode_test)

    p_demo = sub.add_parser("demo", help="offline demo of the beacon sequence")
    common(p_demo)
    p_demo.add_argument("--diverge", action="store_true", help="demo the divergence alert instead")
    p_demo.set_defaults(func=mode_demo)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    args = build_parser().parse_args(argv)
    if getattr(args, "mode", "") == "watch" and not args.log:
        print("watch requires --log", file=sys.stderr)
        return 2
    if getattr(args, "mode", "") == "once" and not args.log:
        print("once requires --log", file=sys.stderr)
        return 2

    def _graceful(signum, _frame):  # noqa: ANN001
        _log("signal {} received, stopping".format(signum))
        raise SystemExit(EXIT_HEALTHY)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _graceful)
        except (ValueError, OSError):
            pass
    return int(args.func(args) or 0)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
