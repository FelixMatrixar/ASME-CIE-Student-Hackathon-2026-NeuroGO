#!/usr/bin/env python3
"""Is the order of tool blocks predictable from part geometry?

Alignment is the ceiling on three tiers at once. `diagnose_tools.py` measured only
**45.4% of operation slots aligned** with ground truth, so even perfect tool
choice caps the tool tier at 9.08/20, and medium and paths are gated the same way.

F-027 established that a plan is a sequence of contiguous tool blocks whose
*order varies between parts* -- "chamfers, then pockets, then holes" holds for
just 54.45%. We currently emit that fixed order always.

With three feature families there are only six possible orders. This asks two
questions:

1. What is the distribution over those six? If one dominates, the ceiling on a
   fixed order is simply its share.
2. Can part-level geometry predict which one? If yes, the same recipe that fixed
   hole chains (F-047) applies. If no, a fixed order is the right answer and the
   ceiling is real.
"""

from __future__ import annotations

import argparse
import collections
import csv
import pathlib
import re
import statistics
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from machineplan.features import extract_features  # noqa: E402
from machineplan.parsing.dataset import MachinePlanDataset  # noqa: E402
from machineplan.parsing.step import parse_step  # noqa: E402

SOLUTION = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = SOLUTION / "data" / "MachinePlan-10K.zip"
DEFAULT_OUT = SOLUTION / "data" / "block_order.csv"
HEAD_BYTES = 400
_SUB = re.compile(r"^Template Subtype:\s*(.+?)\s*$", re.MULTILINE)

FAMILY = {
    "AREA_MILL": "C",       # chamfer
    "FLOOR_WALL": "P",      # pocket
    "DRILLING": "H",        # hole
    "SPOT_DRILLING": "H",
    "DEEP_HOLE_DRILLING": "H",
    "HOLE_MILLING": "H",
    "BORING_REAMING": "H",
}

FEATURES = [
    "n_holes", "n_floors", "n_chamfers", "n_blends",
    "stock_length", "stock_width", "stock_height",
    "max_hole_diameter", "mean_hole_depth", "max_pocket_depth", "n_through",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=pathlib.Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--limit", type=int, default=10000)
    parser.add_argument("--holdout-from", type=int, default=8000)
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    arguments = parser.parse_args()

    rows: list[dict] = []
    orders: collections.Counter[str] = collections.Counter()

    with MachinePlanDataset(arguments.archive) as dataset:
        parts = list(dataset)[: arguments.limit]
        print(f"scanning {len(parts)} parts...\n")

        for number, part in enumerate(parts, start=1):
            if number % 1000 == 0:
                print(f"  {number}/{len(parts)}")
            if not part.brep:
                continue

            sequence: list[str] = []
            for index in sorted(part.operations):
                member = part.operations[index].details
                if not member:
                    continue
                with dataset.open(member) as handle:
                    head = handle.read(HEAD_BYTES).decode("utf-8", errors="replace")
                match = _SUB.search(head)
                if not match:
                    continue
                family = FAMILY.get(match.group(1))
                if family and (not sequence or sequence[-1] != family):
                    sequence.append(family)
            if not sequence:
                continue

            # Order of first appearance, deduplicated: CPH, HCP, ...
            seen: list[str] = []
            for family in sequence:
                if family not in seen:
                    seen.append(family)
            label = "".join(seen)
            orders[label] += 1

            try:
                features = extract_features(parse_step(dataset.read_text(part.brep)))
            except Exception:  # noqa: BLE001
                continue
            holes = features.holes
            rows.append(
                {
                    "part_id": part.part_id,
                    "n_holes": len(holes),
                    "n_floors": len(features.pocket_floors),
                    "n_chamfers": len(features.chamfers),
                    "n_blends": len(features.blends),
                    "stock_length": round(features.stock_length, 2),
                    "stock_width": round(features.stock_width, 2),
                    "stock_height": round(features.stock_height, 2),
                    "max_hole_diameter": round(max((h.diameter_mm for h in holes), default=0.0), 2),
                    "mean_hole_depth": round(
                        statistics.fmean([h.depth_mm for h in holes]) if holes else 0.0, 2),
                    "max_pocket_depth": round(
                        max((features.stock_high[2] - f.z for f in features.pocket_floors),
                            default=0.0), 2),
                    "n_through": sum(
                        1 for h in holes if h.depth_type(features.stock_low[2]) == "through"),
                    "order": label,
                }
            )

    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    with open(arguments.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    rule = "=" * 78
    total = sum(orders.values())
    print(f"\n{rule}\nBLOCK ORDER DISTRIBUTION ({total:,} parts)\n{rule}")
    for label, count in orders.most_common():
        print(f"  {label:6} {count:6,}  {count / total * 100:5.1f}%  "
              f"{'#' * min(count // 40, 55)}")
    print("\n  C = chamfer (AREA_MILL), P = pocket (FLOOR_WALL), H = hole")
    print(f"  our fixed order is CPH -> correct on {orders.get('CPH', 0) / total * 100:.1f}% "
          f"of parts by first-appearance order")

    # --- is it predictable? -------------------------------------------------
    def part_number(part_id: str) -> int:
        digits = "".join(c for c in part_id if c.isdigit())
        return int(digits) if digits else 0

    train = [r for r in rows if part_number(r["part_id"]) < arguments.holdout_from]
    test = [r for r in rows if part_number(r["part_id"]) >= arguments.holdout_from]
    if not train or not test:
        return 0

    counts = collections.Counter(r["order"] for r in train)
    keep = {label for label, count in counts.items() if count >= 20}
    train = [r for r in train if r["order"] in keep]
    test = [r for r in test if r["order"] in keep]

    x_train = np.array([[float(r[f]) for f in FEATURES] for r in train])
    y_train = [r["order"] for r in train]
    x_test = np.array([[float(r[f]) for f in FEATURES] for r in test])
    y_test = np.array([r["order"] for r in test])

    from sklearn.ensemble import HistGradientBoostingClassifier

    model = HistGradientBoostingClassifier(max_iter=300, random_state=0)
    model.fit(x_train, y_train)
    accuracy = float(np.mean(model.predict(x_test) == y_test))
    majority = collections.Counter(y_train).most_common(1)[0][0]
    majority_accuracy = float(np.mean(y_test == majority))

    print(f"\n{rule}\nIS BLOCK ORDER PREDICTABLE? (held-out parts)\n{rule}")
    print(f"  always predict {majority:6}  {majority_accuracy:.3f}")
    print(f"  gradient boosting     {accuracy:.3f}")
    print(f"  gain                  {accuracy - majority_accuracy:+.3f}")
    if accuracy - majority_accuracy < 0.02:
        print("\n  Not predictable from part geometry. A fixed order is the right")
        print("  answer, and the alignment ceiling it implies is real.")
        return 0

    import joblib

    target = SOLUTION / "data" / "block_order_model.joblib"
    joblib.dump({"model": model, "features": FEATURES}, target)
    print(f"\nsaved -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
