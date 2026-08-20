#!/usr/bin/env python3
"""Download the MachinePlan-10K dataset zip, resuming if it was interrupted.

Safe to re-run: a completed download is checksum-verified and skipped, and a
partial download continues from wherever it stopped.

    python scripts/download_dataset.py                 # -> data/MachinePlan-10K.zip
    python scripts/download_dataset.py --dest D:/data  # somewhere with more room
    python scripts/download_dataset.py --verify-only   # just re-check the checksum
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from machineplan.download import EXPECTED_MD5, FILENAME, download, verify  # noqa: E402

DEFAULT_DEST = Path(__file__).resolve().parents[1] / "data"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--dest",
        type=Path,
        default=DEFAULT_DEST,
        help=f"directory to download into (default: {DEFAULT_DEST})",
    )
    parser.add_argument("--quiet", action="store_true", help="suppress progress output")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="check the checksum of an already-downloaded file and exit",
    )
    arguments = parser.parse_args()

    target = arguments.dest / FILENAME if arguments.dest.suffix != ".zip" else arguments.dest

    if arguments.verify_only:
        if not target.exists():
            print(f"no such file: {target}", file=sys.stderr)
            return 2
        ok = verify(target, quiet=arguments.quiet)
        print(f"{'OK' if ok else 'MISMATCH'}: {target} (expected md5 {EXPECTED_MD5})")
        return 0 if ok else 1

    try:
        path = download(target, quiet=arguments.quiet)
    except KeyboardInterrupt:
        print("\ninterrupted; re-run to resume", file=sys.stderr)
        return 130
    except RuntimeError as error:
        print(f"download failed: {error}", file=sys.stderr)
        return 1

    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
