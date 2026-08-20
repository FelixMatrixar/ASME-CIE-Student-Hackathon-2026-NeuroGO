#!/usr/bin/env python3
"""First look inside the dataset zip: verify the layout and dump real samples.

Run this immediately after the download completes. Its job is to confirm or
refute the assumptions baked into the parsers -- particularly the *undocumented*
formats: `details.txt`, `part_XXXXX_operations.json`, and `*_text.stl.txt`.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from machineplan.parsing.dataset import MachinePlanDataset  # noqa: E402

DEFAULT_ARCHIVE = pathlib.Path(__file__).resolve().parents[1] / "data" / "MachinePlan-10K.zip"
RULE = "=" * 78


def head(text: str, lines: int) -> str:
    body = text.splitlines()
    shown = "\n".join(body[:lines])
    if len(body) > lines:
        shown += f"\n... ({len(body) - lines} more lines)"
    return shown


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=pathlib.Path, nargs="?", default=DEFAULT_ARCHIVE)
    parser.add_argument("--part", help="part id to sample (default: the first)")
    parser.add_argument("--lines", type=int, default=40, help="lines to show per sample file")
    arguments = parser.parse_args()

    with MachinePlanDataset(arguments.archive) as dataset:
        print(RULE)
        print(dataset.summary())
        print(RULE)

        part = dataset.part(arguments.part) if arguments.part else next(iter(dataset))
        print(f"\nsampling part: {part}")
        print(f"  root            : {part.root}")
        print(f"  brep            : {part.brep}")
        print(f"  operations.json : {part.operations_json}")
        print(f"  blank mesh      : {part.blank_mesh}")
        print(f"  images          : {sorted(part.images)}")

        print("\n  operations:")
        for operation in part.ordered_operations():
            flags = "".join(
                mark if value else "-"
                for mark, value in (
                    ("d", operation.details),
                    ("m", operation.mesh),
                    ("p", operation.tool_path),
                )
            )
            print(f"    {operation.index:03d}  [{flags}]  tool={operation.tool_id}")

        first = part.ordered_operations()[0] if part.operations else None

        if part.operations_json:
            print(f"\n{RULE}\noperations.json\n{RULE}")
            print(head(dataset.read_text(part.operations_json), arguments.lines))

        if first and first.details:
            print(f"\n{RULE}\ndetails.txt (operation {first.index})\n{RULE}")
            print(head(dataset.read_text(first.details), arguments.lines))

        if first and first.mesh:
            print(f"\n{RULE}\n_text.stl.txt (operation {first.index})\n{RULE}")
            text = dataset.read_text(first.mesh)
            print(head(text, min(arguments.lines, 20)))
            print(f"[{len(text.splitlines()):,} lines, {dataset.member_size(first.mesh):,} bytes]")

        if first and first.tool_path:
            print(f"\n{RULE}\n.ptp (operation {first.index})\n{RULE}")
            print(head(dataset.read_text(first.tool_path), min(arguments.lines, 25)))

        if part.brep:
            print(f"\n{RULE}\n.stp header\n{RULE}")
            print(head(dataset.read_text(part.brep), min(arguments.lines, 25)))

        # Corpus shape, from the index alone -- cheap, no decompression.
        print(f"\n{RULE}\ncorpus shape\n{RULE}")
        counts = Counter(p.operation_count for p in dataset)
        print("operations per part (count: parts):")
        for value in sorted(counts):
            print(f"   {value:3d}: {counts[value]:5d}  {'#' * min(counts[value] // 20, 60)}")

        missing_brep = [p.part_id for p in dataset if not p.brep]
        missing_json = [p.part_id for p in dataset if not p.operations_json]
        incomplete = [
            (p.part_id, op.index)
            for p in dataset
            for op in p.operations.values()
            if not op.is_complete
        ]
        print(f"\nparts missing a BRep          : {len(missing_brep)}")
        print(f"parts missing operations.json : {len(missing_json)}")
        print(f"operations missing a file     : {len(incomplete)}")
        for part_id, index in incomplete[:10]:
            print(f"   {part_id} op {index:03d}")

        tools = Counter(
            op.tool_id for p in dataset for op in p.operations.values()
        )
        print(f"\ndistinct tool ids: {len(tools)}")
        for tool_id, count in tools.most_common(15):
            print(f"   {tool_id:<24} {count:6d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
