"""Parser for the per-operation ``*_details.txt`` NX reports.

Each file holds two "Object name" sections -- the operation, then the tool it
used -- followed by a tool parameter block. Between them they carry the
authoritative labels and the exact cutting geometry::

    ---------- Object name: SPOT_DRILL  ---------------
    Template Type: hole_making              <- o1
    Template Subtype: SPOT_DRILLING         <- o2
    ...
    Order Group          CENTER
    Geometry Group       STEP1HOLE          <- names the feature being cut
    ...
    ----------------Tool  Information---------------
    ---------- Object name: NXT0321_9005460120000  ---------------
    Template Subtype: NC Spot Drill, 142deg, 12mm, Carbide, Uncoated
    Tool Type :      Spot Drill
    (D) Diameter         =      12.000000000 mm
    (PA) Point Angle     =     142.000000000 °
    (PL) Point Length    =       2.065970000 mm
    (FL) Flute Length    =      30.000000000 mm

This is one of three independent sources of the ``(o1, o2)`` labels -- the others
being ``operations.json`` and the ``.ptp`` header comment (F-012) -- so
disagreement between them is a signal that a parser is wrong, not that the data
is.

Published tool parameters are preferred over anything derived: ``(PL) Point
Length`` and ``(C) Chamfer Length`` give the tip geometry directly, so the swept
volume never has to trust a formula. (Both of ours happened to match to four
decimals, but the published value is still the one to use.)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final

# "---------- Object name: SPOT_DRILL  ---------------"
_OBJECT_RE = re.compile(r"^-+\s*Object name:\s*(.+?)\s*-+\s*$", re.MULTILINE)
_TEMPLATE_TYPE_RE = re.compile(r"^Template Type:\s*(.+?)\s*$", re.MULTILINE)
_TEMPLATE_SUBTYPE_RE = re.compile(r"^Template Subtype:\s*(.+?)\s*$", re.MULTILINE)
_TOOL_SECTION_RE = re.compile(r"^-+\s*Tool\s+Information\s*-+\s*$", re.MULTILINE)
_TOOL_TYPE_RE = re.compile(r"^Tool Type\s*:\s*(.+?)\s*$", re.MULTILINE)
# "(PL) Point Length    =       2.065970000 mm"
_PARAMETER_RE = re.compile(r"\((\w+)\)\s*(.+?)\s*=\s*([-+]?[\d.]+)\s*(mm|°)?\s*$", re.MULTILINE)
# "Order Group          MILL_ROUGH"
_FIELD_RE = re.compile(r"^(Operation Name|Operation Type|Order Group|Method Group|"
                       r"Geometry Group|Cutting Time|Non-Cutting Time|Total Machine Time)"
                       r"\s{2,}(.+?)\s*$", re.MULTILINE)

# NX "Tool Type :" strings mapped onto the contest's tool_type vocabulary.
TOOL_TYPE_MAP: Final[dict[str, str]] = {
    "chamfer mill": "chamfer_mill",
    "end mill": "end_mill",
    "endmill": "end_mill",
    "milling tool": "end_mill",
    # NX names its generic 5-parameter milling cutter this way; it is what
    # FLOOR_WALL pocketing and HOLE_MILLING actually use.
    "milling tool-5 parameters": "end_mill",
    "milling tool-5 params": "end_mill",
    "milling tool-7 parameters": "end_mill",
    "milling tool-10 parameters": "end_mill",
    "spot drill": "spot_drill",
    "spotdrilling tool": "spot_drill",
    "center drill": "spot_drill",
    # The generic NX drill class, used by DRILLING and DEEP_HOLE_DRILLING.
    "drilling tool": "twist_drill",
    "drill": "twist_drill",
    "twist drill": "twist_drill",
    "standard drill": "twist_drill",
    "step drill": "twist_drill",
    "insert drill": "insert_drill",
    "indexable insert drill": "insert_drill",
    "gun drill": "gun_drill",
    "spade drill": "spade_drill",
    "boring tool": "boring_tool",
    "boring bar": "boring_tool",
    "reaming tool": "boring_tool",
    "reamer": "boring_tool",
    "back spotfacing tool": "boring_tool",
}


class DetailsParseError(ValueError):
    """Raised when a details.txt cannot be interpreted."""


@dataclass(frozen=True, slots=True)
class ToolInfo:
    """The tool section of a details report."""

    tool_id: str
    library_name: str
    nx_tool_type: str
    parameters: dict[str, float] = field(default_factory=dict)

    @property
    def tool_type(self) -> str | None:
        """The contest-vocabulary tool type, or ``None`` if unmapped."""
        return TOOL_TYPE_MAP.get(self.nx_tool_type.strip().lower())

    @property
    def diameter_mm(self) -> float | None:
        return self.parameters.get("D")

    @property
    def flute_length_mm(self) -> float | None:
        return self.parameters.get("FL")

    @property
    def overall_length_mm(self) -> float | None:
        return self.parameters.get("L")

    @property
    def point_angle_deg(self) -> float | None:
        return self.parameters.get("PA")

    @property
    def tip_length_mm(self) -> float | None:
        """Axial length of the tapered tip, however this tool spells it.

        Drills publish it as ``(PL) Point Length``, chamfer mills as
        ``(C) Chamfer Length``. Flat-bottomed tools have neither, and 0.0 is the
        right answer for them.
        """
        for code in ("PL", "C"):
            if code in self.parameters:
                return self.parameters[code]
        return 0.0

    @property
    def corner_radius_mm(self) -> float:
        for code in ("CR", "R1"):
            if code in self.parameters:
                return self.parameters[code]
        return 0.0

    def __str__(self) -> str:
        diameter = f"D{self.diameter_mm:g}" if self.diameter_mm else "D?"
        return f"{self.tool_id} ({self.tool_type or self.nx_tool_type}, {diameter})"


@dataclass(frozen=True, slots=True)
class OperationDetails:
    """One operation's report: labels, grouping, timing, and its tool."""

    operation_name: str
    o1: str
    o2: str
    operation_type: str | None = None
    order_group: str | None = None
    method_group: str | None = None
    geometry_group: str | None = None
    cutting_time: str | None = None
    non_cutting_time: str | None = None
    total_time: str | None = None
    tool: ToolInfo | None = None

    def __str__(self) -> str:
        return f"{self.o1}/{self.o2} [{self.operation_name}] tool={self.tool}"


def _parameters(text: str) -> dict[str, float]:
    found: dict[str, float] = {}
    for code, _label, value, _unit in _PARAMETER_RE.findall(text):
        try:
            found.setdefault(code, float(value))
        except ValueError:  # pragma: no cover - defensive
            continue
    return found


def parse_details(text: str) -> OperationDetails:
    """Parse a ``*_details.txt`` report.

    Splits on the "Tool Information" banner so the operation's ``Template Type``
    is never confused with the tool's -- both sections use the same key, and the
    tool's is always the literal string ``Library``.
    """
    text = text.lstrip("﻿")
    split = _TOOL_SECTION_RE.search(text)
    operation_text = text[: split.start()] if split else text
    tool_text = text[split.end() :] if split else ""

    objects = _OBJECT_RE.findall(operation_text)
    if not objects:
        raise DetailsParseError("no 'Object name' section found")
    operation_name = objects[0]

    type_match = _TEMPLATE_TYPE_RE.search(operation_text)
    subtype_match = _TEMPLATE_SUBTYPE_RE.search(operation_text)
    if not type_match or not subtype_match:
        raise DetailsParseError("operation section has no Template Type/Subtype")

    fields = dict(_FIELD_RE.findall(operation_text))

    tool: ToolInfo | None = None
    if tool_text:
        tool_objects = _OBJECT_RE.findall(tool_text)
        tool_subtype = _TEMPLATE_SUBTYPE_RE.search(tool_text)
        tool_type = _TOOL_TYPE_RE.search(tool_text)
        if tool_objects:
            tool = ToolInfo(
                tool_id=tool_objects[0],
                library_name=tool_subtype.group(1) if tool_subtype else "",
                nx_tool_type=tool_type.group(1) if tool_type else "",
                parameters=_parameters(tool_text),
            )

    return OperationDetails(
        operation_name=operation_name,
        o1=type_match.group(1),
        o2=subtype_match.group(1),
        operation_type=fields.get("Operation Type"),
        order_group=fields.get("Order Group"),
        method_group=fields.get("Method Group"),
        geometry_group=fields.get("Geometry Group"),
        cutting_time=fields.get("Cutting Time"),
        non_cutting_time=fields.get("Non-Cutting Time"),
        total_time=fields.get("Total Machine Time"),
        tool=tool,
    )


def parse_labels_only(text: str) -> tuple[str, str]:
    """Fast path: pull just ``(o1, o2)`` from the head of a report.

    Used by the corpus scan, which reads only the first few hundred bytes of each
    of the 91,702 reports rather than decompressing them whole.
    """
    text = text.lstrip("﻿")
    type_match = _TEMPLATE_TYPE_RE.search(text)
    subtype_match = _TEMPLATE_SUBTYPE_RE.search(text)
    if not type_match or not subtype_match:
        raise DetailsParseError("no Template Type/Subtype in the supplied text")
    return type_match.group(1), subtype_match.group(1)
