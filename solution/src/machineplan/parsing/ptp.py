"""Parser for the ``.ptp`` NC-code tool path files.

The dialect NX emits here is small but *heavily modal*: a sample AREA_MILL
operation declares ``G1`` once and then sends 250 consecutive blocks carrying
only the axis words that changed. Any parser that does not carry modal state
forward will silently produce a path full of holes, so the state machine is the
whole job.

Codes observed in the sample operation::

    G0 G1 G17 G21 G43 G54 G90 G94   M2 M3 M5 M6

Arcs (``G2``/``G3``) and drilling canned cycles (``G81``-``G89``) do not appear
in that one file but are expected in hole-making operations, so both are handled
here rather than discovered later as a crash.

The leading comment block also carries supervision worth keeping::

    (AREA_MILL , TOOL : UGT0205_001)

-- the operation subtype and the tool library id, which tie a tool path back to
its ``o2`` label and its entry in the NX tool library.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Literal, Sequence

Vector = tuple[float, float, float]
MotionKind = Literal["rapid", "linear", "arc_cw", "arc_ccw", "cycle"]

# One address word: a letter followed by a signed, possibly trailing-dot number.
_WORD_RE = re.compile(r"([A-Za-z])\s*([+-]?(?:\d+\.?\d*|\.\d+))")
_COMMENT_RE = re.compile(r"\(([^)]*)\)")
# "(AREA_MILL , TOOL : UGT0205_001)"
_OPERATION_RE = re.compile(r"^\s*([A-Z_][A-Z0-9_]*)\s*,\s*TOOL\s*:\s*(\S+?)\s*$")
# "(PARTNAME        : FEATURED_PART_00001.PRT  )"
_HEADER_RE = re.compile(r"^\s*([A-Z][A-Z ]*?)\s*:\s*(.*?)\s*$")

RAPID_CODES = {0}
LINEAR_CODES = {1}
ARC_CW_CODES = {2}
ARC_CCW_CODES = {3}
# G4 is a dwell. Its X/P/U word is a *duration*, not a coordinate -- "G4 X.084"
# means pause 0.084 s. Reading that X as an axis word drags the tool to X=0.084,
# which for a drill at depth carves a long trench through solid material. This
# was a real bug: it produced 6.4x overcut on deep-hole drilling before being
# caught by the per-subtype validation.
DWELL_CODE = 4
# Canned cycles. G81-G89 are the familiar drilling/boring family, but NX also
# posts G73 (high-speed peck) and G74/G76, and missing G73 is not harmless: an
# unrecognised cycle falls through to the "no motion mode" fallback, becomes a
# non-cutting rapid, and the operation silently sweeps nothing at all.
CYCLE_CODES = frozenset({73, 74, 76}) | frozenset(range(81, 90))
CYCLE_CANCEL = 80
MOTION_CODES = RAPID_CODES | LINEAR_CODES | ARC_CW_CODES | ARC_CCW_CODES | CYCLE_CODES | {CYCLE_CANCEL}


class PtpParseError(ValueError):
    """Raised when a tool path file cannot be interpreted."""


@dataclass(frozen=True, slots=True)
class Move:
    """A single commanded motion, resolved to absolute start and end points."""

    kind: MotionKind
    start: Vector
    end: Vector
    feed: float | None = None
    center: Vector | None = None
    block: int | None = None

    @property
    def is_cutting(self) -> bool:
        """Whether this move is expected to remove material.

        Rapids are positioning moves; in a well-formed NX program they happen at
        clearance height and cut nothing. Canned cycles do cut.
        """
        return self.kind != "rapid"

    @property
    def length(self) -> float:
        return sum((b - a) ** 2 for a, b in zip(self.start, self.end)) ** 0.5

    @property
    def is_vertical(self) -> bool:
        """A pure Z move -- a plunge or a retract."""
        return abs(self.start[0] - self.end[0]) < 1e-9 and abs(self.start[1] - self.end[1]) < 1e-9

    @property
    def is_planar(self) -> bool:
        """A move at constant Z, the common case in 2.5-axis machining."""
        return abs(self.start[2] - self.end[2]) < 1e-9


@dataclass(slots=True)
class ToolPath:
    """A parsed ``.ptp`` file: header metadata plus the resolved motion list."""

    moves: list[Move] = field(default_factory=list)
    header: dict[str, str] = field(default_factory=dict)
    operation: str | None = None
    tool_id: str | None = None
    spindle_rpm: float | None = None
    tool_change: int | None = None
    metric: bool = True
    comments: list[str] = field(default_factory=list)
    source: Path | None = None

    @property
    def cutting_moves(self) -> list[Move]:
        return [move for move in self.moves if move.is_cutting]

    @property
    def z_levels(self) -> list[float]:
        """Distinct Z heights at which cutting happens, deepest first.

        2.5-axis machining is organised as a stack of constant-Z passes, so these
        levels are the natural decomposition for computing a swept volume.
        """
        levels = {round(move.end[2], 6) for move in self.cutting_moves if move.is_planar}
        return sorted(levels)

    @property
    def bounds(self) -> tuple[Vector, Vector]:
        """Axis-aligned bounds of every commanded point, rapids included."""
        if not self.moves:
            raise PtpParseError("tool path contains no moves")
        points = [move.start for move in self.moves] + [move.end for move in self.moves]
        low = tuple(min(point[axis] for point in points) for axis in range(3))
        high = tuple(max(point[axis] for point in points) for axis in range(3))
        return low, high  # type: ignore[return-value]

    @property
    def cutting_length(self) -> float:
        return sum(move.length for move in self.cutting_moves)

    @property
    def rapid_length(self) -> float:
        return sum(move.length for move in self.moves if not move.is_cutting)

    def __str__(self) -> str:
        return (
            f"ToolPath({self.operation or '?'} tool={self.tool_id or '?'} "
            f"moves={len(self.moves)} cutting={len(self.cutting_moves)} "
            f"levels={len(self.z_levels)} cut_len={self.cutting_length:.1f}mm)"
        )


def _center_from_radius(
    start: Vector,
    end: Vector,
    radius: float,
    motion: MotionKind,
) -> Vector | None:
    """Resolve an ``R``-format arc centre in the XY plane.

    G-code allows an arc to be given either by centre offsets (``I``/``J``) or by
    radius (``R``). Two centres satisfy any chord-plus-radius; the convention is
    that a **positive** ``R`` selects the minor arc (<= 180 degrees) and a
    **negative** ``R`` the major one.

    Without this, an R-format arc has no centre, gets treated as a straight
    chord, and a circular hole-milling pass collapses to a polygon -- undercutting
    badly. Returns ``None`` when the radius cannot span the chord.
    """
    import math

    dx = end[0] - start[0]
    dy = end[1] - start[1]
    chord = math.hypot(dx, dy)
    if chord < 1e-12:
        return None

    half = chord / 2.0
    magnitude = abs(radius)
    if magnitude < half - 1e-9:
        return None  # radius too small to reach; malformed block
    height = math.sqrt(max(magnitude * magnitude - half * half, 0.0))

    midpoint = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
    # Unit chord normal, rotated +90 degrees.
    normal = (-dy / chord, dx / chord)

    sign = 1.0 if motion == "arc_ccw" else -1.0
    if radius < 0:
        sign = -sign

    return (
        midpoint[0] + sign * height * normal[0],
        midpoint[1] + sign * height * normal[1],
        start[2],
    )


def _iter_blocks(text: str) -> Iterator[tuple[str, list[str]]]:
    """Yield ``(code_part, comments)`` for each line, stripping comment spans."""
    for line in text.splitlines():
        comments = [match.group(1) for match in _COMMENT_RE.finditer(line)]
        code = _COMMENT_RE.sub(" ", line).strip()
        if code or comments:
            yield code, comments


def parse_ptp(source: str | Path, *, encoding: str = "utf-8") -> ToolPath:
    """Parse a ``.ptp`` tool path into absolute moves.

    ``source`` may be a path or the file's text content.
    """
    if isinstance(source, Path):
        text = source.read_text(encoding=encoding, errors="replace")
        path = source
    elif "\n" in str(source) or not str(source).endswith(".ptp"):
        text = str(source)
        path = None
    else:  # a path given as a plain string
        path = Path(source)
        text = path.read_text(encoding=encoding, errors="replace")

    result = ToolPath(source=path)

    # Modal state.
    position: list[float | None] = [None, None, None]
    motion: MotionKind | None = None
    feed: float | None = None
    absolute = True
    block_number: int | None = None
    cycle_retract: float | None = None

    for code, comments in _iter_blocks(text):
        for comment in comments:
            result.comments.append(comment)
            operation_match = _OPERATION_RE.match(comment)
            if operation_match:
                result.operation = operation_match.group(1)
                result.tool_id = operation_match.group(2)
                continue
            header_match = _HEADER_RE.match(comment)
            if header_match:
                result.header.setdefault(header_match.group(1).strip(), header_match.group(2))

        if not code:
            continue

        words = [(letter.upper(), float(value)) for letter, value in _WORD_RE.findall(code)]
        if not words:
            continue

        axis_words: dict[str, float] = {}
        arc_words: dict[str, float] = {}
        motion_this_block: MotionKind | None = None
        cycle_this_block = False
        dwell_this_block = any(
            letter == "G" and int(value) == DWELL_CODE for letter, value in words
        )

        for letter, value in words:
            if letter == "N":
                block_number = int(value)
            elif letter == "G":
                integer = int(value)
                if integer == DWELL_CODE:
                    continue
                if integer in RAPID_CODES:
                    motion = motion_this_block = "rapid"
                elif integer in LINEAR_CODES:
                    motion = motion_this_block = "linear"
                elif integer in ARC_CW_CODES:
                    motion = motion_this_block = "arc_cw"
                elif integer in ARC_CCW_CODES:
                    motion = motion_this_block = "arc_ccw"
                elif integer in CYCLE_CODES:
                    motion = motion_this_block = "cycle"
                    cycle_this_block = True
                elif integer == CYCLE_CANCEL:
                    motion = None
                elif integer == 90:
                    absolute = True
                elif integer == 91:
                    absolute = False
                elif integer == 20:
                    result.metric = False
                elif integer == 21:
                    result.metric = True
            elif letter in ("X", "Y", "Z"):
                axis_words[letter] = value
            elif letter in ("I", "J", "K"):
                arc_words[letter] = value
            elif letter == "R" and motion in ("arc_cw", "arc_ccw"):
                arc_words["R"] = value
            elif letter == "F":
                feed = value
            elif letter == "S":
                result.spindle_rpm = value
            elif letter == "T":
                result.tool_change = int(value)
            elif letter == "R":
                cycle_retract = value

        # A dwell block's axis-looking words are durations; it commands no motion.
        if dwell_this_block or not axis_words:
            continue
        if motion is None:
            # Axis words with no motion mode yet (e.g. after a G80): treat as a
            # positioning move rather than dropping the point on the floor.
            motion_this_block = motion = "rapid"

        start: Vector = tuple(0.0 if value is None else value for value in position)  # type: ignore[assignment]
        end = list(start)
        for index, letter in enumerate("XYZ"):
            if letter in axis_words:
                end[index] = axis_words[letter] if absolute else start[index] + axis_words[letter]

        # Before the first move every axis is unknown; a block that does not name
        # all three cannot be resolved to a real segment, so seed and move on.
        if any(value is None for value in position):
            for index, letter in enumerate("XYZ"):
                if letter in axis_words:
                    position[index] = end[index]
            if any(value is None for value in position):
                continue
            start = tuple(position)  # type: ignore[assignment]
            end = list(start)

        center: Vector | None = None
        if motion in ("arc_cw", "arc_ccw"):
            if {"I", "J", "K"} & set(arc_words):
                center = (
                    start[0] + arc_words.get("I", 0.0),
                    start[1] + arc_words.get("J", 0.0),
                    start[2] + arc_words.get("K", 0.0),
                )
            elif "R" in arc_words:
                center = _center_from_radius(
                    start, (end[0], end[1], end[2]), arc_words["R"], motion
                )

        end_vector: Vector = (end[0], end[1], end[2])
        if end_vector != start or cycle_this_block:
            result.moves.append(
                Move(
                    kind=motion,
                    start=start,
                    end=end_vector,
                    feed=feed if motion != "rapid" else None,
                    center=center,
                    block=block_number,
                )
            )
            # A canned cycle drills to Z then returns to the retract plane.
            if cycle_this_block and cycle_retract is not None:
                retract: Vector = (end_vector[0], end_vector[1], cycle_retract)
                result.moves.append(
                    Move(kind="rapid", start=end_vector, end=retract, block=block_number)
                )
                end_vector = retract

        position = list(end_vector)

    if not result.moves:
        raise PtpParseError(f"no motion blocks found in {path or 'input'}")
    return result


def discretize(
    moves: Sequence[Move],
    *,
    max_step: float = 1.0,
    arc_segments: int = 32,
) -> list[Vector]:
    """Flatten moves into a dense polyline, expanding arcs into chords.

    ``max_step`` bounds the spacing between successive points so a swept volume
    built from these positions does not miss material between samples.
    """
    import math

    if not moves:
        return []

    points: list[Vector] = [moves[0].start]
    for move in moves:
        if move.kind in ("arc_cw", "arc_ccw") and move.center is not None:
            centre = move.center
            start_angle = math.atan2(move.start[1] - centre[1], move.start[0] - centre[0])
            end_angle = math.atan2(move.end[1] - centre[1], move.end[0] - centre[0])
            radius = math.hypot(move.start[0] - centre[0], move.start[1] - centre[1])
            sweep = end_angle - start_angle
            if move.kind == "arc_cw":
                while sweep >= 0:
                    sweep -= 2 * math.pi
            else:
                while sweep <= 0:
                    sweep += 2 * math.pi
            steps = max(arc_segments, int(abs(sweep) * radius / max_step) + 1)
            for index in range(1, steps + 1):
                fraction = index / steps
                angle = start_angle + sweep * fraction
                points.append(
                    (
                        centre[0] + radius * math.cos(angle),
                        centre[1] + radius * math.sin(angle),
                        move.start[2] + (move.end[2] - move.start[2]) * fraction,
                    )
                )
            continue

        steps = max(1, int(move.length / max_step) + 1)
        for index in range(1, steps + 1):
            fraction = index / steps
            points.append(
                (
                    move.start[0] + (move.end[0] - move.start[0]) * fraction,
                    move.start[1] + (move.end[1] - move.start[1]) * fraction,
                    move.start[2] + (move.end[2] - move.start[2]) * fraction,
                )
            )
    return points
