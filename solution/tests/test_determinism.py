"""The pipeline must produce identical output for identical input.

Determinism is a claim we make in the write-up, so it is tested rather than
asserted. It is not automatic: a pipeline can drift run to run through dictionary
iteration order, unseeded sampling, floating-point reduction order, or a model
that samples at inference.

Ours does not, and the two learned components do not change that. A gradient
boosted classifier is a fixed function once fitted: `random_state` decides which
trees get built during training and has no effect on `predict` afterwards.

The check covers the whole chain, not just the plan: operation labels, tool
choices, every mesh volume and face count, and every line of emitted machine
code.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from machineplan.features import extract_features
from machineplan.generate import generate_part
from machineplan.parsing.step import parse_step
from machineplan.predict import plan_part

REPO = Path(__file__).resolve().parents[2]
TEST_DATA = REPO / "Test_Data"
ARCHIVE = Path(__file__).resolve().parents[1] / "data" / "MachinePlan-10K.zip"


def fingerprint(part_id: str, step_text: str) -> str:
    """A hash over every value that reaches the submission."""
    features = extract_features(parse_step(step_text))
    plan = plan_part(part_id, features)
    generated = generate_part(plan, features)

    digest = hashlib.sha256()
    for operation in plan.operations:
        digest.update(
            f"{operation.o1}|{operation.o2}|{operation.tool_type}|"
            f"{operation.tool_diameter_mm:.6f}".encode()
        )
    for mesh in generated.ipws:
        digest.update(f"{mesh.volume:.9f}|{len(mesh.faces)}".encode())
    for text in generated.tool_paths:
        digest.update(text.encode())
    return digest.hexdigest()


def _sample_parts(limit: int = 3) -> list[tuple[str, str]]:
    """Prefer the released test set; fall back to the corpus archive."""
    if TEST_DATA.is_dir():
        parts: list[tuple[str, str]] = []
        for folder in sorted(p for p in TEST_DATA.iterdir() if p.is_dir())[:limit]:
            step = next(
                (c for c in sorted(folder.iterdir())
                 if c.suffix.lower() in (".stp", ".step")), None
            )
            if step is not None:
                parts.append((folder.name, step.read_text(encoding="utf-8", errors="replace")))
        if parts:
            return parts

    if ARCHIVE.exists():
        from machineplan.parsing.dataset import MachinePlanDataset

        with MachinePlanDataset(ARCHIVE) as dataset:
            return [
                (part.part_id, dataset.read_text(part.brep))
                for part in list(dataset)[:limit] if part.brep
            ]
    return []


PARTS = _sample_parts()


@pytest.mark.skipif(not PARTS, reason="neither Test_Data nor the corpus archive is present")
def test_pipeline_is_deterministic() -> None:
    """Running the same part twice must produce byte-identical results."""
    for part_id, step_text in PARTS:
        first = fingerprint(part_id, step_text)
        second = fingerprint(part_id, step_text)
        assert first == second, f"{part_id} differed between runs"


@pytest.mark.skipif(not PARTS, reason="no sample parts available")
def test_distinct_parts_differ() -> None:
    """Guard against a fingerprint that is constant and would pass vacuously."""
    if len(PARTS) < 2:
        pytest.skip("need at least two parts")
    digests = {fingerprint(part_id, text) for part_id, text in PARTS}
    assert len(digests) == len(PARTS), "different parts produced the same fingerprint"


@pytest.mark.skipif(not PARTS, reason="no sample parts available")
def test_feature_recognition_is_order_stable() -> None:
    """Recognised features must come back in a stable order, not just a stable set.

    Dictionary and set iteration are the usual sources of run-to-run drift, and
    an unstable feature order would reorder operations without changing which
    ones occur, which the medium tier scores per index.
    """
    part_id, text = PARTS[0]
    first = extract_features(parse_step(text))
    second = extract_features(parse_step(text))

    assert [h.diameter_mm for h in first.holes] == [h.diameter_mm for h in second.holes]
    assert [f.z for f in first.pocket_floors] == [f.z for f in second.pocket_floors]
    assert [c.z_low for c in first.chamfers] == [c.z_low for c in second.chamfers]
