"""Reduced analysis of a Martini 3 peptide/membrane trajectory.

Everything computed here ends up in ``summary_metrics.json`` (< 1 MB) and in
SVG figures, which are the only artefacts that travel back to git.  The
trajectory itself stays on the workstation.

Metrics
-------
``membrane_insertion``
    Peptide bead centroid depth below/above the bilayer mid-plane
    (``z_distance_nm``; negative = inserted towards the lower leaflet), the
    per-residue depth profile and the fraction of frames spent in the
    interfacial / core region.

``lipid_order``
    Martini tail order parameter ``S = <P2(cos theta)>`` of the sn-1 and sn-2
    chains (theta = angle between consecutive tail-bead bonds and the bilayer
    normal), overall and per species.

``pore``
    Water beads inside a cylinder (radius ``pore_radius_nm``) around the
    peptide lateral position, restricted to the membrane core slab; normalised
    by the bulk water number density to give a pore score in [0, ...).

``membrane``
    Bilayer thickness (phosphate-to-phosphate distance) and area per lipid.

The analysis is deliberately linear in the number of frames and uses numpy
vectorisation where it matters; a 1 us / 19k bead system is processed in a
couple of minutes on a laptop.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "AnalysisUnavailable",
    "analyse_trajectory",
    "summarise_logs",
    "write_summary",
    "decimate",
]


class AnalysisUnavailable(RuntimeError):
    """Raised when trajectory analysis cannot run (missing backend/files)."""


def decimate(values: Sequence[float], max_points: int = 400) -> List[float]:
    """Evenly thin a series so that JSON stays small but shapes are kept."""
    values = list(values)
    if len(values) <= max_points:
        return [round(float(value), 4) for value in values]
    stride = max(1, int(math.ceil(len(values) / float(max_points))))
    thinned = values[::stride]
    if thinned and values and thinned[-1] != values[-1]:
        thinned.append(values[-1])
    return [round(float(value), 4) for value in thinned]


def _pbc_delta(delta: Any, box: float) -> Any:
    try:  # numpy arrays
        import numpy as _np

        return delta - box * _np.round(delta / box)
    except Exception:  # pragma: no cover - scalar fallback
        return delta - box * round(delta / box)


def _stats(values: Sequence[float]) -> Dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "std": None, "min": None, "max": None}
    import statistics

    return {
        "n": len(values),
        "mean": round(statistics.fmean(values), 4),
        "std": round(statistics.pstdev(values), 4) if len(values) > 1 else 0.0,
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def _require_mdanalysis():
    try:
        import MDAnalysis as mda  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise AnalysisUnavailable(
            "MDAnalysis is required for trajectory analysis: pip install MDAnalysis "
            "(the summary can still be produced from logs with --no-trajectory). "
            "original error: {}".format(exc)
        )
    return mda


def analyse_trajectory(
    gro_path: str,
    xtc_path: str,
    peptide_atoms: int,
    lipid_resnames: Sequence[str],
    pore_radius_nm: float = 1.2,
    water_core_halfheight_nm: float = 0.9,
    max_frames: int = 400,
    equilibrated_fraction: float = 0.5,
) -> Dict[str, Any]:
    """Compute insertion depth, tail order parameters and pore metrics."""
    if not os.path.exists(xtc_path):
        raise AnalysisUnavailable("trajectory not found: {}".format(xtc_path))
    mda = _require_mdanalysis()
    import numpy as np

    universe = mda.Universe(gro_path, xtc_path)
    total_frames = len(universe.trajectory)
    if total_frames == 0:
        raise AnalysisUnavailable("empty trajectory")
    stride = max(1, int(math.ceil(total_frames / float(max_frames))))

    atoms = universe.atoms
    resnames = np.array([str(name).upper() for name in atoms.resnames])
    atomnames = np.array([str(name).upper() for name in atoms.names])
    peptide_mask = np.arange(len(atoms)) < int(peptide_atoms)
    water_mask = np.isin(resnames, ["W", "SW", "PW"])
    lipid_mask = np.isin(resnames, [name.upper() for name in lipid_resnames])
    phosphate_mask = lipid_mask & (atomnames == "PO4")

    if not lipid_mask.any():
        raise AnalysisUnavailable("no lipid beads found (expected {})".format(list(lipid_resnames)))

    # --- tail bond pairs for the order parameter -------------------------
    chains = {
        "sn1": ["C1A", "D2A", "C2A", "C3A", "C4A", "C5A"],
        "sn2": ["C1B", "D2B", "C2B", "C3B", "C4B", "C5B"],
    }
    by_residue: Dict[int, Dict[str, int]] = {}
    for position, (resid, name) in enumerate(zip(atoms.resids, atomnames)):
        if lipid_mask[position]:
            by_residue.setdefault(int(resid), {})[str(name)] = position
    bond_pairs: Dict[str, List[Tuple[int, int]]] = {"sn1": [], "sn2": []}
    for _resid, names in by_residue.items():
        for chain, order in chains.items():
            present = [names[name] for name in order if name in names]
            for first, second in zip(present[:-1], present[1:]):
                bond_pairs[chain].append((first, second))

    species_pairs: Dict[str, Dict[str, List[Tuple[int, int]]]] = {}
    for species in {str(name).upper() for name in lipid_resnames}:
        subset = [
            (first, second)
            for first, second in bond_pairs["sn1"]
            if resnames[first] == species
        ]
        subset2 = [
            (first, second)
            for first, second in bond_pairs["sn2"]
            if resnames[first] == species
        ]
        if subset or subset2:
            species_pairs[species] = {"sn1": subset, "sn2": subset2}

    # --- accumulators ----------------------------------------------------
    times_ns: List[float] = []
    z_series: List[float] = []
    core_water_series: List[float] = []
    pore_score_series: List[float] = []
    thickness_series: List[float] = []
    order_series: Dict[str, List[float]] = {"sn1": [], "sn2": []}
    species_order: Dict[str, Dict[str, List[float]]] = {
        species: {"sn1": [], "sn2": []} for species in species_pairs
    }
    per_residue_z: Optional[np.ndarray] = None
    bulk_density_samples: List[float] = []
    core_water_density_samples: List[float] = []
    peptide_z_min = float("inf")
    peptide_z_max = float("-inf")

    for frame_index, timestep in enumerate(universe.trajectory[::stride]):
        box = np.asarray(timestep.dimensions[:3], dtype=float) / 10.0  # nm
        positions = atoms.positions / 10.0                              # nm
        lz = float(box[2])

        # membrane mid-plane: circular mean of the phosphate beads
        if phosphate_mask.any():
            phos = positions[phosphate_mask, 2]
            angles = 2.0 * math.pi * phos / lz
            mid = math.atan2(float(np.sin(angles).mean()), float(np.cos(angles).mean()))
            centre_z = (mid / (2.0 * math.pi)) * lz
        else:  # pragma: no cover - fallback
            centre_z = lz / 2.0

        peptide_positions = positions[peptide_mask]
        if len(peptide_positions) == 0:
            raise AnalysisUnavailable("peptide selection is empty")
        peptide_centre = peptide_positions.mean(axis=0)

        dz = float(_pbc_delta(peptide_centre[2] - centre_z, lz))

        times_ns.append(float(timestep.time) / 1000.0)
        z_series.append(dz)
        peptide_z_min = min(peptide_z_min, dz)
        peptide_z_max = max(peptide_z_max, dz)

        if per_residue_z is None and len(peptide_positions) > 0:
            per_residue_z = np.zeros(len(peptide_positions))
        elif per_residue_z is not None:
            per_residue_z += _pbc_delta(peptide_positions[:, 2] - centre_z, lz)

        # --- water in the membrane core around the peptide --------------
        core_half = water_core_halfheight_nm
        w_positions = positions[water_mask]
        if len(w_positions):
            wz = _pbc_delta(w_positions[:, 2] - centre_z, lz)
            wx = _pbc_delta(w_positions[:, 0] - peptide_centre[0], box[0])
            wy = _pbc_delta(w_positions[:, 1] - peptide_centre[1], box[1])
            in_core = np.abs(wz) <= core_half
            in_cylinder = (wx * wx + wy * wy) <= (pore_radius_nm ** 2)
            core_count = int(np.count_nonzero(in_core & in_cylinder))
            cylinder_volume = math.pi * (pore_radius_nm ** 2) * (2.0 * core_half)
            core_water_series.append(float(core_count))
            core_water_density_samples.append(core_count / cylinder_volume)
            # bulk reference: a 1 nm slab 2.5-3.5 nm away from the mid-plane
            bulk = (np.abs(wz) >= 2.5) & (np.abs(wz) <= 3.5)
            slab_volume = box[0] * box[1] * 1.0
            bulk_density_samples.append(float(np.count_nonzero(bulk)) / slab_volume)

        # --- order parameters -------------------------------------------
        for chain, pairs in bond_pairs.items():
            if not pairs:
                continue
            first = np.array([pair[0] for pair in pairs])
            second = np.array([pair[1] for pair in pairs])
            delta = positions[second] - positions[first]
            delta[:, 2] = _pbc_delta(delta[:, 2], lz)
            lengths = np.linalg.norm(delta, axis=1)
            valid = lengths > 1e-6
            if not np.any(valid):
                continue
            cos_theta = delta[valid, 2] / lengths[valid]
            s_values = 0.5 * (3.0 * cos_theta ** 2 - 1.0)
            order_series[chain].append(float(s_values.mean()))
            for species, species_chain in species_pairs.items():
                sp_pairs = species_chain.get(chain) or []
                if not sp_pairs:
                    continue
                sp_first = np.array([pair[0] for pair in sp_pairs])
                sp_second = np.array([pair[1] for pair in sp_pairs])
                sp_delta = positions[sp_second] - positions[sp_first]
                sp_delta[:, 2] = _pbc_delta(sp_delta[:, 2], lz)
                sp_len = np.linalg.norm(sp_delta, axis=1)
                sp_valid = sp_len > 1e-6
                if np.any(sp_valid):
                    sp_cos = sp_delta[sp_valid, 2] / sp_len[sp_valid]
                    species_order[species][chain].extend((0.5 * (3.0 * sp_cos ** 2 - 1.0)).tolist())

        # --- bilayer thickness ------------------------------------------
        if phosphate_mask.any():
            pz = _pbc_delta(positions[phosphate_mask, 2] - centre_z, lz)
            upper = pz[pz > 0]
            lower = pz[pz < 0]
            if len(upper) and len(lower):
                thickness_series.append(float(upper.mean() - lower.mean()))

    # --- pore score -------------------------------------------------------
    pore_scores: List[float] = []
    for core_density, bulk_density in zip(core_water_density_samples, bulk_density_samples):
        if bulk_density <= 0:
            pore_scores.append(0.0)
        else:
            pore_scores.append(core_density / bulk_density)
    bulk_reference = sum(bulk_density_samples) / len(bulk_density_samples) if bulk_density_samples else 0.0
    core_reference = (
        sum(core_water_density_samples) / len(core_water_density_samples)
        if core_water_density_samples
        else 0.0
    )

    # --- equilibrated window ---------------------------------------------
    start = int(len(times_ns) * (1.0 - equilibrated_fraction))
    equilibrated = slice(start, len(times_ns))
    z_eq = z_series[equilibrated]
    order_eq = {chain: order_series[chain][equilibrated] for chain in order_series}
    pore_eq = pore_scores[equilibrated]

    inserted_fraction = (
        sum(1 for value in z_eq if abs(value) < 1.5) / float(len(z_eq)) if z_eq else 0.0
    )
    core_fraction = sum(1 for value in z_eq if abs(value) < 0.8) / float(len(z_eq)) if z_eq else 0.0

    metrics: Dict[str, Any] = {
        "n_frames": len(times_ns),
        "frame_stride": stride,
        "equilibrated_from_ns": times_ns[start] if times_ns else None,
        "membrane_insertion": {
            "z_distance_mean_nm": round(sum(z_eq) / len(z_eq), 4) if z_eq else None,
            "z_distance_min_nm": round(peptide_z_min, 4),
            "z_distance_max_nm": round(peptide_z_max, 4),
            "z_distance_std_nm": _stats(z_eq)["std"],
            "inserted_fraction": round(inserted_fraction, 3),
            "core_fraction": round(core_fraction, 3),
            "per_residue_z_nm": (
                [round(float(value) / max(1, len(times_ns) - start), 3) for value in per_residue_z]
                if per_residue_z is not None
                else []
            ),
            "convention": "peptide bead centroid minus phosphate mid-plane (negative = lower leaflet)",
        },
        "lipid_order": {
            "sn1": round(sum(order_eq["sn1"]) / len(order_eq["sn1"]), 4) if order_eq["sn1"] else None,
            "sn2": round(sum(order_eq["sn2"]) / len(order_eq["sn2"]), 4) if order_eq["sn2"] else None,
            "mean": (
                round(
                    (
                        (sum(order_eq["sn1"]) / len(order_eq["sn1"]) if order_eq["sn1"] else 0.0)
                        + (sum(order_eq["sn2"]) / len(order_eq["sn2"]) if order_eq["sn2"] else 0.0)
                    )
                    / float(
                        int(bool(order_eq["sn1"])) + int(bool(order_eq["sn2"])) or 1
                    ),
                    4,
                )
            ),
            "per_species": {
                species: {
                    chain: round(sum(values) / len(values), 4) if values else None
                    for chain, values in chains_values.items()
                }
                for species, chains_values in species_order.items()
            },
            "definition": "S = <P2(cos theta)> of consecutive Martini tail bonds vs bilayer normal",
        },
        "pore": {
            "pore_formed": bool(pore_eq and (sum(1 for value in pore_eq if value > 0.25) / len(pore_eq)) > 0.10),
            "pore_score_mean": round(sum(pore_eq) / len(pore_eq), 4) if pore_eq else 0.0,
            "pore_score_max": round(max(pore_eq), 4) if pore_eq else 0.0,
            "water_in_core_mean": round(
                sum(core_water_series[equilibrated]) / len(core_water_series[equilibrated]), 3
            ) if core_water_series else 0.0,
            "water_in_core_max": round(max(core_water_series), 3) if core_water_series else 0.0,
            "bulk_water_density_per_nm3": round(bulk_reference, 4),
            "core_water_density_per_nm3": round(core_reference, 4),
            "cylinder_radius_nm": pore_radius_nm,
            "core_halfheight_nm": water_core_halfheight_nm,
            "threshold": "pore_score > 0.25 in > 10% of equilibrated frames",
        },
        "membrane": {
            "thickness_nm": round(sum(thickness_series) / len(thickness_series), 4) if thickness_series else None,
            "thickness_series_nm": decimate(thickness_series, 120),
        },
        "timeseries": {
            "time_ns": decimate(times_ns),
            "z_distance_nm": decimate(z_series),
            "water_in_core": decimate(core_water_series),
            "pore_score": decimate(pore_scores),
            "lipid_order_sn1": decimate(order_series["sn1"]),
            "lipid_order_sn2": decimate(order_series["sn2"]),
        },
        "statistics": {
            "z_distance": _stats(z_series),
            "lipid_order_sn1": _stats(order_series["sn1"]),
            "lipid_order_sn2": _stats(order_series["sn2"]),
        },
    }
    return metrics


def summarise_logs(
    log_state: Optional[Any] = None,
    em_report: Optional[Dict[str, Any]] = None,
    production_ns: Optional[float] = None,
    walltime_s: Optional[float] = None,
) -> Dict[str, Any]:
    """Build the ``simulation`` section from parsed mdrun/em logs."""
    state = log_state
    simulation: Dict[str, Any] = {
        "production_ns": production_ns,
        "completed_ns": None,
        "ns_per_day": None,
        "walltime_h": round(walltime_s / 3600.0, 3) if walltime_s else None,
        "completed_fraction": None,
        "lincs_warnings": 0,
        "diverged": False,
        "divergence_reason": None,
        "gpu": None,
    }
    if state is not None:
        simulation.update(
            {
                "completed_ns": round(float(getattr(state, "simulated_ns", 0.0)), 3),
                "ns_per_day": round(float(state.ns_per_day), 3) if getattr(state, "ns_per_day", None) else None,
                "completed_fraction": (
                    round(float(state.progress), 4) if getattr(state, "progress", None) is not None else None
                ),
                "lincs_warnings": int(getattr(state, "lincs_warnings", 0)),
                "diverged": bool(getattr(state, "is_diverged", False)),
                "divergence_reason": getattr(state, "divergence", None),
                "gpu": getattr(state, "gpu", None),
                "finished": bool(getattr(state, "finished", False)),
            }
        )
    if em_report:
        simulation["minimisation"] = em_report
    return simulation


def write_summary(metrics: Dict[str, Any], path: str) -> str:
    """Write ``summary_metrics.json`` (UTF-8, newline terminated, atomic)."""
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(metrics, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, path)
    return path
