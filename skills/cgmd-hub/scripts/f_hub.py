#!/usr/bin/env python3
"""Client helpers for the fixed F-drive CGMD desktop workflow.

This module is intentionally conservative:

* it never invents a desktop capability from repository contents;
* it builds every run/result path below the fixed F: roots;
* it requires an explicit local opt-in before adding the desktop-side
  confirmation string for a mutating ``files`` action;
* it treats a mailbox timeout or a partial pipeline result as incomplete,
  never as a completed simulation.

The same file contains a small, dependency-free XVG insertion-depth
calculator for the fallback ``gmx traj`` route.  The production pipeline has
its own MDAnalysis implementation; both use the peptide bead centroid
relative to the phosphate mid-plane and minimum-image/PBC handling.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core import hub_mailbox  # noqa: E402

CONFIRM_TEXT = "CGMD_F_MIGRATION_CONFIRMED"
RUN_ROOT = r"F:\cgmd\runs"
RESULT_ROOT = r"F:\cgmd\results"
TARGET_REPO = r"F:\cgmd\0fuye"
MAGAININ2 = "GIGKFLHSAKKFGKAFVGEIMNS"
TASK_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
MUTATING_FILE_ACTIONS = {
    "migrate",
    "deploy",
    "handover_stage",
    "handover_enable",
    "handover_rollback",
}
TEXT_STAGING_SUFFIXES = {".mdp", ".ndx", ".txt", ".json"}


def validate_task_id(task_id: str) -> str:
    """Return a safe task directory name or raise ``ValueError``."""
    if not TASK_ID_RE.match(task_id or ""):
        raise ValueError("task_id must match [A-Za-z0-9_-]+")
    return task_id


def f_run_dir(task_id: str) -> str:
    return RUN_ROOT + "\\" + validate_task_id(task_id)


def f_result_dir(task_id: str) -> str:
    return RESULT_ROOT + "\\" + validate_task_id(task_id)


def build_files_args(
    action: str,
    *,
    task_id: str = "legacy-cgmd-100ns-20261030",
    source_prefix: str = "cgmd_100ns",
    branch: str = "",
    confirm_mutation: bool = False,
    copy_credentials: bool = False,
    timeout_s: int = 1800,
) -> Dict[str, Any]:
    """Build a validated ``files`` mailbox payload."""
    action = action.lower()
    allowed = MUTATING_FILE_ACTIONS | {"survey", "status"}
    if action not in allowed:
        raise ValueError("unsupported files action: %s" % action)
    validate_task_id(task_id)
    if not re.match(r"^[A-Za-z0-9_.-]+$", source_prefix or ""):
        raise ValueError("source_prefix contains unsupported characters")
    if branch and (not re.match(r"^[A-Za-z0-9_./-]+$", branch) or ".." in branch or branch.startswith("-")):
        raise ValueError("unsafe branch name")
    payload: Dict[str, Any] = {
        "action": action,
        "task_id": task_id,
        "source_prefix": source_prefix,
        "timeout_s": int(timeout_s),
    }
    if branch:
        payload["branch"] = branch
    if copy_credentials:
        payload["copy_credentials"] = True
    if action in MUTATING_FILE_ACTIONS:
        if not confirm_mutation:
            raise ValueError(
                "mutating files action %s requires --confirm-mutation" % action
            )
        payload["confirm"] = CONFIRM_TEXT
    return payload


def build_pipeline_args(
    task_id: str,
    *,
    sequence: str = MAGAININ2,
    name: str = "magainin-2",
    production_ns: float = 100.0,
    equilibration_ns: float = 10.0,
    lipids: str = "POPE:3,POPG:1",
    temperature_k: float = 310.0,
    salt_m: float = 0.15,
    maxh_hours: float = 0.5,
    segment_ns: float = 10.0,
    timeout_s: int = 5400,
    install: bool = False,
) -> Dict[str, Any]:
    """Build the exact native-pipeline payload for the fixed F: layout."""
    if not re.match(r"^[ACDEFGHIKLMNPQRSTVWY]+$", sequence or ""):
        raise ValueError("sequence must contain one-letter amino-acid codes")
    if production_ns <= 0 or equilibration_ns < 0:
        raise ValueError("production_ns must be positive and equilibration_ns non-negative")
    payload: Dict[str, Any] = {
        "sequence": sequence,
        "name": name,
        "task_id": validate_task_id(task_id),
        "production_ns": float(production_ns),
        "equilibration_ns": float(equilibration_ns),
        "lipids": lipids,
        "temperature_K": float(temperature_k),
        "salt_M": float(salt_m),
        "gpu_id": 0,
        "workdir": f_run_dir(task_id),
        "outdir": f_result_dir(task_id),
        "maxh_hours": float(maxh_hours),
        "segment_ns": float(segment_ns),
        "timeout_s": int(timeout_s),
    }
    if install:
        payload["install"] = True
    return payload


def send_and_wait(
    repo: str,
    kind: str,
    payload: Dict[str, Any],
    *,
    note: str = "",
    timeout_s: int = 1800,
    interval_s: int = 15,
) -> Dict[str, Any]:
    """Queue one mailbox job on hub/mailbox and return its actual receipt."""
    job_id = hub_mailbox.send(
        repo,
        kind,
        payload,
        note=note,
        timeout_s=timeout_s,
    )
    print("mailbox: queued %s as %s" % (kind, job_id), file=sys.stderr)
    # The desk polls once per minute and still has to publish the receipt after
    # the child exits, so the client-side wait needs a margin beyond the job's
    # own timeout; otherwise a just-in-time receipt can look like a timeout.
    return hub_mailbox.wait(
        repo, job_id, timeout=timeout_s + 600, interval=interval_s
    )


def assess_files_result(result: Dict[str, Any], action: str) -> Dict[str, Any]:
    """Summarise whether a files receipt proves the requested action."""
    detail = result.get("detail") or {}
    assessment: Dict[str, Any] = {
        "job_id": result.get("id"),
        "kind": result.get("kind"),
        "action": action,
        "status": result.get("status"),
        "summary": result.get("summary"),
        "proved": False,
    }
    if result.get("kind") != "files":
        assessment["reason"] = "receipt kind is not files"
        return assessment
    if result.get("status") == "unsupported":
        assessment["reason"] = "desktop worker does not have the files kind loaded"
        return assessment
    if action == "migrate":
        rows = detail.get("files") or []
        verified = [
            row for row in rows
            if row.get("status") in {"copied_verified", "already_verified"}
        ]
        assessment.update(
            {
                "files_seen": len(rows),
                "files_verified": len(verified),
                "receipt": detail.get("receipt"),
                "proved": bool(rows) and len(verified) == len(rows)
                and result.get("status") == "ok",
            }
        )
        return assessment
    if action == "deploy":
        deployment = detail.get("deployment") or {}
        assessment.update(
            {
                "target_repo": detail.get("target_repo"),
                "target_head": detail.get("target_head"),
                "deployment_ready": deployment.get("ready"),
                "proved": bool(deployment.get("ready"))
                and result.get("status") in {"ok", "partial"},
            }
        )
        return assessment
    if action in {"handover_stage", "handover_enable", "handover_rollback", "status"}:
        assessment["tasks_after"] = detail.get("tasks_after") or detail.get("tasks")
        assessment["script"] = detail.get("script")
        assessment["state_dir"] = detail.get("state_dir")
        assessment["proved"] = result.get("status") == "ok"
        return assessment
    assessment["proved"] = result.get("status") == "ok"
    return assessment


def assess_pipeline_result(
    result: Dict[str, Any],
    *,
    expected_ns: float = 100.0,
    dt_ps: float = 0.02,
) -> Dict[str, Any]:
    """Decide whether a pipeline receipt proves full production completion.

    A timeout, partial status, missing counters, divergence, or a step count
    below ``expected_ns / dt`` is never promoted to success.
    """
    detail = result.get("detail") or {}
    expected_steps = int(round(expected_ns * 1000.0 / dt_ps))
    steps = detail.get("steps_completed")
    completed_ns = detail.get("completed_ns")
    proved = bool(
        result.get("kind") == "pipeline"
        and result.get("status") == "ok"
        and detail.get("completed") is True
        and detail.get("diverged") is not True
        and isinstance(steps, (int, float))
        and int(steps) >= expected_steps
        and isinstance(completed_ns, (int, float))
        and float(completed_ns) >= expected_ns - 1e-9
    )
    return {
        "job_id": result.get("id"),
        "status": result.get("status"),
        "summary": result.get("summary"),
        "expected_ns": expected_ns,
        "expected_steps": expected_steps,
        "completed_ns": completed_ns,
        "steps_completed": steps,
        "ns_per_day": detail.get("ns_per_day"),
        "workdir": detail.get("workdir"),
        "output": detail.get("output"),
        "proved_complete": proved,
    }


def extract_pipeline_artifacts(
    result: Dict[str, Any], destination: str | Path
) -> Dict[str, Any]:
    """Write the small summary/SVG payload embedded in a pipeline receipt.

    The authoritative files remain below F:\\cgmd\\results on the desktop.  This
    creates only the requested session-viewable copy and rejects unsafe or
    oversized artifact paths.
    """
    detail = result.get("detail") or {}
    metrics = detail.get("summary_metrics")
    metrics_json = detail.get("summary_metrics_json")
    expected_sha256 = str(detail.get("metrics_sha256") or "").lower()
    exact_metrics_copy = False
    if isinstance(metrics_json, str) and metrics_json:
        parsed = json.loads(metrics_json)
        if not isinstance(parsed, dict):
            raise ValueError("embedded summary_metrics_json is not a JSON object")
        metrics_text = metrics_json
        exact_metrics_copy = True
    elif isinstance(metrics, dict):
        metrics_text = json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    else:
        raise ValueError("pipeline receipt does not embed summary_metrics")
    metrics_bytes = metrics_text.encode("utf-8")
    metrics_sha256 = hashlib.sha256(metrics_bytes).hexdigest()
    if exact_metrics_copy and expected_sha256 and metrics_sha256 != expected_sha256:
        raise ValueError("extracted summary_metrics.json does not match the desktop SHA-256")
    target = Path(destination)
    target.mkdir(parents=True, exist_ok=True)
    written: List[Dict[str, Any]] = []
    metrics_path = target / "summary_metrics.json"
    metrics_path.write_bytes(metrics_bytes)
    written.append(
        {
            "path": str(metrics_path),
            "bytes": len(metrics_bytes),
            "sha256": metrics_sha256,
            "exact_desktop_copy": exact_metrics_copy
            and (not expected_sha256 or metrics_sha256 == expected_sha256),
        }
    )

    svg_artifacts = detail.get("svg_artifacts") or {}
    if isinstance(svg_artifacts, dict):
        for relative, content in svg_artifacts.items():
            if not isinstance(content, str) or len(content.encode("utf-8")) > 262144:
                continue
            relative_path = Path(str(relative).replace("\\", "/"))
            if relative_path.is_absolute() or ".." in relative_path.parts:
                continue
            if relative_path.suffix.lower() != ".svg":
                continue
            out_path = target / relative_path
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8")
            written.append(
                {"path": str(out_path), "bytes": len(content.encode("utf-8"))}
            )
    total = sum(int(row["bytes"]) for row in written)
    return {
        "destination": str(target),
        "files": written,
        "total_bytes": total,
        "expected_metrics_sha256": expected_sha256,
        "metrics_sha256": metrics_sha256,
        "exact_metrics_copy": exact_metrics_copy
        and (not expected_sha256 or metrics_sha256 == expected_sha256),
    }


def _minimum_image(delta: float, length: float) -> float:
    if length <= 0:
        raise ValueError("box length must be positive")
    return delta - length * round(delta / length)


def _circular_mean_z(values: Sequence[float], length: float) -> float:
    if not values:
        raise ValueError("at least one phosphate z coordinate is required")
    sx = 0.0
    sy = 0.0
    scale = 2.0 * math.pi / length
    for value in values:
        angle = value * scale
        sx += math.cos(angle)
        sy += math.sin(angle)
    if sx == 0.0 and sy == 0.0:
        raise ValueError("circular phosphate mean is undefined")
    return (math.atan2(sy, sx) / scale) % length


def parse_xvg_numeric(path: str | Path) -> List[List[float]]:
    """Parse numeric XVG rows, skipping comments and Grace metadata."""
    rows: List[List[float]] = []
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "@", "&")):
            continue
        parts = line.replace(",", " ").split()
        try:
            values = [float(part) for part in parts]
        except ValueError:
            continue
        if len(values) >= 4:
            rows.append(values)
    if not rows:
        raise ValueError("no numeric XVG rows in %s" % path)
    return rows


def _coordinates(rows: List[List[float]]) -> Tuple[List[float], List[List[Tuple[float, float, float]]]]:
    width = len(rows[0])
    if width < 4 or (width - 1) % 3:
        raise ValueError("coordinate XVG must contain time plus xyz triplets")
    times: List[float] = []
    frames: List[List[Tuple[float, float, float]]] = []
    for row in rows:
        if len(row) != width:
            raise ValueError("coordinate XVG rows have inconsistent widths")
        times.append(row[0])
        frames.append(
            [
                (row[index], row[index + 1], row[index + 2])
                for index in range(1, width, 3)
            ]
        )
    return times, frames


def _box_z_lengths(rows: List[List[float]]) -> List[float]:
    lengths: List[float] = []
    for row in rows:
        if len(row) == 4:
            lengths.append(row[3])
        elif len(row) >= 10:
            lengths.append(row[3])
        elif len(row) == 2:
            lengths.append(row[1])
        else:
            raise ValueError("box XVG must contain time plus 1, 3 or 9 box values")
    return lengths


def insertion_depth_from_xvg(
    peptide_xvg: str | Path,
    phosphate_xvg: str | Path,
    box_xvg: str | Path,
    *,
    start_ps: Optional[float] = None,
    end_ps: Optional[float] = None,
) -> Dict[str, Any]:
    """Compute PBC-aware peptide centroid depth from coordinate XVGs.

    ``z_distance_nm`` is peptide bead-centroid z minus the circular-mean
    phosphate mid-plane, minimum-imaged into [-Lz/2, Lz/2].
    ``insertion_depth_nm`` is phosphate half-thickness minus abs(z_distance):
    positive means the centroid lies between the two mean phosphate planes.
    This is a geometric insertion measure, not evidence of a pore.
    """
    peptide_times, peptide_frames = _coordinates(parse_xvg_numeric(peptide_xvg))
    phosphate_times, phosphate_frames = _coordinates(parse_xvg_numeric(phosphate_xvg))
    box_rows = parse_xvg_numeric(box_xvg)
    box_times = [row[0] for row in box_rows]
    box_lengths = _box_z_lengths(box_rows)
    count = min(len(peptide_times), len(phosphate_times), len(box_times))
    if count == 0:
        raise ValueError("no overlapping frames")

    series: List[Dict[str, float]] = []
    for index in range(count):
        time_ps = peptide_times[index]
        if start_ps is not None and time_ps < start_ps:
            continue
        if end_ps is not None and time_ps > end_ps:
            continue
        if abs(phosphate_times[index] - time_ps) > 1e-6 or abs(box_times[index] - time_ps) > 1e-6:
            raise ValueError("peptide, phosphate and box XVG times do not align")
        lz = box_lengths[index]
        peptide = peptide_frames[index]
        reference_z = peptide[0][2]
        unwrapped = [
            reference_z + _minimum_image(atom[2] - reference_z, lz)
            for atom in peptide
        ]
        peptide_z = sum(unwrapped) / len(unwrapped)
        phosphate_z = [atom[2] for atom in phosphate_frames[index]]
        midplane_z = _circular_mean_z(phosphate_z, lz)
        relative_phosphate = [
            _minimum_image(value - midplane_z, lz) for value in phosphate_z
        ]
        upper = [value for value in relative_phosphate if value > 0]
        lower = [value for value in relative_phosphate if value < 0]
        if not upper or not lower:
            raise ValueError("both phosphate leaflets are required")
        half_thickness = (sum(upper) / len(upper) - sum(lower) / len(lower)) / 2.0
        z_distance = _minimum_image(peptide_z - midplane_z, lz)
        series.append(
            {
                "time_ps": float(time_ps),
                "z_distance_nm": float(z_distance),
                "phosphate_half_thickness_nm": float(half_thickness),
                "insertion_depth_nm": float(half_thickness - abs(z_distance)),
            }
        )
    if not series:
        raise ValueError("sampling window contains no frames")
    z_values = [row["z_distance_nm"] for row in series]
    depth_values = [row["insertion_depth_nm"] for row in series]
    return {
        "method": (
            "peptide bead centroid unwrapped against its first bead by minimum "
            "image; phosphate mid-plane from circular mean; insertion depth = "
            "phosphate half-thickness - abs(peptide centroid minus mid-plane)"
        ),
        "sampling": {
            "frames": len(series),
            "start_ps": series[0]["time_ps"],
            "end_ps": series[-1]["time_ps"],
        },
        "z_distance_mean_nm": statistics.fmean(z_values),
        "z_distance_std_nm": statistics.pstdev(z_values) if len(z_values) > 1 else 0.0,
        "insertion_depth_mean_nm": statistics.fmean(depth_values),
        "insertion_depth_std_nm": statistics.pstdev(depth_values) if len(depth_values) > 1 else 0.0,
        "inserted_fraction": sum(value > 0 for value in depth_values) / len(depth_values),
        "series": series,
        "interpretation_limit": "geometric insertion only; this is not pore evidence",
    }


def stage_text_files(
    repo: str,
    files: Dict[str, str | Path],
    *,
    ref: str = hub_mailbox.DEFAULT_REF,
) -> List[str]:
    """Push explicitly listed small text inputs to the mailbox ref.

    Keys are mailbox-relative paths.  Heavy/binary artefacts and coordinate
    files are rejected by suffix.  Callers must clean the exact returned
    paths after the desktop has consumed them; git history can still retain
    formerly committed text even after removal.
    """
    adds: Dict[str, bytes] = {}
    for remote_path, local_path in files.items():
        if remote_path.startswith("/") or ".." in Path(remote_path).parts:
            raise ValueError("unsafe staged path: %s" % remote_path)
        source = Path(local_path)
        if source.suffix.lower() not in TEXT_STAGING_SUFFIXES:
            raise ValueError("refusing to stage non-allowlisted suffix: %s" % source)
        data = source.read_bytes()
        if len(data) > 1_000_000:
            raise ValueError("refusing to stage a file over 1 MB: %s" % source)
        if b"\x00" in data:
            raise ValueError("refusing to stage binary-looking data: %s" % source)
        adds[remote_path] = data
    if adds:
        hub_mailbox.push_files(repo, ref, adds, [], "mailbox: stage small text inputs")
    return sorted(adds)


def cleanup_staged_files(
    repo: str,
    paths: Iterable[str],
    *,
    ref: str = hub_mailbox.DEFAULT_REF,
) -> Dict[str, Any]:
    """Remove exact staged paths and verify them on a fresh mailbox fetch."""
    removals = sorted(set(paths))
    for path in removals:
        if path.startswith("/") or ".." in Path(path).parts:
            raise ValueError("unsafe staged path: %s" % path)
    if removals:
        hub_mailbox.push_files(repo, ref, {}, removals, "mailbox: remove staged text inputs")
    commit = hub_mailbox.fetch_ref(repo, ref)
    remaining: List[str] = []
    if commit:
        present = set(hub_mailbox.list_files(repo, commit, ""))
        remaining = [path for path in removals if path in present]
    return {
        "removed": removals,
        "remaining_after_fetch": remaining,
        "verified_removed": not remaining,
        "note": "git history may retain text that was committed earlier",
    }


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="fixed F-drive CGMD mailbox helper")
    parser.add_argument("--repo", default=str(REPO_ROOT), help="checkout used to access hub/mailbox")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("caps", help="print the offline capability card")

    files_p = sub.add_parser("files", help="send a fixed-path files job")
    files_p.add_argument("--action", default="survey")
    files_p.add_argument("--task-id", default="legacy-cgmd-100ns-20261030")
    files_p.add_argument("--source-prefix", default="cgmd_100ns")
    files_p.add_argument("--branch", default="")
    files_p.add_argument("--confirm-mutation", action="store_true")
    files_p.add_argument("--copy-credentials", action="store_true")
    files_p.add_argument("--timeout", type=int, default=1800)
    files_p.add_argument("--dry-run", action="store_true", help="print payload without sending")

    gmx_p = sub.add_parser("gmx", help="send one whitelisted gmx job")
    gmx_p.add_argument("--task-id", required=True)
    gmx_p.add_argument("--stdin-text", default="")
    gmx_p.add_argument("--timeout", type=int, default=900)
    gmx_p.add_argument("argv", nargs=argparse.REMAINDER)

    pipe_p = sub.add_parser("pipeline", help="send/retry the native pipeline under F: roots")
    pipe_p.add_argument("--task-id", required=True)
    pipe_p.add_argument("--sequence", default=MAGAININ2)
    pipe_p.add_argument("--production-ns", type=float, default=100.0)
    pipe_p.add_argument("--equilibration-ns", type=float, default=10.0)
    pipe_p.add_argument("--attempts", type=int, default=1)
    pipe_p.add_argument("--install", action="store_true")
    pipe_p.add_argument("--dry-run", action="store_true")
    pipe_p.add_argument("--artifact-dir", default="", help="write embedded summary/SVG copies here")

    depth_p = sub.add_parser("insertion-depth", help="compute PBC-aware depth from XVG files")
    depth_p.add_argument("peptide_xvg")
    depth_p.add_argument("phosphate_xvg")
    depth_p.add_argument("box_xvg")
    depth_p.add_argument("--start-ps", type=float)
    depth_p.add_argument("--end-ps", type=float)

    clean_p = sub.add_parser("cleanup-staging", help="remove exact staged mailbox paths")
    clean_p.add_argument("paths", nargs="+")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    repo = str(Path(args.repo).resolve())

    if args.command == "caps":
        _print_json(hub_mailbox.capabilities(repo))
        return 0

    if args.command == "files":
        payload = build_files_args(
            args.action,
            task_id=args.task_id,
            source_prefix=args.source_prefix,
            branch=args.branch,
            confirm_mutation=args.confirm_mutation,
            copy_credentials=args.copy_credentials,
            timeout_s=args.timeout,
        )
        if args.dry_run:
            _print_json(payload)
            return 0
        result = send_and_wait(
            repo,
            "files",
            payload,
            note="f_hub files %s" % args.action,
            timeout_s=args.timeout,
        )
        _print_json({"result": result, "assessment": assess_files_result(result, args.action)})
        return 0 if assess_files_result(result, args.action)["proved"] else 6

    if args.command == "gmx":
        gmx_argv = list(args.argv)
        if gmx_argv and gmx_argv[0] == "--":
            gmx_argv = gmx_argv[1:]
        if not gmx_argv:
            raise SystemExit("gmx argv is required after --")
        payload = {
            "argv": gmx_argv,
            "workdir": f_run_dir(args.task_id),
            "timeout_s": int(args.timeout),
        }
        if args.stdin_text:
            payload["stdin_text"] = args.stdin_text
        result = send_and_wait(
            repo,
            "gmx",
            payload,
            note="f_hub gmx under F: run root",
            timeout_s=args.timeout,
        )
        _print_json(result)
        return 0 if result.get("status") == "ok" else 6

    if args.command == "pipeline":
        payload = build_pipeline_args(
            args.task_id,
            sequence=args.sequence,
            production_ns=args.production_ns,
            equilibration_ns=args.equilibration_ns,
            install=args.install,
        )
        if args.dry_run:
            _print_json(payload)
            return 0
        attempts: List[Dict[str, Any]] = []
        for _ in range(max(1, int(args.attempts))):
            result = send_and_wait(
                repo,
                "pipeline",
                payload,
                note="f_hub native pipeline under F: roots",
                timeout_s=5400,
            )
            assessment = assess_pipeline_result(result, expected_ns=args.production_ns)
            attempts.append({"result": result, "assessment": assessment})
            if assessment["proved_complete"]:
                output: Dict[str, Any] = {"attempts": attempts, "proved_complete": True}
                if args.artifact_dir:
                    output["artifacts"] = extract_pipeline_artifacts(result, args.artifact_dir)
                _print_json(output)
                return 0
            if result.get("status") in {"unsupported", "fail", "error"}:
                break
        _print_json({"attempts": attempts, "proved_complete": False})
        return 6

    if args.command == "insertion-depth":
        _print_json(
            insertion_depth_from_xvg(
                args.peptide_xvg,
                args.phosphate_xvg,
                args.box_xvg,
                start_ps=args.start_ps,
                end_ps=args.end_ps,
            )
        )
        return 0

    if args.command == "cleanup-staging":
        outcome = cleanup_staged_files(repo, args.paths)
        _print_json(outcome)
        return 0 if outcome["verified_removed"] else 6

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
