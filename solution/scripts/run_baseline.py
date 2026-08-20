#!/usr/bin/env python3
"""End-to-end baseline: BRep in, submission out, scored locally.

Deliberately the *first* complete pipeline rather than a good one. Its job is to
turn "we have no submission" into "we have a number", prove the output formats
against the official validator, and show empirically where the points are.

    BRep -> features -> plan -> IPW meshes + NC code -> files -> score
"""

from __future__ import annotations

import argparse
import io
import pathlib
import statistics
import subprocess
import sys
import time

import trimesh

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from machineplan.features import extract_features  # noqa: E402
from machineplan.generate import generate_part  # noqa: E402
from machineplan.parsing.dataset import MachinePlanDataset  # noqa: E402
from machineplan.parsing.details import parse_details  # noqa: E402
from machineplan.parsing.step import parse_step  # noqa: E402
from machineplan.predict import plan_part  # noqa: E402
from machineplan.scoring.easy import score_easy  # noqa: E402
from machineplan.scoring.geometry import as_solid  # noqa: E402
from machineplan.geometry.sweep import SweepError, material_removed, sweep_moves  # noqa: E402
from machineplan.generate import stock_mesh, tool_for  # noqa: E402
from machineplan.parsing.ptp import parse_ptp  # noqa: E402
from machineplan.scoring.geometry import denoise_difference  # noqa: E402
from machineplan.scoring.hard import ToolPrediction, score_tool_paths, score_tools  # noqa: E402
from machineplan.scoring.medium import score_medium  # noqa: E402
from machineplan.submission import write_submission  # noqa: E402
from machineplan.vocab import Operation  # noqa: E402

SOLUTION = pathlib.Path(__file__).resolve().parents[1]
REPO = SOLUTION.parent
DEFAULT_ARCHIVE = SOLUTION / "data" / "MachinePlan-10K.zip"
DEFAULT_OUT = SOLUTION / "outputs" / "baseline"
HEAD_BYTES = 2600


def truth_for(dataset: MachinePlanDataset, part) -> tuple[list[Operation], list[ToolPrediction]]:
    """Ground-truth operation sequence and tools for a part."""
    sequence: list[Operation] = []
    tools: list[ToolPrediction] = []
    for index in sorted(part.operations):
        member = part.operations[index].details
        if not member:
            continue
        details = parse_details(dataset.read_text(member))
        sequence.append(Operation(details.o1, details.o2))
        tool = details.tool
        tool_type = tool.tool_type if tool else None
        diameter = tool.diameter_mm if tool else None
        tools.append(ToolPrediction(tool_type or "unknown", diameter or 0.0))
    return sequence, tools


def score_paths(generated, features, truth_ipws: list) -> float:
    """Score the generated NC code by sweeping it and comparing to real removal.

    Each emitted `.ptp` is parsed back and swept with the tool that operation
    declared, then clipped to the stock present at that point -- the same route
    the rubric takes. Round-tripping our own output also checks it is parseable,
    which a file that merely exists does not guarantee.
    """
    if not truth_ipws:
        return 0.0

    swept_volumes: list = []
    removed: list = []
    stock = stock_mesh(features)
    previous = stock

    for index, text in enumerate(generated.tool_paths):
        if index >= len(truth_ipws):
            break
        operation = generated.plan.operations[index]
        try:
            path = parse_ptp(text)
            swept = sweep_moves(path.cutting_moves, tool_for(operation))
            swept_volumes.append(material_removed(previous, swept.solid))
        except (SweepError, Exception):  # noqa: BLE001 - unscorable path scores zero
            swept_volumes.append(None)

        current = as_solid(truth_ipws[index])
        try:
            difference = trimesh.boolean.boolean_manifold([previous, current], "difference")
            removed.append(denoise_difference(difference) if difference is not None else None)
        except Exception:  # noqa: BLE001
            removed.append(None)
        previous = current

    usable = [(s, r) for s, r in zip(swept_volumes, removed) if r is not None]
    if not usable:
        return 0.0
    return score_tool_paths([s for s, _ in usable], [r for _, r in usable]).points


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=pathlib.Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument(
        "--offset", type=int, default=0,
        help="skip this many parts first. Use it to score parts the hole-chain "
             "classifier never trained on -- the dataset is built from the first "
             "2,500, so --offset 3000 is an honest held-out run.",
    )
    parser.add_argument("--skip-medium", action="store_true",
                        help="skip IPW scoring (the slow part)")
    parser.add_argument("--skip-paths", action="store_true",
                        help="skip tool-path sweeping (slower still)")
    arguments = parser.parse_args()

    easy_points: list[float] = []
    tool_points: list[float] = []
    medium_points: list[float] = []
    path_points: list[float] = []
    lengths: list[tuple[int, int]] = []
    failures = 0
    written_paths = None
    started = time.perf_counter()

    with MachinePlanDataset(arguments.archive) as dataset:
        parts = list(dataset)[arguments.offset : arguments.offset + arguments.limit]
        print(f"running baseline on {len(parts)} parts -> {arguments.out}\n")
        print(f"{'part':22}{'ops':>9}{'easy':>7}{'tools':>7}{'medium':>8}  detail")
        print("-" * 78)

        for part in parts:
            if not part.brep:
                continue
            try:
                features = extract_features(parse_step(dataset.read_text(part.brep)))
                plan = plan_part(part.part_id, features)
                generated = generate_part(plan, features)
                written_paths = write_submission(generated, arguments.out)
            except Exception as error:  # noqa: BLE001
                failures += 1
                print(f"{part.part_id:22}  FAILED {type(error).__name__}: {error}")
                continue

            truth_sequence, truth_tools = truth_for(dataset, part)
            easy = score_easy(plan.sequence, truth_sequence)
            tools = score_tools(
                [ToolPrediction(op.tool_type, op.tool_diameter_mm) for op in plan.operations],
                truth_tools,
            )
            easy_points.append(easy.points)
            tool_points.append(tools.points)
            lengths.append((len(plan.operations), len(truth_sequence)))

            medium_text = ""
            if not arguments.skip_medium:
                truth_ipws = []
                for index in sorted(part.operations):
                    member = part.operations[index].mesh
                    if member:
                        truth_ipws.append(
                            trimesh.load(io.BytesIO(dataset.read_bytes(member)), file_type="stl")
                        )
                try:
                    medium = score_medium(
                        [as_solid(m) for m in generated.ipws],
                        [as_solid(m) for m in truth_ipws],
                    )
                    medium_points.append(medium.points)
                    medium_text = f"iou {medium.mean_iou:.4f}"
                except Exception as error:  # noqa: BLE001
                    medium_text = f"medium failed: {type(error).__name__}"

                if not arguments.skip_paths:
                    try:
                        points = score_paths(generated, features, truth_ipws)
                        path_points.append(points)
                        medium_text += f" paths {points:.1f}"
                    except Exception as error:  # noqa: BLE001
                        medium_text += f" paths failed: {type(error).__name__}"

            print(f"{part.part_id:22}{len(plan.operations):>4}/{len(truth_sequence):<4}"
                  f"{easy.points:>7.1f}{tools.points:>7.1f}"
                  f"{(medium_points[-1] if medium_points and not arguments.skip_medium else 0):>8.1f}"
                  f"  lev {easy.normalized_levenshtein:.3f} f1 {easy.f1:.3f} {medium_text}")

    elapsed = time.perf_counter() - started
    rule = "=" * 78
    print(f"\n{rule}")
    print(f"BASELINE SCORE over {len(easy_points)} parts ({failures} failures, {elapsed:.1f}s)")
    print(rule)

    easy_mean = statistics.fmean(easy_points) if easy_points else 0.0
    tool_mean = statistics.fmean(tool_points) if tool_points else 0.0
    medium_mean = statistics.fmean(medium_points) if medium_points else 0.0
    path_mean = statistics.fmean(path_points) if path_points else 0.0
    attempted = 75 if (arguments.skip_paths or not path_points) else 100
    print(f"  easy   {easy_mean:6.2f} / 20")
    print(f"  medium {medium_mean:6.2f} / 35" + ("  (skipped)" if arguments.skip_medium else ""))
    print(f"  tools  {tool_mean:6.2f} / 20")
    print(f"  paths  {path_mean:6.2f} / 25" + ("  (skipped)" if arguments.skip_paths else ""))
    print(f"  {'-' * 30}")
    print(f"  TOTAL  {easy_mean + medium_mean + tool_mean + path_mean:6.2f} / 100 "
          f"(of {attempted} attempted)")

    if lengths:
        predicted = statistics.fmean(p for p, _ in lengths)
        actual = statistics.fmean(t for _, t in lengths)
        print(f"\n  operations per part: predicted {predicted:.2f}, actual {actual:.2f}")

    # Prove the formats against the official validator.
    if written_paths is not None:
        print(f"\n{rule}\nOFFICIAL VALIDATOR\n{rule}")
        validator = REPO / "validate_submission.py"
        easy_files = sorted(written_paths.easy.glob("*_sequence.json"))
        hard_files = sorted(written_paths.hard.glob("*_tools.json"))
        checks = [
            ("easy", easy_files[-1] if easy_files else None),
            ("hard", hard_files[-1] if hard_files else None),
            ("medium", written_paths.medium),
            ("hard", written_paths.hard_tool_path),
        ]
        for difficulty, target in checks:
            if target is None:
                continue
            result = subprocess.run(
                [sys.executable, str(validator), str(target), "--difficulty", difficulty],
                capture_output=True, text=True,
            )
            first = result.stdout.strip().splitlines()[:1]
            print(f"  {difficulty:7} {target.name:42} {first[0] if first else result.stderr[:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
