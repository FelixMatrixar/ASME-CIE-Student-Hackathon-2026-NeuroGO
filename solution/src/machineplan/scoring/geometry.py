"""Shared solid-geometry helpers for the medium and hard tiers.

Everything here is volume-based. The medium tier needs IoU resolved to better
than 0.001 to distinguish the top rubric band (0.999-1.0, worth 35 points) from
the next one down (0.99-0.999, worth 25), so approximate voxel IoU is not good
enough as a primary metric -- exact mesh booleans are required. Voxel IoU is kept
only as a diagnostic fallback for meshes that refuse to become watertight.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh


class DegenerateMeshError(ValueError):
    """Raised when a mesh cannot be made solid enough to compute a volume."""


def _is_usable(mesh: trimesh.Trimesh) -> bool:
    """Whether the boolean backend will accept this mesh as a solid."""
    return bool(mesh.is_volume) and np.isfinite(mesh.volume) and abs(mesh.volume) > 0


def as_solid(mesh: trimesh.Trimesh, *, name: str = "mesh") -> trimesh.Trimesh:
    """Return a watertight, outward-oriented version of ``mesh``.

    **Repairs are applied only when the mesh is actually broken.** This is not
    mere efficiency: face-culling repairs such as ``nondegenerate_faces`` remove
    sliver triangles, and the solids here legitimately contain them. A chamfer
    removal volume is a long thin wedge -- 53,101 mm^3 spread along 339 mm -- so
    unconditional "cleanup" deletes real geometry and turns a valid solid into a
    non-watertight one. That was a live bug: it silently corrupted IoU for
    exactly the thin-wedge operations the hard tier cares about.

    Repair therefore escalates gently and stops as soon as the mesh is usable.
    """
    if _is_usable(mesh):
        return mesh if mesh.volume > 0 else _flipped(mesh)

    solid = mesh.copy()

    # Cheapest first: merging coincident vertices closes most seam-type gaps
    # without deleting anything.
    solid.merge_vertices()
    trimesh.repair.fix_winding(solid)
    if _is_usable(solid):
        return solid if solid.volume > 0 else _flipped(solid)

    trimesh.repair.fix_normals(solid)
    if _is_usable(solid):
        return solid if solid.volume > 0 else _flipped(solid)

    # Only now, with the mesh known to be broken, drop faces that cannot
    # contribute: exact duplicates and zero-area triangles.
    solid.update_faces(solid.unique_faces())
    solid.update_faces(solid.nondegenerate_faces())
    solid.remove_unreferenced_vertices()
    if not solid.is_watertight:
        trimesh.repair.fill_holes(solid)
    trimesh.repair.fix_normals(solid)

    if not np.isfinite(solid.volume) or abs(solid.volume) <= 0:
        raise DegenerateMeshError(f"{name} has non-positive volume ({solid.volume})")
    if not solid.is_volume:
        raise DegenerateMeshError(
            f"{name} could not be repaired into a solid "
            f"(watertight={solid.is_watertight}, winding={solid.is_winding_consistent})"
        )
    return solid if solid.volume > 0 else _flipped(solid)


def _flipped(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Return an inward-facing mesh flipped outward, without touching the original."""
    flipped = mesh.copy()
    flipped.invert()
    return flipped


def _boolean_volume(operation: str, a: trimesh.Trimesh, b: trimesh.Trimesh) -> float:
    """Volume of a boolean between two solids, treating an empty result as zero."""
    result = trimesh.boolean.boolean_manifold([a, b], operation)
    if result is None or result.is_empty or len(result.faces) == 0:
        return 0.0
    return abs(float(result.volume))


@dataclass(frozen=True, slots=True)
class VolumeComparison:
    """Volumetric agreement between a predicted solid and a reference solid."""

    predicted_volume: float
    truth_volume: float
    intersection: float
    union: float

    @property
    def iou(self) -> float:
        return self.intersection / self.union if self.union > 0 else 0.0

    @property
    def overcut(self) -> float:
        """Material removed that should not have been, over the reference volume.

        Per Rubrics.pdf: "Overcut refers to the volume of material removed that
        should not have been removed". That is the part of the *prediction*
        lying outside the reference, ``|P \\ G| / |G|``.
        """
        if self.truth_volume <= 0:
            return 0.0
        return max(self.predicted_volume - self.intersection, 0.0) / self.truth_volume

    @property
    def undercut(self) -> float:
        """Material that should have been removed but was not, over the reference volume.

        The part of the *reference* the prediction missed, ``|G \\ P| / |G|``.
        """
        if self.truth_volume <= 0:
            return 0.0
        return max(self.truth_volume - self.intersection, 0.0) / self.truth_volume

    def __str__(self) -> str:
        return (
            f"iou {self.iou:.5f}  over {self.overcut:.4f}  under {self.undercut:.4f}  "
            f"vol {self.predicted_volume:.1f}v{self.truth_volume:.1f}"
        )


def compare_volumes(
    predicted: trimesh.Trimesh,
    truth: trimesh.Trimesh,
    *,
    repair: bool = True,
) -> VolumeComparison:
    """Exact volumetric IoU plus over/under-cut between two solids."""
    if repair:
        predicted = as_solid(predicted, name="predicted")
        truth = as_solid(truth, name="truth")

    predicted_volume = abs(float(predicted.volume))
    truth_volume = abs(float(truth.volume))

    # Disjoint bounding boxes mean an empty intersection; skip the boolean.
    if _bounds_disjoint(predicted, truth):
        return VolumeComparison(predicted_volume, truth_volume, 0.0, predicted_volume + truth_volume)

    intersection = _boolean_volume("intersection", predicted, truth)
    # Inclusion-exclusion is both faster and more numerically stable here than a
    # second boolean, and guarantees union >= intersection exactly.
    union = predicted_volume + truth_volume - intersection

    return VolumeComparison(
        predicted_volume=predicted_volume,
        truth_volume=truth_volume,
        intersection=intersection,
        union=max(union, 0.0),
    )


def _bounds_disjoint(a: trimesh.Trimesh, b: trimesh.Trimesh, tolerance: float = 1e-9) -> bool:
    return bool(np.any(a.bounds[1] + tolerance < b.bounds[0]) or np.any(b.bounds[1] + tolerance < a.bounds[0]))


def removed_volume(before: trimesh.Trimesh, after: trimesh.Trimesh) -> trimesh.Trimesh:
    """The material an operation removed: ``before - after``.

    This is the quantity the hard tier scores a submitted tool path against, and
    it is also exactly what separates consecutive medium-tier IPWs. Computing it
    once serves both tiers.
    """
    before = as_solid(before, name="before")
    after = as_solid(after, name="after")
    result = trimesh.boolean.boolean_manifold([before, after], "difference")
    if result is None or result.is_empty:
        raise DegenerateMeshError("operation removed no material")
    return result


def denoise_difference(
    solid: trimesh.Trimesh,
    *,
    min_thickness_mm: float = 0.05,
) -> trimesh.Trimesh:
    """Strip re-tessellation slivers from a ``before - after`` difference.

    The IPW meshes are re-triangulated after every operation, so the boolean
    difference of two consecutive IPWs contains, besides the material actually
    removed, thin sheets wherever a planar face happened to be tessellated
    differently. Measured on ``featured_part_00001``: the difference for a
    through-drilling operation had 20 connected bodies, of which one was the real
    9.4 mm hole (6,123 mm^3, 99.8%) and nineteen were sheets as thin as **17
    microns** spanning up to 92 mm.

    For a large operation that noise is irrelevant. For a small one it dominates:
    the spot-drilling difference totalled 42.0 mm^3 of which the real dimple was
    only 3.3 mm^3 -- **the noise was 12x the signal**. Comparing a correct swept
    volume against that raw difference scores near zero (see F-021).

    A body is discarded purely on **thickness**, not on volume: those sheets are
    thin but not small (0.017 x 70.9 x 37.9 mm is still 18 mm^3, far larger than
    the 3.3 mm^3 dimple that was the real signal), so any volume-based filter
    keeps exactly the wrong bodies. Thickness is also the physically defensible
    criterion -- the smallest tool in the library is 5 mm across, so nothing it
    removes can be tens of microns thick in every cross-section.
    """
    bodies = solid.split(only_watertight=False)
    if len(bodies) <= 1:
        return solid

    total = sum(abs(body.volume) for body in bodies)
    if total <= 0:
        return solid

    kept = [
        body for body in bodies if float(np.min(body.extents)) >= min_thickness_mm
    ]
    if not kept:
        return solid
    if len(kept) == len(bodies):
        return solid
    if len(kept) == 1:
        return kept[0]
    merged = trimesh.boolean.boolean_manifold(kept, "union")
    return merged if merged is not None and not merged.is_empty else kept[0]


def largest_body(solid: trimesh.Trimesh) -> trimesh.Trimesh:
    """The single largest connected component of ``solid``.

    Blunter than :func:`denoise_difference`, and correct only when the operation
    is known to have removed one connected lump. Useful as a diagnostic upper
    bound on how much of a difference is signal.
    """
    bodies = solid.split(only_watertight=False)
    if len(bodies) <= 1:
        return solid
    return max(bodies, key=lambda body: abs(body.volume))


def voxel_iou(
    predicted: trimesh.Trimesh,
    truth: trimesh.Trimesh,
    pitch: float = 1.0,
) -> float:
    """Approximate IoU by voxel occupancy. Diagnostic fallback only.

    At the part scale here (200-500 mm) a 1 mm pitch resolves IoU to roughly
    1e-3, which straddles the top medium band rather than resolving it. Use
    :func:`compare_volumes` for anything that counts.
    """
    predicted_voxels = predicted.voxelized(pitch=pitch).fill()
    truth_voxels = truth.voxelized(pitch=pitch).fill()

    predicted_points = {tuple(p) for p in predicted_voxels.sparse_indices}
    origin_shift = np.round((truth_voxels.origin - predicted_voxels.origin) / pitch).astype(int)
    truth_points = {tuple(p + origin_shift) for p in truth_voxels.sparse_indices}

    intersection = len(predicted_points & truth_points)
    union = len(predicted_points | truth_points)
    return intersection / union if union else 0.0
