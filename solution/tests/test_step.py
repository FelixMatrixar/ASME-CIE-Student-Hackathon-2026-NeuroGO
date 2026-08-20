"""Tests for the STEP reader and BRep feature recognition."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from machineplan.features import extract_features
from machineplan.parsing.step import StepParseError, parse_step

ARCHIVE = Path(__file__).resolve().parents[1] / "data" / "MachinePlan-10K.zip"

# A minimal but structurally faithful STEP fragment: one cylindrical face whose
# boundary carries a CLOSED circular edge (#41 uses vertex #30 at both ends),
# which is what marks a hole rather than a corner blend.
HOLE_STEP = """
ISO-10303-21;
HEADER;
ENDSEC;
DATA;
#10=CARTESIAN_POINT('',(50.,60.,0.));
#11=DIRECTION('',(0.,0.,1.));
#12=DIRECTION('',(1.,0.,0.));
#13=AXIS2_PLACEMENT_3D('',#10,#11,#12);
#14=CYLINDRICAL_SURFACE('',#13,5.);
#20=CARTESIAN_POINT('',(55.,60.,20.));
#21=CARTESIAN_POINT('',(55.,60.,0.));
#30=VERTEX_POINT('',#20);
#31=VERTEX_POINT('',#21);
#40=CIRCLE('',#13,5.);
#41=EDGE_CURVE('',#30,#30,#40,.T.);
#42=EDGE_CURVE('',#31,#31,#40,.T.);
#50=ORIENTED_EDGE('',*,*,#41,.T.);
#51=ORIENTED_EDGE('',*,*,#42,.T.);
#60=EDGE_LOOP('',(#50,#51));
#61=FACE_OUTER_BOUND('',#60,.T.);
#70=ADVANCED_FACE('',(#61),#14,.T.);
ENDSEC;
END-ISO-10303-21;
"""

# Same shape, but the arc edge has two DISTINCT vertices -- a corner blend.
BLEND_STEP = HOLE_STEP.replace(
    "#41=EDGE_CURVE('',#30,#30,#40,.T.);", "#41=EDGE_CURVE('',#30,#31,#40,.T.);"
).replace(
    "#42=EDGE_CURVE('',#31,#31,#40,.T.);", "#42=EDGE_CURVE('',#31,#30,#40,.T.);"
)


def test_parses_instances() -> None:
    model = parse_step(HOLE_STEP)
    assert len(model) == 17  # every #id in the fixture
    assert len(model.faces) == 1


def test_reads_cylindrical_surface_geometry() -> None:
    face = parse_step(HOLE_STEP).faces[0]
    assert face.is_cylindrical
    assert face.radius == pytest.approx(5.0)
    assert face.is_vertical_axis
    assert face.placement is not None
    assert face.placement.origin == pytest.approx((50.0, 60.0, 0.0))


def test_closed_circular_edge_marks_a_hole() -> None:
    """The discriminator: closed edge (same vertex twice) means a full cylinder."""
    assert parse_step(HOLE_STEP).faces[0].closed_circles > 0
    assert parse_step(BLEND_STEP).faces[0].closed_circles == 0


def test_hole_and_blend_are_classified_apart() -> None:
    """Regression: both are cylinders bounded by CIRCLE curves.

    Testing the curve type alone classified fillets as holes and over-detected
    by 2.6x (6.16 holes per part against a published 2.33).
    """
    assert len(extract_features(parse_step(HOLE_STEP)).holes) == 1
    assert len(extract_features(parse_step(HOLE_STEP)).blends) == 0
    assert len(extract_features(parse_step(BLEND_STEP)).holes) == 0
    assert len(extract_features(parse_step(BLEND_STEP)).blends) == 1


def test_hole_geometry_is_recovered() -> None:
    hole = extract_features(parse_step(HOLE_STEP)).holes[0]
    assert hole.diameter_mm == pytest.approx(10.0)
    assert (hole.x, hole.y) == pytest.approx((50.0, 60.0))
    assert hole.depth_mm == pytest.approx(20.0)
    assert hole.aspect_ratio() == pytest.approx(2.0)


def test_bounds_use_vertex_points_only() -> None:
    """Placement origins are construction geometry and must not set the bounds.

    Including every CARTESIAN_POINT inflated the measured block height from
    ~100 mm to ~136 mm against the paper's published mean.
    """
    low, high = parse_step(HOLE_STEP).bounds
    assert low[2] == pytest.approx(0.0)
    assert high[2] == pytest.approx(20.0)
    # #10 sits on the axis at (50,60,0) and is not a vertex; the vertices are at x=55.
    assert low[0] == pytest.approx(55.0)


def test_argument_splitting_handles_nested_tuples() -> None:
    """Commas inside a coordinate tuple must not split the argument list."""
    model = parse_step(HOLE_STEP)
    assert model.point(10) == pytest.approx((50.0, 60.0, 0.0))


def test_empty_input_raises() -> None:
    with pytest.raises(StepParseError):
        parse_step("ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\n")


def test_surface_census_reports_types() -> None:
    assert parse_step(HOLE_STEP).surface_type_census() == {"CYLINDRICAL_SURFACE": 1}


@pytest.mark.skipif(not ARCHIVE.exists(), reason="dataset archive not present")
def test_real_part_matches_published_statistics() -> None:
    """Sanity-check a handful of real parts against the paper's ranges."""
    from machineplan.parsing.dataset import MachinePlanDataset

    with MachinePlanDataset(ARCHIVE) as dataset:
        for part in list(dataset)[:15]:
            assert part.brep
            features = extract_features(parse_step(dataset.read_text(part.brep)))
            # Blocks are 200-500 mm in L/W and 50-150 mm in H.
            assert 200.0 <= features.stock_length <= 500.0, part.part_id
            assert 200.0 <= features.stock_width <= 500.0, part.part_id
            assert 50.0 <= features.stock_height <= 150.0, part.part_id
            # Holes span 5-50 mm and a part carries at most 6.
            assert len(features.holes) <= 6, part.part_id
            for hole in features.holes:
                assert 5.0 <= hole.diameter_mm <= 50.0, part.part_id
                assert hole.depth_mm > 0
