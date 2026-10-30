"""Read-only preflight for the three A-beta project inputs.

This is deliberately not an installer, shell, or simulation engine. It only
inspects three explicitly named GRO files, the project directory, free space,
and executables visible on PATH. A matching sequence is not proof of topology,
protonation, force-field compatibility, docking provenance, or experimental
chemical identity. No source file, working directory, or scheduled task is
modified. Scientific runs must not be started on the strength of this report.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

SOURCE = Path(r"F:\0wsh\asd\gromacs_md")
PROJECT = Path(r"F:\Abeta_MD_20261030_01")
DRIVE = Path("F:\\")
PEPTIDES = {"ylsllqr": "YLSLLQR", "fllhttr": "FLLHTTR", "alllhrc": "ALLLHRC"}
AA = dict(zip(
    ("ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE", "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL"),
    "ARNDCQEGHILKMFPSTWYV",
))
AA.update({"HID": "H", "HIE": "H", "HIP": "H", "HSD": "H", "HSE": "H", "HSP": "H", "CYX": "C"})


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def inspect_gro(path: Path, sequence: str) -> dict:
    """Find exact contiguous residue-name matches without inferring bonds."""
    out = {"path": str(path), "exists": path.is_file(), "expected_sequence": sequence}
    if not out["exists"]:
        return out
    try:
        out["size_bytes"] = path.stat().st_size
        out["sha256"] = sha256(path)
        with path.open(encoding="utf-8", errors="strict") as f:
            title = f.readline().rstrip("\r\n")
            count = int(f.readline().strip())
            if count < 1 or count > 10_000_000:
                raise ValueError("invalid atom count")
            residues = []
            previous_key = None
            for i in range(count):
                line = f.readline()
                if len(line) < 44:
                    raise ValueError(f"truncated atom line {i + 1}")
                key = (line[:5].strip(), line[5:10].strip().upper())
                atom = line[10:15].strip().upper()
                # Validate the fixed-width atom number and coordinates as well.
                int(line[15:20]); float(line[20:28]); float(line[28:36]); float(line[36:44])
                if key != previous_key:
                    residues.append({"number": key[0], "name": key[1], "atoms": []})
                    previous_key = key
                residues[-1]["atoms"].append(atom)
            box = f.readline().split()
            if len(box) not in (3, 9):
                raise ValueError("missing or malformed box")
            [float(x) for x in box]
        letters = ''.join(AA.get(r["name"], "?") for r in residues)
        matches = []
        for i in range(len(residues) - len(sequence) + 1):
            if letters[i:i + len(sequence)] != sequence:
                continue
            group = residues[i:i + len(sequence)]
            # Avoid matching across separate chains/residue resets. GRO residue
            # numbers are modulo 100000 and need not start at one.
            try:
                numbers = [int(r["number"]) for r in group]
            except ValueError:
                continue
            if any((a + 1) % 100000 != b for a, b in zip(numbers, numbers[1:])):
                continue
            matches.append({
                "residue_numbers": [r["number"] for r in group],
                "residue_names": [r["name"] for r in group],
                "n_terminal_atoms": group[0]["atoms"],
                "c_terminal_atoms": group[-1]["atoms"],
                "cysteine_atoms": [r["atoms"] for r in group if AA.get(r["name"]) == "C"],
            })
        out.update(title=title, atom_count=count, matches=matches,
                   status="unique_sequence_match" if len(matches) == 1 else "ambiguous_or_missing")
    except (OSError, ValueError, UnicodeError) as exc:
        out.update(status="error", error=str(exc))
    return out


def survey(source: Path = SOURCE, project: Path = PROJECT, drive: Path = DRIVE) -> dict:
    result = {
        "schema": "abeta.preflight.v1", "mode": "read_only", "source": str(source),
        "project": {"path": str(project), "exists": project.is_dir()},
        "inputs": {name: inspect_gro(source / ("md_" + name) / "complex.gro", seq)
                   for name, seq in PEPTIDES.items()},
        # PATH discovery is not proof of installation or absence elsewhere.
        "executables_on_path": {x: shutil.which(x) for x in ("gmx", "plumed", "westpa", "mkdssp", "dssp", "python")},
        "not_checked": ["DMD license and engine", "force fields and water models", "pose provenance",
                        "covalent topology", "experimental termini and redox state", "simulation readiness"],
    }
    try:
        usage = shutil.disk_usage(drive)
        result["drive"] = {"path": str(drive), "total_bytes": usage.total, "free_bytes": usage.free}
    except OSError as exc:
        result["drive"] = {"path": str(drive), "error": str(exc)}
    return result


def main() -> int:
    if os.name != "nt":
        print(json.dumps({"status": "unsupported", "reason": "desktop preflight requires Windows"}))
        return 2
    try:
        print(json.dumps(survey(), ensure_ascii=True, separators=(",", ":")))
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
