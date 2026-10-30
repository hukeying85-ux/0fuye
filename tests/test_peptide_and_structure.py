"""Physico-chemical descriptors and the built-in peptide structure builder."""

from __future__ import annotations

import os

import pytest

from cgmd import peptide, seq2pdb

MAGAININ2 = "GIGKFLHSAKKFGKAFVGEIMNS"


def test_charge_and_pi():
    # magainin-2: 4 Lys, 1 Glu, 1 His -> net charge ~ +3 at pH 7.4
    charge = peptide.net_charge(MAGAININ2, 7.4)
    assert 2.5 < charge < 3.5
    assert peptide.net_charge(MAGAININ2, 1.0) > peptide.net_charge(MAGAININ2, 13.0)
    pi = peptide.isoelectric_point(MAGAININ2)
    assert 9.5 < pi < 11.5
    assert abs(peptide.net_charge(MAGAININ2, pi)) < 0.01


def test_gravy_and_moment():
    assert peptide.gravy(MAGAININ2) < 0.5
    assert peptide.gravy("LLLLLLLLLL") > 3.5
    moment = peptide.hydrophobic_moment(MAGAININ2)
    assert 0.3 < moment["mu_h"] < 1.2
    assert moment["end"] - moment["start"] + 1 == moment["window"]
    # an ideal amphipathic helix has a much larger moment than a random one
    assert peptide.hydrophobic_moment("LKKLLKKLLKKL")["mu_h"] > 0.4


def test_describe_block():
    info = peptide.describe(MAGAININ2)
    assert info["length"] == 23
    assert info["cationic_residues"] == 4
    assert info["anionic_residues"] == 1
    assert info["molar_mass_da"] == pytest.approx(2466.9, abs=5)
    assert 0 <= info["amphipathic_face_ratio"] <= 1
    assert info["three_letter"][0] == "GLY"


def test_fasta_wrapping():
    text = peptide.to_fasta(MAGAININ2, name="magainin2", width=10)
    lines = text.strip().splitlines()
    assert lines[0] == ">magainin2"
    assert "".join(lines[1:]) == MAGAININ2


@pytest.mark.parametrize("ss", ["C", "H"])
def test_build_pdb_geometry(tmp_path, ss):
    path = str(tmp_path / "pep.pdb")
    info = seq2pdb.build_pdb(MAGAININ2, path, ss=ss)
    assert os.path.exists(path)
    assert info["residues"] == 23
    assert info["heavy_atoms"] == 173
    assert info["clashes"] == []
    with open(path, encoding="ascii") as handle:
        lines = handle.readlines()
    atoms = [line for line in lines if line.startswith("ATOM")]
    assert len(atoms) == 173
    # backbone N-CA bond length check on the first residue
    n = [float(atoms[0][30:38]), float(atoms[0][38:46]), float(atoms[0][46:54])]
    ca = [float(atoms[1][30:38]), float(atoms[1][38:46]), float(atoms[1][46:54])]
    distance = sum((a - b) ** 2 for a, b in zip(n, ca)) ** 0.5
    assert 1.40 < distance < 1.52


def test_all_residues_build_without_clashes(tmp_path):
    path = str(tmp_path / "all.pdb")
    info = seq2pdb.build_pdb("ACDEFGHIKLMNPQRSTVWY", path)
    assert info["residues"] == 20
    assert info["clashes"] == []


def test_missing_pdb_raises(tmp_path):
    from core.task_contract import TaskError

    with pytest.raises(TaskError):
        seq2pdb.build_structure("KKLL", str(tmp_path), pdb_path=str(tmp_path / "nope.pdb"))
