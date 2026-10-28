"""Task contract for the desktop hub <-> phone <-> CGMD pipeline handshake.

The whole federation agrees on exactly one file::

    results/status/cgmd_task.json

Anybody (phone, Arena agent, laptop) may write a *pending* task into that file
on the current git branch.  The Windows workstation polls the branch every
60 s, silently claims the task, runs GROMACS in WSL2 on the GPU and finally
flips ``status`` to ``completed_on_desktop`` (or ``failed_on_desktop``) and
pushes the reduced JSON result back onto the same branch.

Design rules
------------
* Standard library only -- this module must run on Windows PowerShell's
  embedded python, inside WSL2 and on a phone-side GitHub Action alike.
* All timestamps are Beijing time (``Asia/Shanghai``) and ISO-8601 with an
  explicit offset, so the phone can sort them without guessing.
* Writes are atomic (``os.replace``) and always UTF-8 without BOM: a half
  written JSON must never be committed by the poller.
* Unknown keys are preserved when a task round-trips through the desktop, so
  a newer phone client can add fields without breaking older runners.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import random
import re
import string
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

__all__ = [
    "SCHEMA",
    "TASK_PATH",
    "RESULT_PATH",
    "DEFAULT_TOPIC",
    "DEFAULT_REPO",
    "STATUSES",
    "FINAL_STATUSES",
    "STATUS_DONE",
    "STATUS_FAILED",
    "TaskError",
    "beijing_now",
    "beijing_iso",
    "parse_iso",
    "new_task_id",
    "new_task",
    "validate_task",
    "load_task",
    "dump_task",
    "set_status",
    "claim_task",
    "is_claimable",
    "reduced_result",
    "summarise",
    "validate_sequence",
]

SCHEMA = "cgmd.task.v1"
RESULT_SCHEMA = "cgmd.summary.v1"

TASK_PATH = "results/status/cgmd_task.json"
RESULT_PATH = "results/status/cgmd_result.json"

DEFAULT_TOPIC = "arena-beacon-95bc796a66"
DEFAULT_REPO = "hukeying85-ux/0fuye"

# Life-cycle ------------------------------------------------------------------
IDLE = "idle"
PENDING = "pending"
CLAIMED = "claimed"
RUNNING = "running"
STATUS_DONE = "completed_on_desktop"
STATUS_FAILED = "failed_on_desktop"
CANCELLED = "cancelled"

STATUSES = (IDLE, PENDING, CLAIMED, RUNNING, STATUS_DONE, STATUS_FAILED, CANCELLED)
FINAL_STATUSES = (STATUS_DONE, STATUS_FAILED, CANCELLED)

# Transitions the desktop runner is allowed to perform.
ALLOWED_TRANSITIONS = {
    PENDING: {CLAIMED, CANCELLED, STATUS_FAILED},
    CLAIMED: {RUNNING, PENDING, STATUS_FAILED, CANCELLED},
    RUNNING: {STATUS_DONE, STATUS_FAILED},
    IDLE: {PENDING, IDLE},
    STATUS_DONE: {PENDING},
    STATUS_FAILED: {PENDING},
    CANCELLED: {PENDING},
}

AA_1TO3 = {
    "A": "ALA", "R": "ARG", "N": "ASN", "D": "ASP", "C": "CYS",
    "Q": "GLN", "E": "GLU", "G": "GLY", "H": "HIS", "I": "ILE",
    "L": "LEU", "K": "LYS", "M": "MET", "F": "PHE", "P": "PRO",
    "S": "SER", "T": "THR", "W": "TRP", "Y": "TYR", "V": "VAL",
}
VALID_AA = set(AA_1TO3)

MAX_PEPTIDE_LEN = 120


class TaskError(Exception):
    """Raised when a task file violates the contract."""


# ---------------------------------------------------------------------------
# time helpers -- the phone lives in UTC+8, keep everything in Beijing time
# ---------------------------------------------------------------------------
try:  # Python >= 3.9
    from zoneinfo import ZoneInfo

    _BEIJING = ZoneInfo("Asia/Shanghai")
except Exception:  # pragma: no cover - very old python / missing tzdata
    _BEIJING = timezone(timedelta(hours=8), name="Asia/Shanghai")


def beijing_now() -> datetime:
    """Current time in Beijing (Asia/Shanghai)."""
    return datetime.now(_BEIJING)


def beijing_iso(moment: Optional[datetime] = None) -> str:
    """ISO-8601 string with the +08:00 offset, second resolution."""
    moment = moment or beijing_now()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_BEIJING)
    return moment.astimezone(_BEIJING).isoformat(timespec="seconds")


def parse_iso(text: str) -> datetime:
    """Parse an ISO-8601 timestamp; naive values are assumed Beijing time."""
    if not isinstance(text, str) or not text:
        raise TaskError("empty timestamp")
    cleaned = text.strip().replace("Z", "+00:00")
    moment = datetime.fromisoformat(cleaned)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_BEIJING)
    return moment.astimezone(_BEIJING)


def new_task_id(moment: Optional[datetime] = None) -> str:
    moment = moment or beijing_now()
    suffix = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(4))
    return "cgmd-{}-{}".format(moment.astimezone(_BEIJING).strftime("%Y%m%d-%H%M%S"), suffix)


def local_hostname() -> str:
    """Best effort host name, without importing platform-specific modules."""
    for key in ("COMPUTERNAME", "HOSTNAME", "NAME"):
        value = os.environ.get(key)
        if value:
            return value.lower()
    try:
        import socket

        return socket.gethostname().lower()
    except Exception:  # pragma: no cover
        return "unknown-host"


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
def validate_sequence(sequence: str, max_len: int = MAX_PEPTIDE_LEN) -> str:
    """Normalise a one-letter peptide sequence, raising ``TaskError`` if bad."""
    if not isinstance(sequence, str):
        raise TaskError("peptide.sequence must be a string")
    cleaned = re.sub(r"[\s\-]", "", sequence).upper()
    if not cleaned:
        raise TaskError("peptide.sequence is empty")
    if len(cleaned) > max_len:
        raise TaskError("peptide too long: {} aa (max {})".format(len(cleaned), max_len))
    bad = sorted({aa for aa in cleaned if aa not in VALID_AA})
    if bad:
        raise TaskError("unsupported residues in sequence: {}".format(", ".join(bad)))
    return cleaned


def _require(mapping: Dict[str, Any], key: str, types, where: str) -> Any:
    if key not in mapping:
        raise TaskError("missing key '{}' in {}".format(key, where))
    value = mapping[key]
    if not isinstance(value, types):
        raise TaskError("key '{}' in {} has wrong type {}".format(key, where, type(value).__name__))
    return value


def validate_task(task: Dict[str, Any], strict: bool = True) -> Dict[str, Any]:
    """Validate (and lightly normalise) a task document.

    Returns the task dict.  Raises :class:`TaskError` on contract violations.
    """
    if not isinstance(task, dict):
        raise TaskError("task document must be a JSON object")
    schema = task.get("schema", SCHEMA)
    if schema != SCHEMA:
        raise TaskError("unsupported schema '{}' (expected '{}')".format(schema, SCHEMA))
    task["schema"] = SCHEMA

    status = task.get("status", IDLE)
    if status not in STATUSES:
        raise TaskError("unknown status '{}'; allowed: {}".format(status, ", ".join(STATUSES)))
    task["status"] = status

    if status == IDLE and not strict:
        return task

    if status != IDLE:
        peptide = _require(task, "peptide", dict, "task")
        sequence = validate_sequence(peptide.get("sequence", ""))
        peptide["sequence"] = sequence
        peptide.setdefault("name", "peptide-{}aa".format(len(sequence)))

        sim = task.setdefault("simulation", {})
        for key, minimum in (("production_ns", 0.01), ("equilibration_ns", 0.0)):
            if key in sim:
                value = sim[key]
                if not isinstance(value, (int, float)) or float(value) < minimum:
                    raise TaskError("simulation.{} must be a number >= {}".format(key, minimum))
        if "gpu_id" in sim and not isinstance(sim["gpu_id"], int):
            raise TaskError("simulation.gpu_id must be an integer")

        membrane = task.setdefault("membrane", {})
        lipids = membrane.setdefault("lipids", {"POPE": 3, "POPG": 1})
        if not isinstance(lipids, dict) or not lipids:
            raise TaskError("membrane.lipids must be a non-empty object")
        for name, ratio in lipids.items():
            if not isinstance(ratio, (int, float)) or ratio <= 0:
                raise TaskError("membrane.lipids.{} must be a positive number".format(name))

    task.setdefault("task_id", new_task_id())
    task.setdefault("created_at", beijing_iso())
    task.setdefault("updated_at", task["created_at"])
    task.setdefault("created_by", "unknown")
    task.setdefault("attempts", 0)
    task.setdefault("history", [])
    if not isinstance(task["history"], list):
        raise TaskError("history must be a list")
    outputs = task.setdefault("outputs", {})
    outputs.setdefault("dir", "results/cgmd")
    outputs.setdefault("ntfy_topic", DEFAULT_TOPIC)
    return task


# ---------------------------------------------------------------------------
# io
# ---------------------------------------------------------------------------
def load_task(path: str = TASK_PATH, strict: bool = True) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8-sig") as handle:
        try:
            task = json.load(handle)
        except json.JSONDecodeError as exc:
            raise TaskError("{} is not valid JSON: {}".format(path, exc))
    return validate_task(task, strict=strict)


def dump_task(task: Dict[str, Any], path: str = TASK_PATH) -> None:
    """Atomically write a task document as UTF-8 JSON."""
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(task, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# state machine
# ---------------------------------------------------------------------------
def set_status(
    task: Dict[str, Any],
    status: str,
    note: Optional[str] = None,
    strict_transition: bool = True,
    **extra: Any,
) -> Dict[str, Any]:
    """Move a task to ``status``, appending to ``history``."""
    if status not in STATUSES:
        raise TaskError("unknown status '{}'".format(status))
    current = task.get("status", IDLE)
    if strict_transition and status != current:
        allowed = ALLOWED_TRANSITIONS.get(current, set())
        if status not in allowed:
            raise TaskError("illegal transition {} -> {}".format(current, status))
    entry = {"at": beijing_iso(), "status": status}
    if note:
        entry["note"] = note
    task["status"] = status
    task["updated_at"] = entry["at"]
    task.setdefault("history", []).append(entry)
    if len(task["history"]) > 60:
        task["history"] = task["history"][-60:]
    for key, value in extra.items():
        task[key] = value
    return task


def is_claimable(task: Dict[str, Any], stale_seconds: int = 6 * 3600, now: Optional[datetime] = None) -> bool:
    """True when the desktop should pick this task up.

    A ``pending`` task is claimable.  A ``claimed``/``running`` task whose
    claim is older than ``stale_seconds`` is considered abandoned and may be
    re-claimed (the previous attempt almost certainly died with the machine).
    """
    now = now or beijing_now()
    status = task.get("status")
    if status == PENDING:
        return True
    if status in (CLAIMED, RUNNING):
        claim = task.get("claim") or {}
        stamp = claim.get("claimed_at") or task.get("updated_at")
        try:
            age = (now - parse_iso(stamp)).total_seconds() if stamp else stale_seconds + 1
        except TaskError:
            return True
        return age > stale_seconds
    return False


def claim_task(task: Dict[str, Any], owner: str, host: Optional[str] = None) -> Dict[str, Any]:
    """Mark a task as claimed by this workstation."""
    task["attempts"] = int(task.get("attempts", 0)) + 1
    task["claim"] = {
        "owner": owner,
        "host": host or local_hostname(),
        "claimed_at": beijing_iso(),
        "attempt": task["attempts"],
    }
    return set_status(task, CLAIMED, note="claimed by {}".format(owner))


def reduced_result(
    task: Dict[str, Any],
    metrics: Dict[str, Any],
    metrics_path: str,
    figures: Optional[List[str]] = None,
    notes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build the compact result block embedded in the task file.

    Keep this small (< 8 kB): it is committed on every finished task and is
    what the phone notification and ``results/status/cgmd_result.json`` show.
    """
    metrics = metrics or {}
    insertion = metrics.get("membrane_insertion", {}) or {}
    order = metrics.get("lipid_order", {}) or {}
    pore = metrics.get("pore", {}) or {}
    sim = metrics.get("simulation", {}) or {}
    peptide = metrics.get("peptide", {}) or {}
    return {
        "schema": RESULT_SCHEMA,
        "task_id": task.get("task_id"),
        "status": task.get("status"),
        "finished_at": beijing_iso(),
        "metrics_path": metrics_path,
        "figures": figures or [],
        "headline": {
            "peptide": peptide.get("name") or task.get("peptide", {}).get("name"),
            "sequence": peptide.get("sequence") or task.get("peptide", {}).get("sequence"),
            "net_charge": peptide.get("net_charge_ph7_4", peptide.get("net_charge")),
            "z_distance_nm": insertion.get("z_distance_mean_nm"),
            "lipid_order_mean": order.get("mean"),
            "pore_formed": pore.get("pore_formed"),
            "water_in_core_mean": pore.get("water_in_core_mean"),
            "ns_per_day": sim.get("ns_per_day"),
            "production_ns": sim.get("production_ns"),
            "walltime_h": sim.get("walltime_h"),
        },
        "notes": notes or [],
    }


def summarise(task: Dict[str, Any]) -> str:
    """One-line human readable summary (used by logs and ntfy messages)."""
    peptide = task.get("peptide") or {}
    sim = task.get("simulation") or {}
    membrane = task.get("membrane") or {}
    lipids = membrane.get("lipids") or {}
    ratio = ":".join("{}".format(int(v)) for v in lipids.values()) if lipids else "?"
    names = ":".join(lipids.keys()) if lipids else "?"
    return "{} | {} ({}) | {}={} | prod {} ns | gpu {}".format(
        task.get("task_id", "?"),
        peptide.get("name", "?"),
        peptide.get("sequence", "?"),
        names,
        ratio,
        sim.get("production_ns", "?"),
        sim.get("gpu_id", 0),
    )


# ---------------------------------------------------------------------------
# task factory
# ---------------------------------------------------------------------------
def new_task(
    sequence: str,
    name: Optional[str] = None,
    production_ns: float = 1000.0,
    equilibration_ns: float = 20.0,
    created_by: str = "arena-agent",
    lipids: Optional[Dict[str, float]] = None,
    gpu_id: int = 0,
    temperature_k: float = 310.0,
    salt_m: float = 0.15,
    subject: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a fresh, fully validated *pending* task document."""
    sequence = validate_sequence(sequence)
    production_ns = 1000.0 if production_ns is None else float(production_ns)
    equilibration_ns = 20.0 if equilibration_ns is None else float(equilibration_ns)
    gpu_id = 0 if gpu_id is None else int(gpu_id)
    temperature_k = 310.0 if temperature_k is None else float(temperature_k)
    salt_m = 0.15 if salt_m is None else float(salt_m)
    task = {
        "schema": SCHEMA,
        "task_id": new_task_id(),
        "status": PENDING,
        "created_at": beijing_iso(),
        "created_by": created_by,
        "priority": 3,
        "peptide": {
            "name": name or "pep-{}aa".format(len(sequence)),
            "sequence": sequence,
            "structure_pdb": None,
            "n_copies": 1,
            "secondary_structure": "C",
        },
        "membrane": {
            "model": "bacterial-inner-membrane",
            "lipids": lipids or {"POPE": 3, "POPG": 1},
            "box_xy_nm": 12.0,
            "salt_M": salt_m,
            "temperature_K": temperature_k,
        },
        "simulation": {
            "em_steps": 5000,
            "equilibration_ns": equilibration_ns,
            "production_ns": production_ns,
            "dt_fs": 20,
            "gpu_id": gpu_id,
            "seed": -1,
        },
        "analysis": {
            "frame_stride_ps": 1000,
            "pore_radius_nm": 1.2,
            "water_core_halfheight_nm": 0.9,
        },
        "outputs": {
            "dir": "results/cgmd",
            "ntfy_topic": DEFAULT_TOPIC,
            "repo": DEFAULT_REPO,
        },
        "attempts": 0,
        "history": [{"at": beijing_iso(), "status": PENDING, "note": subject or "created"}],
    }
    return validate_task(task)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cmd_new(args: argparse.Namespace) -> int:
    task = new_task(
        sequence=args.sequence,
        name=args.name,
        production_ns=args.production_ns,
        equilibration_ns=args.equilibration_ns,
        created_by=args.created_by,
        gpu_id=args.gpu_id,
        salt_m=args.salt,
        temperature_k=args.temperature,
    )
    if args.write:
        dump_task(task, args.write)
        print("wrote {} ({})".format(args.write, task["task_id"]))
    else:
        print(json.dumps(task, ensure_ascii=False, indent=2))
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    task = load_task(args.path, strict=False)
    if args.json:
        print(json.dumps(task, ensure_ascii=False, indent=2))
    else:
        print(summarise(task))
        print("status : {}".format(task.get("status")))
        print("updated: {}".format(task.get("updated_at")))
        for entry in task.get("history", [])[-5:]:
            print("  {} {:<22} {}".format(entry.get("at"), entry.get("status"), entry.get("note", "")))
    return 0


def _cmd_set_status(args: argparse.Namespace) -> int:
    task = load_task(args.path, strict=False)
    set_status(task, args.status, note=args.note, strict_transition=not args.force)
    dump_task(task, args.path)
    print("{} -> {}".format(task.get("task_id"), args.status))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    try:
        task = load_task(args.path)
    except TaskError as exc:
        print("INVALID: {}".format(exc), file=sys.stderr)
        return 2
    print("OK {} {}".format(task.get("status"), summarise(task)))
    return 0


def _cmd_claim(args: argparse.Namespace) -> int:
    task = load_task(args.path, strict=False)
    if not is_claimable(task, stale_seconds=args.stale_seconds):
        print("not claimable: status={}".format(task.get("status")))
        return 1
    claim_task(task, owner=args.owner)
    dump_task(task, args.path)
    print("claimed {} (attempt {})".format(task.get("task_id"), task.get("attempts")))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m core.task_contract",
        description="Create, inspect and move CGMD task documents.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="create a pending task")
    p_new.add_argument("--sequence", required=True, help="one-letter peptide sequence")
    p_new.add_argument("--name", default=None)
    p_new.add_argument("--production-ns", dest="production_ns", type=float, default=1000.0)
    p_new.add_argument("--equilibration-ns", dest="equilibration_ns", type=float, default=20.0)
    p_new.add_argument("--gpu-id", dest="gpu_id", type=int, default=0)
    p_new.add_argument("--salt", type=float, default=0.15)
    p_new.add_argument("--temperature", type=float, default=310.0)
    p_new.add_argument("--created-by", dest="created_by", default="cli")
    p_new.add_argument("--write", default=None, help="write the task to this path")
    p_new.set_defaults(func=_cmd_new)

    p_show = sub.add_parser("show", help="print a task")
    p_show.add_argument("--path", default=TASK_PATH)
    p_show.add_argument("--json", action="store_true")
    p_show.set_defaults(func=_cmd_show)

    p_set = sub.add_parser("set-status", help="move a task to a new status")
    p_set.add_argument("status", choices=STATUSES)
    p_set.add_argument("--path", default=TASK_PATH)
    p_set.add_argument("--note", default=None)
    p_set.add_argument("--force", action="store_true", help="skip transition checks")
    p_set.set_defaults(func=_cmd_set_status)

    p_val = sub.add_parser("validate", help="validate a task document")
    p_val.add_argument("--path", default=TASK_PATH)
    p_val.set_defaults(func=_cmd_validate)

    p_claim = sub.add_parser("claim", help="claim a pending task for this host")
    p_claim.add_argument("--path", default=TASK_PATH)
    p_claim.add_argument("--owner", default="desktop")
    p_claim.add_argument("--stale-seconds", dest="stale_seconds", type=int, default=6 * 3600)
    p_claim.set_defaults(func=_cmd_claim)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
