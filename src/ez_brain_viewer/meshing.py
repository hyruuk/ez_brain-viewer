"""Volume-label → triangle mesh conversion with on-disk caching.

Deterministic atlases: binary mask = (volume == label_index).
Probabilistic atlases: binary mask = (volume[..., label_index] >= threshold).

Vertices are transformed by the atlas affine into world coords (MNI152 mm)
so all ROI meshes and the template mesh share the same coordinate frame.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pyvista as pv
from skimage import measure

from . import config
from .atlases import AtlasData

MESH_CACHE_VERSION = 2  # v2: fix triangle winding for negative-det affines


class MeshBuilder:
    def __init__(self, cache_dir: Path = config.MESH_CACHE_DIR):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def label_to_mesh(
        self,
        atlas: AtlasData,
        label_index: int,
        threshold: float = 0.25,
        smoothing_iters: int = config.ROI_SMOOTH_ITERS,
    ) -> pv.PolyData:
        cache_path = self._cache_path(atlas.id, label_index, threshold, smoothing_iters)
        if cache_path.exists():
            mesh = pv.read(str(cache_path))
            if isinstance(mesh, pv.PolyData) and mesh.n_points > 0:
                return mesh

        mask = self._label_mask(atlas, label_index, threshold)
        if not np.any(mask):
            raise ValueError(
                f"Atlas {atlas.id!r} label {label_index} is empty under current threshold."
            )

        mesh = _mask_to_polydata(mask, atlas.affine, smoothing_iters)
        mesh.save(str(cache_path))
        return mesh

    def _cache_path(
        self, atlas_id: str, label_index: int, threshold: float, smoothing_iters: int
    ) -> Path:
        key = f"v{MESH_CACHE_VERSION}|{atlas_id}|{label_index}|{threshold:.4f}|{smoothing_iters}"
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / f"{atlas_id}_{label_index}_{digest}.vtp"

    @staticmethod
    def _label_mask(atlas: AtlasData, label_index: int, threshold: float) -> np.ndarray:
        if atlas.is_probabilistic:
            if atlas.volume.ndim != 4:
                raise ValueError(f"Probabilistic atlas {atlas.id!r} should have 4D volume.")
            return atlas.volume[..., label_index] >= threshold
        if atlas.volume.ndim != 3:
            raise ValueError(f"Deterministic atlas {atlas.id!r} should have 3D volume.")
        return atlas.volume == label_index


def _mask_to_polydata(
    mask: np.ndarray,
    affine: np.ndarray,
    smoothing_iters: int,
    level: float = 0.5,
) -> pv.PolyData:
    """Voxel volume → smoothed PolyData in world (affine-transformed) coords.

    For binary masks pass `level=0.5` (default). For intensity or probability
    volumes, pass an explicit threshold matching the data scale.
    """
    # Pad with zeros to guarantee a watertight surface at the volume boundary.
    dtype = np.float32 if mask.dtype.kind == "f" else np.uint8
    padded = np.pad(mask.astype(dtype), pad_width=1, mode="constant", constant_values=0)

    verts, faces, _normals, _vals = measure.marching_cubes(padded, level=level)
    # Undo the pad offset.
    verts = verts - 1.0

    # Voxel → world coords via the atlas affine.
    homog = np.c_[verts, np.ones(len(verts))]
    world = (affine @ homog.T).T[:, :3]

    # marching_cubes emits triangles with a fixed winding in voxel-index space.
    # If the affine's 3×3 has a negative determinant (very common in MNI152
    # volumes where X is flipped for radiological convention) the world-space
    # winding ends up inverted — outward-facing normals then point *inward*,
    # and backface-culling hides the near-camera triangles. Flip per-triangle
    # vertex order to restore correct outward normals in world coords.
    if np.linalg.det(affine[:3, :3]) < 0:
        faces = faces[:, ::-1]

    # pyvista face array: [3, i0, i1, i2, 3, i0, i1, i2, ...]
    pv_faces = np.hstack(
        [np.full((len(faces), 1), 3, dtype=np.int64), faces.astype(np.int64)]
    ).ravel()
    mesh = pv.PolyData(world, pv_faces)
    mesh = mesh.clean()
    if smoothing_iters > 0 and mesh.n_points > 0:
        mesh = mesh.smooth_taubin(n_iter=smoothing_iters, pass_band=0.05)
    return mesh
