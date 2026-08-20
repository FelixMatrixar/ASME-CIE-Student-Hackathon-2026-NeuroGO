#!/usr/bin/env python3
"""Where does the predicted operation count go wrong?

F-037 showed medium IoU is essentially the ratio of predicted to true operation
count, so counting correctly is now the single objective across 55 points. This
attributes the error two ways:

  1. **per operation label** -- which of the seven `o2` subtypes we over- or
     under-generate, and by how much;
  2. **per recognised feature** -- whether our hole / pocket / chamfer counts match
     the corpus statistics published in Dataset_Description.pdf, which is where a
     label error usually originates.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from machineplan.features import extract_features  # noqa: E402
from machineplan.parsing.dataset import MachinePlanDataset  # noqa: E402
from machineplan.parsing.details import parse_details  # noqa: E402
from machineplan.parsing.step import parse_step  # noqa: E402
from machineplan.predict import plan_part  # noqa: E402

DEFAULT_ARCHIVE = pathlib.Path(__file__).resolve().parents[1] / "data" / "MachinePlan-10K.zip"
HEAD_BYTES = 400

# Per-part means published in Dataset_Description.pdf section 6.6.
PAPER_FEATURES = {"holes": 2.33, "pockets": 1.85, "chamfers": 1.63}
# Corpus operation shares, Table 4.
PAPER_LABEL_SHARE = {
    "DRILLING": 0.331, "AREA_MILL": 0.219, "FLOOR_WALL": 0.202,
    "SPOT_DRILLING": 0.155, "DEEP_HOLE_DRILLING": 0.049,
    "HOLE_MILLING": 0.038, "BORING_REAMING": 0.006,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=pathlib.Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--limit", type=int, default=200)
    arguments = parser.parse_args()

    predicted_labels: collections.Counter[str] = collections.Counter()
    truth_labels: collections.Counter[str] = collections.Counter()
    per_part_error: collections.Counter[str] = collections.Counter()
    per_part_abs: collections.Counter[str] = collections.Counter()
    parts_wrong: collections.Counter[str] = collections.Counter()
    feature_counts: dict[str, list[int]] = collections.defaultdict(list)
    ratios: list[float] = []
    parts_done = 0

    with MachinePlanDataset(arguments.archive) as dataset:
        parts = list(dataset)[: arguments.limit]
        print(f"scanning {len(parts)} parts...\n")

        for part in parts:
            if not part.brep:
                continue
            try:
                features = extract_features(parse_step(dataset.read_text(part.brep)))
                plan = plan_part(part.part_id, features)
            except Exception:  # noqa: BLE001
                continue

            truth: list[str] = []
            for index in sorted(part.operations):
                member = part.operations[index].details
                if not member:
                    continue
                with dataset.open(member) as handle:
                    head = handle.read(HEAD_BYTES).decode("utf-8", errors="replace")
                try:
                    _, o2 = _labels(head)
                except ValueError:
                    continue
                truth.append(o2)
            if not truth:
                continue

            parts_done += 1
            feature_counts["holes"].append(len(features.holes))
            feature_counts["pockets"].append(len(features.pocket_floors))
            feature_counts["chamfers"].append(len(features.chamfers))

            mine = [operation.o2 for operation in plan.operations]
            predicted_labels.update(mine)
            truth_labels.update(truth)

            mine_counter = collections.Counter(mine)
            truth_counter = collections.Counter(truth)
            for label in set(mine_counter) | set(truth_counter):
                delta = mine_counter[label] - truth_counter[label]
                per_part_error[label] += delta
                # Absolute error is the one that matters: F-037 scores each part
                # independently, so per-part mistakes of opposite sign do NOT
                # cancel even though they vanish from the net figure.
                per_part_abs[label] += abs(delta)
                if delta:
                    parts_wrong[label] += 1

            ratios.append(min(len(mine), len(truth)) / max(len(mine), len(truth)))

    rule = "=" * 78
    print(rule)
    print(f"{parts_done} parts. mean length ratio {statistics.fmean(ratios):.4f} "
          f"-> medium IoU ~{statistics.fmean(ratios):.3f} (F-037)")
    print(rule)

    print(f"\n--- recognised features per part vs the paper ---")
    print(f"{'feature':14}{'ours':>9}{'paper':>9}{'delta':>9}")
    for name, expected in PAPER_FEATURES.items():
        values = feature_counts[name]
        ours = statistics.fmean(values) if values else 0.0
        print(f"{name:14}{ours:>9.3f}{expected:>9.3f}{ours - expected:>+9.3f}")

    print(f"\n--- operations by label: predicted vs truth ---")
    total_predicted = sum(predicted_labels.values())
    total_truth = sum(truth_labels.values())
    print(f"{'label':22}{'pred':>8}{'truth':>8}{'delta':>9}{'pred%':>8}{'true%':>8}{'paper%':>8}")
    for label in sorted(set(predicted_labels) | set(truth_labels),
                        key=lambda name: -truth_labels[name]):
        mine = predicted_labels[label]
        theirs = truth_labels[label]
        print(f"{label:22}{mine:>8,}{theirs:>8,}{mine - theirs:>+9,}"
              f"{mine / max(total_predicted, 1) * 100:>7.1f}%"
              f"{theirs / max(total_truth, 1) * 100:>7.1f}%"
              f"{PAPER_LABEL_SHARE.get(label, 0) * 100:>7.1f}%")
    print(f"{'TOTAL':22}{total_predicted:>8,}{total_truth:>8,}"
          f"{total_predicted - total_truth:>+9,}")

    print(f"\n--- net over/under-generation per part ---")
    for label, delta in sorted(per_part_error.items(), key=lambda item: -abs(item[1])):
        print(f"  {label:22}{delta / max(parts_done, 1):>+8.3f} per part")

    print(f"\n{rule}\nPER-PART ACCURACY (what F-037 actually scores)\n{rule}")
    print(f"{'label':22}{'net/part':>11}{'|err|/part':>12}{'parts wrong':>13}")
    for label, absolute in sorted(per_part_abs.items(), key=lambda item: -item[1]):
        print(f"  {label:20}{per_part_error[label] / parts_done:>+11.3f}"
              f"{absolute / parts_done:>12.3f}"
              f"{parts_wrong[label]:>8,}/{parts_done}")
    total_abs = sum(per_part_abs.values())
    print(f"  {'TOTAL':20}{'':>11}{total_abs / parts_done:>12.3f}")

    print(f"\n  Cancellation check: net error is "
          f"{abs(sum(per_part_error.values())) / parts_done:.3f}/part but absolute "
          f"error is {total_abs / parts_done:.3f}/part.")
    print(f"  Only the absolute figure affects the score.")
    return 0


def _labels(head: str) -> tuple[str, str]:
    import re
    type_match = re.search(r"^Template Type:\s*(\S+)", head, re.MULTILINE)
    subtype_match = re.search(r"^Template Subtype:\s*(.+?)\s*$", head, re.MULTILINE)
    if not type_match or not subtype_match:
        raise ValueError("no labels")
    return type_match.group(1), subtype_match.group(1)


if __name__ == "__main__":
    raise SystemExit(main())
