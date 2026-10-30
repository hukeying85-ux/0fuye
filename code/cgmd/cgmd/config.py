"""Runtime configuration for the CGMD pipeline.

Everything is resolved from (in order of precedence):

1. explicit CLI flags,
2. environment variables (``CGMD_*``),
3. ``skills/cgmd-hub/config/cgmd_hub.local.json`` (gitignored, workstation
   specific paths),
4. sensible defaults that work on the reference Windows + WSL2 GPU box.

The Martini 3 force field is *never* vendored into this repository (it is
third-party material with its own licence).  :func:`resolve_martini3_dir`
therefore looks for it on disk or shallow-clones the upstream git repository.
"""

from __future__ import annotations

import glob
import json
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = [
    "Config",
    "resolve_martini3_dir",
    "fetch_martini_forcefields",
    "find_binary",
    "load_local_config",
    "MARTINI_FF_URL",
    "MARTINI_FF_SUBDIR",
]

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

#: Upstream home of the Martini 3 parameter files.  There is **no PyPI
#: package** called ``martini-forcefields``, so the pipeline clones this
#: repository (shallow) and picks ``regular/v3.0.0/gmx_files`` out of it.
MARTINI_FF_URL = "https://github.com/marrink-lab/martini-forcefields.git"
MARTINI_FF_SUBDIR = os.path.join("regular", "v3.0.0", "gmx_files")

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


def _contains_itp(path: str) -> bool:
    return bool(glob.glob(os.path.join(path, "**", "*.itp"), recursive=True))


def find_gmx_files(root: str) -> Optional[str]:
    """Locate the directory that holds ``martini_v3.0.0*.itp`` under *root*.

    ``marrink-lab/martini-forcefields`` keeps the runnable parameters in
    ``martini_forcefields/regular/v3.0.0/gmx_files`` (the package directory is
    inside the repository, not at its root); older mirrors and hand-made copies
    put them straight in ``regular/v3.0.0/gmx_files`` or at the top level.  All
    of those resolve, and an explicit layout wins so a checkout carrying several
    Martini versions never mixes them.
    """
    if not root or not os.path.isdir(root):
        return None
    direct = [
        os.path.join(root, MARTINI_FF_SUBDIR),
        os.path.join(root, "martini_forcefields", MARTINI_FF_SUBDIR),
        root,
    ]
    for candidate in direct:
        if os.path.isdir(candidate) and glob.glob(os.path.join(candidate, "martini_v3*.itp")):
            return os.path.abspath(candidate)
    for pattern in ("**/" + MARTINI_FF_SUBDIR.replace(os.sep, "/"),
                    "**/gmx_files",
                    "**/martini_v3*.itp"):
        for candidate in sorted(glob.glob(os.path.join(root, pattern), recursive=True)):
            folder = candidate if os.path.isdir(candidate) else os.path.dirname(candidate)
            if glob.glob(os.path.join(folder, "martini_v3*.itp")):
                return os.path.abspath(folder)
    return None


def fetch_martini_forcefields(
    dest: Optional[str] = None,
    url: Optional[str] = None,
    depth: int = 1,
    timeout: int = 900,
    logger: Optional[Any] = None,
) -> str:
    """Shallow-clone the Martini 3 parameters and return the ``gmx_files`` dir.

    PyPI has no ``martini-forcefields`` distribution, so the only automatic
    source is the upstream git repository.  The clone is *shallow* (``--depth
    1``, a handful of MB) and lands in ``<repo>/forcefields/martini-forcefields``
    which ``.gitignore`` keeps out of version control (third-party licence).
    """
    say = logger or (lambda message: None)
    url = url or os.environ.get("CGMD_MARTINI_FF_URL") or MARTINI_FF_URL
    dest = dest or os.environ.get("CGMD_MARTINI_FF_CLONE") or os.path.join(
        REPO_ROOT, "forcefields", "martini-forcefields"
    )
    dest = os.path.abspath(os.path.expanduser(os.path.expandvars(dest)))
    found = find_gmx_files(dest)
    if found:
        say("Martini 3 force field already cloned: {}".format(found))
        return found

    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    if os.path.isdir(os.path.join(dest, ".git")):
        command = ["git", "-C", dest, "fetch", "--depth", str(depth), "origin"]
        say("$ " + " ".join(command))
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        if completed.returncode != 0:
            raise RuntimeError("git fetch of {} failed: {}".format(url, (completed.stderr or completed.stdout or "").strip()[:300]))
        command = ["git", "-C", dest, "reset", "--hard", "FETCH_HEAD"]
    else:
        if os.path.isdir(dest) and os.listdir(dest):
            raise RuntimeError(
                "{} exists but does not contain the Martini 3 files; remove it first".format(dest)
            )
        command = ["git", "clone", "--depth", str(depth), "--single-branch", url, dest]
    say("$ " + " ".join(command))
    completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if completed.returncode != 0:
        raise RuntimeError(
            "git clone of {} failed ({}): {}".format(
                url, completed.returncode, (completed.stderr or completed.stdout or "").strip()[:300]
            )
        )
    found = find_gmx_files(dest)
    if not found:
        raise RuntimeError(
            "{} was cloned but no martini_v3*.itp was found under {}".format(url, dest)
        )
    say("Martini 3 force field ready: {}".format(found))
    return found


def resolve_martini3_dir(
    explicit: Optional[str] = None,
    auto_clone: bool = False,
    clone_root: Optional[str] = None,
    logger: Optional[Any] = None,
) -> str:
    """Locate a directory that contains the Martini 3 ``*.itp`` files.

    Search order: the argument, the workstation-local hub config, the usual
    on-disk locations, an existing ``marrink-lab/martini-forcefields`` checkout
    and (only when *auto_clone* is true) a fresh shallow clone of that
    repository.  PyPI is deliberately not consulted: no such distribution
    exists, and a stale pip name in the error message only wastes a round trip.
    """
    candidates: List[str] = []
    if explicit:
        candidates.append(explicit)
    local = load_local_config()
    for key in ("martini3_dir", "martini_dir", "forcefield_dir"):
        value = local.get(key)
        if isinstance(value, str) and value:
            candidates.append(value)
    candidates.extend(DEFAULT_FF_CANDIDATES)

    # an existing clone from a previous run (cheap, no network)
    clone_dest = clone_root or os.path.join(REPO_ROOT, "forcefields", "martini-forcefields")
    candidates.append(clone_dest)

    for candidate in candidates:
        if not candidate:
            continue
        path = os.path.expanduser(os.path.expandvars(candidate))
        if not os.path.isdir(path):
            continue
        resolved = find_gmx_files(path) or path
        if _contains_itp(resolved):
            return os.path.abspath(resolved)

    if auto_clone:
        return fetch_martini_forcefields(dest=clone_dest, logger=logger)

    raise FileNotFoundError(
        "Martini 3 force field not found. The parameters are not on PyPI; fetch them with\n"
        "    git clone --depth 1 {} {}\n"
        "and point\n"
        "    CGMD_MARTINI3_DIR={}\n"
        "at that directory (or pass --martini3-dir / --fetch-forcefield).".format(
            MARTINI_FF_URL,
            clone_dest,
            os.path.join(clone_dest, MARTINI_FF_SUBDIR),
        )
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
    #: Shallow-clone marrink-lab/martini-forcefields when nothing is found.
    fetch_forcefield: bool = True
    #: Wall-clock ceiling per mdrun call (hours).  0 = run to the last step.
    #: A positive value lets one mdrun return cleanly with a checkpoint before
    #: a mailbox/job-level timeout fires, and the next call continues from it.
    maxh_hours: float = 0.0
    #: Longest single production segment (ns).  0 = the whole production run.
    segment_ns: float = 0.0

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

    @property
    def mdrun_gpu_flags(self) -> List[str]:
        """Martini 3 uses reaction-field: there is no PME to place on the GPU."""
        return ["-nb", "gpu", "-bonded", "gpu", "-gpu_id", str(self.gpu_id)]

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
        fetch_forcefield=bool(local.get("fetch_forcefield", True)),
        maxh_hours=float(sim.get("maxh_hours", 0.0) or 0.0),
        segment_ns=float(sim.get("segment_ns", 0.0) or 0.0),
    )
