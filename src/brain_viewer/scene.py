"""Scene orchestration: owns the plotter, template actor, and ROI layers.

Works with both `pyvista.Plotter` (headless tests, exports) and
`pyvistaqt.QtInteractor` (GUI) — they share the relevant API surface.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pyvista as pv
from PIL import Image

from . import config
from .atlases import AtlasRegistry
from .meshing import MeshBuilder
from .templates import TemplateRegistry

CameraPreset = Literal[
    "left", "right", "anterior", "posterior", "superior", "inferior", "oblique"
]


@dataclass
class Layer:
    id: str
    atlas_id: str
    label_index: int
    label_name: str
    color: tuple[float, float, float]
    opacity: float
    show_label: bool
    mesh: pv.PolyData
    mesh_actor: Any  # vtkActor
    label_actor: Any | None = None  # vtkActor or None


class SceneManager:
    def __init__(
        self,
        plotter: pv.Plotter,
        atlases: AtlasRegistry,
        templates: TemplateRegistry,
        mesh_builder: MeshBuilder,
    ) -> None:
        self.plotter = plotter
        self.atlases = atlases
        self.templates = templates
        self.mesh_builder = mesh_builder

        self.layers: dict[str, Layer] = {}
        self._template_id: str | None = None
        self._template_actor: Any | None = None
        self._template_opacity: float = config.DEFAULT_TEMPLATE_OPACITY
        self._template_visible: bool = True

        plotter.set_background("white")
        try:
            plotter.enable_anti_aliasing("msaa", multi_samples=8)
        except Exception:
            # Not all plotter backends support MSAA; safe to ignore.
            pass

    # -- Template ------------------------------------------------------------

    @property
    def template_id(self) -> str | None:
        return self._template_id

    def set_template(
        self,
        template_id: str,
        opacity: float | None = None,
        visible: bool | None = None,
    ) -> None:
        if opacity is not None:
            self._template_opacity = opacity
        if visible is not None:
            self._template_visible = visible

        tpl = self.templates.get_template(template_id)
        self._template_id = template_id

        if self._template_actor is not None:
            self.plotter.remove_actor(self._template_actor, render=False)
            self._template_actor = None

        if self._template_visible:
            self._template_actor = self.plotter.add_mesh(
                tpl.mesh,
                color=(0.85, 0.85, 0.90),
                opacity=self._template_opacity,
                specular=0.3,
                specular_power=15,
                smooth_shading=True,
                name="__template__",
            )
        self._render()

    def set_template_visible(self, visible: bool) -> None:
        if self._template_id is None:
            self._template_visible = visible
            return
        self.set_template(self._template_id, visible=visible)

    def set_template_opacity(self, opacity: float) -> None:
        self._template_opacity = opacity
        if self._template_actor is not None:
            self._template_actor.prop.opacity = opacity
            self._render()

    # -- Layers --------------------------------------------------------------

    def add_layer(
        self,
        atlas_id: str,
        label_index: int,
        color: tuple[float, float, float],
        opacity: float = 1.0,
        show_label: bool = False,
    ) -> str:
        atlas = self.atlases.get_atlas(atlas_id)
        label = next((lb for lb in atlas.labels if lb.index == label_index), None)
        if label is None:
            raise KeyError(f"Atlas {atlas_id!r} has no label index {label_index}")

        mesh = self.mesh_builder.label_to_mesh(atlas, label_index)

        layer_id = uuid.uuid4().hex[:12]
        mesh_actor = self.plotter.add_mesh(
            mesh,
            color=color,
            opacity=opacity,
            smooth_shading=True,
            specular=0.2,
            specular_power=10,
            name=f"layer_{layer_id}",
        )

        label_actor = None
        if show_label:
            label_actor = self._add_label(layer_id, mesh, label.name)

        self.layers[layer_id] = Layer(
            id=layer_id,
            atlas_id=atlas_id,
            label_index=label_index,
            label_name=label.name,
            color=color,
            opacity=opacity,
            show_label=show_label,
            mesh=mesh,
            mesh_actor=mesh_actor,
            label_actor=label_actor,
        )
        self._render()
        return layer_id

    def update_layer(
        self,
        layer_id: str,
        color: tuple[float, float, float] | None = None,
        opacity: float | None = None,
        show_label: bool | None = None,
    ) -> None:
        layer = self.layers[layer_id]

        if color is not None:
            layer.color = color
            layer.mesh_actor.prop.color = color
        if opacity is not None:
            layer.opacity = opacity
            layer.mesh_actor.prop.opacity = opacity
        if show_label is not None and show_label != layer.show_label:
            layer.show_label = show_label
            if show_label:
                layer.label_actor = self._add_label(layer_id, layer.mesh, layer.label_name)
            else:
                if layer.label_actor is not None:
                    self.plotter.remove_actor(layer.label_actor, render=False)
                    layer.label_actor = None
        self._render()

    def remove_layer(self, layer_id: str) -> None:
        layer = self.layers.pop(layer_id, None)
        if layer is None:
            return
        self.plotter.remove_actor(layer.mesh_actor, render=False)
        if layer.label_actor is not None:
            self.plotter.remove_actor(layer.label_actor, render=False)
        self._render()

    def clear_layers(self) -> None:
        for layer_id in list(self.layers.keys()):
            self.remove_layer(layer_id)

    def _add_label(self, layer_id: str, mesh: pv.PolyData, name: str) -> Any:
        centroid = np.array(mesh.center)[np.newaxis, :]
        return self.plotter.add_point_labels(
            centroid,
            [name],
            always_visible=True,
            shape=None,
            font_size=28,
            text_color="black",
            point_size=1,
            name=f"label_{layer_id}",
        )

    # -- Camera --------------------------------------------------------------

    def set_camera_preset(self, preset: CameraPreset) -> None:
        if preset not in config.CAMERA_PRESETS:
            raise KeyError(f"Unknown camera preset: {preset!r}")
        pos, focal, up = config.CAMERA_PRESETS[preset]
        self.plotter.camera_position = [pos, focal, up]
        self.plotter.reset_camera()
        self._render()

    # -- Export --------------------------------------------------------------

    def export_png(
        self,
        path: str | Path,
        width_px: int,
        dpi: int = 300,
        transparent: bool = True,
        height_px: int | None = None,
    ) -> Path:
        """Render the current scene into a fresh off-screen plotter, then save PNG.

        The live plotter is never resized. DPI is written as PNG metadata only.
        """
        path = Path(path)
        base_w, base_h = config.EXPORT_BASE_SIZE
        target_w = int(width_px)
        target_h = int(height_px) if height_px else int(round(base_h * (target_w / base_w)))

        # Render at target pixel size directly. `screenshot(scale=N)` does not
        # scale 2D overlays (labels, axes) reliably, so we avoid it.
        off = pv.Plotter(off_screen=True, window_size=(target_w, target_h))
        off.set_background("white")
        try:
            off.enable_anti_aliasing("msaa", multi_samples=8)
        except Exception:
            pass

        if self._template_visible and self._template_id is not None:
            tpl = self.templates.get_template(self._template_id)
            off.add_mesh(
                tpl.mesh,
                color=(0.85, 0.85, 0.90),
                opacity=self._template_opacity,
                specular=0.3,
                specular_power=15,
                smooth_shading=True,
            )

        # Scale font size with target width so labels stay legible at all sizes.
        font_px = max(14, int(round(28 * target_w / base_w)))

        for layer in self.layers.values():
            off.add_mesh(
                layer.mesh,
                color=layer.color,
                opacity=layer.opacity,
                smooth_shading=True,
                specular=0.2,
                specular_power=10,
            )
            if layer.show_label:
                centroid = np.array(layer.mesh.center)[np.newaxis, :]
                off.add_point_labels(
                    centroid,
                    [layer.label_name],
                    always_visible=True,
                    shape=None,
                    font_size=font_px,
                    text_color="black",
                    point_size=1,
                )

        off.camera_position = self.plotter.camera_position

        arr = off.screenshot(transparent_background=transparent, return_img=True)
        off.close()

        mode = "RGBA" if arr.shape[2] == 4 else "RGB"
        Image.fromarray(arr, mode=mode).save(str(path), dpi=(dpi, dpi))
        return path

    # -- Internals -----------------------------------------------------------

    def _render(self) -> None:
        render = getattr(self.plotter, "render", None)
        if render is not None:
            render()
