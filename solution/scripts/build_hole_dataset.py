#!/usr/bin/env python3
"""Extract a training table of (hole geometry -> operation chain).

F-033 showed every hole in the corpus takes one of only 14 operation chains, and
F-046 recorded three hand-built rules that failed because no threshold I could
find separates the groups. That is a classification problem with 10,000 labelled
parts sitting unused, so this builds the table.

**Leakage discipline.** Only fields available at inference are recorded as
features -- everything is derived from the BRep. The chain label comes from
`details.txt`, which is a *target*, never an input (Tutorial p.3). The output
carries `part_id` so the split can be done by part: holes on one part share a
block, a feature mix and a tool set, so splitting by hole would leak.

One feature deserves a note: `top_drop` is how far a hole's mouth sits below the
stock top. A hole nested inside a pocket opens at the pocket floor, so this is a
direct measurement of the "is it inside a pocket" question that Q-013 raised and
that three hand-built rules could not answer.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
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
DEFAULT_OUT = SOLUTION / "data" / "hole_chains.csv"
HEAD_BYTES = 400
MATCH_TOLERANCE_MM = 1.0

_SUB = re.compile(r"^Template Subtype:\s*(.+?)\s*$", re.MULTILINE)
HOLE_SUBTYPES = {
    "DRILLING", "SPOT_DRILLING", "DEEP_HOLE_DRILLING", "HOLE_MILLING", "BORING_REAMING",
}

FIELDS = [
    "part_id", "diameter_mm", "depth_mm", "aspect", "through", "top_drop",
    "depth_fraction", "stock_height", "n_holes", "same_diameter_count",
    "in_pocket", "chain",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=pathlib.Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=2500)
    arguments = parser.parse_args()

    rows: list[dict] = []
    chains: collections.Counter[str] = collections.Counter()
    parts_used = 0

    with MachinePlanDataset(arguments.archive) as dataset:
        parts = list(dataset)[: arguments.limit]
        print(f"extracting from {len(parts)} parts...")

        for number, part in enumerate(parts, start=1):
            if number % 250 == 0:
                print(f"  {number}/{len(parts)}  {len(rows)} holes")
            if not part.brep:
                continue
            try:
                features = extract_features(parse_step(dataset.read_text(part.brep)))
            except Exception:  # noqa: BLE001
                continue
            if not features.holes:
                continue

            positioned: list[tuple[float, float, str, int]] = []
            for index in sorted(part.operations):
                operation = part.operations[index]
                if not operation.details or not operation.tool_path:
                    continue
                with dataset.open(operation.details) as handle:
                    head = handle.read(HEAD_BYTES).decode("utf-8", errors="replace")
                match = _SUB.search(head)
                if not match or match.group(1) not in HOLE_SUBTYPES:
                    continue
                try:
                    path = parse_ptp(dataset.read_text(operation.tool_path))
                except Exception:  # noqa: BLE001
                    continue
                cutting = path.cutting_moves
                if not cutting:
                    continue
                positioned.append(
                    (cutting[0].start[0], cutting[0].start[1], match.group(1), index)
                )

            per_hole: dict[int, list[tuple[int, str]]] = collections.defaultdict(list)
            for x, y, subtype, index in positioned:
                best, best_distance = None, MATCH_TOLERANCE_MM
                for hole_index, hole in enumerate(features.holes):
                    distance = ((hole.x - x) ** 2 + (hole.y - y) ** 2) ** 0.5
                    if distance < best_distance:
                        best, best_distance = hole_index, distance
                if best is not None:
                    per_hole[best].append((index, subtype))

            diameters = collections.Counter(round(h.diameter_mm, 2) for h in features.holes)
            top = features.stock_high[2]
            height = features.stock_height
            used = False

            for hole_index, hole in enumerate(features.holes):
                chain = per_hole.get(hole_index)
                if not chain:
                    continue
                chain.sort()
                label = "|".join(subtype for _, subtype in chain)
                chains[label] += 1
                used = True

                in_pocket = any(
                    floor.x_min - 1.0 <= hole.x <= floor.x_max + 1.0
                    and floor.y_min - 1.0 <= hole.y <= floor.y_max + 1.0
                    and floor.z > hole.bottom_z
                    for floor in features.pocket_floors
                )
                rows.append(
                    {
                        "part_id": part.part_id,
                        "diameter_mm": round(hole.diameter_mm, 4),
                        "depth_mm": round(hole.depth_mm, 4),
                        "aspect": round(hole.aspect_ratio(), 4),
                        "through": int(hole.depth_type(features.stock_low[2]) == "through"),
                        "top_drop": round(top - hole.top_z, 4),
                        "depth_fraction": round(hole.depth_mm / height, 4) if height else 0.0,
                        "stock_height": round(height, 3),
                        "n_holes": len(features.holes),
                        "same_diameter_count": diameters[round(hole.diameter_mm, 2)],
                        "in_pocket": int(in_pocket),
                        "chain": label,
                    }
                )
            if used:
                parts_used += 1

    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    with open(arguments.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nwrote {len(rows):,} holes from {parts_used:,} parts -> {arguments.out}")
    print(f"\n{len(chains)} distinct chains:")
    for label, count in chains.most_common(20):
        print(f"  {count:6,}  {count / len(rows) * 100:5.1f}%  {label}")
    (arguments.out.with_suffix(".chains.json")).write_text(
        json.dumps(dict(chains.most_common()), indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
