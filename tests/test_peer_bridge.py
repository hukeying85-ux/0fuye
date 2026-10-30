"""Safety checks for the single, public, non-sensitive peer handshake."""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PEER = "hukeying85-ux/0fuye#arena/7ed6241a-0fuye"


class PeerBridgeTests(unittest.TestCase):
    def test_single_safe_version_probe(self):
        jobs = sorted((ROOT / "inbox").glob("*.json"))
        self.assertEqual(len(jobs), 1, "No production or private-data job should be queued yet")
        job = json.loads(jobs[0].read_text(encoding="utf-8"))
        self.assertRegex(jobs[0].stem, r"^\d{8}T\d{6}-[a-f0-9]{6}$")
        self.assertEqual(job["id"], jobs[0].stem)
        self.assertEqual(job["schema"], "cgmd.mailbox.request.v1")
        self.assertEqual(job["kind"], "gmx")
        self.assertEqual(job["args"], {"argv": ["--version"]})
        raw = jobs[0].read_text(encoding="utf-8")
        self.assertNotIn("F:\\", raw)
        self.assertNotIn("token", raw.lower())

    def test_bootstrap_is_peer_only_and_never_enables_shell(self):
        text = (ROOT / "bridge" / "enable-existing-hub-peer.ps1").read_text(encoding="utf-8")
        self.assertIn(PEER, text)
        self.assertIn("$cfg.locked_repo", text)
        # Older local configs omit this key. The worker defaults it to true;
        # a real JSON false must still stop us rather than silently enabling it.
        self.assertIn("$cfg.PSObject.Properties['mailbox_enabled']", text)
        self.assertIn("$mailboxField.Value -isnot [bool]", text)
        self.assertIn("if (-not $mailboxField.Value)", text)
        self.assertNotIn("$data['mailbox_enabled']", text)
        self.assertIn("$cfg.allow_shell", text)
        # In Windows PowerShell 5.1 a bare $null binds as an empty String
        # to .NET File.Replace and fails *before* the local config is changed.
        self.assertIn("[System.Management.Automation.Language.NullString]::Value", text)
        self.assertNotIn("[IO.File]::Replace($tmp, $cfgPath, $null)", text)
        self.assertIn("$installed.peer_repos", text)
        self.assertNotRegex(text.lower(), r"\bgit\s+push\b|\bregister-scheduledtask\b")


if __name__ == "__main__":
    unittest.main()
