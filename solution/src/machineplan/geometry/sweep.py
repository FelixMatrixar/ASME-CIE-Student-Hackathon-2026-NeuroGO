"""Swept-volume computation: turn a tool path into the solid it removes.

This is the core of the 25-point tool-path score, and by F-005 it is also the
quantity the 35-point medium tier is built from, since

    swept_volume(operation k)  ==  IPW(k-1) - IPW(k)

**The exactness argument.** Every tool in this dataset is a convex solid of
revolution (see :mod:`machineplan.geometry.tooling`). For a convex body ``K``
translated along a straight segment from ``a`` to ``b``, the swept region is the
Minkowski sum of ``K`` with that segment, and for convex ``K`` that is exactly

    conv( (K + a) u (K + b) )

-- the convex hull of the tool placed at both endpoints. So each linear move is
computed *exactly* rather than sampled, and discretization error enters only
through arc chording and the revolve resolution. This is both more accurate and
far cheaper than stamping the tool at densely sampled positions.

Convexity is load-bearing: the identity fails for a non-convex tool, so any
future tool with an undercut profile must be decomposed into convex pieces first.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
import trimesh

from machineplan.geometry.tooling import Tool
from machineplan.parsing.ptp import Move, ToolPath

# Segments shorter than this are treated as a single tool placement rather than
# a hull of two near-identical positions, which would be numerically degenerate.
MIN_SEGMENT_MM = 1e-6

# Union batches are reduced pairwise in a tree rather than accumulated linearly:
# a running union grows monotonically and every step pays for its full size,
# whereas tree reduction keeps intermediate operands small.
UNION_BATCH = 16


class SweepError(RuntimeError):
    """Raised when a swept volume cannot be produced."""


@dataclass(frozen=True, slots=True)
class SweptVolume:
    """The solid removed by a tool path, plus provenance for debugging."""

    solid: trimesh.Trimesh
    segment_count: int
    tool: Tool

    @property
    def volume(self) -> float:
        return abs(float(self.solid.volume))

    def __str__(self) -> str:
        return (
            f"SweptVolume({self.tool}, {self.segment_count} segments, "
            f"{self.volume:,.1f} mm^3)"
        )


def _place(solid: trimesh.Trimesh, position: Sequence[float]) -> trimesh.Trimesh:
    moved = solid.copy()
    moved.apply_translation(np.asarray(position, dtype=float))
    return moved


def segment_sweep(tool_solid: trimesh.Trimesh, start: Sequence[float], end: Sequence[float]) -> trimesh.Trimesh:
    """Exact swept volume of a convex tool translated from ``start`` to ``end``.

    Returns the convex hull of the tool at both endpoints; for a convex tool this
    *is* the swept region, not an approximation of it.
    """
    start_array = np.asarray(start, dtype=float)
    end_array = np.asarray(end, dtype=float)
    if float(np.linalg.norm(end_array - start_array)) < MIN_SEGMENT_MM:
        return _place(tool_solid, start_array)

    vertices = np.vstack(
        [tool_solid.vertices + start_array, tool_solid.vertices + end_array]
    )
    return trimesh.Trimesh(vertices=vertices, process=True).convex_hull


def _union(meshes: Sequence[trimesh.Trimesh]) -> trimesh.Trimesh:
    """Union a list of solids by pairwise tree reduction."""
    if not meshes:
        raise SweepError("nothing to union")
    current = list(meshes)
    while len(current) > 1:
        nxt: list[trimesh.Trimesh] = []
        for index in range(0, len(current), UNION_BATCH):
            batch = current[index : index + UNION_BATCH]
            if len(batch) == 1:
                nxt.append(batch[0])
            else:
                merged = trimesh.boolean.boolean_manifold(batch, "union")
                if merged is None or merged.is_empty:
                    raise SweepError("union produced an empty solid")
                nxt.append(merged)
        current = nxt
    return current[0]


def sweep_moves(
    moves: Iterable[Move],
    tool: Tool,
    *,
    arc_step_mm: float = 0.5,
    include_rapids: bool = False,
) -> SweptVolume:
    """Swept volume of ``moves`` for ``tool``.

    Rapids are excluded by default: in a well-formed NX program they happen at
    clearance height and remove nothing. Set ``include_rapids`` when validating a
    path that may plunge in rapid.
    """
    tool_solid = tool.solid()
    selected = [move for move in moves if include_rapids or move.is_cutting]
    if not selected:
        raise SweepError("tool path contains no cutting moves")

    hulls: list[trimesh.Trimesh] = []
    for move in selected:
        if move.kind in ("arc_cw", "arc_ccw") and move.center is not None:
            points = _chord_points(move, arc_step_mm)
            for start, end in zip(points, points[1:]):
                hulls.append(segment_sweep(tool_solid, start, end))
        else:
            hulls.append(segment_sweep(tool_solid, move.start, move.end))

    return SweptVolume(solid=_union(hulls), segment_count=len(hulls), tool=tool)


def _chord_points(move: Move, step_mm: float) -> list[tuple[float, float, float]]:
    """Chord the arc finely enough that the sagitta stays under ``step_mm``."""
    import math

    assert move.center is not None
    centre = move.center
    radius = math.hypot(move.start[0] - centre[0], move.start[1] - centre[1])
    start_angle = math.atan2(move.start[1] - centre[1], move.start[0] - centre[0])
    end_angle = math.atan2(move.end[1] - centre[1], move.end[0] - centre[0])

    sweep = end_angle - start_angle
    if move.kind == "arc_cw":
        while sweep >= 0:
            sweep -= 2 * math.pi
    else:
        while sweep <= 0:
            sweep += 2 * math.pi

    arc_length = abs(sweep) * radius
    steps = max(2, int(arc_length / max(step_mm, 1e-6)) + 1)
    points = []
    for index in range(steps + 1):
        fraction = index / steps
        angle = start_angle + sweep * fraction
        points.append(
            (
                centre[0] + radius * math.cos(angle),
                centre[1] + radius * math.sin(angle),
                move.start[2] + (move.end[2] - move.start[2]) * fraction,
            )
        )
    return points


def sweep_tool_path(
    path: ToolPath,
    tool: Tool,
    *,
    arc_step_mm: float = 0.5,
    include_rapids: bool = False,
) -> SweptVolume:
    """Swept volume for a parsed :class:`~machineplan.parsing.ptp.ToolPath`."""
    return sweep_moves(
        path.moves, tool, arc_step_mm=arc_step_mm, include_rapids=include_rapids
    )


def material_removed(
    stock: trimesh.Trimesh,
    swept: trimesh.Trimesh,
) -> trimesh.Trimesh:
    """Intersect a swept volume with the stock actually present.

    A tool path sweeps through air as well as material; only the part
    intersecting the current in-process workpiece is genuinely removed. This is
    what makes a swept volume comparable to ``IPW(k-1) - IPW(k)``.
    """
    result = trimesh.boolean.boolean_manifold([swept, stock], "intersection")
    if result is None or result.is_empty:
        raise SweepError("swept volume does not intersect the stock")
    return result
