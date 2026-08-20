#!/usr/bin/env python3
"""Where does the tool tier lose its 13 points?

The tools tier has never been analysed. It scores each operation on two
attributes, and the rubric makes them very unequal: **a wrong tool type scores
zero for the operation regardless of diameter**, while an exact type with a
diameter within 2% scores full marks.

So the tier decomposes cleanly and the two halves need different fixes:

    points = f(type correct?) x g(relative diameter error)

This measures both separately, against ground truth, over the full corpus. It
also separates *alignment* error (our operation k is a different kind of
operation from truth's k) from genuine tool-choice error, since the first is a
sequence problem wearing a tool problem's clothing.
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
from machineplan.scoring.rubric import RELATIVE_SIZE_ERROR_BANDS, score_lower_is_better  # noqa: E402

SOLUTION = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = SOLUTION / "data" / "MachinePlan-10K.zip"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=pathlib.Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--limit", type=int, default=400)
    parser.add_argument("--offset", type=int, default=8000, help="held-out range")
    arguments = parser.parse_args()

    aligned = 0
    misaligned = 0
    type_hits = 0
    errors_by_type: dict[str, list[float]] = collections.defaultdict(list)
    points_by_type: dict[str, list[float]] = collections.defaultdict(list)
    confusion: collections.Counter[tuple[str, str]] = collections.Counter()
    truth_diameter_by_type: dict[str, list[float]] = collections.defaultdict(list)
    ours_diameter_by_type: dict[str, list[float]] = collections.defaultdict(list)

    with MachinePlanDataset(arguments.archive) as dataset:
        parts = list(dataset)[arguments.offset : arguments.offset + arguments.limit]
        print(f"scanning {len(parts)} held-out parts (offset {arguments.offset})...\n")

        for part in parts:
            if not part.brep:
                continue
            try:
                features = extract_features(parse_step(dataset.read_text(part.brep)))
                plan = plan_part(part.part_id, features)
            except Exception:  # noqa: BLE001
                continue

            truth: list[tuple[str, float, str]] = []
            for index in sorted(part.operations):
                member = part.operations[index].details
                if not member:
                    continue
                details = parse_details(dataset.read_text(member))
                tool = details.tool
                truth.append(
                    (
                        (tool.tool_type if tool else None) or "unknown",
                        (tool.diameter_mm if tool else None) or 0.0,
                        details.o2,
                    )
                )

            for index in range(max(len(plan.operations), len(truth))):
                if index >= len(plan.operations) or index >= len(truth):
                    misaligned += 1
                    continue
                operation = plan.operations[index]
                truth_type, truth_diameter, truth_o2 = truth[index]

                if operation.o2 != truth_o2:
                    # Different kind of operation entirely: this is a sequence
                    # error surfacing in the tool tier, not a tool-choice error.
                    misaligned += 1
                    continue
                aligned += 1

                confusion[(truth_type, operation.tool_type)] += 1
                truth_diameter_by_type[truth_type].append(truth_diameter)
                ours_diameter_by_type[truth_type].append(operation.tool_diameter_mm)

                if operation.tool_type != truth_type:
                    points_by_type[truth_type].append(0.0)
                    continue
                type_hits += 1
                if truth_diameter <= 0:
                    points_by_type[truth_type].append(0.0)
                    continue
                relative = abs(operation.tool_diameter_mm - truth_diameter) / truth_diameter
                errors_by_type[truth_type].append(relative)
                points_by_type[truth_type].append(
                    score_lower_is_better(relative, RELATIVE_SIZE_ERROR_BANDS)
                )

    total = aligned + misaligned
    rule = "=" * 78
    print(rule)
    print(f"{total:,} operation slots: {aligned:,} aligned ({aligned / total * 100:.1f}%), "
          f"{misaligned:,} misaligned ({misaligned / total * 100:.1f}%)")
    print(rule)
    print("\nMisaligned slots score zero no matter how good the tool choice is.")
    print("That share is a *sequence* problem, not a tool problem.\n")

    if aligned:
        print(f"Of the aligned slots, tool TYPE correct: {type_hits:,}/{aligned:,} "
              f"({type_hits / aligned * 100:.1f}%)\n")

    print(f"{'true tool type':16}{'n':>7}{'type ok':>9}{'dia err':>10}{'pts/10':>8}"
          f"{'our dia':>10}{'true dia':>10}")
    print("-" * 78)
    for tool_type in sorted(points_by_type, key=lambda t: -len(points_by_type[t])):
        points = points_by_type[tool_type]
        errors = errors_by_type.get(tool_type, [])
        hits = sum(1 for (t, o), c in confusion.items() if t == tool_type and o == tool_type
                   for _ in range(c))
        total_type = sum(c for (t, _), c in confusion.items() if t == tool_type)
        print(f"{tool_type:16}{len(points):>7,}"
              f"{hits / max(total_type, 1):>9.3f}"
              f"{(statistics.fmean(errors) if errors else float('nan')):>10.3f}"
              f"{statistics.fmean(points):>8.2f}"
              f"{statistics.fmean(ours_diameter_by_type[tool_type]):>10.2f}"
              f"{statistics.fmean(truth_diameter_by_type[tool_type]):>10.2f}")

    print(f"\n--- type confusion (true -> ours), top mismatches ---")
    for (truth_type, ours), count in confusion.most_common(40):
        if truth_type == ours:
            continue
        print(f"  {truth_type:16} -> {ours:16} {count:6,}")

    if points_by_type:
        overall = [p for values in points_by_type.values() for p in values]
        print(f"\n--- headroom ---")
        print(f"  mean points on aligned slots : {statistics.fmean(overall):.2f} / 10")
        print(f"  aligned share                : {aligned / total:.3f}")
        print(f"  => tier estimate             : "
              f"{statistics.fmean(overall) / 10 * (aligned / total) * 20:.2f} / 20")
        print(f"  perfect tools on current alignment would give "
              f"{(aligned / total) * 20:.2f} / 20")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
