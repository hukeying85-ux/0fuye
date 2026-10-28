"""Generate a GROMACS ``index.ndx`` for Martini membrane systems.

``gmx make_ndx`` is interactive and its default groups are unusable for
Martini (every bead is an "atom"), so the file is written directly from the
``.gro`` produced by ``insane``.  Groups produced:

======  ====================================================================
System  everything (required by several gmx analysis tools)
Peptide the Martini beads of the peptide (first N atoms of the box)
Membrane all lipid beads (POPE + POPG by default)
POPE    / POPG  per lipid species
Water   W beads
Ions    NA / CL / K / CA / MG ...
Headgroups  phosphate + choline/amine/ glycerol beads of the membrane
Tails   the four tail beads of each lipid (sn-1 and sn-2)
======  ====================================================================
"""

from __future__ import annotations

import os
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

__all__ = ["read_gro", "write_index", "HEADGROUP_BEADS", "SN1_BEADS", "SN2_BEADS"]

HEADGROUP_BEADS = {"PO4", "NH3", "NC3", "GL0", "GL1", "GL2", "ROH", "CNO", "Q0", "Qa"}
SN1_BEADS = {"C1A", "D2A", "C3A", "C4A", "C2A", "C5A", "D1A", "D2A", "D3A", "D4A", "C1A"}
SN2_BEADS = {"C1B", "C2B", "C3B", "C4B", "C5B", "D2B", "D3B", "D4B"}

ION_NAMES = {"NA", "CL", "K", "CA", "MG", "ZN", "NA+", "CL-", "K+", "CA2+", "MG2+"}


def read_gro(path: str) -> Tuple[List[Dict[str, object]], Optional[List[float]]]:
    """Parse a ``.gro`` file into atom records plus the box vector."""
    atoms: List[Dict[str, object]] = []
    box: Optional[List[float]] = None
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        lines = handle.readlines()
    if len(lines) < 3:
        raise ValueError("{} is not a valid .gro file".format(path))
    for line in lines[2:-1]:
        if len(line) < 44:
            continue
        try:
            atoms.append(
                {
                    "resid": int(line[0:5]),
                    "resname": line[5:10].strip(),
                    "atomname": line[10:15].strip(),
                    "index": int(line[15:20]),
                    "x": float(line[20:28]),
                    "y": float(line[28:36]),
                    "z": float(line[36:44]),
                }
            )
        except ValueError:
            continue
    last = lines[-1].split()
    try:
        box = [float(value) for value in last[:3]]
    except ValueError:
        box = None
    return atoms, box


def _write_group(handle, name: str, indices: Sequence[int], per_line: int = 15) -> None:
    if not indices:
        return
    handle.write("[ {} ]\n".format(name))
    for start in range(0, len(indices), per_line):
        handle.write(" ".join(str(value) for value in indices[start:start + per_line]) + "\n")


def write_index(
    gro_path: str,
    out_path: str,
    peptide_atoms: int = 0,
    lipid_names: Iterable[str] = ("POPE", "POPG"),
) -> Dict[str, object]:
    """Write ``index.ndx`` and return a summary of the groups."""
    atoms, box = read_gro(gro_path)
    lipids = {name.upper() for name in lipid_names}
    groups: Dict[str, List[int]] = {name: [] for name in ("System", "Peptide", "Membrane", "Water", "Ions", "Headgroups", "Tails")}
    for name in sorted(lipids):
        groups[name] = []

    for position, atom in enumerate(atoms, start=1):
        resname = str(atom["resname"]).upper()
        atomname = str(atom["atomname"]).upper()
        groups["System"].append(position)
        if position <= peptide_atoms:
            groups["Peptide"].append(position)
            continue
        if resname in lipids:
            groups["Membrane"].append(position)
            groups[resname].append(position)
            if atomname in HEADGROUP_BEADS:
                groups["Headgroups"].append(position)
            if atomname in SN1_BEADS or atomname in SN2_BEADS:
                groups["Tails"].append(position)
        elif resname in ("W", "SW", "PW"):
            groups["Water"].append(position)
        elif resname in ION_NAMES:
            groups["Ions"].append(position)

    directory = os.path.dirname(os.path.abspath(out_path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
        for name, indices in groups.items():
            _write_group(handle, name, indices)
    return {
        "index": out_path,
        "groups": {name: len(indices) for name, indices in groups.items() if indices},
        "atoms": len(atoms),
        "box_nm": box,
    }
