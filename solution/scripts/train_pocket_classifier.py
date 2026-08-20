#!/usr/bin/env python3
"""Train a classifier for how many operations a recognised pocket floor takes.

Companion to `train_hole_classifier.py`, same discipline: split by part, compare
against the current rule rather than against chance, and refuse to ship a model
that does not clearly beat it.

The ceiling here is lower than for holes and known in advance. Of 4,644
`FLOOR_WALL` operations, **22.5% match no recognised floor at all** -- those are
pockets we fail to *find*, which no counting model can recover. Among floors we
do find, 86.9% take one operation, so the current "one op per floor" rule is
already strong and the model has only 13% of cases to win on.
"""

from __future__ import annotations

import argparse
import collections
import csv
import pathlib
import sys

import numpy as np

SOLUTION = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_DATA = SOLUTION / "data" / "pocket_counts.csv"
DEFAULT_MODEL = SOLUTION / "data" / "pocket_count_model.joblib"

FEATURES = [
    "length_mm", "width_mm", "footprint_mm2", "depth_mm", "depth_fraction",
    "corner_radius", "reach_ratio", "touches", "n_floors", "is_nested",
    "aspect", "stock_height",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=pathlib.Path, default=DEFAULT_DATA)
    parser.add_argument("--model-out", type=pathlib.Path, default=DEFAULT_MODEL)
    parser.add_argument("--test-fraction", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=0)
    arguments = parser.parse_args()

    with open(arguments.data, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        print("no rows; run build_pocket_dataset.py first", file=sys.stderr)
        return 2

    parts = sorted({row["part_id"] for row in rows})
    rng = np.random.default_rng(arguments.seed)
    rng.shuffle(parts)
    cut = int(len(parts) * (1 - arguments.test_fraction))
    train_parts = set(parts[:cut])
    train = [row for row in rows if row["part_id"] in train_parts]
    test = [row for row in rows if row["part_id"] not in train_parts]

    print(f"{len(rows):,} floors over {len(parts):,} parts")
    print(f"  train {len(train):,} floors / test {len(test):,} floors")

    def matrix(subset: list[dict]) -> np.ndarray:
        return np.array([[float(row[name]) for name in FEATURES] for row in subset])

    x_train = matrix(train)
    y_train = np.array([int(row["n_ops"]) for row in train])
    x_test = matrix(test)
    y_test = np.array([int(row["n_ops"]) for row in test])

    # The current rule: exactly one operation per recognised floor.
    rule_accuracy = float(np.mean(y_test == 1))
    rule_count_error = float(np.mean(np.abs(1 - y_test)))

    from sklearn.ensemble import HistGradientBoostingClassifier

    model = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.1, l2_regularization=1.0,
        random_state=arguments.seed,
    )
    model.fit(x_train, y_train)
    predictions = model.predict(x_test)
    model_accuracy = float(np.mean(predictions == y_test))
    model_count_error = float(np.mean(np.abs(predictions - y_test)))

    rule = "=" * 78
    print(f"\n{rule}\nOPERATIONS PER POCKET FLOOR (held-out parts)\n{rule}")
    print(f"{'predictor':28}{'accuracy':>10}{'|count error|':>16}")
    print(f"{'  always 1 (current rule)':28}{rule_accuracy:>10.3f}{rule_count_error:>16.3f}")
    print(f"{'  gradient boosting':28}{model_accuracy:>10.3f}{model_count_error:>16.3f}")

    delta = model_accuracy - rule_accuracy
    error_delta = rule_count_error - model_count_error
    print(f"\n  accuracy gain    {delta:+.3f}")
    print(f"  count-error gain {error_delta:+.3f} operations per floor")

    print(f"\n--- true distribution in the test set ---")
    for value, count in sorted(collections.Counter(y_test.tolist()).items()):
        hit = int(np.sum((predictions == value) & (y_test == value)))
        print(f"  {value} ops: {count:5,}  model recall {hit / count:.3f}")

    if error_delta > 0.01:
        import joblib

        arguments.model_out.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": model, "features": FEATURES}, arguments.model_out)
        print(f"\nsaved -> {arguments.model_out}")
    else:
        print("\nnot saved: the model does not beat 'always 1' by enough to justify it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
