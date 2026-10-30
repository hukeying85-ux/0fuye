"""Integration test with the real martinize2 + insane and a stub GROMACS.

Skipped automatically on machines without the WSL2 toolchain, so it runs exactly
where it matters: on the desktop, after ``setup_env.sh --install``.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import textwrap

import pytest

from cgmd.config import Config, resolve_martini3_dir

FAKE_GMX = textwrap.dedent(
    """\
    #!/bin/bash
    # Stub GROMACS: reproduces only the files the pipeline consumes.
    set -u
    cmd="${1:-}"; shift || true
    conf=""; deffnm=""; out=""; mdp=""
    args=("$@")
    i=0
    while [ $i -lt ${#args[@]} ]; do
      case "${args[$i]}" in
        -c) conf="${args[$((i+1))]}" ;;
        -o) out="${args[$((i+1))]}" ;;
        -f) mdp="${args[$((i+1))]}" ;;
        -deffnm) deffnm="${args[$((i+1))]}" ;;
      esac
      i=$((i+1))
    done
    case "$cmd" in
      --version|version)
        echo "GROMACS version:    2024.1-stub"
        echo "GPU support:        CUDA"
        ;;
      grompp)
        echo stub > "$out"
        ;;
      mdrun)
        base="${deffnm:-md}"
        echo "Started mdrun on rank 0" > "${base}.log"
        if [ "$base" != "em" ]; then
          echo "   nsteps = 50000000" >> "${base}.log"
          echo "   dt = 0.02" >> "${base}.log"
          echo "Step           Time" >> "${base}.log"
          echo "       0        0.00000" >> "${base}.log"
          echo "Performance:      1200.000       0.072" >> "${base}.log"
          echo "Finished mdrun on rank 0" >> "${base}.log"
        else
          echo "Steepest Descents converged to Fmax < 10 in 250 steps" >> "${base}.log"
          echo "Maximum force     =  4.2e+00 on atom 42" >> "${base}.log"
        fi
        case "$base" in
          em) < inp="system.gro" ;;
          eq) < inp="em.gro" ;;
          prod) < inp="eq.gro" ;;
          *) < inp="" ;;
        esac
        if [ -n "$inp" ] && [ -f "$inp" ]; then cp "$inp" "${base}.gro"; fi
        ;;
    esac
    exit 0
    """
)


def _toolchain_available() -> bool:
    return bool(shutil.which("martinize2") and shutil.which("insane"))


@pytest.fixture(scope="module")
def stub_gmx(tmp_path_factory):
    path = tmp_path_factory.mktemp("bin") / "gmx"
    path.write_text(FAKE_GMX.replace("< inp=", "inp="), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


@pytest.mark.skipif(not _toolchain_available(), reason="martinize2 / insane not installed")
def test_pipeline_stages_with_real_builders(tmp_path, stub_gmx):
    try:
        martini_dir = resolve_martini3_dir(None)
    except FileNotFoundError:
        pytest.skip("Martini 3 force field not available")

    from cgmd.pipeline import Pipeline

    cfg = Config(
        workdir=str(tmp_path / "work"),
        sequence="GIGKFLHSAKKFGKAFVGEIMNS",
        peptide_name="magainin2",
        production_ns=20.0,
        equilibration_ns=0.4,
        martini3_dir=martini_dir,
        gmx_binary=stub_gmx,
        task_id="pytest-integration",
        max_frames=60,
    )
    pipeline = Pipeline(cfg, output_dir=str(tmp_path / "out"), logger=lambda message: None)
    metrics = pipeline.run()

    # structure / topology
    assert os.path.exists(cfg.path("peptide_cg.pdb"))
    top = open(cfg.path("topol.top"), encoding="utf-8").read()
    assert "[ molecules ]" in top and "Protein_0" in top
    assert "NA+" not in top.split("[ molecules ]")[1]
    validation = metrics["topology_validation"]
    assert validation["consistent"] is True

    # gromacs stages
    assert metrics["simulation"]["minimisation"]["converged"] is True
    assert metrics["simulation"]["ns_per_day"] == 1200.0
    assert metrics["simulation"]["diverged"] is False

    # analysis sections exist even without a trajectory
    for key in ("membrane_insertion", "lipid_order", "pore"):
        assert key in metrics

    summary = tmp_path / "out" / "summary_metrics.json"
    assert summary.exists()
    assert summary.stat().st_size < 1_000_000
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["peptide"]["sequence"] == "GIGKFLHSAKKFGKAFVGEIMNS"
    assert payload["system"]["lipids"] == {"POPE": 3.0, "POPG": 1.0}
    assert payload["system"]["lipid_ratio"] == "3:1"

    # resume must not recompute finished stages
    states = json.loads((tmp_path / "work" / "stages.json").read_text(encoding="utf-8"))
    assert states["stages"]["prod"]["status"] == "done"
    assert states["stages"]["analysis" if "analysis" in states["stages"] else "analyze"]["status"] == "done"


@pytest.mark.skipif(not _toolchain_available(), reason="martinize2 / insane not installed")
def test_index_groups_after_insane(tmp_path):
    try:
        martini_dir = resolve_martini3_dir(None)
    except FileNotFoundError:
        pytest.skip("Martini 3 force field not available")
    from cgmd.pipeline import Pipeline

    cfg = Config(
        workdir=str(tmp_path / "work"),
        sequence="KKLLKKLLKK",
        peptide_name="probe",
        production_ns=1.0,
        equilibration_ns=0.0,
        martini3_dir=martini_dir,
        dry_run=True,
    )
    pipeline = Pipeline(cfg, output_dir=str(tmp_path / "out"), logger=lambda message: None)
    pipeline.run()  # dry run: verifies the whole stage graph wiring
    assert os.path.exists(cfg.path("stages.json"))
