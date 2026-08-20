"""Feature recognition from the BRep: holes, pockets and chamfers.

At inference the only real geometric input is the ``.stp`` file, so this is the
front of the whole pipeline. The output vocabulary mirrors the dataset's
generative taxonomy (Dataset_Description.pdf 6.1.2): holes are through or blind,
pockets are corner / edge / center / slot, chamfers sit on top edges.

**Distinguishing a hole from a pocket corner blend** is the one genuinely
delicate part. Both appear as ``CYLINDRICAL_SURFACE`` faces with a vertical axis,
and 25% of all surfaces in the corpus are cylindrical. The discriminator used
here is angular sweep: a hole's wall closes on itself (a full 360 degrees, so its
boundary contains complete circles), while a fillet is a partial arc, typically
90 degrees, sharing tangent edges with two planar walls. Sweep is inferred from
whether the face's boundary carries closed circular edges of the same radius as
the surface.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from machineplan.parsing.step import Face, StepModel

HoleDepth = Literal["through", "blind"]

# Two lengths agree to within this before they are treated as equal (mm).
TOLERANCE = 1e-4
# Holes in the dataset span 5-50 mm diameter (Dataset_Description.pdf Table 2).
MIN_HOLE_DIAMETER = 4.0
MAX_HOLE_DIAMETER = 60.0


@dataclass(frozen=True, slots=True)
class Hole:
    """A cylindrical hole cut downward from the top face."""

    diameter_mm: float
    x: float
    y: float
    top_z: float
    bottom_z: float

    @property
    def depth_mm(self) -> float:
        return self.top_z - self.bottom_z

    @property
    def radius_mm(self) -> float:
        return self.diameter_mm / 2.0

    def depth_type(self, stock_bottom_z: float) -> HoleDepth:
        return "through" if abs(self.bottom_z - stock_bottom_z) <= 1e-3 else "blind"

    def aspect_ratio(self) -> float:
        """Depth over diameter -- what decides peck vs. straight drilling."""
        return self.depth_mm / self.diameter_mm if self.diameter_mm else 0.0

    def __str__(self) -> str:
        return f"hole D{self.diameter_mm:.2f} at ({self.x:.1f},{self.y:.1f}) depth {self.depth_mm:.2f}"


@dataclass(frozen=True, slots=True)
class Blend:
    """A vertical fillet on a pocket's interior corner."""

    radius_mm: float
    x: float
    y: float
    top_z: float
    bottom_z: float

    @property
    def depth_mm(self) -> float:
        return self.top_z - self.bottom_z


@dataclass(frozen=True, slots=True)
class Chamfer:
    """A slanted plane along a top edge of the block."""

    area_mm2: float
    z_low: float
    z_high: float
    normal_z: float
    x_min: float = 0.0
    x_max: float = 0.0
    y_min: float = 0.0
    y_max: float = 0.0
    # The chamfer's supporting plane. A chamfer removes exactly the stock lying
    # on the outward side of this plane, so storing it turns the removal volume
    # into a half-space intersection instead of a wedge to be reconstructed.
    plane_origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    plane_normal: tuple[float, float, float] = (0.0, 0.0, 1.0)

    @property
    def height_mm(self) -> float:
        return self.z_high - self.z_low

    @property
    def runs_along_x(self) -> bool:
        """Whether the chamfer runs along the X axis (a long, narrow strip in X)."""
        return (self.x_max - self.x_min) >= (self.y_max - self.y_min)

    @property
    def centre(self) -> tuple[float, float]:
        return ((self.x_min + self.x_max) / 2.0, (self.y_min + self.y_max) / 2.0)

    def path_endpoints(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """The two ends of the edge this chamfer runs along.

        A chamfer is a long narrow strip; the tool travels its length. Without
        these the generated NC path collapsed to the origin, sweeping nothing on
        21.9% of all operations.
        """
        centre_x, centre_y = self.centre
        if self.runs_along_x:
            return (self.x_min, centre_y), (self.x_max, centre_y)
        return (centre_x, self.y_min), (centre_x, self.y_max)


@dataclass(frozen=True, slots=True)
class PocketFloor:
    """A horizontal plane below the stock top -- the floor of a pocket or slot."""

    z: float
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    # The floor's true outer boundary in XY, ordered. Empty when it could not be
    # recovered, in which case callers fall back to the bounding box. A box is
    # wrong for any pocket that is not an axis-aligned rectangle, and it loses
    # IoU in *both* directions -- measured 0.979 for pockets against 0.993 for
    # holes and 0.995 for chamfers.
    outline: tuple[tuple[float, float], ...] = ()

    @property
    def length_mm(self) -> float:
        return self.x_max - self.x_min

    @property
    def width_mm(self) -> float:
        return self.y_max - self.y_min

    @property
    def footprint_mm2(self) -> float:
        return self.length_mm * self.width_mm

    def touches_boundary(self, low: tuple[float, float, float], high: tuple[float, float, float],
                         tolerance: float = 1e-3) -> int:
        """How many of the block's four sides this floor reaches.

        Distinguishes pocket types the way the dataset defines them: a centre
        pocket touches no side, an edge pocket one, a corner pocket two, and a
        slot spans the block so reaches two opposite sides.
        """
        return sum(
            (
                abs(self.x_min - low[0]) < tolerance,
                abs(self.x_max - high[0]) < tolerance,
                abs(self.y_min - low[1]) < tolerance,
                abs(self.y_max - high[1]) < tolerance,
            )
        )


@dataclass(frozen=True, slots=True)
class PartFeatures:
    """Everything recognised from one part's BRep."""

    holes: tuple[Hole, ...]
    blends: tuple[Blend, ...]
    stock_low: tuple[float, float, float]
    stock_high: tuple[float, float, float]
    planar_faces: int
    cylindrical_faces: int
    chamfers: tuple[Chamfer, ...] = ()
    pocket_floors: tuple[PocketFloor, ...] = ()

    @property
    def stock_height(self) -> float:
        return self.stock_high[2] - self.stock_low[2]

    @property
    def stock_length(self) -> float:
        return self.stock_high[0] - self.stock_low[0]

    @property
    def stock_width(self) -> float:
        return self.stock_high[1] - self.stock_low[1]

    @property
    def through_holes(self) -> tuple[Hole, ...]:
        return tuple(h for h in self.holes if h.depth_type(self.stock_low[2]) == "through")

    @property
    def blind_holes(self) -> tuple[Hole, ...]:
        return tuple(h for h in self.holes if h.depth_type(self.stock_low[2]) == "blind")

    def corner_radius_for(self, floor: "PocketFloor") -> float:
        """The corner-blend radius belonging to ``floor``, or 0 if unfilleted.

        Slots have no interior vertical corners and therefore no fillet
        (Dataset_Description.pdf 6.2), which an empty match handles naturally.
        """
        radii = [
            blend.radius_mm
            for blend in self.blends
            if abs(blend.bottom_z - floor.z) < 0.5
            and floor.x_min - 1.0 <= blend.x <= floor.x_max + 1.0
            and floor.y_min - 1.0 <= blend.y <= floor.y_max + 1.0
        ]
        if not radii:
            return 0.0
        radii.sort()
        return radii[len(radii) // 2]

    def reach_ratio_for(self, floor: "PocketFloor") -> float:
        """Pocket size over the largest endmill its corners admit.

        An interior corner of radius ``r`` can only be machined by an endmill of
        diameter at most ``2r``, so a wide pocket with tight corners cannot be
        cleared by the tool that fits its corners -- the signal for whether NX
        splits it into a roughing pass plus a smaller finishing one.
        Returns 0 when the pocket has no fillet.
        """
        radius = self.corner_radius_for(floor)
        if radius <= 0:
            return 0.0
        return min(floor.length_mm, floor.width_mm) / (2.0 * radius)

    @property
    def pocket_depths(self) -> tuple[float, ...]:
        """Distinct Z levels at which blends bottom out -- one per pocket floor."""
        levels = sorted({round(b.bottom_z, 3) for b in self.blends})
        return tuple(levels)

    def __str__(self) -> str:
        return (
            f"PartFeatures({len(self.holes)} holes "
            f"[{len(self.through_holes)} through, {len(self.blind_holes)} blind], "
            f"{len(self.blends)} corner blends, "
            f"stock {self.stock_length:.0f}x{self.stock_width:.0f}x{self.stock_height:.0f})"
        )


def _is_full_cylinder(face: Face) -> bool:
    """Whether a cylindrical face closes on itself rather than being a corner arc.

    The discriminator is a **closed** boundary edge -- one whose start and end
    vertex are the same instance. A hole wall wraps 360 degrees and so has one;
    a pocket corner blend is a partial sweep with two distinct arc endpoints.

    An earlier version tested whether the boundary contained a ``CIRCLE`` of the
    surface radius. That is true of fillets too -- a 90 degree arc is a full
    circle entity trimmed by its vertices -- and it over-detected holes by 2.6x,
    reporting 6.16 holes per part against the published 2.33.
    """
    if face.radius is None:
        return False
    return face.closed_circles > 0


def extract_features(model: StepModel) -> PartFeatures:
    """Recognise holes, corner blends and stock extents from a parsed STEP model."""
    low, high = model.bounds

    holes: list[Hole] = []
    blends: list[Blend] = []
    chamfers: list[Chamfer] = []
    floors: list[PocketFloor] = []
    planar = cylindrical = 0
    top_z = high[2]
    bottom_z = low[2]

    for face in model.faces:
        if face.is_planar:
            planar += 1
            if face.placement is None or not face.vertices:
                continue
            normal_z = face.placement.axis[2]
            z_low, z_high = face.z_range
            xs = [v[0] for v in face.vertices]
            ys = [v[1] for v in face.vertices]

            if _is_slanted(normal_z):
                # A chamfer plane: neither horizontal nor vertical. In this
                # dataset chamfers are 45 degrees, so |nz| ~ 0.707.
                # Anchor the plane on a real vertex of the face rather than the
                # placement origin, which for a STEP plane can sit anywhere on
                # the surface -- including outside the solid.
                anchor = face.vertices[0]
                chamfers.append(
                    Chamfer(
                        area_mm2=(max(xs) - min(xs)) * (max(ys) - min(ys)),
                        z_low=z_low,
                        z_high=z_high,
                        normal_z=normal_z,
                        x_min=min(xs), x_max=max(xs),
                        y_min=min(ys), y_max=max(ys),
                        plane_origin=anchor,
                        plane_normal=face.placement.axis,
                    )
                )
            elif abs(abs(normal_z) - 1.0) < 1e-6:
                # Horizontal plane. A pocket floor sits strictly between the
                # stock bottom and top; the two extremes are the stock faces.
                if bottom_z + 1e-3 < z_low < top_z - 1e-3:
                    ring = model.outer_boundary(face)
                    floors.append(
                        PocketFloor(
                            z=z_low,
                            x_min=min(xs), x_max=max(xs),
                            y_min=min(ys), y_max=max(ys),
                            outline=tuple((p[0], p[1]) for p in ring),
                        )
                    )
            continue
        if not face.is_cylindrical:
            continue
        cylindrical += 1
        if face.radius is None or not face.is_vertical_axis or face.placement is None:
            continue

        # Named distinctly from the stock's `bottom_z`/`top_z`. They were once
        # the same names, which silently rebound the stock bounds to whichever
        # hole was processed last -- so every planar face examined afterwards was
        # tested against that hole's z-range instead of the block's, and most
        # pocket floors were rejected. That single line accounted for the 22.5%
        # of FLOOR_WALL operations with no recognised floor (F-054, F-055).
        face_bottom_z, face_top_z = face.z_range
        origin = face.placement.origin
        diameter = face.radius * 2.0

        if _is_full_cylinder(face) and MIN_HOLE_DIAMETER <= diameter <= MAX_HOLE_DIAMETER:
            holes.append(
                Hole(
                    diameter_mm=diameter,
                    x=origin[0],
                    y=origin[1],
                    top_z=face_top_z,
                    bottom_z=face_bottom_z,
                )
            )
        else:
            blends.append(
                Blend(
                    radius_mm=face.radius,
                    x=origin[0],
                    y=origin[1],
                    top_z=face_top_z,
                    bottom_z=face_bottom_z,
                )
            )

    holes = _merge_coaxial(holes)
    merged_floors = _merge_floors(floors)
    return PartFeatures(
        holes=tuple(sorted(holes, key=lambda h: (-h.diameter_mm, h.x, h.y))),
        blends=tuple(blends),
        stock_low=low,
        stock_high=high,
        planar_faces=planar,
        cylindrical_faces=cylindrical,
        chamfers=tuple(chamfers),
        pocket_floors=tuple(_reject_hole_bottoms(merged_floors, holes)),
    )


# A real pocket's footprint spans 204-42,349 mm^2 with both sides well above a
# millimetre (Dataset_Description.pdf 6.6). Anything thinner is not a pocket.
MIN_FLOOR_EXTENT_MM = 2.0

# Fraction of the smaller patch that must overlap before two floor patches at the
# same depth are treated as one pocket. Any-contact merging fused distinct
# pockets; see the note in _merge_floors.
MERGE_OVERLAP_FRACTION = 0.30


def _reject_hole_bottoms(
    floors: list[PocketFloor],
    holes: list[Hole],
    tolerance: float = 1.0,
) -> list[PocketFloor]:
    """Drop horizontal faces that are blind-hole bottoms, not pocket floors.

    A blind hole ends in a flat circular face lying strictly between the stock
    bottom and top, which is exactly the test for a pocket floor -- so hole
    bottoms were being counted as pockets. On `featured_part_00019` that produced
    three spurious floors (footprints ``5x0``, ``5x0``, ``5x0``) on a part with
    **no pockets at all**, and over-counting like it made `FLOOR_WALL` wrong on
    58% of parts while its *net* error stayed near zero.

    Two filters, both conservative:
      * a degenerate footprint (either side below :data:`MIN_FLOOR_EXTENT_MM`)
        cannot be a pocket;
      * a footprint that sits within a recognised hole's circle is that hole's
        bottom.
    """
    kept: list[PocketFloor] = []
    for floor in floors:
        if floor.length_mm < MIN_FLOOR_EXTENT_MM or floor.width_mm < MIN_FLOOR_EXTENT_MM:
            continue

        centre_x = (floor.x_min + floor.x_max) / 2.0
        centre_y = (floor.y_min + floor.y_max) / 2.0
        is_hole_bottom = False
        for hole in holes:
            radius = hole.radius_mm + tolerance
            within = (
                abs(centre_x - hole.x) <= radius
                and abs(centre_y - hole.y) <= radius
                and floor.length_mm <= hole.diameter_mm + 2 * tolerance
                and floor.width_mm <= hole.diameter_mm + 2 * tolerance
            )
            if within:
                is_hole_bottom = True
                break
        if not is_hole_bottom:
            kept.append(floor)
    return kept


def _is_slanted(normal_z: float, tolerance: float = 1e-3) -> bool:
    """Whether a plane is neither horizontal nor vertical -- i.e. a chamfer."""
    magnitude = abs(normal_z)
    return tolerance < magnitude < 1.0 - tolerance


def _merge_floors(floors: list[PocketFloor], tolerance: float = 1e-3) -> list[PocketFloor]:
    """Merge floor patches that share a Z level and overlap in plan.

    One pocket floor is often split into several faces by the holes and blends
    piercing it; left separate they would be counted as several pockets.
    """
    merged: list[PocketFloor] = []
    for floor in sorted(floors, key=lambda f: (round(f.z, 3), f.x_min, f.y_min)):
        for index, existing in enumerate(merged):
            if abs(existing.z - floor.z) > tolerance:
                continue
            # Require *substantial* overlap, not mere bounding-box contact.
            #
            # This was tightened on the hypothesis that any-contact merging was
            # fusing distinct pockets, which would explain the 22.5% of
            # FLOOR_WALL operations matching no recognised floor. **It measured
            # exactly neutral** -- 1.220 floors per part and 68.0% exact counts,
            # before and after. The missing pockets are therefore not being
            # merged away; their floor faces are never detected in the first
            # place. Kept because it is the more defensible rule, not because it
            # earned anything.
            overlap_x = min(floor.x_max, existing.x_max) - max(floor.x_min, existing.x_min)
            overlap_y = min(floor.y_max, existing.y_max) - max(floor.y_min, existing.y_min)
            if overlap_x <= tolerance or overlap_y <= tolerance:
                continue
            overlap_area = overlap_x * overlap_y
            smaller_area = min(
                max(floor.length_mm * floor.width_mm, 1e-9),
                max(existing.length_mm * existing.width_mm, 1e-9),
            )
            if overlap_area / smaller_area >= MERGE_OVERLAP_FRACTION:
                merged[index] = PocketFloor(
                    z=existing.z,
                    x_min=min(existing.x_min, floor.x_min),
                    x_max=max(existing.x_max, floor.x_max),
                    y_min=min(existing.y_min, floor.y_min),
                    y_max=max(existing.y_max, floor.y_max),
                )
                break
        else:
            merged.append(floor)
    return merged


def _merge_coaxial(holes: list[Hole], tolerance: float = 1e-3) -> list[Hole]:
    """Merge cylinder faces that describe one physical hole.

    A single hole can be split across several faces -- by a chamfer crossing it,
    or by a seam -- each carrying the same axis and radius. Left unmerged they
    would be counted as several holes.
    """
    merged: list[Hole] = []
    for hole in sorted(holes, key=lambda h: (h.x, h.y, h.diameter_mm, -h.top_z)):
        for index, existing in enumerate(merged):
            same_axis = (
                math.isclose(existing.x, hole.x, abs_tol=tolerance)
                and math.isclose(existing.y, hole.y, abs_tol=tolerance)
            )
            same_size = math.isclose(existing.diameter_mm, hole.diameter_mm, abs_tol=tolerance)
            overlapping = not (
                hole.bottom_z > existing.top_z + tolerance
                or hole.top_z < existing.bottom_z - tolerance
            )
            if same_axis and same_size and overlapping:
                merged[index] = Hole(
                    diameter_mm=existing.diameter_mm,
                    x=existing.x,
                    y=existing.y,
                    top_z=max(existing.top_z, hole.top_z),
                    bottom_z=min(existing.bottom_z, hole.bottom_z),
                )
                break
        else:
            merged.append(hole)
    return merged
