#!/usr/bin/env python3
"""Q-005: how regular are the STEP files, and do we need a full CAD kernel?

The BRep is the only real geometric input available at inference, so reading it
is unavoidable. The question is *how*. A full kernel (cadquery-ocp / OCP, ~400 MB)
is the general answer, but these parts are prismatic blocks carrying only
pockets, holes and chamfers -- if the STEP contains nothing but planes and
cylinders, the features can be lifted straight out of the entity table.

This counts entity types across a sample and reports the surface-type mix, which
decides the toolchain.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from machineplan.parsing.dataset import MachinePlanDataset  # noqa: E402

DEFAULT_ARCHIVE = pathlib.Path(__file__).resolve().parents[1] / "data" / "MachinePlan-10K.zip"

# "#123=CYLINDRICAL_SURFACE('',#45,9.4);"
_ENTITY_RE = re.compile(r"^#(\d+)\s*=\s*([A-Z_0-9]+)\s*\(", re.MULTILINE)
_CYLINDER_RE = re.compile(r"#(\d+)\s*=\s*CYLINDRICAL_SURFACE\s*\(\s*'[^']*'\s*,\s*#(\d+)\s*,\s*([-\d.Ee+]+)\s*\)")
_AXIS2_RE = re.compile(
    r"#(\d+)\s*=\s*AXIS2_PLACEMENT_3D\s*\(\s*'[^']*'\s*,\s*#(\d+)\s*,\s*#(\d+)\s*,\s*#(\d+)\s*\)"
)
_POINT_RE = re.compile(
    r"#(\d+)\s*=\s*CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(\s*([-\d.Ee+]+)\s*,\s*([-\d.Ee+]+)\s*,\s*([-\d.Ee+]+)\s*\)\s*\)"
)
_DIRECTION_RE = re.compile(
    r"#(\d+)\s*=\s*DIRECTION\s*\(\s*'[^']*'\s*,\s*\(\s*([-\d.Ee+]+)\s*,\s*([-\d.Ee+]+)\s*,\s*([-\d.Ee+]+)\s*\)\s*\)"
)

SURFACE_TYPES = {
    "PLANE", "CYLINDRICAL_SURFACE", "CONICAL_SURFACE", "SPHERICAL_SURFACE",
    "TOROIDAL_SURFACE", "B_SPLINE_SURFACE_WITH_KNOTS", "SURFACE_OF_REVOLUTION",
    "SURFACE_OF_LINEAR_EXTRUSION", "RATIONAL_B_SPLINE_SURFACE",
}
CURVE_TYPES = {"LINE", "CIRCLE", "ELLIPSE", "B_SPLINE_CURVE_WITH_KNOTS", "RATIONAL_B_SPLINE_CURVE"}


def extract_cylinders(text: str) -> list[tuple[float, tuple[float, float, float], tuple[float, float, float]]]:
    """Return (radius, origin, axis_direction) for every cylindrical surface."""
    points = {
        int(m.group(1)): (float(m.group(2)), float(m.group(3)), float(m.group(4)))
        for m in _POINT_RE.finditer(text)
    }
    directions = {
        int(m.group(1)): (float(m.group(2)), float(m.group(3)), float(m.group(4)))
        for m in _DIRECTION_RE.finditer(text)
    }
    placements = {
        int(m.group(1)): (int(m.group(2)), int(m.group(3)), int(m.group(4)))
        for m in _AXIS2_RE.finditer(text)
    }

    results = []
    for match in _CYLINDER_RE.finditer(text):
        placement_id = int(match.group(2))
        radius = float(match.group(3))
        placement = placements.get(placement_id)
        if not placement:
            continue
        origin = points.get(placement[0])
        axis = directions.get(placement[1])
        if origin is None or axis is None:
            continue
        results.append((radius, origin, axis))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=pathlib.Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--limit", type=int, default=40, help="parts to scan")
    arguments = parser.parse_args()

    entity_counts: collections.Counter[str] = collections.Counter()
    surface_counts: collections.Counter[str] = collections.Counter()
    curve_counts: collections.Counter[str] = collections.Counter()
    unknown_surfaces: collections.Counter[str] = collections.Counter()
    sizes: list[int] = []

    with MachinePlanDataset(arguments.archive) as dataset:
        parts = list(dataset)[: arguments.limit]
        print(f"scanning {len(parts)} STEP files...\n")

        first_detail = None
        for part in parts:
            if not part.brep:
                continue
            text = dataset.read_text(part.brep)
            sizes.append(len(text))
            for match in _ENTITY_RE.finditer(text):
                name = match.group(2)
                entity_counts[name] += 1
                if name in SURFACE_TYPES:
                    surface_counts[name] += 1
                elif name in CURVE_TYPES:
                    curve_counts[name] += 1
                elif name.endswith("_SURFACE"):
                    unknown_surfaces[name] += 1

            if first_detail is None:
                cylinders = extract_cylinders(text)
                first_detail = (part.part_id, cylinders)

    rule = "=" * 78
    print(rule)
    print(f"{len(sizes)} parts, mean STEP size {sum(sizes) / max(len(sizes), 1) / 1024:.1f} KB")
    print(rule)

    print("\n--- SURFACE types (this decides the toolchain) ---")
    total_surfaces = sum(surface_counts.values())
    for name, count in surface_counts.most_common():
        print(f"  {name:38} {count:7,}  {count / total_surfaces * 100:6.2f}%")
    if unknown_surfaces:
        print("  unexpected surface types:")
        for name, count in unknown_surfaces.most_common():
            print(f"     {name:35} {count:7,}")
    else:
        print("  (no surface types outside the expected set)")

    print("\n--- CURVE types ---")
    total_curves = sum(curve_counts.values())
    for name, count in curve_counts.most_common():
        print(f"  {name:38} {count:7,}  {count / max(total_curves, 1) * 100:6.2f}%")

    print("\n--- top entity types overall ---")
    for name, count in entity_counts.most_common(15):
        print(f"  {name:38} {count:7,}")

    if first_detail:
        part_id, cylinders = first_detail
        print(f"\n--- cylindrical surfaces in {part_id} (candidate holes) ---")
        grouped: collections.Counter[tuple[float, float, float]] = collections.Counter()
        for radius, origin, axis in cylinders:
            grouped[(round(radius, 3), round(origin[0], 2), round(origin[1], 2))] += 1
        print(f"  {len(cylinders)} cylindrical faces, "
              f"{len(grouped)} distinct (radius, x, y) triples")
        for (radius, x, y), count in sorted(grouped.items()):
            print(f"     r={radius:8.3f}  d={radius * 2:8.3f}  at ({x:8.2f},{y:8.2f})  x{count}")
        axes = collections.Counter(
            tuple(round(a, 3) for a in axis) for _, _, axis in cylinders
        )
        print(f"  axis directions: {dict(axes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
