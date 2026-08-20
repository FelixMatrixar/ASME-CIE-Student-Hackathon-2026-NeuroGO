"""Turn recognised BRep features into a predicted machining plan.

This is the **baseline** predictor: deliberately simple, built from the rules
mined in F-033/F-034, and intended to establish an end-to-end pipeline and a
score floor rather than to win. Every threshold here is empirical, taken from
1,120 position-matched holes, and every one is a place to improve.

Structure follows what the corpus actually does:

* **Per feature, a chain of operations** â€” F-033 found only 14 distinct chains
  across all holes, so each hole is classified into one.
* **Grouped into contiguous tool blocks** â€” F-027 found the plan is tool-change
  minimisation, so operations are batched by tool rather than emitted per
  feature.

Known gaps, all of which cost points and none of which are hidden:
  - Pocket *type* (corner / edge / center / slot) is approximated by how many
    block sides the floor touches; the real taxonomy is richer.
  - `HOLE_MILLING` selection is unexplained (Q-013); the band rule below is a
    correlation, not a mechanism.
  - Nested pockets and feature interactions are ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from machineplan.features import Hole, PartFeatures
from machineplan.models import block_order, hole_chain
from machineplan.vocab import Operation, infer_main_label

# --- thresholds mined in F-034, all empirical -------------------------------
# Holes with a spot drill average 14.1 mm; those without, 22.0 mm.
SPOT_DRILL_MAX_DIAMETER = 20.0
# DEEP_HOLE_DRILLING has mean aspect 6.27 vs 4.45, and never below 12.1 mm.
DEEP_HOLE_MIN_ASPECT = 5.0
DEEP_HOLE_MIN_DIAMETER = 12.1
# Drilling pass count. F-034 measured the true distribution over 989 holes:
# 63% take a single pass, 14% two, 15% three, 8% four -- a mean of 1.69 passes
# per hole. Crucially the *diameter* means for 1, 2 and 3 passes are nearly
# identical (16.6 / 16.9 / 17.3 mm), so diameter barely separates them; only the
# 4-pass group stands out at 23.8 mm.
#
# An earlier rule gave every hole above 12.1 mm a pilot plus a finish pass, which
# produced ~2.4 passes per hole and over-generated DRILLING by 0.94 operations
# per part -- more than the entire net count error (F-038). Since medium IoU
# tracks the operation *count* (F-037), matching the marginal distribution beats
# being right per hole, so a second pass is now added only where the evidence is
# strong.
PILOT_MIN_DIAMETER = 19.3
EXTRA_PASS_MIN_DIAMETER = 26.0
# HOLE_MILLING is followed by BORING_REAMING in only 1.9% of hole chains (F-033),
# and BORING_REAMING is the rarest subtype in the corpus at 0.6% of operations.
# Boring is therefore reserved for the top of the milled range: F-034 measured
# bored holes at 13.8-19.9 mm with a 16.4 mm mean, but a 13.5 mm threshold
# over-generated it more than threefold (62 predicted against 19 true).
BORING_MIN_DIAMETER = 18.0
# Milled holes. F-034 measured a tight 12.3-19.9 mm band, but that came from
# position-matched holes only and missed the large end: `featured_part_00008`
# has three D30.5 through-holes that NX mills
# (MILL_THROUGH_HOLE_FROM_SOLID_MATERIAL), which our drill rule turned into nine
# operations instead of three. Both groups share a *low aspect ratio*, which is
# the more reliable signal; the upper diameter bound is therefore relaxed.
# The mechanism is still unexplained -- see Q-013.
HOLE_MILLING_RANGE = (12.3, 19.9)
HOLE_MILLING_MAX_ASPECT = 3.0
# Large bores are milled regardless of aspect: relaxing the aspect limit to 4.0
# across the whole range instead caught far too many drilled holes
# (HOLE_MILLING +85, DRILLING -231), so the large end is handled as its own case.
LARGE_BORE_MIN_DIAMETER = 30.0
# Standard spot drill in the library is 12 mm (14,150 of 14,189 uses).
SPOT_DRILL_DIAMETER = 12.0
# Every one of the 20,067 AREA_MILL operations uses this one tool (F-026).
CHAMFER_MILL_DIAMETER = 20.0
# Pocket size over the largest endmill its corners admit, above which the pocket
# is split into two operations. Weakly separating (4.58 vs 3.91) but the only
# signal found -- depth and footprint do not distinguish at all (F-041).
POCKET_SPLIT_REACH_RATIO = 4.2


@dataclass(frozen=True, slots=True)
class PlannedOperation:
    """One predicted operation, with the tool and the feature it targets."""

    o1: str
    o2: str
    tool_type: str
    tool_diameter_mm: float
    x: float = 0.0
    y: float = 0.0
    z_top: float = 0.0
    z_bottom: float = 0.0
    feature: str = ""
    # Second endpoint for operations that travel along a line (chamfers).
    end_x: float | None = None
    end_y: float | None = None

    @property
    def operation(self) -> Operation:
        return Operation(self.o1, self.o2)

    @property
    def tool_key(self) -> tuple[str, float]:
        return (self.tool_type, round(self.tool_diameter_mm, 3))


@dataclass(slots=True)
class Plan:
    """A predicted plan for one part."""

    part_id: str
    operations: list[PlannedOperation] = field(default_factory=list)

    @property
    def sequence(self) -> list[Operation]:
        return [op.operation for op in self.operations]

    def __len__(self) -> int:
        return len(self.operations)

    def __str__(self) -> str:
        return f"Plan({self.part_id}, {len(self.operations)} operations)"


def _drill_size_for(diameter: float) -> float:
    """Snap a required hole size onto the 0.1 mm drill grid the library uses."""
    return round(diameter, 1)


# Tool diameter as a fraction of the finished hole diameter, measured over 1,200
# parts by `scripts/mine_tool_diameters.py`. Medians, which are far tighter than
# the means where the distribution is skewed.
#
#   subtype                pos/of      n      median     sd
#   DRILLING                 1/1    1,507      1.000    0.070
#   DRILLING                 1/2      696      0.583    0.116
#   DRILLING                 2/2      696      1.000    0.013
#   DRILLING                 1/3      207      0.263    0.065
#   DRILLING                 2/3      207      0.628    0.041
#   DRILLING                 3/3      207      1.000    0.000
#   DEEP_HOLE_DRILLING       1/1      559      0.383    0.197
#   HOLE_MILLING             1/1      371      0.779    0.106
#   BORING_REAMING           1/1       65      0.993    0.004
#
# Two corrections this made to hand-guessed values, worth naming because they
# were the whole tool-tier loss (diagnose_tools.py):
#   * DEEP_HOLE_DRILLING is a *small pilot* drill (mean 8.18 mm across only 12
#     distinct sizes), not a full-size one. Assigning the finished diameter gave
#     a 0.598 relative error and 4.3/10 on 621 operations.
#   * HOLE_MILLING uses 0.78 of the bore, not the 0.6 that was guessed.
# The final drilling pass is *exactly* the finished diameter -- sd 0.000 on the
# 3-of-3 case -- which is the one value that needs no tolerance at all.
DEEP_HOLE_DIAMETER_RATIO = 0.383
HOLE_MILLING_DIAMETER_RATIO = 0.779
BORING_DIAMETER_RATIO = 0.993
_DRILL_PILOT_RATIOS: dict[int, tuple[float, ...]] = {
    1: (1.000,),
    2: (0.583, 1.000),
    3: (0.263, 0.628, 1.000),
}


def _drill_ratio(position: int, total: int) -> float:
    """Fraction of the finished diameter for drilling pass ``position`` of ``total``."""
    if total in _DRILL_PILOT_RATIOS:
        table = _DRILL_PILOT_RATIOS[total]
        return table[min(position, len(table) - 1)]
    # Beyond the measured cases, step linearly up to full size on the last pass.
    if total <= 1:
        return 1.0
    return 0.263 + (1.0 - 0.263) * (position / (total - 1))


def _tool_for_subtype(subtype: str, diameter: float, position: int, drill_total: int) -> tuple[str, float]:
    """Pick a tool type and diameter for one step of a predicted chain.

    The classifier predicts *which* operations occur, not what they cut with, so
    sizes come from the measured ratios above rather than from the chain.
    """
    if subtype == "SPOT_DRILLING":
        # One tool across every instance in the corpus: 12 mm, 1 distinct size.
        return "spot_drill", SPOT_DRILL_DIAMETER
    if subtype == "HOLE_MILLING":
        return "end_mill", max(4.0, round(diameter * HOLE_MILLING_DIAMETER_RATIO, 1))
    if subtype == "BORING_REAMING":
        return "boring_tool", round(diameter * BORING_DIAMETER_RATIO, 1)
    if subtype == "DEEP_HOLE_DRILLING":
        return "twist_drill", _drill_size_for(max(diameter * DEEP_HOLE_DIAMETER_RATIO, 4.0))
    return "twist_drill", _drill_size_for(
        max(diameter * _drill_ratio(position, drill_total), 4.0)
    )


def plan_hole_from_chain(hole: Hole, chain: list[str]) -> list[PlannedOperation]:
    """Turn a predicted ``o2`` chain into planned operations with tools."""
    operations: list[PlannedOperation] = []
    drill_total = sum(1 for subtype in chain if subtype == "DRILLING")
    drill_seen = 0
    for subtype in chain:
        position = drill_seen
        if subtype == "DRILLING":
            drill_seen += 1
        tool_type, tool_diameter = _tool_for_subtype(
            subtype, hole.diameter_mm, position, drill_total
        )
        operations.append(
            PlannedOperation(
                o1=infer_main_label(subtype),
                o2=subtype,
                tool_type=tool_type,
                tool_diameter_mm=tool_diameter,
                x=hole.x,
                y=hole.y,
                z_top=hole.top_z,
                z_bottom=hole.bottom_z,
                feature="hole",
            )
        )
    return operations


def plan_hole(hole: Hole, stock_bottom_z: float) -> list[PlannedOperation]:
    """Classify one hole into an operation chain (F-033).

    This is the **rule-based fallback**, used when no trained model is present.
    It is kept because it makes the pipeline runnable from a clean checkout, and
    because it is the baseline the classifier had to beat: 0.391 chain accuracy
    against the model's 0.948 on held-out parts.
    """
    operations: list[PlannedOperation] = []
    diameter = hole.diameter_mm
    aspect = hole.aspect_ratio()
    through = hole.depth_type(stock_bottom_z) == "through"

    def add(o2: str, tool_type: str, tool_diameter: float) -> None:
        operations.append(
            PlannedOperation(
                o1=infer_main_label(o2),
                o2=o2,
                tool_type=tool_type,
                tool_diameter_mm=tool_diameter,
                x=hole.x,
                y=hole.y,
                z_top=hole.top_z,
                z_bottom=hole.bottom_z,
                feature="hole",
            )
        )

    mid_band = (
        HOLE_MILLING_RANGE[0] <= diameter <= HOLE_MILLING_RANGE[1]
        and aspect <= HOLE_MILLING_MAX_ASPECT
    )
    large_bore = diameter >= LARGE_BORE_MIN_DIAMETER

    if mid_band or large_bore:
        # F-033 splits milled holes into two distinct chains, and diameter picks
        # between them:
        #   `HOLE_MILLING` alone            90 holes (8.0%)  -- the large bores
        #   `SPOT -> DRILL -> HOLE_MILLING` 50 holes (4.5%)  -- the mid band
        # A mid-band bore is small enough to start as a drilled hole and then be
        # opened out; a large bore is milled from solid
        # (`MILL_THROUGH_HOLE_FROM_SOLID_MATERIAL`). Emitting milling alone for
        # both cost two operations on every mid-band hole.
        # Applying the SPOT -> DRILL prefix to *every* mid-band bore was tried and
        # measured worse: only 50 of the 140 non-boring milled holes take it (36%),
        # so it over-generates on the rest. Easy rose 13.67 -> 14.00 but medium
        # fell 13.33 -> 12.08 and the length ratio dropped 0.8707 -> 0.8557.
        # Nothing in the recognised geometry separates the two groups, so the
        # majority chain is emitted unprefixed -- see Q-013.
        add("HOLE_MILLING", "end_mill", max(6.0, round(diameter * 0.6, 1)))
        # Reaming finishes only the mid-band bores; large ones are left as milled.
        if mid_band and diameter >= BORING_MIN_DIAMETER:
            add("BORING_REAMING", "boring_tool", round(diameter, 1))
        return operations

    if diameter <= SPOT_DRILL_MAX_DIAMETER:
        add("SPOT_DRILLING", "spot_drill", SPOT_DRILL_DIAMETER)

    pecked = (
        through
        and aspect >= DEEP_HOLE_MIN_ASPECT
        and diameter >= DEEP_HOLE_MIN_DIAMETER
    )

    # A pilot pass where the evidence supports it. The common case is one pass
    # straight to size (63% of holes -- see PILOT_MIN_DIAMETER), *but* a pecked
    # hole always gets one: the F-033 chains that contain DEEP_HOLE_DRILLING are
    # `SPOT -> DRILL -> DEEP -> DRILL` (12.2% of holes) and
    # `SPOT -> DRILL -> DEEP -> DRILL -> DRILL` (7.5%), which bracket the pecking
    # pass with drilling on both sides. Emitting only the trailing one
    # under-generated DRILLING by 0.61 operations per part.
    if pecked or diameter >= PILOT_MIN_DIAMETER:
        pilot = _drill_size_for(max(diameter * 0.55, 5.0))
        add("DRILLING", "twist_drill", pilot)

    if pecked:
        add("DEEP_HOLE_DRILLING", "twist_drill", _drill_size_for(diameter))

    add("DRILLING", "twist_drill", _drill_size_for(diameter))

    # The 5-operation chain adds a further finishing pass on the larger bores.
    if diameter >= EXTRA_PASS_MIN_DIAMETER or (pecked and diameter >= PILOT_MIN_DIAMETER):
        add("DRILLING", "twist_drill", _drill_size_for(diameter))

    return operations


def plan_part(part_id: str, features: PartFeatures) -> Plan:
    """Predict a full plan from recognised features.

    Operations are generated per feature, then reordered into contiguous
    tool blocks (F-027). Block order follows the dominant corpus pattern:
    chamfers, then pockets, then holes -- which held for 54% of parts as a
    standalone rule (F-027) and is the best single ordering available until
    precedence constraints are modelled.
    """
    chamfer_ops: list[PlannedOperation] = []
    pocket_ops: list[PlannedOperation] = []
    hole_ops: list[PlannedOperation] = []

    # Chamfers: one AREA_MILL pass each, always the same 20 mm chamfer mill.
    # The endpoints matter: without them the emitted path collapsed to the
    # origin and swept nothing on 21.9% of all operations.
    for index, chamfer in enumerate(features.chamfers):
        start, end = chamfer.path_endpoints()
        chamfer_ops.append(
            PlannedOperation(
                o1="mill_contour",
                o2="AREA_MILL",
                tool_type="chamfer_mill",
                tool_diameter_mm=CHAMFER_MILL_DIAMETER,
                x=start[0],
                y=start[1],
                z_top=chamfer.z_high,
                z_bottom=chamfer.z_low,
                feature="chamfer",
                end_x=end[0],
                end_y=end[1],
            )
        )

    # Pocket floors: normally one FLOOR_WALL pass each. A pocket that is wide
    # relative to its corner radius cannot be cleared by the tool its corners
    # admit (diameter <= 2r), so NX splits it into a roughing pass plus a
    # smaller finishing one -- pockets needing an extra operation measure a
    # size/2r of 4.58 against 3.91 for those that do not (F-041).
    # Shallowest floor first. Pocket operations were previously emitted in
    # face-discovery order, which is arbitrary -- and because the medium tier
    # compares the IPW at each index, an arbitrary order makes the intermediate
    # states wrong even when the final part is right. That shows up as pockets
    # carrying *both* overcut and undercut (0.0123 / 0.0091), which a pure
    # geometry error would not.
    for floor in sorted(features.pocket_floors, key=lambda f: f.z):
        smaller = min(floor.length_mm, floor.width_mm)
        diameter = 20.0 if smaller > 60.0 else 12.0 if smaller > 30.0 else 6.0
        # One pass per floor. Splitting on the reach ratio was implemented and
        # measured: it fixed the *marginal* count (FLOOR_WALL net -0.515 ->
        # -0.015) while making per-part accuracy worse (69 -> 86 parts wrong,
        # length ratio 0.8707 -> 0.8649). Since F-037 scores each part
        # independently, a weak signal that matches the aggregate is a net loss.
        for _ in range(1):
            pocket_ops.append(
                PlannedOperation(
                    o1="mill_planar",
                    o2="FLOOR_WALL",
                    tool_type="end_mill",
                    tool_diameter_mm=diameter,
                    x=(floor.x_min + floor.x_max) / 2.0,
                    y=(floor.y_min + floor.y_max) / 2.0,
                    z_top=features.stock_high[2],
                    z_bottom=floor.z,
                    feature="pocket",
                )
            )

    # Holes: the learned chain classifier where a model is available, the rules
    # otherwise. One batched call per part rather than one per hole.
    chains = hole_chain.predict_chains(features.holes, features)
    for index, hole in enumerate(features.holes):
        chain = chains[index] if chains else None
        if chain:
            hole_ops.extend(plan_hole_from_chain(hole, chain))
        else:
            hole_ops.extend(plan_hole(hole, features.stock_low[2]))

    # Block order is predicted, not fixed. The old fixed chamfer -> pocket -> hole
    # order was correct on only 26.5% of parts; the modal order is actually
    # hole -> chamfer -> pocket (34.1%), and the order is 0.896-predictable from
    # part geometry (F-052). Misordered blocks zero the slot in the medium,
    # tools *and* tool-path tiers, not just Levenshtein.
    grouped = {
        block_order.CHAMFER: _group_by_tool(chamfer_ops),
        block_order.POCKET: _group_by_tool(pocket_ops),
        block_order.HOLE: _group_by_tool(hole_ops),
    }
    ordered: list[PlannedOperation] = []
    for family in block_order.predict_order(features):
        ordered.extend(grouped.pop(family, []))
    for remaining in grouped.values():  # nothing may be dropped
        ordered.extend(remaining)
    return Plan(part_id=part_id, operations=ordered)


# How same-tool blocks are ordered inside a feature family. The medium tier
# compares the workpiece at every index, so this decides the intermediate states
# even when the finished part is right. Measured: the final part reaches IoU
# 0.9965 with 67.5% of parts above the top band threshold, while the mean across
# indices is only 0.9909 with 31.4% above it. That gap is entirely sequencing.
TOOL_BLOCK_ORDER = "first_use"


def _group_by_tool(operations: list[PlannedOperation]) -> list[PlannedOperation]:
    """Batch operations into contiguous same-tool blocks (F-027).

    Order within a block is stable. Blocks themselves are ordered by
    :data:`TOOL_BLOCK_ORDER`; ``"large_first"`` follows the usual roughing
    convention of removing bulk with the biggest cutter before moving to smaller
    ones, and ``"first_use"`` keeps the original insertion order.
    """
    blocks: dict[tuple[str, float], list[PlannedOperation]] = {}
    for operation in operations:
        blocks.setdefault(operation.tool_key, []).append(operation)

    keys = list(blocks)
    if TOOL_BLOCK_ORDER == "large_first":
        keys.sort(key=lambda key: -key[1])
    elif TOOL_BLOCK_ORDER == "small_first":
        keys.sort(key=lambda key: key[1])

    ordered: list[PlannedOperation] = []
    for key in keys:
        ordered.extend(blocks[key])
    return ordered
