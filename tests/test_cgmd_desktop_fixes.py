"""Regression tests for the four modelling bugs found on DESKTOP-IEUDGS5.

(a) the Martini 3 parameters are *not* on PyPI: they come from a shallow clone
    of ``marrink-lab/martini-forcefields`` at ``regular/v3.0.0/gmx_files``;
(b) martinize2 must not be pointed at an external ``vermouth_files`` checkout,
    ``-ss`` has to be one code per residue, and it has to run with
    ``cwd=workdir`` so ``Protein_0.itp`` lands next to ``topol.top``;
(c) every ``martini_v3.0.0*.itp`` the topology needs is copied flat next to
    ``topol.top`` and included by basename;
(d) Martini 3 is reaction-field, so mdrun gets ``-nb gpu -bonded gpu -gpu_id N``
    and never ``-pme``.
"""

from __future__ import annotations

import os
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest

from cgmd import topology
from cgmd.config import (
    Config,
    fetch_martini_forcefields,
    find_gmx_files,
    resolve_martini3_dir,
)
from cgmd.engine import Gromacs
from cgmd.pipeline import Pipeline

MAGAININ2 = "GIGKFLHSAKKFGKAFVGEIMNS"
FF_TOPS_SHIM = "[ defaults ]\n1 2 no 1.0 1.0\n[ atomtypes ]\nQ5 0 72.0 0 A\n"

FAKE_MARTINIZE = textwrap.dedent(
    """\
    #!/bin/bash
    # Records how it was called and reproduces martinize2's real side effects:
    # <name>.itp is written in the CURRENT DIRECTORY, not next to -o.
    set -u
    echo "$@" > "$(dirname "$0")/martinize2.argv"
    echo "$PWD" > "$(dirname "$0")/martinize2.cwd"
    if [ "${1:-}" = "-list-ff" ]; then
      echo "martini3001"
      exit 0
    fi
    out=""; pdb=""; name="Protein"
    args=("$@")
    i=0
    while [ $i -lt ${#args[@]} ]; do
      case "${args[$i]}" in
        -o) out="${args[$((i+1))]}" ;;
        -x) pdb="${args[$((i+1))]}" ;;
        -name) name="${args[$((i+1))]}" ;;
      esac
      i=$((i+1))
    done
    printf 'ATOM      1  BB  ALA A   1      0.000   0.000   0.000  1.00  0.00\\n' > "$pdb"
    printf '[ moleculetype ]\\n%s_0 1\\n[ atoms ]\\n 1 Q5 1 ALA BB 1 0.0\\n[ system ]\\npeptide\\n[ molecules ]\\n%s_0 1\\n' \\
        "$name" "$name" > "${name}_0.itp"
    printf '#include "%s_0.itp"\\n[ system ]\\npeptide\\n[ molecules ]\\n%s_0 1\\n' "$name" "$name" > "$out"
    exit 0
    """
)


@pytest.fixture()
def fake_martinize(tmp_path):
    path = tmp_path / "martinize2"
    path.write_text(FAKE_MARTINIZE, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


class _StubEngine:
    """Advances 10 ns per mdrun call and leaves a checkpoint behind."""

    def __init__(self, cfg: Config, ns_per_call: float = 10.0) -> None:
        self.cfg = cfg
        self.ns_per_call = ns_per_call
        self.calls = []

    def mdrun(self, deffnm, **kwargs):
        self.calls.append((deffnm, dict(kwargs)))
        ns = self.ns_per_call * len(self.calls)
        steps = int(round(ns / self.cfg.dt_ps * 1000.0))
        log = (
            "Started mdrun on rank 0\n"
            "   nsteps = {total}\n"
            "   dt = {dt}\n"
            "Step           Time\n"
            "   {steps}   {time:.5f}\n"
            "Performance:      900.000       0.096\n"
            "Finished mdrun on rank 0\n"
        ).format(
            total=int(round(self.cfg.production_ns / self.cfg.dt_ps * 1000.0)),
            dt=self.cfg.dt_ps,
            steps=steps,
            time=ns * 1000.0,
        )
        with open(self.cfg.path(deffnm + ".log"), "w", encoding="utf-8") as handle:
            handle.write(log)
        Path(self.cfg.path(deffnm + ".cpt")).write_text("checkpoint", encoding="utf-8")
        return 0


# ---------------------------------------------------------------------------
# (a) force field: shallow clone of the upstream repository
# ---------------------------------------------------------------------------
def _make_upstream(path: Path) -> Path:
    gmx_files = path / "regular" / "v3.0.0" / "gmx_files"
    gmx_files.mkdir(parents=True)
    (gmx_files / "martini_v3.0.0.itp").write_text(
        "[ defaults ]\n1 2 no 1.0 1.0\n[ atomtypes ]\nQ5 0 72.0 0 A\n", encoding="utf-8"
    )
    (gmx_files / "martini_v3.0.0_ions_v1.itp").write_text(
        "[ moleculetype ]\nNA 1\n[ atoms ]\n1 Q5 1 NA NA 1 1.0\n", encoding="utf-8"
    )
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
           "PATH": os.environ.get("PATH", "")}
    subprocess.run(["git", "init", "-q", str(path)], check=True, env=env)
    subprocess.run(["git", "-C", str(path), "add", "."], check=True, env=env)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "ff"], check=True, env=env)
    return gmx_files


def test_find_gmx_files_prefers_the_v3_layout(tmp_path):
    gmx_files = _make_upstream(tmp_path / "ff")
    assert Path(find_gmx_files(str(tmp_path / "ff"))).resolve() == gmx_files.resolve()


def test_find_gmx_files_handles_the_upstream_package_layout(tmp_path):
    """marrink-lab keeps the files under the *package* dir, not the repo root."""
    package = tmp_path / "martini-forcefields" / "martini_forcefields"
    gmx_files = package / "regular" / "v3.0.0" / "gmx_files"
    gmx_files.mkdir(parents=True)
    (gmx_files / "martini_v3.0.0.itp").write_text(FF_TOPS_SHIM, encoding="utf-8")
    assert Path(find_gmx_files(str(tmp_path / "martini-forcefields"))).resolve() == gmx_files.resolve()


def test_forcefield_is_shallow_cloned_from_git_not_pypi(tmp_path):
    upstream = tmp_path / "upstream"
    _make_upstream(upstream)
    dest = tmp_path / "clone"

    found = fetch_martini_forcefields(dest=str(dest), url=upstream.as_uri())

    assert Path(found).resolve() == (dest / "regular" / "v3.0.0" / "gmx_files").resolve()
    assert (Path(found) / "martini_v3.0.0.itp").is_file()
    # a second call reuses the checkout instead of cloning again
    assert fetch_martini_forcefields(dest=str(dest), url=upstream.as_uri()) == found
    resolved = resolve_martini3_dir(str(dest), auto_clone=False)
    assert Path(resolved).name == "gmx_files"


def test_missing_forcefield_error_names_git_not_pip(monkeypatch, tmp_path):
    monkeypatch.setenv("CGMD_MARTINI3_DIR", "")
    monkeypatch.setattr("cgmd.config.DEFAULT_FF_CANDIDATES", ())
    monkeypatch.setattr("cgmd.config.load_local_config", lambda: {})
    with pytest.raises(FileNotFoundError) as error:
        resolve_martini3_dir(str(tmp_path / "nothing-here"), auto_clone=False,
                             clone_root=str(tmp_path / "clone"))
    message = str(error.value)
    assert "martini-forcefields.git" in message
    assert "regular/v3.0.0/gmx_files" in message
    assert "pip install martini-forcefields" not in message


# ---------------------------------------------------------------------------
# (b) martinize2: bundled force field, residue-length -ss, cwd=workdir
# ---------------------------------------------------------------------------
def test_martinize2_uses_bundled_ff_and_runs_in_the_workdir(tmp_path, fake_martinize):
    workdir = tmp_path / "work"
    cfg = Config(
        workdir=str(workdir),
        sequence=MAGAININ2,
        peptide_name="magainin2",
        secondary_structure="H",
        martinize_binary=fake_martinize,
        gmx_binary="/bin/true",
        dry_run=False,
    )
    pipeline = Pipeline(cfg, output_dir=str(tmp_path / "out"), logger=lambda message: None)
    pipeline.engine = Gromacs(cfg, logger=lambda message: None)

    structure = tmp_path / "peptide.pdb"
    structure.write_text("ATOM      1  N   GLY A   1      0.000   0.000   0.000\n", encoding="utf-8")
    info = pipeline.stage_martinize({"path": str(structure)})

    command = pipeline.engine.commands[-1]
    assert "-ff-dir" not in command and "-map-dir" not in command
    assert command[command.index("-ff") + 1] == "martini3001"
    assert command[command.index("-ss") + 1] == "H" * len(MAGAININ2)
    assert info["secondary_structure"] == "H" * len(MAGAININ2)
    assert info["ss_expanded_to_residues"] == len(MAGAININ2)

    # Protein_0.itp has to be in the run directory, not in the caller's cwd
    assert (workdir / "Protein_0.itp").is_file()
    argv = (tmp_path / "martinize2.argv").read_text(encoding="utf-8")
    assert "-ff-dir" not in argv and "-map-dir" not in argv
    assert Path((tmp_path / "martinize2.cwd").read_text(encoding="utf-8").strip()).resolve() == workdir.resolve()
    assert info["beads"] >= 1


def test_secondary_structure_expansion_rules(tmp_path):
    def build(ss: str, sequence: str = MAGAININ2) -> str:
        cfg = Config(workdir=str(tmp_path / ss.replace(" ", "")), sequence=sequence,
                     secondary_structure=ss, dry_run=True)
        return Pipeline(cfg, output_dir=str(tmp_path / "out"), logger=lambda m: None).secondary_structure_string()

    assert build("H") == "H" * 23
    assert build("C") == "C" * 23
    assert build("H" * 23) == "H" * 23
    assert build("HH") == "H" * 23   # a stray short string still expands to the residue count


# ---------------------------------------------------------------------------
# (c) flat includes next to topol.top
# ---------------------------------------------------------------------------
FF_TOPS = "[ defaults ]\n1 2 no 1.0 1.0\n[ atomtypes ]\nQ5 0 72.0 0 A\n"
LIPIDS = (
    "[moleculetype]\nPOPE 1\n[atoms]\n1 Q5 1 POPE PO4 1 -1.0\n2 Q5 1 POPE NH3 2 1.0\n"
    "\n[moleculetype]\nPOPG 1\n[atoms]\n1 Q5 1 POPG PO4 1 -1.0\n"
)
SOLVENT = "[moleculetype]\nW 1\n[atoms]\n1 P4 1 W W 1 0.0\n"
INESANE_TOP = '#include "martini.itp"\n[ system ]\ntest\n\n[ molecules ]\nProtein 1\nPOPE 4\nPOPG 1\nW 10\n'
PEPTIDE_TOP = '#include "Protein_0.itp"\n[ system ]\npeptide\n\n[ molecules ]\nProtein_0 1\n'
PEPTIDE_ITP = "[moleculetype]\nProtein_0 1\n[atoms]\n1 Q5 1 ALA BB 1 0.0\n2 C1 1 ALA SC1 2 0.0\n"


def test_topology_flattens_force_field_includes(tmp_path):
    ff = tmp_path / "forcefields" / "martini-forcefields" / "regular" / "v3.0.0" / "gmx_files"
    ff.mkdir(parents=True)
    (ff / "martini_v3.0.0.itp").write_text(FF_TOPS, encoding="utf-8")
    (ff / "martini_v3.0.0_lipids.itp").write_text(LIPIDS, encoding="utf-8")
    (ff / "martini_v3.0.0_solvent.itp").write_text(SOLVENT, encoding="utf-8")

    work = tmp_path / "work"
    work.mkdir()
    (work / "insane.top").write_text(INESANE_TOP, encoding="utf-8")
    (work / "peptide.top").write_text(PEPTIDE_TOP, encoding="utf-8")
    (work / "Protein_0.itp").write_text(PEPTIDE_ITP, encoding="utf-8")

    report = topology.build_topology(
        str(work / "insane.top"), str(work / "peptide.top"), [str(ff)], str(work / "topol.top")
    )
    text = (work / "topol.top").read_text(encoding="utf-8")
    includes = [line for line in text.splitlines() if line.startswith("#include")]

    assert includes[0] == '#include "martini_v3.0.0.itp"'
    assert '#include "martini_v3.0.0_lipids.itp"' in includes
    assert '#include "Protein_0.itp"' in includes
    # every include is a bare basename and the file really is next to topol.top
    for line in includes:
        name = line.split('"')[1]
        assert os.sep not in name and "/" not in name
        assert (work / name).is_file(), name
    assert report["include_style"] == "flat"
    assert "martini_v3.0.0_lipids.itp" in report["flat_includes"]
    assert report["expected_atoms"] == 2 + 4 * 2 + 1 + 10


def test_topology_can_still_emit_force_field_paths(tmp_path):
    ff = tmp_path / "ff"
    ff.mkdir()
    (ff / "martini_v3.0.0.itp").write_text(FF_TOPS, encoding="utf-8")
    (ff / "lipid.itp").write_text(LIPIDS, encoding="utf-8")
    (ff / "solvent.itp").write_text(SOLVENT, encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    (work / "insane.top").write_text(INESANE_TOP, encoding="utf-8")
    (work / "peptide.top").write_text(PEPTIDE_TOP, encoding="utf-8")
    (work / "Protein_0.itp").write_text(PEPTIDE_ITP, encoding="utf-8")

    report = topology.build_topology(
        str(work / "insane.top"), str(work / "peptide.top"), [str(ff)], str(work / "topol.top"),
        flat_includes=False,
    )
    text = (work / "topol.top").read_text(encoding="utf-8")
    assert "ff/martini_v3.0.0.itp" in text.replace(os.sep, "/")
    assert report["include_style"] == "forcefield-paths"


# ---------------------------------------------------------------------------
# (d) mdrun flags for reaction-field Martini 3
# ---------------------------------------------------------------------------
def test_mdrun_gpu_flags_have_no_pme(tmp_path):
    cfg = Config(workdir=str(tmp_path), gpu_id=0, dry_run=True)
    engine = Gromacs(cfg, logger=lambda message: None)

    engine.mdrun("prod")
    command = engine.commands[-1]
    joined = " ".join(command)
    assert "-nb gpu -bonded gpu -gpu_id 0" in joined
    assert "-pme" not in joined
    assert cfg.mdrun_gpu_flags == ["-nb", "gpu", "-bonded", "gpu", "-gpu_id", "0"]

    engine.mdrun("em", nb="cpu")
    em = " ".join(engine.commands[-1])
    assert "-nb cpu" in em and "-gpu_id" not in em and "-pme" not in em

    engine.mdrun("prod", maxh=1.5, nsteps=250000, continue_run=True)
    resumed = " ".join(engine.commands[-1])
    assert "-maxh 1.500" in resumed and "-cpi prod.cpt" in resumed and "-nsteps 250000" in resumed


# ---------------------------------------------------------------------------
# resumable production: -maxh chunks + checkpoint continuation
# ---------------------------------------------------------------------------
def test_production_loop_chunks_and_resumes(tmp_path):
    cfg = Config(
        workdir=str(tmp_path / "work"),
        sequence=MAGAININ2,
        production_ns=100.0,
        segment_ns=10.0,
        maxh_hours=1.5,
        dry_run=False,
    )
    pipeline = Pipeline(cfg, output_dir=str(tmp_path / "out"), logger=lambda message: None)
    pipeline.engine = _StubEngine(cfg)

    report = pipeline._mdrun_until("prod", 100.0, "prod")

    assert report["completed"] is True
    assert report["ns"] == pytest.approx(100.0)
    assert report["mdrun_calls"] == 10
    assert report["nsteps_completed"] == 5_000_000
    assert report["ns_per_day"] == 900.0
    first = pipeline.engine.calls[0][1]
    assert first["nsteps"] == 500_000  # 10 ns at 20 fs
    assert first["continue_run"] is False  # nothing to resume from yet
    assert first["maxh"] == 1.5
    assert pipeline.engine.calls[1][1]["continue_run"] is True


def test_partial_production_is_not_marked_done(tmp_path):
    cfg = Config(workdir=str(tmp_path / "work"), sequence=MAGAININ2, dry_run=True)
    pipeline = Pipeline(cfg, output_dir=str(tmp_path / "out"), logger=lambda message: None)
    pipeline._mark("prod", "partial", ns=42.0)
    assert pipeline._stage_done("prod") is False
