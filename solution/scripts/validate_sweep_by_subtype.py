#!/usr/bin/env python3
"""Q-007: does the swept-volume engine hold across all seven o2 subtypes?

F-016 validated one chamfering operation at IoU 0.99997. That test never
exercised conical drill tips or canned cycles, and hole-making is 58% of all
operations -- so this stratifies over subtypes and reports the rubric score each
would earn.

Every tool comes from the published `details.txt` parameters, never a guess.
"""

from __future__ import annotations

import argparse
import io
import pathlib
import statistics
import sys
import time
from collections import defaultdict

import trimesh

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from machineplan.geometry.sweep import SweepError, material_removed, sweep_moves  # noqa: E402
from machineplan.geometry.tooling import Tool, UnknownToolError  # noqa: E402
from machineplan.parsing.dataset import MachinePlanDataset, PartFiles  # noqa: E402
from machineplan.parsing.details import parse_details  # noqa: E402
from machineplan.parsing.ptp import parse_ptp  # noqa: E402
from machineplan.scoring.geometry import (  # noqa: E402
    as_solid,
    compare_volumes,
    denoise_difference,
)
from machineplan.scoring.rubric import (  # noqa: E402
    OVERCUT_BANDS,
    PATH_IOU_BANDS,
    score_higher_is_better,
    score_lower_is_better,
)

DEFAULT_ARCHIVE = pathlib.Path(__file__).resolve().parents[1] / "data" / "MachinePlan-10K.zip"
SUBTYPES = (
    "AREA_MILL", "FLOOR_WALL", "DRILLING", "SPOT_DRILLING",
    "DEEP_HOLE_DRILLING", "HOLE_MILLING", "BORING_REAMING",
)


def load_mesh(dataset: MachinePlanDataset, member: str) -> trimesh.Trimesh:
    return trimesh.load(io.BytesIO(dataset.read_bytes(member)), file_type="stl")


def evaluate(dataset: MachinePlanDataset, part: PartFiles, index: int) -> dict | None:
    """Sweep one operation and score it against the IPW difference."""
    operation = part.operations[index]
    details = parse_details(dataset.read_text(operation.details))
    if details.tool is None:
        return None
    try:
        tool = Tool.from_tool_info(details.tool)
    except UnknownToolError as error:
        return {"subtype": details.o2, "error": str(error)}

    before_member = part.blank_mesh if index == 1 else part.operations[index - 1].mesh
    if not before_member:
        return None

    before = as_solid(load_mesh(dataset, before_member), name="before")
    after = as_solid(load_mesh(dataset, operation.mesh), name="after")
    raw_truth = trimesh.boolean.boolean_manifold([before, after], "difference")
    if raw_truth is None or raw_truth.is_empty:
        return None
    # Consecutive IPWs are re-tessellated, so their difference carries thin
    # sheets alongside the real material. Score against the cleaned reference and
    # report both, so the size of the noise stays visible (F-021).
    truth = denoise_difference(raw_truth)

    path = parse_ptp(dataset.read_text(operation.tool_path))
    started = time.perf_counter()
    try:
        swept = sweep_moves(path.cutting_moves, tool)
        clipped = material_removed(before, swept.solid)
    except SweepError as error:
        return {"subtype": details.o2, "error": str(error)}
    elapsed = time.perf_counter() - started

    comparison = compare_volumes(clipped, truth)
    points = (
        score_higher_is_better(comparison.iou, PATH_IOU_BANDS)
        + score_lower_is_better(comparison.overcut, OVERCUT_BANDS)
        + score_lower_is_better(comparison.undercut, OVERCUT_BANDS)
    )
    return {
        "part": part.part_id,
        "index": index,
        "subtype": details.o2,
        "o1": details.o1,
        "tool_type": tool.tool_type,
        "diameter": tool.diameter_mm,
        "geometry_group": details.geometry_group,
        "iou": comparison.iou,
        "overcut": comparison.overcut,
        "undercut": comparison.undercut,
        "raw_points": points,
        "scaled_points": points / 30.0 * 25.0,
        "seconds": elapsed,
        "segments": swept.segment_count,
        "truth_volume": abs(float(truth.volume)),
        "raw_truth_volume": abs(float(raw_truth.volume)),
        "noise_fraction": max(
            abs(float(raw_truth.volume)) - abs(float(truth.volume)), 0.0
        ) / max(abs(float(raw_truth.volume)), 1e-12),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=pathlib.Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--per-subtype", type=int, default=3, help="operations to test per subtype")
    parser.add_argument("--scan-parts", type=int, default=120, help="parts to scan for candidates")
    arguments = parser.parse_args()

    with MachinePlanDataset(arguments.archive) as dataset:
        # Find candidate operations per subtype, reading only each report's head.
        print(f"scanning up to {arguments.scan_parts} parts for candidates...")
        candidates: dict[str, list[tuple[PartFiles, int]]] = defaultdict(list)
        for part in list(dataset)[: arguments.scan_parts]:
            for index, operation in part.operations.items():
                if all(len(candidates[s]) >= arguments.per_subtype for s in SUBTYPES):
                    break
                with dataset.open(operation.details) as handle:
                    head = handle.read(400).decode("utf-8", errors="replace")
                for subtype in SUBTYPES:
                    if f"Template Subtype: {subtype}" in head:
                        if len(candidates[subtype]) < arguments.per_subtype:
                            candidates[subtype].append((part, index))
                        break

        found = {s: len(candidates[s]) for s in SUBTYPES}
        print(f"candidates found: {found}\n")

        results: list[dict] = []
        for subtype in SUBTYPES:
            for part, index in candidates[subtype]:
                outcome = evaluate(dataset, part, index)
                if outcome is None:
                    continue
                if "error" in outcome:
                    print(f"  {subtype:20} {part.part_id} op{index:02d}  ERROR: {outcome['error']}")
                    continue
                results.append(outcome)
                print(
                    f"  {subtype:20} {outcome['part']} op{outcome['index']:02d}  "
                    f"{outcome['tool_type']:12} D{outcome['diameter']:<6g} "
                    f"IoU {outcome['iou']:.5f}  over {outcome['overcut']:.4f}  "
                    f"under {outcome['undercut']:.4f}  "
                    f"{outcome['scaled_points']:5.1f}/25  {outcome['seconds']:5.2f}s  "
                    f"vol {outcome['truth_volume']:10.2f}  noise {outcome['noise_fraction']*100:5.1f}%"
                )

        print("\n" + "=" * 78)
        print(f"{'subtype':22}{'n':>3}{'mean IoU':>11}{'min IoU':>11}{'mean pts':>10}{'mean s':>8}")
        print("=" * 78)
        for subtype in SUBTYPES:
            rows = [r for r in results if r["subtype"] == subtype]
            if not rows:
                print(f"{subtype:22}{0:>3}{'-':>11}{'-':>11}{'-':>10}{'-':>8}")
                continue
            print(
                f"{subtype:22}{len(rows):>3}"
                f"{statistics.fmean(r['iou'] for r in rows):>11.5f}"
                f"{min(r['iou'] for r in rows):>11.5f}"
                f"{statistics.fmean(r['scaled_points'] for r in rows):>10.1f}"
                f"{statistics.fmean(r['seconds'] for r in rows):>8.2f}"
            )
        if results:
            print("-" * 78)
            print(
                f"{'OVERALL':22}{len(results):>3}"
                f"{statistics.fmean(r['iou'] for r in results):>11.5f}"
                f"{min(r['iou'] for r in results):>11.5f}"
                f"{statistics.fmean(r['scaled_points'] for r in results):>10.1f}"
                f"{statistics.fmean(r['seconds'] for r in results):>8.2f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
