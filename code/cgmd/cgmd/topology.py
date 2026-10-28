"""Assemble a runnable GROMACS topology from ``insane`` + ``martinize2`` output.

``insane`` only writes a ``[ molecules ]`` list and a dangling
``#include "martini.itp"``: it knows nothing about where the Martini 3
parameters live and (depending on the version) uses legacy ion names such as
``NA+``.  ``martinize2`` writes its own small ``.top`` with the real
moleculetype name (``Protein_0``).

This module reconciles the three files:

1. index every ``[ moleculetype ]`` found under the force-field directory
   (recursively), together with its atom count;
2. translate legacy molecule names (``NA+`` -> ``NA``);
3. include the base force-field file(s) (``[ defaults ]`` / ``[ atomtypes ]``)
   plus exactly the files that define the molecules actually used;
4. rewrite ``[ molecules ]`` with the peptide moleculetype from ``martinize2``;
5. cross-check the atom count against the coordinate file.

The result is a self-contained ``topol.top`` that ``gmx grompp`` accepts
without any manual editing.
"""

from __future__ import annotations

import difflib
import glob
import os
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

__all__ = [
    "MoleculeType",
    "MoleculeTypeIndex",
    "ION_ALIASES",
    "parse_molecules",
    "parse_moleculetypes",
    "build_topology",
    "count_gro_atoms",
]

#: legacy (Martini 2 / old insane) -> Martini 3 moleculetype names
ION_ALIASES = {
    "NA+": "NA",
    "CL-": "CL",
    "K+": "K",
    "CA2+": "CA",
    "MG2+": "MG",
    "ZN2+": "ZN",
    "OH-": "OH",
    "SOL": "W",
    "HOH": "W",
    "TIP3": "W",
    "TIP3P": "W",
    "WATER": "W",
}

_ANY_LIPID_HINTS = ("PC", "PE", "PG", "PS", "PA", "PI", "CL", "SM", "CHOL", "GM1")


@dataclass
class MoleculeType:
    name: str
    path: str
    natoms: int
    nrexcl: int = 1


class MoleculeTypeIndex:
    """Index of every ``[ moleculetype ]`` under one or more directories."""

    def __init__(self, roots: Sequence[str]) -> None:
        self.roots: List[str] = []
        for root in roots:
            if root and os.path.isdir(root) and root not in self.roots:
                self.roots.append(root)
        self.types: Dict[str, MoleculeType] = {}
        self.files: List[str] = []
        self.base_files: List[str] = []
        self._scan()

    def _scan(self) -> None:
        for root in self.roots:
            for path in sorted(glob.glob(os.path.join(root, "**", "*.itp"), recursive=True)):
                self.files.append(path)
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as handle:
                        text = handle.read()
                except OSError:
                    continue
                if re.search(r"^\s*\[\s*defaults\s*\]", text, re.MULTILINE) or re.search(
                    r"^\s*\[\s*atomtypes\s*\]", text, re.MULTILINE
                ):
                    if path not in self.base_files:
                        self.base_files.append(path)
                for molecule in parse_moleculetypes(path, text=text):
                    self.types.setdefault(molecule.name, molecule)

    def __contains__(self, name: str) -> bool:
        return name in self.types

    def get(self, name: str) -> Optional[MoleculeType]:
        return self.types.get(name)

    def suggest(self, name: str) -> List[str]:
        return difflib.get_close_matches(name, list(self.types), n=4, cutoff=0.6)

    def describe(self) -> Dict[str, object]:
        return {
            "roots": self.roots,
            "itp_files": len(self.files),
            "base_files": self.base_files,
            "moleculetypes": len(self.types),
            "has_pope": "POPE" in self.types,
            "has_popg": "POPG" in self.types,
            "has_water": "W" in self.types,
        }


def parse_moleculetypes(path: str, text: Optional[str] = None) -> List[MoleculeType]:
    """Extract ``[ moleculetype ]`` blocks (name, nrexcl, atom count)."""
    if text is None:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    found: List[MoleculeType] = []
    section = ""
    current: Optional[Dict[str, object]] = None

    def flush() -> None:
        nonlocal current
        if current is not None and current.get("name"):
            found.append(
                MoleculeType(
                    name=str(current["name"]),
                    path=path,
                    natoms=int(current["natoms"]),
                    nrexcl=int(current["nrexcl"]),
                )
            )
        current = None

    for raw in text.splitlines():
        line = raw.split(";")[0].strip()
        if not line:
            continue
        if line.startswith("["):
            section = line.strip("[]").strip().lower()
            if section == "moleculetype":
                flush()
                current = {"name": None, "nrexcl": 1, "natoms": 0}
            continue
        if line.startswith("#"):
            continue
        if current is None:
            continue
        if section == "moleculetype" and current.get("name") is None:
            parts = line.split()
            current["name"] = parts[0]
            if len(parts) > 1 and parts[1].isdigit():
                current["nrexcl"] = int(parts[1])
            continue
        if section == "atoms":
            current["natoms"] = int(current["natoms"]) + 1
    flush()
    return found


def parse_molecules(top_path: str) -> List[Tuple[str, int]]:
    """Return ``[(molecule, count), ...]`` from a ``.top`` file."""
    entries: List[Tuple[str, int]] = []
    section = ""
    with open(top_path, "r", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.split(";")[0].strip()
            if not line:
                continue
            if line.startswith("["):
                section = line.strip("[]").strip().lower()
                continue
            if section != "molecules" or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[-1].lstrip("-").isdigit():
                entries.append((parts[0], int(parts[-1])))
    return entries


def count_gro_atoms(path: str) -> Optional[int]:
    """Atom count from a ``.gro`` file (second line, or line count - 3)."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            handle.readline()
            second = handle.readline().strip()
        if second.isdigit():
            return int(second)
    except OSError:
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return max(0, sum(1 for _ in handle) - 3)
    except OSError:
        return None


def _include_path(target: str, top_dir: str) -> str:
    try:
        relative = os.path.relpath(os.path.abspath(target), os.path.abspath(top_dir))
    except ValueError:  # different drive on Windows
        relative = os.path.abspath(target)
    return relative.replace(os.sep, "/")


def build_topology(
    insane_top: str,
    peptide_top: str,
    ff_roots: Sequence[str],
    out_path: str,
    system_name: str = "CGMD Martini 3 system",
    peptide_count: Optional[int] = None,
) -> Dict[str, object]:
    """Write a complete ``topol.top`` and return a validation report."""
    index = MoleculeTypeIndex(ff_roots)
    if not index.base_files:
        raise RuntimeError(
            "no force-field base file ([ defaults ] / [ atomtypes ]) found under {}".format(list(ff_roots))
        )

    # 1. peptide moleculetype, straight from martinize2
    peptide_molecules = parse_molecules(peptide_top)
    if not peptide_molecules:
        raise RuntimeError("martinize2 topology {} has no [ molecules ] block".format(peptide_top))
    peptide_name, peptide_number = peptide_molecules[0]
    if peptide_count is not None:
        peptide_number = int(peptide_count)

    peptide_itp_includes: List[str] = []
    peptide_top_dir = os.path.dirname(os.path.abspath(peptide_top))
    with open(peptide_top, "r", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            match = re.match(r'\s*#include\s+"([^"]+)"', raw)
            if match:
                candidate = os.path.join(peptide_top_dir, match.group(1))
                if os.path.exists(candidate):
                    peptide_itp_includes.append(candidate)
    if peptide_name not in index.types and not peptide_itp_includes:
        raise RuntimeError(
            "peptide moleculetype '{}' is not defined by {} and no include was found".format(
                peptide_name, peptide_top
            )
        )

    # 2. molecules produced by insane
    entries = parse_molecules(insane_top)
    if not entries:
        raise RuntimeError("insane topology {} has no [ molecules ] block".format(insane_top))

    resolved: List[Tuple[str, int, Optional[MoleculeType]]] = []
    missing: List[str] = []
    for name, count in entries:
        if name == "Protein":
            resolved.append((peptide_name, peptide_number, None))
            continue
        mapped = ION_ALIASES.get(name.upper(), name)
        info = index.get(mapped)
        if info is None:
            info = index.get(name)
            mapped = name
        if info is None:
            missing.append(name)
            resolved.append((name, count, None))
        else:
            resolved.append((mapped, count, info))
    if missing:
        details = []
        for name in missing:
            hints = index.suggest(name)
            details.append("  {} (did you mean: {})".format(name, ", ".join(hints) if hints else "no close match"))
        raise RuntimeError(
            "moleculetypes missing from the Martini 3 force field:\n{}\nsearched: {}".format(
                "\n".join(details), ", ".join(index.roots)
            )
        )

    # 3. assemble includes (base first, then everything that defines a molecule)
    include_files: List[str] = list(index.base_files)
    for _name, _count, info in resolved:
        if info is not None and info.path not in include_files:
            include_files.append(info.path)
    include_files.extend(path for path in peptide_itp_includes if path not in include_files)

    top_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(top_dir, exist_ok=True)
    lines: List[str] = [
        "; ===================================================================",
        "; CGMD-Engine topology -- generated automatically, do not edit by hand",
        "; Martini 3 force field: {}".format(", ".join(index.roots)),
        "; peptide moleculetype : {} x{}".format(peptide_name, peptide_number),
        "; ===================================================================",
        "",
    ]
    for path in include_files:
        lines.append('#include "{}"'.format(_include_path(path, top_dir)))
    lines += ["", "[ system ]", "; name", system_name, "", "[ molecules ]", "; name  number"]
    for name, count, _info in resolved:
        lines.append("{:<16}{:>8}".format(name, count))
    with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")

    expected_atoms = 0
    for name, count, info in resolved:
        if info is not None:
            expected_atoms += info.natoms * count
    # The peptide itp is not part of the FF index: parse it directly.
    peptide_atoms = 0
    for path in peptide_itp_includes:
        for molecule in parse_moleculetypes(path):
            if molecule.name == peptide_name:
                peptide_atoms = molecule.natoms
                break
    if peptide_atoms:
        expected_atoms += peptide_atoms * peptide_number

    return {
        "topology": out_path,
        "peptide_moleculetype": peptide_name,
        "peptide_atoms_per_copy": peptide_atoms,
        "molecules": [{"name": name, "count": count} for name, count, _info in resolved],
        "includes": include_files,
        "expected_atoms": expected_atoms,
        "forcefield": index.describe(),
    }


def validate_topology(report: Dict[str, object], gro_path: str) -> Dict[str, object]:
    """Compare the topology atom count with the coordinate file."""
    observed = count_gro_atoms(gro_path)
    expected = int(report.get("expected_atoms") or 0)
    ok = observed is None or observed == expected
    return {
        "gro_atoms": observed,
        "topology_atoms": expected,
        "consistent": bool(ok),
        "difference": (observed - expected) if (observed is not None) else None,
    }
