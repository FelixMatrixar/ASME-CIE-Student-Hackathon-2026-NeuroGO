#!/usr/bin/env python3
"""Q-008: what structure is there in the operation sequences?

Scans every part's ``operations.json`` -- 10,000 small files rather than the
91,702 ``details.txt`` reports -- and asks the questions that decide whether this
is a learning problem or a rule-recovery problem:

1. What is the ``name`` vocabulary, and does it leak the feature being cut?
2. What is the ``type`` vocabulary, and how does it relate to (o1, o2)?
3. **Is the sequence canonically ordered?** The CAD generator adds features in a
   fixed order (chamfers, then pockets, then holes). If the machining plan
   follows the same order, an enormous amount of sequence structure is free.
4. What do the operation-to-operation transitions look like?
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

# Coarse family for the ordering test, inferred from the operation name.
CHAMFER = "chamfer"
POCKET = "pocket"
HOLE = "hole"
FAMILY_ORDER = {CHAMFER: 0, POCKET: 1, HOLE: 2}


def classify(name: str, op_type: str) -> str | None:
    """Bucket an operation into chamfer / pocket / hole by its NX name."""
    upper = name.upper()
    if "CHAMFER" in upper or upper.startswith("AREA_MILL"):
        return CHAMFER
    if "DRILL" in upper or "REAM" in upper or "BORE" in upper or "HOLE" in upper:
        # "HOLE_MILLING" of a large hole is still a hole feature.
        return HOLE
    if "MILL" in upper or "POCKET" in upper or "NOTCH" in upper or "SLOT" in upper:
        return POCKET
    return None


def strip_suffix(name: str) -> str:
    """``AREA_MILL_1`` and ``AREA_MILL_12`` collapse onto ``AREA_MILL``."""
    return re.sub(r"_\d+$", "", name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=pathlib.Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--limit", type=int, default=0, help="parts to scan (0 = all)")
    parser.add_argument("--top", type=int, default=30)
    arguments = parser.parse_args()

    names: collections.Counter[str] = collections.Counter()
    types: collections.Counter[str] = collections.Counter()
    transitions: collections.Counter[tuple[str, str]] = collections.Counter()
    family_counts: collections.Counter[str] = collections.Counter()
    tools_per_name: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)

    ordered_parts = 0
    unordered_parts = 0
    unordered_examples: list[tuple[str, list[str]]] = []
    unclassified: collections.Counter[str] = collections.Counter()
    total_parts = 0
    total_operations = 0
    repeat_runs = 0

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

            families: list[str] = []
            previous_base: str | None = None
            for entry in operations:
                name = entry.get("name", "")
                op_type = entry.get("type", "")
                base = strip_suffix(name)
                names[base] += 1
                types[op_type] += 1
                tools_per_name[base][entry.get("tool_name", "?")] += 1
                if previous_base is not None:
                    transitions[(previous_base, base)] += 1
                    if previous_base == base:
                        repeat_runs += 1
                previous_base = base

                family = classify(name, op_type)
                if family is None:
                    unclassified[base] += 1
                else:
                    families.append(family)
                    family_counts[family] += 1

            ranks = [FAMILY_ORDER[f] for f in families]
            if ranks == sorted(ranks):
                ordered_parts += 1
            else:
                unordered_parts += 1
                if len(unordered_examples) < 8:
                    unordered_examples.append(
                        (part.part_id, [e.get("name", "") for e in operations])
                    )

    rule = "=" * 78
    print(rule)
    print(f"{total_parts} parts, {total_operations} operations")
    print(rule)

    print(f"\n--- operation `type` vocabulary ({len(types)} distinct) ---")
    for value, count in types.most_common():
        print(f"  {value:44} {count:7,}  {count / total_operations * 100:5.1f}%")

    print(f"\n--- operation `name` vocabulary ({len(names)} distinct, top {arguments.top}) ---")
    for value, count in names.most_common(arguments.top):
        tools = len(tools_per_name[value])
        print(f"  {value:44} {count:7,}  {count / total_operations * 100:5.1f}%  "
              f"{tools:3d} tool(s)")
    if len(names) > arguments.top:
        tail = sum(c for _, c in names.most_common()[arguments.top:])
        print(f"  {'... ' + str(len(names) - arguments.top) + ' more':44} {tail:7,}")

    print(f"\n--- feature family mix ---")
    total_family = sum(family_counts.values())
    for family, count in family_counts.most_common():
        print(f"  {family:12} {count:7,}  {count / total_family * 100:5.1f}%")
    if unclassified:
        print(f"  unclassified names: {len(unclassified)} distinct, "
              f"{sum(unclassified.values())} operations")
        for value, count in unclassified.most_common(8):
            print(f"     {value:40} {count:6,}")

    print(f"\n{rule}")
    print("ORDERING HYPOTHESIS: chamfer -> pocket -> hole")
    print(rule)
    checked = ordered_parts + unordered_parts
    print(f"  parts following the order : {ordered_parts:6,} / {checked:,}  "
          f"({ordered_parts / checked * 100:.2f}%)")
    print(f"  parts violating it        : {unordered_parts:6,} / {checked:,}  "
          f"({unordered_parts / checked * 100:.2f}%)")
    for part_id, sequence in unordered_examples:
        print(f"     {part_id}: {' -> '.join(sequence)}")

    print(f"\n--- consecutive repeats (same operation name back to back) ---")
    print(f"  {repeat_runs:,} of {total_operations - total_parts:,} transitions "
          f"({repeat_runs / max(total_operations - total_parts, 1) * 100:.1f}%)")

    print(f"\n--- top transitions ---")
    for (before, after), count in transitions.most_common(20):
        print(f"  {before:34} -> {after:34} {count:7,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
