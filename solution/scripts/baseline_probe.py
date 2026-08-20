#!/usr/bin/env python3
"""Measure what trivial medium-tier baselines score on the sample IPW sequence.

The point is to establish a score floor and, more usefully, to find out how much
volumetric resolution the rubric's top IoU band actually demands.
"""

from __future__ import annotations

import pathlib
import sys

import trimesh

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from machineplan.scoring.medium import score_medium  # noqa: E402

SAMPLES = pathlib.Path(__file__).resolve().parents[2] / "sample_submission" / "medium"


def main() -> int:
    paths = sorted(SAMPLES.glob("*.stl"))
    if not paths:
        print(f"no sample STLs under {SAMPLES}", file=sys.stderr)
        return 2
    truth = [trimesh.load(p, file_type="stl") for p in paths]

    constant = [truth[0].copy() for _ in truth]
    lagged = [truth[0].copy()] + [t.copy() for t in truth[:-1]]
    exact = [t.copy() for t in truth]

    print("A. constant first-IPW :", score_medium(constant, truth))
    print("B. lag-by-one         :", score_medium(lagged, truth))
    print("C. exact              :", score_medium(exact, truth))

    print("\nper-operation IoU for the constant-first-IPW baseline:")
    for index, value in enumerate(score_medium(constant, truth).per_operation_iou, start=1):
        print(f"   op {index}: {value:.5f}")

    stock = truth[0].volume
    print(f"\nfirst IPW volume: {stock:,.0f} mm^3")
    print(f"total removed over the sequence: {stock - truth[-1].volume:,.0f} mm^3 "
          f"({(stock - truth[-1].volume) / stock * 100:.2f}% of the block)")
    print(f"volume budget for IoU 0.999: ~{stock * 0.001:,.0f} mm^3 of error")
    print("\nper-operation material removed:")
    for index, (before, after) in enumerate(zip(truth, truth[1:]), start=2):
        removed = before.volume - after.volume
        print(f"   op {index}: {removed:12,.1f} mm^3   "
              f"({'BELOW' if removed < stock * 0.001 else 'above'} the 0.999 error budget)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
