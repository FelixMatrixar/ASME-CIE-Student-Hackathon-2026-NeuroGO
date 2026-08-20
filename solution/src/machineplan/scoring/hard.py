"""Hard-tier scoring: tool selection (20 points) and tool path geometry (25 points).

Tool selection compares type and diameter per operation. A wrong type zeroes the
whole operation regardless of how close the diameter is, so type accuracy
dominates -- an important signal for how to weight a predictor's loss.

Tool path geometry compares the swept volume of the submitted path against the
boolean difference of the before/after IPWs. Note the identity this rests on:

    swept_volume(operation k) == IPW(k-1) - IPW(k)

which is the same quantity the medium tier is built from. A single geometry
engine therefore serves both tiers; see :mod:`machineplan.scoring.geometry`.

Both sub-scores are rescaled onto their stated section budgets because the
printed tables do not sum to them -- see :mod:`machineplan.scoring.rubric`.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Sequence

import trimesh

from machineplan.scoring.geometry import DegenerateMeshError, compare_volumes
from machineplan.scoring.rubric import (
    HARD_PATH_BUDGET,
    HARD_TOOL_BUDGET,
    OVERCUT_BANDS,
    PATH_IOU_BANDS,
    RELATIVE_SIZE_ERROR_BANDS,
    rescale,
    score_higher_is_better,
    score_lower_is_better,
)

# Best achievable raw totals from the printed tables, used for rescaling.
_RAW_TOOL_MAX = 10.0
_RAW_PATH_MAX = 15.0 + 7.5 + 7.5


@dataclass(frozen=True, slots=True)
class ToolPrediction:
    """One operation's predicted or ground-truth tool."""

    tool_type: str
    diameter_mm: float


@dataclass(frozen=True, slots=True)
class ToolScore:
    """Tool-selection agreement across a part's operations."""

    per_operation_points: list[float]
    type_matches: int
    scored_operations: int
    points: float

    @property
    def type_accuracy(self) -> float:
        return self.type_matches / self.scored_operations if self.scored_operations else 0.0

    def __str__(self) -> str:
        return (
            f"tools {self.points:4.1f}/{HARD_TOOL_BUDGET:.0f}  "
            f"type acc {self.type_accuracy:.3f} ({self.type_matches}/{self.scored_operations})"
        )


def score_tools(
    predicted: Sequence[ToolPrediction],
    truth: Sequence[ToolPrediction],
) -> ToolScore:
    """Score predicted tool type and diameter, operation by operation."""
    per_operation: list[float] = []
    type_matches = 0
    total = max(len(predicted), len(truth))

    for index in range(total):
        if index >= len(predicted) or index >= len(truth):
            per_operation.append(0.0)
            continue
        prediction, reference = predicted[index], truth[index]
        if prediction.tool_type != reference.tool_type:
            # A wrong tool type scores zero for the operation: the rubric treats
            # the resulting geometry as non-equivalent regardless of size.
            per_operation.append(0.0)
            continue
        type_matches += 1
        if reference.diameter_mm <= 0:
            per_operation.append(0.0)
            continue
        relative_error = abs(prediction.diameter_mm - reference.diameter_mm) / reference.diameter_mm
        per_operation.append(score_lower_is_better(relative_error, RELATIVE_SIZE_ERROR_BANDS))

    raw = statistics.fmean(per_operation) if per_operation else 0.0
    return ToolScore(
        per_operation_points=per_operation,
        type_matches=type_matches,
        scored_operations=total,
        points=rescale(raw, _RAW_TOOL_MAX, HARD_TOOL_BUDGET),
    )


@dataclass(frozen=True, slots=True)
class PathScore:
    """Swept-volume agreement for a part's tool paths."""

    per_operation_iou: list[float]
    per_operation_overcut: list[float]
    per_operation_undercut: list[float]
    points: float

    @property
    def mean_iou(self) -> float:
        return statistics.fmean(self.per_operation_iou) if self.per_operation_iou else 0.0

    @property
    def mean_overcut(self) -> float:
        return statistics.fmean(self.per_operation_overcut) if self.per_operation_overcut else 1.0

    @property
    def mean_undercut(self) -> float:
        return statistics.fmean(self.per_operation_undercut) if self.per_operation_undercut else 1.0

    def __str__(self) -> str:
        return (
            f"paths {self.points:4.1f}/{HARD_PATH_BUDGET:.0f}  "
            f"iou {self.mean_iou:.4f}  over {self.mean_overcut:.4f}  under {self.mean_undercut:.4f}"
        )


def score_tool_paths(
    swept_volumes: Sequence[trimesh.Trimesh | None],
    removed_volumes: Sequence[trimesh.Trimesh],
) -> PathScore:
    """Compare per-operation swept volumes against the material actually removed.

    ``swept_volumes[i]`` is the solid swept by the submitted tool path for
    operation ``i``; ``removed_volumes[i]`` is ``IPW(i-1) - IPW(i)`` from ground
    truth. A ``None`` entry means the path could not be simulated and scores zero.
    """
    ious: list[float] = []
    overcuts: list[float] = []
    undercuts: list[float] = []

    for index in range(max(len(swept_volumes), len(removed_volumes))):
        swept = swept_volumes[index] if index < len(swept_volumes) else None
        reference = removed_volumes[index] if index < len(removed_volumes) else None
        if swept is None or reference is None:
            ious.append(0.0)
            overcuts.append(1.0)
            undercuts.append(1.0)
            continue
        try:
            comparison = compare_volumes(swept, reference)
        except DegenerateMeshError:
            ious.append(0.0)
            overcuts.append(1.0)
            undercuts.append(1.0)
            continue
        ious.append(comparison.iou)
        overcuts.append(comparison.overcut)
        undercuts.append(comparison.undercut)

    mean_iou = statistics.fmean(ious) if ious else 0.0
    mean_overcut = statistics.fmean(overcuts) if overcuts else 1.0
    mean_undercut = statistics.fmean(undercuts) if undercuts else 1.0

    raw = (
        score_higher_is_better(mean_iou, PATH_IOU_BANDS)
        + score_lower_is_better(mean_overcut, OVERCUT_BANDS)
        + score_lower_is_better(mean_undercut, OVERCUT_BANDS)
    )
    return PathScore(
        per_operation_iou=ious,
        per_operation_overcut=overcuts,
        per_operation_undercut=undercuts,
        points=rescale(raw, _RAW_PATH_MAX, HARD_PATH_BUDGET),
    )
