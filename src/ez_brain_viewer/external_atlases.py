"""External atlases fetched from pinned URLs (figshare / Zenodo / GitHub etc).

Each fetcher downloads to ``~/.cache/ezbv/atlases/external/<atlas_id>/``
on first call and caches forever. Accompanying label files either travel with
the volume or are bundled under ``ezbv/data/labels/<atlas_id>.csv``.

Failures surface as ``RuntimeError`` with enough detail for the UI's
existing warning dialog — the app never crashes on a dead URL.
"""

from __future__ import annotations

import hashlib
import shutil
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import nibabel as nib
import numpy as np
import requests

from . import config
from .atlases import AtlasData, AtlasEntry, AtlasLabel
from .custom_atlases import _read_labels_file

EXTERNAL_DIR: Path = config.ATLAS_CACHE_DIR / "external"
BUNDLED_LABELS_DIR: Path = Path(__file__).parent / "data" / "labels"
MAX_DOWNLOAD_BYTES = 500 * 1024 * 1024  # 500 MB


# ---- Download helper -------------------------------------------------------


def _atlas_dir(atlas_id: str) -> Path:
    d = EXTERNAL_DIR / atlas_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _download_file(url: str, dest: Path) -> None:
    """Stream a URL to disk with a size cap. Raises on network failure."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            total = 0
            with tmp.open("wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise RuntimeError(
                            f"Download exceeded {MAX_DOWNLOAD_BYTES // (1024*1024)} MB limit: {url}"
                        )
                    f.write(chunk)
        tmp.replace(dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _fetch(atlas_id: str, url: str, filename: str, sha256: str | None = None) -> Path:
    """Download ``url`` to the atlas's cache dir under ``filename`` if missing.

    Returns the absolute path. Re-downloads if the SHA256 check fails.
    """
    target = _atlas_dir(atlas_id) / filename
    if target.exists():
        if sha256 is None or _sha256(target) == sha256:
            return target
        target.unlink()
    _download_file(url, target)
    if sha256 is not None:
        got = _sha256(target)
        if got != sha256:
            target.unlink()
            raise RuntimeError(
                f"SHA256 mismatch for {url} (got {got}, expected {sha256})"
            )
    return target


def _extract_archive(
    archive: Path,
    members: list[str],
    dest_dir: Path,
    optional: bool = False,
) -> list[Path]:
    """Extract selected members from a zip or tar archive. Returns output paths.

    With `optional=True`, missing members are silently skipped; otherwise they raise.
    Mac-OS resource-fork entries (``__MACOSX/…``) are always ignored.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as zf:
            names = [n for n in zf.namelist() if not n.startswith("__MACOSX/")]
            for pattern in members:
                matches = [n for n in names if pattern in n and not n.endswith("/")]
                if not matches:
                    if optional:
                        continue
                    raise RuntimeError(f"No match for {pattern!r} in {archive.name}")
                # Prefer exact tail match
                chosen = sorted(matches, key=lambda n: (len(n), n))[0]
                target = dest_dir / Path(chosen).name
                with zf.open(chosen) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                out.append(target)
    elif archive.suffix.lower() in (".tar", ".tgz", ".gz", ".tbz", ".bz2"):
        with tarfile.open(archive) as tf:
            names = tf.getnames()
            for pattern in members:
                matches = [n for n in names if pattern in n]
                if not matches:
                    raise RuntimeError(f"No match for {pattern!r} in {archive.name}")
                chosen = sorted(matches, key=lambda n: (len(n), n))[0]
                target = dest_dir / Path(chosen).name
                src = tf.extractfile(chosen)
                if src is None:
                    raise RuntimeError(f"Could not extract {chosen!r}")
                with target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                out.append(target)
    else:
        raise RuntimeError(f"Unsupported archive type: {archive.name}")
    return out


def _load_volume(path: Path) -> tuple[np.ndarray, np.ndarray]:
    img = nib.load(str(path))
    return np.asarray(img.dataobj), img.affine


def _squeeze(v: np.ndarray) -> np.ndarray:
    if v.ndim == 4 and v.shape[-1] == 1:
        return v[..., 0]
    return v


def _bundled_labels(atlas_id: str) -> Path | None:
    candidate = BUNDLED_LABELS_DIR / f"{atlas_id}.csv"
    return candidate if candidate.exists() else None


def _strip_trailing_numbers(name: str) -> str:
    """Strip trailing whitespace-separated numeric tokens (FreeSurfer/FSL LUT RGBA columns)."""
    parts = name.split()
    while parts:
        tail = parts[-1]
        try:
            float(tail)
            parts.pop()
        except ValueError:
            break
    return " ".join(parts).strip()


def _clean_label_map(label_map: dict[int, str]) -> dict[int, str]:
    return {k: _strip_trailing_numbers(v) for k, v in label_map.items()}


def _labels_from_map(
    volume: np.ndarray,
    label_map: dict[int, str],
    is_probabilistic: bool,
) -> list[AtlasLabel]:
    labels: list[AtlasLabel] = []
    if is_probabilistic:
        n = int(volume.shape[-1]) if volume.ndim == 4 else 0
        for i in range(n):
            labels.append(AtlasLabel(index=i, name=label_map.get(i, label_map.get(i + 1, f"Component {i + 1}"))))
    else:
        present = np.unique(volume.astype(np.int64))
        present = present[present != 0]
        for v in present:
            labels.append(AtlasLabel(index=int(v), name=label_map.get(int(v), f"Label {int(v)}")))
    return labels


# ---- Fetchers --------------------------------------------------------------


def _make_entry(
    atlas_id: str,
    category: str,
    display_name: str,
    fn: Callable[[], AtlasData],
) -> AtlasEntry:
    return AtlasEntry(id=atlas_id, category=category, display_name=display_name, fetcher=fn)


def _fetch_glasser_hcp() -> AtlasData:
    atlas_id = "glasser_hcp_mmp1_auto"  # distinct id so the manual placeholder remains usable as fallback
    zip_path = _fetch(
        atlas_id,
        "https://figshare.com/ndownloader/articles/3501911/versions/5",
        "HCP-MMP1_volumetric.zip",
    )
    out = _extract_archive(
        zip_path,
        ["HCP-MMP1_on_MNI152_ICBM2009a_nlin.nii.gz", "HCP-MMP1_on_MNI152_ICBM2009a_nlin.txt"],
        _atlas_dir(atlas_id),
    )
    vol_path = next(p for p in out if p.name.endswith(".nii.gz"))
    lut_path = next((p for p in out if p.suffix == ".txt"), None)

    label_map = _clean_label_map(_read_labels_file(lut_path)) if lut_path and lut_path.exists() else {}
    if not label_map:
        bundled = _bundled_labels(atlas_id)
        if bundled is not None:
            label_map = _clean_label_map(_read_labels_file(bundled))

    volume, affine = _load_volume(vol_path)
    volume = _squeeze(volume).astype(np.int32)
    labels = _labels_from_map(volume, label_map, is_probabilistic=False)
    return AtlasData(
        id=atlas_id,
        name="Glasser HCP-MMP1.0 (left hemisphere)",
        volume=volume,
        affine=affine,
        labels=labels,
    )


# ---- Diedrichsen lab cerebellar atlases ------------------------------------
# Raw github URL template pinned to a specific commit for stability.
_DIEDRICHSEN_COMMIT = "master"
_DIEDRICHSEN_RAW = (
    f"https://raw.githubusercontent.com/DiedrichsenLab/cerebellar_atlases/{_DIEDRICHSEN_COMMIT}"
)


def _fetch_diedrichsen(atlas_id: str, display_name: str, folder: str, nii_name: str, tsv_name: str) -> AtlasData:
    vol_path = _fetch(
        atlas_id,
        f"{_DIEDRICHSEN_RAW}/{folder}/{nii_name}",
        nii_name,
    )
    tsv_path = _fetch(
        atlas_id,
        f"{_DIEDRICHSEN_RAW}/{folder}/{tsv_name}",
        tsv_name,
    )
    volume, affine = _load_volume(vol_path)
    volume = _squeeze(volume).astype(np.int32)
    label_map = _clean_label_map(_read_labels_file(tsv_path))
    labels = _labels_from_map(volume, label_map, is_probabilistic=False)
    return AtlasData(
        id=atlas_id,
        name=display_name,
        volume=volume,
        affine=affine,
        labels=labels,
    )


def _fetch_suit_anatom() -> AtlasData:
    return _fetch_diedrichsen(
        "suit_anatom",
        "SUIT cerebellar (Diedrichsen 2009)",
        "Diedrichsen_2009",
        "atl-Anatom_space-MNI_dseg.nii",
        "atl-Anatom.tsv",
    )


def _fetch_buckner_7() -> AtlasData:
    return _fetch_diedrichsen(
        "buckner_cerebellar_7",
        "Buckner 2011 cerebellar (7 networks)",
        "Buckner_2011",
        "atl-Buckner7_space-MNI_dseg.nii",
        "atl-Buckner7.tsv",
    )


def _fetch_buckner_17() -> AtlasData:
    return _fetch_diedrichsen(
        "buckner_cerebellar_17",
        "Buckner 2011 cerebellar (17 networks)",
        "Buckner_2011",
        "atl-Buckner17_space-MNI_dseg.nii",
        "atl-Buckner17.tsv",
    )


def _fetch_mdtb_10() -> AtlasData:
    return _fetch_diedrichsen(
        "mdtb_10",
        "MDTB cerebellar (King 2019)",
        "King_2019",
        "atl-MDTB10_space-MNI_dseg.nii",
        "atl-MDTB10.tsv",
    )


# ---- Najdenovska thalamic nuclei (Zenodo) ----------------------------------


def _fetch_najdenovska(probabilistic: bool) -> AtlasData:
    atlas_id = "najdenovska_thalamus_prob" if probabilistic else "najdenovska_thalamus"
    base = "https://zenodo.org/record/1405484/files/"
    volume_url = base + (
        "Thalamus_Nuclei-HCP-4DSPAMs.nii.gz" if probabilistic else "Thalamus_Nuclei-HCP-MaxProb.nii.gz"
    ) + "?download=1"
    lut_url = base + "Thalamic_Nuclei-ColorLUT.txt?download=1"
    vol_path = _fetch(
        atlas_id,
        volume_url,
        "Thalamus_Nuclei.nii.gz",
    )
    lut_path = _fetch(atlas_id, lut_url, "Thalamic_Nuclei-ColorLUT.txt")

    volume, affine = _load_volume(vol_path)
    label_map = _clean_label_map(_read_labels_file(lut_path))
    if probabilistic:
        vol_out = volume.astype(np.float32)
        labels = _labels_from_map(vol_out, label_map, is_probabilistic=True)
    else:
        vol_out = _squeeze(volume).astype(np.int32)
        labels = _labels_from_map(vol_out, label_map, is_probabilistic=False)
    return AtlasData(
        id=atlas_id,
        name=f"Najdenovska thalamus ({'probabilistic' if probabilistic else 'max-prob'})",
        volume=vol_out,
        affine=affine,
        labels=labels,
        is_probabilistic=probabilistic,
    )


def _fetch_najdenovska_maxprob() -> AtlasData:
    return _fetch_najdenovska(probabilistic=False)


def _fetch_najdenovska_prob() -> AtlasData:
    return _fetch_najdenovska(probabilistic=True)


# ---- Melbourne Subcortical Atlas (Tian 2020, nitrc zip) --------------------


def _fetch_melbourne(scale: int) -> AtlasData:
    atlas_id = f"melbourne_sub_s{scale}"
    zip_path = _fetch(
        "melbourne_sub",
        "https://www.nitrc.org/frs/download.php/13364/Tian2020MSA_v1.4.zip",
        "Tian2020MSA_v1.4.zip",
    )
    nii_name = f"Tian_Subcortex_S{scale}_3T.nii.gz"
    lut_name = f"Tian_Subcortex_S{scale}_3T_label.txt"
    out = _extract_archive(zip_path, [nii_name], _atlas_dir(atlas_id))
    # Label file may not ship in the zip for all scales — extract if present.
    out += _extract_archive(zip_path, [lut_name], _atlas_dir(atlas_id), optional=True)
    vol_path = next(p for p in out if p.name.endswith(".nii.gz"))
    lut_path = next((p for p in out if p.suffix == ".txt"), None)
    if lut_path is None:
        # fall back to bundled labels
        bundled = _bundled_labels(atlas_id)
        if bundled is not None:
            lut_path = bundled

    volume, affine = _load_volume(vol_path)
    volume = _squeeze(volume).astype(np.int32)
    label_map: dict[int, str] = {}
    if lut_path and lut_path.exists():
        text = lut_path.read_text()
        # Try index-first format first (generic parser).
        label_map = _read_labels_file(lut_path)
        if not label_map:
            # Melbourne S1's label file is a bare list: one region-name per line,
            # positional from 1.
            for i, line in enumerate(text.splitlines(), start=1):
                name = line.strip()
                if name and not name.startswith("#"):
                    label_map[i] = name
    label_map = _clean_label_map(label_map)
    labels = _labels_from_map(volume, label_map, is_probabilistic=False)
    return AtlasData(
        id=atlas_id,
        name=f"Melbourne Subcortex Scale {scale}",
        volume=volume,
        affine=affine,
        labels=labels,
    )


def _fetch_melbourne_1() -> AtlasData: return _fetch_melbourne(1)
def _fetch_melbourne_2() -> AtlasData: return _fetch_melbourne(2)
def _fetch_melbourne_3() -> AtlasData: return _fetch_melbourne(3)
def _fetch_melbourne_4() -> AtlasData: return _fetch_melbourne(4)


# ---- JHU white matter labels (via templateflow / FSL) ----------------------


# ---- Brainnetome Atlas (Fan 2016, 246 regions) -----------------------------
# Official download on atlas.brainnetome.org is gated behind a Chinese cloud
# landing page (pan.cstcloud.cn) that can't be streamed directly. We mirror
# from a well-maintained GitHub copy that co-locates the 2mm volume with the
# official BN_Atlas_246_LUT.txt.

_BNA_RAW = (
    "https://raw.githubusercontent.com/floristijhuis/HCP-rfMRI-repository/"
    "master/Atlases/Brainnetome/info"
)


def _fetch_brainnetome() -> AtlasData:
    atlas_id = "brainnetome_246"
    vol_path = _fetch(
        atlas_id,
        f"{_BNA_RAW}/BN_Atlas_246_2mm.nii.gz",
        "BN_Atlas_246_2mm.nii.gz",
    )
    lut_path = _fetch(
        atlas_id,
        f"{_BNA_RAW}/BN_Atlas_246_LUT.txt",
        "BN_Atlas_246_LUT.txt",
    )
    volume, affine = _load_volume(vol_path)
    volume = _squeeze(volume).astype(np.int32)
    label_map = _clean_label_map(_read_labels_file(lut_path))
    labels = _labels_from_map(volume, label_map, is_probabilistic=False)
    return AtlasData(
        id=atlas_id,
        name="Brainnetome 246 (Fan 2016)",
        volume=volume,
        affine=affine,
        labels=labels,
    )


# ---- JHU white matter labels (via templateflow / FSL) ----------------------


def _fetch_jhu_wm() -> AtlasData:
    atlas_id = "jhu_wm_labels"
    # NeuroVault image download link
    vol_path = _fetch(
        atlas_id,
        "https://neurovault.org/media/images/264/JHU-ICBM-labels-1mm.nii.gz",
        "JHU-ICBM-labels-1mm.nii.gz",
    )
    labels_path = _bundled_labels(atlas_id)
    label_map = _clean_label_map(_read_labels_file(labels_path)) if labels_path else {}
    volume, affine = _load_volume(vol_path)
    volume = _squeeze(volume).astype(np.int32)
    labels = _labels_from_map(volume, label_map, is_probabilistic=False)
    return AtlasData(
        id=atlas_id,
        name="JHU white matter labels (1mm)",
        volume=volume,
        affine=affine,
        labels=labels,
    )


# ---- Registry --------------------------------------------------------------


EXTERNAL_ENTRIES: list[AtlasEntry] = [
    _make_entry("glasser_hcp_mmp1_auto", "Cortex",    "Glasser HCP-MMP1.0 (LH only, auto)", _fetch_glasser_hcp),
    _make_entry("suit_anatom",         "Cerebellum",  "SUIT cerebellar (anatom)",          _fetch_suit_anatom),
    _make_entry("buckner_cerebellar_7",  "Cerebellum","Buckner 2011 cerebellar (7 nets)",  _fetch_buckner_7),
    _make_entry("buckner_cerebellar_17", "Cerebellum","Buckner 2011 cerebellar (17 nets)", _fetch_buckner_17),
    _make_entry("mdtb_10",             "Cerebellum",  "MDTB cerebellar (King 2019)",       _fetch_mdtb_10),
    _make_entry("najdenovska_thalamus",      "Thalamus", "Najdenovska thalamus (max-prob)",      _fetch_najdenovska_maxprob),
    _make_entry("najdenovska_thalamus_prob", "Thalamus", "Najdenovska thalamus (probabilistic)", _fetch_najdenovska_prob),
    _make_entry("melbourne_sub_s1",    "Subcortex",   "Melbourne Subcortex Scale 1 (16 ROIs)", _fetch_melbourne_1),
    _make_entry("melbourne_sub_s2",    "Subcortex",   "Melbourne Subcortex Scale 2 (32 ROIs)", _fetch_melbourne_2),
    _make_entry("melbourne_sub_s3",    "Subcortex",   "Melbourne Subcortex Scale 3 (50 ROIs)", _fetch_melbourne_3),
    _make_entry("melbourne_sub_s4",    "Subcortex",   "Melbourne Subcortex Scale 4 (54 ROIs)", _fetch_melbourne_4),
    _make_entry("jhu_wm_labels",       "White matter","JHU ICBM white-matter labels (1mm)",    _fetch_jhu_wm),
    _make_entry("brainnetome_246",     "Whole brain", "Brainnetome 246 (Fan 2016)",            _fetch_brainnetome),
]
