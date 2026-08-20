"""Resumable downloader for the MachinePlan-10K dataset hosted on Zenodo.

The dataset is a single ~5.2 GB zip. Zenodo serves it over plain HTTPS with
``Range`` support, so an interrupted transfer can be continued instead of
restarted. Nothing outside the standard library is required, which matters
because this is the first thing that has to run on a fresh machine.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

RECORD_ID = "21653081"
FILENAME = "MachinePlan-10K.zip"
URL = f"https://zenodo.org/api/records/{RECORD_ID}/files/{FILENAME}/content"
EXPECTED_SIZE = 5_209_843_207
EXPECTED_MD5 = "831ccc4bd0ee62759ec383556b8c95da"

CHUNK = 1 << 20  # 1 MiB
MAX_ATTEMPTS = 100
BACKOFF_SECONDS = 5


@dataclass
class Progress:
    """Human-readable snapshot of an in-flight transfer."""

    downloaded: int
    total: int
    started_at: float

    @property
    def fraction(self) -> float:
        return self.downloaded / self.total if self.total else 0.0

    def render(self) -> str:
        elapsed = max(time.monotonic() - self.started_at, 1e-6)
        rate = self.downloaded / elapsed
        remaining = (self.total - self.downloaded) / rate if rate > 0 else float("inf")
        return (
            f"{self.fraction * 100:5.1f}%  "
            f"{self.downloaded / 1e9:6.2f}/{self.total / 1e9:.2f} GB  "
            f"{rate / 1e6:6.2f} MB/s  "
            f"eta {_format_duration(remaining)}"
        )


def _format_duration(seconds: float) -> str:
    if seconds == float("inf") or seconds > 86_400 * 7:
        return "--:--"
    seconds = int(seconds)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _free_bytes(path: Path) -> int:
    target = path
    while not target.exists():
        target = target.parent
    return shutil.disk_usage(target).free


def _open_range(url: str, offset: int) -> urllib.request.addinfourl:
    """Open ``url`` starting at ``offset``, verifying the server honours it."""
    request = urllib.request.Request(url, headers={"User-Agent": "machineplan-downloader/1.0"})
    if offset:
        request.add_header("Range", f"bytes={offset}-")
    response = urllib.request.urlopen(request, timeout=60)
    if offset and response.status != 206:
        response.close()
        raise RuntimeError(
            f"server ignored Range request (status {response.status}); "
            "delete the partial file to restart from zero"
        )
    return response


def download(destination: Path, *, quiet: bool = False) -> Path:
    """Fetch the dataset zip to ``destination``, resuming a partial file if present.

    Returns the path to the completed download. Raises on checksum mismatch so a
    corrupted transfer is never silently handed to the parsers.
    """
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")

    if destination.exists() and destination.stat().st_size == EXPECTED_SIZE:
        _log(f"{destination.name} already present; verifying checksum", quiet)
        if verify(destination, quiet=quiet):
            return destination
        _log("checksum mismatch on existing file; re-downloading", quiet)
        destination.unlink()

    offset = partial.stat().st_size if partial.exists() else 0
    if offset > EXPECTED_SIZE:
        _log("partial file is larger than expected; discarding it", quiet)
        partial.unlink()
        offset = 0

    needed = EXPECTED_SIZE - offset
    free = _free_bytes(partial)
    if free < needed:
        raise RuntimeError(
            f"need {needed / 1e9:.1f} GB free for the download but only "
            f"{free / 1e9:.1f} GB is available on {partial.anchor or partial.parent}"
        )
    if offset:
        _log(f"resuming at {offset / 1e9:.2f} GB", quiet)

    progress = Progress(downloaded=offset, total=EXPECTED_SIZE, started_at=time.monotonic())
    attempt = 0
    last_report = 0.0

    while progress.downloaded < EXPECTED_SIZE:
        try:
            response = _open_range(URL, progress.downloaded)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            attempt += 1
            if attempt >= MAX_ATTEMPTS:
                raise RuntimeError(f"giving up after {attempt} failed attempts: {error}") from error
            _log(f"connection failed ({error}); retrying in {BACKOFF_SECONDS}s", quiet)
            time.sleep(BACKOFF_SECONDS)
            continue

        attempt = 0
        try:
            with response, open(partial, "ab") as handle:
                while True:
                    block = response.read(CHUNK)
                    if not block:
                        break
                    handle.write(block)
                    progress.downloaded += len(block)
                    now = time.monotonic()
                    if not quiet and now - last_report >= 2.0:
                        last_report = now
                        print(f"\r{progress.render()}", end="", file=sys.stderr, flush=True)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            # The bytes already flushed to disk stay valid; the next pass resumes.
            _log(f"\ntransfer interrupted ({error}); resuming", quiet)
            time.sleep(BACKOFF_SECONDS)

    if not quiet:
        print(f"\r{progress.render()}", file=sys.stderr, flush=True)

    actual = partial.stat().st_size
    if actual != EXPECTED_SIZE:
        raise RuntimeError(f"downloaded {actual} bytes, expected {EXPECTED_SIZE}")

    os.replace(partial, destination)
    if not verify(destination, quiet=quiet):
        raise RuntimeError(
            f"MD5 mismatch on {destination}; the file is corrupt and was left in place "
            "for inspection. Delete it and re-run to retry."
        )
    _log(f"downloaded and verified {destination}", quiet)
    return destination


def verify(path: Path, *, quiet: bool = False) -> bool:
    """Return whether ``path`` matches the published MD5 for the dataset zip."""
    digest = hashlib.md5()
    size = path.stat().st_size
    read = 0
    last_report = 0.0
    started = time.monotonic()
    with open(path, "rb") as handle:
        while block := handle.read(CHUNK * 8):
            digest.update(block)
            read += len(block)
            now = time.monotonic()
            if not quiet and now - last_report >= 2.0:
                last_report = now
                elapsed = max(now - started, 1e-6)
                print(
                    f"\rverifying {read / size * 100:5.1f}%  {read / elapsed / 1e6:6.1f} MB/s",
                    end="",
                    file=sys.stderr,
                    flush=True,
                )
    if not quiet:
        print(f"\rverifying 100.0%{' ' * 24}", file=sys.stderr, flush=True)
    return digest.hexdigest() == EXPECTED_MD5


def _log(message: str, quiet: bool) -> None:
    if not quiet:
        print(message, file=sys.stderr, flush=True)
