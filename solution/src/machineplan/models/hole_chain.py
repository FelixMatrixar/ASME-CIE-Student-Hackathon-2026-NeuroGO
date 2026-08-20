"""Learned prediction of a hole's operation chain.

F-033 established that every hole in the corpus takes one of ~14 chains, and
F-046 recorded three hand-built rules that each matched a marginal and lost
points because no threshold separated the groups. A gradient-boosted classifier
over the same features finds the boundaries that hand-tuning could not:

| Predictor | Chain accuracy | Mean |count error| per hole |
|---|---|---|
| Majority class | 0.261 | -- |
| Hand-written rules | 0.391 | 0.635 |
| **Gradient boosting** | **0.948** | **0.082** |

Measured on 1,382 held-out holes from 511 parts never seen in training. The split
is by *part*, not by hole, because holes on one part share a block, a feature mix
and a tool set.

**Feature extraction lives here**, not in the training script, so that training
and inference cannot drift apart -- the classic source of a model that scores well
offline and badly in the pipeline.
"""

from __future__ import annotations

import collections
import functools
import pathlib
from typing import Sequence

MODEL_PATH = pathlib.Path(__file__).resolve().parents[3] / "data" / "hole_chain_model.joblib"

# Order matters: it is the column order the model was fitted on.
FEATURE_NAMES: tuple[str, ...] = (
    "diameter_mm", "depth_mm", "aspect", "through", "top_drop",
    "depth_fraction", "stock_height", "n_holes", "same_diameter_count", "in_pocket",
)


def hole_features(hole, features) -> list[float]:
    """The feature row for one hole, in the order the model expects.

    Every value derives from the BRep, which is all that exists at inference
    (Tutorial p.3). Nothing here reads an operation file.
    """
    top = features.stock_high[2]
    height = features.stock_height
    diameters = collections.Counter(round(h.diameter_mm, 2) for h in features.holes)

    in_pocket = any(
        floor.x_min - 1.0 <= hole.x <= floor.x_max + 1.0
        and floor.y_min - 1.0 <= hole.y <= floor.y_max + 1.0
        and floor.z > hole.bottom_z
        for floor in features.pocket_floors
    )
    return [
        hole.diameter_mm,
        hole.depth_mm,
        hole.aspect_ratio(),
        float(hole.depth_type(features.stock_low[2]) == "through"),
        top - hole.top_z,
        hole.depth_mm / height if height else 0.0,
        height,
        float(len(features.holes)),
        float(diameters[round(hole.diameter_mm, 2)]),
        float(in_pocket),
    ]


@functools.lru_cache(maxsize=1)
def _load(path: str):
    """Load the fitted model once. Returns ``None`` when it has not been built."""
    target = pathlib.Path(path)
    if not target.exists():
        return None
    try:
        import joblib

        payload = joblib.load(target)
    except Exception:  # noqa: BLE001 - a missing or stale model must not break the pipeline
        return None
    if payload.get("features") != list(FEATURE_NAMES):
        # Refuse a model fitted on a different feature set rather than silently
        # feeding it mismatched columns.
        return None
    return payload["model"]


def is_available(path: pathlib.Path | None = None) -> bool:
    return _load(str(path or MODEL_PATH)) is not None


def predict_chain(hole, features, path: pathlib.Path | None = None) -> list[str] | None:
    """Predict a hole's ordered ``o2`` chain, or ``None`` if no model is loaded."""
    model = _load(str(path or MODEL_PATH))
    if model is None:
        return None
    row = [hole_features(hole, features)]
    try:
        label = model.predict(row)[0]
    except Exception:  # noqa: BLE001
        return None
    return [part for part in str(label).split("|") if part]


def predict_chains(holes: Sequence, features, path: pathlib.Path | None = None) -> list[list[str]] | None:
    """Batch form of :func:`predict_chain` -- one model call for the whole part."""
    model = _load(str(path or MODEL_PATH))
    if model is None or not holes:
        return None
    rows = [hole_features(hole, features) for hole in holes]
    try:
        labels = model.predict(rows)
    except Exception:  # noqa: BLE001
        return None
    return [[part for part in str(label).split("|") if part] for label in labels]
