"""Atlas access for brain_viewer.

Each fetcher normalizes heterogeneous nilearn return types into a uniform
`AtlasData` dataclass. Deterministic atlases yield a 3D int volume; probabilistic
atlases yield a 4D float volume (last axis = region).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import nibabel as nib
import numpy as np

from . import config


@dataclass(frozen=True)
class AtlasLabel:
    index: int
    name: str


@dataclass
class AtlasData:
    id: str
    name: str
    volume: np.ndarray
    affine: np.ndarray
    labels: list[AtlasLabel]
    is_probabilistic: bool = False


# ---- Helpers ---------------------------------------------------------------


def _load_volume(maps_path_or_img) -> tuple[np.ndarray, np.ndarray]:
    if isinstance(maps_path_or_img, (str, Path)):
        img = nib.load(str(maps_path_or_img))
    else:
        img = maps_path_or_img
    return np.asarray(img.dataobj), img.affine


def _decode(label) -> str:
    if isinstance(label, bytes):
        return label.decode("utf-8", errors="replace")
    return str(label)


def _data_dir() -> str:
    return str(config.ATLAS_CACHE_DIR)


# ---- Fetchers --------------------------------------------------------------


def _labels_from_positional_list(raw_labels) -> list[AtlasLabel]:
    """Standard nilearn pattern: labels[i] (string) maps to volume value i; [0] is Background."""
    labels: list[AtlasLabel] = []
    for i, name in enumerate(raw_labels):
        decoded = _decode(name)
        if i == 0 or decoded.lower() == "background":
            continue
        labels.append(AtlasLabel(index=i, name=decoded))
    return labels


def _squeeze_if_4d_singleton(volume: np.ndarray) -> np.ndarray:
    if volume.ndim == 4 and volume.shape[-1] == 1:
        return volume[..., 0]
    return volume


def _fetch_harvard_oxford_cort() -> AtlasData:
    from nilearn import datasets

    ho = datasets.fetch_atlas_harvard_oxford(
        "cort-maxprob-thr25-2mm", data_dir=_data_dir(), symmetric_split=False
    )
    volume, affine = _load_volume(ho.maps)
    return AtlasData(
        id="harvard_oxford_cort",
        name="Harvard-Oxford Cortical (maxprob thr25, 2mm)",
        volume=_squeeze_if_4d_singleton(volume).astype(np.int32),
        affine=affine,
        labels=_labels_from_positional_list(ho.labels),
    )


def _fetch_harvard_oxford_sub() -> AtlasData:
    from nilearn import datasets

    ho = datasets.fetch_atlas_harvard_oxford(
        "sub-maxprob-thr25-2mm", data_dir=_data_dir(), symmetric_split=False
    )
    volume, affine = _load_volume(ho.maps)
    return AtlasData(
        id="harvard_oxford_sub",
        name="Harvard-Oxford Subcortical (maxprob thr25, 2mm)",
        volume=_squeeze_if_4d_singleton(volume).astype(np.int32),
        affine=affine,
        labels=_labels_from_positional_list(ho.labels),
    )


def _fetch_aal() -> AtlasData:
    from nilearn import datasets

    aal = datasets.fetch_atlas_aal(version="SPM12", data_dir=_data_dir())
    volume, affine = _load_volume(aal.maps)
    indices = [int(i) for i in aal.indices]
    labels = [AtlasLabel(index=idx, name=_decode(name)) for idx, name in zip(indices, aal.labels)]
    return AtlasData(
        id="aal",
        name="AAL (SPM12)",
        volume=_squeeze_if_4d_singleton(volume).astype(np.int32),
        affine=affine,
        labels=labels,
    )


def _fetch_destrieux() -> AtlasData:
    from nilearn import datasets

    d = datasets.fetch_atlas_destrieux_2009(data_dir=_data_dir())
    volume, affine = _load_volume(d.maps)
    return AtlasData(
        id="destrieux",
        name="Destrieux 2009 (cortical gyri/sulci)",
        volume=_squeeze_if_4d_singleton(volume).astype(np.int32),
        affine=affine,
        labels=_labels_from_positional_list(d.labels),
    )


def _fetch_juelich() -> AtlasData:
    from nilearn import datasets

    j = datasets.fetch_atlas_juelich("maxprob-thr25-2mm", data_dir=_data_dir())
    volume, affine = _load_volume(j.maps)
    return AtlasData(
        id="juelich",
        name="Jülich (maxprob thr25, 2mm)",
        volume=_squeeze_if_4d_singleton(volume).astype(np.int32),
        affine=affine,
        labels=_labels_from_positional_list(j.labels),
    )


def _fetch_msdl() -> AtlasData:
    from nilearn import datasets

    msdl = datasets.fetch_atlas_msdl(data_dir=_data_dir())
    volume, affine = _load_volume(msdl.maps)  # 4D probabilistic
    labels = [AtlasLabel(index=i, name=_decode(n)) for i, n in enumerate(msdl.labels)]
    return AtlasData(
        id="msdl",
        name="MSDL (probabilistic functional networks)",
        volume=volume.astype(np.float32),
        affine=affine,
        labels=labels,
        is_probabilistic=True,
    )


def _fetch_schaefer(n_rois: int) -> Callable[[], AtlasData]:
    def fetcher() -> AtlasData:
        from nilearn import datasets

        s = datasets.fetch_atlas_schaefer_2018(
            n_rois=n_rois, yeo_networks=7, resolution_mm=2, data_dir=_data_dir()
        )
        volume, affine = _load_volume(s.maps)
        return AtlasData(
            id=f"schaefer_{n_rois}_7",
            name=f"Schaefer 2018 ({n_rois} parcels, 7 networks, 2mm)",
            volume=_squeeze_if_4d_singleton(volume).astype(np.int32),
            affine=affine,
            labels=_labels_from_positional_list(s.labels),
        )

    return fetcher


def _fetch_yeo(n_networks: int) -> Callable[[], AtlasData]:
    def fetcher() -> AtlasData:
        from nilearn import datasets

        y = datasets.fetch_atlas_yeo_2011(
            data_dir=_data_dir(), n_networks=n_networks, thickness="thick"
        )
        volume, affine = _load_volume(y.maps)
        return AtlasData(
            id=f"yeo_{n_networks}",
            name=f"Yeo 2011 ({n_networks} networks, thick)",
            volume=_squeeze_if_4d_singleton(volume).astype(np.int32),
            affine=affine,
            labels=_labels_from_positional_list(y.labels),
        )

    return fetcher


def _fetch_glasser() -> AtlasData:
    """Load the Glasser HCP-MMP1.0 atlas projected to MNI152 volume space.

    This file is not bundled with nilearn. The user must place it at:
        ~/.cache/brain_viewer/atlases/glasser/HCP-MMP1_on_MNI152.nii.gz
    along with a CSV of labels at:
        ~/.cache/brain_viewer/atlases/glasser/HCP-MMP1_labels.csv
    (columns: index, name). Raises a friendly error otherwise.
    """
    root = config.ATLAS_CACHE_DIR / "glasser"
    vol_path = root / "HCP-MMP1_on_MNI152.nii.gz"
    labels_path = root / "HCP-MMP1_labels.csv"
    if not vol_path.exists() or not labels_path.exists():
        raise FileNotFoundError(
            "Glasser HCP-MMP1.0 files not found.\n"
            f"Expected:\n  {vol_path}\n  {labels_path}\n"
            "This atlas is not bundled with nilearn; see README.md for setup."
        )
    volume, affine = _load_volume(vol_path)
    labels: list[AtlasLabel] = []
    with labels_path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            idx = int(row["index"])
            if idx == 0:
                continue
            labels.append(AtlasLabel(index=idx, name=row["name"]))
    return AtlasData(
        id="glasser_hcp_mmp1",
        name="Glasser HCP-MMP1.0 (on MNI152)",
        volume=volume.astype(np.int32),
        affine=affine,
        labels=labels,
    )


# ---- Registry --------------------------------------------------------------


_REGISTRY: list[tuple[str, str, Callable[[], AtlasData]]] = [
    ("harvard_oxford_cort", "Harvard-Oxford Cortical",      _fetch_harvard_oxford_cort),
    ("harvard_oxford_sub",  "Harvard-Oxford Subcortical",   _fetch_harvard_oxford_sub),
    ("aal",                 "AAL (SPM12)",                  _fetch_aal),
    ("destrieux",           "Destrieux 2009",               _fetch_destrieux),
    ("juelich",             "Jülich cytoarchitectonic",     _fetch_juelich),
    ("schaefer_100_7",      "Schaefer 100 / 7 nets",        _fetch_schaefer(100)),
    ("schaefer_200_7",      "Schaefer 200 / 7 nets",        _fetch_schaefer(200)),
    ("schaefer_400_7",      "Schaefer 400 / 7 nets",        _fetch_schaefer(400)),
    ("schaefer_600_7",      "Schaefer 600 / 7 nets",        _fetch_schaefer(600)),
    ("schaefer_1000_7",     "Schaefer 1000 / 7 nets",       _fetch_schaefer(1000)),
    ("yeo_7",               "Yeo 7 networks",               _fetch_yeo(7)),
    ("yeo_17",              "Yeo 17 networks",              _fetch_yeo(17)),
    ("msdl",                "MSDL (probabilistic)",          _fetch_msdl),
    ("glasser_hcp_mmp1",    "Glasser HCP-MMP1.0 (manual)",  _fetch_glasser),
]

_FETCHERS: dict[str, Callable[[], AtlasData]] = {aid: fn for aid, _n, fn in _REGISTRY}
_DISPLAY_NAMES: dict[str, str] = {aid: name for aid, name, _fn in _REGISTRY}


@dataclass
class AtlasRegistry:
    _cache: dict[str, AtlasData] = field(default_factory=dict)

    def list_atlases(self) -> list[tuple[str, str]]:
        return [(aid, _DISPLAY_NAMES[aid]) for aid, _, _ in _REGISTRY]

    def get_atlas(self, atlas_id: str) -> AtlasData:
        if atlas_id not in _FETCHERS:
            raise KeyError(f"Unknown atlas id: {atlas_id!r}")
        cached = self._cache.get(atlas_id)
        if cached is not None:
            return cached
        atlas = _FETCHERS[atlas_id]()
        self._cache[atlas_id] = atlas
        return atlas
