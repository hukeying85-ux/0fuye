"""Adjust INSANE's monovalent salt to include requested added NaCl pairs.

INSANE's positive -salt estimates total ionic strength including counterions;
for a charged membrane that can yield no co-ions. This routine interprets the
requested molarity as added salt pairs in the nominal water volume, while
retaining the existing neutralizing ions. One Martini W represents four waters.
"""
from __future__ import annotations

import random
from typing import Dict


def ensure_salt_pairs(gro_path: str, top_path: str, salt_m: float, seed: int = -1) -> Dict[str, int]:
    from .topology import parse_molecules

    entries = parse_molecules(top_path)
    waters = sum(n for name, n in entries if name == "W")
    sodium = sum(n for name, n in entries if name in ("NA", "NA+"))
    chloride = sum(n for name, n in entries if name in ("CL", "CL-"))
    with open(gro_path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    rows = lines[2:-1]
    if len(rows) != int(lines[1]):
        raise ValueError("invalid INSANE coordinates")
    counts = {name: sum(1 for row in rows if row[5:10].strip() in names) for name, names in {
        "W": ("W",), "NA": ("NA", "NA+"), "CL": ("CL", "CL-")}.items()}
    if (counts["W"], counts["NA"], counts["CL"]) != (waters, sodium, chloride):
        raise ValueError("INSANE solvent counts do not match coordinates")
    target = max(0, int(round(float(salt_m) * 4 * (waters + sodium + chloride) / 55.5)))
    extra = max(0, target - min(sodium, chloride))
    positions = [i for i, row in enumerate(rows) if row[5:10].strip() == "W"]
    if 2 * extra > len(positions):
        raise ValueError("not enough solvent to add requested NaCl")
    chosen = random.Random(seed if seed >= 0 else None).sample(positions, 2 * extra)
    picked = set(chosen)
    new_na, new_cl = [], []
    for j, i in enumerate(chosen):
        row = rows[i]
        name = "NA" if j < extra else "CL"
        ion = row[:5] + "{:<5}{:>5}".format(name, name) + row[15:]
        (new_na if j < extra else new_cl).append(ion)
    before, water_rows, na_rows, cl_rows = [], [], [], []
    for i, row in enumerate(rows):
        if i in picked:
            continue
        name = row[5:10].strip()
        if name == "W":
            water_rows.append(row)
        elif name in ("NA", "NA+", "CL", "CL-"):
            normalized = "NA" if name.startswith("NA") else "CL"
            row = row[:5] + "{:<5}{:>5}".format(normalized, normalized) + row[15:]
            (na_rows if normalized == "NA" else cl_rows).append(row)
        else:
            before.append(row)
    ordered = before + water_rows + na_rows + new_na + cl_rows + new_cl
    ordered = [row[:15] + "{:5d}".format((i + 1) % 100000) + row[20:] for i, row in enumerate(ordered)]
    with open(gro_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines[:2] + ordered + [lines[-1]]) + "\n")
    # INSANE writes [molecules] last. Preserve non-solvent entries and replace
    # the solvent block to match the new coordinate order exactly.
    with open(top_path, encoding="utf-8") as f:
        text = f.read()
    import re
    match = re.search(r"(?im)^\s*\[\s*molecules\s*\]\s*$", text)
    if not match:
        raise ValueError("INSANE topology has no molecules section")
    keep = [(name, n) for name, n in entries if name not in ("W", "NA", "NA+", "CL", "CL-")]
    keep += [("W", waters - 2 * extra), ("NA", sodium + extra), ("CL", chloride + extra)]
    with open(top_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text[:match.end()] + "\n; name number\n")
        for name, n in keep:
            if n:
                f.write("{:<16}{:>8}\n".format(name, n))
    return {"target_pairs": target, "added_pairs": extra, "water": waters - 2 * extra,
            "sodium": sodium + extra, "chloride": chloride + extra}
