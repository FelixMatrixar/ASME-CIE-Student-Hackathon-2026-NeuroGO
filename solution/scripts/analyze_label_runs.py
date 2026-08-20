#!/usr/bin/env python3
"""Does within-block ordering actually affect the easy-tier score?

Levenshtein is computed on the sequence of **(o1, o2) labels**, not on which
physical feature each operation targets. So if a contiguous same-tool block
carries the same label throughout -- five consecutive SPOT_DRILLING operations,
say -- then permuting the holes within that block changes the label sequence not
at all, and the ordering rule inside a block is irrelevant to scoring.

This measures:
  1. what fraction of same-tool blocks are label-homogeneous;
  2. how many distinct label *runs* a part's sequence has, versus its operation
     count -- i.e. how much shorter the "block sequence" is than the raw one.

The second number bounds the real difficulty of the Levenshtein sub-score.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import re
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from machineplan.parsing.dataset import MachinePlanDataset  # noqa: E402

DEFAULT_ARCHIVE = pathlib.Path(__file__).resolve().parents[1] / "data" / "MachinePlan-10K.zip"
HEAD_BYTES = 400
_SUBTYPE_RE = re.compile(r"^Template Subtype:\s*(.+?)\s*$", re.MULTILINE)


def runs(values: list[str]) -> list[str]:
    """Collapse consecutive duplicates: [a,a,b,b,b,a] -> [a,b,a]."""
    out: list[str] = []
    for value in values:
        if not out or out[-1] != value:
            out.append(value)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=pathlib.Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--limit", type=int, default=1200)
    arguments = parser.parse_args()

    homogeneous_blocks = 0
    mixed_blocks = 0
    mixed_examples: list[str] = []

    operation_counts: list[int] = []
    run_counts: list[int] = []
    compression: list[float] = []
    run_length_hist: collections.Counter[int] = collections.Counter()

    with MachinePlanDataset(arguments.archive) as dataset:
        parts = list(dataset)[: arguments.limit]
        print(f"scanning {len(parts)} parts...\n")

        for part in parts:
            if not part.operations_json:
                continue
            payload = dataset.read_json(part.operations_json)
            entries = payload.get("operations", [])
            if not entries:
                continue

            labels: list[str] = []
            for index in sorted(part.operations):
                member = part.operations[index].details
                if not member:
                    break
                with dataset.open(member) as handle:
                    head = handle.read(HEAD_BYTES).decode("utf-8", errors="replace")
                match = _SUBTYPE_RE.search(head)
                if not match:
                    break
                labels.append(match.group(1))
            if len(labels) != len(entries):
                continue

            tools = [entry.get("tool_name", "?") for entry in entries]

            # Contiguous same-tool blocks, and whether each is label-homogeneous.
            start = 0
            for position in range(1, len(tools) + 1):
                if position == len(tools) or tools[position] != tools[start]:
                    block = labels[start:position]
                    if len(block) > 1:
                        if len(set(block)) == 1:
                            homogeneous_blocks += 1
                        else:
                            mixed_blocks += 1
                            if len(mixed_examples) < 6:
                                mixed_examples.append(
                                    f"{part.part_id} ops {start + 1}-{position}: "
                                    + " ".join(block)
                                )
                    start = position

            collapsed = runs(labels)
            operation_counts.append(len(labels))
            run_counts.append(len(collapsed))
            compression.append(len(collapsed) / len(labels))
            for label in set(collapsed):
                pass
            current = 1
            for a, b in zip(labels, labels[1:]):
                if a == b:
                    current += 1
                else:
                    run_length_hist[current] += 1
                    current = 1
            run_length_hist[current] += 1

    rule = "=" * 78
    total_blocks = homogeneous_blocks + mixed_blocks
    print(rule)
    print(f"{len(operation_counts):,} parts, {sum(operation_counts):,} operations")
    print(rule)

    print("\nAre multi-operation same-tool blocks label-homogeneous?")
    print(f"  homogeneous : {homogeneous_blocks:6,} / {total_blocks:,}  "
          f"({homogeneous_blocks / max(total_blocks, 1) * 100:.2f}%)")
    print(f"  mixed       : {mixed_blocks:6,} / {total_blocks:,}  "
          f"({mixed_blocks / max(total_blocks, 1) * 100:.2f}%)")
    for line in mixed_examples:
        print(f"     {line}")

    print("\nLabel sequence vs collapsed run sequence")
    print(f"  mean operations per part : {statistics.fmean(operation_counts):6.2f}")
    print(f"  mean label runs per part : {statistics.fmean(run_counts):6.2f}")
    print(f"  median label runs        : {statistics.median(run_counts):6.1f}")
    print(f"  mean compression         : {statistics.fmean(compression):6.3f}  "
          f"(runs / operations)")

    print("\n--- distribution of label run lengths ---")
    total_runs = sum(run_length_hist.values())
    for length in sorted(run_length_hist):
        count = run_length_hist[length]
        if count / total_runs < 0.002:
            continue
        print(f"  {length:3d} in a row {count:7,}  {count / total_runs * 100:5.2f}%  "
              f"{'#' * min(count // 60, 55)}")

    print(f"\n{rule}")
    print("IMPLICATION")
    print(rule)
    print(f"  {homogeneous_blocks / max(total_blocks, 1) * 100:.1f}% of same-tool blocks carry one label, so")
    print("  permuting operations inside a block does not change the label sequence")
    print("  and cannot change the Levenshtein score.")
    print(f"  The sequence to get right is ~{statistics.fmean(run_counts):.1f} runs long,")
    print(f"  not ~{statistics.fmean(operation_counts):.1f} operations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
