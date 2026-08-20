#!/usr/bin/env python3
"""Does our held-out score transfer to the released test set?

The test folders contain only the boundary representation and renders, so there
is no ground truth and we cannot score ourselves on them directly. Our best
estimate is the held-out score on corpus parts the models never saw, but that
estimate is only meaningful if the two sets look alike.

This compares the recognised feature distributions, and then checks whether our
per-part score depends on complexity. If test parts are systematically more
complex and our score falls with complexity, the held-out figure is optimistic
and we should say so rather than quote it plainly.
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from machineplan.features import extract_features  # noqa: E402
from machineplan.parsing.dataset import MachinePlanDataset  # noqa: E402
from machineplan.parsing.step import parse_step  # noqa: E402
from machineplan.predict import plan_part  # noqa: E402

SOLUTION = pathlib.Path(__file__).resolve().parents[1]
REPO = SOLUTION.parent
DEFAULT_TEST = REPO / "Test_Data"
DEFAULT_ARCHIVE = SOLUTION / "data" / "MachinePlan-10K.zip"
DEFAULT_SCORES = SOLUTION / "outputs" / "eval_final.csv"


def summarise(name: str, rows: list[dict]) -> None:
    print(f"\n{name}  ({len(rows)} parts)")
    for key, label in (
        ("ops", "predicted operations"),
        ("holes", "holes"),
        ("pockets", "pocket floors"),
        ("chamfers", "chamfer faces"),
        ("height", "block height, mm"),
    ):
        values = [r[key] for r in rows]
        print(f"    {label:22} mean {statistics.fmean(values):7.2f}   "
              f"range {min(values):6.1f} to {max(values):6.1f}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", type=pathlib.Path, default=DEFAULT_TEST)
    parser.add_argument("--archive", type=pathlib.Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--scores", type=pathlib.Path, default=DEFAULT_SCORES)
    parser.add_argument("--offset", type=int, default=8000)
    parser.add_argument("--limit", type=int, default=400)
    arguments = parser.parse_args()

    def describe(part_id: str, features) -> dict:
        plan = plan_part(part_id, features)
        return {
            "part_id": part_id,
            "ops": len(plan.operations),
            "holes": len(features.holes),
            "pockets": len(features.pocket_floors),
            "chamfers": len(features.chamfers),
            "height": features.stock_height,
        }

    test_rows: list[dict] = []
    for folder in sorted(p for p in arguments.test.iterdir() if p.is_dir()):
        step = next((c for c in sorted(folder.iterdir())
                     if c.suffix.lower() in (".stp", ".step")), None)
        if step is None:
            continue
        features = extract_features(parse_step(step.read_text(encoding="utf-8", errors="replace")))
        test_rows.append(describe(folder.name, features))

    holdout_rows: list[dict] = []
    with MachinePlanDataset(arguments.archive) as dataset:
        for part in list(dataset)[arguments.offset : arguments.offset + arguments.limit]:
            if not part.brep:
                continue
            try:
                features = extract_features(parse_step(dataset.read_text(part.brep)))
            except Exception:  # noqa: BLE001
                continue
            holdout_rows.append(describe(part.part_id, features))

    rule = "=" * 74
    print(rule)
    print("FEATURE DISTRIBUTION: released test set against our held-out sample")
    print(rule)
    summarise("Released test set", test_rows)
    summarise(f"Held-out corpus parts (>= {arguments.offset})", holdout_rows)

    test_ops = statistics.fmean(r["ops"] for r in test_rows)
    hold_ops = statistics.fmean(r["ops"] for r in holdout_rows)
    print(f"\n  Test parts carry {test_ops / hold_ops:.2f}x the operations of our held-out sample.")

    # --- does our score depend on complexity? ------------------------------
    if not arguments.scores.exists():
        print(f"\n(no scores at {arguments.scores}; run evaluate.py first)")
        return 0

    with open(arguments.scores, newline="", encoding="utf-8") as handle:
        scored = {r["part_id"]: r for r in csv.DictReader(handle)}
    joined = [
        (r["ops"], float(scored[r["part_id"]]["total"]))
        for r in holdout_rows if r["part_id"] in scored
    ]
    if len(joined) < 10:
        return 0

    print(f"\n{rule}")
    print("DOES OUR SCORE FALL AS PARTS GET MORE COMPLEX?")
    print(rule)
    buckets: dict[str, list[float]] = {}
    for ops, total in joined:
        if ops <= 8:
            key = "  <= 8 operations"
        elif ops <= 13:
            key = "  9 to 13"
        elif ops <= 20:
            key = " 14 to 20"
        else:
            key = " over 20"
        buckets.setdefault(key, []).append(total)
    print(f"{'predicted operations':24}{'parts':>7}{'mean score of 75':>20}")
    for key in sorted(buckets):
        values = buckets[key]
        print(f"{key:24}{len(values):>7}{statistics.fmean(values):>20.2f}")

    xs = [float(o) for o, _ in joined]
    ys = [t for _, t in joined]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    print(f"\n  correlation between operation count and score: {cov / den:+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
