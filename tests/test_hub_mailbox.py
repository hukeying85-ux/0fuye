"""The git mailbox is the bridge between any session and the desktop.

These tests build a real bare remote plus two clones, so both directions of the
protocol (the agent-side client here, the PowerShell worker on the desk) are
exercised against actual git plumbing.
"""

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import hub_mailbox  # noqa: E402

GIT_ENV = {
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def _git(cwd, *args):
    env = dict(os.environ)
    env.update(GIT_ENV)
    return subprocess.check_output(["git"] + list(args), cwd=cwd, env=env,
                                   stderr=subprocess.STDOUT).decode("utf-8", "replace")


@pytest.fixture()
def rig(tmp_path):
    """bare remote + two clones: `agent` queues, `desk` answers."""
    remote = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    remote.mkdir()
    _git(str(remote), "init", "--bare", "--quiet")
    seed.mkdir()
    _git(str(seed), "init", "--quiet")
    (seed / "README.md").write_text("seed\n", encoding="utf-8")
    _git(str(seed), "add", "README.md")
    _git(str(seed), "commit", "--quiet", "-m", "seed")
    _git(str(seed), "branch", "-M", "main")
    _git(str(seed), "remote", "add", "origin", str(remote))
    _git(str(seed), "push", "--quiet", "origin", "main")
    _git(str(remote), "symbolic-ref", "HEAD", "refs/heads/main")

    clones = {}
    for name in ("agent", "desk"):
        target = tmp_path / name
        _git(str(tmp_path), "clone", "--quiet", str(remote), str(target))
        clones[name] = str(target)
    return clones


def test_send_creates_the_mailbox_branch_without_touching_the_work_tree(rig):
    agent = rig["agent"]
    before = _git(agent, "status", "--porcelain")
    job_id = hub_mailbox.send(agent, "ping", {"echo": "hi"}, note="unit test")
    assert _git(agent, "status", "--porcelain") == before   # no work-tree change
    assert _git(agent, "rev-parse", "--abbrev-ref", "HEAD").strip() == "main"

    tip = hub_mailbox.fetch_ref(agent, hub_mailbox.DEFAULT_REF)
    assert tip
    raw = hub_mailbox.read_file(agent, tip, "inbox/%s.json" % job_id)
    request = json.loads(raw.decode("utf-8"))
    assert request["schema"] == hub_mailbox.SCHEMA_REQUEST
    assert request["kind"] == "ping"
    assert request["note"] == "unit test"
    assert request["args"] == {"echo": "hi"}


def test_worker_answers_and_the_client_sees_the_result(rig):
    agent, desk = rig["agent"], rig["desk"]

    def handler(request):
        return {"status": "ok", "summary": "pong from %s" % request["args"]["echo"],
                "detail": {"seen": request["id"]}}

    job_id = hub_mailbox.send(agent, "ping", {"echo": "desk"})
    assert hub_mailbox.read_result(agent, job_id) is None

    served = hub_mailbox.serve_once(desk, handler, worker="test-desk")
    assert len(served) == 1 and served[0]["status"] == "ok"

    result = hub_mailbox.wait(agent, job_id, timeout=5, interval=1, verbose=False)
    assert result["status"] == "ok"
    assert result["summary"] == "pong from desk"
    assert result["kind"] == "ping"
    assert result["detail"]["seen"] == job_id
    assert result["worker"] == "test-desk"

    # the request is consumed, exactly once
    snap = hub_mailbox.snapshot(agent)
    assert snap["pending"] == []
    assert job_id in snap["done"]
    assert hub_mailbox.serve_once(desk, handler) == []


def test_a_crashing_worker_still_publishes_an_error(rig):
    agent, desk = rig["agent"], rig["desk"]

    def handler(request):
        raise RuntimeError("gmx exploded")

    job_id = hub_mailbox.send(agent, "smoke", {"ps": 100})
    hub_mailbox.serve_once(desk, handler)
    result = hub_mailbox.wait(agent, job_id, timeout=5, interval=1, verbose=False)
    assert result["status"] == "error"
    assert "gmx exploded" in result["summary"]
    assert hub_mailbox.snapshot(agent)["pending"] == []


def test_two_clients_queue_without_fighting_over_a_branch(rig):
    """The whole point: requests never touch the caller's branch."""
    agent, desk = rig["agent"], rig["desk"]
    first = hub_mailbox.send(agent, "ping", {}, note="first")
    second = hub_mailbox.send(desk, "selfcheck", {}, note="second")
    snap = hub_mailbox.snapshot(agent)
    assert sorted(snap["pending"]) == sorted([first, second])

    served = hub_mailbox.serve_once(agent, lambda request: {"status": "ok",
                                                            "summary": request["note"]},
                                    max_jobs=2, worker="agent-worker")
    # ids are chronological to the second, so two jobs queued inside the same
    # second may be claimed in either order - both must still be answered
    assert sorted(item["summary"] for item in served) == ["first", "second"]
    assert hub_mailbox.wait(desk, first, timeout=5, interval=1, verbose=False)["status"] == "ok"
    assert hub_mailbox.read_result(desk, second)["summary"] == "second"


def test_wait_reports_a_lost_request_instead_of_hanging(rig):
    agent = rig["agent"]
    job_id = hub_mailbox.send(agent, "ping")
    # somebody deletes the request and never answers
    hub_mailbox.push_files(agent, hub_mailbox.DEFAULT_REF, {}, ["inbox/%s.json" % job_id],
                           "mailbox: drop %s" % job_id)
    result = hub_mailbox.wait(agent, job_id, timeout=1, interval=1, verbose=False)
    assert result["status"] == hub_mailbox.STATUS_LOST


def test_unknown_kind_is_rejected_before_it_reaches_the_desk(rig):
    with pytest.raises(hub_mailbox.MailboxError):
        hub_mailbox.send(rig["agent"], "format-my-disk", {})


def test_cli_round_trip(rig):
    agent = rig["agent"]
    out = subprocess.check_output(
        [sys.executable, "-m", "core.hub_mailbox", "--repo", agent, "send",
         "--kind", "ping", "--note", "cli"], cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        stderr=subprocess.STDOUT)
    payload = json.loads(out.decode("utf-8"))
    assert payload["id"]
    assert "wait" in payload["next"]


def test_the_powershell_worker_speaks_the_same_schema():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "skills", "cgmd-hub", "runner", "Invoke-CgmdMailbox.ps1")
    source = open(path, "rb").read().decode("ascii")   # pure ASCII is a hard rule
    assert "cgmd.mailbox.result.v1" in source
    assert "inbox" in source and "outbox" in source
    assert "hub/mailbox" in source


def test_mailbox_worker_static_contract():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "skills", "cgmd-hub", "runner", "Invoke-CgmdMailbox.ps1")
    source = open(path, "rb").read().decode("ascii")
    assert "cgmd.mailbox.worker.v1" in source
    # no shell by default, allowlisted gmx, worktree instead of the caller's tree
    assert "shell jobs are disabled" in source
    assert "GmxAllowList" in source
    assert "hub-mailbox" in source and "worktree" in source
    # every kind the client can send has an answer
    for kind in ("ping", "selfcheck", "sync", "smoke", "gmx", "shell", "pipeline"):
        assert "'%s'" % kind in source, kind


def test_poller_self_heals_without_a_human():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    source = open(os.path.join(root, "skills", "cgmd-hub", "runner", "Invoke-CgmdPoll.ps1"),
                  "rb").read().decode("ascii")
    assert "Open-PollLock" in source                 # stale lock is broken, not fatal
    assert "breaking a stale poll lock" in source
    assert "Test-SmokeDue" in source                 # periodic 100 ps without a request file
    assert "smoke schedule: queued an automatic 100 ps verification" in source
    assert "Invoke-MailboxOnce" in source            # other sessions -> this workstation
    assert "Clear-PollPid" in source


# ---------------------------------------------------------------------------
# cross-repository: an Arena session token only covers the repo the session
# lives in, so a peer queues in *its own* mailbox and the desk answers into the
# desk repo.  These tests pin that protocol down.
# ---------------------------------------------------------------------------
@pytest.fixture()
def two_remotes(tmp_path):
    made = {}
    for name in ("jev", "desk"):
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


def test_parse_peer_accepts_slug_ref_and_url():
    assert hub_mailbox.parse_peer("hukeying85-ux/JevHarness") == (
        "https://github.com/hukeying85-ux/JevHarness.git", "hub/mailbox")
    assert hub_mailbox.parse_peer("hukeying85-ux/0fuye#peer-test") == (
        "https://github.com/hukeying85-ux/0fuye.git", "peer-test")
    url, ref = hub_mailbox.parse_peer("https://example.com/x/y.git")
    assert (url, ref) == ("https://example.com/x/y.git", "hub/mailbox")


def test_peer_job_queued_in_another_repo_is_answered_into_the_desk_repo(two_remotes):
    jev, desk = two_remotes["jev"], two_remotes["desk"]

    # the peer can only push to its own repository
    job_id = hub_mailbox.send(jev, "ping", {"note": "from jev"}, note="cross-repo")

    def handler(request):
        return {"status": "ok", "summary": "peer pong", "detail": {"seen": request["id"]}}

    answered = hub_mailbox.peer_once(desk, [two_remotes["jev_url"]], handler)
    assert [item["id"] for item in answered] == [job_id]
    assert answered[0]["status"] == "ok"
    assert answered[0]["peer"] == two_remotes["jev_url"]

    # the caller reads the answer out of the desk repository
    result = hub_mailbox.read_result(desk, job_id)
    assert result["status"] == "ok"
    assert result["summary"] == "peer pong"

    # idempotent: a request that stays in the peer inbox is never run twice
    again = hub_mailbox.peer_once(desk, [two_remotes["jev_url"]], handler)
    assert again == []


def test_unreachable_peer_is_skipped_without_raising(two_remotes, tmp_path):
    desk = two_remotes["desk"]
    missing = "file://" + str(tmp_path / "nope.git")
    assert hub_mailbox.peer_once(desk, [missing], lambda request: {"status": "ok"}) == []


def test_cli_read_repo_reads_the_answer_from_the_desk_clone(two_remotes):
    jev, desk = two_remotes["jev"], two_remotes["desk"]
    job_id = hub_mailbox.send(jev, "ping", {}, note="cli read-repo")
    hub_mailbox.peer_once(desk, [two_remotes["jev_url"]],
                          lambda request: {"status": "ok", "summary": "served"})
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw = subprocess.check_output(
        [sys.executable, "-m", "core.hub_mailbox", "--repo", jev, "show", job_id, "--read-repo", desk],
        env=env, cwd=jev).decode("utf-8")
    assert json.loads(raw)["summary"] == "served"
