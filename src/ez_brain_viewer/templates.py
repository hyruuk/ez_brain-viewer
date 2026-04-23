"""Template (glass-brain) surface meshes.

All meshes are returned in MNI152 world coordinates (mm). fsaverage meshes live in
FreeSurfer's native coord system, which is linearly close to MNI152 — acceptable
for stylized figures, with a documented mm-scale drift vs. volume atlases.

Cache filenames include TEMPLATE_CACHE_VERSION so a bump forces a rebuild.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import pyvista as pv

from . import config
from .meshing import _mask_to_polydata


TEMPLATE_CACHE_VERSION = 5  # v5: fix triangle winding for negative-det affines
INFLATED_MIDLINE_GAP_MM = 20.0  # total gap between LH and RH medial walls on inflated


@dataclass
class TemplateMesh:
    id: str
    name: str
    mesh: pv.PolyData


# ---- Builders --------------------------------------------------------------


def _build_mni152_detailed() -> pv.PolyData:
    """Detailed MNI152 brain surface with gyri — iso-surface of the GM probability map.

    The GM probability template has clear contrast between cortical ribbon (high
    probability) and sulcal CSF / background (low probability), so marching-cubes
    at ~0.5 traces a surface that shows gyri faithfully. Includes subcortical GM,
    so subcortical ROIs still sit inside the shell.
    """
    from nilearn import datasets

    img = datasets.load_mni152_gm_template(resolution=1)
    data = np.asarray(img.dataobj).astype(np.float32)
    return _mask_to_polydata(data, img.affine, smoothing_iters=5, level=0.5)


def _load_ho_sub_image():
    """Return the Harvard-Oxford sub Nifti1Image (handling path-vs-image ambiguity)."""
    import nibabel as nib
    from nilearn import datasets

    ho = datasets.fetch_atlas_harvard_oxford(
        "sub-maxprob-thr25-2mm",
        data_dir=str(config.ATLAS_CACHE_DIR),
        symmetric_split=False,
    )
    maps = ho.maps
    if isinstance(maps, (str, Path)):
        return nib.load(str(maps))
    return maps  # already a Nifti1Image


def _ho_sub_label_index(needle: str) -> int | None:
    """Return the Harvard-Oxford sub label index whose name contains `needle`."""
    from nilearn import datasets

    ho = datasets.fetch_atlas_harvard_oxford(
        "sub-maxprob-thr25-2mm",
        data_dir=str(config.ATLAS_CACHE_DIR),
        symmetric_split=False,
    )
    for i, name in enumerate(ho.labels):
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="replace")
        if needle.lower() in str(name).lower():
            return i
    return None


def _build_mni152_subcortex() -> pv.PolyData:
    """Subcortical-GM envelope — union of Pauli 2017 deterministic ROIs.

    Harvard-Oxford sub includes "Cerebral White Matter" and "Cerebral Cortex"
    labels that span most of each hemisphere, so using it as a shell gives
    a full-brain blob. Pauli 2017 is all-GM-only (thalamus / striatum /
    pallidum / hippocampus / amygdala / accumbens) — a proper subcortex shell.
    """
    import nibabel as nib
    from nilearn import datasets

    p = datasets.fetch_atlas_pauli_2017(atlas_type="deterministic", data_dir=str(config.ATLAS_CACHE_DIR))
    img = nib.load(str(p.maps)) if isinstance(p.maps, (str, Path)) else p.maps
    data = np.asarray(img.dataobj)
    mask = data > 0
    return _mask_to_polydata(mask, img.affine, smoothing_iters=config.TEMPLATE_SMOOTH_ITERS)


def _build_mni152_brainstem() -> pv.PolyData:
    """Brain-Stem envelope — just the Harvard-Oxford sub Brain-Stem label."""
    idx = _ho_sub_label_index("brain-stem") or _ho_sub_label_index("brainstem")
    if idx is None:
        raise RuntimeError("Could not find a Brain-Stem label in Harvard-Oxford sub.")
    img = _load_ho_sub_image()
    data = np.asarray(img.dataobj)
    mask = data == idx
    return _mask_to_polydata(mask, img.affine, smoothing_iters=config.TEMPLATE_SMOOTH_ITERS)


def _build_mni152_cerebellum() -> pv.PolyData:
    """Union of SUIT anatomic cerebellar labels."""
    from .external_atlases import _fetch_suit_anatom

    atlas = _fetch_suit_anatom()
    mask = atlas.volume > 0
    return _mask_to_polydata(mask, atlas.affine, smoothing_iters=config.TEMPLATE_SMOOTH_ITERS)


def _build_mni152_brain_mask() -> pv.PolyData:
    """Simple MNI152 brain-mask envelope — chunky but encloses all subcortex."""
    from nilearn import datasets

    img = datasets.load_mni152_brain_mask()
    data = np.asarray(img.dataobj).astype(bool)
    return _mask_to_polydata(data, img.affine, smoothing_iters=config.TEMPLATE_SMOOTH_ITERS)


def _fsaverage_combined(which: str) -> pv.PolyData:
    """Load fsaverage LH+RH of the given surface type ('pial', 'white', 'infl')."""
    from nilearn import datasets, surface

    fs = datasets.fetch_surf_fsaverage("fsaverage6", data_dir=str(config.ATLAS_CACHE_DIR))
    lh_coords, lh_faces = surface.load_surf_mesh(fs[f"{which}_left"])
    rh_coords, rh_faces = surface.load_surf_mesh(fs[f"{which}_right"])

    if which == "infl":
        # Raw fsaverage inflated hemispheres extend past the mid-sagittal plane
        # (LH reaches into X>0, RH reaches into X<0), so concatenated they overlap
        # badly. Translate each so its medial-most X lands a fixed distance from
        # midline — guarantees a clean gap independent of raw extents.
        lh_coords = lh_coords.copy()
        rh_coords = rh_coords.copy()
        half_gap = INFLATED_MIDLINE_GAP_MM / 2.0
        lh_coords[:, 0] -= lh_coords[:, 0].max() + half_gap
        rh_coords[:, 0] += half_gap - rh_coords[:, 0].min()

    n_lh = len(lh_coords)
    coords = np.vstack([lh_coords, rh_coords])
    faces = np.vstack([lh_faces, rh_faces + n_lh])

    pv_faces = np.hstack(
        [np.full((len(faces), 1), 3, dtype=np.int64), faces.astype(np.int64)]
    ).ravel()
    return pv.PolyData(coords, pv_faces).clean()


def _build_fsaverage_pial() -> pv.PolyData:
    return _fsaverage_combined("pial")


def _build_fsaverage_white() -> pv.PolyData:
    return _fsaverage_combined("white")


def _build_fsaverage_inflated() -> pv.PolyData:
    return _fsaverage_combined("infl")


_BUILDERS: dict[str, tuple[str, Callable[[], pv.PolyData]]] = {
    "mni152_detailed":    ("MNI152 (detailed, gyri)",      _build_mni152_detailed),
    "mni152_brain":       ("MNI152 brain mask (simple)",   _build_mni152_brain_mask),
    "mni152_subcortex":   ("MNI152 subcortex (HO union)",  _build_mni152_subcortex),
    "mni152_cerebellum":  ("MNI152 cerebellum (SUIT union)", _build_mni152_cerebellum),
    "mni152_brainstem":   ("MNI152 brainstem",             _build_mni152_brainstem),
    "fsaverage_pial":     ("fsaverage pial",               _build_fsaverage_pial),
    "fsaverage_white":    ("fsaverage white",              _build_fsaverage_white),
    "fsaverage_inflated": ("fsaverage inflated",           _build_fsaverage_inflated),
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

        disk_path = self.cache_dir / f"{template_id}_v{TEMPLATE_CACHE_VERSION}.vtp"
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
