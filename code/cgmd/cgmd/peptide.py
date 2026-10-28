"""Physico-chemical description of candidate antimicrobial peptides.

All values are computed from first principles with the standard residue scales
so that ``summary_metrics.json`` is self-describing and reproducible, and so
that peptides can be ranked *before* burning GPU hours:

* net charge at pH 7.4 (Henderson-Hasselbalch, Hill-style with pKa table);
* isoelectric point (bisection on the charge curve);
* GRAVY (Kyte & Doolittle hydropathy);
* mean hydrophobic moment <mu_H> (Eisenberg consensus scale, 100 deg per
  residue for an ideal alpha-helix, 160 deg for a beta-strand);
* crude molar mass and helical-wheel-friendly per-residue data.

Pure standard library: this module is imported by the desktop runner, the
analysis stage and (optionally) the phone-side pre-check.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from core.task_contract import AA_1TO3, TaskError, validate_sequence

__all__ = [
    "AA_1TO3",
    "AA_MASS",
    "KYTE_DOOLITTLE",
    "EISENBERG",
    "PKAS",
    "net_charge",
    "isoelectric_point",
    "gravy",
    "hydrophobic_moment",
    "molar_mass",
    "describe",
    "to_fasta",
]

AA_1TO3.update  # keep the imported mapping visible to type checkers

AA_MASS = {  # average residue masses in Da (free amino acid minus water)
    "A": 71.08, "R": 156.19, "N": 114.10, "D": 115.09, "C": 103.14,
    "Q": 128.13, "E": 129.12, "G": 57.05, "H": 137.14, "I": 113.16,
    "L": 113.16, "K": 128.17, "M": 131.20, "F": 147.18, "P": 97.12,
    "S": 87.08, "T": 101.10, "W": 186.21, "Y": 163.18, "V": 99.13,
}

KYTE_DOOLITTLE = {
    "A": 1.8, "R": -4.5, "N": -3.5, "D": -3.5, "C": 2.5,
    "Q": -3.5, "E": -3.5, "G": -0.4, "H": -3.2, "I": 4.5,
    "L": 3.8, "K": -3.9, "M": 1.9, "F": 2.8, "P": -1.6,
    "S": -0.8, "T": -0.7, "W": -0.9, "Y": -1.3, "V": 4.2,
}

# Eisenberg consensus hydrophobicity scale (used for hydrophobic moments)
EISENBERG = {
    "A": 0.62, "R": -2.53, "N": -0.78, "D": -0.90, "C": 0.29,
    "Q": -0.85, "E": -0.74, "G": 0.48, "H": -0.40, "I": 1.38,
    "L": 1.06, "K": -1.50, "M": 0.64, "F": 1.19, "P": 0.12,
    "S": -0.18, "T": -0.05, "W": 0.81, "Y": 0.26, "V": 1.08,
}

# pKa values used for the charge model (side chain + termini)
PKAS = {
    "N_term": 9.69,
    "C_term": 2.34,
    "D": 3.65,
    "E": 4.25,
    "C": 8.18,
    "Y": 10.07,
    "H": 6.00,
    "K": 10.53,
    "R": 12.50,
}

POSITIVE = set("KR")
NEGATIVE = set("DE")


def _clean(sequence: str) -> str:
    return validate_sequence(sequence)


def net_charge(sequence: str, ph: float = 7.4) -> float:
    """Net charge in elementary charges at ``ph``."""
    seq = _clean(sequence)
    charge = 0.0
    # positive groups
    charge += 1.0 / (1.0 + 10.0 ** (ph - PKAS["N_term"]))
    for residue in ("K", "R", "H"):
        count = seq.count(residue)
        if count:
            charge += count / (1.0 + 10.0 ** (ph - PKAS[residue]))
    # negative groups
    charge -= 1.0 / (1.0 + 10.0 ** (PKAS["C_term"] - ph))
    for residue in ("D", "E", "C", "Y"):
        count = seq.count(residue)
        if count:
            charge -= count / (1.0 + 10.0 ** (PKAS[residue] - ph))
    return charge


def isoelectric_point(sequence: str, tolerance: float = 1e-3) -> float:
    """pH at which the net charge vanishes (bisection, 0..14)."""
    _clean(sequence)
    low, high = 0.0, 14.0
    for _ in range(60):
        mid = 0.5 * (low + high)
        if net_charge(sequence, mid) > 0:
            low = mid
        else:
            high = mid
        if high - low < tolerance:
            break
    return round(0.5 * (low + high), 2)


def gravy(sequence: str) -> float:
    """Grand average of hydropathy (Kyte & Doolittle)."""
    seq = _clean(sequence)
    return round(sum(KYTE_DOOLITTLE[aa] for aa in seq) / float(len(seq)), 3)


def hydrophobic_moment(
    sequence: str,
    window: int = 11,
    angle_deg: float = 100.0,
) -> Dict[str, float]:
    """Mean hydrophobic moment ``<mu_H>`` and the best window position.

    ``angle_deg`` is the rotation per residue: 100 deg for an ideal
    alpha-helix, 160 deg for an extended beta-strand (Eisenberg convention).
    """
    seq = _clean(sequence)
    window = max(3, min(int(window), len(seq)))
    angle = math.radians(angle_deg)
    best = {"mu_h": 0.0, "start": 0, "end": window, "window": window, "angle_deg": angle_deg}
    mean_overall = 0.0
    windows = 0
    for start in range(0, len(seq) - window + 1):
        sin_sum = 0.0
        cos_sum = 0.0
        for offset, aa in enumerate(seq[start:start + window]):
            value = EISENBERG[aa]
            sin_sum += value * math.sin(offset * angle)
            cos_sum += value * math.cos(offset * angle)
        mu = math.hypot(sin_sum, cos_sum) / window
        mean_overall += mu
        windows += 1
        if mu > best["mu_h"]:
            best.update({"mu_h": mu, "start": start + 1, "end": start + window})
    if windows:
        best["mu_h_mean_all_windows"] = round(mean_overall / windows, 3)
    best["mu_h"] = round(best["mu_h"], 3)
    return best


def molar_mass(sequence: str) -> float:
    """Approximate molar mass in Da (residue masses + one water)."""
    seq = _clean(sequence)
    return round(sum(AA_MASS[aa] for aa in seq) + 18.015, 2)


def helical_wheel(sequence: str, residues_per_turn: float = 3.6) -> List[Dict[str, float]]:
    """Positions of residues on an ideal helical wheel (for plotting)."""
    seq = _clean(sequence)
    out = []
    for index, aa in enumerate(seq):
        theta = 2.0 * math.pi * (index / residues_per_turn)
        out.append(
            {
                "index": index + 1,
                "residue": aa,
                "x": round(math.cos(theta), 4),
                "y": round(math.sin(theta), 4),
                "hydrophobicity": EISENBERG[aa],
            }
        )
    return out


def amphipathic_face_ratio(sequence: str) -> float:
    """Fraction of hydrophobic residues on the most hydrophobic helix face.

    A crude but useful discriminator for membrane-active AMPs: high values
    (>= 0.4) indicate a well segregated amphipathic helix.
    """
    seq = _clean(sequence)
    if len(seq) < 7:
        return 0.0
    best = 0.0
    for shift in range(0, 5):
        hydrophobic = 0
        total = 0
        for index, aa in enumerate(seq):
            if (index + shift) % 5 in (0, 1, 2):
                total += 1
                if EISENBERG[aa] > 0.2:
                    hydrophobic += 1
        if total:
            best = max(best, hydrophobic / float(total))
    return round(best, 3)


def describe(sequence: str, ph: float = 7.4) -> Dict[str, object]:
    """Full descriptor block written into ``summary_metrics.json``."""
    seq = _clean(sequence)
    moment = hydrophobic_moment(seq)
    charge = net_charge(seq, ph)
    return {
        "sequence": seq,
        "length": len(seq),
        "three_letter": [AA_1TO3[aa] for aa in seq],
        "net_charge_ph7_4": round(charge, 2),
        "net_charge_int": int(round(charge)),
        "isoelectric_point": isoelectric_point(seq),
        "gravy": gravy(seq),
        "hydrophobic_moment_helix": moment["mu_h"],
        "hydrophobic_moment_window": [moment["start"], moment["end"]],
        "hydrophobic_moment_beta": hydrophobic_moment(seq, angle_deg=160.0)["mu_h"],
        "amphipathic_face_ratio": amphipathic_face_ratio(seq),
        "molar_mass_da": molar_mass(seq),
        "composition": {aa: seq.count(aa) for aa in sorted(set(seq))},
        "cationic_residues": sum(seq.count(aa) for aa in POSITIVE),
        "anionic_residues": sum(seq.count(aa) for aa in NEGATIVE),
        "aromatic_residues": sum(seq.count(aa) for aa in "FWY"),
        "ph": ph,
    }


def to_fasta(sequence: str, name: str = "peptide", width: int = 60) -> str:
    """FASTA text for the given peptide (used for ``martinize2`` inputs)."""
    seq = _clean(sequence)
    lines = [">{}".format(name)]
    for start in range(0, len(seq), width):
        lines.append(seq[start:start + width])
    return "\n".join(lines) + "\n"


def canonical_name(sequence: str) -> str:
    seq = _clean(sequence)
    return "pep-{}aa-{:+.0f}".format(len(seq), net_charge(seq))
