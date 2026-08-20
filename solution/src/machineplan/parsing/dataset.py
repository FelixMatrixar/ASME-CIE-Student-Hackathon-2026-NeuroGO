"""Lazy, zip-backed reader for the MachinePlan-10K dataset.

The dataset ships as a single 5.2 GB zip that expands to an estimated 25-30 GB.
On the development machine that would not fit, so nothing is ever extracted:
``zipfile.ZipFile`` gives random access to members through the central
directory, and parts are read on demand.

The documented layout (Dataset_Description.pdf Fig. 1) is::

    MachinePlan-10K/
      part_00001/
        part_00001.stp                  BRep, available at inference
        part_00001_operations.json      CAM operation sequence metadata
        front_wireframe.png             \\
        top_wireframe.png                | four rendered views,
        right_wireframe.png              | available at inference
        isometric_shaded.png            /
        000_BLANK_text.stl.txt          IPW before the first operation
        001_UGT0205_001_details.txt     operation 1: tool/operation report
        001_UGT0205_001_text.stl.txt    operation 1: IPW mesh
        001_UGT0205_001.ptp             operation 1: tool path
        ...

Operation files are keyed by a zero-padded index and the tool id, so the tool
used by each operation is recoverable from the filename alone.

Structure is *discovered* from the archive rather than assumed, because the
prefix directory and separator style are not guaranteed to match the document.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path, PurePosixPath
from typing import Iterator

# "001_UGT0205_001_details.txt" / "001_UGT0205_001_text.stl.txt" / "001_UGT0205_001.ptp"
_OPERATION_RE = re.compile(
    r"^(?P<index>\d{3})_(?P<tool_id>.+?)(?P<suffix>_details\.txt|_text\.stl\.txt|\.ptp)$"
)
_BLANK_RE = re.compile(r"^0{3}_BLANK_text\.stl\.txt$", re.IGNORECASE)
_IMAGE_SUFFIXES = (".png",)


class DatasetError(RuntimeError):
    """Raised when the archive does not look like MachinePlan-10K."""


@dataclass(slots=True)
class OperationFiles:
    """The three files describing one operation, as archive member names."""

    index: int
    tool_id: str
    details: str | None = None
    mesh: str | None = None
    tool_path: str | None = None

    @property
    def is_complete(self) -> bool:
        return all((self.details, self.mesh, self.tool_path))


@dataclass(slots=True)
class PartFiles:
    """Every archive member belonging to one part."""

    part_id: str
    root: str
    brep: str | None = None
    operations_json: str | None = None
    blank_mesh: str | None = None
    images: dict[str, str] = field(default_factory=dict)
    operations: dict[int, OperationFiles] = field(default_factory=dict)

    @property
    def operation_count(self) -> int:
        return len(self.operations)

    def ordered_operations(self) -> list[OperationFiles]:
        return [self.operations[key] for key in sorted(self.operations)]

    def __str__(self) -> str:
        return f"{self.part_id} ({self.operation_count} operations)"


class MachinePlanDataset:
    """Random-access reader over the dataset zip.

    Intended for ``with`` use, since it holds an open archive handle::

        with MachinePlanDataset("data/MachinePlan-10K.zip") as dataset:
            part = dataset.part("part_00001")
            text = dataset.read_text(part.operations[1].details)
    """

    def __init__(self, archive: str | Path) -> None:
        self.path = Path(archive)
        if not self.path.exists():
            raise FileNotFoundError(
                f"{self.path} not found -- run scripts/download_dataset.py first"
            )
        self._zip = zipfile.ZipFile(self.path)

    # ------------------------------------------------------------- lifecycle

    def close(self) -> None:
        self._zip.close()

    def __enter__(self) -> "MachinePlanDataset":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------- indexing

    @cached_property
    def _index(self) -> dict[str, PartFiles]:
        """Group every archive member under the part folder that owns it."""
        parts: dict[str, PartFiles] = {}
        for name in self._zip.namelist():
            if name.endswith("/"):
                continue
            posix = PurePosixPath(name)
            if len(posix.parts) < 2:
                continue
            # The part folder is the last directory component.
            part_id = posix.parts[-2]
            filename = posix.name
            root = str(posix.parent)

            part = parts.get(part_id)
            if part is None:
                part = parts[part_id] = PartFiles(part_id=part_id, root=root)

            lowered = filename.lower()
            if lowered.endswith(".stp") or lowered.endswith(".step"):
                part.brep = name
            elif lowered.endswith("_operations.json"):
                part.operations_json = name
            elif _BLANK_RE.match(filename):
                part.blank_mesh = name
            elif lowered.endswith(_IMAGE_SUFFIXES):
                part.images[posix.stem] = name
            else:
                match = _OPERATION_RE.match(filename)
                if not match:
                    continue
                index = int(match.group("index"))
                entry = part.operations.get(index)
                if entry is None:
                    entry = part.operations[index] = OperationFiles(
                        index=index, tool_id=match.group("tool_id")
                    )
                suffix = match.group("suffix")
                if suffix == "_details.txt":
                    entry.details = name
                elif suffix == "_text.stl.txt":
                    entry.mesh = name
                else:
                    entry.tool_path = name

        # Drop folders that carry no operations and no BRep -- these are archive
        # scaffolding (a top-level README, say), not parts.
        real = {
            key: value
            for key, value in parts.items()
            if value.operations or value.brep or value.operations_json
        }
        if not real:
            raise DatasetError(f"{self.path} contains no recognizable part folders")
        return real

    @property
    def part_ids(self) -> list[str]:
        return sorted(self._index)

    def __len__(self) -> int:
        return len(self._index)

    def __contains__(self, part_id: str) -> bool:
        return part_id in self._index

    def __iter__(self) -> Iterator[PartFiles]:
        for part_id in self.part_ids:
            yield self._index[part_id]

    def part(self, part_id: str) -> PartFiles:
        try:
            return self._index[part_id]
        except KeyError:
            raise KeyError(f"no part {part_id!r} in {self.path.name}") from None

    # ------------------------------------------------------------- accessors

    def read_bytes(self, member: str) -> bytes:
        return self._zip.read(member)

    def read_text(self, member: str, *, encoding: str = "utf-8") -> str:
        return self._zip.read(member).decode(encoding, errors="replace")

    def open(self, member: str) -> io.BufferedIOBase:
        return self._zip.open(member)

    def read_json(self, member: str) -> dict:
        return json.loads(self.read_text(member))

    def member_size(self, member: str) -> int:
        return self._zip.getinfo(member).file_size

    def summary(self) -> str:
        counts = [part.operation_count for part in self]
        total = sum(counts)
        complete = sum(
            1 for part in self for op in part.operations.values() if op.is_complete
        )
        return (
            f"{self.path.name}: {len(self)} parts, {total} operations "
            f"({complete} with all three files), "
            f"{min(counts, default=0)}-{max(counts, default=0)} operations per part"
        )
