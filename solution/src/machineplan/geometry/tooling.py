"""Cutting-tool solids, built as solids of revolution from a 2D profile.

Every tool in the dataset's vocabulary is a surface of revolution about the
spindle axis, and -- importantly for :mod:`machineplan.geometry.sweep` -- every
one of them is **convex**. A flat endmill is a cylinder; a drill is a cylinder
with a conical point, which is a bullet shape and still convex; a chamfer mill is
a truncated cone on a cylindrical shank. Convexity is what makes an exact swept
volume cheap to compute.

The control point is the **tool tip**: the origin of each profile sits at the
lowest cutting point, because that is what NC coordinates refer to once ``G43``
length compensation is applied.

.. warning::
   Tip diameters, point angles and flute lengths here are defaults inferred from
   the tool names published in Dataset_Description.pdf Table 5 (e.g. "Chamfer
   Mill 20 x 3 x 45 deg.", "NC Spot Drill, 142 deg"). They must be **calibrated
   against ``details.txt``** once the dataset is available -- the swept volume,
   and therefore 25 of the 100 points, depends directly on getting them right.
   See ``Q-006`` in FINDINGS.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import numpy as np
import trimesh

# Angular resolution when revolving a profile. 64 sections keeps the radius
# error below ~0.1% of the tool radius, comfortably under the tolerance the
# tool-diameter rubric bands care about.
DEFAULT_SECTIONS = 64

# Defaults pending calibration against details.txt -- see module warning.
DEFAULT_FLUTE_RATIO = 4.0  # flute length as a multiple of diameter
CHAMFER_TIP_DIAMETER_MM = 3.0
CHAMFER_ANGLE_DEG = 45.0
TWIST_DRILL_POINT_ANGLE_DEG = 118.0
SPOT_DRILL_POINT_ANGLE_DEG = 142.0
INSERT_DRILL_POINT_ANGLE_DEG = 180.0  # flat-bottomed insert drills
GUN_DRILL_POINT_ANGLE_DEG = 124.0
SPADE_DRILL_POINT_ANGLE_DEG = 130.0


class UnknownToolError(ValueError):
    """Raised for a tool type outside the contest vocabulary."""


@dataclass(frozen=True, slots=True)
class Tool:
    """A cutting tool, identified as the rubric identifies it: type plus diameter.

    ``tip_length_mm`` overrides the tip geometry derived from the tool type. Real
    tools publish this directly -- drills as ``(PL) Point Length``, chamfer mills
    as ``(C) Chamfer Length`` -- so prefer :meth:`from_tool_info`, which uses the
    measured value rather than trusting a formula.
    """

    tool_type: str
    diameter_mm: float
    flute_length_mm: float | None = None
    tip_length_mm: float | None = None

    def __post_init__(self) -> None:
        if self.diameter_mm <= 0 or not math.isfinite(self.diameter_mm):
            raise ValueError(f"tool diameter must be a finite positive number, got {self.diameter_mm}")
        if self.tip_length_mm is not None and self.tip_length_mm < 0:
            raise ValueError(f"tip length cannot be negative, got {self.tip_length_mm}")

    @classmethod
    def from_tool_info(cls, info: "ToolInfoLike") -> "Tool":
        """Build a tool from a parsed ``details.txt`` tool section.

        Uses the published diameter, flute length and tip length, falling back to
        derived geometry only where a value is absent.
        """
        tool_type = info.tool_type
        if tool_type is None:
            raise UnknownToolError(f"unmapped NX tool type: {info.nx_tool_type!r}")
        if info.diameter_mm is None:
            raise UnknownToolError(f"tool {info.tool_id!r} publishes no (D) diameter")
        return cls(
            tool_type=tool_type,
            diameter_mm=info.diameter_mm,
            flute_length_mm=info.flute_length_mm,
            tip_length_mm=info.tip_length_mm,
        )

    @property
    def radius_mm(self) -> float:
        return self.diameter_mm / 2.0

    @property
    def effective_flute_length_mm(self) -> float:
        if self.flute_length_mm is not None:
            return self.flute_length_mm
        return self.diameter_mm * DEFAULT_FLUTE_RATIO

    def profile(self) -> np.ndarray:
        """Return the ``(radius, height)`` profile, tip at the origin.

        The profile is a closed half-section revolved about the Z axis: it starts
        on the axis at the tip, runs out to the cutting edge, up the flute, and
        back to the axis at the top.
        """
        return _profile_for(
            self.tool_type,
            self.radius_mm,
            self.effective_flute_length_mm,
            self.tip_length_mm,
        )

    def solid(self, sections: int = DEFAULT_SECTIONS) -> trimesh.Trimesh:
        """The tool as a watertight mesh, tip at the origin, axis along +Z."""
        return _solid_for(
            self.tool_type,
            self.radius_mm,
            self.effective_flute_length_mm,
            self.tip_length_mm,
            sections,
        )

    @property
    def tip_height_mm(self) -> float:
        """Height of the tapered tip, i.e. how far up the full diameter is reached."""
        profile = self.profile()
        full_radius = profile[:, 0].max()
        for radius, height in profile:
            if radius >= full_radius - 1e-9:
                return float(height)
        return 0.0

    def __str__(self) -> str:
        return f"{self.tool_type} D{self.diameter_mm:g}mm"


class ToolInfoLike(Protocol):
    """The subset of ``parsing.details.ToolInfo`` that :meth:`Tool.from_tool_info` needs."""

    tool_id: str
    nx_tool_type: str

    @property
    def tool_type(self) -> str | None: ...
    @property
    def diameter_mm(self) -> float | None: ...
    @property
    def flute_length_mm(self) -> float | None: ...
    @property
    def tip_length_mm(self) -> float | None: ...


def _cone_height(radius: float, included_angle_deg: float) -> float:
    """Axial height of a conical point with the given included angle."""
    if included_angle_deg >= 180.0:
        return 0.0
    half_angle = math.radians(included_angle_deg / 2.0)
    return radius / math.tan(half_angle)


def _drill_profile(
    radius: float,
    flute_length: float,
    point_angle_deg: float,
    tip_length: float | None = None,
) -> np.ndarray:
    """Conical point on a cylindrical body -- convex, tip at the origin.

    ``tip_length`` is the published ``(PL) Point Length`` when available; the
    derived value from the point angle is only a fallback.
    """
    tip = tip_length if tip_length is not None else _cone_height(radius, point_angle_deg)
    body = max(flute_length, tip + 1e-3)
    return np.array(
        [
            [0.0, 0.0],
            [radius, tip],
            [radius, body],
            [0.0, body],
        ],
        dtype=float,
    )


def _endmill_profile(radius: float, flute_length: float) -> np.ndarray:
    """Flat-bottomed cylinder."""
    return np.array(
        [
            [0.0, 0.0],
            [radius, 0.0],
            [radius, flute_length],
            [0.0, flute_length],
        ],
        dtype=float,
    )


def _chamfer_profile(
    radius: float,
    flute_length: float,
    tip_length: float | None = None,
) -> np.ndarray:
    """Truncated cone rising at the chamfer angle onto a cylindrical shank.

    Named in the tool library as e.g. "Chamfer Mill 20 x 3 x 45 deg.": 20 mm
    body diameter, 3 mm tip diameter, 45 degree flank. ``tip_length`` is the
    published ``(C) Chamfer Length`` when available.
    """
    if tip_length is not None:
        rise = tip_length
        tip_radius = max(radius - rise * math.tan(math.radians(CHAMFER_ANGLE_DEG)), 0.0)
    else:
        tip_radius = min(CHAMFER_TIP_DIAMETER_MM / 2.0, radius * 0.9)
        rise = (radius - tip_radius) / math.tan(math.radians(CHAMFER_ANGLE_DEG))
    body = max(flute_length, rise + 1e-3)
    return np.array(
        [
            [0.0, 0.0],
            [tip_radius, 0.0],
            [radius, rise],
            [radius, body],
            [0.0, body],
        ],
        dtype=float,
    )


_POINT_ANGLES = {
    "twist_drill": TWIST_DRILL_POINT_ANGLE_DEG,
    "spot_drill": SPOT_DRILL_POINT_ANGLE_DEG,
    "insert_drill": INSERT_DRILL_POINT_ANGLE_DEG,
    "gun_drill": GUN_DRILL_POINT_ANGLE_DEG,
    "spade_drill": SPADE_DRILL_POINT_ANGLE_DEG,
    "boring_tool": 180.0,  # boring bars finish an existing bore with a flat face
}


def _profile_for(
    tool_type: str,
    radius: float,
    flute_length: float,
    tip_length: float | None = None,
) -> np.ndarray:
    if tool_type == "end_mill":
        return _endmill_profile(radius, flute_length)
    if tool_type == "chamfer_mill":
        return _chamfer_profile(radius, flute_length, tip_length)
    if tool_type in _POINT_ANGLES:
        return _drill_profile(radius, flute_length, _POINT_ANGLES[tool_type], tip_length)
    raise UnknownToolError(f"unknown tool type: {tool_type!r}")


@lru_cache(maxsize=256)
def _solid_for(
    tool_type: str,
    radius: float,
    flute_length: float,
    tip_length: float | None,
    sections: int,
) -> trimesh.Trimesh:
    """Revolve a tool profile into a mesh.

    Cached because a single operation sweeps the *same* tool across hundreds of
    segments, and re-revolving it each time dominates the runtime otherwise.
    """
    profile = _profile_for(tool_type, radius, flute_length, tip_length)
    solid = trimesh.creation.revolve(linestring=profile, sections=sections)
    if not solid.is_watertight:
        trimesh.repair.fill_holes(solid)
    trimesh.repair.fix_normals(solid)
    if solid.volume < 0:
        solid.invert()
    return solid


def tool_from_library_name(name: str) -> Tool | None:
    """Best-effort parse of an NX tool-library display name into a :class:`Tool`.

    Handles the forms seen in Dataset_Description.pdf Table 5, e.g.
    ``"Chamfer Mill 20 x 3 x 45 deg."``, ``"ENDMILL 16 mm (2P460-1600-NA 1630)"``,
    ``"Carbide Drill 9.4 mm (860.1-0940-075A1-MM 2214)"``. Returns ``None`` when
    the name does not yield a diameter, rather than guessing.
    """
    import re

    lowered = name.lower()
    if "chamfer" in lowered:
        tool_type = "chamfer_mill"
    elif "spot" in lowered:
        tool_type = "spot_drill"
    elif "endmill" in lowered or "end mill" in lowered:
        tool_type = "end_mill"
    elif "bore" in lowered or "boring" in lowered or "ream" in lowered:
        tool_type = "boring_tool"
    elif "gun" in lowered:
        tool_type = "gun_drill"
    elif "spade" in lowered:
        tool_type = "spade_drill"
    elif "insert" in lowered:
        tool_type = "insert_drill"
    elif "drill" in lowered:
        tool_type = "twist_drill"
    else:
        return None

    # Prefer an explicit "<number> mm"; fall back to the first bare number, which
    # is how the chamfer mills are written ("Chamfer Mill 20 x 3 x 45 deg.").
    match = re.search(r"(\d+(?:\.\d+)?)\s*mm", lowered)
    if not match:
        match = re.search(r"(\d+(?:\.\d+)?)", lowered)
    if not match:
        return None
    return Tool(tool_type=tool_type, diameter_mm=float(match.group(1)))
