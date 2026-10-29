"""Regression tests for the three things that were broken on the workstation.

1. the desk advertised a repo it is not allowed to use, and every path in it
   assumed an E: drive that the GPU box does not have;
2. the boot animation never played, because the two dsh-video-skin clips were
   never committed (the overlay sat on a black screen for 14.5 s);
3. /mobile answered 404, because the PWA directory was never committed either.

Plus: a status JSON file containing the literal ``False`` used to crash every
reader that touched it.
"""

import json
import os
import pathlib
import subprocess
import sys
import threading
import urllib.request

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PANEL = ROOT / "code" / "panel"
RUNNER = ROOT / "skills" / "cgmd-hub" / "runner"

sys.path.insert(0, str(PANEL))


# ---------------------------------------------------------------------------
# 1. no E: drive required anywhere
# ---------------------------------------------------------------------------
def test_resolver_maps_a_missing_drive_onto_a_real_one():
    import desktop_ops

    existing = str(ROOT / "README.md")
    # a path that exists verbatim must come back untouched
    assert str(desktop_ops.resolve_win_path(existing)) == existing
    # a drive this machine does not have must not raise, and must not silently
    # point at something that cannot exist
    resolved = desktop_ops.resolve_win_path(r"E:\definitely\not\here\nothing.exe")
    assert str(resolved) == r"E:\definitely\not\here\nothing.exe"
    # a legacy E: path whose tail exists on a real drive is rewritten
    rel = str(ROOT).replace("/", "\\").lstrip("\\")
    if ":" in rel:  # windows-only assertion
        candidate = desktop_ops.resolve_win_path("E:\\" + rel)
        assert pathlib.Path(str(candidate)).exists()


def test_installer_drive_defaults_to_the_app_drive():
    import desktop_ops

    source = (PANEL / "desktop_ops.py").read_text(encoding="utf-8")
    assert 'drive: str = ""' in source, "start_install must not default to E:"
    assert "drive_clean = (drive or app_drive())" in source
    assert desktop_ops.app_drive().endswith(":")


def test_catalog_probes_go_through_the_resolver():
    source = (PANEL / "desktop_ops.py").read_text(encoding="utf-8")
    assert "cp = resolve_win_path(p)" in source


def test_deploy_and_launcher_do_not_prefer_a_specific_drive():
    deploy = (PANEL / "deploy.ps1").read_text(encoding="ascii")
    assert "function Resolve-AnyDrive" in deploy
    assert "$petRoot = Resolve-AnyDrive" in deploy
    assert "Resolve-AnyDrive 'E:\\0apps\\jev-chat-windows'" in deploy

    launcher = (PANEL / "launch_panel.ps1").read_text(encoding="ascii")
    assert "elseif (Test-Path -LiteralPath 'E:\\')" not in launcher
    assert "foreach ($drv in @('C:\\', 'D:\\', 'E:\\', 'F:\\', 'G:\\'))" in launcher


def test_private_companion_dirs_are_resolved():
    source = (PANEL / "desktop_ops.py").read_text(encoding="utf-8")
    assert 'jev_dir = resolve_win_path(r"E:\\0apps\\jev-chat-windows")' in source
    assert 'vault_dir = resolve_win_path(r"E:\\0yf")' in source


# ---------------------------------------------------------------------------
# 2. the boot animation survives without the missing mp4
# ---------------------------------------------------------------------------
def test_boot_overlay_has_a_fallback_layer_and_poster():
    index = (PANEL / "index.html").read_text(encoding="utf-8")
    assert 'id="boot-fallback"' in index
    assert 'poster="/assets/boot-mascot.jpg' in index
    assert (PANEL / "assets" / "boot-mascot.jpg").is_file()

    app = (PANEL / "app.js").read_text(encoding="utf-8")
    assert "function showBootFallback" in app
    assert "showBootFallback(\"dsh_video_boot_error\")" in app
    assert "readyState === 0" in app, "a 404 that never fires onerror must still fall back"

    css = (PANEL / "style.css").read_text(encoding="utf-8")
    assert ".dsvs-boot-fallback-art" in css and "@keyframes bootMascotFloat" in css
    assert "prefers-reduced-motion" in css


def test_the_missing_clips_are_expected_not_a_crash():
    """Both <video> tags must carry a poster, since the mp4s are not shipped."""
    index = (PANEL / "index.html").read_text(encoding="utf-8")
    for vid in ("skin-video", "boot-video"):
        start = index.index('id="%s"' % vid)
        tag = index[start:index.index(">", start)]
        assert "poster=" in tag, vid


def test_desk_is_bound_to_the_locked_repository():
    """The account roster may list other logins; the *bound repo* may not.

    The brand chip, the footer and every "repo" fallback used to print
    mqgg5630-cyber/0fuye, which is a different account than the one this
    checkout is locked to.
    """
    index = (PANEL / "index.html").read_text(encoding="utf-8")
    app = (PANEL / "app.js").read_text(encoding="utf-8")
    assert "mqgg5630-cyber/0fuye" not in index
    assert 's.repo || "mqgg5630-cyber/0fuye"' not in app
    assert 'repoInfo.owner || "mqgg5630-cyber"' not in app
    assert "hukeying85-ux/0fuye" in index


# ---------------------------------------------------------------------------
# 3. /mobile works without the never-committed PWA
# ---------------------------------------------------------------------------
@pytest.fixture()
def panel_server(tmp_path):
    import server as panel_server_module

    store = panel_server_module.Store(tmp_path / "data", tmp_path / "results", tmp_path / "hub", demo=True)
    srv = panel_server_module.make_server("127.0.0.1", 0, store)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv.server_address[1]
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def _get(port, path):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=10) as response:
            return response.status, response.read()
    except Exception as exc:  # HTTPError carries the code
        return getattr(exc, "code", 0), b""


def test_mobile_companion_is_served(panel_server):
    status, body = _get(panel_server, "/mobile")
    assert status == 200
    assert b"Arena Desk" in body
    assert b"/api/state" in body


def test_mobile_manifest_and_worker_are_served(panel_server):
    status, body = _get(panel_server, "/mobile/manifest.webmanifest")
    assert status == 200
    manifest = json.loads(body.decode("utf-8"))
    assert manifest["start_url"] == "/mobile"
    assert len(manifest["icons"]) == 3

    status, body = _get(panel_server, "/mobile/sw.js")
    assert status == 200 and b"addEventListener" in body


def test_mobile_icons_reuse_the_shipped_png(panel_server):
    status, body = _get(panel_server, "/mobile/icon-192.png")
    assert status == 200
    assert body[:8] == b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# 4. a status file that is not JSON must never take the watch down
# ---------------------------------------------------------------------------
def test_every_runner_reads_status_json_defensively():
    for name in ("Invoke-CgmdPoll.ps1", "Invoke-CgmdMailbox.ps1", "Invoke-CgmdBridge.ps1",
                 "Test-CgmdHub.ps1", "Sync-Desktop.ps1", "Run-Gmx-Native.ps1", "Run-Smoke.ps1"):
        source = (RUNNER / name).read_text(encoding="ascii")
        assert "ConvertFrom-Json" in source, name
        # each file must guard the parse; a bare `return ($raw | ConvertFrom-Json)` is the bug
        assert "return ($raw | ConvertFrom-Json)\n" not in source.replace(
            "        return ($raw | ConvertFrom-Json)\n    } catch {", ""), name


def test_poller_repairs_invalid_status_files():
    source = (RUNNER / "Invoke-CgmdPoll.ps1").read_text(encoding="ascii")
    assert "function Repair-StatusFiles" in source
    assert "removing a status file that is not JSON" in source
    assert "repair: drop status files that are not JSON" in source


def test_the_selfcheck_report_is_a_real_document():
    """It may be tracked again, but only as a genuine cgmd.selfcheck.v1 object.

    The file once held the literal text ``False``, which made ConvertFrom-Json
    throw inside every reader (one mailbox job died on it).
    """
    report = ROOT / "results" / "status" / "desktop_selfcheck.json"
    if not report.exists():
        return
    text = report.read_text(encoding="utf-8").strip()
    assert text.startswith("{"), "desktop_selfcheck.json must be a JSON object, not %r" % text[:20]
    document = json.loads(text)
    assert document.get("schema") == "cgmd.selfcheck.v1"
    assert isinstance(document.get("checks"), list)


# ---------------------------------------------------------------------------
# 5. the self-check must report the engine that actually computes
# ---------------------------------------------------------------------------
def test_selfcheck_prefers_the_native_build_over_a_stale_wsl_one():
    source = (RUNNER / "Test-CgmdHub.ps1").read_text(encoding="ascii")
    assert "function Get-NativeGmxInfo" in source
    assert "GPU support:" in source
    # the native probe has to run even when WSL answers
    assert "$nativeInfo = Get-NativeGmxInfo -Exe (Find-NativeGmx)" in source
    assert "native windows" in source
    assert "gromacs_native = [string]$nativeInfo['version']" in source
    assert "gromacs_wsl    = [string]$probe['GMX_VERSION']" in source


def test_martini_deps_do_not_fail_a_workstation_that_runs_native_gromacs():
    source = (RUNNER / "Test-CgmdHub.ps1").read_text(encoding="ascii")
    assert "only the Martini pipeline needs these" in source
    assert "the native GROMACS path does not" in source
