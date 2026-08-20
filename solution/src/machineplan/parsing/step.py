"""A targeted STEP (ISO-10303-21) reader for MachinePlan-10K parts.

**Why not a CAD kernel.** The obvious move is OpenCascade via `cadquery-ocp`
(~400 MB). Measured across a sample of these files, it is not needed: every
surface in the corpus is either a ``PLANE`` (74.8%) or a ``CYLINDRICAL_SURFACE``
(25.2%) -- no splines, cones or tori -- and the files average 25 KB. The parts are
prismatic blocks carrying pockets, holes and chamfers, exactly as the dataset
paper describes, so the geometry can be lifted straight out of the entity table.

That buys a dependency-free reader we fully understand, which matters because the
BRep is the *only* real geometric input available at inference.

The reader is deliberately partial. It resolves the entity reference graph and
extracts faces with their surface geometry and boundary vertices -- enough for
feature recognition -- and does no topological validation, boolean evaluation or
tolerance handling. If a future part introduces a spline surface this will
silently see fewer faces, so :func:`surface_type_census` exists to check that
assumption on new data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterator

Vector = tuple[float, float, float]

# "#123=NAME(args...);" possibly spanning lines. STEP allows arbitrary whitespace.
_INSTANCE_RE = re.compile(r"#(\d+)\s*=\s*([A-Za-z_0-9]+)\s*\((.*?)\)\s*;", re.DOTALL)
_DATA_SECTION_RE = re.compile(r"\bDATA\s*;(.*?)\bENDSEC\s*;", re.DOTALL)
_REFERENCE_RE = re.compile(r"#(\d+)")


class StepParseError(ValueError):
    """Raised when a STEP file cannot be interpreted."""


def _split_arguments(text: str) -> list[str]:
    """Split a STEP argument list on top-level commas.

    Commas inside nested parentheses (a coordinate tuple) or inside a quoted
    string must not split, so a naive ``str.split(',')`` is wrong.
    """
    parts: list[str] = []
    depth = 0
    in_string = False
    current: list[str] = []
    for character in text:
        if in_string:
            current.append(character)
            if character == "'":
                in_string = False
            continue
        if character == "'":
            in_string = True
            current.append(character)
        elif character == "(":
            depth += 1
            current.append(character)
        elif character == ")":
            depth -= 1
            current.append(character)
        elif character == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    if current:
        parts.append("".join(current).strip())
    return parts


def _numbers(text: str) -> list[float]:
    """Every numeric literal in an argument, in order."""
    return [float(value) for value in re.findall(r"-?\d+\.?\d*(?:[Ee][-+]?\d+)?", text)]


@dataclass(slots=True)
class Entity:
    """One ``#id = TYPE(args)`` instance."""

    id: int
    type: str
    raw: str
    arguments: list[str] = field(default_factory=list)

    def references(self) -> list[int]:
        return [int(value) for value in _REFERENCE_RE.findall(self.raw)]


@dataclass(frozen=True, slots=True)
class Placement:
    """An ``AXIS2_PLACEMENT_3D``: an origin plus a primary axis."""

    origin: Vector
    axis: Vector


@dataclass(frozen=True, slots=True)
class Face:
    """One ``ADVANCED_FACE`` reduced to what feature recognition needs."""

    id: int
    surface_type: str
    placement: Placement | None
    radius: float | None
    vertices: tuple[Vector, ...]
    circle_radii: tuple[float, ...]
    outer_bound_count: int
    inner_bound_count: int
    closed_circles: int = 0
    """Boundary edges that are *closed* circles (start vertex == end vertex).

    This is what separates a hole wall from a pocket corner blend. Both are
    cylindrical faces, and both are bounded by ``CIRCLE`` curves -- a 90 degree
    fillet arc is a full circle entity trimmed by its edge vertices, so the curve
    type alone tells you nothing. A hole's wall closes on itself, giving an edge
    whose two vertices are the same instance; a fillet's arc has two distinct
    endpoints. Using the curve type instead over-detected holes 2.6x.
    """

    @property
    def z_range(self) -> tuple[float, float]:
        if not self.vertices:
            return (0.0, 0.0)
        values = [v[2] for v in self.vertices]
        return (min(values), max(values))

    @property
    def is_planar(self) -> bool:
        return self.surface_type == "PLANE"

    @property
    def is_cylindrical(self) -> bool:
        return self.surface_type == "CYLINDRICAL_SURFACE"

    @property
    def is_vertical_axis(self) -> bool:
        """Whether the surface axis runs along +/-Z, as all 2.5-axis features do."""
        if self.placement is None:
            return False
        return abs(abs(self.placement.axis[2]) - 1.0) < 1e-6

    @property
    def has_holes(self) -> bool:
        """Whether the face carries inner boundaries -- e.g. a top face pierced by holes."""
        return self.inner_bound_count > 0


class StepModel:
    """The parsed contents of one ``.stp`` file."""

    def __init__(self, text: str) -> None:
        match = _DATA_SECTION_RE.search(text)
        body = match.group(1) if match else text
        self.entities: dict[int, Entity] = {}
        for instance in _INSTANCE_RE.finditer(body):
            identifier = int(instance.group(1))
            self.entities[identifier] = Entity(
                id=identifier,
                type=instance.group(2).upper(),
                raw=instance.group(3),
            )
        if not self.entities:
            raise StepParseError("no STEP instances found")
        self._faces: list[Face] | None = None

    # ----------------------------------------------------------- primitives

    def of_type(self, name: str) -> Iterator[Entity]:
        for entity in self.entities.values():
            if entity.type == name:
                yield entity

    def _arguments(self, entity: Entity) -> list[str]:
        if not entity.arguments:
            entity.arguments = _split_arguments(entity.raw)
        return entity.arguments

    def point(self, identifier: int) -> Vector | None:
        entity = self.entities.get(identifier)
        if entity is None or entity.type != "CARTESIAN_POINT":
            return None
        values = _numbers(entity.raw)
        return (values[0], values[1], values[2]) if len(values) >= 3 else None

    def direction(self, identifier: int) -> Vector | None:
        entity = self.entities.get(identifier)
        if entity is None or entity.type != "DIRECTION":
            return None
        values = _numbers(entity.raw)
        return (values[0], values[1], values[2]) if len(values) >= 3 else None

    def placement(self, identifier: int) -> Placement | None:
        entity = self.entities.get(identifier)
        if entity is None or entity.type != "AXIS2_PLACEMENT_3D":
            return None
        references = entity.references()
        if len(references) < 2:
            return None
        origin = self.point(references[0])
        axis = self.direction(references[1])
        if origin is None or axis is None:
            return None
        return Placement(origin=origin, axis=axis)

    # --------------------------------------------------------------- faces

    def _loop_vertices(
        self, loop_id: int, seen: set[int]
    ) -> tuple[list[Vector], list[float], int]:
        """Vertices, circle radii, and closed-circle count reachable from an edge loop.

        Only points reached **through a ``VERTEX_POINT``** count as vertices. The
        traversal also passes through ``CIRCLE``, ``LINE``, ``VECTOR`` and
        ``AXIS2_PLACEMENT_3D``, each of which references construction
        ``CARTESIAN_POINT``\\ s -- arc centres, line origins, placement anchors --
        that need not lie on the face or even inside the solid.

        Collecting those inflated every bounding box built from ``face.vertices``.
        Two symptoms it produced: chamfer faces reporting a z-range of
        63.5-127.7 mm on a 73.6 mm block, and pocket-clearing paths covering
        roughly 11x the real footprint.
        """
        vertices: list[Vector] = []
        radii: list[float] = []
        closed = 0
        stack = [loop_id]
        while stack:
            identifier = stack.pop()
            if identifier in seen:
                continue
            seen.add(identifier)
            entity = self.entities.get(identifier)
            if entity is None:
                continue
            if entity.type == "VERTEX_POINT":
                for reference in entity.references():
                    value = self.point(reference)
                    if value is not None:
                        vertices.append(value)
                continue
            if entity.type == "CARTESIAN_POINT":
                # Construction geometry; not a point on the face.
                continue
            if entity.type in ("CIRCLE", "ELLIPSE"):
                values = _numbers(entity.raw)
                if values:
                    radii.append(values[-1] if entity.type == "CIRCLE" else values[-2])
            if entity.type == "EDGE_CURVE":
                # EDGE_CURVE('', #start_vertex, #end_vertex, #curve, .T.)
                references = entity.references()
                if len(references) >= 3 and references[0] == references[1]:
                    curve = self.entities.get(references[2])
                    if curve is not None and curve.type == "CIRCLE":
                        closed += 1
            # Follow structural references, but never step onto a surface.
            if entity.type in (
                "EDGE_LOOP", "ORIENTED_EDGE", "EDGE_CURVE", "VERTEX_POINT",
                "CIRCLE", "ELLIPSE", "LINE", "VECTOR", "AXIS2_PLACEMENT_3D",
            ):
                stack.extend(entity.references())
        return vertices, radii, closed

    @property
    def faces(self) -> list[Face]:
        """Every ``ADVANCED_FACE``, with surface geometry and boundary vertices."""
        if self._faces is not None:
            return self._faces

        faces: list[Face] = []
        for entity in self.of_type("ADVANCED_FACE"):
            arguments = self._arguments(entity)
            if len(arguments) < 2:
                continue
            bound_ids = [int(value) for value in _REFERENCE_RE.findall(arguments[1])]
            surface_ids = [int(value) for value in _REFERENCE_RE.findall(arguments[2])] if len(arguments) > 2 else []
            if not surface_ids:
                continue
            surface = self.entities.get(surface_ids[0])
            if surface is None:
                continue

            radius: float | None = None
            placement: Placement | None = None
            surface_references = surface.references()
            if surface_references:
                placement = self.placement(surface_references[0])
            if surface.type == "CYLINDRICAL_SURFACE":
                values = _numbers(surface.raw)
                if values:
                    radius = values[-1]

            outer = inner = 0
            vertices: list[Vector] = []
            radii: list[float] = []
            closed_circles = 0
            seen: set[int] = set()
            for bound_id in bound_ids:
                bound = self.entities.get(bound_id)
                if bound is None:
                    continue
                if bound.type == "FACE_OUTER_BOUND":
                    outer += 1
                elif bound.type == "FACE_BOUND":
                    inner += 1
                for loop_id in bound.references():
                    loop_vertices, loop_radii, loop_closed = self._loop_vertices(loop_id, seen)
                    vertices.extend(loop_vertices)
                    radii.extend(loop_radii)
                    closed_circles += loop_closed

            faces.append(
                Face(
                    id=entity.id,
                    surface_type=surface.type,
                    placement=placement,
                    radius=radius,
                    vertices=tuple(vertices),
                    circle_radii=tuple(radii),
                    outer_bound_count=outer,
                    inner_bound_count=inner,
                    closed_circles=closed_circles,
                )
            )
        self._faces = faces
        return faces

    # -------------------------------------------------------------- extras

    def outer_boundary(self, face: Face) -> list[Vector]:
        """The face's outer boundary as an **ordered** vertex ring.

        ``Face.vertices`` is an unordered bag, which is enough for a bounding box
        but not for the real footprint -- and a bounding box is wrong for any
        pocket that is not an axis-aligned rectangle, costing IoU in both
        directions at once.

        An ``EDGE_LOOP`` lists its ``ORIENTED_EDGE``\\ s in order, and each edge
        names a start and end vertex; the boolean flag says whether the edge runs
        with or against the underlying curve. Walking them in list order, flipping
        where the flag is false, recovers the ring.
        """
        entity = self.entities.get(face.id)
        if entity is None:
            return []
        arguments = self._arguments(entity)
        if len(arguments) < 2:
            return []

        for bound_id in (int(v) for v in _REFERENCE_RE.findall(arguments[1])):
            bound = self.entities.get(bound_id)
            if bound is None or bound.type != "FACE_OUTER_BOUND":
                continue
            for loop_id in bound.references():
                loop = self.entities.get(loop_id)
                if loop is None or loop.type != "EDGE_LOOP":
                    continue
                ring: list[Vector] = []
                for edge_id in loop.references():
                    oriented = self.entities.get(edge_id)
                    if oriented is None or oriented.type != "ORIENTED_EDGE":
                        continue
                    forward = ".T." in oriented.raw.rsplit(",", 1)[-1]
                    references = oriented.references()
                    if not references:
                        continue
                    curve = self.entities.get(references[-1])
                    if curve is None or curve.type != "EDGE_CURVE":
                        continue
                    edge_references = curve.references()
                    if len(edge_references) < 2:
                        continue
                    start_id, end_id = edge_references[0], edge_references[1]
                    if not forward:
                        start_id, end_id = end_id, start_id
                    for vertex_id in (start_id, end_id):
                        vertex = self.entities.get(vertex_id)
                        if vertex is None or vertex.type != "VERTEX_POINT":
                            continue
                        refs = vertex.references()
                        if not refs:
                            continue
                        point = self.point(refs[0])
                        if point is not None and (not ring or point != ring[-1]):
                            ring.append(point)
                if len(ring) >= 3:
                    return ring
        return []

    @property
    def bounds(self) -> tuple[Vector, Vector]:
        """Axis-aligned bounds over the model's **vertex** points.

        Deliberately not over every ``CARTESIAN_POINT``: the file also carries
        construction geometry -- placement origins for surfaces and curves -- that
        can sit outside the solid. Including those inflated the measured block
        height from ~100 mm to ~136 mm against the paper's published mean.
        """
        real: list[Vector] = []
        for entity in self.of_type("VERTEX_POINT"):
            references = entity.references()
            if not references:
                continue
            value = self.point(references[0])
            if value is not None:
                real.append(value)
        if not real:
            raise StepParseError("model contains no vertex points")
        low = tuple(min(p[axis] for p in real) for axis in range(3))
        high = tuple(max(p[axis] for p in real) for axis in range(3))
        return low, high  # type: ignore[return-value]

    def surface_type_census(self) -> dict[str, int]:
        """Count surface types, to verify the planes-and-cylinders assumption."""
        census: dict[str, int] = {}
        for face in self.faces:
            census[face.surface_type] = census.get(face.surface_type, 0) + 1
        return census

    def __len__(self) -> int:
        return len(self.entities)

    def __str__(self) -> str:
        return f"StepModel({len(self.entities)} entities, {len(self.faces)} faces)"


def parse_step(text: str) -> StepModel:
    """Parse STEP text into a :class:`StepModel`."""
    return StepModel(text)
