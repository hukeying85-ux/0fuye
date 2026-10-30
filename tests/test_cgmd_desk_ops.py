"""The `cgmd` mailbox capability (``code/cgmd/desk_ops.py``).

The interesting parts are the ones that run without GROMACS: sequence ->
backbone beads, the geometry of the water grid, and the sequence recovery that
lets the desk describe a run it found on disk.  ``run`` itself is exercised on
the workstation, not here.
"""

from __future__ import annotations

import json
import os

import pytest

import desk_ops

FAKE_ITP = """[ defaults ]
1 2 no 1.0 1.0

[ atomtypes ]
Q5 72.0 0.0 A 0.47 4.4
Qa 72.0 -1.0 A 0.47 4.4
Qd 72.0 1.0 A 0.47 4.4
W  72.0 0.0 A 0.47 2.0
NA 36.0 1.0 A 0.47 1.0
CL 36.0 -1.0 A 0.47 1.0

[ moleculetype ]
W 1
[ atoms ]
1 W 1 W W 1 0.0 72.0

[ moleculetype ]
NA 1
[ atoms ]
1 NA 1 NA NA 1 1.0 36.0

[ moleculetype ]
CL 1
[ atoms ]
1 CL 1 CL CL 1 -1.0 36.0
"""


@pytest.fixture()
def ff_dir(tmp_path):
    folder = os.path.join(str(tmp_path), "ff")
    os.makedirs(folder)
    with open(os.path.join(folder, "martini_v3.0.0.itp"), "w", encoding="utf-8") as handle:
        handle.write(FAKE_ITP)
    return folder


def test_charges_carry_sidechain_and_termini():
    charges = desk_ops.peptide_charges("KLVFFAE")
    assert charges[0] == 2.0      # Lys sidechain + N-terminus
    assert charges[-1] == -2.0    # Glu sidechain + C-terminus
    assert charges[1:6] == [0.0] * 5
    assert sum(charges) == 0.0


def test_bead_type_follows_charge():
    assert desk_ops.bead_type(1.0) == "Qd"
    assert desk_ops.bead_type(-1.0) == "Qa"
    assert desk_ops.bead_type(0.0) == "Q5"


def test_build_writes_a_self_consistent_system(tmp_path, ff_dir):
    workdir = os.path.join(str(tmp_path), "run")
    system = desk_ops.build_system("KLVFFAE", workdir, os.path.join(ff_dir, "martini_v3.0.0.itp"),
                                   box_nm=6.0)
    assert system["residues"] == 7
    assert system["beads_total"] == system["water_beads"] + system["na"] + system["cl"] + 7
    assert system["na"] == system["cl"], "a neutral peptide needs a symmetric salt pair count"
    beads, box = desk_ops.read_gro(system["gro"])
    assert len(beads) == system["beads_total"]
    assert box == 6.0
    peptide = [item for item in beads if item[1] == "BB"]
    assert len(peptide) == 7
    assert all(0.0 <= point <= 6.0 for item in peptide for point in item[2]), "inside the box"
    with open(system["top"], encoding="utf-8") as handle:
        topology = handle.read()
    assert "Peptide 1" in topology
    assert "W {}".format(system["water_beads"]) in topology


def test_gro_round_trip_recovers_the_sequence(tmp_path, ff_dir):
    system = desk_ops.build_system("KLVFFAE", os.path.join(str(tmp_path), "seq"),
                                   os.path.join(ff_dir, "martini_v3.0.0.itp"), box_nm=5.0)
    assert desk_ops.sequence_from_gro(system["gro"]) == "KLVFFAE"


def test_radius_of_gyration_and_clusters():
    line = [(0.0, 0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0, 0.0)]
    tight = [(0.0, 0.0, 0.0), (0.2, 0.0, 0.0), (0.0, 0.2, 0.0)]
    apart = [(0.0, 0.0, 0.0), (3.0, 0.0, 0.0)]
    assert desk_ops.radius_of_gyration(tight) < 0.2
    assert desk_ops.contact_clusters(tight)["largest"] == 3
    assert desk_ops.contact_clusters(apart)["largest"] == 1
    assert line  # keep the fixture list referenced for readability


def test_ff_bundle_picks_the_files_that_define_the_molecules(ff_dir):
    includes, molecules = desk_ops.ff_bundle(os.path.join(ff_dir, "martini_v3.0.0.itp"))
    assert "W" in molecules and "NA" in molecules and "CL" in molecules
    assert includes == [os.path.join(ff_dir, "martini_v3.0.0.itp")]


def test_main_reports_unsupported_mode(tmp_path):
    out = os.path.join(str(tmp_path), "result.json")
    code = desk_ops.main(["--mode", "nonsense", "--out", out])
    assert code == 2
    with open(out, encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["status"] == "unsupported"
    assert "unknown mode" in payload["summary"]
