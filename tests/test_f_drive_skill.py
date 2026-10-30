"""F-drive migration skill and fixed-path mailbox wiring.

These tests prove repository-side wiring only.  They deliberately do not
claim that a workstation has loaded the code: that requires an actual
``files`` receipt whose detail reports the F: script/state paths.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

from core import hub_mailbox

ROOT = Path(__file__).resolve().parents[1]
HUB = ROOT / "skills" / "cgmd-hub"
RUNNER = HUB / "runner"
HELPER_PATH = HUB / "scripts" / "f_hub.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_helper():
    spec = importlib.util.spec_from_file_location("cgmd_f_hub", HELPER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skill_document_is_discoverable_and_truth_labelled():
    skill = _read(HUB / "SKILL.md")
    assert skill.startswith("---\nname: cgmd-hub\n")
    assert "代码已提交" in skill
    assert "已部署" in skill
    assert "已加载并实测" in skill
    assert r"F:\cgmd\runs\<任务ID>" in skill
    assert "refs/heads/hub/mailbox" in skill
    assert "不得继续写入 C 盘" in skill


def test_mailbox_client_advertises_files_and_stdin():
    assert "files" in hub_mailbox.KINDS
    assert "SHA-256" in hub_mailbox.JOB_HELP["files"]
    assert "stdin_text" in hub_mailbox.JOB_HELP["gmx"]
    caps = hub_mailbox.capabilities(str(ROOT))
    assert any("--kind files" in step for step in caps["first_steps"])
    assert any("F:" in step and "cgmd" in step and "runs" in step for step in caps["first_steps"])


def test_mailbox_worker_wires_files_stdin_and_f_roots():
    source = _read(RUNNER / "Invoke-CgmdMailbox.ps1")
    assert "function Invoke-JobFiles" in source
    assert "'files'     { return Invoke-JobFiles -JobArgs $jobArgs }" in source
    assert "Invoke-CgmdFiles.ps1" in source
    assert "[string]$StdinText = ''" in source
    assert "ConvertTo-StdinText" in source
    assert "Test-PathUnderRoot" in source
    assert "pipeline workdir must be under run_root" in source
    assert "pipeline outdir must be under result_root" in source


def test_files_runner_is_fixed_path_hash_verified_and_non_deleting():
    source = _read(RUNNER / "Invoke-CgmdFiles.ps1")
    assert r"$script:FixedSourceDir = 'C:\cgmd\0fuye\skills\cgmd-hub\state'" in source
    assert r"$script:FixedTargetRepo = 'F:\cgmd\0fuye'" in source
    assert r"$script:FixedRunRoot = 'F:\cgmd\runs'" in source
    assert r"$script:FixedResultRoot = 'F:\cgmd\results'" in source
    assert "CGMD_F_MIGRATION_CONFIRMED" in source
    assert "Get-FileHash" in source and "SHA256" in source
    assert "migration aborted before copy" in source
    assert "C: originals retained" in source
    assert "Remove-Item" not in source
    assert "handover_rollback" in source
    assert "Export-ScheduledTask" in source
    dirty = source.index("status', '--porcelain")
    reset = source.index("'reset', '--hard'")
    assert dirty < reset


def test_pipeline_defaults_use_configured_f_roots():
    source = _read(RUNNER / "Invoke-CgmdPipeline.ps1")
    assert "Get-Property $cfg 'run_root'" in source
    assert "Get-Property $cfg 'result_root'" in source
    assert "DefaultResultFile" in source
    assert "summary_metrics = $metrics" in source
    assert "svg_artifacts" in source
    assert "metrics_sha256" in source


def test_template_and_bootstrap_default_to_f_drive():
    template = json.loads(_read(HUB / "config" / "cgmd_hub.json"))
    assert template["repo_path"] == r"F:\cgmd\0fuye"
    assert template["run_root"] == r"F:\cgmd\runs"
    assert template["result_root"] == r"F:\cgmd\results"
    assert template["allow_shell"] is False
    bootstrap = _read(HUB / "bootstrap_desktop.ps1")
    assert "[string]$RepoPath = 'F:\\cgmd\\0fuye'" in bootstrap


def test_helper_builds_only_f_drive_payloads():
    helper = _load_helper()
    pipeline = helper.build_pipeline_args("magainin2-100ns-20261030")
    assert pipeline["workdir"] == r"F:\cgmd\runs\magainin2-100ns-20261030"
    assert pipeline["outdir"] == r"F:\cgmd\results\magainin2-100ns-20261030"
    assert pipeline["sequence"] == "GIGKFLHSAKKFGKAFVGEIMNS"
    assert pipeline["production_ns"] == 100.0
    assert pipeline["equilibration_ns"] == 10.0
    with pytest.raises(ValueError):
        helper.build_files_args("migrate")
    migrate = helper.build_files_args("migrate", confirm_mutation=True)
    assert migrate["confirm"] == helper.CONFIRM_TEXT
    with pytest.raises(ValueError):
        helper.build_pipeline_args("../escape")


def test_helper_rejects_partial_pipeline_claims():
    helper = _load_helper()
    partial = {
        "id": "job-partial",
        "kind": "pipeline",
        "status": "partial",
        "summary": "25000 steps only",
        "detail": {
            "completed": False,
            "completed_ns": 0.5,
            "steps_completed": 25000,
            "diverged": False,
        },
    }
    assert helper.assess_pipeline_result(partial)["proved_complete"] is False
    complete = {
        "id": "job-complete",
        "kind": "pipeline",
        "status": "ok",
        "summary": "complete",
        "detail": {
            "completed": True,
            "completed_ns": 100.0,
            "steps_completed": 5000000,
            "diverged": False,
        },
    }
    assert helper.assess_pipeline_result(complete)["proved_complete"] is True


def test_helper_insertion_depth_uses_pbc_and_midplane(tmp_path):
    helper = _load_helper()
    peptide = tmp_path / "peptide.xvg"
    phosphate = tmp_path / "phosphate.xvg"
    box = tmp_path / "box.xvg"
    peptide.write_text(
        "0 0 0 9.9 0 0 0.1\n20000 0 0 9.9 0 0 0.1\n", encoding="utf-8"
    )
    phosphate.write_text(
        "0 0 0 8.0 0 0 8.2 0 0 2.0 0 0 1.8\n"
        "20000 0 0 8.0 0 0 8.2 0 0 2.0 0 0 1.8\n",
        encoding="utf-8",
    )
    box.write_text("0 10 10 10\n20000 10 10 10\n", encoding="utf-8")
    outcome = helper.insertion_depth_from_xvg(peptide, phosphate, box)
    assert outcome["sampling"]["frames"] == 2
    assert outcome["z_distance_mean_nm"] == pytest.approx(0.0, abs=1e-9)
    assert outcome["insertion_depth_mean_nm"] == pytest.approx(1.9)
    assert "not pore evidence" in outcome["interpretation_limit"]


def test_helper_staging_refuses_gro_and_big_binary(tmp_path, monkeypatch):
    helper = _load_helper()
    pushed = []
    monkeypatch.setattr(
        helper.hub_mailbox,
        "push_files",
        lambda repo, ref, adds, removes, message: pushed.append((repo, ref, adds, removes, message)),
    )
    mdp = tmp_path / "prod.mdp"
    mdp.write_text("integrator = md\n", encoding="ascii")
    assert helper.stage_text_files("repo", {"staging/job/prod.mdp": mdp}) == ["staging/job/prod.mdp"]
    assert pushed

    topology = tmp_path / "topol.top"
    topology.write_text("[ system ]\n", encoding="ascii")
    with pytest.raises(ValueError):
        helper.stage_text_files("repo", {"staging/job/topol.top": topology})

    gro = tmp_path / "system.gro"
    gro.write_text("not staged\n", encoding="ascii")
    with pytest.raises(ValueError):
        helper.stage_text_files("repo", {"staging/job/system.gro": gro})

    binary = tmp_path / "bad.mdp"
    binary.write_bytes(b"abc\x00")
    with pytest.raises(ValueError):
        helper.stage_text_files("repo", {"staging/job/bad.mdp": binary})


def test_helper_extracts_only_small_session_artifacts(tmp_path):
    helper = _load_helper()
    result = {
        "kind": "pipeline",
        "detail": {
            "summary_metrics": {"schema": "cgmd.summary.v1"},
            "svg_artifacts": {
                "figures/depth.svg": "<svg xmlns='http://www.w3.org/2000/svg'></svg>",
                "../escape.svg": "<svg></svg>",
                "figures/not-svg.txt": "no",
            },
        },
    }
    outcome = helper.extract_pipeline_artifacts(result, tmp_path)
    assert (tmp_path / "summary_metrics.json").exists()
    assert (tmp_path / "figures" / "depth.svg").exists()
    assert not (tmp_path.parent / "escape.svg").exists()
    assert outcome["total_bytes"] < 1_000_000


def test_helper_preserves_exact_summary_bytes(tmp_path):
    import hashlib

    helper = _load_helper()
    exact = '{"z": 1, "a": 2}\n'
    result = {
        "kind": "pipeline",
        "detail": {
            "summary_metrics": {"a": 2, "z": 1},
            "summary_metrics_json": exact,
            "metrics_sha256": hashlib.sha256(exact.encode("utf-8")).hexdigest(),
            "svg_artifacts": {},
        },
    }
    outcome = helper.extract_pipeline_artifacts(result, tmp_path)
    assert (tmp_path / "summary_metrics.json").read_bytes() == exact.encode("utf-8")
    assert outcome["exact_metrics_copy"] is True
