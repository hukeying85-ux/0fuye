"""Turn a one-letter peptide sequence into an all-atom PDB for ``martinize2``.

``martinize2`` needs a *structure*, not a sequence.  Three routes are offered,
in decreasing order of quality:

1. ``--pdb FILE``               -- use an experimentally determined / predicted
                                   structure (AlphaFold2, ColabFold, ...).
2. ``--predictor CMD``          -- run an external predictor template, e.g.
                                   ``colabfold_batch {fasta} {outdir}`` and pick
                                   the best ranked model.
3. built-in builder (default)   -- idealised extended strand (or ideal helix)
                                   built from internal coordinates (NeRF).
                                   This is the classic "no-structure" start for
                                   disordered antimicrobial peptides and is
                                   perfectly adequate for Martini 3, where
                                   every side chain collapses onto one or two
                                   beads.  Elastic-network bonds and the first
                                   20 ns equilibration remove the idealisation.

The builder writes heavy atoms only (hydrogens are dropped anyway with
``martinize2 -ignh``) and keeps bond lengths/angles at their standard values,
so distance based bond perception inside ``martinize2`` is unambiguous.
"""

from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
from typing import Dict, List, Optional, Sequence, Tuple

from core.task_contract import AA_1TO3, TaskError, validate_sequence

__all__ = [
    "build_structure",
    "build_pdb",
    "write_pdb",
    "predict_with_external",
    "check_clashes",
]

Point = Tuple[float, float, float]

#: ideal backbone geometry (Angstrom / degrees)
BOND_N_CA = 1.458
BOND_CA_C = 1.525
BOND_C_N = 1.329
BOND_C_O = 1.231
ANGLE_N_CA_C = 111.0
ANGLE_CA_C_N = 116.2
ANGLE_C_N_CA = 121.7
ANGLE_CA_C_O = 120.5

#: phi/psi used by the built-in builder
TORSIONS = {
    "C": (-139.0, 135.0),  # extended beta-like strand (default: coil input)
    "E": (-139.0, 135.0),
    "H": (-57.0, -47.0),   # ideal alpha-helix
}

OMEGA = 180.0


# ---------------------------------------------------------------------------
# small vector helpers (pure python: no numpy requirement)
# ---------------------------------------------------------------------------
def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(a: Point, factor: float) -> Point:
    return (a[0] * factor, a[1] * factor, a[2] * factor)


def _cross(a: Point, b: Point) -> Point:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a: Point) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a: Point) -> Point:
    length = _norm(a)
    if length < 1e-9:
        return (1.0, 0.0, 0.0)
    return _scale(a, 1.0 / length)


def place(a: Point, b: Point, c: Point, bond: float, angle_deg: float, torsion_deg: float) -> Point:
    """Place atom ``D`` bonded to ``C`` (NeRF internal coordinates).

    ``|D-C| = bond``, ``angle(B, C, D) = angle_deg``, ``dihedral(A, B, C, D) =
    torsion_deg``.  Distances in Angstrom, angles in degrees.
    """
    angle = math.radians(angle_deg)
    torsion = math.radians(torsion_deg)
    bc = _unit(_sub(c, b))
    normal = _unit(_cross(_sub(b, a), bc))
    if _norm(normal) < 1e-6:  # A-B-C collinear: pick any perpendicular
        normal = _unit(_cross(bc, (0.0, 1.0, 0.0)))
        if _norm(normal) < 1e-6:
            normal = _unit(_cross(bc, (1.0, 0.0, 0.0)))
    binormal = _cross(normal, bc)
    offset = (
        -bond * math.cos(angle),
        bond * math.sin(angle) * math.cos(torsion),
        bond * math.sin(angle) * math.sin(torsion),
    )
    return (
        c[0] + offset[0] * bc[0] + offset[1] * binormal[0] + offset[2] * normal[0],
        c[1] + offset[0] * bc[1] + offset[1] * binormal[1] + offset[2] * normal[1],
        c[2] + offset[0] * bc[2] + offset[1] * binormal[2] + offset[2] * normal[2],
    )


def _dist(a: Point, b: Point) -> float:
    return _norm(_sub(a, b))


# ---------------------------------------------------------------------------
# side chain builders
# ---------------------------------------------------------------------------
# chi1 defaults (degrees) -- standard rotamer-like values, extended where it
# matters so that neighbouring side chains do not interpenetrate.
CHI1 = {
    "A": -60.0, "R": -65.0, "N": -65.0, "D": -65.0, "C": 60.0, "Q": -65.0,
    "E": -65.0, "G": 0.0, "H": -65.0, "I": -60.0, "L": -60.0, "K": -65.0,
    "M": -65.0, "F": -65.0, "P": -30.0, "S": 60.0, "T": 60.0, "W": -65.0,
    "Y": -65.0, "V": -60.0,
}
CHI2 = 180.0
CHI1_3 = {AA_1TO3[one]: value for one, value in CHI1.items()}
CHI3 = -65.0
CHI4 = 180.0

# planar ring geometry
RING_CC = 1.39   # aromatic C-C
RING_CN = 1.36   # aromatic C-N
RING_CO = 1.36   # phenol C-O


def _cbb(atom: Dict[str, Point], res: str, torsion: float = 122.6) -> Point:
    """Place CB using (N, C, CA) as reference: angle C-CA-CB, torsion N-C-CA-CB."""
    return place(atom["N"], atom["C"], atom["CA"], 1.530, 110.5, torsion)


def _walk(start: Tuple[float, float], side: float, step_deg: float, count: int) -> List[Tuple[float, float]]:
    """Walk along a regular polygon (2D): ``count`` steps of length ``side``
    with a fixed turn of ``step_deg`` degrees (exterior angle)."""
    x, y = start
    heading = 0.0
    points: List[Tuple[float, float]] = []
    for _ in range(count):
        heading += math.radians(step_deg)
        x += side * math.cos(heading)
        y += side * math.sin(heading)
        points.append((x, y))
    return points


def _ring_canvas(
    atom: Dict[str, Point],
    canvas: Dict[str, Tuple[float, float]],
    neighbour: str = "CD1",
) -> None:
    """Attach a planar ring defined on a 2D canvas to the already placed CB.

    The canvas is rotated into 3D so that the bond ``CG -> neighbour`` makes a
    tetrahedral-ish 120 deg angle with ``CB -> CG`` (the ideal value for an
    aromatic ring), and so that the ring plane orientation is set by chi2.
    """
    res = atom["_res"]
    origin2 = canvas["CG"]
    direction2 = (canvas[neighbour][0] - origin2[0], canvas[neighbour][1] - origin2[1])
    length = math.hypot(*direction2)
    if length < 1e-9:  # pragma: no cover - defensive
        direction2, length = (1.0, 0.0), 1.0
    ux, uy = direction2[0] / length, direction2[1] / length
    # 2D -> local ring frame: x along CG->neighbour, y perpendicular
    local: Dict[str, Tuple[float, float]] = {}
    for name, (x, y) in canvas.items():
        dx, dy = x - origin2[0], y - origin2[1]
        local[name] = (dx * ux + dy * uy, -dx * uy + dy * ux)

    origin = atom["CG"]
    e1 = _unit(_sub(origin, atom["CB"]))                 # CB -> CG
    ref = _unit(_sub(atom["CB"], atom["CA"]))
    perp = _sub(ref, _scale(e1, _dot(ref, e1)))
    if _norm(perp) < 1e-6:  # pragma: no cover - defensive
        perp = _cross(e1, (0.0, 0.0, 1.0))
    perp = _unit(perp)
    # direction of the CG -> neighbour bond: 120 deg away from CB -> CG
    ring_x = _add(
        _scale(e1, math.cos(math.radians(120.0))),
        _scale(perp, math.sin(math.radians(120.0))),
    )
    ring_x = _unit(ring_x)
    normal = _unit(_cross(e1, ring_x))
    chi = math.radians(90.0 if res in ("PHE", "TYR", "TRP", "HIS") else 0.0)
    ring_x = _add(_scale(ring_x, math.cos(chi)), _scale(normal, math.sin(chi)))
    normal = _unit(_cross(e1, ring_x))

    for name, (x, y) in local.items():
        if name == "CG":
            continue
        atom[name] = _add(origin, _add(_scale(ring_x, x), _scale(normal, y)))


def _sidechain(atom: Dict[str, Point], res: str) -> None:
    """Build the side chain of ``res`` in place (heavy atoms only)."""
    atom["_res"] = res  # type: ignore[assignment]
    if res == "GLY":
        return
    atom["CB"] = _cbb(atom, res)
    if res == "ALA":
        return
    chi1 = CHI1_3[res]

    if res == "SER":
        atom["OG"] = place(atom["N"], atom["CA"], atom["CB"], 1.417, 110.7, chi1)
    elif res == "CYS":
        atom["SG"] = place(atom["N"], atom["CA"], atom["CB"], 1.808, 114.4, chi1)
    elif res == "THR":
        atom["OG1"] = place(atom["N"], atom["CA"], atom["CB"], 1.433, 109.6, chi1)
        atom["CG2"] = place(atom["N"], atom["CA"], atom["CB"], 1.521, 110.5, chi1 + 120.0)
    elif res == "VAL":
        atom["CG1"] = place(atom["N"], atom["CA"], atom["CB"], 1.521, 110.5, chi1)
        atom["CG2"] = place(atom["N"], atom["CA"], atom["CB"], 1.521, 110.5, chi1 + 120.0)
    elif res == "LEU":
        atom["CG"] = place(atom["N"], atom["CA"], atom["CB"], 1.530, 116.3, chi1)
        atom["CD1"] = place(atom["CA"], atom["CB"], atom["CG"], 1.521, 110.5, CHI2)
        atom["CD2"] = place(atom["CA"], atom["CB"], atom["CG"], 1.521, 110.5, CHI2 + 120.0)
    elif res == "ILE":
        atom["CG1"] = place(atom["N"], atom["CA"], atom["CB"], 1.530, 110.4, chi1)
        atom["CG2"] = place(atom["N"], atom["CA"], atom["CB"], 1.521, 110.5, chi1 + 120.0)
        atom["CD1"] = place(atom["CA"], atom["CB"], atom["CG1"], 1.513, 113.8, 170.0)
    elif res == "MET":
        atom["CG"] = place(atom["N"], atom["CA"], atom["CB"], 1.520, 114.1, chi1)
        atom["SD"] = place(atom["CA"], atom["CB"], atom["CG"], 1.803, 112.7, CHI2)
        atom["CE"] = place(atom["CB"], atom["CG"], atom["SD"], 1.791, 100.9, CHI3)
    elif res in ("PHE", "TYR"):
        atom["CG"] = place(atom["N"], atom["CA"], atom["CB"], 1.510, 114.0, chi1)
        # regular hexagon CG-CD1-CE1-CZ-CE2-CD2 (side 1.39 A)
        cg, cd1, ce1, cz, ce2, cd2 = _walk((0.0, 0.0), RING_CC, 60.0, 6)[:6]
        canvas = {"CG": cg, "CD1": cd1, "CE1": ce1, "CZ": cz, "CE2": ce2, "CD2": cd2}
        _ring_canvas(atom, canvas, neighbour="CD1")
        if res == "TYR":
            atom["OH"] = place(atom["CE2"], atom["CD2"], atom["CZ"], RING_CO, 119.9, 180.0)
    elif res == "HIS":
        atom["CG"] = place(atom["N"], atom["CA"], atom["CB"], 1.500, 113.0, chi1)
        # regular pentagon CG-CD2-NE2-CE1-ND1 (side 1.36 A)
        cg, cd2, ne2, ce1, nd1 = _walk((0.0, 0.0), RING_CN, 72.0, 5)[:5]
        canvas = {"CG": cg, "CD2": cd2, "NE2": ne2, "CE1": ce1, "ND1": nd1}
        _ring_canvas(atom, canvas, neighbour="CD2")
    elif res == "TRP":
        atom["CG"] = place(atom["N"], atom["CA"], atom["CB"], 1.510, 114.0, chi1)
        # indole = pentagon (CD2-CE2-NE1-CD1-CG) fused to a hexagon
        # (CD2-CE2-CZ2-CH2-CZ3-CE3) sharing the CD2-CE2 edge.
        cd2 = (0.0, 0.0)
        ce2 = (RING_CC, 0.0)
        ne1, cd1, cg = _walk(ce2, RING_CC, -72.0, 3)      # closes onto CD2
        cz2, ch2, cz3, ce3 = _walk(ce2, RING_CC, 60.0, 4)  # closes onto CD2
        canvas = {
            "CG": cg, "CD1": cd1, "NE1": ne1, "CE2": ce2, "CD2": cd2,
            "CE3": ce3, "CZ3": cz3, "CH2": ch2, "CZ2": cz2,
        }
        _ring_canvas(atom, canvas, neighbour="CD2")
    elif res == "ASP":
        atom["CG"] = place(atom["N"], atom["CA"], atom["CB"], 1.516, 113.5, chi1)
        atom["OD1"] = place(atom["CA"], atom["CB"], atom["CG"], 1.249, 118.9, CHI2)
        atom["OD2"] = place(atom["CA"], atom["CB"], atom["CG"], 1.249, 118.9, CHI2 + 180.0)
    elif res == "ASN":
        atom["CG"] = place(atom["N"], atom["CA"], atom["CB"], 1.516, 113.5, chi1)
        atom["OD1"] = place(atom["CA"], atom["CB"], atom["CG"], 1.231, 120.8, CHI2)
        atom["ND2"] = place(atom["CA"], atom["CB"], atom["CG"], 1.328, 117.0, CHI2 + 180.0)
    elif res == "GLU":
        atom["CG"] = place(atom["N"], atom["CA"], atom["CB"], 1.520, 114.1, chi1)
        atom["CD"] = place(atom["CA"], atom["CB"], atom["CG"], 1.516, 113.5, CHI2)
        atom["OE1"] = place(atom["CB"], atom["CG"], atom["CD"], 1.250, 118.9, CHI3)
        atom["OE2"] = place(atom["CB"], atom["CG"], atom["CD"], 1.250, 118.9, CHI3 + 180.0)
    elif res == "GLN":
        atom["CG"] = place(atom["N"], atom["CA"], atom["CB"], 1.520, 114.1, chi1)
        atom["CD"] = place(atom["CA"], atom["CB"], atom["CG"], 1.516, 113.5, CHI2)
        atom["OE1"] = place(atom["CB"], atom["CG"], atom["CD"], 1.231, 120.8, CHI3)
        atom["NE2"] = place(atom["CB"], atom["CG"], atom["CD"], 1.328, 117.0, CHI3 + 180.0)
    elif res == "LYS":
        atom["CG"] = place(atom["N"], atom["CA"], atom["CB"], 1.520, 114.1, chi1)
        atom["CD"] = place(atom["CA"], atom["CB"], atom["CG"], 1.520, 111.3, CHI2)
        atom["CE"] = place(atom["CB"], atom["CG"], atom["CD"], 1.520, 111.3, CHI3)
        atom["NZ"] = place(atom["CG"], atom["CD"], atom["CE"], 1.489, 111.9, CHI4)
    elif res == "ARG":
        atom["CG"] = place(atom["N"], atom["CA"], atom["CB"], 1.520, 114.1, chi1)
        atom["CD"] = place(atom["CA"], atom["CB"], atom["CG"], 1.520, 111.3, CHI2)
        atom["NE"] = place(atom["CB"], atom["CG"], atom["CD"], 1.460, 112.0, CHI3)
        atom["CZ"] = place(atom["CG"], atom["CD"], atom["NE"], 1.330, 124.2, 180.0)
        atom["NH1"] = place(atom["CD"], atom["NE"], atom["CZ"], 1.326, 120.0, 180.0)
        atom["NH2"] = place(atom["CD"], atom["NE"], atom["CZ"], 1.326, 120.0, 0.0)
    elif res == "PRO":
        # pyrrolidine ring: close CB -> CG -> CD -> N by scanning chi2
        atom["CG"] = place(atom["N"], atom["CA"], atom["CB"], 1.492, 104.0, chi1)
        best: Optional[Tuple[float, Point]] = None
        for torsion in range(-80, 81, 2):
            candidate = place(atom["CA"], atom["CB"], atom["CG"], 1.503, 105.0, float(torsion))
            error = abs(_dist(candidate, atom["N"]) - 1.473)
            if best is None or error < best[0]:
                best = (error, candidate)
        atom["CD"] = best[1]
    else:  # pragma: no cover - unreachable for the 20 standard residues
        raise TaskError("no side chain builder for {}".format(res))


# ---------------------------------------------------------------------------
# peptide assembly
# ---------------------------------------------------------------------------
def _backbone(sequence: str, ss: str = "C") -> List[Dict[str, object]]:
    """Build all atoms of the peptide as a list of residue dictionaries."""
    phi0, psi0 = TORSIONS.get((ss or "C").upper(), TORSIONS["C"])
    residues: List[Dict[str, object]] = []
    previous: Dict[str, Point] = {}

    for index, one_letter in enumerate(sequence):
        resname = AA_1TO3[one_letter]
        atom: Dict[str, Point] = {}
        if index == 0:
            atom["N"] = (0.0, 0.0, 0.0)
            atom["CA"] = (BOND_N_CA, 0.0, 0.0)
            atom["C"] = place((0.0, 1.0, 0.0), atom["N"], atom["CA"], BOND_CA_C, ANGLE_N_CA_C, 180.0)
            atom["O"] = place(atom["N"], atom["CA"], atom["C"], BOND_C_O, ANGLE_CA_C_O, psi0 - 180.0)
        else:
            n_prev, ca_prev, c_prev = previous["N"], previous["CA"], previous["C"]
            atom["N"] = place(n_prev, ca_prev, c_prev, BOND_C_N, ANGLE_CA_C_N, psi0)
            atom["CA"] = place(ca_prev, c_prev, atom["N"], BOND_N_CA, ANGLE_C_N_CA, OMEGA)
            atom["C"] = place(c_prev, atom["N"], atom["CA"], BOND_CA_C, ANGLE_N_CA_C, phi0)
            atom["O"] = place(atom["N"], atom["CA"], atom["C"], BOND_C_O, ANGLE_CA_C_O, psi0 - 180.0)

        _sidechain(atom, resname)
        for key in [k for k in atom if k.startswith("_")]:
            atom.pop(key)
        residues.append({"_name": resname, "_one": one_letter, "atoms": atom})
        previous = atom

    return residues


def check_clashes(residues: Sequence[Dict[str, object]], cutoff: float = 1.0) -> List[str]:
    """Report atoms of different residues that are closer than ``cutoff`` A."""
    problems: List[str] = []
    flat: List[Tuple[int, str, Point]] = []
    for index, residue in enumerate(residues):
        for name, coord in residue["atoms"].items():  # type: ignore[union-attr]
            flat.append((index, name, coord))
    for i in range(len(flat)):
        res_i, name_i, coord_i = flat[i]
        for j in range(i + 1, len(flat)):
            res_j, name_j, coord_j = flat[j]
            if abs(res_i - res_j) <= 1:
                continue
            if _dist(coord_i, coord_j) < cutoff:
                problems.append(
                    "clash {}{} - {}{} ({:.2f} A)".format(
                        residues[res_i]["_name"],
                        name_i,
                        residues[res_j]["_name"],
                        name_j,
                        _dist(coord_i, coord_j),
                    )
                )
                if len(problems) > 10:
                    return problems
    return problems


def write_pdb(residues: Sequence[Dict[str, object]], path: str, title: str = "CGMD peptide") -> str:
    """Write heavy atoms in PDB format (chain A, sequential resids)."""
    lines: List[str] = ["REMARK   1 {}".format(title)]
    serial = 0
    for index, residue in enumerate(residues, start=1):
        atoms: Dict[str, Point] = residue["atoms"]  # type: ignore[assignment]
        order = [name for name in ("N", "CA", "C", "O") if name in atoms]
        order += [name for name in atoms if name not in order]
        for name in order:
            serial += 1
            x, y, z = atoms[name]
            element = "S" if name.startswith("S") else ("O" if name.startswith("O") else ("N" if name.startswith("N") else "C"))
            lines.append(
                "ATOM  {:5d} {:>4s} {:>3s} A{:4d}    {:8.3f}{:8.3f}{:8.3f}{:6.2f}{:6.2f}          {:>2s}".format(
                    serial, name, residue["_name"], index, x, y, z, 1.0, 0.0, element
                )
            )
    lines.append("TER")
    lines.append("END")
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="ascii", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    return path


def build_pdb(
    sequence: str,
    path: str,
    ss: str = "C",
    title: Optional[str] = None,
) -> Dict[str, object]:
    """Build an idealised all-atom peptide and write it to ``path``."""
    sequence = validate_sequence(sequence)
    residues = _backbone(sequence, ss=ss)
    clashes = check_clashes(residues)
    write_pdb(residues, path, title=title or "CGMD built peptide")
    return {
        "path": path,
        "residues": len(residues),
        "heavy_atoms": sum(len(r["atoms"]) for r in residues),  # type: ignore[arg-type]
        "secondary_structure": (ss or "C").upper(),
        "clashes": clashes,
        "method": "builtin-extended" if (ss or "C").upper() not in ("H",) else "builtin-helix",
    }


# ---------------------------------------------------------------------------
# external structure prediction
# ---------------------------------------------------------------------------
def predict_with_external(
    sequence: str,
    workdir: str,
    command_template: str,
    timeout: int = 1800,
) -> str:
    """Run a user supplied predictor and return the PDB it produced.

    ``command_template`` may use ``{fasta}``, ``{outdir}``, ``{name}`` and
    ``{sequence}``.  The first ``*.pdb`` found inside ``{outdir}`` is returned;
    ColabFold style ``*_unrelaxed_rank_001*.pdb`` files are preferred.
    """
    sequence = validate_sequence(sequence)
    outdir = os.path.abspath(os.path.join(workdir, "prediction"))
    os.makedirs(outdir, exist_ok=True)
    fasta = os.path.join(outdir, "peptide.fasta")
    with open(fasta, "w", encoding="ascii", newline="\n") as handle:
        handle.write(">peptide\n{}\n".format(sequence))
    command = command_template.format(fasta=fasta, outdir=outdir, name="peptide", sequence=sequence)
    completed = subprocess.run(
        command, shell=True, cwd=outdir, capture_output=True, text=True, timeout=timeout
    )
    if completed.returncode != 0:
        raise TaskError(
            "structure predictor failed ({}): {}".format(completed.returncode, (completed.stderr or "")[-800:])
        )
    candidates: List[str] = []
    for root, _dirs, files in os.walk(outdir):
        for name in files:
            if name.lower().endswith(".pdb"):
                candidates.append(os.path.join(root, name))
    if not candidates:
        raise TaskError("structure predictor produced no PDB in {}".format(outdir))
    preferred = [path for path in candidates if re.search(r"rank_001|ranked_0|best", os.path.basename(path), re.IGNORECASE)]
    chosen = sorted(preferred or candidates)[0]
    final = os.path.join(workdir, "peptide_atomistic.pdb")
    shutil.copyfile(chosen, final)
    return final


def build_structure(
    sequence: str,
    workdir: str,
    pdb_path: Optional[str] = None,
    predictor: Optional[str] = None,
    ss: str = "C",
) -> Dict[str, object]:
    """Resolve the all-atom input structure (explicit PDB > predictor > builder)."""
    os.makedirs(workdir, exist_ok=True)
    if pdb_path:
        if not os.path.exists(pdb_path):
            raise TaskError("structure_pdb not found: {}".format(pdb_path))
        target = os.path.join(workdir, "peptide_atomistic.pdb")
        if os.path.abspath(pdb_path) != os.path.abspath(target):
            shutil.copyfile(pdb_path, target)
        return {"path": target, "method": "provided-pdb", "source": pdb_path}
    if predictor:
        path = predict_with_external(sequence, workdir, predictor)
        return {"path": path, "method": "external-predictor", "source": predictor}
    info = build_pdb(sequence, os.path.join(workdir, "peptide_atomistic.pdb"), ss=ss)
    info["source"] = "builtin"
    return info
