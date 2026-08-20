#!/usr/bin/env python3
"""The decisive experiment for the hard tier.

``operations.json`` publishes ``volume_removed_mm3`` for every operation, and the
IPW meshes bracket each operation. So for one real operation we can check three
independent quantities against each other:

1. ``volume_removed_mm3`` from the metadata
2. ``IPW(k-1) - IPW(k)`` computed by boolean difference of the meshes
3. the swept volume of the ``.ptp`` tool path, clipped to the stock present

(1) vs (2) validates our mesh reading. (2) vs (3) validates the whole
swept-volume engine -- and therefore whether the 25-point tool-path tier is
reachable at all.
"""

from __future__ import annotations

import argparse
import io
import pathlib
import re
import sys
import time

import trimesh

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from machineplan.geometry.sweep import material_removed, sweep_moves  # noqa: E402
from machineplan.geometry.tooling import Tool  # noqa: E402
from machineplan.parsing.dataset import MachinePlanDataset  # noqa: E402
from machineplan.parsing.ptp import parse_ptp  # noqa: E402
from machineplan.scoring.geometry import as_solid, compare_volumes  # noqa: E402

DEFAULT_ARCHIVE = pathlib.Path(__file__).resolve().parents[1] / "data" / "MachinePlan-10K.zip"

# "(D) Diameter         =      20.000000000 mm"
_PARAM_RE = re.compile(r"\((\w+)\)\s*([A-Za-z ]+?)\s*=\s*([-\d.]+)\s*(mm|°)?")
_TOOL_TYPE_RE = re.compile(r"^Tool Type\s*:\s*(.+?)\s*$", re.MULTILINE)
_TEMPLATE_TYPE_RE = re.compile(r"^Template Type:\s*(\S+)\s*$", re.MULTILINE)
_TEMPLATE_SUBTYPE_RE = re.compile(r"^Template Subtype:\s*(.+?)\s*$", re.MULTILINE)


def parse_tool_parameters(details: str) -> dict[str, float]:
    """Pull the ``(D) Diameter = 20.0 mm`` style parameter block out of details.txt."""
    found: dict[str, float] = {}
    for code, _name, value, _unit in _PARAM_RE.findall(details):
        found.setdefault(code, float(value))
    return found


def load_mesh(dataset: MachinePlanDataset, member: str) -> trimesh.Trimesh:
    """Load an ASCII STL stored as ``*_text.stl.txt``."""
    raw = dataset.read_bytes(member)
    return trimesh.load(io.BytesIO(raw), file_type="stl")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=pathlib.Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--part", default="featured_part_00001")
    parser.add_argument("--operation", type=int, default=1)
    parser.add_argument("--tool-type", default="chamfer_mill")
    arguments = parser.parse_args()

    with MachinePlanDataset(arguments.archive) as dataset:
        part = dataset.part(arguments.part)
        metadata = dataset.read_json(part.operations_json)
        entry = metadata["operations"][arguments.operation - 1]
        operation = part.operations[arguments.operation]

        print(f"part {part.part_id}, operation {arguments.operation}: "
              f"{entry['name']} ({entry['type']}) tool={entry['tool_name']}")

        # ---- tool parameters straight from details.txt ---------------------
        details = dataset.read_text(operation.details)
        parameters = parse_tool_parameters(details)
        tool_type_text = _TOOL_TYPE_RE.search(details)
        subtype = _TEMPLATE_SUBTYPE_RE.search(details)
        print(f"\ndetails.txt tool: {tool_type_text.group(1) if tool_type_text else '?'}"
              f"  / {subtype.group(1) if subtype else '?'}")
        for code in ("D", "R1", "L", "C", "B", "FL"):
            if code in parameters:
                print(f"   ({code}) = {parameters[code]:g}")

        diameter = parameters.get("D")
        flute = parameters.get("FL")
        if diameter is None:
            print("no (D) diameter in details.txt; cannot proceed", file=sys.stderr)
            return 2
        tool = Tool(arguments.tool_type, diameter_mm=diameter, flute_length_mm=flute)
        print(f"\nreconstructed tool: {tool}")
        print(f"   our tip height     {tool.tip_height_mm:.4f} mm")
        if "C" in parameters:
            delta = abs(tool.tip_height_mm - parameters["C"])
            verdict = "MATCH" if delta < 1e-3 else f"MISMATCH by {delta:.4f} mm"
            print(f"   details (C) length {parameters['C']:.4f} mm  -> {verdict}")

        # ---- (1) metadata vs (2) mesh difference ---------------------------
        reported = float(entry["volume_removed_mm3"])
        after = load_mesh(dataset, operation.mesh)
        before_member = (
            part.blank_mesh
            if arguments.operation == 1
            else part.operations[arguments.operation - 1].mesh
        )
        before = load_mesh(dataset, before_member)

        before_solid = as_solid(before, name="before")
        after_solid = as_solid(after, name="after")
        difference = before_solid.volume - after_solid.volume

        print(f"\n--- volume removed by this operation ---")
        print(f"  (1) operations.json volume_removed_mm3 : {reported:14,.4f}")
        print(f"  (2) IPW(k-1).volume - IPW(k).volume    : {difference:14,.4f}")
        print(f"      agreement                          : "
              f"{abs(reported - difference) / reported * 100:.4f}% error")
        print(f"      IPW(k) volume vs metadata volume_mm3: "
              f"{after_solid.volume:,.4f} vs {float(entry['volume_mm3']):,.4f}")

        # ---- (3) swept volume ---------------------------------------------
        path = parse_ptp(dataset.read_text(operation.tool_path))
        print(f"\n  tool path: {path}")
        print(f"      metadata cutting length {entry['toolpath_cutting_length_mm']:,.3f} mm")
        print(f"      our parsed cutting length {path.cutting_length:,.3f} mm")

        started = time.perf_counter()
        swept = sweep_moves(path.cutting_moves, tool)
        clipped = material_removed(before_solid, swept.solid)
        elapsed = time.perf_counter() - started

        print(f"\n  (3) swept volume (raw)                 : {swept.volume:14,.4f}")
        print(f"      swept volume clipped to stock      : {clipped.volume:14,.4f}")
        print(f"      vs reported removed                : "
              f"{abs(clipped.volume - reported) / reported * 100:.2f}% error")
        print(f"      elapsed {elapsed:.2f} s")

        # ---- the metric that actually scores -------------------------------
        truth_removed = trimesh.boolean.boolean_manifold(
            [before_solid, after_solid], "difference"
        )
        comparison = compare_volumes(clipped, truth_removed)
        print(f"\n--- what the rubric would score ---")
        print(f"  swept-vs-truth {comparison}")
        print(f"  IoU {comparison.iou:.5f}   overcut {comparison.overcut:.5f}   "
              f"undercut {comparison.undercut:.5f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
