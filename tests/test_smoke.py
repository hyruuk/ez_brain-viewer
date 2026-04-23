"""Smoke tests for the ezbv pipeline.

These exercise the end-to-end flow without launching the Qt GUI:
- atlas fetch (cached in CI reruns)
- mesh extraction
- SceneManager scene assembly
- off-screen PNG export
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyvista as pv
from PIL import Image

import pytest

from ezbv import config
from ezbv.atlases import AtlasRegistry
from ezbv.external_atlases import EXTERNAL_ENTRIES
from ezbv.meshing import MeshBuilder
from ezbv.scene import SceneManager
from ezbv.templates import TemplateRegistry


# Atlases that are small-cached and reliably load in CI without long downloads.
FAST_ATLASES = [
    "harvard_oxford_cort",
    "harvard_oxford_sub",
    "destrieux",
    "juelich",
    "schaefer_100_7",
    "schaefer_400_7",
    "yeo_7",
    "yeo_17",
    "msdl",
    "pauli_2017_det",
    "basc_64_sym",
]


@pytest.mark.parametrize("atlas_id", FAST_ATLASES)
def test_registered_atlas_loads(atlas_id: str) -> None:
    """Every listed atlas loads into a usable AtlasData."""
    reg = AtlasRegistry()
    atlas = reg.get_atlas(atlas_id)
    assert atlas.volume.ndim in (3, 4)
    assert len(atlas.labels) >= 1
    mb = MeshBuilder()
    # Mesh the first non-empty label.
    for lb in atlas.labels[:5]:
        try:
            mesh = mb.label_to_mesh(atlas, lb.index)
            assert mesh.n_points > 50
            return
        except ValueError:
            continue
    pytest.fail(f"No non-empty label found in first 5 of {atlas_id}")


def test_external_entries_catalog() -> None:
    """External atlas entries register with distinct IDs and non-empty names."""
    reg = AtlasRegistry()
    reg.register_external(EXTERNAL_ENTRIES)
    listing = reg.list_atlases()
    ids = {aid for aid, _ in listing}
    for e in EXTERNAL_ENTRIES:
        assert e.id in ids, f"External entry {e.id!r} missing from registry listing"
        assert e.display_name.strip()


def test_harvard_oxford_cort_loads_and_meshes() -> None:
    reg = AtlasRegistry()
    atlas = reg.get_atlas("harvard_oxford_cort")
    assert atlas.volume.ndim == 3
    assert not atlas.is_probabilistic
    assert len(atlas.labels) > 30

    mb = MeshBuilder()
    mesh = mb.label_to_mesh(atlas, atlas.labels[0].index)
    assert mesh.n_points > 0
    assert mesh.n_cells > 0


def test_mni152_template_loads() -> None:
    tr = TemplateRegistry()
    tpl = tr.get_template("mni152_brain")
    assert tpl.mesh.n_points > 1000
    pts = np.asarray(tpl.mesh.points)
    # MNI brain should span roughly a human-head bounding box in mm.
    extent = pts.max(0) - pts.min(0)
    assert np.all(extent > 80)


def test_scene_export_produces_transparent_png(tmp_path: Path) -> None:
    reg = AtlasRegistry()
    templates = TemplateRegistry()
    mb = MeshBuilder()

    plotter = pv.Plotter(off_screen=True, window_size=config.EXPORT_BASE_SIZE)
    scene = SceneManager(plotter, reg, templates, mb)
    scene.add_template("mni152_brain", opacity=0.15)

    atlas = reg.get_atlas("harvard_oxford_sub")
    amyg = next(lb for lb in atlas.labels if "Left Amygdala" in lb.name)
    scene.add_layer(
        "harvard_oxford_sub",
        amyg.index,
        color=(1.0, 0.4, 0.0),
        opacity=1.0,
        show_label=True,
    )
    scene.set_camera_preset("oblique")

    out_path = tmp_path / "test.png"
    scene.export_png(out_path, width_px=1200, dpi=200, transparent=True)

    assert out_path.exists()
    img = Image.open(out_path)
    assert img.mode == "RGBA"
    assert img.size == (1200, int(1200 * config.EXPORT_BASE_SIZE[1] / config.EXPORT_BASE_SIZE[0]))
    dpi = img.info.get("dpi")
    assert dpi is not None
    assert abs(dpi[0] - 200) < 0.01 and abs(dpi[1] - 200) < 0.01

    arr = np.array(img)
    # Real transparency present (some fully-transparent pixels).
    assert (arr[..., 3] == 0).any()
    # And some opaque region content.
    assert (arr[..., 3] == 255).any()
