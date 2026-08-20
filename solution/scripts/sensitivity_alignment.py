#!/usr/bin/env python3
"""How much does F-037 depend on an assumption the rubric never states?

Q-002: the rubric says medium IoU is "averaged across all operations" but does
not define what happens when the predicted sequence is a different length from
the truth. Our scorer assumes the strict reading -- score over the union of
indices, so an unmatched operation contributes IoU 0.

F-037 concluded from that scorer that medium IoU is essentially the operation
count ratio (r = 0.999), and that conclusion drove the project's priorities for
several hours. If the graders instead truncate to the shorter sequence, length
mismatch is nearly free and the tier is geometry-driven instead.

This scores the same parts under both conventions. The point is not to pick a
winner -- only the organizers can -- but to know how much rides on the guess.
"""

from __future__ import annotations

import argparse
import io
import pathlib
import statistics
import sys

import trimesh

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from machineplan.features import extract_features  # noqa: E402
from machineplan.generate import generate_part  # noqa: E402
from machineplan.parsing.dataset import MachinePlanDataset  # noqa: E402
from machineplan.parsing.step import parse_step  # noqa: E402
from machineplan.predict import plan_part  # noqa: E402
from machineplan.scoring.geometry import as_solid  # noqa: E402
from machineplan.scoring.medium import score_medium  # noqa: E402

SOLUTION = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = SOLUTION / "data" / "MachinePlan-10K.zip"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=pathlib.Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--offset", type=int, default=3000)
    arguments = parser.parse_args()

    union_points: list[float] = []
    truncate_points: list[float] = []
    union_iou: list[float] = []
    truncate_iou: list[float] = []
    ratios: list[float] = []
    mismatched = 0

    with MachinePlanDataset(arguments.archive) as dataset:
        parts = list(dataset)[arguments.offset : arguments.offset + arguments.limit]
        print(f"scoring {len(parts)} held-out parts under both conventions...\n")

        for part in parts:
            if not part.brep:
                continue
            try:
                features = extract_features(parse_step(dataset.read_text(part.brep)))
                plan = plan_part(part.part_id, features)
                generated = generate_part(plan, features)
                truth = [
                    as_solid(trimesh.load(
                        io.BytesIO(dataset.read_bytes(part.operations[i].mesh)), file_type="stl"
                    ))
                    for i in sorted(part.operations) if part.operations[i].mesh
                ]
                if not truth:
                    continue
                predicted = [as_solid(m) for m in generated.ipws]
            except Exception:  # noqa: BLE001
                continue

            if len(predicted) != len(truth):
                mismatched += 1
            ratios.append(min(len(predicted), len(truth)) / max(len(predicted), len(truth)))

            union = score_medium(predicted, truth, alignment="union")
            truncated = score_medium(predicted, truth, alignment="truncate")
            union_points.append(union.points)
            truncate_points.append(truncated.points)
            union_iou.append(union.mean_iou)
            truncate_iou.append(truncated.mean_iou)

    if not union_points:
        print("no parts scored", file=sys.stderr)
        return 2

    rule = "=" * 78
    print(rule)
    print(f"{len(union_points)} parts, {mismatched} with a length mismatch "
          f"({mismatched / len(union_points) * 100:.0f}%), "
          f"mean length ratio {statistics.fmean(ratios):.3f}")
    print(rule)
    print(f"{'convention':14}{'mean points':>14}{'mean IoU':>12}{'parts >= 0.90':>16}")
    for label, points, ious in (
        ("union (ours)", union_points, union_iou),
        ("truncate", truncate_points, truncate_iou),
    ):
        above = sum(1 for value in ious if value >= 0.90)
        print(f"{label:14}{statistics.fmean(points):>14.2f}"
              f"{statistics.fmean(ious):>12.4f}{above:>12}/{len(ious)}")

    gap = statistics.fmean(truncate_points) - statistics.fmean(union_points)
    print(f"\n  difference: {gap:+.2f} points of 35 "
          f"({gap / 35 * 100:+.0f}% of the tier)")

    # Under truncation, does count still predict IoU?
    if len(ratios) > 3:
        def correlation(xs: list[float], ys: list[float]) -> float:
            mx, my = statistics.fmean(xs), statistics.fmean(ys)
            cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
            return cov / den if den else 0.0

        print(f"\n  correlation of length ratio with IoU:")
        print(f"    union    r = {correlation(ratios, union_iou):+.4f}   <- F-037 measured 0.999")
        print(f"    truncate r = {correlation(ratios, truncate_iou):+.4f}")
        print("\n  If the truncate correlation is weak, F-037's 'count is everything'")
        print("  conclusion holds only under our assumed convention (Q-002).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
