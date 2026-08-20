#!/usr/bin/env python3
"""Sweep a real .ptp tool path and report the solid it removes.

End-to-end exercise of parse -> tool solid -> swept volume, and a timing probe:
the swept volume has to run ~91,700 times to cover the dataset, so per-operation
cost matters.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from machineplan.geometry.sweep import sweep_moves  # noqa: E402
from machineplan.geometry.tooling import Tool  # noqa: E402
from machineplan.parsing.ptp import parse_ptp  # noqa: E402

DEFAULT_PTP = (
    pathlib.Path(__file__).resolve().parents[2]
    / "sample_submission" / "hard_tool_path" / "featured_part_00001_operation_01.ptp"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=pathlib.Path, nargs="?", default=DEFAULT_PTP)
    parser.add_argument("--tool-type", default="chamfer_mill")
    parser.add_argument("--diameter", type=float, default=20.0)
    parser.add_argument("--flute", type=float, default=30.0)
    parser.add_argument("--export", type=pathlib.Path, help="write the swept solid to an STL")
    arguments = parser.parse_args()

    tool_path = parse_ptp(arguments.path)
    tool = Tool(arguments.tool_type, arguments.diameter, arguments.flute)

    print(f"path : {tool_path}")
    print(f"tool : {tool}  (tip height {tool.tip_height_mm:.3f} mm, "
          f"solid {tool.solid().volume:,.1f} mm^3)")

    started = time.perf_counter()
    swept = sweep_moves(tool_path.cutting_moves, tool)
    elapsed = time.perf_counter() - started

    print(f"\nswept: {swept}")
    print(f"  watertight   : {swept.solid.is_watertight}")
    print(f"  triangles    : {len(swept.solid.faces):,}")
    print(f"  bounds  X {swept.solid.bounds[0][0]:9.3f} .. {swept.solid.bounds[1][0]:9.3f}")
    print(f"          Y {swept.solid.bounds[0][1]:9.3f} .. {swept.solid.bounds[1][1]:9.3f}")
    print(f"          Z {swept.solid.bounds[0][2]:9.3f} .. {swept.solid.bounds[1][2]:9.3f}")
    print(f"\n  elapsed      : {elapsed:.2f} s for {swept.segment_count} segments")
    print(f"  projected    : {elapsed * 91702 / 3600:.1f} h to sweep all 91,702 dataset operations")

    if arguments.export:
        swept.solid.export(arguments.export)
        print(f"\nwrote {arguments.export}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
