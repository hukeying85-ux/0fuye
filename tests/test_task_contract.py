"""Contract tests for results/status/cgmd_task.json."""

from __future__ import annotations

import json
import os

import pytest

from core import task_contract as tc


def test_new_task_is_valid_and_pending():
    task = tc.new_task("GIGKFLHSAKKFGKAFVGEIMNS", name="magainin2", production_ns=500)
    assert task["schema"] == tc.SCHEMA
    assert task["status"] == tc.PENDING
    assert task["peptide"]["sequence"] == "GIGKFLHSAKKFGKAFVGEIMNS"
    assert task["membrane"]["lipids"] == {"POPE": 3, "POPG": 1}
    assert task["outputs"]["ntfy_topic"] == tc.DEFAULT_TOPIC
    assert task["task_id"].startswith("cgmd-")


def test_sequence_validation_rejects_garbage():
    with pytest.raises(tc.TaskError):
        tc.validate_sequence("MAGAININ2")
    with pytest.raises(tc.TaskError):
        tc.validate_sequence("")
    with pytest.raises(tc.TaskError):
        tc.validate_sequence("A" * (tc.MAX_PEPTIDE_LEN + 1))
    assert tc.validate_sequence("gigk-flhs aakk") == "GIGKFLHSAAKK"


def test_roundtrip_preserves_unknown_keys(tmp_path):
    task = tc.new_task("KKLLLLKK", name="probe")
    task["custom_field"] = {"from": "phone"}
    path = str(tmp_path / "cgmd_task.json")
    tc.dump_task(task, path)
    loaded = tc.load_task(path)
    assert loaded["custom_field"] == {"from": "phone"}
    with open(path, "rb") as handle:
        raw = handle.read()
    assert not raw.startswith(b"\xef\xbb\xbf"), "task JSON must be UTF-8 without BOM"
    assert raw.endswith(b"\n")


def test_state_machine_enforces_transitions():
    task = tc.new_task("KKLLLLKK", name="probe")
    tc.set_status(task, tc.CLAIMED, note="test")
    tc.set_status(task, tc.RUNNING)
    tc.set_status(task, tc.STATUS_DONE)
    assert task["status"] == tc.STATUS_DONE
    assert [entry["status"] for entry in task["history"]][-3:] == [tc.CLAIMED, tc.RUNNING, tc.STATUS_DONE]
    with pytest.raises(tc.TaskError):
        tc.set_status(task, tc.RUNNING)


def test_claim_semantics():
    task = tc.new_task("KKLLLLKK", name="probe")
    assert tc.is_claimable(task)
    tc.claim_task(task, owner="desktop")
    assert task["attempts"] == 1
    assert task["claim"]["owner"] == "desktop"
    assert not tc.is_claimable(task, stale_seconds=6 * 3600)
    # an abandoned claim becomes claimable again
    assert tc.is_claimable(task, stale_seconds=-1)


def test_validate_rejects_bad_numbers():
    task = tc.new_task("KKLLLLKK")
    task["simulation"]["production_ns"] = -5
    with pytest.raises(tc.TaskError):
        tc.validate_task(task)


def test_beijing_timestamps_carry_offset():
    stamp = tc.beijing_iso()
    assert stamp.endswith("+08:00")
    moment = tc.parse_iso(stamp)
    assert moment.utcoffset().total_seconds() == 8 * 3600


def test_reduced_result_shape():
    task = tc.new_task("KKLLLLKK", name="probe")
    task["status"] = tc.STATUS_DONE
    metrics = {
        "membrane_insertion": {"z_distance_mean_nm": -0.42},
        "lipid_order": {"mean": 0.91},
        "pore": {"pore_formed": True, "water_in_core_mean": 12.0},
        "simulation": {"ns_per_day": 950.0, "production_ns": 1000.0, "walltime_h": 25.2},
        "peptide": {"name": "probe", "sequence": "KKLLLLKK", "net_charge_ph7_4": 2.0},
    }
    result = tc.reduced_result(task, metrics, "results/cgmd/x/summary_metrics.json", figures=["a.svg"])
    assert result["schema"] == tc.RESULT_SCHEMA
    assert result["headline"]["z_distance_nm"] == -0.42
    assert result["headline"]["net_charge"] == 2.0
    assert result["headline"]["pore_formed"] is True
    assert len(json.dumps(result)) < 4000


def test_cli_new_writes_file(tmp_path):
    path = str(tmp_path / "task.json")
    assert tc.main(["new", "--sequence", "KKLLLLKK", "--write", path]) == 0
    assert os.path.exists(path)
    assert tc.load_task(path)["status"] == tc.PENDING


def test_idle_document_is_accepted():
    idle = {"schema": tc.SCHEMA, "task_id": "idle", "status": "idle"}
    assert tc.validate_task(dict(idle))["status"] == "idle"
