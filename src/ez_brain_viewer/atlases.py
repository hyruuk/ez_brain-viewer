"""Atlas access for ezbv.

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


def _labels_from_lut(lut, index_col: str = "index", name_col: str = "name") -> list[AtlasLabel]:
    """Extract labels from a BIDS-style lookup-table DataFrame."""
    labels: list[AtlasLabel] = []
    cols = {str(c).lower(): c for c in lut.columns}
    idx_key = cols.get(index_col, next(iter(lut.columns)))
    name_key = cols.get(name_col)
    if name_key is None:
        for cand in ("name", "label", "region", "roi"):
            if cand in cols:
                name_key = cols[cand]
                break
    if name_key is None:
        name_key = list(lut.columns)[1] if len(lut.columns) > 1 else idx_key
    for _, row in lut.iterrows():
        try:
            idx = int(row[idx_key])
        except (ValueError, TypeError):
            continue
        if idx == 0:
            continue
        name = _decode(row[name_key])
        if name.lower() == "background":
            continue
        labels.append(AtlasLabel(index=idx, name=name))
    return labels


def _auto_labels_4d(n_components: int, prefix: str = "Component") -> list[AtlasLabel]:
    return [AtlasLabel(index=i, name=f"{prefix} {i + 1}") for i in range(n_components)]


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


def _fetch_talairach(level_name: str) -> Callable[[], AtlasData]:
    def fetcher() -> AtlasData:
        from nilearn import datasets

        t = datasets.fetch_atlas_talairach(level_name, data_dir=_data_dir())
        volume, affine = _load_volume(t.maps)
        return AtlasData(
            id=f"talairach_{level_name}",
            name=f"Talairach ({level_name})",
            volume=_squeeze_if_4d_singleton(volume).astype(np.int32),
            affine=affine,
            labels=_labels_from_positional_list(t.labels),
        )

    return fetcher


def _fetch_basc(resolution: int, version: str = "sym") -> Callable[[], AtlasData]:
    def fetcher() -> AtlasData:
        from nilearn import datasets

        b = datasets.fetch_atlas_basc_multiscale_2015(
            resolution=resolution, version=version, data_dir=_data_dir()
        )
        volume, affine = _load_volume(b.maps)
        return AtlasData(
            id=f"basc_{resolution}_{version}",
            name=f"BASC multiscale {resolution} ({version})",
            volume=_squeeze_if_4d_singleton(volume).astype(np.int32),
            affine=affine,
            labels=_labels_from_lut(b.lut),
        )

    return fetcher


def _fetch_pauli_2017(atlas_type: str) -> Callable[[], AtlasData]:
    def fetcher() -> AtlasData:
        from nilearn import datasets

        p = datasets.fetch_atlas_pauli_2017(atlas_type=atlas_type, data_dir=_data_dir())
        volume, affine = _load_volume(p.maps)
        is_prob = atlas_type == "probabilistic"
        if is_prob:
            n_components = int(volume.shape[-1]) if volume.ndim == 4 else 0
            # Pauli's `labels` are positional, one per component. Exclude Background if present.
            names = [_decode(n) for n in p.labels]
            labels = [
                AtlasLabel(index=i, name=names[i] if i < len(names) else f"Component {i + 1}")
                for i in range(n_components)
                if i >= len(names) or names[i].lower() != "background"
            ]
            vol_out = volume.astype(np.float32)
        else:
            labels = _labels_from_positional_list(p.labels)
            vol_out = _squeeze_if_4d_singleton(volume).astype(np.int32)
        return AtlasData(
            id=f"pauli_2017_{atlas_type}",
            name=f"Pauli 2017 subcortical ({atlas_type})",
            volume=vol_out,
            affine=affine,
            labels=labels,
            is_probabilistic=is_prob,
        )

    return fetcher


def _fetch_difumo(dimension: int, resolution_mm: int = 2) -> Callable[[], AtlasData]:
    def fetcher() -> AtlasData:
        from nilearn import datasets

        d = datasets.fetch_atlas_difumo(
            dimension=dimension, resolution_mm=resolution_mm, data_dir=_data_dir()
        )
        volume, affine = _load_volume(d.maps)
        # d.labels is a DataFrame with columns: "Component", "Difumo_names", "Yeo_networks7", …
        raw = d.labels
        try:
            if hasattr(raw, "columns"):
                names_col = next(
                    (c for c in raw.columns if "name" in str(c).lower()),
                    raw.columns[1] if len(raw.columns) > 1 else raw.columns[0],
                )
                names = [_decode(v) for v in raw[names_col].tolist()]
            else:
                names = [_decode(v) for v in raw]
        except Exception:
            names = []
        n_components = int(volume.shape[-1]) if volume.ndim == 4 else 0
        labels = [
            AtlasLabel(index=i, name=(names[i] if i < len(names) and names[i] else f"Component {i + 1}"))
            for i in range(n_components)
        ]
        return AtlasData(
            id=f"difumo_{dimension}",
            name=f"DiFuMo {dimension}",
            volume=volume.astype(np.float32),
            affine=affine,
            labels=labels,
            is_probabilistic=True,
        )

    return fetcher


def _fetch_smith_2009(dimension: int, resting: bool = True) -> Callable[[], AtlasData]:
    def fetcher() -> AtlasData:
        from nilearn import datasets

        s = datasets.fetch_atlas_smith_2009(
            dimension=dimension, resting=resting, data_dir=_data_dir()
        )
        volume, affine = _load_volume(s.maps)
        n = int(volume.shape[-1]) if volume.ndim == 4 else 0
        return AtlasData(
            id=f"smith_2009_{'rsn' if resting else 'brainmap'}_{dimension}",
            name=f"Smith 2009 {'RSN' if resting else 'BrainMap'} {dimension}",
            volume=volume.astype(np.float32),
            affine=affine,
            labels=_auto_labels_4d(n, prefix="Network"),
            is_probabilistic=True,
        )

    return fetcher


def _fetch_craddock_2012() -> AtlasData:
    from nilearn import datasets

    c = datasets.fetch_atlas_craddock_2012(data_dir=_data_dir())
    # Pick the spatial-homogeneity group-mean map (4D probabilistic).
    volume, affine = _load_volume(c.scorr_mean)
    n = int(volume.shape[-1]) if volume.ndim == 4 else 0
    return AtlasData(
        id="craddock_2012",
        name="Craddock 2012 (scorr_mean)",
        volume=volume.astype(np.float32),
        affine=affine,
        labels=_auto_labels_4d(n, prefix="Component"),
        is_probabilistic=True,
    )


def _fetch_allen_2011_rsn() -> AtlasData:
    from nilearn import datasets

    a = datasets.fetch_atlas_allen_2011(data_dir=_data_dir())
    volume, affine = _load_volume(a.rsn28)
    n = int(volume.shape[-1]) if volume.ndim == 4 else 0
    # `.networks` is list[list[str]] — a group-name per RSN plus subnet names;
    # flatten to single "Group: Name" per component via `.rsn_indices`.
    labels: list[AtlasLabel] = []
    rsn_indices = getattr(a, "rsn_indices", None)
    networks = getattr(a, "networks", None)
    if networks is not None and rsn_indices is not None:
        # rsn_indices: list of (group_name, [list of indices into the 28-stack])
        # Build a flat map index -> "group / subnet"
        name_map: dict[int, str] = {}
        try:
            for group_name, indices in rsn_indices:
                for j, idx in enumerate(indices):
                    name_map[int(idx)] = f"{_decode(group_name)}"
        except Exception:
            pass
        for i in range(n):
            labels.append(AtlasLabel(index=i, name=name_map.get(i, f"RSN {i + 1}")))
    else:
        labels = _auto_labels_4d(n, prefix="RSN")
    return AtlasData(
        id="allen_2011_rsn",
        name="Allen 2011 (28 RSNs)",
        volume=volume.astype(np.float32),
        affine=affine,
        labels=labels,
        is_probabilistic=True,
    )


def _fetch_glasser() -> AtlasData:
    """Load the Glasser HCP-MMP1.0 atlas projected to MNI152 volume space.

    This file is not bundled with nilearn. The user must place it at:
        ~/.cache/ezbv/atlases/glasser/HCP-MMP1_on_MNI152.nii.gz
    along with a CSV of labels at:
        ~/.cache/ezbv/atlases/glasser/HCP-MMP1_labels.csv
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


@dataclass(frozen=True)
class AtlasEntry:
    id: str
    category: str            # e.g. "Cortex", "Subcortex", "Cerebellum", …
    display_name: str        # plain name; final shown label adds a [Category] prefix
    fetcher: Callable[[], AtlasData]


_BUILTIN_REGISTRY: list[AtlasEntry] = [
    # Cortical (whole cortex or cortex-heavy)
    AtlasEntry("harvard_oxford_cort", "Cortex", "Harvard-Oxford Cortical", _fetch_harvard_oxford_cort),
    AtlasEntry("destrieux",           "Cortex", "Destrieux 2009",          _fetch_destrieux),
    AtlasEntry("juelich",             "Cortex", "Jülich cytoarchitectonic", _fetch_juelich),
    AtlasEntry("schaefer_100_7",      "Cortex", "Schaefer 100 / 7 nets",   _fetch_schaefer(100)),
    AtlasEntry("schaefer_200_7",      "Cortex", "Schaefer 200 / 7 nets",   _fetch_schaefer(200)),
    AtlasEntry("schaefer_400_7",      "Cortex", "Schaefer 400 / 7 nets",   _fetch_schaefer(400)),
    AtlasEntry("schaefer_600_7",      "Cortex", "Schaefer 600 / 7 nets",   _fetch_schaefer(600)),
    AtlasEntry("schaefer_1000_7",     "Cortex", "Schaefer 1000 / 7 nets",  _fetch_schaefer(1000)),
    AtlasEntry("yeo_7",               "Cortex", "Yeo 7 networks",          _fetch_yeo(7)),
    AtlasEntry("yeo_17",              "Cortex", "Yeo 17 networks",         _fetch_yeo(17)),
    AtlasEntry("talairach_lobe",      "Cortex", "Talairach (lobe)",        _fetch_talairach("lobe")),
    AtlasEntry("talairach_gyrus",     "Cortex", "Talairach (gyrus)",       _fetch_talairach("gyrus")),
    AtlasEntry("talairach_ba",        "Cortex", "Talairach (Brodmann)",    _fetch_talairach("ba")),
    AtlasEntry("allen_2011_rsn",      "Cortex", "Allen 2011 (28 RSNs)",    _fetch_allen_2011_rsn),
    # Subcortical
    AtlasEntry("harvard_oxford_sub",  "Subcortex", "Harvard-Oxford Subcortical", _fetch_harvard_oxford_sub),
    AtlasEntry("pauli_2017_det",      "Subcortex", "Pauli 2017 (deterministic)", _fetch_pauli_2017("deterministic")),
    AtlasEntry("pauli_2017_prob",     "Subcortex", "Pauli 2017 (probabilistic)", _fetch_pauli_2017("probabilistic")),
    # Whole brain (cortex + subcortex ± cerebellum)
    AtlasEntry("aal",                 "Whole brain", "AAL (SPM12)",        _fetch_aal),
    AtlasEntry("basc_64_sym",         "Whole brain", "BASC 64 (sym)",      _fetch_basc(64, "sym")),
    AtlasEntry("basc_122_sym",        "Whole brain", "BASC 122 (sym)",     _fetch_basc(122, "sym")),
    AtlasEntry("basc_444_sym",        "Whole brain", "BASC 444 (sym)",     _fetch_basc(444, "sym")),
    AtlasEntry("difumo_64",           "Whole brain", "DiFuMo 64",          _fetch_difumo(64)),
    AtlasEntry("difumo_256",          "Whole brain", "DiFuMo 256",         _fetch_difumo(256)),
    AtlasEntry("difumo_1024",         "Whole brain", "DiFuMo 1024",        _fetch_difumo(1024)),
    AtlasEntry("craddock_2012",       "Whole brain", "Craddock 2012",      _fetch_craddock_2012),
    # Functional networks
    AtlasEntry("msdl",                "Networks", "MSDL (probabilistic)",  _fetch_msdl),
    AtlasEntry("smith_2009_rsn_10",   "Networks", "Smith 2009 RSN-10",     _fetch_smith_2009(10, resting=True)),
    AtlasEntry("smith_2009_rsn_70",   "Networks", "Smith 2009 RSN-70",     _fetch_smith_2009(70, resting=True)),
    # Manual placeholder until external_atlases replaces it
    AtlasEntry("glasser_hcp_mmp1",    "Cortex", "Glasser HCP-MMP1.0 (manual)", _fetch_glasser),
]

_FETCHERS: dict[str, Callable[[], AtlasData]] = {e.id: e.fetcher for e in _BUILTIN_REGISTRY}
_ENTRIES: dict[str, AtlasEntry] = {e.id: e for e in _BUILTIN_REGISTRY}


_CATEGORY_ORDER = ["Cortex", "Subcortex", "Cerebellum", "Thalamus", "White matter", "Whole brain", "Networks", "Custom"]


def _category_sort_key(cat: str) -> tuple[int, str]:
    try:
        return (_CATEGORY_ORDER.index(cat), cat)
    except ValueError:
        return (len(_CATEGORY_ORDER), cat)


@dataclass
class AtlasRegistry:
    _cache: dict[str, AtlasData] = field(default_factory=dict)
    _external_fetchers: dict[str, Callable[[], AtlasData]] = field(default_factory=dict)
    _external_entries: dict[str, AtlasEntry] = field(default_factory=dict)

    def register_external(self, entries: list[AtlasEntry]) -> None:
        """Merge external (network-fetched) atlases into the registry."""
        for e in entries:
            self._external_fetchers[e.id] = e.fetcher
            self._external_entries[e.id] = e

    def list_atlases(self) -> list[tuple[str, str]]:
        from .custom_atlases import list_custom_atlases

        combined: list[AtlasEntry] = list(_BUILTIN_REGISTRY) + list(self._external_entries.values())
        combined.sort(key=lambda e: (_category_sort_key(e.category), e.display_name.lower()))

        result = [(e.id, f"[{e.category}] {e.display_name}") for e in combined]
        for s in list_custom_atlases():
            result.append((s.id, f"[Custom] {s.name}"))
        return result

    def get_atlas(self, atlas_id: str) -> AtlasData:
        cached = self._cache.get(atlas_id)
        if cached is not None:
            return cached

        if atlas_id in _FETCHERS:
            atlas = _FETCHERS[atlas_id]()
        elif atlas_id in self._external_fetchers:
            atlas = self._external_fetchers[atlas_id]()
        else:
            from .custom_atlases import fetch_custom_atlas, list_custom_atlases

            spec = next((s for s in list_custom_atlases() if s.id == atlas_id), None)
            if spec is None:
                raise KeyError(f"Unknown atlas id: {atlas_id!r}")
            atlas = fetch_custom_atlas(spec)

        self._cache[atlas_id] = atlas
        return atlas

    def invalidate(self, atlas_id: str) -> None:
        self._cache.pop(atlas_id, None)
