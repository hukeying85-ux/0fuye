"""Vector figures for the CGMD summary (SVG by default, PNG optional).

Figures are intentionally plain: no colours that need a colour bar, no
external fonts, no raster data -- so each SVG stays well below 100 kB and the
whole figure set is a few hundred kB, which keeps the git round-trip tiny.

Figure labels are ASCII only; human readable Chinese text lives in
``summary_metrics.json`` and in the push notification instead, which avoids
missing-glyph boxes on machines without CJK fonts.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence

__all__ = ["make_figures"]


def _pyplot():
    import matplotlib

    matplotlib.use("Agg")
    matplotlib.rcParams.update(
        {
            "svg.fonttype": "none",
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 7,
            "figure.autolayout": True,
            "axes.unicode_minus": False,
        }
    )
    import matplotlib.pyplot as plt  # noqa: F401

    return plt


def _save(fig, outdir: str, stem: str, formats: Sequence[str]) -> List[str]:
    paths: List[str] = []
    for extension in formats:
        path = os.path.join(outdir, "{}.{}".format(stem, extension))
        fig.savefig(path, format=extension, bbox_inches="tight")
        paths.append(path)
    return paths


def make_figures(
    metrics: Dict[str, Any],
    peptide_description: Optional[Dict[str, Any]] = None,
    outdir: str = "figures",
    formats: Sequence[str] = ("svg",),
) -> List[str]:
    """Create the summary figures and return their paths."""
    os.makedirs(outdir, exist_ok=True)
    try:
        plt = _pyplot()
    except Exception:  # pragma: no cover - matplotlib is optional
        return []

    produced: List[str] = []
    timeseries = metrics.get("timeseries", {}) or {}
    time_ns = timeseries.get("time_ns") or []
    insertion = metrics.get("membrane_insertion", {}) or {}
    order = metrics.get("lipid_order", {}) or {}
    pore = metrics.get("pore", {}) or {}
    membrane = metrics.get("membrane", {}) or {}

    # --- 1. insertion depth ------------------------------------------------
    if time_ns and timeseries.get("z_distance_nm"):
        fig, axis = plt.subplots(figsize=(5.2, 2.8))
        axis.axhspan(-0.8, 0.8, color="#d9edf7", alpha=0.7, label="membrane core")
        axis.axhspan(-1.5, -0.8, color="#f2f2f2", alpha=0.7, label="interface")
        axis.axhspan(0.8, 1.5, color="#f2f2f2", alpha=0.7)
        axis.plot(time_ns, timeseries["z_distance_nm"], color="#1f4e79", lw=1.0)
        axis.axhline(0.0, color="#555555", lw=0.6, ls=":")
        axis.set_xlabel("time (ns)")
        axis.set_ylabel("peptide depth z (nm)")
        axis.set_title(
            "Peptide insertion depth (mean {:.2f} nm)".format(insertion.get("z_distance_mean_nm") or 0.0)
        )
        axis.legend(loc="lower right", frameon=False)
        produced += _save(fig, outdir, "z_distance_vs_time", formats)
        plt.close(fig)

    # --- 2. lipid order parameters ---------------------------------------
    if time_ns and (timeseries.get("lipid_order_sn1") or timeseries.get("lipid_order_sn2")):
        fig, axis = plt.subplots(figsize=(5.2, 2.8))
        sn1 = timeseries.get("lipid_order_sn1") or []
        sn2 = timeseries.get("lipid_order_sn2") or []
        if sn1:
            axis.plot(_x_for(sn1, time_ns), sn1, color="#c0504d", lw=1.0, label="sn-1")
        if sn2:
            axis.plot(_x_for(sn2, time_ns), sn2, color="#4f81bd", lw=1.0, label="sn-2")
        axis.set_xlabel("time (ns)")
        axis.set_ylabel("order parameter S")
        axis.set_title("Martini tail order parameter (mean {:.3f})".format(order.get("mean") or 0.0))
        axis.axhline(0.0, color="#888888", lw=0.6, ls=":")
        axis.legend(frameon=False)
        produced += _save(fig, outdir, "lipid_order_vs_time", formats)
        plt.close(fig)

    # --- 3. water in the membrane core -----------------------------------
    if time_ns and timeseries.get("water_in_core"):
        fig, axis = plt.subplots(figsize=(5.2, 2.6))
        axis.plot(time_ns, timeseries["water_in_core"], color="#2e75b6", lw=1.0)
        axis.fill_between(time_ns, 0, timeseries["water_in_core"], color="#2e75b6", alpha=0.25)
        axis.set_xlabel("time (ns)")
        axis.set_ylabel("water beads in core cylinder")
        axis.set_title(
            "Pore indicator (max {}, formed: {})".format(
                pore.get("water_in_core_max"), "yes" if pore.get("pore_formed") else "no"
            )
        )
        produced += _save(fig, outdir, "water_in_core_vs_time", formats)
        plt.close(fig)

    # --- 4. peptide depth profile + helical wheel ------------------------
    profile = insertion.get("per_residue_z_nm") or []
    description = peptide_description or {}
    if profile or description:
        fig, axes = plt.subplots(1, 2, figsize=(6.4, 2.9))
        if profile:
            axes[0].bar(range(1, len(profile) + 1), profile, color="#7f7f7f", width=0.8)
            axes[0].axhline(0.0, color="#333333", lw=0.6)
            axes[0].set_xlabel("residue index")
            axes[0].set_ylabel("mean depth z (nm)")
            axes[0].set_title("Per-residue insertion")
        sequence = description.get("sequence") or ""
        if sequence:
            residues_per_turn = 3.6
            import math

            for index, residue in enumerate(sequence):
                theta = 2.0 * math.pi * index / residues_per_turn
                scale = 1.0
                axes[1].plot(
                    [scale * math.cos(theta)],
                    [scale * math.sin(theta)],
                    marker="o",
                    markersize=3 + 3 * _hydrophobicity(residue),
                    color=_hydro_colour(residue),
                )
                axes[1].annotate(
                    residue,
                    (1.12 * math.cos(theta), 1.12 * math.sin(theta)),
                    fontsize=6,
                    ha="center",
                    va="center",
                )
            axes[1].set_xlim(-1.5, 1.5)
            axes[1].set_ylim(-1.5, 1.5)
            axes[1].set_aspect("equal")
            axes[1].axis("off")
            axes[1].set_title("Helical wheel (hydrophobic = orange)")
        produced += _save(fig, outdir, "peptide_summary", formats)
        plt.close(fig)

    # --- 5. bilayer thickness -------------------------------------------
    thickness = membrane.get("thickness_series_nm") or []
    if thickness:
        fig, axis = plt.subplots(figsize=(5.2, 2.2))
        axis.plot(range(len(thickness)), thickness, color="#9bbb59", lw=1.0)
        axis.set_xlabel("frame")
        axis.set_ylabel("thickness (nm)")
        axis.set_title("Bilayer thickness (mean {:.2f} nm)".format(membrane.get("thickness_nm") or 0.0))
        produced += _save(fig, outdir, "bilayer_thickness", formats)
        plt.close(fig)

    return produced


def _x_for(series: Sequence[float], time_ns: Sequence[float]) -> Sequence[float]:
    """Match a decimated series to the time axis length."""
    if len(series) == len(time_ns):
        return time_ns
    step = max(1, int(len(time_ns) / max(1, len(series))))
    return time_ns[::step][: len(series)]


_EISENBERG = {
    "A": 0.62, "R": -2.53, "N": -0.78, "D": -0.90, "C": 0.29, "Q": -0.85,
    "E": -0.74, "G": 0.48, "H": -0.40, "I": 1.38, "L": 1.06, "K": -1.50,
    "M": 0.64, "F": 1.19, "P": 0.12, "S": -0.18, "T": -0.05, "W": 0.81,
    "Y": 0.26, "V": 1.08,
}


def _hydrophobicity(residue: str) -> float:
    return max(0.0, min(1.0, (_EISENBERG.get(residue, 0.0) + 2.6) / 4.0))


def _hydro_colour(residue: str) -> str:
    value = _EISENBERG.get(residue, 0.0)
    if value > 0.6:
        return "#c55a11"
    if value > 0.1:
        return "#f4b183"
    if value > -0.7:
        return "#8faadc"
    return "#2f5597"
