"""User-supplied custom atlases.

A small JSON index at ``~/.cache/ezbv/atlases/custom/index.json`` tracks
registered custom atlases. Each spec points at a cached NIfTI volume and an
optional labels CSV/TSV/TXT. Adding a custom atlas downloads-or-copies the
source files into that dir so it keeps working offline afterwards.

Atlas IDs are prefixed ``custom__`` so they can't collide with nilearn-provided
atlas IDs.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import nibabel as nib
import numpy as np
import requests

from . import config
from .atlases import AtlasData, AtlasLabel

CUSTOM_DIR: Path = config.ATLAS_CACHE_DIR / "custom"
INDEX_PATH: Path = CUSTOM_DIR / "index.json"
CUSTOM_ID_PREFIX = "custom__"
MAX_DOWNLOAD_BYTES = 500 * 1024 * 1024  # 500 MB


@dataclass
class CustomAtlasSpec:
    id: str
    name: str
    volume_filename: str
    labels_filename: str | None
    is_probabilistic: bool

    def volume_path(self) -> Path:
        return CUSTOM_DIR / self.id / self.volume_filename

    def labels_path(self) -> Path | None:
        if not self.labels_filename:
            return None
        return CUSTOM_DIR / self.id / self.labels_filename


# ---- Index persistence -----------------------------------------------------


def _load_index() -> list[CustomAtlasSpec]:
    if not INDEX_PATH.exists():
        return []
    try:
        raw = json.loads(INDEX_PATH.read_text())
    except Exception:
        return []
    specs: list[CustomAtlasSpec] = []
    for entry in raw:
        try:
            specs.append(CustomAtlasSpec(**entry))
        except Exception:
            continue
    return specs


def _save_index(specs: Iterable[CustomAtlasSpec]) -> None:
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps([asdict(s) for s in specs], indent=2))


def list_custom_atlases() -> list[CustomAtlasSpec]:
    """All custom atlases currently registered on disk."""
    return _load_index()


# ---- Adding / removing -----------------------------------------------------


def add_custom_atlas(
    display_name: str,
    volume_source: str,
    labels_source: str | None = None,
) -> CustomAtlasSpec:
    """Register a new custom atlas. `volume_source` and `labels_source` can be
    a local file path or an HTTP(S) URL.

    Raises `ValueError` on malformed input or `RuntimeError` on download failure.
    """
    display_name = display_name.strip()
    if not display_name:
        raise ValueError("Display name cannot be empty.")
    volume_source = volume_source.strip()
    if not volume_source:
        raise ValueError("Volume source cannot be empty.")

    slug = _slugify(display_name)
    atlas_id = f"{CUSTOM_ID_PREFIX}{slug}"
    # Disambiguate if the same name already exists.
    existing_ids = {s.id for s in _load_index()}
    base_id = atlas_id
    counter = 2
    while atlas_id in existing_ids:
        atlas_id = f"{base_id}_{counter}"
        counter += 1

    target_dir = CUSTOM_DIR / atlas_id
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        volume_filename = _fetch_to(target_dir, volume_source, expected_suffixes=(".nii", ".nii.gz"))
        labels_filename: str | None = None
        if labels_source and labels_source.strip():
            labels_filename = _fetch_to(
                target_dir,
                labels_source.strip(),
                expected_suffixes=(".csv", ".tsv", ".txt", ".json"),
            )

        # Probe the NIfTI to detect probabilistic (4D with >1 volume) vs deterministic.
        volume_path = target_dir / volume_filename
        img = nib.load(str(volume_path))
        shape = tuple(int(s) for s in img.shape)
        is_probabilistic = len(shape) == 4 and shape[-1] > 1

        spec = CustomAtlasSpec(
            id=atlas_id,
            name=display_name,
            volume_filename=volume_filename,
            labels_filename=labels_filename,
            is_probabilistic=is_probabilistic,
        )
        specs = _load_index()
        specs.append(spec)
        _save_index(specs)
        return spec
    except Exception:
        # Clean up partial downloads on failure so the next attempt starts clean.
        shutil.rmtree(target_dir, ignore_errors=True)
        raise


def remove_custom_atlas(atlas_id: str) -> None:
    specs = _load_index()
    specs = [s for s in specs if s.id != atlas_id]
    _save_index(specs)
    shutil.rmtree(CUSTOM_DIR / atlas_id, ignore_errors=True)


# ---- Fetching an AtlasData from a spec -------------------------------------


def fetch_custom_atlas(spec: CustomAtlasSpec) -> AtlasData:
    """Load a custom atlas's NIfTI (+ optional labels file) into an AtlasData."""
    img = nib.load(str(spec.volume_path()))
    volume = np.asarray(img.dataobj)
    affine = img.affine

    if spec.is_probabilistic:
        volume = volume.astype(np.float32)
        if volume.ndim != 4:
            raise ValueError(
                f"Custom atlas {spec.id!r} flagged probabilistic but volume is {volume.ndim}D."
            )
        n_regions = int(volume.shape[-1])
        label_map = _read_labels_file(spec.labels_path()) if spec.labels_path() else {}
        labels = [
            AtlasLabel(index=i, name=label_map.get(i, f"Region {i + 1}"))
            for i in range(n_regions)
        ]
    else:
        volume = _squeeze_singleton(volume).astype(np.int32)
        if volume.ndim != 3:
            raise ValueError(
                f"Custom atlas {spec.id!r} should be 3D deterministic, got {volume.ndim}D."
            )
        present = np.unique(volume)
        present = present[present != 0]
        label_map = _read_labels_file(spec.labels_path()) if spec.labels_path() else {}
        labels = [
            AtlasLabel(index=int(v), name=label_map.get(int(v), f"Label {int(v)}"))
            for v in present
        ]

    return AtlasData(
        id=spec.id,
        name=f"Custom: {spec.name}",
        volume=volume,
        affine=affine,
        labels=labels,
        is_probabilistic=spec.is_probabilistic,
    )


# ---- Helpers ---------------------------------------------------------------


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_")
    return s or hashlib.sha1(name.encode()).hexdigest()[:8]


def _squeeze_singleton(arr: np.ndarray) -> np.ndarray:
    if arr.ndim == 4 and arr.shape[-1] == 1:
        return arr[..., 0]
    return arr


def _is_url(s: str) -> bool:
    try:
        u = urlparse(s)
        return u.scheme in ("http", "https") and bool(u.netloc)
    except Exception:
        return False


def _infer_filename(source: str, fallback: str) -> str:
    if _is_url(source):
        name = Path(urlparse(source).path).name
    else:
        name = Path(source).name
    return name or fallback


def _fetch_to(
    target_dir: Path,
    source: str,
    expected_suffixes: tuple[str, ...],
) -> str:
    """Download (URL) or copy (local) `source` into `target_dir`. Returns filename."""
    filename = _infer_filename(source, "atlas.bin")
    if not filename.lower().endswith(tuple(s.lower() for s in expected_suffixes)):
        # best-effort: don't reject, but we won't try to rename either — let it through
        pass
    dest = target_dir / filename

    if _is_url(source):
        with requests.get(source, stream=True, timeout=60) as r:
            r.raise_for_status()
            total = 0
            with dest.open("wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise RuntimeError(
                            f"Download exceeded {MAX_DOWNLOAD_BYTES // (1024*1024)} MB limit."
                        )
                    f.write(chunk)
    else:
        src = Path(source).expanduser().resolve()
        if not src.exists():
            raise FileNotFoundError(f"Source not found: {src}")
        shutil.copyfile(src, dest)

    return filename


def _read_labels_file(path: Path) -> dict[int, str]:
    """Parse a labels file in CSV/TSV/TXT/JSON into `{integer_index: name}`."""
    if path is None or not path.exists():
        return {}

    suffix = path.suffix.lower()
    text = path.read_text(errors="replace")

    # JSON
    if suffix == ".json":
        try:
            raw = json.loads(text)
            if isinstance(raw, dict):
                return {int(k): str(v) for k, v in raw.items() if _is_int(k)}
            if isinstance(raw, list):
                return {
                    int(r.get("index", i)): str(r.get("name", ""))
                    for i, r in enumerate(raw)
                    if isinstance(r, dict) and _is_int(r.get("index", i))
                }
        except Exception:
            pass

    # CSV/TSV with header
    try:
        import pandas as pd

        df = pd.read_csv(path, sep=None, engine="python")
        df.columns = [str(c).strip().lower() for c in df.columns]
        idx_col = next((c for c in df.columns if c in ("index", "id", "value", "label")), None)
        name_col = next(
            (c for c in df.columns if c in ("name", "label_name", "region", "roi")),
            None,
        )
        if idx_col is not None and name_col is not None:
            result: dict[int, str] = {}
            for _, row in df.iterrows():
                if _is_int(row[idx_col]):
                    result[int(row[idx_col])] = str(row[name_col])
            if result:
                return result
    except Exception:
        pass

    # Plain text "index name" lines
    result: dict[int, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) >= 2 and _is_int(parts[0]):
            result[int(parts[0])] = parts[1].strip()
    return result


def _is_int(x: Any) -> bool:
    try:
        int(x)
        return True
    except (ValueError, TypeError):
        return False
