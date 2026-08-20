"""Tests for tool solids and swept volumes.

Wherever possible these check against a *closed-form* answer rather than a
golden value, because the swept volume feeds an IoU that must resolve to 0.999.
A test that only pins current behaviour would let a systematic error through.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from machineplan.geometry.sweep import segment_sweep, sweep_moves, material_removed
from machineplan.geometry.tooling import Tool, UnknownToolError, tool_from_library_name
from machineplan.parsing.ptp import Move, parse_ptp

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PTP = REPO_ROOT / "sample_submission" / "hard_tool_path" / "featured_part_00001_operation_01.ptp"

# Revolving a profile into 64 sections inscribes the true circle, so areas come
# out slightly under the analytic value. 64 sections gives ~0.16% deficit.
SECTION_TOLERANCE = 0.005


# --------------------------------------------------------------------- tooling

def test_end_mill_is_a_cylinder() -> None:
    tool = Tool("end_mill", diameter_mm=10.0, flute_length_mm=20.0)
    expected = math.pi * 5.0**2 * 20.0
    assert tool.solid().volume == pytest.approx(expected, rel=SECTION_TOLERANCE)
    assert tool.solid().is_watertight


def test_end_mill_has_no_tapered_tip() -> None:
    assert Tool("end_mill", 10.0).tip_height_mm == pytest.approx(0.0)


def test_twist_drill_point_height_follows_the_included_angle() -> None:
    # A 118 degree point on a 10 mm drill: h = r / tan(59 deg).
    tool = Tool("twist_drill", diameter_mm=10.0, flute_length_mm=50.0)
    expected = 5.0 / math.tan(math.radians(59.0))
    assert tool.tip_height_mm == pytest.approx(expected, rel=1e-6)


def test_drill_volume_is_cylinder_minus_the_missing_cone() -> None:
    tool = Tool("twist_drill", diameter_mm=10.0, flute_length_mm=50.0)
    radius, tip = 5.0, tool.tip_height_mm
    # Body from 0..50 minus the material absent below the cone.
    expected = math.pi * radius**2 * 50.0 - (math.pi * radius**2 * tip / 3.0) * 2
    # cone occupies 1/3 of its bounding cylinder, so 2/3 is absent
    assert tool.solid().volume == pytest.approx(expected, rel=SECTION_TOLERANCE)


def test_chamfer_mill_rises_at_45_degrees() -> None:
    # 20 mm body, 3 mm tip, 45 deg flank -> rise = (10 - 1.5) / tan(45) = 8.5 mm.
    tool = Tool("chamfer_mill", diameter_mm=20.0, flute_length_mm=30.0)
    assert tool.tip_height_mm == pytest.approx(8.5, rel=1e-6)


def test_all_tools_are_convex() -> None:
    """Convexity is what makes segment_sweep exact -- assert it explicitly."""
    for tool_type in (
        "end_mill", "chamfer_mill", "twist_drill", "spot_drill",
        "insert_drill", "gun_drill", "spade_drill", "boring_tool",
    ):
        solid = Tool(tool_type, diameter_mm=12.0, flute_length_mm=40.0).solid()
        assert solid.is_watertight, tool_type
        # A convex solid equals its own convex hull, up to meshing noise.
        assert solid.volume == pytest.approx(solid.convex_hull.volume, rel=1e-6), tool_type


def test_unknown_tool_type_raises() -> None:
    with pytest.raises(UnknownToolError):
        Tool("laser_cutter", 10.0).solid()


def test_invalid_diameter_raises() -> None:
    with pytest.raises(ValueError):
        Tool("end_mill", 0.0)
    with pytest.raises(ValueError):
        Tool("end_mill", float("inf"))


@pytest.mark.parametrize(
    "name, tool_type, diameter",
    [
        ("Chamfer Mill 20 x 3 x 45 deg.", "chamfer_mill", 20.0),
        # 142 is the point angle, not the diameter: the explicit "12 mm" wins.
        ("NC Spot Drill, 142 deg, 12 mm, Carbide, Uncoated", "spot_drill", 12.0),
        ("ENDMILL 16 mm (2P460-1600-NA 1630)", "end_mill", 16.0),
        ("End Mill 20 mm", "end_mill", 20.0),
        ("Carbide Drill 9.4 mm (860.1-0940-075A1-MM 2214)", "twist_drill", 9.4),
    ],
)
def test_library_name_parsing(name: str, tool_type: str, diameter: float) -> None:
    tool = tool_from_library_name(name)
    assert tool is not None
    assert tool.tool_type == tool_type
    assert tool.diameter_mm == pytest.approx(diameter)


def test_library_name_parsing_returns_none_when_unsure() -> None:
    assert tool_from_library_name("Mystery Widget") is None


# ----------------------------------------------------------------- swept volume

def test_linear_sweep_matches_the_closed_form() -> None:
    """A cylinder dragged horizontally sweeps a slab plus a full cylinder.

    Volume = pi r^2 h  (the tool itself, split across the two rounded ends)
           + 2 r * L * h  (the rectangular slab between them)
    """
    radius, height, length = 5.0, 20.0, 100.0
    tool = Tool("end_mill", diameter_mm=2 * radius, flute_length_mm=height)
    swept = segment_sweep(tool.solid(), (0.0, 0.0, 0.0), (length, 0.0, 0.0))
    expected = math.pi * radius**2 * height + 2 * radius * length * height
    assert swept.volume == pytest.approx(expected, rel=SECTION_TOLERANCE)


def test_vertical_plunge_sweeps_an_extended_cylinder() -> None:
    radius, height, depth = 4.0, 30.0, 12.0
    tool = Tool("end_mill", diameter_mm=2 * radius, flute_length_mm=height)
    swept = segment_sweep(tool.solid(), (0.0, 0.0, 0.0), (0.0, 0.0, -depth))
    expected = math.pi * radius**2 * (height + depth)
    assert swept.volume == pytest.approx(expected, rel=SECTION_TOLERANCE)


def test_zero_length_move_yields_the_bare_tool() -> None:
    tool = Tool("end_mill", diameter_mm=10.0, flute_length_mm=20.0)
    swept = segment_sweep(tool.solid(), (1.0, 2.0, 3.0), (1.0, 2.0, 3.0))
    assert swept.volume == pytest.approx(tool.solid().volume, rel=1e-9)


def test_sweep_is_translation_invariant() -> None:
    tool = Tool("end_mill", diameter_mm=8.0, flute_length_mm=15.0)
    near = segment_sweep(tool.solid(), (0.0, 0.0, 0.0), (10.0, 0.0, 0.0))
    far = segment_sweep(tool.solid(), (500.0, 300.0, 100.0), (510.0, 300.0, 100.0))
    assert near.volume == pytest.approx(far.volume, rel=1e-9)


def test_overlapping_moves_are_not_double_counted() -> None:
    """Retracing the same segment must not inflate the swept volume."""
    tool = Tool("end_mill", diameter_mm=10.0, flute_length_mm=20.0)
    there = Move("linear", (0.0, 0.0, 0.0), (50.0, 0.0, 0.0))
    back = Move("linear", (50.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    once = sweep_moves([there], tool)
    twice = sweep_moves([there, back], tool)
    assert twice.volume == pytest.approx(once.volume, rel=1e-6)


def test_union_of_disjoint_moves_adds_up() -> None:
    tool = Tool("end_mill", diameter_mm=6.0, flute_length_mm=10.0)
    first = Move("linear", (0.0, 0.0, 0.0), (20.0, 0.0, 0.0))
    second = Move("linear", (0.0, 500.0, 0.0), (20.0, 500.0, 0.0))
    single = sweep_moves([first], tool).volume
    both = sweep_moves([first, second], tool).volume
    assert both == pytest.approx(2 * single, rel=1e-6)


def test_rapids_are_excluded_by_default() -> None:
    tool = Tool("end_mill", diameter_mm=10.0, flute_length_mm=20.0)
    cutting = Move("linear", (0.0, 0.0, 0.0), (20.0, 0.0, 0.0))
    rapid = Move("rapid", (20.0, 0.0, 0.0), (20.0, 400.0, 0.0))
    assert sweep_moves([cutting, rapid], tool).volume == pytest.approx(
        sweep_moves([cutting], tool).volume, rel=1e-9
    )
    assert sweep_moves([cutting, rapid], tool, include_rapids=True).volume > (
        sweep_moves([cutting], tool).volume
    )


def test_arc_sweep_is_bounded_by_its_annulus() -> None:
    """A quarter arc must sweep between the inscribed and circumscribed bounds."""
    radius, tool_radius, height = 50.0, 5.0, 10.0
    tool = Tool("end_mill", diameter_mm=2 * tool_radius, flute_length_mm=height)
    arc = Move("arc_ccw", (radius, 0.0, 0.0), (0.0, radius, 0.0), center=(0.0, 0.0, 0.0))
    swept = sweep_moves([arc], tool, arc_step_mm=0.25)
    annulus = math.pi * ((radius + tool_radius) ** 2 - (radius - tool_radius) ** 2) / 4 * height
    ends = math.pi * tool_radius**2 * height
    assert swept.volume == pytest.approx(annulus + ends, rel=0.02)


def test_material_removed_clips_the_sweep_to_the_stock() -> None:
    """Only the part of a sweep inside the stock counts as removed material."""
    stock = trimesh.creation.box((100, 100, 100))
    tool = Tool("end_mill", diameter_mm=10.0, flute_length_mm=200.0)
    # Sweep well beyond the stock in X; the clipped result must fit inside it.
    swept = sweep_moves([Move("linear", (-500.0, 0.0, 0.0), (500.0, 0.0, 0.0))], tool)
    clipped = material_removed(stock, swept.solid)
    assert clipped.volume < swept.volume
    assert clipped.volume <= stock.volume + 1e-6


# ------------------------------------------------------------------ real path

@pytest.mark.skipif(not SAMPLE_PTP.exists(), reason="sample ptp not present")
def test_real_chamfer_path_sweeps_a_plausible_volume() -> None:
    """End-to-end: parse the real AREA_MILL path and sweep its chamfer tool.

    Per the kickoff slides this operation uses a 20 mm chamfer mill. The result
    must be a positive, watertight solid confined to the path's own bounds grown
    by the tool radius -- a sweep escaping that box means the hull math is wrong.
    """
    path = parse_ptp(SAMPLE_PTP)
    tool = Tool("chamfer_mill", diameter_mm=20.0, flute_length_mm=30.0)
    swept = sweep_moves(path.cutting_moves, tool)

    assert swept.volume > 0
    assert swept.solid.is_watertight

    low, high = path.bounds
    margin = tool.radius_mm + 1e-3
    bounds = swept.solid.bounds
    for axis in range(3):
        assert bounds[0][axis] >= low[axis] - margin - 1e-6
        assert bounds[1][axis] <= high[axis] + margin + tool.effective_flute_length_mm + 1e-6
