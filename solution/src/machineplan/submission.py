"""Write submission artifacts in the exact formats ``validate_submission.py`` accepts.

Four deliverables, each with its own naming rule:

    easy/<part_id>_sequence.json
    medium/<part_id>_operation_NN.stl
    hard/<part_id>_tools.json
    hard_tool_path/<part_id>_operation_NN.ptp

Two details the validator enforces and that are easy to get wrong:
``operation_number`` runs 1..N with no gaps, and ``summary.number_of_operations``
must equal the array length. Note also that ``operations.json`` in the *dataset*
numbers from 0 (F-017) while submissions number from 1 -- an off-by-one waiting
to happen.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import trimesh

from machineplan.generate import GeneratedPart
from machineplan.predict import Plan


@dataclass(frozen=True, slots=True)
class SubmissionPaths:
    """Where each tier's artifacts were written."""

    easy: Path
    medium: Path
    hard: Path
    hard_tool_path: Path


def write_easy(plan: Plan, directory: Path) -> Path:
    """Write the operation-sequence JSON."""
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "part_id": plan.part_id,
        "summary": {"number_of_operations": len(plan.operations)},
        "operations": [
            {"operation_number": index, "o1": operation.o1, "o2": operation.o2}
            for index, operation in enumerate(plan.operations, start=1)
        ],
    }
    path = directory / f"{plan.part_id}_sequence.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def write_hard_tools(plan: Plan, directory: Path) -> Path:
    """Write the tool type and diameter JSON."""
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "part_id": plan.part_id,
        "summary": {"number_of_operations": len(plan.operations)},
        "operations": [
            {
                "operation_number": index,
                "tool_type": operation.tool_type,
                "tool_diameter_mm": round(float(operation.tool_diameter_mm), 4),
            }
            for index, operation in enumerate(plan.operations, start=1)
        ],
    }
    path = directory / f"{plan.part_id}_tools.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def write_medium(generated: GeneratedPart, directory: Path) -> list[Path]:
    """Write one binary STL per operation."""
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for index, mesh in enumerate(generated.ipws, start=1):
        path = directory / f"{generated.part_id}_operation_{index:02d}.stl"
        mesh.export(path, file_type="stl")
        written.append(path)
    return written


def write_tool_paths(generated: GeneratedPart, directory: Path) -> list[Path]:
    """Write one PTP per operation."""
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for index, text in enumerate(generated.tool_paths, start=1):
        path = directory / f"{generated.part_id}_operation_{index:02d}.ptp"
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def write_submission(generated: GeneratedPart, root: Path) -> SubmissionPaths:
    """Write all four deliverables for one part beneath ``root``."""
    paths = SubmissionPaths(
        easy=root / "easy",
        medium=root / "medium" / generated.part_id,
        hard=root / "hard",
        hard_tool_path=root / "hard_tool_path" / generated.part_id,
    )
    write_easy(generated.plan, paths.easy)
    write_hard_tools(generated.plan, paths.hard)
    write_medium(generated, paths.medium)
    write_tool_paths(generated, paths.hard_tool_path)
    return paths


def load_stl(path: Path) -> trimesh.Trimesh:
    """Read back a written STL, for round-trip checks."""
    return trimesh.load(path, file_type="stl")
