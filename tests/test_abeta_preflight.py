import importlib.util
import os
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "code" / "abeta" / "preflight.py"
spec = importlib.util.spec_from_file_location("abeta_preflight", SCRIPT)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def atom(resid, resname, atomname, number):
    return f"{resid:5d}{resname:<5}{atomname:>5}{number:5d}{0.1:8.3f}{0.2:8.3f}{0.3:8.3f}\n"


def gro(path, groups):
    lines = []
    number = 0
    for rid, res, atoms in groups:
        for name in atoms:
            number += 1
            lines.append(atom(rid, res, name, number))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("example\n" + str(number) + "\n" + "".join(lines) + "   9.0 9.0 9.0\n")


def sample():
    return [(1, "ALA", ["N", "H1", "H2", "H3"]), (2, "LEU", ["CA"]),
            (3, "CYS", ["SG", "HG", "C", "OC1", "OC2"])]


def test_unique_sequence_and_terminal_atoms(tmp_path):
    path = tmp_path / "test.gro"
    gro(path, [(80, "GLU", ["N"])] + sample())
    result = p.inspect_gro(path, "ALC")
    assert result["status"] == "unique_sequence_match"
    assert result["matches"][0]["n_terminal_atoms"] == ["N", "H1", "H2", "H3"]
    assert result["matches"][0]["cysteine_atoms"] == [["SG", "HG", "C", "OC1", "OC2"]]
    assert len(result["sha256"]) == 64


def test_duplicate_matches_are_not_treated_as_unique(tmp_path):
    path = tmp_path / "test.gro"
    gro(path, sample() + [(7, "GLY", ["CA"])] + sample())
    result = p.inspect_gro(path, "ALC")
    assert result["status"] == "ambiguous_or_missing"
    assert len(result["matches"]) == 2


def test_truncated_file_is_error_not_success(tmp_path):
    path = tmp_path / "broken.gro"
    path.write_text("title\n100\nshort\n")
    assert p.inspect_gro(path, "ALC")["status"] == "error"


def test_survey_is_read_only_and_missing_software_not_asserted_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(p.shutil, "which", lambda x: None)
    before = sorted(tmp_path.iterdir())
    result = p.survey(tmp_path / "source", tmp_path / "project", tmp_path)
    assert not result["project"]["exists"]
    assert all(item["status"] == "missing" for item in result["inputs"].values())
    assert all(item["copies"] == 0 for item in result["inputs"].values())
    assert result["executables_on_path"]["plumed"] is None
    assert "DMD license and engine" in result["not_checked"]
    assert sorted(tmp_path.iterdir()) == before


def test_windows_dispatch_is_fixed_and_redacts_report():
    root = SCRIPT.parents[2]
    worker = (root / "skills/cgmd-hub/runner/Invoke-CgmdMailbox.ps1").read_text(encoding="utf-8")
    section = worker.split("function Invoke-JobAbetaPreflight {", 1)[1].split("\nfunction Invoke-Job {", 1)[0]
    assert "param($JobArgs)" not in section
    assert "'code\\abeta\\preflight.py'" in section
    assert "detail = $report" not in section
    assert "logs_tail" not in section
    assert "'abeta_preflight' { return Invoke-JobAbetaPreflight }" in worker
    # the interpreter is chosen the same way the cgmd kind chooses it
    assert "Get-DeskPython" in section


def test_rejects_match_crossing_residue_number_reset(tmp_path):
    path = tmp_path / "test.gro"
    gro(path, [(9, 'ALA', ['CA']), (10, 'LEU', ['CA']), (1, 'CYS', ['CA'])])
    assert p.inspect_gro(path, 'ALC')['status'] == 'ambiguous_or_missing'


def test_find_copies_sees_the_batch_folders_newest_first(tmp_path):
    """The desk keeps md_<peptide> at the top level *and* inside batch folders."""
    old = tmp_path / "md_ylsllqr" / "complex.gro"
    new = tmp_path / "rerun_four_systems-20260831-151645" / "md_ylsllqr" / "complex.gro"
    other = tmp_path / "rerun_four_systems-20260831-151645" / "md_fllhttr" / "complex.gro"
    for path in (old, new, other):
        gro(path, sample())
    os.utime(old, (time.time() - 9 * 86400, time.time() - 9 * 86400))
    os.utime(new, (time.time(), time.time()))
    found = p.find_copies(tmp_path, "ylsllqr")
    assert found == [new, old], found


def test_inspect_input_reports_copies_and_uses_a_matching_one(tmp_path):
    broken = tmp_path / "md_alllhrc" / "complex.gro"
    broken.parent.mkdir(parents=True)
    broken.write_text("title\n2\nshort\n")            # newest, but unreadable
    good = tmp_path / "older-batch" / "md_alllhrc" / "complex.gro"
    gro(good, sample())
    os.utime(broken, (time.time(), time.time()))
    os.utime(good, (time.time() - 3600, time.time() - 3600))

    result = p.inspect_input(tmp_path, "alllhrc", "ALC")
    assert result["copies"] == 2
    assert result["status"] == "unique_sequence_match"
    assert Path(result["selected"]) == good
    assert [item["status"] for item in result["copy_statuses"]][0] == "error"


def test_inspect_input_missing_is_not_an_error(tmp_path):
    result = p.inspect_input(tmp_path, "fllhttr", "FLLHTTR")
    assert result["status"] == "missing"
    assert result["copies"] == 0
    assert result["selected"] is None
