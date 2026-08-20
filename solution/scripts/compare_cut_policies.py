#!/usr/bin/env python3
"""Which features are worth cutting into the IPW chain?

F-036 found that cutting *everything* scored below cutting *nothing*, because an
approximate removal is worse than none on a metric where the block is only ~4.75%
machined. That argues for per-feature opt-in -- but which features earn their
place is an empirical question, so this measures every policy on the same parts.
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

DEFAULT_ARCHIVE = pathlib.Path(__file__).resolve().parents[1] / "data" / "MachinePlan-10K.zip"

POLICIES: dict[str, frozenset[str]] = {
    "nothing (null)": frozenset(),
    "holes only": frozenset({"hole"}),
    "holes+chamfers": frozenset({"hole", "chamfer"}),
    "holes+pockets": frozenset({"hole", "pocket"}),
    "everything": frozenset({"hole", "pocket", "chamfer"}),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=pathlib.Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--limit", type=int, default=12)
    arguments = parser.parse_args()

    results: dict[str, list[float]] = {name: [] for name in POLICIES}
    ious: dict[str, list[float]] = {name: [] for name in POLICIES}

    with MachinePlanDataset(arguments.archive) as dataset:
        parts = list(dataset)[: arguments.limit]
        print(f"comparing {len(POLICIES)} cut policies over {len(parts)} parts\n")
        header = f"{'part':22}" + "".join(f"{name:>17}" for name in POLICIES)
        print(header)
        print("-" * len(header))

        for part in parts:
            if not part.brep:
                continue
            try:
                features = extract_features(parse_step(dataset.read_text(part.brep)))
                plan = plan_part(part.part_id, features)
            except Exception:  # noqa: BLE001
                continue

            truth = []
            for index in sorted(part.operations):
                member = part.operations[index].mesh
                if member:
                    truth.append(
                        as_solid(
                            trimesh.load(
                                io.BytesIO(dataset.read_bytes(member)), file_type="stl"
                            )
                        )
                    )
            if not truth:
                continue

            row = f"{part.part_id:22}"
            for name, policy in POLICIES.items():
                try:
                    generated = generate_part(plan, features, cut_features=policy)
                    score = score_medium([as_solid(m) for m in generated.ipws], truth)
                    results[name].append(score.points)
                    ious[name].append(score.mean_iou)
                    row += f"{score.points:8.1f} ({score.mean_iou:.3f})"
                except Exception:  # noqa: BLE001
                    row += f"{'fail':>17}"
            print(row)

    rule = "=" * 78
    print(f"\n{rule}\nMEDIUM TIER BY CUT POLICY\n{rule}")
    print(f"{'policy':20}{'mean pts':>11}{'mean IoU':>11}{'min IoU':>10}{'parts >= 0.90':>16}")
    for name in POLICIES:
        values = results[name]
        iou_values = ious[name]
        if not values:
            continue
        above = sum(1 for v in iou_values if v >= 0.90)
        print(f"{name:20}{statistics.fmean(values):>11.2f}"
              f"{statistics.fmean(iou_values):>11.4f}{min(iou_values):>10.4f}"
              f"{above:>10}/{len(iou_values)}")

    best = max(results, key=lambda n: statistics.fmean(results[n]) if results[n] else -1)
    print(f"\n  best policy: {best}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
