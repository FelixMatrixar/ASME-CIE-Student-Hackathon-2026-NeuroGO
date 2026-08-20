#!/usr/bin/env python3
"""Generate the contest submission from the released test data.

Reads each part's boundary representation from a directory tree like

    Test_Data/
      featured_part_12017/
        featured_part_12017.stp
        front_wireframe.png ...
      featured_part_22222/
        Featured_part_22222.stp
        Note.txt

and writes the four deliverables. Only the `.stp` is read: the renders are never
opened, which is what lets `featured_part_22222` work at all, since its note says
to infer it without any images.

The part identifier comes from the **folder name**, not the file name. One test
part capitalises its file differently from its folder, and the official validator
requires the identifier inside each JSON to match the one in its filename.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from machineplan.features import extract_features  # noqa: E402
from machineplan.generate import generate_part  # noqa: E402
from machineplan.parsing.step import parse_step  # noqa: E402
from machineplan.predict import plan_part  # noqa: E402
from machineplan.submission import write_submission  # noqa: E402

SOLUTION = pathlib.Path(__file__).resolve().parents[1]
REPO = SOLUTION.parent
DEFAULT_INPUT = REPO / "Test_Data"
DEFAULT_OUT = SOLUTION / "outputs" / "submission"


def find_step(folder: pathlib.Path) -> pathlib.Path | None:
    """The part's STEP file, matched case-insensitively."""
    for candidate in sorted(folder.iterdir()):
        if candidate.is_file() and candidate.suffix.lower() in (".stp", ".step"):
            return candidate
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=pathlib.Path, default=DEFAULT_INPUT)
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument("--validate", action="store_true",
                        help="run the official validator on every artifact written")
    arguments = parser.parse_args()

    folders = sorted(p for p in arguments.input.iterdir() if p.is_dir())
    if not folders:
        print(f"no part folders under {arguments.input}", file=sys.stderr)
        return 2

    print(f"generating submission for {len(folders)} parts -> {arguments.out}\n")
    print(f"{'part':26}{'ops':>5}{'holes':>7}{'pockets':>9}{'chamfers':>10}{'sec':>7}")
    print("-" * 66)

    written: list[tuple[str, object]] = []
    failures: list[str] = []
    started = time.perf_counter()

    for folder in folders:
        part_id = folder.name
        step_path = find_step(folder)
        if step_path is None:
            failures.append(f"{part_id}: no STEP file")
            print(f"{part_id:26}  NO STEP FILE")
            continue
        try:
            began = time.perf_counter()
            model = parse_step(step_path.read_text(encoding="utf-8", errors="replace"))
            features = extract_features(model)
            plan = plan_part(part_id, features)
            generated = generate_part(plan, features)
            paths = write_submission(generated, arguments.out)
            elapsed = time.perf_counter() - began
        except Exception as error:  # noqa: BLE001
            failures.append(f"{part_id}: {type(error).__name__}: {error}")
            print(f"{part_id:26}  FAILED {type(error).__name__}: {error}")
            continue

        written.append((part_id, paths))
        print(f"{part_id:26}{len(plan.operations):>5}{len(features.holes):>7}"
              f"{len(features.pocket_floors):>9}{len(features.chamfers):>10}"
              f"{elapsed:>7.2f}")

    total = time.perf_counter() - started
    rule = "=" * 66
    print(f"\n{rule}")
    print(f"{len(written)} parts written, {len(failures)} failures, {total:.1f}s total")
    print(rule)
    for line in failures:
        print(f"  {line}")

    if arguments.validate and written:
        print(f"\n{rule}\nOFFICIAL VALIDATOR\nEvery artifact, not a sample\n{rule}")
        validator = REPO / "validate_submission.py"
        checked = passed = 0
        problems: list[str] = []
        for part_id, paths in written:
            targets = [
                ("easy", paths.easy / f"{part_id}_sequence.json"),
                ("hard", paths.hard / f"{part_id}_tools.json"),
                ("medium", paths.medium),
                ("hard", paths.hard_tool_path),
            ]
            for difficulty, target in targets:
                checked += 1
                result = subprocess.run(
                    [sys.executable, str(validator), str(target),
                     "--difficulty", difficulty],
                    capture_output=True, text=True,
                )
                if result.returncode == 0:
                    passed += 1
                else:
                    problems.append(f"{part_id} [{difficulty}] {result.stdout.strip()[:160]}")
        print(f"  {passed}/{checked} artifacts valid")
        for line in problems[:20]:
            print(f"    {line}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
