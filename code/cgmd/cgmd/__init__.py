"""CGMD-Engine: Martini 3 coarse-grained antimicrobial-peptide pipeline.

The package turns

    (peptide sequence | PDB)  ->  Martini 3 topology  ->  POPE:POPG 3:1 bilayer
    ->  GPU energy minimisation / 20 ns equilibration / microsecond production
    ->  ``summary_metrics.json`` (< 1 MB) + vector figures

and is driven from the repository root by ``python -m cgmd.cli`` (see
``code/cgmd/README.md``).  Heavy trajectory files never leave the workstation;
only reduced metrics and SVG/PNG figures are pushed back to git.
"""

from __future__ import annotations

__all__ = ["__version__"]
__version__ = "1.0.0"
