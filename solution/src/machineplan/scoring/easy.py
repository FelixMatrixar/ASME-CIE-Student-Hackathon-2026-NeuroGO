"""Easy-tier scoring: normalized Levenshtein distance and multiset F1 (20 points).

Both metrics operate on sequences of :class:`~machineplan.vocab.Operation`
tokens, where one token is the ``(o1, o2)`` pair for a single operation. The two
metrics are deliberately complementary: Levenshtein punishes getting the *order*
wrong, F1 punishes getting the *composition* wrong. A prediction can ace one and
fail the other, so both are reported separately.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Hashable, Sequence

from machineplan.scoring.rubric import (
    EASY_BUDGET,
    F1_BANDS,
    LEVENSHTEIN_BANDS,
    score_higher_is_better,
    score_lower_is_better,
)


def levenshtein(predicted: Sequence[Hashable], truth: Sequence[Hashable]) -> int:
    """Edit distance between two sequences under unit insert/delete/substitute cost.

    Two-row dynamic program: O(len(predicted) * len(truth)) time, O(len(truth))
    space. Sequences here are at most ~38 operations, so this is not a bottleneck,
    but the whole 10k dataset gets scored repeatedly during development.
    """
    if predicted == truth:
        return 0
    if not predicted:
        return len(truth)
    if not truth:
        return len(predicted)

    previous = list(range(len(truth) + 1))
    for i, predicted_token in enumerate(predicted, start=1):
        current = [i]
        for j, truth_token in enumerate(truth, start=1):
            current.append(
                min(
                    previous[j] + 1,  # deletion
                    current[j - 1] + 1,  # insertion
                    previous[j - 1] + (predicted_token != truth_token),  # substitution
                )
            )
        previous = current
    return previous[-1]


def normalized_levenshtein(predicted: Sequence[Hashable], truth: Sequence[Hashable]) -> float:
    """``d_L(P, G) / max(|P|, |G|)`` as defined in the rubric. Lower is better.

    Two empty sequences score 0.0 (a perfect match), not a division by zero.
    """
    longest = max(len(predicted), len(truth))
    if longest == 0:
        return 0.0
    return levenshtein(predicted, truth) / longest


def f1_multiset(predicted: Sequence[Hashable], truth: Sequence[Hashable]) -> float:
    """F1 over the *multiset* of operations, ignoring order.

    Multiset semantics matter: a part needing three DRILLING operations gets
    credit for three, not one. True positives are the multiset intersection,
    ``sum(min(count_predicted, count_truth))`` over each distinct token.
    """
    if not predicted and not truth:
        return 1.0
    if not predicted or not truth:
        return 0.0

    predicted_counts = Counter(predicted)
    truth_counts = Counter(truth)
    true_positives = sum((predicted_counts & truth_counts).values())
    if true_positives == 0:
        return 0.0

    precision = true_positives / len(predicted)
    recall = true_positives / len(truth)
    return 2 * precision * recall / (precision + recall)


@dataclass(frozen=True, slots=True)
class EasyScore:
    """Both easy-tier metrics with their rubric points."""

    normalized_levenshtein: float
    f1: float
    levenshtein_points: float
    f1_points: float
    predicted_length: int
    truth_length: int

    @property
    def points(self) -> float:
        """Combined easy-tier score, out of :data:`EASY_BUDGET`."""
        return self.levenshtein_points + self.f1_points

    def __str__(self) -> str:
        return (
            f"easy {self.points:4.1f}/{EASY_BUDGET:.0f}  "
            f"lev {self.normalized_levenshtein:.3f} ({self.levenshtein_points:.0f}pt)  "
            f"f1 {self.f1:.3f} ({self.f1_points:.0f}pt)  "
            f"len {self.predicted_length}v{self.truth_length}"
        )


def score_easy(predicted: Sequence[Hashable], truth: Sequence[Hashable]) -> EasyScore:
    """Score one part's predicted operation sequence against ground truth."""
    distance = normalized_levenshtein(predicted, truth)
    f1 = f1_multiset(predicted, truth)
    return EasyScore(
        normalized_levenshtein=distance,
        f1=f1,
        levenshtein_points=score_lower_is_better(distance, LEVENSHTEIN_BANDS),
        f1_points=score_higher_is_better(f1, F1_BANDS),
        predicted_length=len(predicted),
        truth_length=len(truth),
    )
