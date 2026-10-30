"""Git-backed job mailbox: any session -> the desktop workstation, and back.

Why a mailbox and not a request file on the working branch
----------------------------------------------------------
The desktop hub already polls a branch every 60 s.  Dropping a request file on
that same branch works, but every agent that touches it races the hub's delete
and the operator's rebase: that exact conflict cost several manual rounds.

This module speaks a tiny protocol over a **dedicated ref** (``hub/mailbox`` by
default) so that:

* the caller never commits to its own branch (no rebase conflicts, ever);
* any session, on any branch, on any machine, can queue work;
* the desk writes the answer next to the request, so a caller only has to read
  one file it already knows the name of.

Layout on the mailbox ref::

    inbox/<id>.json     request  (cgmd.mailbox.request.v1)
    outbox/<id>.json    result   (cgmd.mailbox.result.v1)

``id`` is ``YYYYmmddTHHMMSS-<6 hex>`` so lexical order is chronological.

Writes never touch the work tree: a throw-away index (``GIT_INDEX_FILE``) plus
``commit-tree`` + ``push`` is enough, and it is safe to call from inside a dirty
checkout that belongs to something else entirely.

CLI
---
    python3 -m core.hub_mailbox send --kind smoke --note "10-29 retest"
    python3 -m core.hub_mailbox send --kind gmx --arg --version
    python3 -m core.hub_mailbox wait 20261029T124500-ab12cd --timeout 900
    python3 -m core.hub_mailbox run  --kind selfcheck --timeout 600
    python3 -m core.hub_mailbox ls
    python3 -m core.hub_mailbox show 20261029T124500-ab12cd
"""

import argparse
import datetime
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_REQUEST = "cgmd.mailbox.request.v1"
SCHEMA_RESULT = "cgmd.mailbox.result.v1"
DEFAULT_REF = "hub/mailbox"

# Kinds the desktop worker knows.  shell is opt-in on the desk side.
KINDS = ("ping", "selfcheck", "smoke", "sync", "gmx", "deskdiag", "deskfix", "shell", "pipeline", "cgmd")

# One line per kind, printed by ``caps`` so a brand-new session never has to
# guess what the desk can do.
JOB_HELP = {
    "ping": "is the desk alive? host, gmx version, gpus, LAN addresses, bridge port (~1 s)",
    "selfcheck": "18-item health check, writes results/status/desktop_selfcheck.json",
    "smoke": '{"ps": 100} real GROMACS run on the GPU, writes results/status/gmx_smoke.json',
    "sync": '{"desk": true} pull the branch on the desk, redeploy Arena Desk, restart the panel',
    "gmx": '--arg --version whitelisted gmx sub-command, argv lives in args.argv',
    "deskdiag": "file hashes repo-vs-desk, scheduled tasks, served HTML, boot ack, lock state",
    "deskfix": "re-arm the logon trigger, keep the panel alive, launch the boot animation now",
    "shell": "opt-in on the desk side (allow_shell=false by default)",
    "cgmd": '{"mode": "build|run|probe|search|ff|all"} coarse-grained MD, no shell needed',
    "pipeline": "Martini pipeline, not wired yet - use smoke or gmx",
}

# Status files the desk publishes; ``caps`` reads them straight from the tree.
STATUS_FILES = {
    "heartbeat": "results/status/hub_heartbeat.json",
    "selfcheck": "results/status/desktop_selfcheck.json",
    "smoke": "results/status/gmx_smoke.json",
    "mailbox": "results/status/hub_mailbox.json",
}

STATUS_OK = "ok"
STATUS_FAIL = "fail"
STATUS_ERROR = "error"
STATUS_UNSUPPORTED = "unsupported"
STATUS_TIMEOUT = "timeout"
STATUS_LOST = "lost"


class MailboxError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# tiny git layer
# ---------------------------------------------------------------------------
def _run(repo: str, args: List[str], data: Optional[bytes] = None,
         env: Optional[Dict[str, str]] = None, timeout: int = 180) -> Tuple[int, bytes, bytes]:
    proc = subprocess.Popen(
        ["git"] + args,
        cwd=repo,
        stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        out, err = proc.communicate(data, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        return 124, out or b"", (err or b"") + b"\nmailbox: git timed out"
    return proc.returncode, out or b"", err or b""


def _git(repo: str, args: List[str], data: Optional[bytes] = None,
         env: Optional[Dict[str, str]] = None) -> bytes:
    code, out, err = _run(repo, args, data, env)
    if code != 0:
        raise MailboxError("git %s failed (%d): %s" % (
            " ".join(args), code,
            (err or out).decode("utf-8", "replace").strip()[:400]))
    return out


def repo_root(path: str) -> str:
    return _git(path, ["rev-parse", "--show-toplevel"]).decode("utf-8").strip()


def tracking_ref(remote: str, ref: str) -> str:
    return "refs/remotes/%s/%s" % (remote, ref)


def fetch_ref(repo: str, ref: str, remote: str = "origin") -> Optional[str]:
    """Fetch ``ref`` into its remote-tracking ref; return the tip or None."""
    code, out, err = _run(repo, ["fetch", "--quiet", remote,
                                 "+refs/heads/%s:%s" % (ref, tracking_ref(remote, ref))])
    if code != 0:
        # A missing branch is normal the first time; anything else is not.
        text = (err or out).decode("utf-8", "replace")
        if "couldn't find remote ref" in text or "not our ref" in text or "no such remote ref" in text:
            return None
        raise MailboxError("mailbox fetch failed: " + text.strip()[:300])
    code, out, _ = _run(repo, ["rev-parse", "--verify", tracking_ref(remote, ref)])
    if code != 0:
        return None
    return out.decode("utf-8").strip() or None


def list_files(repo: str, commit: str, prefix: str) -> List[str]:
    if not commit:
        return []
    code, out, _ = _run(repo, ["ls-tree", "-r", "--name-only", commit, "--", prefix])
    if code != 0:
        return []
    return [line for line in out.decode("utf-8", "replace").splitlines() if line.strip()]


def read_file(repo: str, commit: str, path: str) -> Optional[bytes]:
    if not commit:
        return None
    code, out, _ = _run(repo, ["cat-file", "-p", "%s:%s" % (commit, path)])
    return out if code == 0 else None


def remote_has_ref(repo: str, ref: str, remote: str = "origin") -> bool:
    code, out, _ = _run(repo, ["ls-remote", "--heads", remote, ref])
    if code != 0:
        return False
    return bool(out.strip())


# ---------------------------------------------------------------------------
# writing to the ref without touching the work tree
# ---------------------------------------------------------------------------
def _author_args() -> List[str]:
    return ["-c", "user.name=CGMD-Desk",
            "-c", "user.email=hukeying85-ux@users.noreply.github.com"]


def push_files(repo: str, ref: str, adds: Dict[str, bytes], removes: List[str],
               message: str, remote: str = "origin", attempts: int = 4) -> str:
    """Commit ``adds``/``removes`` on top of ``ref`` and push.  Returns the sha."""
    last = ""
    for attempt in range(attempts):
        base = fetch_ref(repo, ref, remote)
        tmp = tempfile.mkdtemp(prefix="cgmd-mailbox-")
        index = os.path.join(tmp, "index")
        env = dict(os.environ)
        env["GIT_INDEX_FILE"] = index
        try:
            _git(repo, ["read-tree", base] if base else ["read-tree", "--empty"], env=env)
            for path, data in adds.items():
                blob = _git(repo, ["hash-object", "-w", "--stdin"], data=data).decode("utf-8").strip()
                _git(repo, ["update-index", "--add", "--cacheinfo",
                            "100644,%s,%s" % (blob, path)], env=env)
            for path in removes:
                _run(repo, ["update-index", "--force-remove", path], env=env)
            tree = _git(repo, ["write-tree"], env=env).decode("utf-8").strip()
            args = _author_args() + ["commit-tree", tree, "-m", message]
            if base:
                args += ["-p", base]
            commit = _git(repo, args, env=env).decode("utf-8").strip()
            code, out, err = _run(repo, ["push", "--quiet", remote,
                                         "%s:refs/heads/%s" % (commit, ref)])
            if code == 0:
                _run(repo, ["update-ref", tracking_ref(remote, ref), commit])
                return commit
            last = (err or out).decode("utf-8", "replace").strip()[:400]
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        # Someone else pushed first: rebuild on the new tip.
        time.sleep(1.5 + attempt)
    raise MailboxError("mailbox push failed after %d attempts: %s" % (attempts, last))


# ---------------------------------------------------------------------------
# jobs
# ---------------------------------------------------------------------------
def new_id() -> str:
    return "%s-%04x" % (time.strftime("%Y%m%dT%H%M%S"), random.randint(0, 0xFFFF))


def me() -> str:
    return os.environ.get("CGMD_MAILBOX_FROM") or (os.environ.get("USER") or
                                                   os.environ.get("USERNAME") or "unknown")


def send(repo: str, kind: str, args: Optional[Dict[str, Any]] = None,
         note: str = "", ref: str = DEFAULT_REF, timeout_s: int = 1800,
         remote: str = "origin", sender: Optional[str] = None) -> str:
    if kind not in KINDS:
        raise MailboxError("unknown kind %r (choose from %s)" % (kind, ", ".join(KINDS)))
    job_id = new_id()
    request = {
        "schema": SCHEMA_REQUEST,
        "id": job_id,
        "kind": kind,
        "args": args or {},
        "note": note,
        "from": sender or me(),
        "host": os.environ.get("COMPUTERNAME") or os.uname()[1] if hasattr(os, "uname") else "unknown",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "timeout_s": int(timeout_s),
    }
    body = json.dumps(request, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    push_files(repo, ref, {"inbox/%s.json" % job_id: body}, [], "mailbox: request %s (%s)" % (job_id, kind),
               remote=remote)
    return job_id


def read_result(repo: str, job_id: str, ref: str = DEFAULT_REF, remote: str = "origin") -> Optional[Dict[str, Any]]:
    commit = fetch_ref(repo, ref, remote)
    if not commit:
        return None
    raw = read_file(repo, commit, "outbox/%s.json" % job_id)
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return None


def request_pending(repo: str, job_id: str, ref: str = DEFAULT_REF, remote: str = "origin") -> bool:
    commit = fetch_ref(repo, ref, remote)
    if not commit:
        return False
    return bool(read_file(repo, commit, "inbox/%s.json" % job_id))


def wait(repo: str, job_id: str, ref: str = DEFAULT_REF, timeout: int = 1800,
         interval: int = 15, remote: str = "origin", verbose: bool = True) -> Dict[str, Any]:
    """Block until the desk answers.  Never raises on a timeout: it reports it."""
    started = time.time()
    last_note = 0.0
    while True:
        result = read_result(repo, job_id, ref=ref, remote=remote)
        if result is not None:
            return result
        elapsed = time.time() - started
        if elapsed >= timeout:
            still_queued = request_pending(repo, job_id, ref=ref, remote=remote)
            return {
                "schema": SCHEMA_RESULT,
                "id": job_id,
                "kind": "unknown",
                "status": STATUS_TIMEOUT if still_queued else STATUS_LOST,
                "seconds": round(elapsed, 1),
                "summary": ("request is still queued after %d s (desk idle or busy)" % timeout)
                           if still_queued else ("request vanished without a result; the desk never saw it"),
            }
        if verbose and elapsed - last_note >= 60:
            last_note = elapsed
            sys.stderr.write("mailbox: waiting for %s (%d s)\n" % (job_id, int(elapsed)))
            sys.stderr.flush()
        time.sleep(max(2, interval))


def parse_peer(entry: str, default_ref: str = DEFAULT_REF) -> Tuple[str, str]:
    """``owner/repo`` or ``owner/repo#ref`` or a full URL -> (url, ref)."""
    text = (entry or "").strip()
    ref = default_ref
    if "#" in text:
        text, _, tail = text.partition("#")
        if tail.strip():
            ref = tail.strip()
    if "://" in text or text.startswith("git@"):
        url = text
    elif text.count("/") == 1:
        url = "https://github.com/%s.git" % text
    else:
        url = text
    return url, ref


def peer_once(desk_repo: str, peers: List[str], handler, ref: str = DEFAULT_REF,
              remote: str = "origin", max_jobs: int = 1,
              worker: str = "peer") -> List[Dict[str, Any]]:
    """Answer jobs that were queued in *other* repositories' mailboxes.

    An Arena session token is scoped to the one repository the session lives in:
    a JevHarness session that tries to push into 0fuye gets ``403 Resource not
    accessible by integration``.  So a peer queues work in its own mailbox, the
    desk pulls that ref **anonymously** (every peer repo is public), runs the job
    here, and publishes the answer into its own mailbox -- the caller reads it by
    id from the desk repo.

    This is the Python twin of ``Invoke-PeerCycle`` in
    ``skills/cgmd-hub/runner/Invoke-CgmdMailbox.ps1``; the tests drive this one.
    """
    results: List[Dict[str, Any]] = []
    if not peers:
        return results
    tip = fetch_ref(desk_repo, ref, remote)
    answered = set()
    if tip:
        answered = {os.path.basename(path)[:-5] for path in list_files(desk_repo, tip, "outbox")
                    if path.endswith(".json")}
    budget = max(0, int(max_jobs))
    for index, entry in enumerate(peers, start=1):
        if budget <= 0:
            break
        url, peer_ref = parse_peer(entry, ref)
        tracking = "refs/remotes/peer-%d/%s" % (index, peer_ref)
        # anonymous first: the desk's stored credential belongs to one repo only
        code, _, _ = _run(desk_repo, ["-c", "credential.helper=", "fetch", "--quiet", "--no-tags",
                                      url, "+refs/heads/%s:%s" % (peer_ref, tracking)])
        if code != 0:
            continue
        peer_tip = _run(desk_repo, ["rev-parse", tracking])[1].decode("utf-8", "replace").strip()
        if not peer_tip:
            continue
        adds: Dict[str, bytes] = {}
        for path in sorted(list_files(desk_repo, peer_tip, "inbox")):
            if not path.endswith(".json") or budget <= 0:
                continue
            job_id = os.path.basename(path)[:-5]
            if job_id in answered:
                continue
            raw = read_file(desk_repo, peer_tip, path)
            if raw is None:
                continue
            try:
                request = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                request = {"id": job_id, "kind": "unknown", "args": {}}
            started = time.time()
            try:
                answer = handler(request) or {}
                status = answer.pop("status", STATUS_OK)
                summary = answer.pop("summary", "")
                detail = answer.get("detail", answer)
            except Exception as exc:  # noqa: BLE001 - published, never raised
                status, summary, detail = STATUS_ERROR, str(exc)[:300], {}
            result = {
                "schema": SCHEMA_RESULT,
                "id": job_id,
                "kind": request.get("kind", "unknown"),
                "status": status,
                "summary": summary,
                "detail": detail,
                "note": request.get("note", ""),
                "requested_by": request.get("from", "peer"),
                "peer": entry,
                "worker": worker,
                "seconds": round(time.time() - started, 2),
                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00", time.gmtime(time.time() + 8 * 3600)),
            }
            adds["outbox/%s.json" % job_id] = json.dumps(result, ensure_ascii=False,
                                                         indent=2).encode("utf-8")
            answered.add(job_id)
            results.append(result)
            budget -= 1
        if adds:
            push_files(desk_repo, ref, adds, [],
                       "mailbox: %d peer answer(s) from %s" % (len(adds), worker), remote=remote)
    return results


def snapshot(repo: str, ref: str = DEFAULT_REF, remote: str = "origin") -> Dict[str, Any]:
    commit = fetch_ref(repo, ref, remote)
    pending = [os.path.basename(path)[:-5] for path in list_files(repo, commit, "inbox")
               if path.endswith(".json")]
    done = [os.path.basename(path)[:-5] for path in list_files(repo, commit, "outbox")
            if path.endswith(".json")]
    return {"ref": ref, "tip": commit, "pending": sorted(pending), "done": sorted(done)}


# ---------------------------------------------------------------------------
# worker side (the desk uses PowerShell; this keeps the protocol testable and
# lets any machine with Python serve jobs too)
# ---------------------------------------------------------------------------
def serve_once(repo: str, handler, ref: str = DEFAULT_REF, remote: str = "origin",
               max_jobs: int = 1, worker: str = "python") -> List[Dict[str, Any]]:
    """Claim up to ``max_jobs`` queued requests, answer them, publish results.

    ``handler(request) -> dict`` must return at least ``status`` and ``summary``;
    anything else it returns is published as the result ``detail``.
    A crashing handler becomes a published ``error`` result, never a lost job.
    """
    commit = fetch_ref(repo, ref, remote)
    if not commit:
        return []
    seen: List[Dict[str, Any]] = []
    inbox = sorted(path for path in list_files(repo, commit, "inbox") if path.endswith(".json"))
    for path in inbox[:max_jobs]:
        raw = read_file(repo, commit, path)
        if raw is None:
            continue
        try:
            request = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            request = {"id": os.path.basename(path)[:-5], "kind": "unknown", "args": {}}
        job_id = request.get("id") or os.path.basename(path)[:-5]
        started = time.time()
        try:
            answer = handler(request) or {}
            status = answer.pop("status", STATUS_OK)
            summary = answer.pop("summary", "")
            # a handler may return an explicit detail block; otherwise whatever
            # else it returned becomes the detail
            detail = answer.get("detail", answer)
        except Exception as exc:  # noqa: BLE001 - published, never raised
            status, summary, detail = STATUS_ERROR, str(exc)[:300], {}
        result = {
            "schema": SCHEMA_RESULT,
            "id": job_id,
            "kind": request.get("kind", "unknown"),
            "status": status,
            "summary": summary,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(started)),
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "seconds": round(time.time() - started, 2),
            "worker": worker,
            "detail": detail,
        }
        body = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        push_files(repo, ref, {"outbox/%s.json" % job_id: body}, [path],
                   "mailbox: result %s (%s)" % (job_id, result["kind"]), remote=remote)
        seen.append(result)
    return seen


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _print(payload: Any) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _load_status(repo: str) -> Dict[str, Any]:
    """Best-effort read of the desk-published status files (never raises)."""
    out: Dict[str, Any] = {}
    for name, rel in STATUS_FILES.items():
        path = os.path.join(repo, rel.replace("/", os.sep))
        try:
            with open(path, "r", encoding="utf-8-sig") as fh:
                out[name] = json.load(fh)
        except Exception as exc:  # noqa: BLE001 - a missing file is normal
            out[name] = {"_error": "%s: %s" % (type(exc).__name__, exc)}
    return out


def _age_minutes(stamp: Any) -> Optional[float]:
    text = str(stamp or "").strip()
    if not text:
        return None
    normalised = text.replace("Z", "+00:00")
    try:
        parsed = datetime.datetime.fromisoformat(normalised)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return round((datetime.datetime.now(datetime.timezone.utc) - parsed).total_seconds() / 60.0, 1)


def capabilities(repo: str, ref: str = DEFAULT_REF) -> Dict[str, Any]:
    """A self-orienting card for a session that has just cloned the repo.

    Reads only what is committed, so it works offline and costs no git push.
    """
    status = _load_status(repo)
    heartbeat = status.get("heartbeat") or {}
    selfcheck = status.get("selfcheck") or {}
    smoke = status.get("smoke") or {}
    mailbox = status.get("mailbox") or {}

    versions = selfcheck.get("versions") or {}
    host = selfcheck.get("host") or {}
    gpus = versions.get("gpus") or (smoke.get("software") or {}).get("gpus") or []
    gmx_version = versions.get("gromacs") or (smoke.get("software") or {}).get("gromacs", {}).get("version")
    age = _age_minutes(heartbeat.get("at"))
    desk_alive = isinstance(age, (int, float)) and age <= 120

    return {
        "schema": "cgmd.hub.capabilities.v1",
        "repo": "hukeying85-ux/0fuye",
        "branch": "arena/32cd826e-0fuye",
        "mailbox_ref": ref,
        "entry_command": "python3 -m core.hub_mailbox",
        "desk": {
            "host": heartbeat.get("host") or host.get("computer"),
            "state": heartbeat.get("state"),
            "heartbeat_at": heartbeat.get("at"),
            "heartbeat_age_min": age,
            "alive": desk_alive,
            "interval_s": heartbeat.get("interval_s"),
            "branch": heartbeat.get("branch"),
            "head": heartbeat.get("head"),
            "gromacs": gmx_version,
            "gpu": (gpus[0] if gpus and isinstance(gpus[0], str) else
                    ((gpus[0] or {}).get("name") if gpus and isinstance(gpus[0], dict) else None)),
            "gpus": len(gpus) if isinstance(gpus, list) else 0,
        },
        "selfcheck": {
            "overall": selfcheck.get("overall"),
            "checked_at": selfcheck.get("checked_at"),
            "counts": selfcheck.get("summary"),
        },
        "smoke": {
            "status": smoke.get("status"),
            "generated_at": smoke.get("generated_at"),
            "ps_completed": smoke.get("ps_completed"),
            "ns_per_day": (smoke.get("mdrun") or {}).get("performance_ns_per_day"),
            "accelerator": smoke.get("accelerator"),
        },
        "mailbox": {
            "state": mailbox.get("state"),
            "queued": mailbox.get("queued"),
            "last_jobs": mailbox.get("last_jobs"),
        },
        "jobs": dict(JOB_HELP),
        "first_steps": [
            "python3 -m core.hub_mailbox run --kind ping --timeout 300",
            "python3 -m core.hub_mailbox run --kind smoke --json-args '{\"ps\": 100}' --timeout 1800",
        ],
        "if_broken": [
            "python3 -m core.hub_mailbox run --kind deskdiag --timeout 600",
            "python3 -m core.hub_mailbox run --kind deskfix --timeout 600",
            "python3 -m core.hub_mailbox run --kind sync --json-args '{\"desk\": true}' --timeout 900",
            "python3 -m core.hub_mailbox run --kind selfcheck --timeout 900",
        ],
        "cross_repo": {
            "why": "an Arena session token only writes the repository the session lives in (403 everywhere else)",
            "recipe": [
                "git clone https://github.com/hukeying85-ux/0fuye.git /tmp/desk",
                "python3 -m core.hub_mailbox --repo <your checkout> run --kind ping --read-repo /tmp/desk",
            ],
            "requires": "your repository is listed in the desk's peer_repos (set it with --kind deskfix)",
        },
        "rules": [
            "never ask the user to paste a command; every desk action goes through this mailbox",
            "outside this repo you can only push your own mailbox: queue there, read the answer with --read-repo",
            "never commit or push from the calling session; jobs live on the mailbox ref",
            "this sandbox reaches github.com only - do not try the LAN bridge from here",
            "the desk has no E: drive; the panel is Arena Desk on 127.0.0.1:18765",
            "a job that returns timeout usually means the desk worker stopped - say so plainly",
        ],
        "user_action_required": False,
    }


def _summarise(result: Dict[str, Any]) -> str:
    return "%s %s: %s" % (result.get("kind", "?"), result.get("status", "?"),
                          result.get("summary", ""))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m core.hub_mailbox",
                                     description="queue work for the CGMD desktop through git")
    parser.add_argument("--repo", default=".", help="path inside the checkout (default: .)")
    parser.add_argument("--ref", default=DEFAULT_REF, help="mailbox branch (default: %s)" % DEFAULT_REF)
    parser.add_argument("--remote", default="origin")
    sub = parser.add_subparsers(dest="command")

    send_p = sub.add_parser("send", help="queue a job")
    send_p.add_argument("--kind", required=True, choices=KINDS)
    send_p.add_argument("--arg", action="append", default=[], help="gmx/shell argv word")
    send_p.add_argument("--json-args", default="{}", help="raw JSON object for args")
    send_p.add_argument("--note", default="")
    send_p.add_argument("--timeout", type=int, default=1800)
    send_p.add_argument("--wait", action="store_true", help="wait for the result after sending")

    wait_p = sub.add_parser("wait", help="wait for one job id")
    wait_p.add_argument("id")
    wait_p.add_argument("--timeout", type=int, default=1800)
    wait_p.add_argument("--interval", type=int, default=15)
    wait_p.add_argument("--read-repo", default="",
                        help="look the answer up here instead (a clone of the desk repo)")

    run_p = sub.add_parser("run", help="send and wait")
    run_p.add_argument("--kind", required=True, choices=KINDS)
    run_p.add_argument("--arg", action="append", default=[])
    run_p.add_argument("--json-args", default="{}")
    run_p.add_argument("--note", default="")
    run_p.add_argument("--timeout", type=int, default=1800)
    run_p.add_argument("--interval", type=int, default=15)
    run_p.add_argument("--read-repo", default="",
                       help="queue from this repo but read the answer from the desk repo")

    sub.add_parser("ls", help="list queued and answered jobs")
    sub.add_parser("caps", help="what can this desk do? (offline capability card)")

    show_p = sub.add_parser("show", help="print one result")
    show_p.add_argument("id")
    show_p.add_argument("--read-repo", default="", help="read the answer from this clone instead")

    args = parser.parse_args(argv)
    repo = repo_root(os.path.abspath(args.repo))
    read_repo = repo
    asked = getattr(args, "read_repo", "") or ""
    if asked:
        read_repo = repo_root(os.path.abspath(asked))

    if args.command == "send":
        payload = json.loads(args.json_args) if args.json_args else {}
        if args.arg:
            payload = dict(payload, argv=list(args.arg))
        job_id = send(repo, args.kind, payload, note=args.note, ref=args.ref,
                      timeout_s=args.timeout, remote=args.remote)
        if not args.wait:
            _print({"id": job_id, "ref": args.ref,
                    "next": "python3 -m core.hub_mailbox wait %s" % job_id})
            return 0
        result = wait(repo, job_id, ref=args.ref, timeout=args.timeout, remote=args.remote)
        _print(result)
        return 0 if result.get("status") == STATUS_OK else 6

    if args.command == "wait":
        result = wait(read_repo, args.id, ref=args.ref, timeout=args.timeout,
                      interval=args.interval, remote=args.remote)
        _print(result)
        return 0 if result.get("status") == STATUS_OK else 6

    if args.command == "run":
        payload = json.loads(args.json_args) if args.json_args else {}
        if args.arg:
            payload = dict(payload, argv=list(args.arg))
        job_id = send(repo, args.kind, payload, note=args.note, ref=args.ref,
                      timeout_s=args.timeout, remote=args.remote)
        sys.stderr.write("mailbox: queued %s as %s\n" % (args.kind, job_id))
        result = wait(read_repo, job_id, ref=args.ref, timeout=args.timeout,
                      interval=args.interval, remote=args.remote)
        _print(result)
        return 0 if result.get("status") == STATUS_OK else 6

    if args.command == "caps":
        _print(capabilities(repo, ref=args.ref))
        return 0

    if args.command == "ls":
        _print(snapshot(repo, ref=args.ref, remote=args.remote))
        return 0

    if args.command == "show":
        result = read_result(read_repo, args.id, ref=args.ref, remote=args.remote)
        if result is None:
            _print({"id": args.id, "status": STATUS_LOST,
                    "summary": "no result on %s yet" % args.ref})
            return 6
        _print(result)
        return 0 if result.get("status") == STATUS_OK else 6

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
