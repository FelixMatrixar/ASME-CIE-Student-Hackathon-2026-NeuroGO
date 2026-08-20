"""Tests for the local rubric reimplementation.

Run with:  .venv/Scripts/python -m pytest tests -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from machineplan.scoring.easy import f1_multiset, levenshtein, normalized_levenshtein, score_easy
from machineplan.scoring.geometry import compare_volumes, removed_volume
from machineplan.scoring.hard import ToolPrediction, score_tool_paths, score_tools
from machineplan.scoring.medium import score_medium
from machineplan.vocab import Operation, infer_main_label

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_MEDIUM = REPO_ROOT / "sample_submission" / "medium"


# --------------------------------------------------------------------------- easy

def test_levenshtein_basic() -> None:
    assert levenshtein("kitten", "sitting") == 3
    assert levenshtein([], []) == 0
    assert levenshtein("abc", "") == 3


def test_normalized_levenshtein_is_bounded() -> None:
    assert normalized_levenshtein([], []) == 0.0
    assert normalized_levenshtein("abc", "abc") == 0.0
    assert normalized_levenshtein("abc", "xyz") == 1.0


def test_f1_respects_multiset_counts() -> None:
    # Three drills predicted against three drills is perfect; predicting one is not.
    assert f1_multiset(["d", "d", "d"], ["d", "d", "d"]) == 1.0
    assert f1_multiset(["d"], ["d", "d", "d"]) == pytest.approx(0.5)
    assert f1_multiset([], []) == 1.0
    assert f1_multiset(["a"], ["b"]) == 0.0


def test_f1_ignores_order_but_levenshtein_does_not() -> None:
    forward = ["a", "b", "c"]
    shuffled = ["c", "b", "a"]
    assert f1_multiset(forward, shuffled) == 1.0
    assert normalized_levenshtein(forward, shuffled) > 0.0


def test_perfect_easy_prediction_scores_full_marks() -> None:
    sequence = [Operation("mill_contour", "AREA_MILL"), Operation("hole_making", "DRILLING")]
    score = score_easy(sequence, sequence)
    assert score.points == 20.0
    assert score.normalized_levenshtein == 0.0
    assert score.f1 == 1.0


def test_band_boundaries_favour_the_participant() -> None:
    # A normalized distance of exactly 0.1 sits in both printed bands; we award
    # the higher of the two.
    truth = list("abcdefghij")
    predicted = list("abcdefghiX")  # one substitution in ten -> exactly 0.1
    score = score_easy(predicted, truth)
    assert score.normalized_levenshtein == pytest.approx(0.1)
    assert score.levenshtein_points == 10.0


# --------------------------------------------------------------------------- vocab

def test_subtype_determines_main_label() -> None:
    assert infer_main_label("AREA_MILL") == "mill_contour"
    assert infer_main_label("FLOOR_WALL") == "mill_planar"
    assert infer_main_label("BORING_REAMING") == "hole_making"
    assert Operation("mill_contour", "AREA_MILL").is_consistent
    assert not Operation("mill_planar", "AREA_MILL").is_consistent


def test_other_is_accepted_by_validator_but_never_consistent() -> None:
    assert Operation("OTHER", "OTHER").is_consistent is False


# --------------------------------------------------------------------------- geometry

def test_identical_solids_have_unit_iou() -> None:
    box = trimesh.creation.box((10, 10, 10))
    comparison = compare_volumes(box, box.copy())
    assert comparison.iou == pytest.approx(1.0, abs=1e-9)
    assert comparison.overcut == pytest.approx(0.0, abs=1e-9)
    assert comparison.undercut == pytest.approx(0.0, abs=1e-9)


def test_disjoint_solids_have_zero_iou() -> None:
    a = trimesh.creation.box((10, 10, 10))
    b = trimesh.creation.box((10, 10, 10))
    b.apply_translation((100, 0, 0))
    assert compare_volumes(a, b).iou == 0.0


def test_half_overlap_iou_is_one_third() -> None:
    # Two unit cubes overlapping in half their volume: |A n B| = 0.5,
    # |A u B| = 1.5, so IoU = 1/3.
    a = trimesh.creation.box((1, 1, 1))
    b = trimesh.creation.box((1, 1, 1))
    b.apply_translation((0.5, 0, 0))
    assert compare_volumes(a, b).iou == pytest.approx(1 / 3, abs=1e-6)


def test_overcut_is_material_removed_that_should_not_have_been() -> None:
    """Prediction larger than reference -> we cut away too much: overcut."""
    truth = trimesh.creation.box((1, 1, 1))
    predicted = trimesh.creation.box((2, 1, 1))
    comparison = compare_volumes(predicted, truth)
    assert comparison.overcut == pytest.approx(1.0, abs=1e-6)
    assert comparison.undercut == pytest.approx(0.0, abs=1e-6)


def test_undercut_is_material_that_should_have_been_removed() -> None:
    """Prediction smaller than reference -> we left material behind: undercut."""
    truth = trimesh.creation.box((2, 1, 1))
    predicted = trimesh.creation.box((1, 1, 1))
    comparison = compare_volumes(predicted, truth)
    assert comparison.undercut == pytest.approx(0.5, abs=1e-6)
    assert comparison.overcut == pytest.approx(0.0, abs=1e-6)


def test_denoise_strips_tessellation_slivers() -> None:
    """A real lump plus a paper-thin sheet must reduce to the lump.

    Mirrors what consecutive IPW meshes actually produce: re-triangulation
    leaves 17-micron sheets alongside the material genuinely removed.
    """
    from machineplan.scoring.geometry import denoise_difference, largest_body

    lump = trimesh.creation.box((10, 10, 10))
    sliver = trimesh.creation.box((0.017, 90, 30))
    sliver.apply_translation((200, 0, 0))
    combined = trimesh.util.concatenate([lump, sliver])

    cleaned = denoise_difference(combined)
    assert cleaned.volume == pytest.approx(lump.volume, rel=1e-6)
    assert largest_body(combined).volume == pytest.approx(lump.volume, rel=1e-6)


def test_denoise_keeps_small_but_solid_features() -> None:
    """A genuinely small chunky feature is not noise and must survive."""
    from machineplan.scoring.geometry import denoise_difference

    big = trimesh.creation.box((50, 50, 50))
    small = trimesh.creation.box((2, 2, 2))
    small.apply_translation((200, 0, 0))
    combined = trimesh.util.concatenate([big, small])
    assert denoise_difference(combined).volume == pytest.approx(
        big.volume + small.volume, rel=1e-6
    )


def test_denoise_leaves_a_single_body_alone() -> None:
    from machineplan.scoring.geometry import denoise_difference

    box = trimesh.creation.box((10, 10, 10))
    assert denoise_difference(box).volume == pytest.approx(box.volume, rel=1e-12)


def test_as_solid_leaves_a_valid_mesh_untouched() -> None:
    """Repair must not damage a mesh that is already a solid.

    Regression test for a real bug: unconditional `nondegenerate_faces` culling
    deleted the sliver triangles that legitimately occur in thin wedge solids
    (a chamfer removal volume), turning a watertight solid into a broken one and
    silently corrupting IoU.
    """
    from machineplan.scoring.geometry import as_solid

    box = trimesh.creation.box((10, 10, 10))
    result = as_solid(box)
    assert result.is_volume
    assert len(result.faces) == len(box.faces)
    assert result.volume == pytest.approx(box.volume, rel=1e-12)


def test_as_solid_preserves_thin_slivers() -> None:
    """A long thin wedge -- the shape a chamfer operation removes -- must survive."""
    from machineplan.scoring.geometry import as_solid

    # 300 mm long, 8 mm across, tapering to an edge: full of sliver triangles.
    wedge = trimesh.Trimesh(
        vertices=[
            [0, 0, 0], [300, 0, 0], [0, 8, 0], [300, 8, 0], [0, 0, 8], [300, 0, 8],
        ],
        faces=[
            [0, 2, 1], [1, 2, 3], [0, 1, 4], [1, 5, 4],
            [0, 4, 2], [2, 4, 5], [2, 5, 3], [3, 5, 1], [4, 5, 2],
        ],
        process=False,
    )
    wedge = as_solid(wedge.convex_hull)
    before = wedge.volume
    assert as_solid(wedge).volume == pytest.approx(before, rel=1e-12)
    assert as_solid(wedge).is_volume


def test_as_solid_reorients_an_inverted_mesh() -> None:
    from machineplan.scoring.geometry import as_solid

    box = trimesh.creation.box((4, 4, 4))
    box.invert()
    assert as_solid(box).volume == pytest.approx(64.0, rel=1e-9)


def test_removed_volume_is_the_difference_of_consecutive_ipws() -> None:
    before = trimesh.creation.box((10, 10, 10))
    after = before.difference(trimesh.creation.box((2, 2, 20)))
    removed = removed_volume(before, after)
    assert removed.volume == pytest.approx(2 * 2 * 10, abs=1e-6)


# --------------------------------------------------------------------------- tiers

def test_medium_scores_perfect_prediction() -> None:
    meshes = [trimesh.creation.box((10, 10, 10)), trimesh.creation.box((8, 8, 8))]
    score = score_medium(meshes, [m.copy() for m in meshes])
    assert score.mean_iou == pytest.approx(1.0, abs=1e-9)
    assert score.points == 35.0


def test_medium_penalises_missing_operations() -> None:
    truth = [trimesh.creation.box((10, 10, 10)), trimesh.creation.box((8, 8, 8))]
    score = score_medium(truth[:1], truth)
    assert score.per_operation_iou[1] == 0.0
    assert score.mean_iou == pytest.approx(0.5)
    assert score.points == 0.0  # below the 0.90 cliff


def test_tool_type_mismatch_zeroes_the_operation() -> None:
    truth = [ToolPrediction("end_mill", 10.0)]
    exact = score_tools([ToolPrediction("end_mill", 10.0)], truth)
    assert exact.points == 20.0
    wrong_type = score_tools([ToolPrediction("twist_drill", 10.0)], truth)
    assert wrong_type.points == 0.0


def test_tool_diameter_error_degrades_gracefully() -> None:
    truth = [ToolPrediction("end_mill", 10.0)]
    # 6% relative error -> the 0.05-0.10 band (6 of 10 raw), rescaled to 20.
    close = score_tools([ToolPrediction("end_mill", 10.6)], truth)
    assert close.points == pytest.approx(6.0 / 10.0 * 20.0)
    assert close.type_accuracy == 1.0


def test_tool_path_perfect_sweep_scores_full_marks() -> None:
    removed = [trimesh.creation.box((5, 5, 5))]
    score = score_tool_paths([removed[0].copy()], removed)
    assert score.mean_iou == pytest.approx(1.0, abs=1e-9)
    assert score.points == pytest.approx(25.0)


def test_unsimulatable_path_scores_zero() -> None:
    score = score_tool_paths([None], [trimesh.creation.box((5, 5, 5))])
    assert score.points == 0.0
    assert score.mean_overcut == 1.0


# --------------------------------------------------------------------------- samples

@pytest.mark.skipif(not SAMPLE_MEDIUM.exists(), reason="sample submission not present")
def test_sample_ipw_meshes_are_loadable_solids() -> None:
    """The contest's own sample STLs must survive our repair path."""
    paths = sorted(SAMPLE_MEDIUM.glob("*.stl"))
    assert paths, "expected sample STL files"
    for path in paths:
        mesh = trimesh.load(path, file_type="stl")
        comparison = compare_volumes(mesh, mesh.copy())
        assert comparison.iou == pytest.approx(1.0, abs=1e-9), path.name
        assert comparison.predicted_volume > 0


@pytest.mark.skipif(not SAMPLE_MEDIUM.exists(), reason="sample submission not present")
def test_sample_ipw_volume_decreases_monotonically() -> None:
    """Machining is subtractive: each IPW must be no larger than the last.

    This is a sanity check on our own understanding of the data as much as on the
    samples -- if it fails, our reading of the file ordering is wrong.
    """
    paths = sorted(SAMPLE_MEDIUM.glob("*.stl"))
    volumes = [trimesh.load(p, file_type="stl").volume for p in paths]
    for earlier, later in zip(volumes, volumes[1:]):
        assert later <= earlier + 1e-6, f"volume grew: {volumes}"
