#!/usr/bin/env python3
"""Validate BRep feature recognition against independently published statistics.

Dataset_Description.pdf reports corpus-level figures that our recognizer never
sees, so they make honest checks:

  * 2.33 holes per part on average (median 2, range 0-6)
  * hole depth types split 50.2% blind / 49.8% through
  * hole diameters span 5.0-50.0 mm, mean 17.47 mm
  * blocks are 200-500 mm in L and W, 50-150 mm in H

Plus a per-part consistency check that does not depend on the paper: every
recognised hole diameter should correspond to a tool that actually machined the
part, since the last tool through a hole sets its final size.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import re
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from machineplan.features import extract_features  # noqa: E402
from machineplan.parsing.dataset import MachinePlanDataset  # noqa: E402
from machineplan.parsing.step import parse_step  # noqa: E402

DEFAULT_ARCHIVE = pathlib.Path(__file__).resolve().parents[1] / "data" / "MachinePlan-10K.zip"
HEAD_BYTES = 2600
_DIAMETER_RE = re.compile(r"\(D\)\s*Diameter\s*=\s*([\d.]+)")
_SUBTYPE_RE = re.compile(r"^Template Type:\s*(\S+)", re.MULTILINE)

PAPER = {
    "holes_per_part": 2.33,
    "blind_share": 0.502,
    "diameter_mean": 17.47,
    "diameter_min": 5.0,
    "diameter_max": 50.0,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=pathlib.Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--limit", type=int, default=400)
    arguments = parser.parse_args()

    hole_counts: list[int] = []
    diameters: list[float] = []
    depth_types: collections.Counter[str] = collections.Counter()
    lengths: list[float] = []
    widths: list[float] = []
    heights: list[float] = []
    surface_census: collections.Counter[str] = collections.Counter()

    matched = unmatched = 0
    unmatched_examples: list[str] = []
    failures = 0

    with MachinePlanDataset(arguments.archive) as dataset:
        parts = list(dataset)[: arguments.limit]
        print(f"scanning {len(parts)} parts...\n")

        for part in parts:
            if not part.brep:
                continue
            try:
                model = parse_step(dataset.read_text(part.brep))
                features = extract_features(model)
            except Exception as error:  # noqa: BLE001 - report, don't abort the sweep
                failures += 1
                if failures <= 3:
                    print(f"  FAILED {part.part_id}: {type(error).__name__}: {error}")
                continue

            for name, count in model.surface_type_census().items():
                surface_census[name] += count

            hole_counts.append(len(features.holes))
            lengths.append(features.stock_length)
            widths.append(features.stock_width)
            heights.append(features.stock_height)
            for hole in features.holes:
                diameters.append(hole.diameter_mm)
                depth_types[hole.depth_type(features.stock_low[2])] += 1

            # Tool diameters used by this part's hole-making operations.
            tool_diameters: set[float] = set()
            for index in sorted(part.operations):
                member = part.operations[index].details
                if not member:
                    continue
                with dataset.open(member) as handle:
                    head = handle.read(HEAD_BYTES).decode("utf-8", errors="replace")
                for value in _DIAMETER_RE.findall(head):
                    tool_diameters.add(round(float(value), 2))

            for hole in features.holes:
                if any(abs(hole.diameter_mm - d) < 0.15 for d in tool_diameters):
                    matched += 1
                else:
                    unmatched += 1
                    if len(unmatched_examples) < 8:
                        unmatched_examples.append(
                            f"{part.part_id}: hole D{hole.diameter_mm:.2f} "
                            f"vs tools {sorted(tool_diameters)}"
                        )

    rule = "=" * 78
    print(rule)
    print(f"{len(hole_counts)} parts parsed, {failures} failures, {len(diameters)} holes found")
    print(rule)

    print("\n--- surface types seen (assumption check) ---")
    for name, count in surface_census.most_common():
        print(f"  {name:34} {count:8,}")

    print(f"\n{'metric':34}{'ours':>12}{'paper':>12}  verdict")
    print("-" * 78)

    def compare(label: str, ours: float, expected: float, tolerance: float) -> None:
        ok = abs(ours - expected) <= tolerance
        print(f"{label:34}{ours:>12.3f}{expected:>12.3f}  {'OK' if ok else 'MISMATCH'}")

    compare("holes per part (mean)", statistics.fmean(hole_counts), PAPER["holes_per_part"], 0.25)
    if diameters:
        compare("hole diameter mean (mm)", statistics.fmean(diameters), PAPER["diameter_mean"], 2.0)
        compare("hole diameter min (mm)", min(diameters), PAPER["diameter_min"], 0.6)
        compare("hole diameter max (mm)", max(diameters), PAPER["diameter_max"], 0.6)
    total_depths = sum(depth_types.values())
    if total_depths:
        compare("blind share", depth_types["blind"] / total_depths, PAPER["blind_share"], 0.08)
    compare("block length mean (mm)", statistics.fmean(lengths), 350.22, 12.0)
    compare("block width mean (mm)", statistics.fmean(widths), 350.61, 12.0)
    compare("block height mean (mm)", statistics.fmean(heights), 100.05, 5.0)

    print(f"\n--- holes per part distribution ---")
    histogram = collections.Counter(hole_counts)
    for value in sorted(histogram):
        count = histogram[value]
        print(f"  {value:2d} holes {count:5,}  {'#' * min(count // 2, 60)}")

    print(f"\n--- hole diameter matched to a tool actually used on the part ---")
    total = matched + unmatched
    if total:
        print(f"  matched   : {matched:6,} / {total:,}  ({matched / total * 100:.2f}%)")
        print(f"  unmatched : {unmatched:6,} / {total:,}  ({unmatched / total * 100:.2f}%)")
    for line in unmatched_examples:
        print(f"     {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
