"""Shared, dependency-free building blocks for the CGMD-Engine federation.

Modules
-------
task_contract
    The single source of truth for ``results/status/cgmd_task.json``:
    schema, validation, atomic read/write and the desktop status machine.
ntfy_beacon
    Zero-token push client for the ``ntfy.sh`` topic used by the phone.
gmx_log
    Incremental GROMACS ``.log`` parser (speed, progress, ETA, LINCS / blow-up).

Nothing in this package imports a third-party library, so it can run on the
Windows host, inside WSL2 and on the phone-side runner alike.
"""

from __future__ import annotations

__all__ = ["task_contract", "ntfy_beacon", "gmx_log"]
__version__ = "1.0.0"
