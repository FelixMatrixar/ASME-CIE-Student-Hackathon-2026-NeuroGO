#!/usr/bin/env python3
"""Why is FLOOR_WALL wrong on 58% of parts when its net error is ~zero?

Net +0.05 per part against an absolute error of 0.88 means pocket recognition
over-counts as often as it under-counts -- a noise problem, not a bias one, and
invisible in aggregate statistics.

Compares recognised pocket floors against true FLOOR_WALL operations per part and
groups the failures, so the dominant failure mode is visible rather than guessed.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from machineplan.features import extract_features  # noqa: E402
from machineplan.parsing.dataset import MachinePlanDataset  # noqa: E402
from machineplan.generate import _pocket_corner_radius  # noqa: E402
from machineplan.parsing.step import parse_step  # noqa: E402

DEFAULT_ARCHIVE = pathlib.Path(__file__).resolve().parents[1] / "data" / "MachinePlan-10K.zip"
_SUB = re.compile(r"^Template Subtype:\s*(.+?)\s*$", re.MULTILINE)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=pathlib.Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--limit", type=int, default=150)
    arguments = parser.parse_args()

    deltas: collections.Counter[int] = collections.Counter()
    examples: list[str] = []
    floors_total = truth_total = 0
    parts = 0
    # Does the true count track the number of distinct Z levels instead?
    zlevel_hits = bbox_hits = 0
    needs_extra: list[float] = []
    needs_one: list[float] = []
    area_extra: list[float] = []
    area_one: list[float] = []

    with MachinePlanDataset(arguments.archive) as dataset:
        for part in list(dataset)[: arguments.limit]:
            if not part.brep:
                continue
            try:
                features = extract_features(parse_step(dataset.read_text(part.brep)))
            except Exception:  # noqa: BLE001
                continue

            truth = 0
            for index in sorted(part.operations):
                member = part.operations[index].details
                if not member:
                    continue
                with dataset.open(member) as handle:
                    head = handle.read(400).decode("utf-8", errors="replace")
                match = _SUB.search(head)
                if match and match.group(1) == "FLOOR_WALL":
                    truth += 1

            floors = len(features.pocket_floors)
            levels = len({round(f.z, 3) for f in features.pocket_floors})
            parts += 1
            floors_total += floors
            truth_total += truth
            deltas[floors - truth] += 1
            if floors == truth:
                bbox_hits += 1
            if levels == truth:
                zlevel_hits += 1

            # Record each floor's depth fraction against whether this part needed
            # more FLOOR_WALL operations than it has floors.
            top = features.stock_high[2]
            height = features.stock_height
            for floor in features.pocket_floors:
                fraction = (top - floor.z) / height if height else 0.0
                (needs_extra if truth > floors else needs_one).append(fraction)
                # Corner radius caps the endmill that can reach the corner
                # (diameter <= 2r), so a large pocket with tight corners may need
                # a roughing tool plus a smaller finishing one -- two operations.
                radius = _pocket_corner_radius(floor, features)
                smaller_side = min(floor.length_mm, floor.width_mm)
                ratio = smaller_side / (2 * radius) if radius > 0 else 0.0
                (area_extra if truth > floors else area_one).append(ratio)

            if floors != truth and len(examples) < 12:
                detail = ", ".join(
                    f"z={f.z:.1f} {f.length_mm:.0f}x{f.width_mm:.0f} "
                    f"d{(top - f.z) / height:.2f} "
                    f"t{f.touches_boundary(features.stock_low, features.stock_high)}"
                    for f in features.pocket_floors
                )
                examples.append(
                    f"{part.part_id}: floors {floors} levels {levels} vs truth {truth}"
                    + (f"  [{detail}]" if detail else "  [none]")
                )

    rule = "=" * 78
    print(rule)
    print(f"{parts} parts. recognised floors {floors_total / parts:.3f}/part, "
          f"true FLOOR_WALL {truth_total / parts:.3f}/part")
    print(rule)

    print("\n--- floors minus true FLOOR_WALL ---")
    for delta in sorted(deltas):
        count = deltas[delta]
        print(f"  {delta:+3d}  {count:4,}  {count / parts * 100:5.1f}%  "
              f"{'#' * min(count // 2, 55)}")

    print(f"\n--- which predictor matches the true count more often? ---")
    print(f"  one op per recognised floor patch : {bbox_hits:4,}/{parts}  "
          f"({bbox_hits / parts * 100:.1f}%)")
    print(f"  one op per distinct Z level       : {zlevel_hits:4,}/{parts}  "
          f"({zlevel_hits / parts * 100:.1f}%)")

    print(f"\n--- do pockets needing an extra operation differ? ---")
    import statistics
    for label, depths, areas in (
        ("needs MORE ops", needs_extra, area_extra),
        ("one op is right", needs_one, area_one),
    ):
        if depths:
            print(f"  {label:18} n={len(depths):4,}  "
                  f"depth fraction mean {statistics.fmean(depths):.3f} "
                  f"(median {statistics.median(depths):.3f})  "
                  f"size/2r mean {statistics.fmean(areas):6.2f}")

    print("\n--- mismatched parts ---")
    for line in examples:
        print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
