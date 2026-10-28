"""Incremental GROMACS ``.log`` parser used by the phone beacon and reports.

Extracted signals
-----------------
* ``step`` / ``time``          -- current integration point
* ``nsteps`` / ``dt``          -- taken from the echoed mdp parameters
* ``ns_per_day``               -- last ``Performance:`` block (GPU speed)
* ``remaining_wall_s``         -- mdrun's own remaining-time estimate
* LINCS warnings and blow-up   -- divergence detection
* start / finish markers

Everything is regex based and dependency free.  The parser is *incremental*:
:class:`LogWatcher` remembers the byte offset and only reads appended data, so
it can follow a 1 microsecond production run without ever re-reading the log.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = [
    "LogState",
    "LogWatcher",
    "parse_log_text",
    "format_hours",
    "DIVERGENCE_PATTERNS",
]

_RE_STEP_HEADER = re.compile(r"^\s*Step\s+Time\s*$", re.IGNORECASE)
_RE_STEP_ROW = re.compile(r"^\s*(\d+)\s+(-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)\s*$")
_RE_STEP_INLINE = re.compile(
    r"^\s*step\s+(\d+)\s*,\s*(?:time|t)\s*=?\s*(-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)",
    re.IGNORECASE,
)
_RE_REMAINING = re.compile(
    r"remaining wall clock time(?:\s+is)?\s*:?\s*(\d+(?:\.\d+)?)\s*(s|sec|seconds|h|hours|min|minutes)",
    re.IGNORECASE,
)
_RE_PERF = re.compile(r"Performance:\s+([\d.]+)\s+([\d.]+)", re.IGNORECASE)
_RE_PERF_NS = re.compile(r"^\s*ns/day\s*[:=]?\s*([\d.]+)", re.IGNORECASE)
_RE_NSTEPS = re.compile(r"^\s*nsteps\s*=\s*(\d+)", re.IGNORECASE)
_RE_DT = re.compile(r"^\s*dt\s*=\s*(-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)\s*$", re.IGNORECASE)
_RE_TOTAL_NS = re.compile(r"^(?:total[-_ ]?ns|production[-_ ]?ns)\s*[:=]\s*([\d.]+)", re.IGNORECASE)

_RE_STARTED = re.compile(r"Started mdrun on rank\s+\d+", re.IGNORECASE)
_RE_FINISHED = re.compile(r"Finished mdrun|Writing final coordinates", re.IGNORECASE)
_RE_LINCS = re.compile(r"LINCS WARNING|LINCS:\s|Too many LINCS", re.IGNORECASE)
_RE_LINCS_WARNING = re.compile(r"LINCS WARNING")
_RE_LINCS_FATAL = re.compile(r"Too many LINCS warnings|LINCS.*(fatal|failed)", re.IGNORECASE)
_RE_NAN = re.compile(r"\b(NaN|nan|Infinity|inf)\b")
_RE_GPU = re.compile(r"GPU\s*#?\s*(\d+)?.*?(?:NVIDIA|GeForce|RTX|A100|H100|Tesla|Quadro|A[0-9]{4})", re.IGNORECASE)

#: text fragments that mean "this simulation is dead, stop waiting"
DIVERGENCE_PATTERNS = (
    ("fatal_error", re.compile(r"Fatal error|FATAL ERROR", re.IGNORECASE)),
    ("segfault", re.compile(r"Segmentation fault|signal 11|STATUS_ACCESS_VIOLATION", re.IGNORECASE)),
    ("blowup", re.compile(r"blowing up|blown up|system (?:is )?exploded|pressure.*nan", re.IGNORECASE)),
    ("nan", re.compile(r"Step \d+.*(?:nan|NaN)")),
    ("lincs_too_many", _RE_LINCS_FATAL),
    ("settle", re.compile(r"Water molecule starting at atom\s+\d+\s+can not be settled", re.IGNORECASE)),
    ("assertion", re.compile(r"Assertion.*failed", re.IGNORECASE)),
    ("out_of_memory", re.compile(r"std::bad_alloc|Out of memory|CUDA_ERROR_OUT_OF_MEMORY", re.IGNORECASE)),
    ("mpi_abort", re.compile(r"MPI_ABORT|application called MPI_Abort", re.IGNORECASE)),
)


def format_hours(seconds: Optional[float]) -> str:
    """``3725`` -> ``"1 h 02 m"`` (empty string for unknown values)."""
    if seconds is None:
        return ""
    try:
        seconds = max(0.0, float(seconds))
    except (TypeError, ValueError):
        return ""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours:
        return "{} h {:02d} m".format(hours, minutes)
    if minutes:
        return "{} m {:02d} s".format(minutes, int(seconds % 60))
    return "{:.0f} s".format(seconds)


@dataclass
class LogState:
    """Rolling state distilled from a GROMACS log."""

    source: str = ""
    step: int = 0
    time_ps: float = 0.0
    total_steps: int = 0
    dt_ps: float = 0.0
    total_ns: Optional[float] = None
    ns_per_day: Optional[float] = None
    remaining_wall_s: Optional[float] = None
    lincs_warnings: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    divergence: Optional[str] = None
    started: bool = False
    finished: bool = False
    gpu: Optional[str] = None
    lines_read: int = 0
    last_line: str = ""
    _pending_step_row: bool = field(default=False, repr=False)

    # -- derived ----------------------------------------------------------
    @property
    def total_ns_resolved(self) -> Optional[float]:
        """Simulated length in ns: explicit value, else ``nsteps * dt``."""
        if self.total_ns:
            return float(self.total_ns)
        if self.total_steps and self.dt_ps:
            return self.total_steps * self.dt_ps / 1000.0
        return None

    @property
    def progress(self) -> Optional[float]:
        """Completed fraction in ``[0, 1]`` (None when unknown)."""
        if self.total_steps > 0 and self.step > 0:
            return max(0.0, min(1.0, self.step / float(self.total_steps)))
        total = self.total_ns_resolved
        if total and self.time_ps > 0:
            return max(0.0, min(1.0, (self.time_ps / 1000.0) / total))
        return None

    @property
    def simulated_ns(self) -> float:
        return self.time_ps / 1000.0

    @property
    def eta_seconds(self) -> Optional[float]:
        """Remaining wall-clock seconds (mdrun estimate first, then ns/day)."""
        if self.remaining_wall_s is not None:
            return float(self.remaining_wall_s)
        total = self.total_ns_resolved
        rate = self.ns_per_day
        if total and rate and rate > 0:
            remaining_ns = max(0.0, total - self.simulated_ns)
            return remaining_ns / rate * 86400.0
        return None

    @property
    def is_diverged(self) -> bool:
        return bool(self.divergence) or bool(self.errors)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "step": self.step,
            "time_ps": round(self.time_ps, 3),
            "total_steps": self.total_steps,
            "total_ns": self.total_ns_resolved,
            "ns_per_day": round(self.ns_per_day, 3) if self.ns_per_day else None,
            "progress": round(self.progress, 4) if self.progress is not None else None,
            "eta_seconds": round(self.eta_seconds, 1) if self.eta_seconds is not None else None,
            "eta_human": format_hours(self.eta_seconds),
            "lincs_warnings": self.lincs_warnings,
            "divergence": self.divergence,
            "errors": self.errors[-5:],
            "warnings": self.warnings[-5:],
            "started": self.started,
            "finished": self.finished,
            "gpu": self.gpu,
            "lines_read": self.lines_read,
        }


class LogWatcher:
    """Tail-follow a log file and keep a :class:`LogState` up to date."""

    def __init__(self, path: str, state: Optional[LogState] = None, from_start: bool = True) -> None:
        self.path = path
        self.state = state or LogState(source=path)
        self.state.source = path
        self._offset = 0 if from_start else self._size()
        self._carry = ""

    def _size(self) -> int:
        try:
            return os.path.getsize(self.path)
        except OSError:
            return 0

    def reset(self) -> None:
        self._offset = 0
        self._carry = ""
        self.state = LogState(source=self.path)

    def poll(self) -> LogState:
        """Consume whatever was appended since the previous call."""
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return self.state
        if size < self._offset:  # truncated / replaced -> start over
            self.reset()
        if size == self._offset:
            return self.state
        with open(self.path, "r", encoding="utf-8", errors="replace") as handle:
            handle.seek(self._offset)
            chunk = handle.read()
            self._offset = handle.tell()
        if self._carry:
            chunk = self._carry + chunk
            self._carry = ""
        if chunk and not chunk.endswith("\n"):
            *lines, self._carry = chunk.split("\n")
            chunk = "\n".join(lines) + "\n"
        for line in chunk.splitlines():
            parse_line(line, self.state)
        return self.state


def _to_seconds(value: str, unit: str) -> float:
    amount = float(value)
    unit = (unit or "s").lower()
    if unit.startswith("h"):
        return amount * 3600.0
    if unit.startswith("min"):
        return amount * 60.0
    return amount


def parse_line(line: str, state: LogState) -> LogState:
    """Feed one log line into ``state`` (mutates and returns it)."""
    state.lines_read += 1
    state.last_line = line

    # -- blow-up / fatal conditions first: they decide everything else -----
    for name, pattern in DIVERGENCE_PATTERNS:
        if pattern.search(line):
            if name in ("lincs_too_many",):
                state.divergence = "lincs"
            else:
                state.divergence = name
            text = line.strip()[:200]
            if text and text not in state.errors:
                state.errors.append(text)
            break

    if _RE_LINCS.search(line):
        if _RE_LINCS_WARNING.search(line) and "too many" not in line.lower():
            state.lincs_warnings += 1
            if len(state.warnings) < 20:
                state.warnings.append(line.strip()[:200])
        if _RE_LINCS_FATAL.search(line):
            state.divergence = "lincs"

    if _RE_STARTED.search(line):
        state.started = True
    if _RE_FINISHED.search(line):
        state.finished = True

    match = _RE_NSTEPS.match(line)
    if match:
        state.total_steps = int(match.group(1))
    match = _RE_DT.match(line)
    if match:
        try:
            state.dt_ps = float(match.group(1))
        except ValueError:
            pass
    match = _RE_TOTAL_NS.match(line)
    if match:
        state.total_ns = float(match.group(1))

    match = _RE_PERF.search(line)
    if match:
        try:
            state.ns_per_day = float(match.group(1))
        except ValueError:
            pass
        state.remaining_wall_s = None  # mdrun's own estimate is now redundant
    match = _RE_PERF_NS.match(line)
    if match:
        try:
            state.ns_per_day = float(match.group(1))
        except ValueError:
            pass

    match = _RE_REMAINING.search(line)
    if match:
        state.remaining_wall_s = _to_seconds(match.group(1), match.group(2))

    match = _RE_STEP_INLINE.match(line)
    if match:
        state.step = int(match.group(1))
        state.time_ps = float(match.group(2))
        state.remaining_wall_s = None

    if _RE_STEP_HEADER.match(line):
        state._pending_step_row = True
    elif state._pending_step_row:
        match = _RE_STEP_ROW.match(line)
        if match:
            state.step = int(match.group(1))
            state.time_ps = float(match.group(2))
            state._pending_step_row = False

    if state.gpu is None and _RE_GPU.search(line):
        state.gpu = line.strip()[:120]

    return state


def parse_log_text(text: str, source: str = "<memory>", total_ns: Optional[float] = None) -> LogState:
    """Parse a whole log body (used by tests and post-mortem reports)."""
    state = LogState(source=source, total_ns=total_ns)
    for line in text.splitlines():
        parse_line(line, state)
    return state
