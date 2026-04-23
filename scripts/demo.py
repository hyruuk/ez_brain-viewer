"""End-to-end demo via SceneManager.

Run:
    python scripts/demo.py

Produces:
    scripts/demo.png             — oblique view, transparent MNI152 + 5 ROIs
    scripts/demo_anterior.png    — same scene, anterior view
"""

from __future__ import annotations

from pathlib import Path

import pyvista as pv

from ez_brain_viewer import config
from ez_brain_viewer.atlases import AtlasRegistry
from ez_brain_viewer.meshing import MeshBuilder
from ez_brain_viewer.scene import SceneManager
from ez_brain_viewer.templates import TemplateRegistry


HIGHLIGHTS = [
    ("harvard_oxford_sub", "Left Hippocampus",    (0.894, 0.102, 0.110), True),
    ("harvard_oxford_sub", "Right Hippocampus",   (0.894, 0.102, 0.110), False),
    ("harvard_oxford_sub", "Left Amygdala",       (1.000, 0.498, 0.000), True),
    ("harvard_oxford_sub", "Right Amygdala",      (1.000, 0.498, 0.000), False),
    ("harvard_oxford_cort", "Frontal Pole",       (0.216, 0.494, 0.722), True),
]


def _find_label(labels, needle: str):
    for lab in labels:
        if needle.lower() in lab.name.lower():
            return lab
    raise LookupError(f"No label matching {needle!r}")


def main() -> None:
    out_dir = Path(__file__).parent

    atlases = AtlasRegistry()
    templates = TemplateRegistry()
    mesh_builder = MeshBuilder()

    plotter = pv.Plotter(off_screen=True, window_size=config.EXPORT_BASE_SIZE)
    scene = SceneManager(plotter, atlases, templates, mesh_builder)

    scene.add_template("mni152_detailed", opacity=config.DEFAULT_TEMPLATE_OPACITY)

    for atlas_id, needle, color, show_label in HIGHLIGHTS:
        atlas = atlases.get_atlas(atlas_id)
        label = _find_label(atlas.labels, needle)
        scene.add_layer(atlas_id, label.index, color=color, opacity=1.0, show_label=show_label)

    scene.set_camera_preset("oblique")
    scene.export_png(out_dir / "demo.png", width_px=3200, dpi=300, transparent=True)
    print("Wrote", out_dir / "demo.png")

    scene.set_camera_preset("anterior")
    scene.export_png(out_dir / "demo_anterior.png", width_px=3200, dpi=300, transparent=True)
    print("Wrote", out_dir / "demo_anterior.png")


if __name__ == "__main__":
    main()
