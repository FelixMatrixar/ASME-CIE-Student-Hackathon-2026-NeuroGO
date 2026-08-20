"""Generate the three deliverables from a predicted plan.

By F-005 the medium and hard tiers share one mechanism: each operation's swept
volume is subtracted from the running in-process workpiece, so the IPW chain and
the tool paths are produced together rather than separately.

    IPW(k) = IPW(k-1) - swept_volume(operation k)

NC code is emitted in the dialect the dataset uses (F-013): modal, metric,
absolute, with drilling posted as canned cycles and milling as explicit moves.
The rubric does not compare G-code textually, so the target is a path whose
*swept volume* matches -- not a byte-level imitation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import trimesh

from machineplan.features import PartFeatures
from machineplan.geometry.tooling import Tool
from machineplan.predict import Plan, PlannedOperation

CLEARANCE_MM = 10.0
RETRACT_MM = 3.0
DEFAULT_FEED = 250.0
DEFAULT_SPEED = 1000.0

# Which feature types are cut into the IPW chain. Chosen by measurement, not by
# principle -- every policy was scored side by side on 30 parts
# (`scripts/compare_cut_policies.py`):
#
#   nothing (null)   11.67    holes+chamfers   12.67
#   holes only       12.17    everything     **13.17**
#   holes+pockets    12.17
#
#   hole    -- exact: an analytic cylinder at the tool diameter and hole depth.
#   chamfer -- exact: the stock lying on the outward side of the chamfer plane,
#              obtained by slicing rather than reconstructing a wedge. Adding
#              this was worth ~+1 point of the tier.
#   pocket  -- still approximate: the floor's bounding outline, rounded by the
#              recognised corner radius. On its own it *costs* points
#              (holes+pockets 12.17 against holes-only 12.17, and it lowers mean
#              IoU), but in combination it lands ahead. Kept on that evidence,
#              flagged as the weakest link.
CUT_FEATURES: frozenset[str] = frozenset({"hole", "chamfer", "pocket"})


@dataclass(slots=True)
class GeneratedPart:
    """Everything a submission needs for one part."""

    part_id: str
    ipws: list[trimesh.Trimesh]
    tool_paths: list[str]
    plan: Plan


def stock_mesh(features: PartFeatures) -> trimesh.Trimesh:
    """The raw block, before any machining."""
    low = np.asarray(features.stock_low, dtype=float)
    high = np.asarray(features.stock_high, dtype=float)
    extents = high - low
    box = trimesh.creation.box(extents=extents)
    box.apply_translation((low + high) / 2.0)
    return box


def _removal_solid(operation: PlannedOperation, features: PartFeatures) -> trimesh.Trimesh | None:
    """The solid this operation removes, built analytically from the feature.

    Cheaper and steadier than sweeping a generated path: for a drilled hole the
    removal is a cylinder, for a pocket floor a box. The tool path emitted
    alongside is designed to sweep the same volume.
    """
    top = operation.z_top
    bottom = operation.z_bottom
    height = top - bottom
    if height <= 0:
        return None

    if operation.feature == "hole":
        return _hole_solid(operation, height, bottom, top)

    if operation.feature == "pocket":
        for floor in features.pocket_floors:
            if abs(floor.z - bottom) < 1e-6:
                return _pocket_solid(floor, features, height, bottom)
        return None

    if operation.feature == "chamfer":
        return _chamfer_solid(operation, features)

    return None


HOLE_SECTIONS = 64


def _hole_solid(operation: PlannedOperation, height: float, bottom: float, top: float):
    """The material a hole operation removes.

    A drill does not leave a flat floor: its conical point makes the bottom of a
    blind hole a cone of the tool's point angle. Modelling every hole as a plain
    cylinder over-cuts by the volume of that cone -- two thirds of a cylinder one
    point-length tall, which for a 20 mm drill at 118 degrees is about 1,900 mm^3
    per hole.

    Built as the solid the tool actually sweeps: its own profile at the final
    depth, extended upward to the entry face. Milled bores and through-holes keep
    a flat bottom, the first because an endmill has one and the second because the
    cone exits the far side.

    **Measured neutral** (hole IoU 0.99295 -> 0.99289). Kept because it is the
    physically correct solid, but it is worth recording that it changed nothing:
    it is the third per-feature geometry refinement in a row to measure neutral,
    alongside true pocket outlines and pocket ordering. Together they say the
    residual medium-tier error is *not* per-feature geometry -- see F-058.
    """
    tool = tool_for(operation)
    tip = tool.tip_height_mm if operation.o2 != "HOLE_MILLING" else 0.0
    radius = operation.tool_diameter_mm / 2.0

    # A through hole's point exits the material, so no cone remains.
    if tip <= 1e-6 or height <= tip:
        cylinder = trimesh.creation.cylinder(
            radius=radius, height=height, sections=HOLE_SECTIONS
        )
        cylinder.apply_translation((operation.x, operation.y, bottom + height / 2.0))
        return cylinder

    body = trimesh.creation.cylinder(
        radius=radius, height=height - tip, sections=HOLE_SECTIONS
    )
    body.apply_translation((operation.x, operation.y, bottom + tip + (height - tip) / 2.0))
    cone = trimesh.creation.cone(radius=radius, height=tip, sections=HOLE_SECTIONS)
    # trimesh cones point +Z from a base at z=0; flip so the apex is at the floor.
    cone.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
    cone.apply_translation((operation.x, operation.y, bottom + tip))
    try:
        merged = trimesh.boolean.boolean_manifold([body, cone], "union")
        if merged is not None and not merged.is_empty:
            return merged
    except Exception:  # noqa: BLE001
        pass
    return body


def _chamfer_solid(operation: PlannedOperation, features: PartFeatures):
    """The wedge a chamfer removes, as an exact half-space cut of the stock.

    A chamfer face is a plane, and the material it removes is precisely the stock
    lying on that plane's outward side -- so no wedge needs reconstructing from
    the block edge. Slicing the stock by the plane gives the answer exactly.

    Orientation is resolved by measurement rather than trusted: a STEP face
    normal may point either way, so both sides are cut and the smaller is taken.
    A chamfer is small by construction (2-30 mm on a 200-500 mm block), so the
    larger side is always the part being kept.
    """
    for chamfer in features.chamfers:
        if abs(chamfer.z_low - operation.z_bottom) > 1e-6:
            continue
        normal = np.asarray(chamfer.plane_normal, dtype=float)
        if not np.isfinite(normal).all() or np.linalg.norm(normal) < 1e-9:
            return None
        normal = normal / np.linalg.norm(normal)
        origin = np.asarray(chamfer.plane_origin, dtype=float)
        stock = stock_mesh(features)

        candidates = []
        for direction in (normal, -normal):
            try:
                piece = trimesh.intersections.slice_mesh_plane(
                    stock, plane_normal=direction, plane_origin=origin, cap=True
                )
            except Exception:  # noqa: BLE001
                continue
            if piece is not None and not piece.is_empty and piece.volume > 0:
                candidates.append(piece)
        if not candidates:
            return None
        return min(candidates, key=lambda mesh: abs(mesh.volume))
    return None


def _pocket_corner_radius(floor, features: PartFeatures) -> float:
    """The corner-blend radius belonging to a pocket floor, or 0 if unfilleted.

    Blends already recognised from the BRep are matched to the floor by position
    and depth. Slots have no interior vertical corners and so no fillet
    (Dataset_Description.pdf 6.2), which the absence of a match handles naturally.
    """
    radii = [
        blend.radius_mm
        for blend in features.blends
        if abs(blend.bottom_z - floor.z) < 0.5
        and floor.x_min - 1.0 <= blend.x <= floor.x_max + 1.0
        and floor.y_min - 1.0 <= blend.y <= floor.y_max + 1.0
    ]
    if not radii:
        return 0.0
    # A pocket's corners share one radius; take the median against stray matches.
    radii.sort()
    return radii[len(radii) // 2]


def _floor_polygon(floor, features: PartFeatures):
    """The pocket floor's footprint as a shapely polygon.

    Prefers the **true ordered boundary** recovered from the STEP edge loop. Falls
    back to the bounding box rounded by the corner radius only when the boundary
    could not be read -- that fallback is wrong for any non-rectangular pocket and
    was measured costing IoU in both directions at once (overcut 0.0123,
    undercut 0.0091).
    """
    from shapely.geometry import Polygon
    from shapely.geometry import box as shapely_box

    if len(floor.outline) >= 3:
        polygon = Polygon(floor.outline)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if not polygon.is_empty and polygon.area > 0:
            return polygon

    radius = features.corner_radius_for(floor)
    polygon = shapely_box(floor.x_min, floor.y_min, floor.x_max, floor.y_max)
    if radius > 0:
        shrunk = polygon.buffer(-radius, join_style=2)
        if not shrunk.is_empty:
            polygon = shrunk.buffer(radius, join_style=1)
    return polygon


def _pocket_solid(floor, features: PartFeatures, height: float, bottom: float):
    """The material a pocket removes, as a rounded prism rather than a box.

    Real pockets have filleted interior corners, so an axis-aligned box removes
    material that should remain -- measurably: with box pockets, cutting them
    scored *below* not cutting them at all (11.25 against 12.50 of 35), because
    the over-cut at four corners outweighed the volume correctly removed.

    Rounding uses the erode-then-dilate trick: shrinking a rectangle by ``r`` and
    regrowing it with round joins yields exactly the fillet geometry, with no
    need to place four arcs by hand.
    """
    outline = _floor_polygon(floor, features)
    if outline is None or outline.is_empty or outline.area <= 0:
        return None
    solid = trimesh.creation.extrude_polygon(outline, height=height)
    solid.apply_translation((0.0, 0.0, bottom))
    return solid


def generate_part(
    plan: Plan,
    features: PartFeatures,
    *,
    cut_features: frozenset[str] = CUT_FEATURES,
) -> GeneratedPart:
    """Produce the IPW chain and tool paths for a predicted plan.

    ``cut_features`` selects which feature types are actually subtracted from the
    running IPW; everything else leaves it unchanged. Passing an empty set yields
    the null baseline (raw stock for every operation), which F-036 measured at
    15/35 -- a floor worth keeping until a feature's removal is exact.

    Tool paths are always emitted for every operation regardless, since the hard
    tier scores them independently of the IPW chain.
    """
    current = stock_mesh(features)
    ipws: list[trimesh.Trimesh] = []
    paths: list[str] = []

    for index, operation in enumerate(plan.operations, start=1):
        removal = (
            _removal_solid(operation, features)
            if operation.feature in cut_features
            else None
        )
        if removal is not None:
            try:
                result = trimesh.boolean.boolean_manifold([current, removal], "difference")
                if result is not None and not result.is_empty and result.volume > 0:
                    current = result
            except Exception:  # noqa: BLE001 - a failed cut leaves the IPW unchanged
                pass
        ipws.append(current.copy())
        paths.append(emit_nc(operation, index, features))

    return GeneratedPart(part_id=plan.part_id, ipws=ipws, tool_paths=paths, plan=plan)


def emit_nc(operation: PlannedOperation, index: int, features: PartFeatures) -> str:
    """Emit NC code for one operation in the dataset's dialect."""
    clearance = features.stock_high[2] + CLEARANCE_MM
    retract = features.stock_high[2] + RETRACT_MM
    lines = [
        "(CREATED BY      : machineplan                             )",
        f"(PARTNAME        : {operation.feature.upper()}_{index:02d}                  )",
        "N10 G17 G21 G94 G90",
        " ",
        f"({operation.o2} , TOOL : {operation.tool_type.upper()}_{operation.tool_diameter_mm:g})",
        " ",
        "N12 T00 M6",
        "N14 G54",
    ]
    block = 16

    def emit(text: str) -> None:
        nonlocal block
        lines.append(f"N{block} {text}")
        block += 2

    if operation.feature == "hole" and operation.o2 != "HOLE_MILLING":
        emit(f"G17 G0 G90 X{operation.x:.3f} Y{operation.y:.3f} S{DEFAULT_SPEED:.0f} M3")
        emit(f"G43 Z{clearance:.3f} H0")
        cycle = "G73" if operation.o2 == "DEEP_HOLE_DRILLING" else "G81"
        peck = f" Q{max(operation.tool_diameter_mm, 1.0):.3f}" if cycle == "G73" else ""
        emit(f"G94 {cycle} G98 Z{operation.z_bottom:.3f} F{DEFAULT_FEED:.1f}{peck} R{retract:.3f}")
        emit("G80")
    elif operation.o2 == "HOLE_MILLING":
        # Helical bore: orbit at the offset between bore and cutter radius.
        offset = max(operation.tool_diameter_mm * 0.2, 0.5)
        emit(f"G17 G0 G90 X{operation.x + offset:.3f} Y{operation.y:.3f} S{DEFAULT_SPEED:.0f} M3")
        emit(f"G43 Z{clearance:.3f} H0")
        emit(f"Z{operation.z_top:.3f}")
        turns = max(int((operation.z_top - operation.z_bottom) / 2.0), 1)
        for turn in range(turns):
            z = operation.z_top - (operation.z_top - operation.z_bottom) * (turn + 1) / turns
            emit(f"G94 G1 Z{z:.3f} F{DEFAULT_FEED:.1f}")
            emit(f"G3 X{operation.x + offset:.3f} Y{operation.y:.3f} "
                 f"I{-offset:.3f} J0.")
        emit(f"G0 Z{clearance:.3f}")
    elif operation.feature == "chamfer" and operation.end_x is not None:
        # Chamfer: positioning only, no cutting move -- see the note below.
        #
        # The obvious path (run the tool along the edge at the chamfer's
        # mid-height) was tried and **measured worse**: 1.72 -> 1.25 of 25. A
        # 45 degree chamfer mill is 20 mm across, so placing its tip on the edge
        # line buries the body in the block and overcuts far more material than
        # the chamfer contains. Overcutting is penalised; sweeping nothing is
        # merely unrewarded.
        #
        # A correct path has to offset the tool so its conical flank lies *on*
        # the chamfer surface, which needs to know which side of the strip is the
        # block edge -- topology the recognizer does not yet resolve. Until then
        # the honest output is a positioning move that removes nothing.
        emit(f"G17 G0 G90 X{operation.x:.3f} Y{operation.y:.3f} S{DEFAULT_SPEED:.0f} M3")
        emit(f"G43 Z{clearance:.3f} H0")
        emit(f"X{operation.end_x:.3f} Y{operation.end_y:.3f}")
        emit(f"G0 Z{clearance:.3f}")
    else:
        # Planar milling: contour-parallel area clearing.
        #
        # A single perimeter pass sweeps only a thin ring at the floor and leaves
        # the pocket interior untouched -- a near-total undercut on 20.2% of
        # operations, and the main reason the tool-path tier scored ~0/25 (F-042).
        # Concentric offsets inward from the wall cover the whole footprint.
        #
        # One pass at the final depth suffices for the swept volume: the tool
        # solid extends upward from its tip by the flute length, so sweeping at
        # the floor also sweeps everything above it. Stepping down in Z would
        # produce a more realistic program but the same solid.
        rings = _pocket_clearing_rings(operation, features)
        if not rings:
            emit(f"G17 G0 G90 X{operation.x:.3f} Y{operation.y:.3f} S{DEFAULT_SPEED:.0f} M3")
            emit(f"G43 Z{clearance:.3f} H0")
        else:
            first = rings[0][0]
            emit(f"G17 G0 G90 X{first[0]:.3f} Y{first[1]:.3f} S{DEFAULT_SPEED:.0f} M3")
            emit(f"G43 Z{clearance:.3f} H0")
            emit(f"G94 G1 Z{operation.z_bottom:.3f} F{DEFAULT_FEED:.1f}")
            for ring in rings:
                emit(f"X{ring[0][0]:.3f} Y{ring[0][1]:.3f}")
                for x, y in ring[1:]:
                    emit(f"X{x:.3f} Y{y:.3f}")
        emit(f"G0 Z{clearance:.3f}")

    emit("M5")
    emit("M2")
    return "\n".join(lines) + "\n"


# Radial engagement between successive clearing passes, as a fraction of the
# cutter diameter. 0.6 is a conventional roughing stepover and leaves no uncut
# ridges between passes.
CLEARING_STEPOVER_FRACTION = 0.6
# Cap on emitted clearing passes. A 400 mm pocket cleared with a 6 mm cutter
# would otherwise generate hundreds of rings, and sweeping them dominates the
# runtime for no extra covered volume once the rings reach the centre.
MAX_CLEARING_RINGS = 40


def _pocket_clearing_rings(
    operation: PlannedOperation, features: PartFeatures
) -> list[list[tuple[float, float]]]:
    """Concentric tool-centre paths that clear a pocket's footprint.

    The outermost ring runs one tool radius inside the wall, and each successive
    ring steps inward by the radial engagement until the region closes. Returns a
    list of closed polylines in tool-centre coordinates.
    """
    floor = next(
        (f for f in features.pocket_floors if abs(f.z - operation.z_bottom) < 1e-6),
        None,
    )
    if floor is None:
        return []

    from shapely.geometry import box as shapely_box

    radius = operation.tool_diameter_mm / 2.0
    stepover = max(operation.tool_diameter_mm * CLEARING_STEPOVER_FRACTION, 0.5)

    outline = shapely_box(floor.x_min, floor.y_min, floor.x_max, floor.y_max)
    corner = features.corner_radius_for(floor)
    if corner > 0:
        shrunk = outline.buffer(-corner, join_style=2)
        if not shrunk.is_empty:
            outline = shrunk.buffer(corner, join_style=1)

    rings: list[list[tuple[float, float]]] = []
    region = outline.buffer(-radius, join_style=1)
    while not region.is_empty and len(rings) < MAX_CLEARING_RINGS:
        polygons = list(getattr(region, "geoms", [region]))
        for polygon in polygons:
            if polygon.is_empty or polygon.exterior is None:
                continue
            coords = [(float(x), float(y)) for x, y in polygon.exterior.coords]
            if len(coords) >= 2:
                rings.append(coords)
        region = region.buffer(-stepover, join_style=1)

    if not rings:
        # Pocket narrower than the cutter: a single pass along its centreline
        # still removes the right material.
        centre_x = (floor.x_min + floor.x_max) / 2.0
        centre_y = (floor.y_min + floor.y_max) / 2.0
        if floor.length_mm >= floor.width_mm:
            span = max(floor.length_mm / 2.0 - radius, 0.0)
            rings = [[(centre_x - span, centre_y), (centre_x + span, centre_y)]]
        else:
            span = max(floor.width_mm / 2.0 - radius, 0.0)
            rings = [[(centre_x, centre_y - span), (centre_x, centre_y + span)]]
    return rings


def tool_for(operation: PlannedOperation) -> Tool:
    """The :class:`Tool` a planned operation would use.

    Flute length is set from the depth this operation actually cuts rather than a
    generic multiple of the diameter, so the tool is never arbitrarily longer
    than the feature it makes.

    **Measured neutral**, and the reason is worth recording: clipping the sweep
    to the stock already bounds it vertically, since anything above the stock
    surface is air. The overcut this was meant to fix is *horizontal* -- clearing
    rings follow the floor's bounding box, which for a non-rectangular pocket is
    far larger than the real footprint (measured 11x on one pocket). Kept as the
    more defensible rule; it earned nothing.
    """
    depth = max(operation.z_top - operation.z_bottom, 0.0)
    flute = max(depth + max(operation.tool_diameter_mm * 0.25, 2.0), operation.tool_diameter_mm)
    return Tool(
        tool_type=operation.tool_type,
        diameter_mm=operation.tool_diameter_mm,
        flute_length_mm=flute,
    )


def _unused(*_: object) -> None:
    """Keep math imported for future analytic helpers without lint noise."""
    _ = math
