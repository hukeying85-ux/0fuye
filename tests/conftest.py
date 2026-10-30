"""Pytest configuration: make the repository importable without installation."""

from __future__ import annotations

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
CGMD_ROOT = os.path.join(REPO_ROOT, "code", "cgmd")
FEDERATION = os.path.join(REPO_ROOT, "code", "federation")

for path in (REPO_ROOT, CGMD_ROOT, FEDERATION):
    if path not in sys.path:
        sys.path.insert(0, path)

os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("CGMD_NTFY_TOPIC", "arena-beacon-95bc796a66")
