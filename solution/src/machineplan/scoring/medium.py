"""Medium-tier scoring: mean IoU across per-operation IPW meshes (35 points).

The rubric averages IoU across all operations and additionally compares the
final IPW against the target BRep. The band table is unusually harsh -- 0.90 is
the floor below which the whole tier scores zero, and the top band demands
0.999 -- so this module reports the per-operation distribution, not just the
mean, because a single bad operation can drag an otherwise excellent run
beneath a band boundary.

Sequence-length mismatch is handled by scoring over the union of operation
indices: an operation the prediction omits, or invents, contributes IoU 0. That
is the interpretation most consistent with the tier being gated on a correct
sequence, and it is stated explicitly rather than hidden, since the rubric does
not spell out the mismatch case.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Sequence

import trimesh

from machineplan.scoring.geometry import DegenerateMeshError, VolumeComparison, compare_volumes
from machineplan.scoring.rubric import MEDIUM_BUDGET, MEDIUM_IOU_BANDS, score_higher_is_better


@dataclass(frozen=True, slots=True)
class MediumScore:
    """Per-operation IPW agreement and the resulting rubric points."""

    per_operation_iou: list[float]
    final_iou: float | None
    points: float
    predicted_count: int
    truth_count: int
    comparisons: list[VolumeComparison | None] = field(default_factory=list, repr=False)

    @property
    def mean_iou(self) -> float:
        return statistics.fmean(self.per_operation_iou) if self.per_operation_iou else 0.0

    @property
    def worst_iou(self) -> float:
        return min(self.per_operation_iou, default=0.0)

    @property
    def worst_operation(self) -> int | None:
        """1-based index of the operation that scored lowest, for triage."""
        if not self.per_operation_iou:
            return None
        return min(range(len(self.per_operation_iou)), key=self.per_operation_iou.__getitem__) + 1

    def __str__(self) -> str:
        final = f"{self.final_iou:.5f}" if self.final_iou is not None else "n/a"
        return (
            f"medium {self.points:4.1f}/{MEDIUM_BUDGET:.0f}  "
            f"mean iou {self.mean_iou:.5f}  worst {self.worst_iou:.5f} "
            f"(op {self.worst_operation})  final-vs-brep {final}  "
            f"ops {self.predicted_count}v{self.truth_count}"
        )


def score_medium(
    predicted: Sequence[trimesh.Trimesh],
    truth: Sequence[trimesh.Trimesh],
    *,
    target: trimesh.Trimesh | None = None,
    alignment: str = "union",
) -> MediumScore:
    """Score a sequence of predicted IPW meshes against ground-truth IPWs.

    ``target`` is the design BRep converted to a mesh; when supplied, the final
    predicted IPW is additionally compared against it and that IoU is folded into
    the mean, mirroring the rubric's "in addition final IPW will be compared
    against the target geometry".

    ``alignment`` selects how a sequence-length mismatch is handled, which the
    rubric does not specify (**Q-002**) and which materially changes the result:

    * ``"union"`` (default) -- score over the union of indices, so a missing or
      surplus operation contributes IoU 0. This is the assumption behind F-037's
      finding that medium IoU tracks the operation-count ratio.
    * ``"truncate"`` -- score only the first ``min(len)`` operations, ignoring the
      overhang. Under this convention length mismatch is nearly free and the tier
      becomes geometry-driven instead.

    The two are not a detail: which one the graders use decides whether effort
    belongs on counting operations or on removal geometry. Both are implemented
    so the sensitivity can be measured rather than assumed -- see
    `scripts/sensitivity_alignment.py`.
    """
    if alignment not in ("union", "truncate"):
        raise ValueError(f"unknown alignment mode: {alignment!r}")

    per_operation: list[float] = []
    comparisons: list[VolumeComparison | None] = []

    span = (
        max(len(predicted), len(truth))
        if alignment == "union"
        else min(len(predicted), len(truth))
    )
    for index in range(span):
        if index >= len(predicted) or index >= len(truth):
            # Missing or surplus operation: no overlap can be credited.
            per_operation.append(0.0)
            comparisons.append(None)
            continue
        try:
            comparison = compare_volumes(predicted[index], truth[index])
        except DegenerateMeshError:
            per_operation.append(0.0)
            comparisons.append(None)
            continue
        per_operation.append(comparison.iou)
        comparisons.append(comparison)

    final_iou: float | None = None
    if target is not None and predicted:
        try:
            final_iou = compare_volumes(predicted[-1], target).iou
        except DegenerateMeshError:
            final_iou = 0.0

    scored = per_operation + ([final_iou] if final_iou is not None else [])
    mean_iou = statistics.fmean(scored) if scored else 0.0

    return MediumScore(
        per_operation_iou=per_operation,
        final_iou=final_iou,
        points=score_higher_is_better(mean_iou, MEDIUM_IOU_BANDS),
        predicted_count=len(predicted),
        truth_count=len(truth),
        comparisons=comparisons,
    )
