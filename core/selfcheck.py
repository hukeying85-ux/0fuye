"""Desktop self-check contract (``cgmd.selfcheck.v1``) and request file.

The Windows workstation writes ``results/status/desktop_selfcheck.json`` from
``skills/cgmd-hub/runner/Test-CgmdHub.ps1``.  Any other client (Arena agent,
laptop, phone) can read it out of git, and can ask the desktop for a fresh run
by committing ``results/status/selfcheck_request.json``.

CLI
---
    python3 -m core.selfcheck show   results/status/desktop_selfcheck.json
    python3 -m core.selfcheck check  results/status/desktop_selfcheck.json
    python3 -m core.selfcheck request --note "why" [--desk] --write
    python3 -m core.selfcheck status --write
    python3 -m core.selfcheck heartbeat
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta

__all__ = [
    "REPORT_SCHEMA",
    "REQUEST_SCHEMA",
    "CHECK_IDS",
    "STATUSES",
    "REPORT_PATH",
    "HEARTBEAT_SCHEMA",
    "HEARTBEAT_PATH",
    "heartbeat_age_minutes",
    "validate_heartbeat",
    "REQUEST_PATH",
    "CheckError",
    "beijing_iso",
    "new_request",
    "validate_request",
    "validate_report",
    "verdict",
    "summarise",
    "format_table",
    "load",
    "dump",
]

REPORT_SCHEMA = "cgmd.selfcheck.v1"
REQUEST_SCHEMA = "cgmd.selfcheck.request.v1"

REPORT_PATH = "results/status/desktop_selfcheck.json"
HEARTBEAT_SCHEMA = "cgmd.heartbeat.v1"
HEARTBEAT_PATH = "results/status/hub_heartbeat.json"
REQUEST_PATH = "results/status/selfcheck_request.json"

CHECK_IDS = (
    "repo",
    "origin",
    "branch",
    "creds",
    "wsl",
    "gpu",
    "gromacs",
    "martini3",
    "python",
    "tools",
    "disk",
    "launcher",
    "task",
    "beacon",
    "desk-src",
    "desk-app",
    "desk-http",
    "gmxrun",
)

STATUSES = ("pass", "warn", "fail")

BEIJING = timezone(timedelta(hours=8))


class CheckError(RuntimeError):
    """Raised when a report or a request document is malformed."""


def beijing_iso() -> str:
    return datetime.now(BEIJING).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# request document
# ---------------------------------------------------------------------------
def new_request(
    note: str = "",
    requested_by: str = "arena-agent",
    desk: bool = False,
    smoke: bool = False,
) -> dict:
    """A request asks the desktop to refresh itself on its next poll.

    ``desk=True`` also redeploys Arena Desk (``code/panel/deploy.ps1``) through
    ``Sync-Desktop.ps1 -Desk``; otherwise only ``Test-CgmdHub.ps1`` runs.
    """
    request = {
        "schema": REQUEST_SCHEMA,
        "requested_at": beijing_iso(),
        "requested_by": requested_by,
        "note": note,
        "desk": bool(desk),
        "smoke": bool(smoke),
    }
    if smoke:
        request["how"] = (
            "the desktop hub runs `python3 -m cgmd.smoke --ps 100` inside WSL2 on "
            "its next poll, publishes results/status/gmx_smoke.json (GROMACS "
            "version + software inventory + 100 ps integration) and deletes this file"
        )
    elif desk:
        request["how"] = (
            "the desktop hub runs Sync-Desktop.ps1 -Desk on its next poll: git "
            "reset to the branch tip, redeploy Arena Desk, run the 17-point "
            "self-check, push results/status/desktop_sync.json + "
            "desktop_selfcheck.json, then delete this file"
        )
    else:
        request["how"] = (
            "the desktop hub runs Test-CgmdHub.ps1 on its next poll, publishes "
            "results/status/desktop_selfcheck.json and deletes this file"
        )
    return request


def validate_request(request: dict) -> list:
    problems = []
    if not isinstance(request, dict):
        return ["request must be a JSON object"]
    if request.get("schema") != REQUEST_SCHEMA:
        problems.append("schema must be {}".format(REQUEST_SCHEMA))
    stamp = request.get("requested_at")
    if not isinstance(stamp, str) or "T" not in stamp:
        problems.append("requested_at must be an ISO-8601 timestamp with a T separator")
    if "requested_by" not in request:
        problems.append("requested_by is required")
    for flag in ("desk", "smoke"):
        if flag in request and not isinstance(request[flag], bool):
            problems.append(flag + " must be a boolean when present")
    return problems


# ---------------------------------------------------------------------------
# heart-beat document (written by the poller, at most once per hour)
# ---------------------------------------------------------------------------
def heartbeat_age_minutes(document: dict) -> float:
    """Minutes since the workstation last polled; negative-ish on clock skew."""
    stamp = document.get("at")
    if not isinstance(stamp, str):
        raise CheckError("heart-beat has no 'at' timestamp")
    moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=BEIJING)
    return (datetime.now(timezone.utc) - moment.astimezone(timezone.utc)).total_seconds() / 60.0


def validate_heartbeat(document: dict) -> list:
    problems = []
    if not isinstance(document, dict):
        return ["heart-beat must be a JSON object"]
    if document.get("schema") != HEARTBEAT_SCHEMA:
        problems.append("schema must be {}".format(HEARTBEAT_SCHEMA))
    for key in ("at", "host", "branch"):
        if not isinstance(document.get(key), str) or not document.get(key):
            problems.append(key + " is required")
    interval = document.get("interval_s")
    if interval is not None and not isinstance(interval, int):
        problems.append("interval_s must be an integer")
    return problems


# ---------------------------------------------------------------------------
# report document
# ---------------------------------------------------------------------------
def validate_report(report: dict) -> list:
    """Return a list of human readable problems (empty list == valid)."""
    problems = []
    if not isinstance(report, dict):
        return ["report must be a JSON object"]
    if report.get("schema") != REPORT_SCHEMA:
        problems.append("schema must be {}".format(REPORT_SCHEMA))
    if report.get("overall") not in STATUSES:
        problems.append("overall must be one of {}".format(", ".join(STATUSES)))
    if not isinstance(report.get("checks"), list) or not report["checks"]:
        problems.append("checks must be a non-empty list")
        return problems

    seen = []
    for index, entry in enumerate(report["checks"]):
        where = "checks[{}]".format(index)
        if not isinstance(entry, dict):
            problems.append(where + " must be an object")
            continue
        for key in ("id", "title", "status", "detail"):
            if not isinstance(entry.get(key), str) or not entry.get(key):
                problems.append(where + "." + key + " is required")
        if entry.get("status") not in STATUSES:
            problems.append(where + ".status must be pass/warn/fail")
        if isinstance(entry.get("id"), str):
            seen.append(entry["id"])
    unknown = [name for name in seen if name not in CHECK_IDS]
    if unknown:
        problems.append("unknown check ids: {}".format(", ".join(sorted(set(unknown)))))

    summary = report.get("summary")
    if not isinstance(summary, dict):
        problems.append("summary is required")
    else:
        for key in ("passed", "warnings", "failed"):
            if not isinstance(summary.get(key), int):
                problems.append("summary.{} must be an integer".format(key))
        failed = summary.get("failed")
        warnings = summary.get("warnings")
        if isinstance(failed, int) and isinstance(warnings, int):
            expected = "pass"
            if failed > 0:
                expected = "fail"
            elif warnings > 0:
                expected = "warn"
            if report.get("overall") != expected:
                problems.append(
                    "overall must be {} for {} failure(s) and {} warning(s)".format(
                        expected, failed, warnings
                    )
                )

    stamp = report.get("checked_at")
    if not isinstance(stamp, str) or "T" not in stamp:
        problems.append("checked_at must be an ISO-8601 timestamp with a T separator")
    return problems


def verdict(report: dict) -> dict:
    """Reduce a report to the facts another client cares about."""
    summary = report.get("summary") or {}
    failing = [
        {"id": entry.get("id"), "detail": entry.get("detail")}
        for entry in report.get("checks", [])
        if entry.get("status") == "fail"
    ]
    warning = [
        {"id": entry.get("id"), "detail": entry.get("detail")}
        for entry in report.get("checks", [])
        if entry.get("status") == "warn"
    ]
    return {
        "overall": report.get("overall"),
        "checked_at": report.get("checked_at"),
        "host": (report.get("host") or {}).get("computer"),
        "branch": (report.get("host") or {}).get("branch"),
        # warnings (for example a tight disk) do not stop the desktop from
        # accepting a task; a single failed check does.
        "ready_for_task": not failing,
        "counts": {
            "passed": summary.get("passed", 0),
            "warnings": summary.get("warnings", 0),
            "failed": summary.get("failed", 0),
        },
        "failing": failing,
        "warnings": warning,
    }


def summarise(report: dict) -> str:
    reduced = verdict(report)
    counts = reduced["counts"]
    return "{} on {} ({}/{} checks, {} warn, {} fail) at {}".format(
        (reduced["overall"] or "unknown").upper(),
        reduced["host"] or "unknown host",
        counts["passed"],
        sum(counts.values()) or counts["passed"],
        counts["warnings"],
        counts["failed"],
        reduced["checked_at"] or "?",
    )


def format_table(report: dict) -> str:
    lines = []
    header = "{:<10} {:<24} {:<6} {}".format("ID", "CHECK", "STATUS", "DETAIL")
    lines.append(header)
    lines.append("-" * len(header))
    for entry in report.get("checks", []):
        lines.append(
            "{:<10} {:<24} {:<6} {}".format(
                str(entry.get("id", "?"))[:10],
                str(entry.get("title", ""))[:24],
                str(entry.get("status", "?"))[:6],
                entry.get("detail", ""),
            )
        )
    lines.append("")
    lines.append(summarise(report))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# io
# ---------------------------------------------------------------------------
def load(path: str) -> dict:
    if not os.path.exists(path):
        raise CheckError("file not found: {}".format(path))
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def dump(document: dict, path: str) -> str:
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return path


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------
def _cmd_check(args: argparse.Namespace) -> int:
    report = load(args.path)
    problems = validate_report(report)
    if problems:
        for problem in problems:
            print("INVALID " + problem)
        return 2
    print("OK " + summarise(report))
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    report = load(args.path)
    print(format_table(report))
    if args.json:
        print()
        print(json.dumps(verdict(report), ensure_ascii=False, indent=2))
    return 0 if verdict(report)["ready_for_task"] else 1


def _cmd_request(args: argparse.Namespace) -> int:
    request = new_request(
        note=args.note or "", requested_by=args.by, desk=bool(args.desk), smoke=bool(args.smoke)
    )
    path = args.path or REQUEST_PATH
    if args.write:
        dump(request, path)
        print("wrote " + path)
    else:
        print(json.dumps(request, ensure_ascii=False, indent=2))
    return 0


def _cmd_heartbeat(args: argparse.Namespace) -> int:
    """Prove the workstation watcher is alive, or say how stale it is."""
    path = args.path or HEARTBEAT_PATH
    if not os.path.exists(path):
        print("NO HEART-BEAT yet - the workstation poller has never published one")
        print("  on the desktop: powershell -NoProfile -ExecutionPolicy Bypass -File "
              "C:\\cgmd\\0fuye\\skills\\cgmd-hub\\runner\\Invoke-CgmdPoll.ps1 -Force")
        return 1
    document = load(path)
    problems = validate_heartbeat(document)
    if problems:
        print("INVALID " + "; ".join(problems))
        return 2
    age = heartbeat_age_minutes(document)
    interval = int(document.get("interval_s") or 60)
    limit = args.max_age if args.max_age else max(interval * 2, 5)
    state = "ALIVE" if age <= limit else "STALE"
    print("{}: {} | host {} | branch {} | head {} | state {} | {:.0f} min ago (limit {:.0f})".format(
        state, document.get("at"), document.get("host"), document.get("branch"),
        document.get("head", "?"), document.get("state", "?"), age, limit))
    if document.get("task_id"):
        print("  last task: {}".format(document.get("task_id")))
    return 0 if state == "ALIVE" else 1


def _cmd_status(args: argparse.Namespace) -> int:
    """One-line answer to the question: can the desktop take a task right now?"""
    report_path = args.path or REPORT_PATH
    if not os.path.exists(report_path):
        print("NO REPORT yet - the desktop has never published a self-check "
              "(queue one with: python3 -m core.selfcheck request --write)")
        return 1
    report = load(report_path)
    problems = validate_report(report)
    if problems:
        print("INVALID " + "; ".join(problems))
        return 2
    reduced = verdict(report)
    print(summarise(report))
    print("ready_for_task: {}".format("yes" if reduced["ready_for_task"] else "no"))
    for entry in reduced["failing"]:
        print("  FAIL {}: {}".format(entry["id"], entry["detail"]))
    for entry in reduced["warnings"]:
        print("  warn {}: {}".format(entry["id"], entry["detail"]))
    if args.write:
        out = args.out or "results/status/desktop_selfcheck_verdict.json"
        dump(reduced, out)
        print("wrote " + out)
    return 0 if reduced["ready_for_task"] else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="cgmd.selfcheck", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command")

    p_show = sub.add_parser("show", help="print the report as a table")
    p_show.add_argument("path", nargs="?", default=REPORT_PATH)
    p_show.add_argument("--json", action="store_true", help="append the reduced verdict")
    p_show.set_defaults(func=_cmd_show)

    p_check = sub.add_parser("check", help="validate the report schema")
    p_check.add_argument("path", nargs="?", default=REPORT_PATH)
    p_check.set_defaults(func=_cmd_check)

    p_request = sub.add_parser("request", help="build (or write) a self-check request")
    p_request.add_argument("--note", default="")
    p_request.add_argument("--by", default="arena-agent")
    p_request.add_argument("--path", default="")
    p_request.add_argument("--write", action="store_true")
    p_request.add_argument("--desk", action="store_true", help="also redeploy Arena Desk")
    p_request.add_argument("--smoke", action="store_true", help="run the 100 ps GROMACS smoke test")
    p_request.set_defaults(func=_cmd_request)

    p_beat = sub.add_parser("heartbeat", help="is the workstation watcher alive?")
    p_beat.add_argument("--path", default="")
    p_beat.add_argument("--max-age", dest="max_age", type=float, default=0.0,
                        help="minutes before the beat counts as stale")
    p_beat.set_defaults(func=_cmd_heartbeat)

    p_status = sub.add_parser("status", help="is the desktop ready for a task?")
    p_status.add_argument("--path", default="")
    p_status.add_argument("--write", action="store_true")
    p_status.add_argument("--out", default="")
    p_status.set_defaults(func=_cmd_status)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
