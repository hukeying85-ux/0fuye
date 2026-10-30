"""Topology reconciliation (insane + martinize2 + Martini 3 force field)."""

from __future__ import annotations

import os

import pytest

from cgmd import topology

FF_TOPS = """\
; minimal Martini 3 stand-in used by the tests
[ defaults ]
1 2 no 1.0 1.0
[ atomtypes ]
Q5 0 72.0 0 A
"""

LIPIDS = """\
[moleculetype]
POPE 1
[atoms]
 1 Q5 1 POPE PO4 1 -1.0
 2 Q5 1 POPE NH3 2 1.0
 3 Q5 1 POPE GL1 3 0.0
 4 C1 1 POPE C1A 4 0.0

[moleculetype]
POPG 1
[atoms]
 1 Q5 1 POPG PO4 1 -1.0
 2 Q5 1 POPG GL0 2 -1.0
 3 C1 1 POPG C1A 3 0.0
"""

SOLVENT = """\
[moleculetype]
W 1
[atoms]
 1 P4 1 W W 1 0.0
"""

IONS = """\
[moleculetype]
NA 1
[atoms]
 1 Q5 1 NA NA 1 1.0

[moleculetype]
CL 1
[atoms]
 1 Q5 1 CL CL 1 -1.0
"""

PEPTIDE_TOP = """\
#include "Protein_0.itp"

[ system ]
peptide

[ molecules ]
Protein_0 1
"""

PEPTIDE_ITP = """\
[moleculetype]
Protein_0 1
[atoms]
 1 Q5  1 ALA BB  1 0.0
 2 C1  1 ALA SC1 2 0.0
 3 Q5n 1 GLU BB  3 -1.0
 4 Q5n 1 GLU SC1 4 -1.0
 5 Q5p 1 LYS BB  5 1.0
 6 Q5p 1 LYS SC1 6 1.0
"""

INSANE_TOP = """\
#include "martini.itp"

[ system ]
Protein in INSANE! Membrane

[ molecules ]
Protein 1
POPE 4
POPG 2
W 10
NA+ 2
CL- 1
"""


@pytest.fixture()
def forcefield(tmp_path):
    ff = tmp_path / "ff"
    ff.mkdir()
    (ff / "martini_v3.0.0.itp").write_text(FF_TOPS, encoding="utf-8")
    (ff / "lipid.itp").write_text(LIPIDS, encoding="utf-8")
    (ff / "solvent.itp").write_text(SOLVENT, encoding="utf-8")
    (ff / "ions.itp").write_text(IONS, encoding="utf-8")
    return str(ff)


def test_moleculetype_parser():
    types = topology.parse_moleculetypes("lipid.itp", text=LIPIDS)
    assert {entry.name: entry.natoms for entry in types} == {"POPE": 4, "POPG": 3}


def test_index_finds_base_file(tmp_path, forcefield):
    index = topology.MoleculeTypeIndex([forcefield])
    assert "POPE" in index and "W" in index
    assert index.base_files and index.base_files[0].endswith("martini_v3.0.0.itp")
    report = index.describe()
    assert report["moleculetypes"] == 5


def test_build_topology_rewrites_names_and_counts(tmp_path, forcefield):
    peptide_top = tmp_path / "peptide.top"
    peptide_top.write_text(PEPTIDE_TOP, encoding="utf-8")
    (tmp_path / "Protein_0.itp").write_text(PEPTIDE_ITP, encoding="utf-8")
    insane_top = tmp_path / "insane.top"
    insane_top.write_text(INSANE_TOP, encoding="utf-8")

    out = tmp_path / "topol.top"
    report = topology.build_topology(
        str(insane_top), str(peptide_top), [forcefield], str(out), system_name="test system"
    )
    text = out.read_text(encoding="utf-8")
    assert "Protein_0" in text and "Protein " not in text.split("[ molecules ]")[1]
    assert "NA " in text and "NA+" not in text
    assert "CL " in text
    # base force field first, molecule definitions after
    includes = [line for line in text.splitlines() if line.startswith("#include")]
    assert "martini_v3.0.0.itp" in includes[0]
    assert any("Protein_0.itp" in line for line in includes)

    # 6 atoms peptide + 4*4 POPE + 2*3 POPG + 10 W + 2 NA + 1 CL
    assert report["expected_atoms"] == 6 + 16 + 6 + 10 + 2 + 1
    assert report["peptide_atoms_per_copy"] == 6


def test_build_topology_reports_missing_molecule(tmp_path, forcefield):
    peptide_top = tmp_path / "peptide.top"
    peptide_top.write_text(PEPTIDE_TOP, encoding="utf-8")
    (tmp_path / "Protein_0.itp").write_text(PEPTIDE_ITP, encoding="utf-8")
    insane_top = tmp_path / "insane.top"
    insane_top.write_text(
        "[ molecules ]\nProtein 1\nPOPE 2\nPOPX 4\n", encoding="utf-8"
    )
    with pytest.raises(RuntimeError) as error:
        topology.build_topology(
            str(insane_top), str(peptide_top), [forcefield], str(tmp_path / "topol.top")
        )
    assert "POPX" in str(error.value)


def test_validate_topology_against_gro(tmp_path):
    gro = tmp_path / "system.gro"
    gro.write_text("test\n3\n    1PEP BB 1 1.0 1.0 1.0\n", encoding="utf-8")
    assert topology.count_gro_atoms(str(gro)) == 3
    report = topology.validate_topology({"expected_atoms": 3}, str(gro))
    assert report["consistent"] is True
    report = topology.validate_topology({"expected_atoms": 4}, str(gro))
    assert report["consistent"] is False
    assert report["difference"] == -1


def test_ion_aliases_cover_legacy_insane_output():
    assert topology.ION_ALIASES["NA+"] == "NA"
    assert topology.ION_ALIASES["CL-"] == "CL"
    assert topology.ION_ALIASES["SOL"] == "W"
