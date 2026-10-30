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
Q5n 72.0 -1.0 A 0.47 4.4
Q5p 72.0 1.0 A 0.47 4.4
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
    assert desk_ops.bead_type(1.0) == "Q5p"
    assert desk_ops.bead_type(-1.0) == "Q5n"
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


def test_search_reads_the_peptide_out_of_the_second_gro(tmp_path, monkeypatch):
    """box.gro (solvent) must not hide the peptide in complex.gro."""
    run = tmp_path / "md_ylsllqr"
    run.mkdir()
    solver = ["box.gro", "3", "    1SOL  HW1    1   0.000   0.000   0.000",
              "    1SOL  HW2    1   0.000   0.000   0.000",
              "    1SOL  OW     1   0.000   0.000   0.000", "   3.000   3.000   3.000"]
    peptide = ["complex.gro", "3"]
    for index, name in enumerate(("TYR", "LEU", "SER"), start=1):
        peptide.append("{:5d}{:<5s}{:>5s}{:5d}{:8.3f}{:8.3f}{:8.3f}".format(
            index, name, "BB", index, 0.5 * index, 0.5, 0.5))
    peptide.append("   3.000   3.000   3.000")
    (run / "box.gro").write_text("\n".join(solver) + "\n", encoding="utf-8")
    (run / "complex.gro").write_text("\n".join(peptide) + "\n", encoding="utf-8")

    status, summary, detail = desk_ops.mode_search(
        {"roots": [str(tmp_path)], "days": 3650, "limit": 4, "depth": 4}, "")
    assert status == "ok"
    candidate = detail["candidates"][0]
    assert candidate["sequence"] == "YLS"
    assert candidate["sequence_source"] == "complex.gro"


def test_which_finds_an_executable_without_shutil(monkeypatch):
    """A Python 3.2 on PATH has no shutil.which; the local helper must cope."""
    monkeypatch.setattr(desk_ops.shutil, "which", None, raising=False)
    found = desk_ops.which("python3" if os.name != "nt" else "python.exe")
    assert found is None or os.path.isfile(found)


def test_peptide_itp_declares_no_molecules(tmp_path, ff_dir):
    """The peptide must be declared once (topol.top), never in the include."""
    system = desk_ops.build_system("KLVFFAE", str(tmp_path / "run"),
                                   os.path.join(ff_dir, "martini_v3.0.0.itp"), box_nm=6.0)
    itp = open(system["itp"], encoding="ascii").read()
    assert "[ molecules ]" not in itp
    assert itp.count("[ moleculetype ]") == 1
    top = open(system["top"], encoding="ascii").read()
    molecules = [line.split() for line in top.split("[ molecules ]")[1].splitlines()
                 if line.strip() and not line.strip().startswith(";")]
    counts = {name: int(count) for name, count in molecules}
    assert counts["Peptide"] == 1
    # one BB bead per residue, plus the solvent and ions, must add up to the .gro
    total = counts["Peptide"] * system["residues"] + counts["W"] + counts["NA"] + counts["CL"]
    assert total == system["beads_total"]


@pytest.mark.skipif(os.name == "nt", reason="the stub driver is a shell script")
def test_run_interleaves_grompp_and_mdrun(tmp_path, ff_dir):
    """eq.gro only exists after mdrun-em; the stages must therefore interleave.

    The first live run fired all three grompp calls up front and stopped at
    'File em.gro does not exist or is not accessible'.
    """
    workdir = tmp_path / "run"
    workdir.mkdir()
    system = desk_ops.build_system("KLVFFAE", str(workdir),
                                   os.path.join(ff_dir, "martini_v3.0.0.itp"), box_nm=6.0)
    assert system["beads_total"] > 0

    calls = tmp_path / "calls.txt"
    stub = tmp_path / "gmx"
    stub.write_text(
        '#!/bin/sh\n'
        'echo "$@" >> "' + str(calls) + '"\n'
        'case "$1" in\n'
        '  grompp) out=""; prev=""\n'
        '    for a in "$@"; do if [ "$prev" = "-o" ]; then out="$a"; fi; prev="$a"; done\n'
        '    : > "$out" ;;\n'
        '  mdrun) deffnm=""; prev=""\n'
        '    for a in "$@"; do if [ "$prev" = "-deffnm" ]; then deffnm="$a"; fi; prev="$a"; done\n'
        '    printf "Performance: 1234.5\\nFinished mdrun\\n" > "$deffnm.log"\n'
        '    : > "$deffnm.gro" ;;\n'
        'esac\n'
        'exit 0\n', encoding="utf-8")
    stub.chmod(0o755)

    status, summary, detail = desk_ops.mode_run(
        {"workdir": str(workdir), "gmx": str(stub), "ns": 0.02, "gpu": False,
         "prod_timeout": 60, "eq_timeout": 60, "em_timeout": 60}, "")
    order = [entry["stage"] for entry in detail["stages"]]
    assert order == ["grompp-em", "mdrun-em", "grompp-eq", "mdrun-eq",
                     "grompp-prod", "mdrun-prod-gpu"], order
    assert status == "ok", (summary, detail["stages"])
    report = detail["report"]
    assert report["finished"] is True
    assert report["performance_ns_per_day"] == 1234.5
    assert report["steps_requested"] == 1000
