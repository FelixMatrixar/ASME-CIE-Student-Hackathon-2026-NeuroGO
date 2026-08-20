#!/usr/bin/env python3
"""Print a structural summary of a .ptp tool path, for eyeballing the parser."""

from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from machineplan.parsing.ptp import discretize, parse_ptp  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=pathlib.Path)
    arguments = parser.parse_args()

    path = parse_ptp(arguments.path)
    print(path)
    print(f"\nheader: {path.header}")
    print(f"operation: {path.operation}   tool id: {path.tool_id}   spindle: {path.spindle_rpm} rpm")
    print(f"units: {'mm' if path.metric else 'inch'}   tool change: T{path.tool_change}")

    low, high = path.bounds
    print(f"\nbounds  X {low[0]:9.3f} .. {high[0]:9.3f}")
    print(f"        Y {low[1]:9.3f} .. {high[1]:9.3f}")
    print(f"        Z {low[2]:9.3f} .. {high[2]:9.3f}")

    kinds: dict[str, int] = {}
    for move in path.moves:
        kinds[move.kind] = kinds.get(move.kind, 0) + 1
    print(f"\nmove kinds: {kinds}")
    print(f"cutting length {path.cutting_length:10.1f} mm")
    print(f"rapid   length {path.rapid_length:10.1f} mm")

    planar = sum(1 for m in path.cutting_moves if m.is_planar)
    vertical = sum(1 for m in path.cutting_moves if m.is_vertical)
    print(f"\ncutting moves: {len(path.cutting_moves)}  "
          f"({planar} planar, {vertical} vertical, "
          f"{len(path.cutting_moves) - planar - vertical} ramping)")

    levels = path.z_levels
    print(f"constant-Z cutting levels: {len(levels)}")
    for level in levels[:12]:
        print(f"   Z = {level:9.3f}")
    if len(levels) > 12:
        print(f"   ... and {len(levels) - 12} more")

    dense = discretize(path.cutting_moves, max_step=1.0)
    print(f"\ndiscretized cutting polyline: {len(dense)} points at 1.0 mm max step")

    print("\nfirst 5 moves:")
    for move in path.moves[:5]:
        print(f"   N{move.block:<4} {move.kind:<7} "
              f"({move.start[0]:8.3f},{move.start[1]:8.3f},{move.start[2]:8.3f}) -> "
              f"({move.end[0]:8.3f},{move.end[1]:8.3f},{move.end[2]:8.3f})  "
              f"len {move.length:7.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
