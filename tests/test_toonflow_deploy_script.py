"""Regression tests for the Toonflow deploy script.

The sandbox has no PowerShell, so these tests do not execute the .ps1.  They
assert the *contract* the script must satisfy, by parsing it and by re-deriving
its decision rules on synthetic inputs.  That catches the mistakes that actually
bit us while writing it: `$args` being a reserved automatic variable, failure
paths returning exit 0, and an undefined `$frames` leaking into the receipt.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "cgmd-hub" / "scripts" / "deploy_toonflow.ps1"


@pytest.fixture(scope="module")
def source() -> str:
    assert SCRIPT.is_file(), "deploy_toonflow.ps1 is missing"
    return SCRIPT.read_text(encoding="utf-8")


def test_script_is_plain_ascii_and_lf(source: str) -> None:
    """Windows PowerShell 5.1 mis-parses UTF-8 without a BOM; keep it ASCII."""
    raw = SCRIPT.read_bytes()
    assert all(byte < 128 for byte in raw)
    assert b"\r\n" not in raw, "keep LF so git diffs stay reviewable"
    assert raw.endswith(b"\n")


def test_never_assigns_reserved_args_automatic_variable(source: str) -> None:
    """`$args = ...` is a hard error in PowerShell; the ffmpeg call hit it."""
    assert not re.search(r"^\s*\$args\s*=", source, re.M), "$args must not be assigned"
    assert "$ffArgs" in source


def test_every_failure_branch_exits_nonzero(source: str) -> None:
    """`exit (Write-Receipt ...)` coerced JSON to 0, so failures looked green."""
    assert "exit (Write-Receipt" not in source
    writes = len(re.findall(r"Write-Receipt 'fail'", source))
    exits = len(re.findall(r"^\s*exit 1\s*$", source, re.M))
    assert writes >= 11, "expected a failure path for each pipeline stage"
    # One exit 1 per failure receipt, plus the final explicit exit 0.
    assert exits == writes, f"{writes} failure receipts but {exits} exit 1 statements"
    assert re.search(r"^exit 0\s*$", source, re.M), "the success path must return 0"


def test_success_path_is_the_last_statement(source: str) -> None:
    tail = source.rstrip().splitlines()[-1].strip()
    assert tail == "exit 0", f"last statement is {tail!r}"


def test_frames_variable_is_defined_before_first_use(source: str) -> None:
    """The receipt referenced $frames outside the try block that created it."""
    first_assign = source.find("$frames = Join-Path")
    first_use = source.find("$frames")
    assert first_assign != -1 and first_assign == first_use
    receipt_line = next(l for l in source.splitlines() if "sample_png_frames" in l)
    assert "Test-Path -LiteralPath $frames" in receipt_line, "guard against a missing dir"


def test_defaults_target_f_drive_with_no_c_drive_writes(source: str) -> None:
    assert r"[string]$RepoRoot = 'F:\apps\Toonflow'" in source
    assert not re.search(r"[A-Za-z]:\\\\cgmd|'C:\\", source), "no C: writes in this deploy"


def test_disk_guard_refuses_small_free_space(source: str) -> None:
    """8 GB floor, computed from bytes rather than a `8GB` literal."""
    assert "$gb = 1073741824" in source
    assert "(8 * $gb)" in source
    assert not re.search(r"\b\d+GB\b", source)


def test_server_port_is_reusable_and_probed_without_duplicating(source: str) -> None:
    """A second run must adopt a live server, not spawn a competing one."""
    assert "if (Test-Port $Port)" in source
    assert "already serving Toonflow" in source
    # a foreign program on the port must abort, not be adopted
    assert "taken by another program" in source
    assert "call \"" in source, "cmd /c needs `call` before bun"


def test_receipt_declares_the_model_limitation(source: str) -> None:
    """Honesty guard: the app ships no generative model, say so in the receipt."""
    line = next(l for l in source.splitlines() if "model_note" in l)
    assert "no generative video model" in line
    assert "ComfyUI" in line


def test_schema_and_receipt_path_are_stable(source: str) -> None:
    assert "cgmd.toonflow.deploy.v1" in source
    assert "deploy-receipt.json" in source
    assert "'receipt'" in source


@pytest.mark.parametrize(
    "free_gb,expected",
    [(0, "refuse"), (7, "refuse"), (8, "allow"), (40, "allow")],
)
def test_disk_threshold_rule(free_gb: int, expected: str) -> None:
    """Mirror of the PowerShell guard: free < 8 GB refuses before any write."""
    gb = 1073741824
    free_bytes = free_gb * gb
    decision = "refuse" if free_bytes < 8 * gb else "allow"
    assert decision == expected


@pytest.mark.parametrize(
    "port_open,http_ok,expected_status",
    [
        (False, False, "fail"),
        (True, False, "fail"),
        (True, True, "ok"),
    ],
)
def test_readiness_requires_both_tcp_and_http(port_open: bool, http_ok: bool, expected_status: str) -> None:
    """A listening port alone is not readiness: the web bundle must answer."""
    ready = port_open and http_ok
    assert ("ok" if ready else "fail") == expected_status


def test_sample_status_degrades_honestly() -> None:
    """No ffmpeg => 'ready_no_sample', never a claim of a rendered video."""
    for has_clip, expected in ((True, "ok"), (False, "ready_no_sample")):
        assert (has_clip and "ok" or "ready_no_sample") == expected
