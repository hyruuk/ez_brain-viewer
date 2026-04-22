"""Template (glass-brain) surface meshes.

All meshes are returned in MNI152 world coordinates (mm). fsaverage meshes live in
FreeSurfer's native coord system, which is linearly close to MNI152 — acceptable
for stylized figures, with a documented mm-scale drift vs. volume atlases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import pyvista as pv

from . import config
from .meshing import _mask_to_polydata


@dataclass
class TemplateMesh:
    id: str
    name: str
    mesh: pv.PolyData


# ---- Builders --------------------------------------------------------------


def _build_mni152_brain() -> pv.PolyData:
    from nilearn import datasets

    img = datasets.load_mni152_brain_mask()
    data = np.asarray(img.dataobj).astype(bool)
    return _mask_to_polydata(data, img.affine, smoothing_iters=config.TEMPLATE_SMOOTH_ITERS)


def _fsaverage_combined(which: str) -> pv.PolyData:
    """Load fsaverage LH+RH of the given surface type ('pial', 'white', 'infl')."""
    from nilearn import datasets, surface

    fs = datasets.fetch_surf_fsaverage("fsaverage6", data_dir=str(config.ATLAS_CACHE_DIR))
    key_lh = f"{which}_left"
    key_rh = f"{which}_right"
    lh_coords, lh_faces = surface.load_surf_mesh(fs[key_lh])
    rh_coords, rh_faces = surface.load_surf_mesh(fs[key_rh])

    n_lh = len(lh_coords)
    coords = np.vstack([lh_coords, rh_coords])
    faces = np.vstack([lh_faces, rh_faces + n_lh])

    pv_faces = np.hstack(
        [np.full((len(faces), 1), 3, dtype=np.int64), faces.astype(np.int64)]
    ).ravel()
    mesh = pv.PolyData(coords, pv_faces).clean()
    return mesh


def _build_fsaverage_pial() -> pv.PolyData:
    return _fsaverage_combined("pial")


def _build_fsaverage_white() -> pv.PolyData:
    return _fsaverage_combined("white")


def _build_fsaverage_inflated() -> pv.PolyData:
    return _fsaverage_combined("infl")


_BUILDERS: dict[str, tuple[str, Callable[[], pv.PolyData]]] = {
    "mni152_brain":       ("MNI152 brain (volume mask)", _build_mni152_brain),
    "fsaverage_pial":     ("fsaverage pial (cortex)",    _build_fsaverage_pial),
    "fsaverage_white":    ("fsaverage white (cortex)",   _build_fsaverage_white),
    "fsaverage_inflated": ("fsaverage inflated",          _build_fsaverage_inflated),
}


# ---- Registry --------------------------------------------------------------


@dataclass
class TemplateRegistry:
    cache_dir: Path = config.TEMPLATE_CACHE_DIR
    _cache: dict[str, TemplateMesh] = field(default_factory=dict)

    def list_templates(self) -> list[tuple[str, str]]:
        return [(tid, name) for tid, (name, _) in _BUILDERS.items()]

    def get_template(self, template_id: str) -> TemplateMesh:
        if template_id not in _BUILDERS:
            raise KeyError(f"Unknown template id: {template_id!r}")
        cached = self._cache.get(template_id)
        if cached is not None:
            return cached

        disk_path = self.cache_dir / f"{template_id}.vtp"
        if disk_path.exists():
            mesh = pv.read(str(disk_path))
            if isinstance(mesh, pv.PolyData) and mesh.n_points > 0:
                result = TemplateMesh(
                    id=template_id,
                    name=_BUILDERS[template_id][0],
                    mesh=mesh,
                )
                self._cache[template_id] = result
                return result

        name, builder = _BUILDERS[template_id]
        mesh = builder()
        mesh.save(str(disk_path))
        result = TemplateMesh(id=template_id, name=name, mesh=mesh)
        self._cache[template_id] = result
        return result
