"""Parser tests for the GROMACS log scanner used by the phone beacon."""

from __future__ import annotations

import os

from core import gmx_log

HEADER = """\
Started mdrun on rank 0 Wed Oct 28 20:00:00 2026
   nsteps = 50000000
   dt = 0.02
"""

PROGRESS = """\
Step           Time
       0        0.00000
Performance:       850.000       0.101
Step           Time
 2500000    50000.00000
Performance:       980.500       0.088
"""

FINISHED = """\
Finished mdrun on rank 0 Wed Oct 28 22:00:00 2026
"""


def test_start_and_parameters():
    state = gmx_log.parse_log_text(HEADER)
    assert state.started is True
    assert state.total_steps == 50_000_000
    assert state.dt_ps == pytest_approx(0.02)


def pytest_approx(value):  # tiny helper to avoid importing pytest.approx at module import
    import pytest

    return pytest.approx(value)


def test_progress_speed_and_eta():
    state = gmx_log.parse_log_text(HEADER + PROGRESS)
    assert state.step == 2_500_000
    assert state.time_ps == 50_000.0
    assert state.ns_per_day == 980.5
    assert state.progress == 0.05
    assert state.simulated_ns == 50.0
    total = state.total_ns_resolved
    assert total == 1000.0  # 5e7 steps * 0.02 ps
    expected_eta = (1000.0 - 50.0) / 980.5 * 86400.0
    assert abs(state.eta_seconds - expected_eta) < 1e-6
    assert "h" in gmx_log.format_hours(state.eta_seconds)


def test_finished_marker():
    state = gmx_log.parse_log_text(HEADER + PROGRESS + FINISHED)
    assert state.finished is True
    assert state.is_diverged is False


def test_lincs_warning_and_blowup_detection():
    log = HEADER + PROGRESS + (
        "Step 2600000, time 52000 (ps)  LINCS WARNING\n"
        "relative constraint deviation after LINCS:\n"
        "rms 0.000512, max 0.0234 (between atoms 12 and 13)\n"
        "Fatal error:\n"
        "Too many LINCS warnings (1000)\n"
    )
    state = gmx_log.parse_log_text(log)
    assert state.lincs_warnings == 1
    assert state.divergence == "lincs"
    assert state.is_diverged is True
    assert state.errors


def test_nan_blowup_marker():
    state = gmx_log.parse_log_text(HEADER + "Step 123, time 2.46 (ps)  NaN detected\n")
    assert state.divergence in ("nan", "blowup")


def test_incremental_watcher(tmp_path):
    path = str(tmp_path / "prod.log")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(HEADER)
    watcher = gmx_log.LogWatcher(path)
    state = watcher.poll()
    assert state.total_steps == 50_000_000
    assert state.step == 0

    with open(path, "a", encoding="utf-8") as handle:
        handle.write(PROGRESS)
    state = watcher.poll()
    assert state.step == 2_500_000
    assert state.ns_per_day == 980.5

    # a truncated/replaced log restarts the parse instead of breaking
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(HEADER)
    state = watcher.poll()
    assert state.step == 0
    assert os.path.getsize(path) > 0


def test_to_dict_is_json_serialisable():
    import json

    state = gmx_log.parse_log_text(HEADER + PROGRESS)
    data = state.to_dict()
    assert json.loads(json.dumps(data))["ns_per_day"] == 980.5
    assert data["eta_human"].endswith("m") or data["eta_human"].endswith("s")
