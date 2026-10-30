"""JobBeacon: Scientific & Long-Running Task Beacon with Mobile PWA Companion.

Licensed under the Apache License, Version 2.0.
100% original clean-room implementation using Python standard library.
"""

from __future__ import annotations

__version__ = "0.2.0"
__license__ = "Apache-2.0"

from .analyzers import analyze_dl_or_bio_log, analyze_md_log, analyze_slurm_table
from .ledger import BeaconLedger
from .notifiers import dispatch_alert
from .tunnels import build_connectivity_plan, generate_pairing_ticket, render_qr_svg

__all__ = [
    "__version__",
    "__license__",
    "BeaconLedger",
    "analyze_dl_or_bio_log",
    "analyze_md_log",
    "analyze_slurm_table",
    "build_connectivity_plan",
    "dispatch_alert",
    "generate_pairing_ticket",
    "render_qr_svg",
]
