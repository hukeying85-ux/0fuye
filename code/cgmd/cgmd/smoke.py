"""Real GROMACS smoke test: build a tiny Martini 3 water box and run 100 ps.

Why this exists
---------------
"GROMACS is installed" is not the same as "GROMACS can integrate".  This module
proves the latter on the workstation itself and returns a self-contained report
with the version of every moving part, so the answer travels back through git
without anybody logging into the machine.

It is deliberately independent of the peptide pipeline:

* no Martinize, no insane, no Martini lipid library is required;
* the box is a plain grid of Martini 3 ``W`` beads written directly to ``.gro``;
* the topology only includes the force-field base file plus the water itp, both
  located with a tiny built-in itp scanner (no Python 3.7+ dependency);
* energy minimisation (steep) then ``ps`` picoseconds of NPT at ``dt`` = 2 fs /
  0.02 ps, exactly the settings the production pipeline uses.

Report schema: ``cgmd.gmxsmoke.v1`` (see :func:`validate_report`).

CLI
---
    python3 -m cgmd.smoke --ps 100 --gpu-id 0 \\
        --workdir ~/cgmd-runs/smoke --out results/status/gmx_smoke.json
    python3 -m cgmd.smoke --show results/status/gmx_smoke.json
"""

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Sequence

SCHEMA = "cgmd.gmxsmoke.v1"

# Martini 3 water: one W bead stands for four water molecules, so a 1000 kg/m3
# box holds one bead every ~0.49 nm.
WATER_SPACING_NM = 0.49

BONDS_NM = 3.0

STATUS_OK = "ok"
STATUS_FAIL = "fail"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


# ---------------------------------------------------------------------------
# software inventory
# ---------------------------------------------------------------------------
def _run(command: Sequence[str], timeout: int = 60, cwd: Optional[str] = None) -> Dict[str, Any]:
    started = time.time()
    try:
        # universal_newlines/text=True and capture_output= only exist on newer
        # interpreters; Ubuntu 18.04 still ships Python 3.6, so stay explicit.
        completed = subprocess.run(
            list(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=timeout,
            cwd=cwd,
        )
        return {
            "command": " ".join(command),
            "returncode": completed.returncode,
            "stdout": completed.stdout or "",
            "stderr": completed.stderr or "",
            "seconds": round(time.time() - started, 2),
        }
    except FileNotFoundError as exc:
        return {"command": " ".join(command), "returncode": 127, "stdout": "", "stderr": str(exc), "seconds": 0.0}
    except subprocess.TimeoutExpired:
        return {"command": " ".join(command), "returncode": 124, "stdout": "", "stderr": "timeout", "seconds": timeout}


def parse_version(text: str) -> Dict[str, Any]:
    """Pull the interesting fields out of ``gmx --version``."""
    def grab(pattern: str) -> Optional[str]:
        match = re.search(pattern, text, re.MULTILINE)
        return match.group(1).strip() if match else None

    info = {
        "version": grab(r"GROMACS version:\s*(\S+)"),
        "precision": grab(r"Precision:\s*(\S+)"),
        "memory_model": grab(r"Memory model:\s*(.+?)\.?\s*$"),
        "simd": grab(r"SIMD instructions:\s*(.+?)\s*$"),
        "gpu_support": grab(r"GPU support:\s*(.+?)\s*$"),
        "cuda_runtime": grab(r"CUDA runtime:\s*(.+?)\s*$"),
        "cuda_driver": grab(r"CUDA driver:\s*(.+?)\s*$"),
        "fft": grab(r"FFT library:\s*(.+?)\s*$"),
        "openmp": grab(r"OpenMP:\s*(.+?)\s*$"),
        "mpi": grab(r"MPI:\s*(.+?)\s*$"),
        "compiler": grab(r"(?:GCC|Clang|CC)\s+[^:]*:\s*(.+?)\s*$"),
        "base_arch": grab(r"Base build CPU arch:\s*(.+?)\s*$"),
    }
    info["cuda"] = bool(info.get("gpu_support") and "cuda" in info["gpu_support"].lower())
    return info


def parse_gpu(text: str) -> List[Dict[str, Any]]:
    """One entry per GPU from ``nvidia-smi --query-gpu=name,driver_version,memory.total``."""
    devices = []
    for line in (text or "").splitlines():
        parts = [piece.strip() for piece in line.split(",")]
        if len(parts) < 3 or not parts[0]:
            continue
        devices.append({"name": parts[0], "driver": parts[1], "memory": parts[2]})
    return devices


def software_inventory(gmx: Optional[str] = None) -> Dict[str, Any]:
    """Everything a reviewer needs to reproduce the run."""
    inventory: Dict[str, Any] = {
        "generated_at": _now(),
        "hostname": platform.node(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "cwd": os.getcwd(),
        "packages": {},
        "tools": {},
    }
    for module in ("numpy", "MDAnalysis", "vermouth", "matplotlib", "insane"):
        try:
            imported = __import__(module)
            inventory["packages"][module] = getattr(imported, "__version__", "unknown")
        except Exception as exc:  # noqa: BLE001 - reported, never raised
            inventory["packages"][module] = "missing ({})".format(type(exc).__name__)

    for name in ("gmx", "gmx_mpi", "martinize2", "insane", "gcc", "nvidia-smi"):
        inventory["tools"][name] = shutil.which(name)

    nvidia = inventory["tools"].get("nvidia-smi")
    if nvidia:
        result = _run([nvidia, "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"], timeout=30)
        inventory["gpus"] = parse_gpu(result["stdout"])
    else:
        inventory["gpus"] = []

    inventory["gromacs"] = {
        "version": None,
        "executable": gmx,
        "available": False,
        "gpu_support": None,
        "cuda": False,
    }
    if gmx:
        result = _run([gmx, "--version"], timeout=60)
        inventory["gromacs"] = parse_version(result["stdout"] + "\n" + result["stderr"])
        inventory["gromacs"]["executable"] = gmx
        inventory["gromacs"]["available"] = bool(inventory["gromacs"].get("version"))
        inventory["gromacs"]["raw"] = (result["stdout"] or result["stderr"]).strip().splitlines()[:40]

    try:
        from .config import resolve_martini3_dir

        inventory["martini3_dir"] = resolve_martini3_dir(None)
    except Exception as exc:  # noqa: BLE001
        inventory["martini3_dir"] = None
        inventory["martini3_error"] = str(exc)[:300]
    return inventory


# ---------------------------------------------------------------------------
# the tiny system
# ---------------------------------------------------------------------------
def write_water_box(path: str, bonds_nm: float = BONDS_NM, spacing: float = WATER_SPACING_NM) -> int:
    """Write a cubic box of Martini ``W`` beads to a ``.gro`` file."""
    edge = float(bonds_nm)
    count_per_axis = int(round(edge / spacing))
    if count_per_axis < 2:
        count_per_axis = 2
    step = edge / count_per_axis
    atoms = 0
    lines = ["CGMD smoke test: Martini 3 water box", "{:d}".format(0)]
    for i in range(count_per_axis):
        for j in range(count_per_axis):
            for k in range(count_per_axis):
                atoms += 1
                x = (i + 0.5) * step
                y = (j + 0.5) * step
                z = (k + 0.5) * step
                lines.append(
                    "{:5d}{:<5s}{:>5s}{:5d}{:8.3f}{:8.3f}{:8.3f}".format(1, "W", "W", atoms, x, y, z)
                )
    lines[1] = "{:d}".format(atoms)
    lines.append("{:10.5f}{:10.5f}{:10.5f}".format(edge, edge, edge))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return atoms


def scan_force_field(ff_roots: Sequence[str]) -> Dict[str, Any]:
    """Find the base file and the Martini water itp without third-party deps.

    Deliberately re-implemented here (instead of importing
    :mod:`cgmd.topology`) so the smoke test also runs on Python 3.6, which is
    what Ubuntu 18.04 ships.
    """
    import glob

    base_files: List[str] = []
    water_file: Optional[str] = None
    water_atoms = 0
    for root in ff_roots:
        if not root or not os.path.isdir(root):
            continue
        for candidate in sorted(glob.glob(os.path.join(root, "**", "*.itp"), recursive=True)):
            try:
                with open(candidate, "r", encoding="utf-8", errors="replace") as handle:
                    text = handle.read()
            except OSError:
                continue
            if re.search(r"^\s*\[\s*(?:defaults|atomtypes)\s*\]", text, re.MULTILINE):
                if candidate not in base_files:
                    base_files.append(candidate)
            if water_file is None:
                for match in re.finditer(
                    r"\[\s*moleculetype\s*\]\s*\n\s*W\s+(\d+)\s*\n(.+?)(?=\n\s*\[\s*moleculetype|\Z)",
                    text,
                    re.DOTALL,
                ):
                    water_file = candidate
                    water_atoms = text[match.start():match.end()].count("\n") and len(
                        [
                            line
                            for line in text[match.start():match.end()].splitlines()
                            if re.match(r"^\s*\d+\s+\S+\s+\d+\s+W\s+", line)
                        ]
                    )
                    break
    return {"base_files": base_files, "water_file": water_file, "water_atoms": water_atoms}


def write_water_topology(path: str, ff_roots: Sequence[str], molecules: int) -> Dict[str, Any]:
    """Minimal ``.top``: base file + water itp + ``[ molecules ] W n``."""
    found = scan_force_field(ff_roots)
    if not found["base_files"]:
        raise RuntimeError(
            "no Martini force-field base file found under {} (pip install martini-forcefields)".format(list(ff_roots))
        )
    if not found["water_file"]:
        raise RuntimeError("moleculetype 'W' (Martini water) is missing from {}".format(list(ff_roots)))
    base = found["base_files"][0]
    water_file = found["water_file"]
    top_dir = os.path.dirname(os.path.abspath(path))
    lines: List[str] = [
        "; CGMD smoke test -- generated by cgmd/smoke.py",
        '#include "{}"'.format(_include_path(base, top_dir)),
    ]
    if os.path.abspath(water_file) != os.path.abspath(base):
        lines.append('#include "{}"'.format(_include_path(water_file, top_dir)))
    lines += [
        "",
        "[ system ]",
        "CGMD Martini 3 water box",
        "",
        "[ molecules ]",
        "W {:d}".format(int(molecules)),
        "",
    ]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    return {
        "path": path,
        "base_file": base,
        "water_itp": water_file,
        "water_atoms": found["water_atoms"],
        "molecules": int(molecules),
    }


def _include_path(target: str, top_dir: str) -> str:
    try:
        relative = os.path.relpath(os.path.abspath(target), os.path.abspath(top_dir))
    except ValueError:  # different drive on Windows
        relative = os.path.abspath(target)
    return relative.replace(os.sep, "/")


EM_MDP = """\
integrator              = steep
emtol                   = 500.0
emstep                  = 0.005
nsteps                  = 500
nstlist                 = 10
cutoff-scheme           = Verlet
verlet-buffer-tolerance = 0.005
pbc                     = xyz
coulombtype             = reaction-field
rcoulomb                = 1.1
epsilon_r               = 15
epsilon_rf              = 0
vdwtype                 = cutoff
vdw-modifier            = Potential-shift
rvdw                    = 1.1
"""

MD_MDP = """\
integrator              = md
dt                      = 0.02
nsteps                  = {nsteps}
comm-mode               = linear
nstcomm                 = 10
constraints             = none
continuation            = no
gen-vel                 = yes
gen-temp                = {temperature}
gen-seed                = -1
nstlist                 = 10
cutoff-scheme           = Verlet
verlet-buffer-tolerance = 0.005
pbc                     = xyz
coulombtype             = reaction-field
rcoulomb                = 1.1
epsilon_r               = 15
epsilon_rf              = 0
vdwtype                 = cutoff
vdw-modifier            = Potential-shift
rvdw                    = 1.1
tcoupl                  = v-rescale
tc-grps                 = System
tau-t                   = 1.0
ref-t                   = {temperature}
pcoupl                  = c-rescale
pcoupltype              = isotropic
tau-p                   = 4.0
compressibility         = 3e-4
ref-p                   = 1.0
nstxout                 = 0
nstvout                 = 0
nstfout                 = 0
nstenergy               = 50
nstlog                  = 50
nstcalcenergy           = 10
nstxout-compressed      = {nstxout_compressed}
compressed-x-grps       = System
"""


def parse_md_log(text: str) -> Dict[str, Any]:
    """Steps, simulated time, performance and the convergence lines of a md.log."""
    info: Dict[str, Any] = {
        "performance_ns_per_day": None,
        "steps_requested": None,
        "steps_done": None,
        "dt_ps": None,
        "simulated_ps": None,
        "wall_seconds": None,
        "finished": "Finished mdrun" in text,
        "fatal": None,
    }
    match = re.search(r"Performance:\s+([0-9.]+)", text)
    if match:
        info["performance_ns_per_day"] = float(match.group(1))
    match = re.search(r"^\s*nsteps\s*=\s*(\d+)", text, re.MULTILINE)
    if match:
        info["steps_requested"] = int(match.group(1))
    match = re.search(r"^\s*dt\s*=\s*([0-9.eE+-]+)", text, re.MULTILINE)
    if match:
        info["dt_ps"] = float(match.group(1))
    if info["steps_requested"] is not None and info["dt_ps"] is not None:
        info["simulated_ps"] = round(info["steps_requested"] * info["dt_ps"], 4)

    # last "Step Time" sample, e.g. "      1000        20.00000"
    samples = re.findall(r"^\s*(\d+)\s+([0-9.]+)\s*$", text, re.MULTILINE)
    if samples:
        info["steps_done"] = int(samples[-1][0])
        info["time_ps"] = float(samples[-1][1])
    for marker in ("Fatal error", "There is no domain decomposition", "GPU API call failed", "CUDA error"):
        if marker in text:
            remainder = text.split(marker, 1)[1].strip().lstrip(":").strip()
            info["fatal"] = remainder.splitlines()[0][:200] if remainder else marker
            break
    match = re.search(r"Performance:\s+[0-9.]+\s+([0-9.]+)", text)
    if match:
        info["wall_seconds"] = round(float(match.group(1)) * 60.0, 2)
    return info


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------
def _tail(path: str, lines: int = 25) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return [line.rstrip("\n") for line in handle.readlines()[-lines:]]
    except OSError:
        return []


def run_smoke(
    ps: float = 100.0,
    gpu_id: int = 0,
    workdir: Optional[str] = None,
    temperature: float = 310.0,
    ntomp: int = 4,
    gmx_binary: Optional[str] = None,
    martini3_dir: Optional[str] = None,
    timeout: int = 1800,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Minimise then integrate ``ps`` picoseconds; return the report document."""
    workdir = os.path.abspath(workdir or os.path.join(os.path.expanduser("~"), "cgmd-runs", "smoke"))
    os.makedirs(workdir, exist_ok=True)

    report: Dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": _now(),
        "status": STATUS_FAIL,
        "ok": False,
        "ps_requested": float(ps),
        "ps_completed": 0.0,
        "workdir": workdir,
        "gpu_id": int(gpu_id),
        "temperature_K": float(temperature),
        "dt_ps": 0.02,
        "steps": {},
        "stages": [],
        "stage_error": None,
        "notes": [],
        "software": {},
        "system": {},
    }

    gmx = gmx_binary
    if gmx and not (os.path.isfile(gmx) and os.access(gmx, os.X_OK)):
        gmx = None                      # an explicit path that does not exist
    if not gmx:
        try:
            from .engine import resolve_gmx

            gmx = resolve_gmx(None)
        except FileNotFoundError:
            gmx = None

    inventory = software_inventory(gmx)
    if martini3_dir:
        inventory["martini3_dir"] = martini3_dir
    report["software"] = inventory
    report["host"] = {
        "hostname": inventory["hostname"],
        "platform": inventory["platform"],
        "python": inventory["python"],
        "gpus": inventory.get("gpus", []),
        "gromacs": (inventory.get("gromacs") or {}).get("version"),
    }

    if gmx is None:
        report["stage_error"] = "GROMACS executable not found (gmx / gmx_mpi); nothing to integrate with"
        report["notes"].append("install: sudo apt install gromacs | conda install -c conda-forge gromacs")
        return report
    report["gmx_binary"] = gmx

    # --- 1. build the system -------------------------------------------------
    gro = os.path.join(workdir, "smoke_box.gro")
    top = os.path.join(workdir, "smoke_box.top")
    atoms = write_water_box(gro)
    roots: List[str] = []
    for candidate in (martini3_dir, inventory.get("martini3_dir")):
        if candidate and os.path.isdir(candidate):
            roots.append(candidate)
            if scan_force_field([candidate])["base_files"]:
                break
    try:
        topology = write_water_topology(top, roots, atoms)
    except Exception as exc:  # noqa: BLE001 - reported, never raised
        report["system"] = {"atoms": atoms, "gro": gro, "box_nm": BONDS_NM}
        report["stage_error"] = "topology: {}".format(exc)
        report["notes"].append("pip install martini-forcefields, or set CGMD_MARTINI3_DIR")
        return report

    report["system"] = {
        "kind": "martini3-water-box",
        "atoms": atoms,
        "molecules": atoms,
        "box_nm": [BONDS_NM, BONDS_NM, BONDS_NM],
        "gro": gro,
        "top": top,
        "topology": topology,
    }

    # --- 2. mdp files --------------------------------------------------------
    em_mdp = os.path.join(workdir, "smoke_em.mdp")
    md_mdp = os.path.join(workdir, "smoke_md.mdp")
    steps = int(round(float(ps) / 0.02))
    report["steps"]["md"] = steps
    with open(em_mdp, "w", encoding="utf-8") as handle:
        handle.write(EM_MDP)
    with open(md_mdp, "w", encoding="utf-8") as handle:
        handle.write(
            MD_MDP.format(
                nsteps=steps,
                temperature=int(temperature),
                nstxout_compressed=max(1, steps // 20),
            )
        )

    if dry_run:
        report["notes"].append("dry run: nothing executed")
        report["status"] = "dry-run"
        return report

    def stage(name: str, command: List[str], expect: Sequence[str] = ()) -> bool:
        result = _run(command, timeout=timeout, cwd=workdir)
        entry = {
            "stage": name,
            "command": " ".join(command),
            "returncode": result["returncode"],
            "seconds": result["seconds"],
            "stderr_tail": result["stderr"].strip().splitlines()[-6:],
        }
        text = result["stdout"] + result["stderr"]
        missing = [token for token in expect if token not in text]
        entry["missing_markers"] = missing
        report["stages"].append(entry)
        return result["returncode"] == 0 and not missing

    # --- 3. energy minimisation ---------------------------------------------
    if not stage("grompp-em", [gmx, "grompp", "-f", "smoke_em.mdp", "-c", "smoke_box.gro",
                               "-p", "smoke_box.top", "-o", "smoke_em.tpr", "-maxwarn", "2"]):
        report["stage_error"] = "grompp (energy minimisation) failed"
        report["seconds_total"] = round(sum(entry["seconds"] for entry in report["stages"]), 2)
        return report
    if not stage("mdrun-em", [gmx, "mdrun", "-deffnm", "smoke_em", "-nb", "cpu", "-ntomp", str(ntomp)],
                 expect=("Steepest Descents",)):
        report["stage_error"] = "mdrun (energy minimisation) failed"
        report["seconds_total"] = round(sum(entry["seconds"] for entry in report["stages"]), 2)
        return report
    report["stages"][-1]["em_log_tail"] = _tail(os.path.join(workdir, "smoke_em.log"), 8)

    # --- 4. 100 ps of dynamics ----------------------------------------------
    if not stage("grompp-md", [gmx, "grompp", "-f", "smoke_md.mdp", "-c", "smoke_em.gro",
                               "-p", "smoke_box.top", "-o", "smoke_md.tpr", "-maxwarn", "2"]):
        report["stage_error"] = "grompp (production) failed"
        report["seconds_total"] = round(sum(entry["seconds"] for entry in report["stages"]), 2)
        return report

    mdrun_base = [gmx, "mdrun", "-deffnm", "smoke_md", "-ntomp", str(ntomp)]
    # -pme / -bonded thread assignment only exists in GROMACS >= 2021; older
    # builds (Ubuntu 18.04 ships 2018/2019) reject those flags outright.
    version_text = str(((report.get("software") or {}).get("gromacs") or {}).get("version") or "")
    major = 0
    match_major = re.match(r"(\d{4})", version_text)
    if match_major:
        major = int(match_major.group(1))
    if major and major < 2021:
        gpu_args = ["-nb", "gpu", "-gpu_id", str(gpu_id)]
        report["notes"].append("GROMACS {} is older than 2021: using -nb gpu only".format(version_text))
    else:
        gpu_args = ["-nb", "gpu", "-pme", "cpu", "-bonded", "gpu", "-gpu_id", str(gpu_id)]
    used = "gpu"
    if not stage("mdrun-md-gpu", mdrun_base + gpu_args):
        used = "cpu"
        report["notes"].append("GPU mdrun failed, retried with -nb cpu (see stages for the GPU error)")
        for artifact in ("smoke_md.log", "smoke_md.edr", "smoke_md.xtc", "smoke_md.gro", "smoke_md.cpt"):
            path = os.path.join(workdir, artifact)
            if os.path.exists(path):
                os.remove(path)
        if not stage("mdrun-md-cpu", mdrun_base + ["-nb", "cpu"]):
            report["stage_error"] = "mdrun (production) failed on GPU and on CPU"
            report["seconds_total"] = round(sum(entry["seconds"] for entry in report["stages"]), 2)
            return report
    report["accelerator"] = used

    # --- 5. verdict ----------------------------------------------------------
    log_path = os.path.join(workdir, "smoke_md.log")
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
            log_text = handle.read()
    except OSError:
        log_text = ""
    log = parse_md_log(log_text)
    report["mdrun"] = log
    report["ps_completed"] = log.get("time_ps") or 0.0
    if not report["ps_completed"] and log["simulated_ps"]:
        report["ps_completed"] = log["simulated_ps"] if log["finished"] else 0.0
    report["log_tail"] = _tail(log_path, 20)
    report["files"] = sorted(
        name for name in os.listdir(workdir) if os.path.isfile(os.path.join(workdir, name))
    )

    tolerance = 0.999
    integrated = report["ps_completed"] >= float(ps) * tolerance - 1e-9
    if log["fatal"]:
        report["stage_error"] = "GROMACS reported: {}".format(log["fatal"])
    elif not integrated:
        report["stage_error"] = "only {:.3f} of {:.1f} ps integrated".format(report["ps_completed"], ps)
    elif not log["finished"]:
        report["stage_error"] = "mdrun produced no 'Finished mdrun' line"

    report["ok"] = bool(integrated and log["finished"] and not log["fatal"])
    report["status"] = STATUS_OK if report["ok"] else STATUS_FAIL
    report["seconds_total"] = round(sum(entry["seconds"] for entry in report["stages"]), 2)
    return report


# ---------------------------------------------------------------------------
# report helpers
# ---------------------------------------------------------------------------
def validate_report(report: Dict[str, Any]) -> List[str]:
    problems: List[str] = []
    if not isinstance(report, dict):
        return ["report must be a JSON object"]
    if report.get("schema") != SCHEMA:
        problems.append("schema must be {}".format(SCHEMA))
    if report.get("status") not in (STATUS_OK, STATUS_FAIL, "dry-run"):
        problems.append("status must be ok/fail/dry-run")
    for key in ("ps_requested", "ps_completed"):
        if not isinstance(report.get(key), (int, float)):
            problems.append(key + " must be a number")
    if not isinstance(report.get("stages"), list):
        problems.append("stages must be a list")
    software = report.get("software")
    if not isinstance(software, dict):
        problems.append("software is required")
    else:
        if not isinstance(software.get("gromacs"), dict):
            problems.append("software.gromacs is required")
        if not isinstance(software.get("packages"), dict):
            problems.append("software.packages is required")
    if report.get("status") == STATUS_OK and not report.get("ok"):
        problems.append("status ok requires ok=true")
    return problems


def summarise(report: Dict[str, Any]) -> str:
    software = report.get("software") or {}
    gromacs = software.get("gromacs") or {}
    gpus = (software.get("gpus") or [{}])
    gpu = gpus[0].get("name") if gpus else "no GPU"
    return "{} | gmx {} ({}) | {} ps on {} | {:.1f}s | {}".format(
        (report.get("status") or "?").upper(),
        gromacs.get("version") or "n/a",
        gromacs.get("gpu_support") or "n/a",
        report.get("ps_completed"),
        report.get("accelerator", gpu),
        report.get("seconds_total") or 0.0,
        report.get("stage_error") or "integrated",
    )


def format_report(report: Dict[str, Any]) -> str:
    software = report.get("software") or {}
    gromacs = software.get("gromacs") or {}
    lines = [
        "status          : {}".format(report.get("status")),
        "generated       : {}".format(report.get("generated_at")),
        "host            : {}".format((report.get("host") or {}).get("hostname")),
        "os              : {}".format(software.get("platform")),
        "python          : {}".format(software.get("python")),
        "gromacs         : {} ({})".format(gromacs.get("version"), gromacs.get("executable")),
        "  precision     : {}".format(gromacs.get("precision")),
        "  simd          : {}".format(gromacs.get("simd")),
        "  gpu support   : {}".format(gromacs.get("gpu_support")),
        "  cuda runtime  : {}".format(gromacs.get("cuda_runtime")),
        "  fft           : {}".format(gromacs.get("fft")),
        "gpus            : {}".format(
            "; ".join("{} ({} {})".format(g.get("name"), g.get("memory"), g.get("driver")) for g in (software.get("gpus") or []))
            or "none detected"
        ),
        "packages        : {}".format(", ".join("{} {}".format(k, v) for k, v in (software.get("packages") or {}).items())),
        "martini3        : {}".format(software.get("martini3_dir") or "not found"),
        "system          : {} atoms, box {} nm".format(
            (report.get("system") or {}).get("atoms"), (report.get("system") or {}).get("box_nm")
        ),
        "integration     : {:.3f} / {} ps ({})".format(
            report.get("ps_completed") or 0.0, report.get("ps_requested"), report.get("accelerator", "?")
        ),
        "performance     : {} ns/day".format((report.get("mdrun") or {}).get("performance_ns_per_day")),
        "wall            : {} s".format(report.get("seconds_total")),
    ]
    if report.get("stage_error"):
        lines.append("error           : {}".format(report["stage_error"]))
    for note in report.get("notes") or []:
        lines.append("note            : {}".format(note))
    return "\n".join(lines)


def dump(report: Dict[str, Any], path: str) -> str:
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="cgmd.smoke", description="100 ps GROMACS smoke test")
    parser.add_argument("--ps", type=float, default=100.0)
    parser.add_argument("--gpu-id", dest="gpu_id", type=int, default=0)
    parser.add_argument("--workdir", default=None)
    parser.add_argument("--temperature", type=float, default=310.0)
    parser.add_argument("--ntomp", type=int, default=4)
    parser.add_argument("--gmx", dest="gmx", default=None)
    parser.add_argument("--martini3-dir", dest="martini3_dir", default=None)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--out", default=None)
    parser.add_argument("--dry-run", dest="dry_run", action="store_true")
    parser.add_argument("--show", default=None, help="only render an existing report")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.show:
        with open(args.show, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        print(format_report(loaded))
        return 0 if loaded.get("ok") else 1

    report = run_smoke(
        ps=args.ps,
        gpu_id=args.gpu_id,
        workdir=args.workdir,
        temperature=args.temperature,
        ntomp=args.ntomp,
        gmx_binary=args.gmx,
        martini3_dir=args.martini3_dir,
        timeout=args.timeout,
        dry_run=args.dry_run,
    )
    if args.out:
        dump(report, args.out)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif not args.json:
        print(format_report(report))
    if args.out:
        print("")
        print(summarise(report))
        print("report: " + os.path.abspath(args.out))
    return 0 if report.get("ok") else 3


if __name__ == "__main__":
    sys.exit(main())
