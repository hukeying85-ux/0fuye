"""GROMACS command construction, execution and environment probing.

The module is deliberately thin: every command is built as a list of arguments
(never a shell string), printed into the run log, and executed with
``subprocess`` while streaming to a per-stage ``.out`` file.  ``--dry-run``
prints the same plan without touching the GPU, which makes the pipeline
testable on machines without GROMACS.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Sequence

__all__ = [
    "Gromacs",
    "StageError",
    "render_mdp",
    "resolve_gmx",
    "probe_gpu",
    "probe_environment",
]

MDP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mdp")


class StageError(RuntimeError):
    """Raised when an external tool exits non-zero."""

    def __init__(self, message: str, command: Sequence[str], returncode: int, tail: str = "") -> None:
        super().__init__(message)
        self.command = list(command)
        self.returncode = returncode
        self.tail = tail


def resolve_gmx(explicit: Optional[str] = None) -> str:
    """Find the GROMACS driver (``gmx``, ``gmx_mpi`` or ``gmx.exe``)."""
    candidates = [explicit] if explicit else []
    candidates += ["gmx", "gmx_mpi", "gmx.exe", "gmx_mpi.exe"]
    for candidate in candidates:
        if not candidate:
            continue
        found = shutil.which(candidate)
        if found:
            return found
    raise FileNotFoundError(
        "GROMACS executable 'gmx' not found on PATH. In WSL2 run\n"
        "    sudo apt install gromacs\n"
        "or activate the conda env that provides GROMACS (`conda activate cgmd`)."
    )


def render_mdp(template_path: str, output_path: str, values: Dict[str, Any]) -> str:
    """Render a ``.mdp.in`` template by replacing ``@TOKEN@`` placeholders."""
    with open(template_path, "r", encoding="utf-8") as handle:
        text = handle.read()

    def replace(match: "re.Match[str]") -> str:
        token = match.group(1)
        if token in values:
            return str(values[token])
        return ""

    rendered = re.sub(r"@([A-Z0-9_]+)@", replace, text)
    leftovers = sorted(set(re.findall(r"@([A-Z0-9_]+)@", rendered)))
    if leftovers:
        raise KeyError("unresolved mdp placeholders: {}".format(", ".join(leftovers)))
    with open(output_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(rendered)
    return output_path


def probe_gpu() -> Dict[str, Any]:
    """Query NVIDIA GPUs through ``nvidia-smi`` (empty dict when absent)."""
    info: Dict[str, Any] = {"available": False, "devices": []}
    exe = shutil.which("nvidia-smi")
    if not exe:
        return info
    try:
        completed = subprocess.run(
            [exe, "--query-gpu=index,name,memory.total,driver_version,compute_cap",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return info
    if completed.returncode != 0:
        info["error"] = (completed.stderr or "").strip()[:300]
        return info
    for line in completed.stdout.strip().splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 3:
            info["devices"].append(
                {
                    "index": parts[0],
                    "name": parts[1],
                    "memory_mb": parts[2],
                    "driver": parts[3] if len(parts) > 3 else None,
                    "compute_capability": parts[4] if len(parts) > 4 else None,
                }
            )
    info["available"] = bool(info["devices"])
    return info


def probe_environment(cfg: Any = None) -> Dict[str, Any]:
    """Collect a machine-readable self-check report (GPUs, GROMACS, tools)."""
    report: Dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "gpu": probe_gpu(),
        "tools": {},
    }
    for key, names in (
        ("gromacs", ["gmx", "gmx_mpi"]),
        ("martinize2", ["martinize2"]),
        ("insane", ["insane"]),
        ("insane_python", ["python3", "python"]),
    ):
        found = None
        for name in names:
            found = shutil.which(name)
            if found:
                break
        report["tools"][key] = found
    gmx = report["tools"].get("gromacs")
    if gmx:
        try:
            completed = subprocess.run([gmx, "--version"], capture_output=True, text=True, timeout=30)
            text = completed.stdout or ""
            version = re.search(r"GROMACS version:\s*(\S+)", text)
            gpu_support = re.search(r"GPU support:\s*(.+)", text)
            report["gromacs"] = {
                "executable": gmx,
                "version": version.group(1) if version else None,
                "gpu_support": gpu_support.group(1).strip() if gpu_support else None,
                "cuda": bool(re.search(r"CUDA", text, re.IGNORECASE)),
            }
        except (OSError, subprocess.SubprocessError) as exc:
            report["gromacs"] = {"executable": gmx, "error": str(exc)[:300]}
    if cfg is not None:
        try:
            from .config import resolve_martini3_dir

            report["martini3_dir"] = resolve_martini3_dir(cfg.martini3_dir)
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            report["martini3_dir"] = None
            report["martini3_error"] = str(exc)[:500]
    return report


class Gromacs:
    """Thin wrapper around ``gmx grompp`` / ``gmx mdrun``."""

    def __init__(self, config: Any, logger: Optional[Any] = None) -> None:
        self.cfg = config
        self.log = logger or (lambda message: print(message, flush=True))
        # construction never fails: mdp rendering / plan inspection must work on
        # a laptop without GROMACS.  The first real grompp/mdrun then reports the
        # actionable install message below.
        try:
            self.exe = config.gmx_binary or resolve_gmx(None)
        except FileNotFoundError:
            self.exe = config.gmx_binary or "gmx"
            self.missing_gmx = True
        else:
            self.missing_gmx = False
        self.commands: List[List[str]] = []

    # -- primitives -------------------------------------------------------
    def _record(self, command: Sequence[str]) -> None:
        self.commands.append(list(command))
        self.log("$ " + " ".join(shlex.quote(part) for part in command))

    def run(
        self,
        command: Sequence[str],
        log_path: Optional[str] = None,
        check: bool = True,
        timeout: Optional[float] = None,
        cwd: Optional[str] = None,
    ) -> int:
        """Run a command, tee stdout/stderr into ``log_path``."""
        if getattr(self, "missing_gmx", False) and not self.cfg.dry_run:
            raise StageError(
                "GROMACS executable 'gmx' not found on PATH. In WSL2 run "
                "'sudo apt install gromacs' or activate the conda env that provides GROMACS.",
                command, 127, "",
            )
        self._record(command)
        if log_path:
            parent = os.path.dirname(os.path.abspath(log_path))
            if parent:
                os.makedirs(parent, exist_ok=True)
        if self.cfg.dry_run:
            if log_path:
                with open(log_path, "a", encoding="utf-8") as handle:
                    handle.write("[dry-run] " + " ".join(command) + "\n")
            return 0
        started = time.time()
        with open(log_path, "a" if log_path else os.devnull, encoding="utf-8") if log_path else open(os.devnull, "w") as handle:
            completed = subprocess.run(
                list(command),
                cwd=cwd or self.cfg.workdir,
                stdout=handle,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
        self.log("  -> exit {} in {:.1f}s".format(completed.returncode, time.time() - started))
        if check and completed.returncode != 0:
            tail = ""
            if log_path and os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8", errors="replace") as reader:
                    tail = "".join(reader.readlines()[-40:])
            raise StageError(
                "command failed: {}".format(" ".join(command[:3])),
                command,
                completed.returncode,
                tail,
            )
        return completed.returncode

    def grompp(
        self,
        stage: str,
        mdp: str,
        conf: str,
        top: str,
        tpr: str,
        ndx: Optional[str] = None,
        maxwarn: int = 2,
        extra: Sequence[str] = (),
    ) -> int:
        command = [self.exe, "grompp", "-f", mdp, "-c", conf, "-p", top, "-o", tpr, "-maxwarn", str(maxwarn)]
        if ndx:
            command += ["-n", ndx]
        command += list(extra)
        return self.run(command, log_path=self.cfg.path("logs", "grompp_{}.out".format(stage)))

    def mdrun(
        self,
        deffnm: str,
        gpu_id: Optional[int] = None,
        ntomp: Optional[int] = None,
        nsteps: Optional[int] = None,
        continue_run: bool = False,
        nb: str = "gpu",
        pme: Optional[str] = None,
        bonded: str = "gpu",
        maxh: Optional[float] = None,
        extra: Sequence[str] = (),
    ) -> int:
        """Run ``gmx mdrun``.

        Martini 3 electrostatics is **reaction-field**, so there is no PME mesh
        at all: the documented GPU invocation is ``-nb gpu -bonded gpu -gpu_id
        N`` with no ``-pme`` flag.  Passing ``-pme cpu``/``-pme gpu`` to a
        reaction-field run only makes mdrun complain about an incompatible
        setting, so ``pme`` defaults to ``None`` (omit the flag) and is only
        emitted when a caller explicitly asks for it (e.g. an all-atom smoke
        test).  ``maxh`` maps onto ``-maxh``, which lets a long production run
        exit cleanly at a step boundary so the next call can continue from the
        checkpoint instead of being killed by a job timeout.
        """
        command = [self.exe, "mdrun", "-deffnm", deffnm, "-nb", nb]
        if bonded and nb == "gpu":
            command += ["-bonded", bonded]
        gpu = self.cfg.gpu_id if gpu_id is None else gpu_id
        if nb == "gpu":
            # keep the documented trio together: -nb gpu -bonded gpu -gpu_id N
            command += ["-gpu_id", str(gpu)]
        if pme:
            command += ["-pme", str(pme)]
        command += ["-dlb", "yes", "-pin", "on"]
        threads = self.cfg.ntomp if ntomp is None else ntomp
        if threads:
            # GROMACS requires an explicit rank count with GPU and -ntomp.
            if nb == "gpu":
                command += ["-ntmpi", "1"]
            command += ["-ntomp", str(threads)]
        if maxh:
            command += ["-maxh", "{:.3f}".format(float(maxh))]
        if nsteps is not None:
            command += ["-nsteps", str(nsteps)]
        if continue_run:
            command += ["-cpi", "{}.cpt".format(deffnm)]
        if self.cfg.mdrun_extra:
            command += shlex.split(self.cfg.mdrun_extra)
        command += list(extra)
        return self.run(command, log_path=self.cfg.path("logs", "mdrun_{}.out".format(os.path.basename(deffnm))))

    # -- mdp rendering ----------------------------------------------------
    def render_all(self, cfg: Any) -> Dict[str, str]:
        """Render em/eq/prod mdp files into the run directory."""
        nstxout = cfg.compressed_stride
        nstlog = max(1000, min(cfg.prod_nsteps // 200, 5000))
        paths = {}
        paths["em"] = render_mdp(
            os.path.join(MDP_DIR, "em.mdp.in"),
            cfg.path("em.mdp"),
            {"EM_NSTEPS": cfg.em_steps, "EMTOL": 10.0},
        )
        paths["eq"] = render_mdp(
            os.path.join(MDP_DIR, "eq.mdp.in"),
            cfg.path("eq.mdp"),
            {
                "EQ_NSTEPS": cfg.eq_nsteps,
                "DT_PS": cfg.dt_ps,
                "TEMPERATURE": cfg.temperature_k,
                "SEED": cfg.seed,
                "DEFINE": "define = -DPOSRES",
                "NSTXOUT_COMPRESSED": max(1000, int(round(1000.0 / cfg.dt_ps))),
            },
        )
        paths["prod"] = render_mdp(
            os.path.join(MDP_DIR, "prod.mdp.in"),
            cfg.path("prod.mdp"),
            {
                "PROD_NSTEPS": cfg.prod_nsteps,
                "DT_PS": cfg.dt_ps,
                "TEMPERATURE": cfg.temperature_k,
                "NSTXOUT_COMPRESSED": nstxout,
                "NSTLOG": nstlog,
            },
        )
        return paths


def write_json(path: str, data: Dict[str, Any]) -> str:
    """UTF-8 JSON with newline, atomically replaced."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, path)
    return path
