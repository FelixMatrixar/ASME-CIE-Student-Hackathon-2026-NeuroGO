#!/usr/bin/env python3
"""Does NX's `Order Group` explain the machining sequence?

The naive "chamfers, then pockets, then holes" hypothesis holds for only 54% of
parts, and the violators consistently run the *reverse*. Two competing orders
means the sequence is governed by something else.

`details.txt` records an `Order Group` per operation (MILL_ROUGH, CENTER, ...),
which is NX's own scheduling bucket. If the plan is simply sorted by order group,
that *is* the deterministic rule -- and predicting the sequence reduces to
predicting a bag of operations plus a fixed sort key.

Reads only the head of each report rather than decompressing it whole.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from machineplan.parsing.dataset import MachinePlanDataset  # noqa: E402

DEFAULT_ARCHIVE = pathlib.Path(__file__).resolve().parents[1] / "data" / "MachinePlan-10K.zip"
HEAD_BYTES = 1400

_SUBTYPE_RE = re.compile(r"^Template Subtype:\s*(.+?)\s*$", re.MULTILINE)
_ORDER_RE = re.compile(r"^Order Group\s{2,}(.+?)\s*$", re.MULTILINE)
_METHOD_RE = re.compile(r"^Method Group\s{2,}(.+?)\s*$", re.MULTILINE)
_GEOM_RE = re.compile(r"^Geometry Group\s{2,}(.+?)\s*$", re.MULTILINE)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=pathlib.Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--limit", type=int, default=1500, help="parts to scan")
    arguments = parser.parse_args()

    order_groups: collections.Counter[str] = collections.Counter()
    method_groups: collections.Counter[str] = collections.Counter()
    geometry_groups: collections.Counter[str] = collections.Counter()
    subtype_by_order: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    # first appearance index of each order group, to infer a global ordering
    position_sum: collections.Counter[str] = collections.Counter()
    position_count: collections.Counter[str] = collections.Counter()

    sorted_parts = 0
    unsorted_parts = 0
    violations: list[tuple[str, list[str]]] = []
    parts_scanned = 0

    with MachinePlanDataset(arguments.archive) as dataset:
        parts = list(dataset)[: arguments.limit]
        print(f"scanning {len(parts)} parts...\n")

        # Pass 1: collect the order-group vocabulary and mean position.
        sequences: list[tuple[str, list[str]]] = []
        for part in parts:
            groups: list[str] = []
            for index in sorted(part.operations):
                member = part.operations[index].details
                if not member:
                    continue
                with dataset.open(member) as handle:
                    head = handle.read(HEAD_BYTES).decode("utf-8", errors="replace")
                order = _ORDER_RE.search(head)
                subtype = _SUBTYPE_RE.search(head)
                method = _METHOD_RE.search(head)
                geometry = _GEOM_RE.search(head)
                if not order:
                    continue
                group = order.group(1)
                groups.append(group)
                order_groups[group] += 1
                if method:
                    method_groups[method.group(1)] += 1
                if geometry:
                    geometry_groups[geometry.group(1)] += 1
                if subtype:
                    subtype_by_order[group][subtype.group(1)] += 1
            if groups:
                parts_scanned += 1
                sequences.append((part.part_id, groups))
                for position, group in enumerate(groups):
                    position_sum[group] += position / max(len(groups) - 1, 1)
                    position_count[group] += 1

    mean_position = {
        group: position_sum[group] / position_count[group] for group in position_count
    }
    ranking = sorted(mean_position, key=mean_position.get)  # type: ignore[arg-type]
    rank_of = {group: index for index, group in enumerate(ranking)}

    # Pass 2: is every part sorted by that ranking?
    for part_id, groups in sequences:
        ranks = [rank_of[g] for g in groups]
        if ranks == sorted(ranks):
            sorted_parts += 1
        else:
            unsorted_parts += 1
            if len(violations) < 6:
                violations.append((part_id, groups))

    rule = "=" * 78
    print(rule)
    print(f"{parts_scanned} parts, {sum(order_groups.values())} operations")
    print(rule)

    print(f"\n--- Order Group vocabulary ({len(order_groups)} distinct) ---")
    print(f"{'group':22}{'count':>9}{'share':>8}{'mean pos':>10}  dominant subtypes")
    for group in ranking:
        count = order_groups[group]
        tops = ", ".join(
            f"{name} {c}" for name, c in subtype_by_order[group].most_common(3)
        )
        print(f"{group:22}{count:>9,}{count / sum(order_groups.values()) * 100:>7.1f}%"
              f"{mean_position[group]:>10.3f}  {tops}")

    print(f"\n--- Method Group ({len(method_groups)} distinct) ---")
    for value, count in method_groups.most_common(10):
        print(f"  {value:34} {count:7,}")

    print(f"\n--- Geometry Group ({len(geometry_groups)} distinct, top 12) ---")
    for value, count in geometry_groups.most_common(12):
        print(f"  {value:34} {count:7,}")

    print(f"\n{rule}")
    print(f"HYPOTHESIS: the plan is sorted by Order Group rank")
    print(f"  inferred rank: {' < '.join(ranking)}")
    print(rule)
    checked = sorted_parts + unsorted_parts
    print(f"  parts consistent with the sort : {sorted_parts:6,} / {checked:,}  "
          f"({sorted_parts / checked * 100:.2f}%)")
    print(f"  parts violating it             : {unsorted_parts:6,} / {checked:,}  "
          f"({unsorted_parts / checked * 100:.2f}%)")
    for part_id, groups in violations:
        print(f"     {part_id}: {' -> '.join(groups)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
