#!/usr/bin/env python3
"""Are operations grouped into contiguous tool blocks?

Neither "chamfer -> pocket -> hole" (54%) nor "sort by Order Group" (28%) explains
the sequence. But the violators all share a shape: operations appear in
*contiguous runs* of the same group, and only the run order varies between parts.

That is the signature of tool-change minimisation, and `operations.json` reports
`tool_changes` per part, so the hypothesis is directly checkable: if every tool
occupies exactly one contiguous block, then `tool_changes == distinct_tools - 1`.

Consequences if true:
  * The easy tier's **F1 sub-score depends only on the multiset** of operations,
    not their order -- 10 of 20 points need no sequencing at all.
  * Levenshtein then reduces to ordering a handful of blocks rather than a
    sequence of up to 38 individual operations.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from machineplan.parsing.dataset import MachinePlanDataset  # noqa: E402

DEFAULT_ARCHIVE = pathlib.Path(__file__).resolve().parents[1] / "data" / "MachinePlan-10K.zip"


def runs(values: list[str]) -> int:
    """Number of contiguous runs in a sequence."""
    return sum(1 for index, value in enumerate(values) if index == 0 or values[index - 1] != value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=pathlib.Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--limit", type=int, default=0)
    arguments = parser.parse_args()

    tools_contiguous = 0
    tools_scattered = 0
    names_contiguous = 0
    changes_match = 0
    changes_mismatch = 0
    total_parts = 0
    total_operations = 0

    block_counts: collections.Counter[int] = collections.Counter()
    excess_runs: collections.Counter[int] = collections.Counter()
    scattered_examples: list[tuple[str, list[str]]] = []

    with MachinePlanDataset(arguments.archive) as dataset:
        parts = list(dataset)
        if arguments.limit:
            parts = parts[: arguments.limit]
        print(f"scanning {len(parts)} parts...\n")

        for part in parts:
            if not part.operations_json:
                continue
            payload = json.loads(dataset.read_text(part.operations_json))
            operations = payload.get("operations", [])
            if not operations:
                continue
            total_parts += 1
            total_operations += len(operations)

            tool_sequence = [entry.get("tool_name", "?") for entry in operations]
            name_sequence = [
                re.sub(r"_\d+$", "", entry.get("name", "")) for entry in operations
            ]

            distinct_tools = len(set(tool_sequence))
            tool_runs = runs(tool_sequence)
            block_counts[tool_runs] += 1
            excess_runs[tool_runs - distinct_tools] += 1

            if tool_runs == distinct_tools:
                tools_contiguous += 1
            else:
                tools_scattered += 1
                if len(scattered_examples) < 6:
                    scattered_examples.append((part.part_id, tool_sequence))

            if runs(name_sequence) == len(set(name_sequence)):
                names_contiguous += 1

            reported = payload.get("machining_summary", {}).get("tool_changes")
            if reported is not None:
                if reported == tool_runs - 1:
                    changes_match += 1
                else:
                    changes_mismatch += 1

    rule = "=" * 78
    print(rule)
    print(f"{total_parts:,} parts, {total_operations:,} operations")
    print(rule)

    print("\nHYPOTHESIS A: each tool occupies exactly one contiguous block")
    print(f"  holds     : {tools_contiguous:6,} / {total_parts:,}  "
          f"({tools_contiguous / total_parts * 100:.2f}%)")
    print(f"  violated  : {tools_scattered:6,} / {total_parts:,}  "
          f"({tools_scattered / total_parts * 100:.2f}%)")

    print("\nHYPOTHESIS B: each operation *name* occupies one contiguous block")
    print(f"  holds     : {names_contiguous:6,} / {total_parts:,}  "
          f"({names_contiguous / total_parts * 100:.2f}%)")

    print("\nCROSS-CHECK: metadata tool_changes == (tool blocks - 1)")
    print(f"  agree     : {changes_match:6,}")
    print(f"  disagree  : {changes_mismatch:6,}")

    print("\n--- excess tool runs beyond the number of distinct tools ---")
    print("    (0 means perfectly blocked; n means n tools were revisited)")
    for excess in sorted(excess_runs):
        count = excess_runs[excess]
        print(f"  +{excess:<3} {count:6,}  {count / total_parts * 100:5.2f}%  "
              f"{'#' * min(count // 60, 60)}")

    print("\n--- tool blocks per part ---")
    for blocks in sorted(block_counts):
        count = block_counts[blocks]
        print(f"  {blocks:3d} blocks {count:6,}  {'#' * min(count // 40, 60)}")

    if scattered_examples:
        print("\n--- examples where a tool is revisited ---")
        for part_id, sequence in scattered_examples:
            print(f"  {part_id}: {' '.join(sequence)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
