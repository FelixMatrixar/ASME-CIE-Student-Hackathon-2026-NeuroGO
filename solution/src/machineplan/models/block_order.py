"""Learned prediction of the order in which tool blocks appear.

F-027 established that a plan is a sequence of contiguous tool blocks whose order
varies between parts. The planner emitted a fixed chamfer -> pocket -> hole order,
which measured correct on only **26.5%** of parts -- the most common order is
actually holes -> chamfers -> pockets at 34.1%.

Order distribution over all 10,000 parts:

    HCP  34.1%   CPH  26.5%   CP  12.0%   HP  6.2%
    CH    5.5%   HC    5.3%   PH   4.5%   single-family  5.9%

and it is highly predictable from part geometry: **0.896 accuracy on held-out
parts against 0.349 for always guessing the most common order.**

This matters beyond the easy tier. Misordered blocks make our operation *k* a
different kind of operation from truth's *k*, which zeroes that slot in the
medium, tools and tool-path tiers as well -- only 45.4% of slots were aligned
before this.
"""

from __future__ import annotations

import functools
import pathlib
import statistics

MODEL_PATH = pathlib.Path(__file__).resolve().parents[3] / "data" / "block_order_model.joblib"

FEATURE_NAMES: tuple[str, ...] = (
    "n_holes", "n_floors", "n_chamfers", "n_blends",
    "stock_length", "stock_width", "stock_height",
    "max_hole_diameter", "mean_hole_depth", "max_pocket_depth", "n_through",
)

# Family codes as used by the label: chamfer, pocket, hole.
CHAMFER, POCKET, HOLE = "C", "P", "H"
DEFAULT_ORDER = "HCP"  # the most common order in the corpus


def part_features(features) -> list[float]:
    """The part-level feature row, in the order the model expects."""
    holes = features.holes
    return [
        float(len(holes)),
        float(len(features.pocket_floors)),
        float(len(features.chamfers)),
        float(len(features.blends)),
        features.stock_length,
        features.stock_width,
        features.stock_height,
        max((hole.diameter_mm for hole in holes), default=0.0),
        statistics.fmean([hole.depth_mm for hole in holes]) if holes else 0.0,
        max((features.stock_high[2] - floor.z for floor in features.pocket_floors), default=0.0),
        float(sum(1 for hole in holes
                  if hole.depth_type(features.stock_low[2]) == "through")),
    ]


@functools.lru_cache(maxsize=1)
def _load(path: str):
    target = pathlib.Path(path)
    if not target.exists():
        return None
    try:
        import joblib

        payload = joblib.load(target)
    except Exception:  # noqa: BLE001 - a missing or stale model must not break the pipeline
        return None
    if payload.get("features") != list(FEATURE_NAMES):
        return None
    return payload["model"]


def predict_order(features, path: pathlib.Path | None = None) -> str:
    """Predict the family order for a part, e.g. ``"HCP"``.

    Falls back to the corpus-modal order when no model is present. The result is
    always filtered to the families the part actually has, so a predicted
    ``"HCP"`` on a part with no chamfers becomes ``"HP"``.
    """
    present = ""
    if features.chamfers:
        present += CHAMFER
    if features.pocket_floors:
        present += POCKET
    if features.holes:
        present += HOLE

    model = _load(str(path or MODEL_PATH))
    predicted = DEFAULT_ORDER
    if model is not None:
        try:
            predicted = str(model.predict([part_features(features)])[0])
        except Exception:  # noqa: BLE001
            predicted = DEFAULT_ORDER

    ordered = [family for family in predicted if family in present]
    # Anything the prediction omitted still has to be emitted; append it in the
    # modal order so no operation is silently dropped.
    ordered += [f for f in DEFAULT_ORDER if f in present and f not in ordered]
    return "".join(ordered)
