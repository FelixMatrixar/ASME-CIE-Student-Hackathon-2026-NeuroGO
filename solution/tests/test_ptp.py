"""Tests for the .ptp NC-code parser.

The modal state machine is the risky part: a block carrying only ``X0.621``
inherits its motion mode, Y, Z and feed from whatever came before. Most of these
tests exist to pin that behaviour down.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from machineplan.parsing.ptp import PtpParseError, discretize, parse_ptp

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PTP = REPO_ROOT / "sample_submission" / "hard_tool_path" / "featured_part_00001_operation_01.ptp"


# --------------------------------------------------------------------- modality

def test_motion_mode_is_modal() -> None:
    """G1 stated once must apply to every following coordinate-only block."""
    program = "\n".join(["N10 G90 G21", "N12 G1 X10 Y0 Z0 F250.", "N14 X20", "N16 X30"])
    path = parse_ptp(program)
    # N12 only seeds the start position -- see test_first_positioning_block_seeds.
    assert [move.kind for move in path.moves] == ["linear", "linear"]
    assert path.moves[0].start == (10.0, 0.0, 0.0)
    assert path.moves[-1].end == (30.0, 0.0, 0.0)


def test_first_positioning_block_seeds_rather_than_cuts() -> None:
    """The block that first establishes all three axes must emit no move.

    Machine position is unknown at program start. Treating the first coordinate
    block as a move from an assumed origin would fabricate a long cut straight
    through the stock and wreck any swept-volume computed from it.
    """
    path = parse_ptp("N10 G90 G1 X100 Y100 Z50 F250.\nN12 X110")
    assert len(path.moves) == 1
    assert path.moves[0].start == (100.0, 100.0, 50.0)


def test_axes_seeded_across_several_blocks() -> None:
    """Real programs set X/Y in one block and Z in the next before moving."""
    # Mirrors the sample: N16 sets X/Y, N18 sets Z, N20 is the first real move.
    path = parse_ptp("N16 G0 G90 X179.5 Y-1.5\nN18 G43 Z98.8 H0\nN20 Z81.1")
    assert len(path.moves) == 1
    assert path.moves[0].start == (179.5, -1.5, 98.8)
    assert path.moves[0].end == (179.5, -1.5, 81.1)


def test_unnamed_axes_persist() -> None:
    """A block naming only X keeps the previous Y and Z."""
    path = parse_ptp("N10 G90 G1 X0 Y5 Z-3 F100.\nN12 X10")
    move = path.moves[-1]
    assert move.end == (10.0, 5.0, -3.0)


def test_feed_is_modal_and_rapids_carry_none() -> None:
    path = parse_ptp("N10 G90 G1 X0 Y0 Z0 F250.\nN12 X10\nN14 G0 X20")
    linear = [m for m in path.moves if m.kind == "linear"]
    rapid = [m for m in path.moves if m.kind == "rapid"]
    assert all(move.feed == 250.0 for move in linear)
    assert all(move.feed is None for move in rapid)


def test_incremental_mode_is_relative() -> None:
    path = parse_ptp("N10 G90 G1 X10 Y10 Z0 F100.\nN12 G91 X5\nN14 X5")
    assert path.moves[-2].end == (15.0, 10.0, 0.0)
    assert path.moves[-1].end == (20.0, 10.0, 0.0)


def test_zero_length_moves_are_dropped() -> None:
    path = parse_ptp("N10 G90 G1 X10 Y0 Z0 F100.\nN12 X10\nN14 X20")
    assert all(move.length > 0 for move in path.moves)


# --------------------------------------------------------------------- comments

def test_operation_and_tool_are_read_from_the_comment() -> None:
    program = "(AREA_MILL , TOOL : UGT0205_001)\nN10 G90 G1 X0 Y0 Z0 F100.\nN12 X10"
    path = parse_ptp(program)
    assert path.operation == "AREA_MILL"
    assert path.tool_id == "UGT0205_001"


def test_header_fields_are_captured() -> None:
    program = "(PARTNAME        : FEATURED_PART_00001.PRT   )\nN10 G90 G1 X0 Y0 Z0 F1.\nN12 X1"
    assert parse_ptp(program).header["PARTNAME"] == "FEATURED_PART_00001.PRT"


def test_comments_do_not_leak_into_code() -> None:
    """An inline comment must not be mistaken for address words."""
    path = parse_ptp("N10 G90 G1 X0 Y0 Z0 F100.\nN12 (X999 Y999) X10")
    assert path.moves[-1].end == (10.0, 0.0, 0.0)


# --------------------------------------------------------------------- geometry

def test_units_and_planes_are_recorded() -> None:
    assert parse_ptp("N10 G21 G1 X0 Y0 Z0 F1.\nN12 X1").metric is True
    assert parse_ptp("N10 G20 G1 X0 Y0 Z0 F1.\nN12 X1").metric is False


def test_planar_and_vertical_classification() -> None:
    path = parse_ptp("N10 G90 G1 X0 Y0 Z0 F100.\nN12 X10\nN14 Z-5")
    horizontal, plunge = path.moves[-2], path.moves[-1]
    assert horizontal.is_planar and not horizontal.is_vertical
    assert plunge.is_vertical and not plunge.is_planar


def test_arc_expands_into_chords() -> None:
    # Full-ish quarter arc from (10,0) to (0,10) about the origin.
    path = parse_ptp("N10 G90 G1 X10 Y0 Z0 F100.\nN12 G3 X0 Y10 I-10 J0")
    arc = path.moves[-1]
    assert arc.kind == "arc_ccw"
    assert arc.center == pytest.approx((0.0, 0.0, 0.0))
    points = discretize([arc], max_step=0.5)
    radii = [(x**2 + y**2) ** 0.5 for x, y, _ in points]
    assert all(radius == pytest.approx(10.0, abs=1e-6) for radius in radii)


def test_discretize_respects_max_step() -> None:
    path = parse_ptp("N10 G90 G1 X0 Y0 Z0 F100.\nN12 X100")
    points = discretize(path.cutting_moves, max_step=1.0)
    gaps = [
        ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 + (b[2] - a[2]) ** 2) ** 0.5
        for a, b in zip(points, points[1:])
    ]
    assert max(gaps) <= 1.0 + 1e-9


def test_dwell_is_not_a_move() -> None:
    """G4 X.084 is a 0.084 s pause, not a move to X=0.084.

    Regression test for a real bug: reading the dwell's X as a coordinate
    dragged a drill 25 mm sideways at full depth, carving a trench through solid
    material and producing 6.4x overcut on deep-hole drilling.
    """
    program = "\n".join([
        "N16 G0 G90 X25.3 Y174.8",
        "N18 G43 Z121.7 H0",
        "N24 G1 Z96.592 F125.",
        "N26 G4 X.084",
        "N28 Z3.5 F250.",
    ])
    path = parse_ptp(program)
    for move in path.moves:
        assert move.start[0] == pytest.approx(25.3), f"dwell moved X: {move}"
        assert move.end[0] == pytest.approx(25.3), f"dwell moved X: {move}"
    assert [m.end[2] for m in path.moves] == pytest.approx([96.592, 3.5])


def test_dwell_with_p_word_is_also_ignored() -> None:
    path = parse_ptp("N10 G90 G1 X0 Y0 Z0 F100.\nN12 G4 P500\nN14 X10")
    assert len(path.moves) == 1
    assert path.moves[0].end == (10.0, 0.0, 0.0)


def test_g73_peck_cycle_is_recognised_as_cutting() -> None:
    """G73 is a canned cycle, not an unknown code.

    Regression test: G73 was missing from the cycle set, so it fell through to
    the no-motion-mode fallback, became a non-cutting rapid, and the operation
    swept nothing. DRILLING is 33% of the dataset's operations.
    """
    program = "\n".join([
        "N16 G17 G0 G90 X127.7 Y39.3",
        "N18 G43 Z98.8 H1",
        "N20 G94 G73 G98 Z-3.211 F250. Q9.201 R90.8",
        "N22 G80",
    ])
    path = parse_ptp(program)
    cutting = path.cutting_moves
    assert cutting, "G73 must produce a cutting move"
    assert cutting[0].kind == "cycle"
    assert cutting[0].end[2] == pytest.approx(-3.211)
    # The cycle retracts to its R plane afterwards.
    assert any(m.kind == "rapid" and m.end[2] == pytest.approx(90.8) for m in path.moves)


@pytest.mark.parametrize("code", [73, 81, 82, 83, 85, 89])
def test_all_canned_cycles_cut(code: int) -> None:
    path = parse_ptp(f"N10 G90 G0 X0 Y0\nN12 Z50\nN14 G{code} Z-10 R5 F100.")
    assert any(move.is_cutting for move in path.moves), f"G{code} produced no cut"


def test_r_format_arc_resolves_a_centre() -> None:
    """Positive R selects the minor arc; the centre must satisfy both endpoints."""
    path = parse_ptp("N10 G90 G1 X10 Y0 Z0 F100.\nN12 G3 X0 Y10 R10")
    arc = path.moves[-1]
    assert arc.center is not None
    assert arc.center[0] == pytest.approx(0.0, abs=1e-9)
    assert arc.center[1] == pytest.approx(0.0, abs=1e-9)


def test_r_format_arc_negative_radius_selects_major_arc() -> None:
    path = parse_ptp("N10 G90 G1 X10 Y0 Z0 F100.\nN12 G3 X0 Y10 R-10")
    arc = path.moves[-1]
    assert arc.center is not None
    # The other valid centre for this chord and radius.
    assert arc.center[0] == pytest.approx(10.0, abs=1e-9)
    assert arc.center[1] == pytest.approx(10.0, abs=1e-9)


def test_r_format_arc_discretizes_onto_the_circle() -> None:
    path = parse_ptp("N10 G90 G1 X10 Y0 Z0 F100.\nN12 G3 X0 Y10 R10")
    points = discretize([path.moves[-1]], max_step=0.5)
    radii = [(x**2 + y**2) ** 0.5 for x, y, _ in points]
    assert all(radius == pytest.approx(10.0, abs=1e-6) for radius in radii)


def test_empty_program_raises() -> None:
    with pytest.raises(PtpParseError):
        parse_ptp("(only a comment)\n")


# --------------------------------------------------------------------- real file

@pytest.mark.skipif(not SAMPLE_PTP.exists(), reason="sample ptp not present")
def test_sample_ptp_parses() -> None:
    path = parse_ptp(SAMPLE_PTP)
    assert path.operation == "AREA_MILL"
    assert path.tool_id == "UGT0205_001"
    assert path.spindle_rpm == 1061.0
    assert path.metric is True
    assert path.header["PARTNAME"] == "FEATURED_PART_00001.PRT"
    assert len(path.moves) == 274
    assert len(path.cutting_moves) == 272


@pytest.mark.skipif(not SAMPLE_PTP.exists(), reason="sample ptp not present")
def test_sample_ptp_is_continuous() -> None:
    """Every move must start where the previous one ended.

    This is the real check on the modal state machine: a dropped or misread axis
    word shows up here as a discontinuity, even when nothing else looks wrong.
    """
    path = parse_ptp(SAMPLE_PTP)
    for earlier, later in zip(path.moves, path.moves[1:]):
        assert later.start == pytest.approx(earlier.end, abs=1e-9)


@pytest.mark.skipif(not SAMPLE_PTP.exists(), reason="sample ptp not present")
def test_sample_ptp_stays_inside_plausible_stock() -> None:
    path = parse_ptp(SAMPLE_PTP)
    low, high = path.bounds
    # Block sizes in this dataset run 200-500 mm in X/Y and 50-150 mm in Z.
    assert 0.0 <= low[0] and high[0] <= 500.0
    assert high[2] <= 150.0


@pytest.mark.skipif(not SAMPLE_PTP.exists(), reason="sample ptp not present")
def test_sample_chamfer_pass_is_mostly_ramping() -> None:
    """AREA_MILL chamfering is a 3D ramp, not a stack of constant-Z passes.

    This pins down F-011: a swept-volume engine that assumes 2.5-axis constant-Z
    levels would mis-model the great majority of this operation's motion.
    """
    path = parse_ptp(SAMPLE_PTP)
    cutting = path.cutting_moves
    ramping = [move for move in cutting if not move.is_planar and not move.is_vertical]
    assert len(ramping) / len(cutting) > 0.9
