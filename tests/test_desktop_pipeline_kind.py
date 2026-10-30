"""The desktop worker must be able to run the whole pipeline by itself.

Pins the wiring that was missing on DESKTOP-IEUDGS5: the ``pipeline`` job kind
(native Python + native gmx.exe, never WSL), the 5400 s per-job ceiling, the
``branch`` switch in deskfix, and the ``arena/*`` scan in the peer cycle.
"""

from __future__ import annotations

import json
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNER = os.path.join(ROOT, "skills", "cgmd-hub", "runner")


def _read(name: str) -> str:
    with open(os.path.join(RUNNER, name), "rb") as handle:
        return handle.read().decode("ascii")


def test_mailbox_worker_wires_the_pipeline_kind():
    source = _read("Invoke-CgmdMailbox.ps1")
    assert "function Invoke-JobPipeline" in source
    assert "'pipeline'  { return Invoke-JobPipeline -JobArgs $jobArgs }" in source
    assert "Invoke-CgmdPipeline.ps1" in source
    assert "-no-notify" not in source  # the CLI flag lives in the runner, not here
    assert "the Martini pipeline job kind is not wired yet" not in source


def test_job_ceiling_is_5400_seconds():
    mailbox = _read("Invoke-CgmdMailbox.ps1")
    bridge = _read("Invoke-CgmdBridge.ps1")
    poll = _read("Invoke-CgmdPoll.ps1")
    assert "[int]$MaxJobSeconds = 5400," in mailbox
    assert "[int]$MaxJobSeconds = 5400," in bridge
    # the poll wrapper must outlive the worker's own 5400 s budget
    assert "-TimeoutSeconds 5700" in poll


def test_deskfix_can_move_the_clone_to_another_branch():
    source = _read("Invoke-CgmdMailbox.ps1")
    assert "Get-Property $JobArgs 'branch'" in source
    assert "Set-HubConfigValue -Name 'branch'" in source
    assert "'reset', '--hard', ('origin/' + $branchValue)" in source
    assert "checkout', '--quiet', '--force'" in source


def test_peer_cycle_scans_hub_mailbox_and_arena_branches():
    source = _read("Invoke-CgmdMailbox.ps1")
    assert "function Get-PeerRefs" in source
    assert "refs/heads/arena/*" in source
    assert "function Receive-PeerRefJobs" in source
    # both the configured ref and the arena refs are fed through the same path
    assert "$refs = @(Get-PeerRefs -Peer $peer)" in source


def test_pipeline_runner_uses_native_python_and_gmx():
    source = _read("Invoke-CgmdPipeline.ps1")
    assert "-m', 'cgmd.cli', 'run'" in source or "'-m', 'cgmd.cli', 'run'" in source
    assert "PYTHONPATH" in source
    assert "Python312" in source          # native 3.12 is preferred
    assert "gmx.exe" in source
    # the WSL binaries are what this path exists to avoid
    assert "wsl.exe" not in source.lower() and "wslpath" not in source.lower()
    assert "--maxh" in source and "[double]$Maxh" in source
    assert "-cpi" in source or "resume" in source.lower()


def test_pipeline_runner_keeps_heavy_artifacts_out_of_the_repository():
    source = _read("Invoke-CgmdPipeline.ps1")
    # work dir stays under the git-ignored hub state, output is the small result
    assert "'cgmd-runs\\'" in source or "cgmd-runs" in source
    assert "summary_metrics.json" in source


def test_pipeline_result_reports_the_numbers_we_have_to_quote():
    source = _read("Invoke-CgmdPipeline.ps1")
    for key in ("completed_ns", "steps_completed", "ns_per_day", "z_distance_nm", "gpu_flags"):
        assert key in source, key


# ---------------------------------------------------------------------------
# cross-branch peer delivery: a session that can only push its own arena branch
# ---------------------------------------------------------------------------
def _git(cwd, *args):
    env = dict(os.environ)
    env.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"})
    return subprocess.check_output(["git"] + list(args), cwd=cwd, env=env,
                                   stderr=subprocess.STDOUT).decode("utf-8", "replace")


@pytest.fixture()
def remotes(tmp_path):
    made = {}
    for name in ("peer", "desk"):
        remote = tmp_path / (name + ".git")
        remote.mkdir()
        _git(str(remote), "init", "--bare", "--quiet")
        seed = tmp_path / (name + "-seed")
        seed.mkdir()
        _git(str(seed), "init", "--quiet")
        (seed / "README.md").write_text("seed\n", encoding="utf-8")
        _git(str(seed), "add", "README.md")
        _git(str(seed), "commit", "--quiet", "-m", "seed")
        _git(str(seed), "branch", "-M", "main")
        _git(str(seed), "remote", "add", "origin", str(remote))
        _git(str(seed), "push", "--quiet", "origin", "main")
        _git(str(remote), "symbolic-ref", "HEAD", "refs/heads/main")
        clone = tmp_path / (name + "-clone")
        _git(str(tmp_path), "clone", "--quiet", str(remote), str(clone))
        made[name] = str(clone)
        made[name + "_url"] = str(remote)
    return made


def test_job_queued_on_an_arena_branch_is_answered(remotes):
    from core import hub_mailbox

    peer, desk = remotes["peer"], remotes["desk"]
    branch = "arena/3a8e0140-0fuye"
    job_id = hub_mailbox.new_id()
    request = {
        "schema": hub_mailbox.SCHEMA_REQUEST,
        "id": job_id,
        "kind": "ping",
        "args": {},
        "note": "queued on my own session branch",
        "from": "arena-session",
        "timeout_s": 300,
    }
    hub_mailbox.push_files(peer, branch, {"inbox/%s.json" % job_id: json.dumps(request).encode("utf-8")},
                           [], "mailbox: request %s" % job_id)

    answered = hub_mailbox.peer_once(desk, [remotes["peer_url"]],
                                     lambda req: {"status": "ok", "summary": "arena branch served"})
    assert [item["id"] for item in answered] == [job_id]
    assert answered[0]["peer_ref"] == branch
    assert answered[0]["status"] == "ok"
    result = hub_mailbox.read_result(desk, job_id)
    assert result["summary"] == "arena branch served"


def test_list_remote_heads_only_returns_arena_branches(remotes):
    from core import hub_mailbox

    peer = remotes["peer"]
    for name in ("arena/aaa", "arena/bbb", "feature/ccc"):
        hub_mailbox.push_files(peer, name, {"README.md": b"x\n"}, [], "seed " + name)
    heads = hub_mailbox.list_remote_heads(peer, remotes["peer_url"])
    assert sorted(heads) == ["arena/aaa", "arena/bbb"]
    assert hub_mailbox.list_remote_heads(peer, "file://" + peer + "-missing") == []


def test_pipeline_kind_is_documented_for_callers():
    from core import hub_mailbox

    assert "pipeline" in hub_mailbox.KINDS
    assert "not wired yet" not in hub_mailbox.JOB_HELP["pipeline"]
    assert "gmx.exe" in hub_mailbox.JOB_HELP["pipeline"]
