"""The desktop self-check contract: request file, report schema, verdict."""

from __future__ import annotations

import json
import os
import re

import pytest

from core import selfcheck

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FIXTURE = os.path.join(REPO_ROOT, "tests", "fixtures", "desktop_selfcheck.example.json")
HUB = os.path.join(REPO_ROOT, "skills", "cgmd-hub")


def _load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# example report
# ---------------------------------------------------------------------------
def test_example_report_is_valid():
    report = _load(FIXTURE)
    assert selfcheck.validate_report(report) == []


def test_example_report_covers_every_check_id():
    report = _load(FIXTURE)
    seen = {entry["id"] for entry in report["checks"]}
    assert seen == set(selfcheck.CHECK_IDS)


def test_verdict_says_desktop_is_ready():
    reduced = selfcheck.verdict(_load(FIXTURE))
    assert reduced["overall"] == "warn"
    assert reduced["ready_for_task"] is True
    assert reduced["counts"]["failed"] == 0


def test_verdict_surfaces_the_warning():
    reduced = selfcheck.verdict(_load(FIXTURE))
    assert [entry["id"] for entry in reduced["warnings"]] == ["disk"]


def test_table_and_summary_render():
    report = _load(FIXTURE)
    table = selfcheck.format_table(report)
    assert "gromacs" in table
    assert "WARN" in selfcheck.summarise(report).upper()


# ---------------------------------------------------------------------------
# validation must actually reject broken reports
# ---------------------------------------------------------------------------
def test_wrong_schema_is_rejected():
    report = _load(FIXTURE)
    report["schema"] = "cgmd.summary.v1"
    assert any("schema" in problem for problem in selfcheck.validate_report(report))


def test_failure_must_flip_overall():
    report = _load(FIXTURE)
    report["checks"][5]["status"] = "fail"
    report["summary"]["failed"] = 1
    problems = selfcheck.validate_report(report)
    assert any("overall must be fail" in problem for problem in problems)


def test_warnings_must_downgrade_overall():
    report = _load(FIXTURE)
    report["overall"] = "pass"
    problems = selfcheck.validate_report(report)
    assert any("overall must be warn" in problem for problem in problems)


def test_a_failure_makes_the_desktop_not_ready():
    report = _load(FIXTURE)
    for entry in report["checks"]:
        if entry["id"] == "gromacs":
            entry["status"] = "fail"
    report["summary"]["passed"] = 12
    report["summary"]["warnings"] = 0
    report["summary"]["failed"] = 1
    report["overall"] = "fail"
    assert selfcheck.validate_report(report) == []
    reduced = selfcheck.verdict(report)
    assert reduced["ready_for_task"] is False
    assert [entry["id"] for entry in reduced["failing"]] == ["gromacs"]


def test_unknown_check_id_is_rejected():
    report = _load(FIXTURE)
    report["checks"].append({"id": "made_up", "title": "x", "status": "pass", "detail": "y"})
    problems = selfcheck.validate_report(report)
    assert any("unknown check ids" in problem for problem in problems)


def test_empty_checks_is_rejected():
    report = _load(FIXTURE)
    report["checks"] = []
    assert selfcheck.validate_report(report) != []


# ---------------------------------------------------------------------------
# request document
# ---------------------------------------------------------------------------
def test_request_roundtrip(tmp_path):
    request = selfcheck.new_request(note="unit test")
    assert selfcheck.validate_request(request) == []
    path = str(tmp_path / "selfcheck_request.json")
    selfcheck.dump(request, path)
    reloaded = selfcheck.load(path)
    assert reloaded["schema"] == selfcheck.REQUEST_SCHEMA
    assert selfcheck.validate_request(reloaded) == []


def test_bad_request_is_rejected():
    assert selfcheck.validate_request({"schema": "nope"}) != []


def test_request_file_in_repo_is_valid():
    path = os.path.join(REPO_ROOT, selfcheck.REQUEST_PATH)
    if not os.path.exists(path):
        pytest.skip("no outstanding self-check request")
    assert selfcheck.validate_request(selfcheck.load(path)) == []


# ---------------------------------------------------------------------------
# the powershell side must stay in step with the python contract
# ---------------------------------------------------------------------------
def test_selfcheck_script_exists_and_is_ascii():
    path = os.path.join(HUB, "runner", "Test-CgmdHub.ps1")
    assert os.path.exists(path)
    with open(path, "rb") as handle:
        handle.read().decode("ascii")


def test_selfcheck_script_knows_every_check_id():
    path = os.path.join(HUB, "runner", "Test-CgmdHub.ps1")
    with open(path, encoding="ascii") as handle:
        source = handle.read()
    for check_id in selfcheck.CHECK_IDS:
        assert "'{}'".format(check_id) in source, check_id
    assert selfcheck.REPORT_SCHEMA in source
    assert selfcheck.REPORT_PATH.replace("/", "\\") in source or "desktop_selfcheck.json" in source


def test_poller_wires_the_request_file():
    path = os.path.join(HUB, "runner", "Invoke-CgmdPoll.ps1")
    with open(path, encoding="ascii") as handle:
        source = handle.read()
    assert "selfcheck_request.json" in source
    assert "Test-CgmdHub.ps1" in source
    assert "desktop_selfcheck.json" in source


def test_bootstrap_runs_the_selfcheck():
    path = os.path.join(HUB, "bootstrap_desktop.ps1")
    with open(path, encoding="ascii") as handle:
        source = handle.read()
    assert "Test-CgmdHub.ps1" in source


def test_cli_status_reports_no_report(tmp_path, capsys):
    missing = str(tmp_path / "nope.json")
    assert selfcheck.main(["status", "--path", missing]) == 1
    assert "NO REPORT" in capsys.readouterr().out


def test_cli_check_accepts_the_fixture(capsys):
    assert selfcheck.main(["check", FIXTURE]) == 0
    assert "OK" in capsys.readouterr().out


def test_cli_show_prints_the_table(capsys):
    assert selfcheck.main(["show", FIXTURE]) == 0
    out = capsys.readouterr().out.lower()
    assert "gromacs" in out and "pass" in out and "warn" in out


# ---------------------------------------------------------------------------
# one-command sync (git + Arena Desk + self-check)
# ---------------------------------------------------------------------------
SYNC_SCRIPT = os.path.join(HUB, "runner", "Sync-Desktop.ps1")


def test_sync_script_exists_and_is_ascii():
    assert os.path.exists(SYNC_SCRIPT)
    with open(SYNC_SCRIPT, "rb") as handle:
        handle.read().decode("ascii")


def test_sync_script_covers_the_whole_chain():
    source = open(SYNC_SCRIPT, encoding="ascii").read()
    assert "reset" in source and "--hard" in source          # pull the branch tip
    assert "code" in source and "panel" in source            # Arena Desk location
    assert "deploy.ps1" in source                            # desk deployment
    assert "Test-CgmdHub.ps1" in source                      # self-check
    assert "desktop_sync.json" in source                     # sync record
    assert "cgmd.desksync.v1" in source                      # its schema
    # exit codes: 4 config, 5 origin lock, 8 git, 9 desk deploy, 7 self-check
    assert "exit 4" in source and "exit 5" in source and "exit 8" in source
    for code in ("= 9", "= 7"):
        assert code in source, code
    assert "exit $exitCode" in source


def test_poller_can_trigger_the_desk_sync():
    source = open(os.path.join(HUB, "runner", "Invoke-CgmdPoll.ps1"), encoding="ascii").read()
    assert "Sync-Desktop.ps1" in source
    assert "wantDesk" in source


def test_request_carries_the_desk_flag():
    request = selfcheck.new_request(note="desk please", desk=True)
    assert request["desk"] is True
    assert selfcheck.validate_request(request) == []
    assert "desk=false" not in request["how"]
    plain = selfcheck.new_request()
    assert plain["desk"] is False


def test_desk_flag_must_be_boolean():
    request = selfcheck.new_request()
    request["desk"] = "yes"
    assert any("desk must be a boolean" in problem for problem in selfcheck.validate_request(request))
