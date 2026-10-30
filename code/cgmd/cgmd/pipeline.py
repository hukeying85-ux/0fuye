"""End-to-end Martini 3 antimicrobial-peptide pipeline.

Stage graph::

    structure -> martinize2 -> insane -> topology -> index
              -> EM -> 20 ns NPT equilibration (POSRES) -> production
              -> analysis -> summary_metrics.json + SVG figures

Every stage is idempotent: the run directory carries ``stages.json`` and a
finished stage is skipped when ``--resume`` is on (the default), which makes a
crashed or interrupted microsecond run restartable with a single command.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

from core import gmx_log

from . import analyze, figure, index as index_mod, peptide, seq2pdb, topology, salt
from .config import Config, resolve_martini3_dir
from .engine import Gromacs, StageError, probe_environment, probe_gpu, write_json

__all__ = ["Pipeline", "PipelineError", "parse_em_log"]

Notify = Callable[[str, str, Optional[List[str]]], None]


class PipelineError(RuntimeError):
    pass


def parse_em_log(text: str) -> Dict[str, Any]:
    """Extract convergence information from an energy-minimisation log."""
    report: Dict[str, Any] = {"converged": False, "steps": None, "max_force": None, "potential_kj": None}
    for line in text.splitlines():
        lowered = line.lower()
        if "converged to fmax" in lowered or "converged to f" in lowered:
            report["converged"] = True
        if "steepest descents converged" in lowered or "converged after" in lowered:
            report["converged"] = True
        if "maximum force" in lowered:
            match = re.search(r"=\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)", line)
            if match:
                report["max_force"] = float(match.group(1))
        if "potential" in lowered and "energy" in lowered and "\n" not in line:
            parts = [part for part in line.replace("=", " ").split() if _is_float(part)]
            if parts:
                report["potential_kj"] = float(parts[0])
        match = re.search(r"\b(?:in|after)\s+(\d+)\s+steps", line, re.IGNORECASE)
        if match:
            report["steps"] = int(match.group(1))
            if "converg" in lowered:
                report["converged"] = True
    if not report["converged"] and "did not converge" in text.lower():
        report["converged"] = False
    return report


def _is_float(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def _first_int(text: str) -> Optional[int]:
    for token in text.replace(",", " ").split():
        if token.isdigit():
            return int(token)
    return None


class Pipeline:
    """Run the pipeline for one :class:`Config`."""

    def __init__(
        self,
        cfg: Config,
        output_dir: str,
        notify: Optional[Notify] = None,
        logger: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.cfg = cfg
        self.output_dir = output_dir
        self.notify = notify or (lambda event, headline, lines=None: None)
        self._log_lines: List[str] = []
        self.logger = logger or self._default_logger
        self.engine: Optional[Gromacs] = None
        self.state: Dict[str, Any] = {"stages": {}, "started_at": _iso()}
        os.makedirs(cfg.workdir, exist_ok=True)
        os.makedirs(cfg.path("logs"), exist_ok=True)
        self._load_state()

    # -- logging / state --------------------------------------------------
    def _default_logger(self, message: str) -> None:
        print(message, flush=True)

    def log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self._log_lines.append("[{}] {}".format(stamp, message))
        self.logger("[{}] {}".format(stamp, message))

    def _load_state(self) -> None:
        path = self.cfg.path("stages.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict):
                    self.state.update(data)
            except (OSError, json.JSONDecodeError):
                pass

    def _save_state(self) -> None:
        self.state["updated_at"] = _iso()
        write_json(self.cfg.path("stages.json"), self.state)

    def _stage_done(self, name: str) -> bool:
        return bool(self.state.get("stages", {}).get(name, {}).get("status") == "done")

    def _mark(self, name: str, status: str, **extra: Any) -> None:
        entry = self.state.setdefault("stages", {}).setdefault(name, {})
        entry.update({"status": status, "at": _iso()})
        entry.update(extra)
        self._save_state()

    # -- main -------------------------------------------------------------
    def run(self) -> Dict[str, Any]:
        started = time.time()
        self.log("CGMD-Engine: sequence={} ({}) production={} ns".format(
            self.cfg.sequence or "-", self.cfg.peptide_name, self.cfg.production_ns
        ))
        if not self.cfg.dry_run:
            try:
                self.cfg.martini3_dir = resolve_martini3_dir(
                    self.cfg.martini3_dir,
                    auto_clone=self.cfg.fetch_forcefield,
                    logger=self.log,
                )
            except (FileNotFoundError, RuntimeError) as exc:
                raise PipelineError(str(exc))
            self.log("Martini 3 force field: {}".format(self.cfg.martini3_dir))
            self.engine = Gromacs(self.cfg, logger=self.log)
            self.engine.render_all(self.cfg)
            env = probe_environment(self.cfg)
            write_json(self.cfg.path("logs", "environment.json"), env)
            if env.get("gpu", {}).get("devices"):
                self.log("GPU: {}".format(env["gpu"]["devices"][0].get("name")))
            else:
                self.log("WARNING: no NVIDIA GPU detected by nvidia-smi")
            write_json(self.cfg.path("run_config.json"), self.cfg.to_dict())

        structure = self.stage_structure()
        martinized = self.stage_martinize(structure)
        system = self.stage_insane(martinized)
        topo = self.stage_topology(system, martinized)
        self.stage_index(system, topo)
        em_report = self.stage_em(system)
        eq_report = self.stage_equilibration()
        if not self.cfg.dry_run and not eq_report.get("completed"):
            raise PipelineError("equilibration incomplete or diverged; production not started")
        prod_report = self.stage_production()

        metrics = self.stage_analyze(structure, topo, em_report, eq_report, prod_report)
        metrics["walltime"] = {
            "total_s": round(time.time() - started, 1),
            "stages": {
                name: entry.get("seconds")
                for name, entry in self.state.get("stages", {}).items()
                if entry.get("seconds") is not None
            },
        }
        complete = self.cfg.dry_run or (prod_report.get("completed") and not prod_report.get("diverged"))
        self._mark("all", "done" if complete else "partial", seconds=round(time.time() - started, 1))
        return metrics

    # -- stages -----------------------------------------------------------
    def stage_structure(self) -> Dict[str, Any]:
        name = "structure"
        if self.cfg.resume and self._stage_done(name):
            self.log("structure: cached")
            with open(self.cfg.path("structure.json"), "r", encoding="utf-8") as handle:
                return json.load(handle)
        started = time.time()
        info = seq2pdb.build_structure(
            self.cfg.sequence,
            self.cfg.workdir,
            pdb_path=self.cfg.structure_pdb,
            predictor=self.cfg.predictor,
            ss=self.cfg.secondary_structure,
        )
        info["sequence"] = self.cfg.sequence
        info["peptide_name"] = self.cfg.peptide_name
        write_json(self.cfg.path("structure.json"), info)
        if info.get("clashes"):
            self.log("structure: {} clash(es) reported by the builder".format(len(info["clashes"])))
        self._mark(name, "done", seconds=round(time.time() - started, 1), method=info.get("method"))
        self.log("structure: {} ({})".format(info.get("method"), os.path.basename(str(info.get("path")))))
        return info

    def stage_martinize(self, structure: Dict[str, Any]) -> Dict[str, Any]:
        name = "martinize"
        if self.cfg.resume and self._stage_done(name):
            self.log("martinize2: cached")
            with open(self.cfg.path("martinize.json"), "r", encoding="utf-8") as handle:
                return json.load(handle)

        started = time.time()
        martinize = self.cfg.martinize_binary or shutil.which("martinize2")
        if self.cfg.dry_run:
            self.log("martinize2: (dry-run) skipping")
            info = {"cg_pdb": self.cfg.path("peptide_cg.pdb"), "top": self.cfg.path("peptide.top"), "dry_run": True}
            write_json(self.cfg.path("martinize.json"), info)
            self._mark(name, "done", seconds=0)
            return info
        if not martinize:
            raise PipelineError(
                "martinize2 not found. Install it with `pip install vermouth` "
                "(this provides the martinize2 executable)."
            )
        force_field = self._choose_force_field(martinize)
        ss = self.secondary_structure_string()
        cg_pdb = os.path.abspath(self.cfg.path("peptide_cg.pdb"))
        peptide_top = os.path.abspath(self.cfg.path("peptide.top"))
        command = [
            martinize,
            "-f", os.path.abspath(str(structure["path"])),
            "-x", cg_pdb,
            "-o", peptide_top,
            "-name", "Protein",
            "-ff", force_field,
            "-ss", ss,
            "-ignh",
            "-elastic",
            "-ef", "500",
            "-el", "0.5",
            "-eu", "0.9",
            "-p", "backbone",
            "-maxwarn", "1",
        ]
        # No -ff-dir / -map-dir on purpose: martinize2 must use the force field
        # and mappings bundled with vermouth (martini3001).  Pointing it at an
        # external vermouth_files checkout is how the mappings went missing and
        # the whole stage failed on the workstation.
        #
        # cwd=workdir is equally deliberate: martinize2 writes <molecule>.itp in
        # the current directory, not next to -o, so without it Protein_0.itp
        # landed in whatever directory the poller happened to start in.
        assert self.engine is not None
        self.engine.run(
            command,
            log_path=self.cfg.path("logs", "martinize2.out"),
            cwd=self.cfg.workdir,
        )

        if not os.path.exists(cg_pdb):
            raise PipelineError("martinize2 did not produce {}".format(cg_pdb))
        beads = sum(1 for line in open(cg_pdb, encoding="utf-8", errors="replace") if line.startswith("ATOM"))
        info = {
            "cg_pdb": cg_pdb,
            "top": peptide_top,
            "force_field": force_field,
            "beads": beads,
            "secondary_structure": ss,
            "secondary_structure_letter": (self.cfg.secondary_structure or "C").upper()[:1],
            "ss_expanded_to_residues": len(ss),
            "cwd": os.path.abspath(self.cfg.workdir),
            "external_vermouth_dirs": [],
        }
        write_json(self.cfg.path("martinize.json"), info)
        self._mark(name, "done", seconds=round(time.time() - started, 1), beads=beads)
        self.log("martinize2: {} Martini beads".format(beads))
        return info

    def _choose_force_field(self, martinize: str) -> str:
        """Pick the Martini 3 force-field name understood by this vermouth."""
        try:
            completed = __import__("subprocess").run(
                [martinize, "-list-ff"], capture_output=True, text=True, timeout=120
            )
            listing = (completed.stdout or "") + (completed.stderr or "")
        except Exception:  # noqa: BLE001 - best effort only
            listing = ""
        for candidate in ("martini3001", "martini3", "martini30", "martini_3"):
            if candidate in listing:
                return candidate
        return "martini3001"

    def secondary_structure_string(self) -> str:
        """Secondary structure as martinize2 wants it: **one code per residue**.

        ``martinize2 -ss H`` is parsed as a *sequence* annotation, so a single
        letter does not mean "all helix" -- the residue-by-residue string does.
        A one-letter request is therefore expanded to the residue count
        (``"H" * len(seq)``), and a string that already has the right length is
        passed through untouched.
        """
        letter = (self.cfg.secondary_structure or "C").upper()[:1] or "C"
        requested = (self.cfg.secondary_structure or "C").upper()
        residues = len(self.cfg.sequence or "")
        if len(requested) > 1 and residues and len(requested) >= residues:
            return requested[:residues]
        if residues:
            return letter * residues
        return letter

    def _vermouth_dirs(self) -> List[str]:
        """Deprecated: martinize2 now always uses vermouth's bundled files."""
        return []

    def stage_insane(self, martinized: Dict[str, Any]) -> Dict[str, Any]:
        name = "insane"
        if self.cfg.resume and self._stage_done(name):
            self.log("insane: cached")
            with open(self.cfg.path("insane.json"), "r", encoding="utf-8") as handle:
                return json.load(handle)

        started = time.time()
        box = self._box_for(martinized.get("cg_pdb"))
        lipids = self.cfg.lipids
        if self.cfg.dry_run:
            self.log("insane: (dry-run) skipping")
            info = {"gro": self.cfg.path("system.gro"), "top": self.cfg.path("insane.top"), "box_nm": box, "dry_run": True}
            write_json(self.cfg.path("insane.json"), info)
            self._mark(name, "done", seconds=0)
            return info

        insane = self.cfg.insane_binary or shutil.which("insane")
        if not insane:
            raise PipelineError(
                "insane not found. Install it with `pip install insane` "
                "or run code/cgmd/setup_env.sh."
            )
        supports_ff = self._insane_supports_ff(insane)
        command = [
            insane,
            "-f", str(martinized["cg_pdb"]),
            "-o", self.cfg.path("system.gro"),
            "-p", self.cfg.path("insane.top"),
            "-pbc", "rectangular",
            "-x", "{:.3f}".format(box[0]),
            "-y", "{:.3f}".format(box[1]),
            "-z", "{:.3f}".format(box[2]),
            "-a", "{:.3f}".format(self.cfg.area_per_lipid),
            "-sol", "W",
            "-salt", "{:.3f}".format(self.cfg.salt_m),
        ]
        for lipid, ratio in lipids.items():
            command += ["-l", "{}:{}".format(lipid, _num(ratio))]
        if supports_ff:
            command += ["-ff", "M3"]
        self.engine.run(command, log_path=self.cfg.path("logs", "insane.out"))  # type: ignore[union-attr]

        gro = self.cfg.path("system.gro")
        if not os.path.exists(gro):
            raise PipelineError("insane did not produce {}".format(gro))
        salt_info = salt.ensure_salt_pairs(gro, self.cfg.path("insane.top"), self.cfg.salt_m, self.cfg.seed)
        info = {
            "salt": salt_info,
            "gro": gro,
            "top": self.cfg.path("insane.top"),
            "box_nm": box,
            "insane_forcefield_flag": supports_ff,
            "atoms": topology.count_gro_atoms(gro),
        }
        write_json(self.cfg.path("insane.json"), info)
        self._mark(name, "done", seconds=round(time.time() - started, 1), atoms=info["atoms"])
        self.log("insane: {} atoms, box {:.1f} x {:.1f} x {:.1f} nm".format(info["atoms"], *box))
        return info

    def _insane_supports_ff(self, insane: str) -> bool:
        try:
            completed = __import__("subprocess").run([insane, "--help"], capture_output=True, text=True, timeout=120)
            text = (completed.stdout or "") + (completed.stderr or "")
            return "-ff" in text
        except Exception:  # noqa: BLE001
            return False

    def _box_for(self, cg_pdb: Optional[str]) -> Sequence[float]:
        """Box size: user request, expanded so the peptide never overlaps images."""
        x = float(self.cfg.box_xy_nm)
        y = float(self.cfg.box_xy_nm)
        z = float(self.cfg.box_z_nm)
        if cg_pdb and os.path.exists(cg_pdb):
            extents = _pdb_extent(cg_pdb)
            if extents:
                x = max(x, extents[0] + 2.0)
                y = max(y, extents[1] + 2.0)
                z = max(z, extents[2] + 3.0)
        return (round(x, 2), round(y, 2), round(z, 2))

    def stage_topology(self, system: Dict[str, Any], martinized: Dict[str, Any]) -> Dict[str, Any]:
        name = "topology"
        if self.cfg.resume and self._stage_done(name):
            with open(self.cfg.path("topology.json"), "r", encoding="utf-8") as handle:
                return json.load(handle)
        started = time.time()
        if self.cfg.dry_run:
            report = {
                "topology": self.cfg.path("topol.top"),
                "peptide_moleculetype": "Protein_0",
                "peptide_atoms_per_copy": 0,
                "molecules": [],
                "includes": [],
                "expected_atoms": 0,
            }
            write_json(self.cfg.path("topology.json"), report)
            self._mark(name, "done", seconds=0)
            return report
        report = topology.build_topology(
            insane_top=str(system["top"]),
            peptide_top=str(martinized["top"]),
            ff_roots=[str(self.cfg.martini3_dir)],
            out_path=self.cfg.path("topol.top"),
            system_name="CGMD {} in POPE:POPG bilayer".format(self.cfg.peptide_name),
            flat_includes=True,
        )
        validation = topology.validate_topology(report, str(system["gro"]))
        report["validation"] = validation
        write_json(self.cfg.path("topology.json"), report)
        self._mark(name, "done", seconds=round(time.time() - started, 1), consistent=validation["consistent"])
        if not validation["consistent"]:
            self.log(
                "WARNING: topology expects {} atoms but the coordinate file has {} "
                "(off by {})".format(validation["topology_atoms"], validation["gro_atoms"], validation["difference"])
            )
        self.log(
            "topology: {} | {} molecule types | {:d} atoms | {} flat include(s)".format(
                report["peptide_moleculetype"], len(report["molecules"]),
                int(report["expected_atoms"] or 0), len(report.get("flat_includes") or []),
            )
        )
        return report

    def stage_index(self, system: Dict[str, Any], topo: Dict[str, Any]) -> Dict[str, Any]:
        name = "index"
        if self.cfg.resume and self._stage_done(name):
            with open(self.cfg.path("index.json"), "r", encoding="utf-8") as handle:
                return json.load(handle)
        started = time.time()
        if self.cfg.dry_run:
            self._mark(name, "done", seconds=0)
            return {"groups": {}}
        peptide_atoms = int(topo.get("peptide_atoms_per_copy") or 0)
        copies = 1
        for molecule in topo.get("molecules", []):
            if molecule.get("name") == topo.get("peptide_moleculetype"):
                copies = int(molecule.get("count") or 1)
                break
        info = index_mod.write_index(
            str(system["gro"]),
            self.cfg.path("index.ndx"),
            peptide_atoms=peptide_atoms * copies,
            lipid_names=list(self.cfg.lipids),
        )
        write_json(self.cfg.path("index.json"), info)
        self._mark(name, "done", seconds=round(time.time() - started, 1))
        return info

    def stage_em(self, system: Dict[str, Any]) -> Dict[str, Any]:
        name = "em"
        if self.cfg.resume and self._stage_done(name):
            self.log("em: cached")
            return self._read_json(self.cfg.path("em.json"), {})
        started = time.time()
        if self.cfg.dry_run:
            self._mark(name, "done", seconds=0)
            return {}
        assert self.engine is not None
        self.engine.grompp("em", self.cfg.path("em.mdp"), str(system["gro"]), self.cfg.path("topol.top"),
                           self.cfg.path("em.tpr"), ndx=self.cfg.path("index.ndx"))
        self.engine.mdrun("em", nb="cpu", ntomp=self.cfg.ntomp or 4)
        report = parse_em_log(_read_text(self.cfg.path("em.log")))
        report["seconds"] = round(time.time() - started, 1)
        write_json(self.cfg.path("em.json"), report)
        self._mark(name, "done", seconds=report["seconds"], converged=report.get("converged"))
        self.log("em: converged={} max_force={}".format(report.get("converged"), report.get("max_force")))
        return report

    def _mdrun_until(self, deffnm: str, target_ns: float, name: str) -> Dict[str, Any]:
        """Integrate ``deffnm`` until ``target_ns``, resuming from the checkpoint.

        A microsecond production run cannot finish inside one job budget, and a
        killed mdrun loses everything since the last checkpoint.  ``-maxh``
        makes mdrun stop *itself* at a step boundary shortly before the ceiling,
        write a ``.cpt`` and exit 0; the next call continues with ``-cpi``.  The
        loop therefore yields honest partial progress instead of a timeout, and
        re-issuing the same job picks up where it left off.
        """
        assert self.engine is not None
        started = time.time()
        state = gmx_log.parse_log_text(_read_text(self.cfg.path("{}.log".format(deffnm))))
        calls = 0
        while True:
            done_ns = state.simulated_ns
            if done_ns >= target_ns - 1e-9:
                break
            remaining_ns = target_ns - done_ns
            segment = self.cfg.segment_ns if self.cfg.segment_ns and self.cfg.segment_ns > 0 else remaining_ns
            steps = max(1, int(round(min(segment, remaining_ns) / self.cfg.dt_ps * 1000.0)))
            checkpoint = self.cfg.path("{}.cpt".format(deffnm))
            resume = bool(self.cfg.resume and done_ns > 0 and os.path.exists(checkpoint))
            if resume:
                self.log("{}: continuing from {:.3f} ns (checkpoint)".format(name, done_ns))
            self.engine.mdrun(
                deffnm,
                nsteps=steps,
                continue_run=resume,
                maxh=self.cfg.maxh_hours or None,
            )
            calls += 1
            state = gmx_log.parse_log_text(_read_text(self.cfg.path("{}.log".format(deffnm))))
            if state.is_diverged:
                break
            if state.simulated_ns <= done_ns + 1e-9:
                # No forward progress: stop instead of spinning on the same step.
                self.log("{}: mdrun made no progress, stopping the loop".format(name))
                break
            if calls >= 200:
                self.log("{}: reached the 200-call safety limit".format(name))
                break
        report = {
            "seconds": round(time.time() - started, 1),
            "ns": round(state.simulated_ns, 3),
            "target_ns": target_ns,
            "completed": state.simulated_ns >= target_ns - 1e-9,
            "remaining_ns": round(max(0.0, target_ns - state.simulated_ns), 3),
            "steps": state.step,
            "nsteps_completed": int(round(state.simulated_ns / self.cfg.dt_ps * 1000.0)),
            "nsteps_target": int(round(target_ns / self.cfg.dt_ps * 1000.0)),
            "ns_per_day": state.ns_per_day,
            "finished": state.finished,
            "diverged": state.is_diverged,
            "divergence": state.divergence,
            "lincs_warnings": state.lincs_warnings,
            "mdrun_calls": calls,
            "maxh_hours": self.cfg.maxh_hours,
            "checkpoint": self.cfg.path("{}.cpt".format(deffnm)),
        }
        return report

    def stage_equilibration(self) -> Dict[str, Any]:
        name = "eq"
        if self.cfg.resume and self._stage_done(name):
            self.log("eq: cached")
            return self._read_json(self.cfg.path("eq.json"), {})
        started = time.time()
        if self.cfg.dry_run:
            self._mark(name, "done", seconds=0)
            return {}
        assert self.engine is not None
        self.engine.grompp("eq", self.cfg.path("eq.mdp"), self.cfg.path("em.gro"), self.cfg.path("topol.top"),
                           self.cfg.path("eq.tpr"), ndx=self.cfg.path("index.ndx"),
                           extra=["-r", self.cfg.path("em.gro")])
        report = self._mdrun_until("eq", self.cfg.equilibration_ns, "eq")
        report["wall_seconds"] = round(time.time() - started, 1)
        write_json(self.cfg.path("eq.json"), report)
        complete = report.get("completed") or report.get("diverged")
        self._mark(name, "done" if complete else "partial", seconds=report["seconds"], ns=report["ns"])
        self.log("eq: {} ns at {} ns/day".format(report["ns"], report["ns_per_day"]))
        return report

    def stage_production(self) -> Dict[str, Any]:
        name = "prod"
        if self.cfg.resume and self._stage_done(name):
            self.log("prod: cached")
            return self._read_json(self.cfg.path("prod.json"), {})
        started = time.time()
        if self.cfg.dry_run:
            self._mark(name, "done", seconds=0)
            return {"dry_run": True}
        assert self.engine is not None
        self.engine.grompp("prod", self.cfg.path("prod.mdp"), self.cfg.path("eq.gro"), self.cfg.path("topol.top"),
                           self.cfg.path("prod.tpr"), ndx=self.cfg.path("index.ndx"),
                           extra=["-t", self.cfg.path("eq.cpt")])
        self.notify("start", "Production started ({} ns, GPU {})".format(self.cfg.production_ns, self.cfg.gpu_id),
                    ["Peptide: {} ({} aa)".format(self.cfg.peptide_name, len(self.cfg.sequence)),
                     "Speed and ETA tracked by node_agent"])
        report = self._mdrun_until("prod", self.cfg.production_ns, "prod")
        report["wall_seconds"] = round(time.time() - started, 1)
        report["gpu_flags"] = " ".join(self.cfg.mdrun_gpu_flags)
        write_json(self.cfg.path("prod.json"), report)
        # "done" only when the requested length really was integrated: a
        # partial production must resume, not be skipped on the next call.
        complete = bool(report.get("completed")) or bool(report.get("diverged"))
        self._mark(name, "done" if complete else "partial", seconds=report["seconds"], ns=report["ns"],
                   diverged=report["diverged"], ns_per_day=report["ns_per_day"])
        self.log("prod: {} ns / {} ns, {} ns/day, diverged={}".format(
            report["ns"], report["target_ns"], report["ns_per_day"], report["diverged"]))
        if report["diverged"]:
            self.notify("error", "Production diverged", ["Reason: {}".format(report["divergence"] or "unknown"),
                                                 "Completed {:.1f} ns".format(report["ns"])])
        return report

    def stage_analyze(
        self,
        structure: Dict[str, Any],
        topo: Dict[str, Any],
        em_report: Dict[str, Any],
        eq_report: Dict[str, Any],
        prod_report: Dict[str, Any],
    ) -> Dict[str, Any]:
        name = "analyze"
        self.log("analysis: reading trajectory")
        started = time.time()
        description = peptide.describe(self.cfg.sequence)
        description["name"] = self.cfg.peptide_name

        state = gmx_log.LogState()
        try:
            state = gmx_log.parse_log_text(_read_text(self.cfg.path("prod.log")))
        except OSError:
            pass

        simulation = analyze.summarise_logs(
            state,
            em_report=em_report,
            production_ns=self.cfg.production_ns,
            walltime_s=prod_report.get("seconds") if isinstance(prod_report, dict) else None,
        )
        simulation["equilibration"] = eq_report
        simulation["production"] = {
            "completed_ns": prod_report.get("ns"),
            "target_ns": prod_report.get("target_ns"),
            "completed": prod_report.get("completed"),
            "steps_completed": prod_report.get("nsteps_completed"),
            "steps_target": prod_report.get("nsteps_target"),
            "mdrun_calls": prod_report.get("mdrun_calls"),
            "maxh_hours": prod_report.get("maxh_hours"),
            "gpu_flags": prod_report.get("gpu_flags"),
            "wall_seconds": prod_report.get("wall_seconds"),
        }

        metrics: Dict[str, Any] = {
            "schema": "cgmd.summary.v1",
            "task_id": self.cfg.task_id,
            "generated_at": _iso(),
            "peptide": description,
            "system": {
                "lipids": self.cfg.lipids,
                "lipid_ratio": ":".join(_num(value) for value in self.cfg.lipids.values()),
                "box_nm": self._box_for(structure.get("path")),
                "temperature_K": self.cfg.temperature_k,
                "salt_M": self.cfg.salt_m,
                "atoms": topo.get("expected_atoms"),
                "molecules": topo.get("molecules"),
                "peptide_beads": topo.get("peptide_atoms_per_copy"),
                "force_field": topo.get("forcefield"),
                "topology_includes": topo.get("flat_includes") or [],
                "index_groups": self._read_json(self.cfg.path("index.json"), {}).get("groups", {}),
            },
            "simulation": simulation,
            "structure": {key: value for key, value in structure.items() if key not in ("clashes",)},
            "topology_validation": topo.get("validation"),
            "environment": self._read_json(self.cfg.path("logs", "environment.json"), {}).get("gromacs"),
            "notes": [],
        }

        if not self.cfg.dry_run:
            try:
                trajectory_metrics = analyze.analyse_trajectory(
                    gro_path=self._coordinate_file(),
                    xtc_path=self.cfg.path("prod.xtc"),
                    peptide_atoms=int(topo.get("peptide_atoms_per_copy") or 0),
                    lipid_resnames=list(self.cfg.lipids),
                    pore_radius_nm=self.cfg.pore_radius_nm,
                    water_core_halfheight_nm=self.cfg.water_core_halfheight_nm,
                    max_frames=self.cfg.max_frames,
                )
                metrics.update(trajectory_metrics)
            except analyze.AnalysisUnavailable as exc:
                metrics["notes"].append("trajectory analysis skipped: {}".format(exc))
                self._empty_metric_sections(metrics)
            except Exception as exc:  # noqa: BLE001 - never lose the run summary
                metrics["notes"].append("trajectory analysis failed: {}".format(str(exc)[:400]))
                self._empty_metric_sections(metrics)
        else:
            metrics["notes"].append("dry run: no trajectory produced")

        # --- figures -----------------------------------------------------
        figures = figure.make_figures(metrics, description, outdir=self._figures_dir())
        # paths are stored relative to the results directory of this run, so the
        # same JSON is valid on the workstation and inside the git checkout
        metrics["figures"] = [os.path.relpath(path, self.output_dir).replace(os.sep, "/") for path in figures]
        write_json(self.cfg.path("metrics.json"), metrics)
        analyze.write_summary(metrics, os.path.join(self.output_dir, "summary_metrics.json"))
        self._mark(name, "done", seconds=round(time.time() - started, 1), figures=len(figures))
        self.log("analysis: {} figure(s) -> {}".format(len(figures), self.output_dir))
        return metrics

    def _coordinate_file(self) -> str:
        """Reference structure for the trajectory: the first stage gro that exists."""
        for name in ("eq.gro", "prod.gro", "em.gro", "system.gro"):
            candidate = self.cfg.path(name)
            if os.path.exists(candidate):
                return candidate
        return self.cfg.path("eq.gro")

    @staticmethod
    def _empty_metric_sections(metrics: Dict[str, Any]) -> None:
        """Keep the summary schema stable when the analysis could not run."""
        metrics.setdefault("membrane_insertion", {
            "z_distance_mean_nm": None, "inserted_fraction": None, "per_residue_z_nm": [],
            "convention": "peptide bead centroid minus phosphate mid-plane",
        })
        metrics.setdefault("lipid_order", {"sn1": None, "sn2": None, "mean": None, "per_species": {}})
        metrics.setdefault("pore", {
            "pore_formed": False, "pore_score_mean": 0.0, "water_in_core_mean": 0.0,
            "water_in_core_max": 0.0,
        })
        metrics.setdefault("membrane", {"thickness_nm": None})
        metrics.setdefault("timeseries", {})

    def _figures_dir(self) -> str:
        path = os.path.join(self.output_dir, "figures")
        os.makedirs(path, exist_ok=True)
        return path

    @staticmethod
    def _read_json(path: str, default: Any) -> Any:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            return default


def _num(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(number)) if number.is_integer() else str(number)


def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _pdb_extent(path: str) -> Optional[Sequence[float]]:
    """Largest extent (nm) of a PDB file along x/y/z."""
    lows = [float("inf")] * 3
    highs = [float("-inf")] * 3
    count = 0
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.startswith(("ATOM", "HETATM")):
                    continue
                try:
                    xyz = [float(line[30:38]), float(line[38:46]), float(line[46:54])]
                except ValueError:
                    continue
                count += 1
                for axis in range(3):
                    lows[axis] = min(lows[axis], xyz[axis])
                    highs[axis] = max(highs[axis], xyz[axis])
    except OSError:
        return None
    if count == 0:
        return None
    return [(highs[axis] - lows[axis]) / 10.0 for axis in range(3)]


def _iso() -> str:
    from core.task_contract import beijing_iso

    return beijing_iso()
