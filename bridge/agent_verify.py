#!/usr/bin/env python3
"""Check the GitHub-mediated desktop handshake receipt (no external packages).

This verifies a branch round trip, NOT that a particular physical machine ran it.
Run after fetching and fast-forwarding this branch. No network calls are made.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CHALLENGE_PATH = "bridge/challenge.json"
REPO = "hukeying85-ux/0fuye"
BRANCH = "arena/7ed6241a-0fuye"
NONCE_PATTERN = re.compile(r"[0-9a-f]{32}\Z")
SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")


class HandshakeError(ValueError):
    """An invalid challenge, receipt, or local Git state."""


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise HandshakeError("Timestamp must be a UTC ISO-8601 string ending in Z")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HandshakeError("Invalid timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise HandshakeError("Timestamp must be UTC")
    return parsed


def validate_challenge(challenge: dict[str, Any]) -> tuple[str, datetime, datetime]:
    if not isinstance(challenge, dict):
        raise HandshakeError("Challenge must be a JSON object")
    if (challenge.get("version") != 1 or challenge.get("kind") != "desktop-handshake"
            or challenge.get("repo") != REPO or challenge.get("branch") != BRANCH):
        raise HandshakeError("Wrong protocol, repository, or branch")
    nonce = challenge.get("nonce")
    if not isinstance(nonce, str) or not NONCE_PATTERN.fullmatch(nonce):
        raise HandshakeError("Invalid nonce")
    issued = _timestamp(challenge.get("issued_at_utc"))
    expires = _timestamp(challenge.get("expires_at_utc"))
    if not issued < expires <= issued + timedelta(days=7):
        raise HandshakeError("Challenge validity must be at most seven days")
    return nonce, issued, expires


def validate_receipt(
    challenge: dict[str, Any], receipt: dict[str, Any], challenge_commit: str,
    now: datetime | None = None,
) -> None:
    nonce, issued, expires = validate_challenge(challenge)
    if not isinstance(receipt, dict):
        raise HandshakeError("Receipt must be a JSON object")
    if not SHA_PATTERN.fullmatch(challenge_commit):
        raise HandshakeError("Invalid challenge commit")
    expected_fields = {
        "version", "nonce", "challenge_commit", "status", "observed_at_utc"
    }
    if set(receipt) != expected_fields:
        raise HandshakeError("Receipt contains missing or unexpected fields")
    if (receipt["version"] != 1 or receipt["nonce"] != nonce
            or receipt["challenge_commit"] != challenge_commit
            or receipt["status"] != "received"):
        raise HandshakeError("Receipt does not match this challenge")
    observed = _timestamp(receipt["observed_at_utc"])
    now = now or datetime.now(timezone.utc)
    if not issued - timedelta(minutes=5) <= observed <= expires:
        raise HandshakeError("Receipt time is outside the challenge window")
    if observed > now + timedelta(minutes=5):
        raise HandshakeError("Receipt timestamp is in the future")


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise HandshakeError("Git check failed: " + " ".join(args))
    return result.stdout.strip()


def main() -> int:
    try:
        if _git("symbolic-ref", "--short", "HEAD") != BRANCH:
            raise HandshakeError("Not on the session branch")
        challenge = json.loads((ROOT / CHALLENGE_PATH).read_text(encoding="utf-8"))
        if _git("status", "--porcelain", "--", CHALLENGE_PATH):
            raise HandshakeError("Challenge has local uncommitted changes")
        nonce, _, expires = validate_challenge(challenge)
        challenge_commit = _git("log", "-1", "--format=%H", "--", CHALLENGE_PATH)
        if not SHA_PATTERN.fullmatch(challenge_commit):
            raise HandshakeError("Challenge is not committed")
        relative_receipt = f"bridge/receipts/{nonce}.json"
        receipt_path = ROOT / relative_receipt
        if not receipt_path.is_file():
            if datetime.now(timezone.utc) > expires:
                raise HandshakeError("Challenge expired without a receipt; rotate it")
            print("WAITING: no desktop receipt on this branch yet")
            return 2
        if _git("status", "--porcelain", "--", relative_receipt):
            raise HandshakeError("Receipt has local uncommitted changes")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        validate_receipt(challenge, receipt, challenge_commit)
        receipt_commit = _git("log", "-1", "--format=%H", "--", relative_receipt)
        if not SHA_PATTERN.fullmatch(receipt_commit):
            raise HandshakeError("Receipt is not committed")
        _git("merge-base", "--is-ancestor", receipt_commit, f"refs/remotes/origin/{BRANCH}")
        print(f"VERIFIED: receipt in origin/{BRANCH} at {receipt['observed_at_utc']}")
        print("Proof: GitHub branch round trip only; device identity is not authenticated.")
        return 0
    except (HandshakeError, OSError, json.JSONDecodeError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
