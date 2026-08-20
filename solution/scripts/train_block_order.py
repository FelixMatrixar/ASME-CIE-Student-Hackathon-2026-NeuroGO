#!/usr/bin/env python3
"""Fit and save the block-order classifier from the mined table.

Split out from `mine_block_order.py` so the model can be refitted without
re-scanning 10,000 parts -- and so it is obvious whether a model was actually
written. That distinction cost a wrong result once: the planner's measured "+2.09"
came from changing the fallback order (CPH -> HCP), not from a model, because the
save step had been added to the mining script but the script never re-run.
"""

from __future__ import annotations

import argparse
import collections
import csv
import pathlib
import sys

import numpy as np

SOLUTION = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_DATA = SOLUTION / "data" / "block_order.csv"
DEFAULT_MODEL = SOLUTION / "data" / "block_order_model.joblib"

FEATURES = [
    "n_holes", "n_floors", "n_chamfers", "n_blends",
    "stock_length", "stock_width", "stock_height",
    "max_hole_diameter", "mean_hole_depth", "max_pocket_depth", "n_through",
]


def part_number(part_id: str) -> int:
    digits = "".join(c for c in part_id if c.isdigit())
    return int(digits) if digits else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=pathlib.Path, default=DEFAULT_DATA)
    parser.add_argument("--model-out", type=pathlib.Path, default=DEFAULT_MODEL)
    parser.add_argument("--holdout-from", type=int, default=8000)
    parser.add_argument("--min-count", type=int, default=20)
    arguments = parser.parse_args()

    with open(arguments.data, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    counts = collections.Counter(row["order"] for row in rows)
    keep = {label for label, count in counts.items() if count >= arguments.min_count}
    dropped = sum(count for label, count in counts.items() if label not in keep)
    rows = [row for row in rows if row["order"] in keep]
    if dropped:
        print(f"filtered {dropped} parts in orders seen < {arguments.min_count} times")

    train = [r for r in rows if part_number(r["part_id"]) < arguments.holdout_from]
    test = [r for r in rows if part_number(r["part_id"]) >= arguments.holdout_from]
    print(f"train {len(train):,} parts (number < {arguments.holdout_from}) / test {len(test):,}")

    def matrix(subset):
        return np.array([[float(r[f]) for f in FEATURES] for r in subset])

    from sklearn.ensemble import HistGradientBoostingClassifier

    model = HistGradientBoostingClassifier(max_iter=300, random_state=0)
    model.fit(matrix(train), [r["order"] for r in train])

    y_test = np.array([r["order"] for r in test])
    accuracy = float(np.mean(model.predict(matrix(test)) == y_test))
    majority = collections.Counter(r["order"] for r in train).most_common(1)[0][0]
    majority_accuracy = float(np.mean(y_test == majority))

    print(f"\n  always predict {majority:6} {majority_accuracy:.3f}")
    print(f"  gradient boosting     {accuracy:.3f}")
    print(f"  gain                  {accuracy - majority_accuracy:+.3f}")

    if accuracy - majority_accuracy < 0.02:
        print("\nnot saved: no clear gain over the modal order")
        return 0

    import joblib

    arguments.model_out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": FEATURES}, arguments.model_out)
    print(f"\nsaved -> {arguments.model_out}  ({arguments.model_out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
