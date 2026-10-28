"""Runtime configuration for the CGMD pipeline.

Everything is resolved from (in order of precedence):

1. explicit CLI flags,
2. environment variables (``CGMD_*``),
3. ``skills/cgmd-hub/config/cgmd_hub.local.json`` (gitignored, workstation
   specific paths),
4. sensible defaults that work on the reference Windows + WSL2 GPU box.

The Martini 3 force field is *never* vendored into this repository (it is
third-party material with its own licence).  :func:`resolve_martini3_dir`
therefore looks for it in the usual places, including the ``martini_forcefields``
PyPI package, and raises an actionable error if it cannot be found.
"""

from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = ["Config", "resolve_martini3_dir", "find_binary", "load_local_config"]

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

DEFAULT_FF_CANDIDATES = (
    os.environ.get("CGMD_MARTINI3_DIR", ""),
    os.path.join(REPO_ROOT, "forcefields", "martini3"),
    os.path.join(REPO_ROOT, "code", "cgmd", "forcefields", "martini3"),
    os.path.join(REPO_ROOT, "forcefields", "martini_v3.0.0"),
    "~/forcefields/martini3",
    "/opt/martini3",
    "/usr/local/share/gromacs/forcefields/martini3",
)


def load_local_config() -> Dict[str, Any]:
    """Read the workstation-local hub config, if present."""
    candidates = [
        os.environ.get("CGMD_HUB_CONFIG", ""),
        os.path.join(REPO_ROOT, "skills", "cgmd-hub", "config", "cgmd_hub.local.json"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8-sig") as handle:
                    data = json.load(handle)
                if isinstance(data, dict):
                    return data
            except (OSError, json.JSONDecodeError):
                continue
    return {}


def find_binary(*names: str) -> Optional[str]:
    """Return the first executable found on PATH."""
    from shutil import which

    for name in names:
        if not name:
            continue
        found = which(name)
        if found:
            return found
    return None


def resolve_martini3_dir(explicit: Optional[str] = None) -> str:
    """Locate a directory that contains the Martini 3 ``*.itp`` files."""
    candidates: List[str] = []
    if explicit:
        candidates.append(explicit)
    local = load_local_config()
    for key in ("martini3_dir", "martini_dir", "forcefield_dir"):
        value = local.get(key)
        if isinstance(value, str) and value:
            candidates.append(value)
    candidates.extend(DEFAULT_FF_CANDIDATES)

    # pip package `martini_forcefields` (recommended, keeps the licence local)
    try:  # pragma: no cover - depends on the workstation environment
        import martini_forcefields  # type: ignore

        package_root = os.path.dirname(martini_forcefields.__file__)
        candidates.extend(
            sorted(glob.glob(os.path.join(package_root, "**", "gmx_files"), recursive=True))
        )
    except Exception:
        pass

    for candidate in candidates:
        if not candidate:
            continue
        path = os.path.expanduser(os.path.expandvars(candidate))
        if os.path.isdir(path) and glob.glob(os.path.join(path, "**", "*.itp"), recursive=True):
            return os.path.abspath(path)
    raise FileNotFoundError(
        "Martini 3 force field not found. Install it with\n"
        "    pip install martini-forcefields\n"
        "or download martini_v3.0.0 from https://cgmartini.nl and point\n"
        "    CGMD_MARTINI3_DIR=/path/to/gmx_files\n"
        "at the directory that contains martini_v3.0.0.itp."
    )


@dataclass
class Config:
    """Fully resolved settings for one production run."""

    workdir: str
    sequence: str = ""
    peptide_name: str = "peptide"
    structure_pdb: Optional[str] = None
    predictor: Optional[str] = None
    secondary_structure: str = "C"

    lipids: Dict[str, float] = field(default_factory=lambda: {"POPE": 3.0, "POPG": 1.0})
    box_xy_nm: float = 12.0
    box_z_nm: float = 8.0
    salt_m: float = 0.15
    temperature_k: float = 310.0
    area_per_lipid: float = 0.60

    production_ns: float = 1000.0
    equilibration_ns: float = 20.0
    em_steps: int = 5000
    dt_ps: float = 0.02
    gpu_id: int = 0
    ntomp: int = 0
    seed: int = -1
    mdrun_extra: str = ""

    frame_stride_ps: float = 1000.0
    pore_radius_nm: float = 1.2
    water_core_halfheight_nm: float = 0.9
    max_frames: int = 400

    martini3_dir: Optional[str] = None
    gmx_binary: Optional[str] = None
    martinize_binary: Optional[str] = None
    insane_binary: Optional[str] = None
    python_binary: str = ""
    keep_raw: bool = True

    task_id: str = ""
    ntfy_topic: str = "arena-beacon-95bc796a66"
    resume: bool = True
    dry_run: bool = False
    openff_backend: str = "auto"

    # -- helpers ----------------------------------------------------------
    def path(self, *parts: str) -> str:
        return os.path.join(self.workdir, *parts)

    @property
    def prod_nsteps(self) -> int:
        return max(1, int(round(self.production_ns / self.dt_ps * 1000.0)))

    @property
    def eq_nsteps(self) -> int:
        return max(1, int(round(self.equilibration_ns / self.dt_ps * 1000.0)))

    @property
    def compressed_stride(self) -> int:
        """Steps between compressed frames (>= 1 ns by default)."""
        steps = int(round(self.frame_stride_ps / self.dt_ps))
        return max(1, min(steps, max(1, self.prod_nsteps // self.max_frames)))

    @property
    def npt_atom_limit(self) -> int:
        return 10_000_000

    def to_dict(self) -> Dict[str, Any]:
        data = self.__dict__.copy()
        data.update(
            {
                "prod_nsteps": self.prod_nsteps,
                "eq_nsteps": self.eq_nsteps,
                "compressed_stride": self.compressed_stride,
            }
        )
        return data


def config_from_task(task: Dict[str, Any], workdir: str) -> Config:
    """Build a :class:`Config` from a validated task document."""
    peptide = task.get("peptide", {}) or {}
    membrane = task.get("membrane", {}) or {}
    sim = task.get("simulation", {}) or {}
    analysis = task.get("analysis", {}) or {}
    outputs = task.get("outputs", {}) or {}
    local = load_local_config()

    box_xy = float(membrane.get("box_xy_nm") or local.get("box_xy_nm") or 12.0)
    return Config(
        workdir=workdir,
        sequence=peptide.get("sequence", ""),
        peptide_name=peptide.get("name") or "peptide",
        structure_pdb=peptide.get("structure_pdb"),
        predictor=peptide.get("predictor"),
        secondary_structure=peptide.get("secondary_structure") or "C",
        lipids={str(k): float(v) for k, v in (membrane.get("lipids") or {"POPE": 3, "POPG": 1}).items()},
        box_xy_nm=box_xy,
        box_z_nm=float(membrane.get("box_z_nm") or local.get("box_z_nm") or 8.0),
        salt_m=float(membrane.get("salt_M", 0.15)),
        temperature_k=float(membrane.get("temperature_K", 310.0)),
        production_ns=float(sim.get("production_ns", 1000.0)),
        equilibration_ns=float(sim.get("equilibration_ns", 20.0)),
        em_steps=int(sim.get("em_steps", 5000)),
        dt_ps=float(sim.get("dt_fs", 20)) / 1000.0,
        gpu_id=int(sim.get("gpu_id", 0)),
        ntomp=int(sim.get("ntomp", 0)),
        seed=int(sim.get("seed", -1)),
        mdrun_extra=str(sim.get("mdrun_extra", "")),
        frame_stride_ps=float(analysis.get("frame_stride_ps", 1000.0)),
        pore_radius_nm=float(analysis.get("pore_radius_nm", 1.2)),
        water_core_halfheight_nm=float(analysis.get("water_core_halfheight_nm", 0.9)),
        task_id=task.get("task_id", ""),
        ntfy_topic=str(outputs.get("ntfy_topic") or "arena-beacon-95bc796a66"),
        martini3_dir=local.get("martini3_dir"),
        gmx_binary=local.get("gmx_binary"),
        martinize_binary=local.get("martinize_binary"),
        insane_binary=local.get("insane_binary"),
    )
