"""Trajectory analysis on a synthetic Martini system (needs MDAnalysis)."""

from __future__ import annotations

import json
import os

import pytest

from cgmd import analyze


@pytest.fixture(scope="module")
def synthetic_system(tmp_path_factory):
    pytest.importorskip("numpy")
    pytest.importorskip("MDAnalysis")
    import MDAnalysis as mda
    import numpy as np

    directory = tmp_path_factory.mktemp("traj")

    # --- build a tiny Martini-like gro: 48 peptide beads, lipids, water
    box_nm = [12.0, 12.0, 8.0]
    records = []          # (resid, resname, atomname, x, y, z)
    resid = 0
    for index in range(48):
        resid = index + 1
        records.append((resid, "PEP", "BB", 5.0 + 0.1 * index, 6.0, 4.0))

    lipid_atoms = ["PO4", "GL1", "GL2", "C1A", "D2A", "C1B", "C2B"]
    tail_offset = {"PO4": 0.0, "GL1": 0.25, "GL2": 0.5, "C1A": 0.8, "D2A": 1.3, "C1B": 0.8, "C2B": 1.3}
    for leaflet_z, sign in ((2.4, 1.0), (5.6, -1.0)):
        for copy in range(6):
            resid += 1
            for name in lipid_atoms:
                records.append((resid, "POPE", name, 3.0 + 0.4 * copy, 5.0, leaflet_z + sign * tail_offset[name]))

    for index in range(200):
        resid += 1
        records.append((resid, "W", "W", 1.0 + 0.5 * (index % 10), 2.0, 6.5 + 0.05 * (index % 20)))

    with open(directory / "system.gro", "w", encoding="utf-8") as handle:
        handle.write("synthetic\n")
        handle.write("{}\n".format(len(records)))
        for serial, (resid_, resname, name, x, y, z) in enumerate(records, start=1):
            handle.write(
                "{:>5}{:<5}{:>5}{:>5}{:>8.3f}{:>8.3f}{:>8.3f}\n".format(
                    resid_ % 100000, resname, name, serial % 100000, x, y, z
                )
            )
        handle.write("  12.00000  12.00000   8.00000\n")

    universe = mda.Universe(str(directory / "system.gro"))
    n_atoms = len(universe.atoms)
    base = universe.atoms.positions.copy()
    peptide_mask = np.arange(n_atoms) < 48
    water_mask = np.array([str(name) == "W" for name in universe.atoms.resnames])

    with mda.Writer(str(directory / "prod.xtc"), n_atoms=n_atoms) as writer:
        for frame in range(12):
            universe.trajectory[0]
            positions = base.copy()
            # peptide starts outside the bilayer and inserts towards the centre
            positions[peptide_mask, 2] += max(0.0, 25.0 - 4.0 * frame)
            if frame >= 8:  # start filling the core with water
                count = (frame - 7) * 12
                chosen = np.where(water_mask)[0][:count]
                positions[chosen, 0] = 60.0
                positions[chosen, 1] = 60.0
                positions[chosen, 2] = 40.0
            universe.atoms.positions = positions
            universe.trajectory.ts.time = frame * 1000.0
            writer.write(universe.atoms)

    return {
        "gro": str(directory / "system.gro"),
        "xtc": str(directory / "prod.xtc"),
        "peptide_atoms": 48,
    }


def test_analysis_produces_bounded_metrics(synthetic_system):
    metrics = analyze.analyse_trajectory(
        synthetic_system["gro"],
        synthetic_system["xtc"],
        peptide_atoms=synthetic_system["peptide_atoms"],
        lipid_resnames=["POPE", "POPG"],
        max_frames=12,
    )
    assert metrics["n_frames"] >= 6
    insertion = metrics["membrane_insertion"]
    assert insertion["z_distance_mean_nm"] is not None
    assert insertion["z_distance_max_nm"] >= insertion["z_distance_min_nm"]
    assert 0.0 <= insertion["inserted_fraction"] <= 1.0
    assert len(insertion["per_residue_z_nm"]) == synthetic_system["peptide_atoms"]

    order = metrics["lipid_order"]
    assert -0.5 <= order["sn1"] <= 1.0
    assert order["per_species"]["POPE"]["sn1"] is not None

    pore = metrics["pore"]
    assert pore["water_in_core_max"] >= pore["water_in_core_mean"] >= 0.0
    assert isinstance(pore["pore_formed"], bool)
    assert metrics["membrane"]["thickness_nm"] is not None

    # the JSON that goes back to git must stay small
    payload = json.dumps(metrics)
    assert len(payload.encode("utf-8")) < 1_000_000
    for key, value in metrics["timeseries"].items():
        assert len(value) <= 121, key


def test_analysis_rejects_missing_trajectory():
    with pytest.raises(analyze.AnalysisUnavailable):
        analyze.analyse_trajectory("nope.gro", "nope.xtc", peptide_atoms=1, lipid_resnames=["POPE"])


def test_summarise_logs():
    from core import gmx_log

    state = gmx_log.parse_log_text(
        "Started mdrun on rank 0\n   nsteps = 1000000\n   dt = 0.02\n"
        "Step           Time\n 500000    10000.00000\nPerformance:       900.000       0.096\n"
    )
    summary = analyze.summarise_logs(state, production_ns=20.0, walltime_s=3600)
    assert summary["ns_per_day"] == 900.0
    assert summary["completed_ns"] == 10.0
    assert summary["completed_fraction"] == 0.5
    assert summary["walltime_h"] == 1.0
    assert summary["diverged"] is False
