"""End-to-end smoke test of the pipeline in --dry-run mode (no GPU needed)."""

from __future__ import annotations

import json
import os

import pytest

from cgmd import cli, pipeline
from core import task_contract as tc


def test_desktop_runner_dry_run(tmp_path):
    """The full hub handshake: pending -> claimed -> running -> completed."""
    repo = tmp_path / "repo"
    task_path = repo / "results" / "status" / "cgmd_task.json"
    task_path.parent.mkdir(parents=True)
    task = tc.new_task("GIGKFLHSAKKFGKAFVGEIMNS", name="magainin2", production_ns=1000)
    tc.dump_task(task, str(task_path))

    import desktop_runner

    args = desktop_runner.build_parser().parse_args([
        "run",
        "--task-file", str(task_path),
        "--repo", str(repo),
        "--workdir-root", str(tmp_path / "work"),
        "--no-notify",
        "--dry-run",
    ])
    runner = desktop_runner.Runner(args)
    assert runner.run() == 0

    finished = tc.load_task(str(task_path))
    assert finished["status"] == tc.STATUS_DONE
    assert finished["attempts"] == 1
    assert finished["result"]["schema"] == tc.RESULT_SCHEMA
    summary = repo / "results" / "cgmd" / task["task_id"] / "summary_metrics.json"
    assert summary.exists()
    assert summary.stat().st_size < 1_000_000
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["peptide"]["sequence"] == "GIGKFLHSAKKFGKAFVGEIMNS"
    # the mirror used by the phone / dashboard
    assert (repo / "results" / "status" / "cgmd_result.json").exists()


def test_cli_plan_is_dry(tmp_path, capsys):
    code = cli.main([
        "plan",
        "--sequence", "KKLLKKLL",
        "--workdir", str(tmp_path / "work"),
        "--output", str(tmp_path / "out"),
        "--no-notify",
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "notes" in out


def test_render_mdp_has_no_placeholders(tmp_path):
    from cgmd.config import Config
    from cgmd.engine import Gromacs

    cfg = Config(workdir=str(tmp_path), sequence="KKLL", production_ns=1000, equilibration_ns=20)
    engine = Gromacs(cfg, logger=lambda message: None)
    paths = engine.render_all(cfg)
    assert set(paths) == {"em", "eq", "prod"}
    for path in paths.values():
        text = open(path, encoding="utf-8").read()
        assert "@" not in text
        assert "reaction-field" in text
        assert "epsilon_r               = 15" in text
    prod = open(paths["prod"], encoding="utf-8").read()
    assert "integrator              = md" in prod
    assert "nsteps                  = {}".format(cfg.prod_nsteps) in prod
    assert cfg.prod_nsteps == 50_000_000  # 1000 ns / 0.02 ps


def test_em_log_parser():
    log = """
Steepest Descents converged to Fmax < 10 in 812 steps
Potential Energy  = -1.234e+06
Maximum force     =  9.8e+00 on atom 42
"""
    report = pipeline.parse_em_log(log)
    assert report["converged"] is True
    assert report["steps"] == 812
    assert report["max_force"] == pytest.approx(9.8)


def test_figure_and_summary_sizes(tmp_path):
    pytest.importorskip("matplotlib")
    from cgmd import analyze, figure

    metrics = {
        "timeseries": {
            "time_ns": [0, 1, 2, 3],
            "z_distance_nm": [2.0, 1.0, 0.2, -0.1],
            "lipid_order_sn1": [0.9, 0.91, 0.9, 0.92],
            "lipid_order_sn2": [0.88, 0.9, 0.91, 0.9],
            "water_in_core": [0, 1, 3, 12],
        },
        "membrane_insertion": {"z_distance_mean_nm": -0.1, "per_residue_z_nm": [0.1, 0.2, -0.3]},
        "lipid_order": {"mean": 0.9},
        "pore": {"pore_formed": True, "water_in_core_max": 12},
        "membrane": {"thickness_nm": 3.3, "thickness_series_nm": [3.3, 3.3]},
    }
    paths = figure.make_figures(metrics, {"sequence": "KKLLKKLL"}, outdir=str(tmp_path / "fig"))
    assert paths
    for path in paths:
        assert path.endswith(".svg")
        assert os.path.getsize(path) < 200_000
    summary_path = str(tmp_path / "summary_metrics.json")
    analyze.write_summary(metrics, summary_path)
    assert os.path.getsize(summary_path) < 1_000_000
