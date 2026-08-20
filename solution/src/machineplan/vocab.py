"""Canonical label vocabularies and the operation token used for sequence scoring.

Two vocabularies are in play and they disagree, deliberately:

* ``vocabularies.json`` in the contest repo (what ``validate_submission.py``
  accepts) includes ``OTHER`` for both ``o1`` and ``o2``.
* The dataset itself (Dataset_Description.pdf, Tables 3 and 4) contains exactly
  three ``o1`` values and seven ``o2`` values across all 91,702 operations.
  ``OTHER`` never appears.

So ``OTHER`` passes validation but can only ever score as a mismatch. It is kept
in :data:`VALIDATOR_O1` / :data:`VALIDATOR_O2` for format-compatibility checks
and excluded from :data:`DATASET_O1` / :data:`DATASET_O2`, which is what any
predictor should actually emit from.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# What the dataset actually contains, with the published operation counts.
DATASET_O1: Final[dict[str, int]] = {
    "hole_making": 53_075,
    "mill_contour": 20_067,
    "mill_planar": 18_560,
}

DATASET_O2: Final[dict[str, int]] = {
    "DRILLING": 30_377,
    "AREA_MILL": 20_067,
    "FLOOR_WALL": 18_560,
    "SPOT_DRILLING": 14_189,
    "DEEP_HOLE_DRILLING": 4_467,
    "HOLE_MILLING": 3_470,
    "BORING_REAMING": 572,
}

TOOL_TYPES: Final[frozenset[str]] = frozenset(
    {
        "chamfer_mill",
        "twist_drill",
        "end_mill",
        "spot_drill",
        "insert_drill",
        "gun_drill",
        "spade_drill",
        "boring_tool",
    }
)

# Superset the official validator accepts.
VALIDATOR_O1: Final[frozenset[str]] = frozenset(DATASET_O1) | {"OTHER"}
VALIDATOR_O2: Final[frozenset[str]] = frozenset(DATASET_O2) | {"OTHER"}

TOTAL_OPERATIONS: Final[int] = sum(DATASET_O2.values())

# Which (o1, o2) pairings are structurally possible. AREA_MILL is exactly
# co-extensive with mill_contour (20,067 each) and FLOOR_WALL with mill_planar
# (18,560 each), so those two subtypes pin their main label uniquely; every
# remaining subtype is a hole-making strategy.
SUBTYPE_TO_MAIN: Final[dict[str, str]] = {
    "AREA_MILL": "mill_contour",
    "FLOOR_WALL": "mill_planar",
    "DRILLING": "hole_making",
    "SPOT_DRILLING": "hole_making",
    "DEEP_HOLE_DRILLING": "hole_making",
    "HOLE_MILLING": "hole_making",
    "BORING_REAMING": "hole_making",
}


@dataclass(frozen=True, slots=True)
class Operation:
    """One machining operation as an (o1, o2) token.

    Frozen and hashable so sequences of these can be compared with edit distance
    and counted as a multiset without further wrapping.
    """

    o1: str
    o2: str

    def __post_init__(self) -> None:
        if self.o1 not in VALIDATOR_O1:
            raise ValueError(f"unknown o1 label: {self.o1!r}")
        if self.o2 not in VALIDATOR_O2:
            raise ValueError(f"unknown o2 label: {self.o2!r}")

    @property
    def is_consistent(self) -> bool:
        """Whether this (o1, o2) pairing occurs in the dataset at all."""
        return SUBTYPE_TO_MAIN.get(self.o2) == self.o1

    def __str__(self) -> str:
        return f"{self.o1}/{self.o2}"


def infer_main_label(o2: str) -> str:
    """Return the only ``o1`` that co-occurs with ``o2`` in the dataset.

    Predicting ``o2`` alone is sufficient: the main label is fully determined by
    the subtype, so a model never needs to predict ``o1`` independently and can
    never lose points to an inconsistent pairing.
    """
    try:
        return SUBTYPE_TO_MAIN[o2]
    except KeyError:
        raise ValueError(f"no dataset main label for subtype {o2!r}") from None
