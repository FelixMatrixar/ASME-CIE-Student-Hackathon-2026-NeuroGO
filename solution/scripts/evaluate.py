#!/usr/bin/env python3
"""Rigorous evaluation: held-out parts, confidence intervals, paired comparison.

`run_baseline.py` reports a point estimate on a handful of parts, which is enough
to see a pipeline working and **not** enough to choose between configurations.
Several decisions in this project were made on 8-30 parts with differences under
a point; this exists to find out which of them were real.

What it adds:

* **Confidence intervals** by bootstrap over parts, so a difference can be judged
  against its own noise.
* **Paired comparison** -- both configurations are scored on the *same* parts and
  the per-part differences are bootstrapped. Pairing removes between-part
  variance, which dominates here (medium scores are 0 or 20+ with little between).
* **Held-out by construction** -- `--offset` past the classifier's training range.

Run with `--config rules` and `--config model` over the same parts to compare.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import pathlib
import statistics
import sys

import numpy as np
import trimesh

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from machineplan.features import extract_features  # noqa: E402
from machineplan.generate import generate_part  # noqa: E402
from machineplan.parsing.dataset import MachinePlanDataset  # noqa: E402
from machineplan.parsing.details import parse_details  # noqa: E402
from machineplan.parsing.step import parse_step  # noqa: E402
from machineplan.predict import plan_part  # noqa: E402
from machineplan.scoring.easy import score_easy  # noqa: E402
from machineplan.scoring.geometry import as_solid  # noqa: E402
from machineplan.scoring.hard import ToolPrediction, score_tools  # noqa: E402
from machineplan.scoring.medium import score_medium  # noqa: E402
from machineplan.vocab import Operation  # noqa: E402

SOLUTION = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = SOLUTION / "data" / "MachinePlan-10K.zip"
MODEL_PATH = SOLUTION / "data" / "hole_chain_model.joblib"


def bootstrap_ci(values: list[float], iterations: int = 5000, seed: int = 0) -> tuple[float, float]:
    """Percentile bootstrap 95% interval for the mean."""
    if len(values) < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    array = np.asarray(values, dtype=float)
    means = array[rng.integers(0, len(array), size=(iterations, len(array)))].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def evaluate(dataset: MachinePlanDataset, parts, skip_medium: bool) -> list[dict]:
    rows: list[dict] = []
    for part in parts:
        if not part.brep:
            continue
        try:
            features = extract_features(parse_step(dataset.read_text(part.brep)))
            plan = plan_part(part.part_id, features)
        except Exception:  # noqa: BLE001
            continue

        truth_sequence: list[Operation] = []
        truth_tools: list[ToolPrediction] = []
        for index in sorted(part.operations):
            member = part.operations[index].details
            if not member:
                continue
            details = parse_details(dataset.read_text(member))
            truth_sequence.append(Operation(details.o1, details.o2))
            tool = details.tool
            truth_tools.append(
                ToolPrediction(
                    (tool.tool_type if tool else None) or "unknown",
                    (tool.diameter_mm if tool else None) or 0.0,
                )
            )
        if not truth_sequence:
            continue

        easy = score_easy(plan.sequence, truth_sequence)
        tools = score_tools(
            [ToolPrediction(op.tool_type, op.tool_diameter_mm) for op in plan.operations],
            truth_tools,
        )

        medium_points = 0.0
        if not skip_medium:
            try:
                generated = generate_part(plan, features)
                truth_ipws = [
                    trimesh.load(io.BytesIO(dataset.read_bytes(part.operations[i].mesh)),
                                 file_type="stl")
                    for i in sorted(part.operations) if part.operations[i].mesh
                ]
                medium_points = score_medium(
                    [as_solid(m) for m in generated.ipws],
                    [as_solid(m) for m in truth_ipws],
                ).points
            except Exception:  # noqa: BLE001
                medium_points = 0.0

        rows.append(
            {
                "part_id": part.part_id,
                "easy": easy.points,
                "medium": medium_points,
                "tools": tools.points,
                "total": easy.points + medium_points + tools.points,
                "predicted_ops": len(plan.operations),
                "true_ops": len(truth_sequence),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=pathlib.Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--limit", type=int, default=150)
    parser.add_argument("--offset", type=int, default=3000, help="past the training range")
    parser.add_argument("--skip-medium", action="store_true")
    parser.add_argument("--out", type=pathlib.Path, help="write per-part scores as CSV")
    parser.add_argument("--compare", type=pathlib.Path,
                        help="a CSV from a previous run, for a paired comparison")
    arguments = parser.parse_args()

    with MachinePlanDataset(arguments.archive) as dataset:
        parts = list(dataset)[arguments.offset : arguments.offset + arguments.limit]
        print(f"evaluating {len(parts)} parts from offset {arguments.offset} "
              f"(model {'present' if MODEL_PATH.exists() else 'ABSENT -> rules'})\n")
        rows = evaluate(dataset, parts, arguments.skip_medium)

    if not rows:
        print("no parts scored", file=sys.stderr)
        return 2

    rule = "=" * 78
    print(rule)
    print(f"{len(rows)} parts scored")
    print(rule)
    print(f"{'tier':10}{'mean':>9}{'95% CI':>22}{'sd':>8}")
    for tier, budget in (("easy", 20), ("medium", 35), ("tools", 20), ("total", 75)):
        values = [row[tier] for row in rows]
        low, high = bootstrap_ci(values)
        sd = statistics.pstdev(values)
        print(f"{tier:10}{statistics.fmean(values):>9.2f}"
              f"{f'[{low:.2f}, {high:.2f}]':>22}{sd:>8.2f}   / {budget}")

    ratios = [min(r["predicted_ops"], r["true_ops"]) / max(r["predicted_ops"], r["true_ops"])
              for r in rows]
    print(f"\nmean length ratio {statistics.fmean(ratios):.4f}")

    if arguments.out:
        arguments.out.parent.mkdir(parents=True, exist_ok=True)
        with open(arguments.out, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nwrote {arguments.out}")

    if arguments.compare and arguments.compare.exists():
        with open(arguments.compare, newline="", encoding="utf-8") as handle:
            other = {row["part_id"]: row for row in csv.DictReader(handle)}
        paired = [(row, other[row["part_id"]]) for row in rows if row["part_id"] in other]
        if paired:
            print(f"\n{rule}\nPAIRED COMPARISON vs {arguments.compare.name} "
                  f"({len(paired)} shared parts)\n{rule}")
            print(f"{'tier':10}{'this':>9}{'other':>9}{'diff':>9}{'95% CI of diff':>24}")
            for tier in ("easy", "medium", "tools", "total"):
                deltas = [row[tier] - float(o[tier]) for row, o in paired]
                low, high = bootstrap_ci(deltas)
                mine = statistics.fmean([row[tier] for row, _ in paired])
                theirs = statistics.fmean([float(o[tier]) for _, o in paired])
                verdict = "significant" if (low > 0 or high < 0) else "NOT significant"
                print(f"{tier:10}{mine:>9.2f}{theirs:>9.2f}{mine - theirs:>+9.2f}"
                      f"{f'[{low:+.2f}, {high:+.2f}]':>20}  {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
