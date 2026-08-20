#!/usr/bin/env python3
"""Train a classifier that maps hole geometry to its operation chain.

F-046 records three hand-built rules that each matched a marginal and lost
points, because no threshold I could find separates the groups. This asks whether
a learned boundary can, using the same features and honest evaluation.

**The split is by part, not by hole.** Holes on one part share a block, a feature
mix and a tool set, so a random split over holes would put near-duplicates on
both sides and report an inflated score.

**The baseline is the current rule set**, not chance. A classifier that cannot
beat the hand-written rules is not worth shipping, and reporting only accuracy
against a majority-class baseline would hide that.
"""

from __future__ import annotations

import argparse
import collections
import csv
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from machineplan.features import Hole  # noqa: E402
from machineplan.predict import plan_hole  # noqa: E402

SOLUTION = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_DATA = SOLUTION / "data" / "hole_chains.csv"
DEFAULT_MODEL = SOLUTION / "data" / "hole_chain_model.joblib"

FEATURES = [
    "diameter_mm", "depth_mm", "aspect", "through", "top_drop",
    "depth_fraction", "stock_height", "n_holes", "same_diameter_count", "in_pocket",
]


def load(path: pathlib.Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def rule_prediction(row: dict) -> str:
    """What the current hand-written rules would emit for this hole."""
    diameter = float(row["diameter_mm"])
    depth = float(row["depth_mm"])
    through = row["through"] == "1"
    # plan_hole works from a Hole plus the stock bottom; reconstruct both so the
    # comparison runs the real code path rather than a re-implementation.
    top_z = float(row["stock_height"])
    hole = Hole(
        diameter_mm=diameter,
        x=0.0,
        y=0.0,
        top_z=top_z,
        bottom_z=top_z - depth,
    )
    stock_bottom = top_z - depth if through else -1e6
    return "|".join(op.o2 for op in plan_hole(hole, stock_bottom))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=pathlib.Path, default=DEFAULT_DATA)
    parser.add_argument("--model-out", type=pathlib.Path, default=DEFAULT_MODEL)
    parser.add_argument("--test-fraction", type=float, default=0.25)
    parser.add_argument("--holdout-from", type=int, default=8000,
                        help="parts with a number >= this are never trained on")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--min-chain-count", type=int, default=5,
        help="drop chains occurring fewer than this many times in the corpus",
    )
    arguments = parser.parse_args()

    rows = load(arguments.data)
    if not rows:
        print("no rows; run build_hole_dataset.py first", file=sys.stderr)
        return 2

    # --- data filtering, disclosed per Tutorial p.9 ------------------------
    # Chains seen only a handful of times cannot be learned or fairly evaluated,
    # and a class with a single member breaks the stratified validation split
    # the booster uses internally. They are dropped from *both* halves rather
    # than only from training, so the reported accuracy is not flattered by
    # quietly removing hard cases from the test set alone.
    chain_totals = collections.Counter(row["chain"] for row in rows)
    rare = {label for label, count in chain_totals.items() if count < arguments.min_chain_count}
    dropped = [row for row in rows if row["chain"] in rare]
    rows = [row for row in rows if row["chain"] not in rare]
    if dropped:
        print(f"filtered {len(dropped):,} holes ({len(dropped) / (len(rows) + len(dropped)) * 100:.2f}%) "
              f"in {len(rare)} chains occurring < {arguments.min_chain_count} times")

    # --- split by part, deterministically on the part number ---------------
    # A *random* part split is statistically fine but leaves no way to know which
    # parts the model saw, so end-to-end evaluation cannot be guaranteed disjoint
    # from training. Splitting on the part number instead means everything at or
    # above `--holdout-from` is provably unseen, and
    # `run_baseline.py --offset 8000` is an honest run by construction.
    def part_number(part_id: str) -> int:
        digits = "".join(character for character in part_id if character.isdigit())
        return int(digits) if digits else 0

    train = [row for row in rows if part_number(row["part_id"]) < arguments.holdout_from]
    test = [row for row in rows if part_number(row["part_id"]) >= arguments.holdout_from]
    if not train or not test:
        print("empty split; check --holdout-from", file=sys.stderr)
        return 2

    train_parts = {row["part_id"] for row in train}
    test_parts = {row["part_id"] for row in test}
    print(f"{len(rows):,} holes over {len(train_parts) + len(test_parts):,} parts")
    print(f"  train {len(train):,} holes / {len(train_parts):,} parts (number < {arguments.holdout_from})")
    print(f"  test  {len(test):,} holes / {len(test_parts):,} parts (number >= {arguments.holdout_from})")

    def matrix(subset: list[dict]) -> np.ndarray:
        return np.array([[float(row[name]) for name in FEATURES] for row in subset])

    x_train, y_train = matrix(train), [row["chain"] for row in train]
    x_test, y_test = matrix(test), [row["chain"] for row in test]

    # --- baselines ---------------------------------------------------------
    majority = collections.Counter(y_train).most_common(1)[0][0]
    majority_accuracy = sum(1 for y in y_test if y == majority) / len(y_test)

    rule_correct = sum(1 for row in test if rule_prediction(row) == row["chain"])
    rule_accuracy = rule_correct / len(test)

    # --- model -------------------------------------------------------------
    from sklearn.ensemble import HistGradientBoostingClassifier

    model = HistGradientBoostingClassifier(
        max_iter=300,
        learning_rate=0.1,
        max_leaf_nodes=31,
        l2_regularization=1.0,
        random_state=arguments.seed,
    )
    model.fit(x_train, y_train)
    predictions = model.predict(x_test)
    model_accuracy = float(np.mean(predictions == np.array(y_test)))

    rule = "=" * 78
    print(f"\n{rule}\nCHAIN PREDICTION ACCURACY (held-out parts)\n{rule}")
    print(f"  majority class      {majority_accuracy:6.3f}   ({majority})")
    print(f"  current rules       {rule_accuracy:6.3f}")
    print(f"  gradient boosting   {model_accuracy:6.3f}")
    delta = model_accuracy - rule_accuracy
    print(f"\n  model vs rules      {delta:+6.3f}  "
          f"({'ship it' if delta > 0.02 else 'not clearly better'})")

    # --- where each one wins ----------------------------------------------
    print(f"\n--- per-chain recall (test set) ---")
    print(f"{'chain':52}{'n':>6}{'rules':>8}{'model':>8}")
    by_chain: dict[str, list[int]] = collections.defaultdict(list)
    for index, row in enumerate(test):
        by_chain[row["chain"]].append(index)
    for label, indices in sorted(by_chain.items(), key=lambda item: -len(item[1]))[:12]:
        rules_hit = sum(1 for i in indices if rule_prediction(test[i]) == label)
        model_hit = sum(1 for i in indices if predictions[i] == label)
        print(f"{label[:50]:52}{len(indices):>6,}"
              f"{rules_hit / len(indices):>8.3f}{model_hit / len(indices):>8.3f}")

    # --- operation-count error, which is what actually scores --------------
    def count_error(predicted: list[str]) -> float:
        errors = [
            abs(len(p.split("|")) - len(row["chain"].split("|")))
            for p, row in zip(predicted, test)
        ]
        return float(np.mean(errors))

    rules_counts = [rule_prediction(row) for row in test]
    print(f"\n--- mean |operation count error| per hole (F-037 is count-driven) ---")
    print(f"  current rules       {count_error(rules_counts):6.3f}")
    print(f"  gradient boosting   {count_error(list(predictions)):6.3f}")

    if delta > 0.02:
        import joblib

        arguments.model_out.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": model, "features": FEATURES}, arguments.model_out)
        print(f"\nsaved -> {arguments.model_out}")
    else:
        print("\nnot saved: the model must beat the rules by >2 points to be worth shipping")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
