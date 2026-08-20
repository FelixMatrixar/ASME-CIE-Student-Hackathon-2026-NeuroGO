#!/usr/bin/env python3
"""Extract a training table of (pocket geometry -> operation count).

F-041 left pocket counting unsolved: after F-040 removed all over-counting the
residual is *pure* under-counting -- 1.39 true `FLOOR_WALL` operations per
recognised floor -- and neither depth (0.263 vs 0.289) nor footprint
(13,931 vs 15,325 mm^2) separates the pockets that need a second operation.

F-047 showed that "no hand-findable separator" is a statement about hand-tuning,
not about the data. This builds the table to test the same idea for pockets.

**Matching.** A pocket operation sweeps an area rather than a point, so it is
attributed to a floor by *depth* first -- the lowest Z the tool reaches should sit
on the floor it is cutting -- and by XY overlap second. Operations that match no
floor are counted separately, since they represent pockets we failed to recognise
at all, which is a different failure from mis-counting the ones we did.
"""

from __future__ import annotations

import argparse
import collections
import csv
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from machineplan.features import extract_features  # noqa: E402
from machineplan.parsing.dataset import MachinePlanDataset  # noqa: E402
from machineplan.parsing.ptp import parse_ptp  # noqa: E402
from machineplan.parsing.step import parse_step  # noqa: E402

SOLUTION = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = SOLUTION / "data" / "MachinePlan-10K.zip"
DEFAULT_OUT = SOLUTION / "data" / "pocket_counts.csv"
HEAD_BYTES = 400
Z_TOLERANCE_MM = 2.0

_SUB = re.compile(r"^Template Subtype:\s*(.+?)\s*$", re.MULTILINE)

FIELDS = [
    "part_id", "length_mm", "width_mm", "footprint_mm2", "depth_mm",
    "depth_fraction", "corner_radius", "reach_ratio", "touches", "n_floors",
    "is_nested", "aspect", "stock_height", "n_ops",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=pathlib.Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=2500)
    arguments = parser.parse_args()

    rows: list[dict] = []
    counts: collections.Counter[int] = collections.Counter()
    unmatched_ops = 0
    total_ops = 0

    with MachinePlanDataset(arguments.archive) as dataset:
        parts = list(dataset)[: arguments.limit]
        print(f"extracting from {len(parts)} parts...")

        for number, part in enumerate(parts, start=1):
            if number % 250 == 0:
                print(f"  {number}/{len(parts)}  {len(rows)} floors")
            if not part.brep:
                continue
            try:
                features = extract_features(parse_step(dataset.read_text(part.brep)))
            except Exception:  # noqa: BLE001
                continue
            if not features.pocket_floors:
                continue

            # Every FLOOR_WALL operation, with the lowest Z its tool reaches.
            operations: list[tuple[float, float, float]] = []
            for index in sorted(part.operations):
                operation = part.operations[index]
                if not operation.details or not operation.tool_path:
                    continue
                with dataset.open(operation.details) as handle:
                    head = handle.read(HEAD_BYTES).decode("utf-8", errors="replace")
                match = _SUB.search(head)
                if not match or match.group(1) != "FLOOR_WALL":
                    continue
                try:
                    path = parse_ptp(dataset.read_text(operation.tool_path))
                except Exception:  # noqa: BLE001
                    continue
                cutting = path.cutting_moves
                if not cutting:
                    continue
                low_z = min(move.end[2] for move in cutting)
                mid_x = sum(move.end[0] for move in cutting) / len(cutting)
                mid_y = sum(move.end[1] for move in cutting) / len(cutting)
                operations.append((low_z, mid_x, mid_y))
            total_ops += len(operations)

            per_floor: collections.Counter[int] = collections.Counter()
            for low_z, mid_x, mid_y in operations:
                best, best_score = None, None
                for floor_index, floor in enumerate(features.pocket_floors):
                    depth_gap = abs(floor.z - low_z)
                    if depth_gap > Z_TOLERANCE_MM:
                        continue
                    inside = (
                        floor.x_min - 2.0 <= mid_x <= floor.x_max + 2.0
                        and floor.y_min - 2.0 <= mid_y <= floor.y_max + 2.0
                    )
                    score = depth_gap + (0.0 if inside else 5.0)
                    if best_score is None or score < best_score:
                        best, best_score = floor_index, score
                if best is None:
                    unmatched_ops += 1
                else:
                    per_floor[best] += 1

            top = features.stock_high[2]
            height = features.stock_height
            for floor_index, floor in enumerate(features.pocket_floors):
                n_ops = per_floor.get(floor_index, 0)
                counts[n_ops] += 1
                radius = features.corner_radius_for(floor)
                nested = any(
                    other.z > floor.z + 1e-3
                    and other.x_min <= floor.x_min + 1.0
                    and other.x_max >= floor.x_max - 1.0
                    and other.y_min <= floor.y_min + 1.0
                    and other.y_max >= floor.y_max - 1.0
                    for other in features.pocket_floors
                )
                longer = max(floor.length_mm, floor.width_mm)
                shorter = max(min(floor.length_mm, floor.width_mm), 1e-6)
                rows.append(
                    {
                        "part_id": part.part_id,
                        "length_mm": round(floor.length_mm, 3),
                        "width_mm": round(floor.width_mm, 3),
                        "footprint_mm2": round(floor.footprint_mm2, 2),
                        "depth_mm": round(top - floor.z, 3),
                        "depth_fraction": round((top - floor.z) / height, 4) if height else 0.0,
                        "corner_radius": round(radius, 3),
                        "reach_ratio": round(features.reach_ratio_for(floor), 4),
                        "touches": floor.touches_boundary(features.stock_low, features.stock_high),
                        "n_floors": len(features.pocket_floors),
                        "is_nested": int(nested),
                        "aspect": round(longer / shorter, 4),
                        "stock_height": round(height, 3),
                        "n_ops": n_ops,
                    }
                )

    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    with open(arguments.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nwrote {len(rows):,} floors -> {arguments.out}")
    print(f"operations: {total_ops:,} total, {unmatched_ops:,} matched no floor "
          f"({unmatched_ops / max(total_ops, 1) * 100:.1f}%)")
    print("\noperations attributed per recognised floor:")
    for value in sorted(counts):
        share = counts[value] / len(rows) * 100
        print(f"  {value} ops: {counts[value]:6,}  {share:5.1f}%  {'#' * min(counts[value] // 20, 55)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
