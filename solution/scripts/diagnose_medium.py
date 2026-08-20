#!/usr/bin/env python3
"""Which operations lose medium-tier IoU, now that counts are nearly right?

F-037 showed medium IoU tracked the operation-count ratio. After F-055 and F-056
that ratio is 0.9811, so counting is no longer the binding constraint and the
residual is geometry -- the term F-044 identified as the second ceiling.

This attributes the loss per operation and per feature type, so the next fix is
chosen by measurement rather than by which geometry looks least finished.
"""

from __future__ import annotations

import argparse
import collections
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
from machineplan.scoring.geometry import as_solid, compare_volumes  # noqa: E402

SOLUTION = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = SOLUTION / "data" / "MachinePlan-10K.zip"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=pathlib.Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--offset", type=int, default=8000)
    arguments = parser.parse_args()

    by_feature: dict[str, list[float]] = collections.defaultdict(list)
    over_by_feature: dict[str, list[float]] = collections.defaultdict(list)
    under_by_feature: dict[str, list[float]] = collections.defaultdict(list)
    part_ious: list[float] = []
    exact_count_ious: list[float] = []
    final_ious: list[float] = []

    with MachinePlanDataset(arguments.archive) as dataset:
        parts = list(dataset)[arguments.offset : arguments.offset + arguments.limit]
        print(f"scanning {len(parts)} held-out parts...\n")

        for part in parts:
            if not part.brep:
                continue
            try:
                features = extract_features(parse_step(dataset.read_text(part.brep)))
                plan = plan_part(part.part_id, features)
                generated = generate_part(plan, features)
                truth = [
                    as_solid(trimesh.load(
                        io.BytesIO(dataset.read_bytes(part.operations[i].mesh)),
                        file_type="stl"))
                    for i in sorted(part.operations) if part.operations[i].mesh
                ]
            except Exception:  # noqa: BLE001
                continue
            if not truth:
                continue

            ious: list[float] = []
            for index in range(min(len(generated.ipws), len(truth))):
                try:
                    comparison = compare_volumes(
                        as_solid(generated.ipws[index]), truth[index]
                    )
                except Exception:  # noqa: BLE001
                    continue
                feature = plan.operations[index].feature or "?"
                by_feature[feature].append(comparison.iou)
                over_by_feature[feature].append(comparison.overcut)
                under_by_feature[feature].append(comparison.undercut)
                ious.append(comparison.iou)

            if ious:
                part_ious.append(statistics.fmean(ious))
                if len(generated.ipws) == len(truth):
                    exact_count_ious.append(statistics.fmean(ious))

            # The final workpiece is order-independent: it is the stock minus the
            # union of everything removed. Comparing it isolates *what* we cut
            # from *when* we cut it. A high final IoU alongside a lower mean says
            # the residual is sequencing; a low final IoU says it is geometry or
            # feature identity.
            try:
                final_ious.append(
                    compare_volumes(as_solid(generated.ipws[-1]), truth[-1]).iou
                )
            except Exception:  # noqa: BLE001
                pass

    rule = "=" * 78
    print(rule)
    print(f"{len(part_ious)} parts scored")
    print(rule)
    print(f"\n{'feature':12}{'n':>7}{'mean IoU':>11}{'min IoU':>10}{'overcut':>10}{'undercut':>10}")
    print("-" * 60)
    for feature in sorted(by_feature, key=lambda f: -len(by_feature[f])):
        values = by_feature[feature]
        print(f"{feature:12}{len(values):>7,}{statistics.fmean(values):>11.5f}"
              f"{min(values):>10.5f}"
              f"{statistics.fmean(over_by_feature[feature]):>10.5f}"
              f"{statistics.fmean(under_by_feature[feature]):>10.5f}")

    if final_ious:
        print(f"\nmean FINAL-part IoU        : {statistics.fmean(final_ious):.5f}"
              "   (order-independent)")
        above = sum(1 for v in final_ious if v >= 0.999)
        print(f"  final IoU >= 0.999       : {above}/{len(final_ious)} parts")
    if part_ious:
        print(f"mean part IoU              : {statistics.fmean(part_ious):.5f}")
    if exact_count_ious:
        print(f"mean IoU, exact-count parts: {statistics.fmean(exact_count_ious):.5f}  "
              f"({len(exact_count_ious)} parts)")
        print("\nBand thresholds: 0.999 -> 35 | 0.99 -> 25 | 0.98 -> 20 | 0.95 -> 15 | 0.90 -> 10")
        for threshold, points in ((0.999, 35), (0.99, 25), (0.98, 20), (0.95, 15), (0.90, 10)):
            share = sum(1 for v in exact_count_ious if v >= threshold) / len(exact_count_ious)
            print(f"  >= {threshold:.3f} ({points:2d} pts): {share * 100:5.1f}% of exact-count parts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
