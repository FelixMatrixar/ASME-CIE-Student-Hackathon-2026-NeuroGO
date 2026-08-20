#!/usr/bin/env python3
"""What diameter does each step of a hole's chain actually use?

`diagnose_tools.py` found tool *type* is already 100% correct on aligned slots,
and the whole tool-tier loss is diameter -- and only on two types:

    chamfer_mill  error 0.000  ->  10.0/10   (one tool, always 20 mm)
    spot_drill    error 0.000  ->  10.0/10   (one tool, always 12 mm)
    twist_drill   error 0.598  ->   4.3/10   <-- systematic
    end_mill      error 0.444  ->   3.1/10   <-- systematic

A 60% relative error is mis-assignment, not noise: our pilot/finish sizing rule
is simply wrong. Rather than guess a third time (F-046), this measures the real
diameter of every step against the hole it is cutting, so the rule can be fitted.

Emits `diameter / hole_diameter` per (subtype, position-in-chain), which is the
form the planner needs.
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
from machineplan.parsing.ptp import parse_ptp  # noqa: E402
from machineplan.parsing.step import parse_step  # noqa: E402

SOLUTION = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = SOLUTION / "data" / "MachinePlan-10K.zip"
HEAD_BYTES = 2600
MATCH_TOLERANCE_MM = 1.0

_SUB = re.compile(r"^Template Subtype:\s*(.+?)\s*$", re.MULTILINE)
_DIA = re.compile(r"\(D\)\s*Diameter\s*=\s*([\d.]+)")
HOLE_SUBTYPES = {
    "DRILLING", "SPOT_DRILLING", "DEEP_HOLE_DRILLING", "HOLE_MILLING", "BORING_REAMING",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=pathlib.Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--limit", type=int, default=1200)
    arguments = parser.parse_args()

    # (subtype, index among that subtype, count of that subtype) -> ratios
    ratios: dict[tuple[str, int, int], list[float]] = collections.defaultdict(list)
    absolute: dict[str, list[float]] = collections.defaultdict(list)
    pocket_ratio: list[float] = []

    with MachinePlanDataset(arguments.archive) as dataset:
        parts = list(dataset)[: arguments.limit]
        print(f"scanning {len(parts)} parts...\n")

        for number, part in enumerate(parts, start=1):
            if number % 300 == 0:
                print(f"  {number}/{len(parts)}")
            if not part.brep:
                continue
            try:
                features = extract_features(parse_step(dataset.read_text(part.brep)))
            except Exception:  # noqa: BLE001
                continue
            if not features.holes:
                continue

            positioned: list[tuple[float, float, str, float, int]] = []
            for index in sorted(part.operations):
                operation = part.operations[index]
                if not operation.details or not operation.tool_path:
                    continue
                with dataset.open(operation.details) as handle:
                    head = handle.read(HEAD_BYTES).decode("utf-8", errors="replace")
                match = _SUB.search(head)
                if not match or match.group(1) not in HOLE_SUBTYPES:
                    continue
                diameter_match = _DIA.search(head)
                if not diameter_match:
                    continue
                try:
                    path = parse_ptp(dataset.read_text(operation.tool_path))
                except Exception:  # noqa: BLE001
                    continue
                cutting = path.cutting_moves
                if not cutting:
                    continue
                positioned.append(
                    (cutting[0].start[0], cutting[0].start[1],
                     match.group(1), float(diameter_match.group(1)), index)
                )

            per_hole: dict[int, list[tuple[int, str, float]]] = collections.defaultdict(list)
            for x, y, subtype, diameter, index in positioned:
                best, best_distance = None, MATCH_TOLERANCE_MM
                for hole_index, hole in enumerate(features.holes):
                    distance = ((hole.x - x) ** 2 + (hole.y - y) ** 2) ** 0.5
                    if distance < best_distance:
                        best, best_distance = hole_index, distance
                if best is not None:
                    per_hole[best].append((index, subtype, diameter))

            for hole_index, chain in per_hole.items():
                hole = features.holes[hole_index]
                if hole.diameter_mm <= 0:
                    continue
                chain.sort()
                subtype_counts = collections.Counter(s for _, s, _ in chain)
                seen: collections.Counter[str] = collections.Counter()
                for _, subtype, diameter in chain:
                    position = seen[subtype]
                    seen[subtype] += 1
                    key = (subtype, position, subtype_counts[subtype])
                    ratios[key].append(diameter / hole.diameter_mm)
                    absolute[subtype].append(diameter)

    rule = "=" * 78
    print(f"\n{rule}\nTOOL DIAMETER / HOLE DIAMETER, by subtype and position\n{rule}")
    print(f"{'subtype':22}{'pos':>5}{'of':>4}{'n':>7}{'mean':>9}{'median':>9}{'sd':>8}")
    for key in sorted(ratios, key=lambda k: (k[0], k[2], k[1])):
        values = ratios[key]
        if len(values) < 20:
            continue
        subtype, position, count = key
        print(f"{subtype:22}{position + 1:>5}{count:>4}{len(values):>7,}"
              f"{statistics.fmean(values):>9.3f}{statistics.median(values):>9.3f}"
              f"{statistics.pstdev(values):>8.3f}")

    print(f"\n--- absolute diameters, for the fixed-tool subtypes ---")
    for subtype in sorted(absolute, key=lambda s: -len(absolute[s])):
        values = absolute[subtype]
        distinct = len(set(round(v, 2) for v in values))
        print(f"  {subtype:22} n={len(values):6,}  mean {statistics.fmean(values):6.2f}  "
              f"{distinct} distinct sizes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
