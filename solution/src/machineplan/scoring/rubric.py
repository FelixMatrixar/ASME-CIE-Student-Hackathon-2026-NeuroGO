"""Point tables from Rubrics.pdf, plus the two places where that document is
internally inconsistent.

Section budgets (easy 20, medium 35, hard 45) sum to 100 and are unambiguous.
Two of the hard sub-tables do not sum to their stated section budget:

* "Tool selection (type and diameter) (20 points)" is followed by a table whose
  best row awards 10.
* "Tool path geometry (25 points)" is followed by an IoU table topping out at 15
  and an over/under-cut table awarding "Points (each)" up to 7.5 — i.e. 15 for
  IoU plus 7.5 overcut plus 7.5 undercut = 30.

Both are resolved here by scoring the tables exactly as printed and then scaling
the section to its stated budget. :data:`SCALE_TO_SECTION_BUDGET` toggles that
behaviour so the raw table numbers stay inspectable. This is a question worth
putting to the organizers rather than silently guessing.

Band boundaries are also ambiguous as printed (0.0-0.1 and 0.1-0.2 both contain
0.1). Bands here are resolved in the participant's favour: a value landing
exactly on a boundary receives the higher score.
"""

from __future__ import annotations

from typing import Final, Sequence

# Flip to False to see the unscaled numbers exactly as the tables print them.
SCALE_TO_SECTION_BUDGET: Final[bool] = True

EASY_BUDGET: Final[float] = 20.0
MEDIUM_BUDGET: Final[float] = 35.0
HARD_TOOL_BUDGET: Final[float] = 20.0
HARD_PATH_BUDGET: Final[float] = 25.0
TOTAL_BUDGET: Final[float] = EASY_BUDGET + MEDIUM_BUDGET + HARD_TOOL_BUDGET + HARD_PATH_BUDGET

# Each band is (threshold, points). Tables are searched top to bottom.
_Band = tuple[float, float]

# Lower is better: award the first band whose threshold the value does not exceed.
LEVENSHTEIN_BANDS: Final[Sequence[_Band]] = (
    (0.1, 10.0),
    (0.2, 8.0),
    (0.3, 6.0),
    (0.4, 4.0),
    (0.5, 2.0),
    (1.0, 0.0),
)

OVERCUT_BANDS: Final[Sequence[_Band]] = (
    (0.05, 7.5),
    (0.15, 6.0),
    (0.25, 4.5),
    (0.35, 3.0),
    (0.45, 1.5),
    (1.0, 0.0),
)

RELATIVE_SIZE_ERROR_BANDS: Final[Sequence[_Band]] = (
    (0.02, 10.0),
    (0.05, 8.0),
    (0.10, 6.0),
    (0.20, 3.0),
    (float("inf"), 1.0),  # exact type match but >20% size error still scores 1
)

# Higher is better: award the first band whose threshold the value meets.
F1_BANDS: Final[Sequence[_Band]] = (
    (0.95, 10.0),
    (0.85, 8.0),
    (0.75, 6.0),
    (0.65, 4.0),
    (0.55, 2.0),
    (0.0, 0.0),
)

MEDIUM_IOU_BANDS: Final[Sequence[_Band]] = (
    (0.999, 35.0),
    (0.99, 25.0),
    (0.98, 20.0),
    (0.95, 15.0),
    (0.90, 10.0),
    (0.0, 0.0),
)

PATH_IOU_BANDS: Final[Sequence[_Band]] = (
    (0.99, 15.0),
    (0.95, 12.0),
    (0.85, 9.0),
    (0.75, 6.0),
    (0.65, 3.0),
    (0.0, 0.0),
)


def score_lower_is_better(value: float, bands: Sequence[_Band]) -> float:
    """Award points where a smaller ``value`` is better (edit distance, cut error)."""
    for threshold, points in bands:
        if value <= threshold:
            return points
    return 0.0


def score_higher_is_better(value: float, bands: Sequence[_Band]) -> float:
    """Award points where a larger ``value`` is better (F1, IoU)."""
    for threshold, points in bands:
        if value >= threshold:
            return points
    return 0.0


def rescale(raw: float, raw_max: float, budget: float) -> float:
    """Scale a raw table score onto its stated section budget.

    Returns ``raw`` unchanged when :data:`SCALE_TO_SECTION_BUDGET` is off, so the
    printed-table numbers remain reachable for comparison.
    """
    if not SCALE_TO_SECTION_BUDGET or raw_max <= 0:
        return raw
    return raw / raw_max * budget
