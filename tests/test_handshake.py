import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge"))
from agent_verify import HandshakeError, validate_challenge, validate_receipt  # noqa: E402

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
COMMIT = "a" * 40
NONCE = "b" * 32


def challenge():
    return {
        "version": 1,
        "kind": "desktop-handshake",
        "repo": "hukeying85-ux/0fuye",
        "branch": "arena/7ed6241a-0fuye",
        "nonce": NONCE,
        "issued_at_utc": (NOW - timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
        "expires_at_utc": (NOW + timedelta(days=6)).isoformat().replace("+00:00", "Z"),
    }


def receipt():
    return {
        "version": 1,
        "nonce": NONCE,
        "challenge_commit": COMMIT,
        "status": "received",
        "observed_at_utc": NOW.isoformat().replace("+00:00", "Z"),
    }


class HandshakeTests(unittest.TestCase):
    def test_valid_receipt(self):
        validate_receipt(challenge(), receipt(), COMMIT, NOW)

    def test_wrong_nonce_rejected(self):
        r = receipt()
        r["nonce"] = "c" * 32
        with self.assertRaises(HandshakeError):
            validate_receipt(challenge(), r, COMMIT, NOW)

    def test_wrong_commit_rejected(self):
        with self.assertRaises(HandshakeError):
            validate_receipt(challenge(), receipt(), "c" * 40, NOW)

    def test_future_and_expired_receipts_rejected(self):
        for observed in (NOW + timedelta(minutes=6), NOW + timedelta(days=7)):
            r = receipt()
            r["observed_at_utc"] = observed.isoformat().replace("+00:00", "Z")
            with self.subTest(observed=observed), self.assertRaises(HandshakeError):
                validate_receipt(challenge(), r, COMMIT, NOW)

    def test_public_receipt_has_no_other_fields(self):
        r = receipt()
        r["hostname"] = "unwanted private info"
        with self.assertRaises(HandshakeError):
            validate_receipt(challenge(), r, COMMIT, NOW)

    def test_wrong_repo_or_branch_rejected(self):
        for field, value in (("repo", "mqgg5630-cyber/leanrea"), ("branch", "main")):
            c = challenge()
            c[field] = value
            with self.subTest(field=field), self.assertRaises(HandshakeError):
                validate_challenge(c)

    def test_long_window_and_invalid_nonce_rejected(self):
        c = challenge()
        c["expires_at_utc"] = (NOW + timedelta(days=8)).isoformat().replace("+00:00", "Z")
        with self.assertRaises(HandshakeError):
            validate_challenge(c)
        c = challenge()
        c["nonce"] = "../../etc/passwd"
        with self.assertRaises(HandshakeError):
            validate_challenge(c)


if __name__ == "__main__":
    unittest.main()
