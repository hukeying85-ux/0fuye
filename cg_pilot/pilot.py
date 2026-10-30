"""Prepare and run an explicitly scoped Martini 3 YLSLLQR aqueous pilot.

The peptide is a *cloud-document candidate*, not verified against F: on the
user's desktop. This code cannot make the desktop execute merely by being
committed or uploaded to Drive; a real desktop runner/receipt is required.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SEQUENCE = "YLSLLQR"
FORCEFIELD_SHA = "784591ebdc91d762ed4df986c4650546c938f776"
FORCEFIELD_URL = (
    "https://codeload.github.com/marrink-lab/martini-forcefields/tar.gz/"
    + FORCEFIELD_SHA
)
FORCEFIELD_FILES = {
    "martini_v3.0.0.itp": "0ecbf0ff334b2ec21dc5e3151aca42167b977bc2aed41eb2a44bd8c997754894",
    "martini_v3.0.0_solvents_v1.itp": "e6a78414b317c38a1a816eded4aee6082a5da1ed229a126359f0cc92314dcb4e",
    "martini_v3.0.0_ions_v1.itp": "699aba132755b0ef13a0d7b41e6230a27777781bdc8075507413b89499c2be4f",
}
STAGES = ("em", "nvt", "npt", "prod")


class PilotError(RuntimeError):
    """A preparation or GROMACS validation gate failed."""


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_forcefield(output: Path, source_dir: Path | None, fetch: bool) -> dict[str, str]:
    """Copy three compatible official Martini 3 files, rejecting version drift."""
    dest = output / "forcefield"
    dest.mkdir(parents=True, exist_ok=False)
    if fetch:
        if source_dir is not None:
            raise PilotError("Use either --fetch-forcefield or --forcefield-dir, not both")
        archive = output / "martini-forcefields.tar.gz"
        with urllib.request.urlopen(FORCEFIELD_URL, timeout=90) as response, archive.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        with tarfile.open(archive, mode="r:gz") as tar:
            members = {Path(m.name).name: m for m in tar.getmembers() if m.isfile()}
            for name in FORCEFIELD_FILES:
                member = members.get(name)
                if member is None or "/regular/v3.0.0/gmx_files/" not in member.name:
                    raise PilotError("Pinned forcefield archive lacks " + name)
                with tar.extractfile(member) as reader, (dest / name).open("wb") as writer:
                    shutil.copyfileobj(reader, writer)
            license_member = members.get("LICENSE")
            if license_member:
                with tar.extractfile(license_member) as reader, (dest / "LICENSE").open("wb") as writer:
                    shutil.copyfileobj(reader, writer)
        archive.unlink()
    else:
        if source_dir is None:
            raise PilotError("Pass --forcefield-dir (official v3.0.0/gmx_files) or --fetch-forcefield")
        for name in FORCEFIELD_FILES:
            shutil.copy2(source_dir / name, dest / name)
        if (source_dir / "LICENSE").exists():
            shutil.copy2(source_dir / "LICENSE", dest / "LICENSE")
    hashes = {name: checksum(dest / name) for name in FORCEFIELD_FILES}
    for name, expected in FORCEFIELD_FILES.items():
        if hashes[name] != expected:
            raise PilotError(f"Forcefield checksum mismatch for {name}: {hashes[name]} != {expected}")
    return hashes


def tool(name: str) -> str:
    """Prefer the active venv's entry points, including Windows .exe shims."""
    beside_python = Path(sys.executable).with_name(name + (".exe" if os.name == "nt" else ""))
    found = str(beside_python) if beside_python.is_file() else shutil.which(name)
    if not found:
        raise PilotError(f"Required tool not installed in the active environment: {name}")
    return found


def invoke(argv: list[str], cwd: Path, log_name: str) -> str:
    result = subprocess.run(argv, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (cwd / log_name).write_text(result.stdout, encoding="utf-8")
    if result.returncode:
        raise PilotError(f"Command failed ({result.returncode}), see {cwd / log_name}: {argv[:2]}")
    return result.stdout


def write_initial_pdb(path: Path, sequence: str) -> None:
    try:
        import PeptideBuilder
        from Bio.PDB import PDBIO
    except ImportError as exc:
        raise PilotError("Install cg_pilot/requirements.txt into an isolated Python environment") from exc
    structure = PeptideBuilder.make_extended_structure(sequence)
    io = PDBIO()
    io.set_structure(structure)
    io.save(str(path))


def itp_atoms(path: Path) -> tuple[list[str], int]:
    in_atoms = False
    names: list[str] = []
    charge = 0.0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split(";", 1)[0].strip()
        if line.startswith("["):
            in_atoms = bool(re.match(r"^\[\s*atoms\s*\]$", line, re.I))
            continue
        if not in_atoms or not line:
            continue
        parts = line.split()
        if len(parts) < 7:
            raise PilotError("Malformed Martini peptide atom: " + raw)
        names.append(parts[4])
        charge += float(parts[6])
    if not names or abs(charge - round(charge)) > 1e-6:
        raise PilotError("Missing bead mapping or unexpected non-integral peptide charge")
    return names, int(round(charge))


def insane_counts(path: Path) -> dict[str, int]:
    in_molecules = False
    counts: dict[str, int] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split(";", 1)[0].strip()
        if re.match(r"^\[\s*molecules\s*\]$", line, re.I):
            in_molecules = True
            continue
        if in_molecules and line.startswith("["):
            break
        if in_molecules and line:
            name, count = line.split()[:2]
            counts[name] = counts.get(name, 0) + int(count)
    if counts.get("Protein") != 1 or counts.get("W", 0) < 100 or not {"NA+", "CL-"}.issubset(counts):
        raise PilotError(f"Unexpected INSANE solvation molecules: {counts}")
    return counts


def normalize_gro(path: Path, peptide_beads: list[str], counts: dict[str, int]) -> int:
    """Rename INSANE ion labels and check CG coordinate/topology bead alignment."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 3:
        raise PilotError("Truncated solvated GRO")
    total = int(lines[1].strip())
    expected = len(peptide_beads) + counts["W"] + counts["NA+"] + counts["CL-"]
    if total != expected or len(lines) != total + 3:
        raise PilotError(f"GRO/topology particle count mismatch: {total} != {expected}")
    result = lines[:2]
    for n, line in enumerate(lines[2:-1]):
        if len(line) < 44:
            raise PilotError(f"Malformed GRO atom line {n + 1}")
        atom = line[10:15].strip()
        if n < len(peptide_beads):
            if atom != peptide_beads[n]:
                raise PilotError(f"Peptide bead {n + 1}: {atom} != {peptide_beads[n]}")
        else:
            resid = line[5:10].strip()
            if resid in ("NA+", "CL-"):
                norm = resid[:-1]
                line = line[:5] + f"{norm:>5}" + f"{norm:>5}" + line[15:]
            elif resid != "W":
                raise PilotError(f"Unexpected solvent/ion residue {resid}")
        result.append(line)
    result.append(lines[-1])
    path.write_text("\n".join(result) + "\n", encoding="utf-8")
    if counts["NA+"] - counts["CL-"] + 1 != 0:
        # The current YLSLLQR model has neutral free termini and one Arg (+1).
        raise PilotError("System ionic charge does not neutralize the +1 peptide")
    return total


def topol_text(counts: dict[str, int]) -> str:
    return """; YLSLLQR, Martini 3.0.0, free NH3+/COO- termini, isolated aqueous pilot.
#include "forcefield/martini_v3.0.0.itp"
#include "forcefield/martini_v3.0.0_solvents_v1.itp"
#include "forcefield/martini_v3.0.0_ions_v1.itp"
#include "Peptide_0.itp"

[ system ]
YLSLLQR single-peptide engineering pilot (NOT Abeta nucleation)

[ molecules ]
Peptide_0       1
W               {W}
NA              {NA}
CL              {CL}
""".format(W=counts["W"], NA=counts["NA+"], CL=counts["CL-"])


def mdp_text(stage: str, steps: int, seed: int) -> str:
    fields = [
        f"integrator = {'steep' if stage == 'em' else 'md'}",
        f"nsteps = {steps}",
        "cutoff-scheme = Verlet",
        "nstlist = 20",
        "rlist = 1.1",
        "coulombtype = reaction-field",
        "rcoulomb = 1.1",
        "epsilon-r = 15",
        "vdwtype = cut-off",
        "vdw-modifier = Potential-shift-verlet",
        "rvdw = 1.1",
        "pbc = xyz",
        "constraints = none",
        "constraint-algorithm = lincs",
        "lincs-iter = 2",
        "lincs-order = 4",
    ]
    if stage == "em":
        fields += ["emtol = 1000", "emstep = 0.01"]
    else:
        fields += [
            "dt = 0.02",  # Martini3, 20 fs
            "tcoupl = v-rescale",
            "tc-grps = System",
            "tau-t = 1.0",
            "ref-t = 300",
            "nstcalcenergy = 100",
            "nstenergy = 1000",
            "nstlog = 1000",
            "nstxout-compressed = 5000",
            "compressed-x-precision = 100",
            f"gen-vel = {'yes' if stage == 'nvt' else 'no'}",
            f"continuation = {'no' if stage == 'nvt' else 'yes'}",
        ]
        if stage == "nvt":
            fields += ["gen-temp = 300", f"gen-seed = {seed}"]
        if stage in ("npt", "prod"):
            fields += [
                "pcoupl = C-rescale", "pcoupltype = isotropic", "tau-p = 4.0",
                "ref-p = 1.0", "compressibility = 3e-4",
            ]
        else:
            fields += ["pcoupl = no"]
    return "\n".join(fields) + "\n"


def prepare(output: Path, forcefield_dir: Path | None, fetch_ff: bool, prod_ns: float, seed: int) -> dict:
    if output.exists() and any(output.iterdir()):
        raise PilotError("Output directory must be new/empty: " + str(output))
    if not 0.1 <= prod_ns <= 1000:
        raise PilotError("--prod-ns must be in [0.1, 1000]")
    output.mkdir(parents=True, exist_ok=True)
    hashes = get_forcefield(output, forcefield_dir, fetch_ff)
    write_initial_pdb(output / "initial_extended.pdb", SEQUENCE)
    martinize = tool("martinize2")
    insane = tool("insane")
    invoke([
        martinize, "-f", "initial_extended.pdb", "-x", "peptide_cg.pdb",
        "-o", "martinize.top", "-ff", "martini3001", "-ss", "C",
        "-name", "Peptide",
    ], output, "martinize.log")
    beads, charge = itp_atoms(output / "Peptide_0.itp")
    if charge != 1:
        raise PilotError(f"Expected YLSLLQR +1 for free termini, found {charge}")
    invoke([
        insane, "-f", "peptide_cg.pdb", "-o", "system.gro",
        "-p", "insane.top", "-box", "7,7,7", "-sol", "W",
        "-salt", "0.15", "-charge", str(charge), "-center",
    ], output, "insane.log")
    counts = insane_counts(output / "insane.top")
    total = normalize_gro(output / "system.gro", beads, counts)
    (output / "topol.top").write_text(topol_text(counts), encoding="utf-8")
    steps = {"em": 5000, "nvt": 50_000, "npt": 50_000, "prod": int(prod_ns * 50_000)}
    for stage in STAGES:
        (output / f"{stage}.mdp").write_text(mdp_text(stage, steps[stage], seed), encoding="utf-8")
    meta = {
        "status": "prepared_not_run", "sequence": SEQUENCE,
        "scope": "single aqueous peptide pilot; not the Aβ method-8 seed/50-Aβ40 experiment",
        "origin": "Drive candidate; NOT verified as recently run on F: drive",
        "structure": "PeptideBuilder extended ideal all-atom input; martinize2 martini3001 -ss C without elastic network",
        "terminal_assumption": "uncapped, free NH3+ / COO-, net peptide charge +1",
        "forcefield_repo_sha": FORCEFIELD_SHA,
        "forcefield_sha256": hashes,
        "box_nm": [7, 7, 7], "salt_M": 0.15, "temperature_K": 300,
        "timestep_ps": 0.02, "production_ns": prod_ns, "seed": seed,
        "peptide_beads": len(beads), "system_beads": total,
        "molecules": {"Peptide_0": 1, "W": counts["W"], "NA": counts["NA+"], "CL": counts["CL-"]},
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "warning": "Inputs only; no GROMACS result or desktop execution is implied.",
    }
    (output / "manifest.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return meta


def command_plan(work: Path, gmx: str = "gmx", gpu_id: int = 0) -> list[list[str]]:
    plan: list[list[str]] = []
    source = "system.gro"
    for stage in STAGES:
        args = [gmx, "grompp", "-f", f"{stage}.mdp", "-c", source,
                "-p", "topol.top", "-o", f"{stage}.tpr"]
        if stage in ("npt", "prod"):
            args.extend(["-t", f"{STAGES[STAGES.index(stage) - 1]}.cpt"])
        plan.append(args)
        mdrun = [gmx, "mdrun", "-deffnm", stage, "-nb", "cpu" if stage == "em" else "gpu"]
        if stage != "em":
            mdrun += ["-gpu_id", str(gpu_id)]
        plan.append(mdrun)
        source = f"{stage}.gro"
    return plan


def run(work: Path, gmx: str, gpu_id: int, dry_run: bool) -> dict:
    if not (work / "manifest.json").is_file() or not (work / "topol.top").is_file():
        raise PilotError("Run `prepare` successfully first")
    meta = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
    if meta.get("status") != "prepared_not_run":
        raise PilotError("Manifest is not an unrun prepared pilot; refusing to overwrite a past run")
    for name, expected in meta.get("forcefield_sha256", {}).items():
        if checksum(work / "forcefield" / name) != expected:
            raise PilotError("Forcefield file changed since preparation: " + name)
    plan = command_plan(work, gmx, gpu_id)
    if dry_run:
        return {"status": "dry_run_only", "workdir": str(work), "commands": plan}
    if shutil.which(gmx) is None and not Path(gmx).is_file():
        raise PilotError("GROMACS executable unavailable: " + gmx)
    if (work / "prod.xtc").exists():
        raise PilotError("Production trajectory exists; refuse to overwrite it")
    results: list[dict] = []
    meta.update({"status": "running_unconfirmed", "started_at_utc": datetime.now(timezone.utc).isoformat()})
    (work / "manifest.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        version = invoke([gmx, "--version"], work, "gmx-version.log")
        for idx, command in enumerate(plan):
            stage = STAGES[idx // 2]
            log = f"{stage}-{'grompp' if idx % 2 == 0 else 'mdrun'}.txt"
            invoke(command, work, log)
            results.append({"stage": stage, "command": command, "exit_code": 0, "log": log})
        if not (work / "prod.gro").is_file() or not (work / "prod.xtc").is_file():
            raise PilotError("GROMACS exited but production outputs missing")
        meta.update({
            "status": "integrated_qc_pending", "gromacs_version_excerpt": version[:1000],
            "prod_gro_sha256": checksum(work / "prod.gro"),
        })
    except (PilotError, OSError, subprocess.SubprocessError) as exc:
        meta.update({"status": "failed_on_runner", "error": str(exc)})
        raise
    finally:
        meta.update({"stages": results, "finished_at_utc": datetime.now(timezone.utc).isoformat()})
        (work / "manifest.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Martini3 single-peptide engineering pilot (not Aβ aggregation)")
    sub = parser.add_subparsers(dest="action", required=True)
    prep = sub.add_parser("prepare", help="build Martini 3 coordinates/topology and validate bead counts")
    prep.add_argument("--output", required=True, type=Path)
    prep.add_argument("--forcefield-dir", type=Path, help="official v3.0.0/gmx_files directory")
    prep.add_argument("--fetch-forcefield", action="store_true", help="fetch pinned official GitHub archive")
    prep.add_argument("--prod-ns", type=float, default=10.0)
    prep.add_argument("--seed", type=int, default=20261030)
    runner = sub.add_parser("run", help="execute EM/NVT/NPT/production with GROMACS")
    runner.add_argument("--workdir", required=True, type=Path)
    runner.add_argument("--gmx", default="gmx")
    runner.add_argument("--gpu-id", type=int, default=0)
    runner.add_argument("--dry-run", action="store_true", help="print commands, never invoke gmx")
    args = parser.parse_args(argv)
    try:
        result = (prepare(args.output.resolve(), args.forcefield_dir.resolve() if args.forcefield_dir else None,
                          args.fetch_forcefield, args.prod_ns, args.seed)
                  if args.action == "prepare" else
                  run(args.workdir.resolve(), args.gmx, args.gpu_id, args.dry_run))
    except (PilotError, OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
