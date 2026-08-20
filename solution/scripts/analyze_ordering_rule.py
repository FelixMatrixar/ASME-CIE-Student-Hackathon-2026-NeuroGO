#!/usr/bin/env python3
"""Q-010: is operation ordering coordinate-dependent or coordinate-free?

This gates up to 8x symmetry augmentation. We cannot re-run NX on a rotated part,
so we test the decisive proxy: **what rule orders operations that share a tool?**

* If they are sorted by absolute X (or Y), a 90 degree rotation maps X to Y and
  reorders the sequence -- naive augmentation would then produce wrong labels.
* If they follow a nearest-neighbour travel path, rotation preserves all
  distances, the order survives, and augmentation is sound.

Consecutive `SPOT_DRILL` runs are the ideal probe: one tool, one point per
operation, several in a row. Each operation's position comes from the first
cutting move of its tool path.
"""

from __future__ import annotations

import argparse
import collections
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from machineplan.parsing.dataset import MachinePlanDataset  # noqa: E402
from machineplan.parsing.ptp import parse_ptp  # noqa: E402

DEFAULT_ARCHIVE = pathlib.Path(__file__).resolve().parents[1] / "data" / "MachinePlan-10K.zip"

Point = tuple[float, float]


def is_sorted_by(points: list[Point], key) -> bool:
    values = [key(p) for p in points]
    return values == sorted(values) or values == sorted(values, reverse=True)


def is_nearest_neighbour(points: list[Point], tolerance: float = 1e-6) -> bool:
    """Whether each step goes to the closest not-yet-visited point."""
    remaining = points[1:]
    current = points[0]
    for actual in points[1:]:
        best = min(remaining, key=lambda p: math.dist(current, p))
        if math.dist(actual, best) > tolerance:
            return False
        remaining = [p for p in remaining if p is not actual]
        current = actual
    return True


def path_length(points: list[Point]) -> float:
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def greedy_length(points: list[Point]) -> float:
    """Length of the greedy nearest-neighbour tour from the same start."""
    remaining = list(points[1:])
    current = points[0]
    total = 0.0
    while remaining:
        nxt = min(remaining, key=lambda p: math.dist(current, p))
        total += math.dist(current, nxt)
        remaining.remove(nxt)
        current = nxt
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=pathlib.Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--limit", type=int, default=600, help="parts to scan")
    parser.add_argument("--min-run", type=int, default=3, help="minimum block length to test")
    arguments = parser.parse_args()

    verdicts: collections.Counter[str] = collections.Counter()
    blocks_tested = 0
    ratio_sum = 0.0
    ratio_worse = 0
    examples: list[str] = []

    with MachinePlanDataset(arguments.archive) as dataset:
        parts = list(dataset)[: arguments.limit]
        print(f"scanning {len(parts)} parts for same-tool runs of >= {arguments.min_run}...\n")

        for part in parts:
            if not part.operations_json:
                continue
            payload = dataset.read_json(part.operations_json)
            operations = payload.get("operations", [])
            if len(operations) < arguments.min_run:
                continue

            # Split into contiguous same-tool runs.
            run: list[int] = []
            previous_tool: str | None = None
            runs: list[list[int]] = []
            for index, entry in enumerate(operations, start=1):
                tool = entry.get("tool_name")
                if tool != previous_tool and run:
                    runs.append(run)
                    run = []
                run.append(index)
                previous_tool = tool
            if run:
                runs.append(run)

            for indices in runs:
                if len(indices) < arguments.min_run:
                    continue
                points: list[Point] = []
                for index in indices:
                    operation = part.operations.get(index)
                    if operation is None or not operation.tool_path:
                        break
                    try:
                        path = parse_ptp(dataset.read_text(operation.tool_path))
                    except Exception:
                        break
                    cutting = path.cutting_moves
                    if not cutting:
                        break
                    points.append((cutting[0].start[0], cutting[0].start[1]))
                if len(points) < arguments.min_run:
                    continue
                # Skip runs where every operation sits at the same XY.
                if len({(round(x, 3), round(y, 3)) for x, y in points}) < len(points):
                    continue

                blocks_tested += 1
                matched = False
                if is_sorted_by(points, lambda p: p[0]):
                    verdicts["sorted by X"] += 1
                    matched = True
                if is_sorted_by(points, lambda p: p[1]):
                    verdicts["sorted by Y"] += 1
                    matched = True
                if is_nearest_neighbour(points):
                    verdicts["nearest-neighbour"] += 1
                    matched = True
                if not matched:
                    verdicts["none of the above"] += 1
                    if len(examples) < 5:
                        examples.append(
                            f"{part.part_id} ops {indices}: "
                            + " ".join(f"({x:.1f},{y:.1f})" for x, y in points)
                        )

                actual = path_length(points)
                greedy = greedy_length(points)
                if greedy > 1e-9:
                    ratio_sum += actual / greedy
                    if actual > greedy + 1e-6:
                        ratio_worse += 1

    rule = "=" * 78
    print(rule)
    print(f"{blocks_tested} same-tool blocks tested")
    print(rule)
    if not blocks_tested:
        print("no qualifying blocks found; try --limit higher or --min-run lower")
        return 0

    print("\nordering rule match (a block can satisfy more than one):")
    for label, count in verdicts.most_common():
        print(f"  {label:22} {count:6,}  {count / blocks_tested * 100:6.2f}%")

    print(f"\ntravel length vs greedy nearest-neighbour tour:")
    print(f"  mean actual/greedy ratio : {ratio_sum / blocks_tested:.4f}")
    print(f"  blocks longer than greedy: {ratio_worse:,} ({ratio_worse / blocks_tested * 100:.2f}%)")

    print(f"\n{rule}")
    coordinate_free = verdicts["nearest-neighbour"] / blocks_tested * 100
    axis_sorted = max(verdicts["sorted by X"], verdicts["sorted by Y"]) / blocks_tested * 100
    print("VERDICT")
    print(rule)
    print(f"  nearest-neighbour (rotation-invariant) : {coordinate_free:6.2f}%")
    print(f"  axis-sorted (rotation would reorder)   : {axis_sorted:6.2f}%")
    if examples:
        print("\nunexplained examples:")
        for line in examples:
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
