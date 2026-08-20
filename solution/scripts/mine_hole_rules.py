#!/usr/bin/env python3
"""Q-011: recover the feature -> operation rules for holes.

Drilling operations name their XY position in the `.ptp`, and `features.py`
recovers each hole's XY from the BRep. Matching the two gives, per *individual
hole*, the exact ordered chain of operations NX applied to it -- which is the
deterministic rule we are trying to recover, observed directly.

Questions this answers:
  * which holes get a SPOT_DRILL first?
  * when does a hole need more than one drilling pass?
  * what decides DEEP_HOLE_DRILLING (pecking) over plain DRILLING?
  * at what diameter does drilling give way to HOLE_MILLING? (tests F-032)
  * when is BORING_REAMING added?
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

DEFAULT_ARCHIVE = pathlib.Path(__file__).resolve().parents[1] / "data" / "MachinePlan-10K.zip"
HEAD_BYTES = 2600
MATCH_TOLERANCE_MM = 1.0

_SUBTYPE_RE = re.compile(r"^Template Subtype:\s*(.+?)\s*$", re.MULTILINE)
_TYPE_RE = re.compile(r"^Template Type:\s*(\S+)", re.MULTILINE)
_DIAMETER_RE = re.compile(r"\(D\)\s*Diameter\s*=\s*([\d.]+)")

HOLE_SUBTYPES = {
    "DRILLING", "SPOT_DRILLING", "DEEP_HOLE_DRILLING", "HOLE_MILLING", "BORING_REAMING",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=pathlib.Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--limit", type=int, default=500)
    arguments = parser.parse_args()

    # hole signature -> observed operation chains
    chains: collections.Counter[tuple[str, ...]] = collections.Counter()
    holes_seen = 0
    holes_matched = 0
    operations_seen = 0
    operations_matched = 0

    spot_by_diameter: dict[bool, list[float]] = {True: [], False: []}
    spot_by_depth_type: collections.Counter[tuple[str, bool]] = collections.Counter()
    subtype_diameters: dict[str, list[float]] = collections.defaultdict(list)
    subtype_aspect: dict[str, list[float]] = collections.defaultdict(list)
    passes_by_diameter: list[tuple[float, int]] = []
    milling_diameters: list[float] = []
    drilling_diameters: list[float] = []
    max_drill_seen = 0.0

    with MachinePlanDataset(arguments.archive) as dataset:
        parts = list(dataset)[: arguments.limit]
        print(f"scanning {len(parts)} parts...\n")

        for part in parts:
            if not part.brep:
                continue
            try:
                features = extract_features(parse_step(dataset.read_text(part.brep)))
            except Exception:  # noqa: BLE001
                continue
            if not features.holes:
                continue

            # Collect this part's hole-making operations with their XY positions.
            positioned: list[tuple[float, float, str, float, int]] = []
            for index in sorted(part.operations):
                operation = part.operations[index]
                if not operation.details or not operation.tool_path:
                    continue
                with dataset.open(operation.details) as handle:
                    head = handle.read(HEAD_BYTES).decode("utf-8", errors="replace")
                subtype_match = _SUBTYPE_RE.search(head)
                if not subtype_match or subtype_match.group(1) not in HOLE_SUBTYPES:
                    continue
                diameter_match = _DIAMETER_RE.search(head)
                diameter = float(diameter_match.group(1)) if diameter_match else 0.0
                subtype = subtype_match.group(1)
                if subtype in ("DRILLING", "DEEP_HOLE_DRILLING"):
                    max_drill_seen = max(max_drill_seen, diameter)
                try:
                    path = parse_ptp(dataset.read_text(operation.tool_path))
                except Exception:  # noqa: BLE001
                    continue
                cutting = path.cutting_moves
                if not cutting:
                    continue
                positioned.append(
                    (cutting[0].start[0], cutting[0].start[1], subtype, diameter, index)
                )
            operations_seen += len(positioned)

            # Match each operation to the nearest hole within tolerance.
            per_hole: dict[int, list[tuple[int, str, float]]] = collections.defaultdict(list)
            for x, y, subtype, diameter, index in positioned:
                best = None
                best_distance = MATCH_TOLERANCE_MM
                for hole_index, hole in enumerate(features.holes):
                    distance = ((hole.x - x) ** 2 + (hole.y - y) ** 2) ** 0.5
                    if distance < best_distance:
                        best, best_distance = hole_index, distance
                if best is not None:
                    per_hole[best].append((index, subtype, diameter))
                    operations_matched += 1

            for hole_index, hole in enumerate(features.holes):
                holes_seen += 1
                chain = per_hole.get(hole_index)
                if not chain:
                    continue
                holes_matched += 1
                chain.sort()
                labels = tuple(subtype for _, subtype, _ in chain)
                chains[labels] += 1

                through = hole.depth_type(features.stock_low[2]) == "through"
                has_spot = "SPOT_DRILLING" in labels
                spot_by_diameter[has_spot].append(hole.diameter_mm)
                spot_by_depth_type[("through" if through else "blind", has_spot)] += 1

                for subtype in set(labels):
                    subtype_diameters[subtype].append(hole.diameter_mm)
                    subtype_aspect[subtype].append(hole.aspect_ratio())

                drill_passes = sum(
                    1 for s in labels if s in ("DRILLING", "DEEP_HOLE_DRILLING")
                )
                passes_by_diameter.append((hole.diameter_mm, drill_passes))
                if "HOLE_MILLING" in labels:
                    milling_diameters.append(hole.diameter_mm)
                elif drill_passes:
                    drilling_diameters.append(hole.diameter_mm)

    rule = "=" * 78
    print(rule)
    print(f"{holes_seen} holes, {holes_matched} matched to operations "
          f"({holes_matched / max(holes_seen, 1) * 100:.1f}%)")
    print(f"{operations_seen} hole operations, {operations_matched} matched "
          f"({operations_matched / max(operations_seen, 1) * 100:.1f}%)")
    print(rule)

    print(f"\n--- operation chains per hole (top 15 of {len(chains)}) ---")
    total_chains = sum(chains.values())
    for chain, count in chains.most_common(15):
        print(f"  {count:5,}  {count / total_chains * 100:5.1f}%  {' -> '.join(chain)}")

    print("\n--- does a hole get a SPOT_DRILL? ---")
    for has_spot in (True, False):
        values = spot_by_diameter[has_spot]
        if values:
            print(f"  spot={str(has_spot):5}  n={len(values):5,}  "
                  f"diameter mean {statistics.fmean(values):6.2f}  "
                  f"min {min(values):5.2f}  max {max(values):5.2f}")
    print("  by depth type:")
    for (depth_type, has_spot), count in sorted(spot_by_depth_type.items()):
        print(f"     {depth_type:8} spot={str(has_spot):5} {count:5,}")

    print("\n--- subtype vs hole geometry ---")
    print(f"{'subtype':22}{'n':>7}{'dia mean':>10}{'dia min':>9}{'dia max':>9}"
          f"{'aspect mean':>13}{'aspect max':>12}")
    for subtype in sorted(subtype_diameters, key=lambda s: -len(subtype_diameters[s])):
        diameters = subtype_diameters[subtype]
        aspects = subtype_aspect[subtype]
        print(f"{subtype:22}{len(diameters):>7,}{statistics.fmean(diameters):>10.2f}"
              f"{min(diameters):>9.2f}{max(diameters):>9.2f}"
              f"{statistics.fmean(aspects):>13.2f}{max(aspects):>12.2f}")

    print(f"\n--- F-032 test: milled vs drilled by diameter ---")
    print(f"  largest drill observed anywhere : {max_drill_seen:.2f} mm")
    if drilling_diameters:
        print(f"  drilled holes  n={len(drilling_diameters):5,}  "
              f"diameter max {max(drilling_diameters):6.2f}")
    if milling_diameters:
        print(f"  milled holes   n={len(milling_diameters):5,}  "
              f"diameter min {min(milling_diameters):6.2f}  "
              f"mean {statistics.fmean(milling_diameters):6.2f}")
        overlap = [d for d in milling_diameters if d <= max(drilling_diameters or [0])]
        print(f"  milled holes inside the drilled range: {len(overlap):,} "
              f"({len(overlap) / len(milling_diameters) * 100:.1f}%)")

    print("\n--- drilling passes vs hole diameter ---")
    buckets: dict[int, list[float]] = collections.defaultdict(list)
    for diameter, passes in passes_by_diameter:
        buckets[passes].append(diameter)
    for passes in sorted(buckets):
        values = buckets[passes]
        print(f"  {passes} pass(es): n={len(values):5,}  "
              f"diameter mean {statistics.fmean(values):6.2f}  "
              f"min {min(values):5.2f}  max {max(values):6.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
