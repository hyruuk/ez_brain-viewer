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
    visible: bool = True


@dataclass
class TemplateShell:
    id: str
    name: str
    mesh: pv.PolyData
    opacity: float
    visible: bool
    actor: Any


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
        # Multiple template shells can be stacked; each has its own opacity.
        self.template_shells: dict[str, TemplateShell] = {}
        # Cull back faces on template shells (on by default: cleaner interior view).
        self._cull_backfaces: bool = True

        plotter.set_background("white")
        try:
            plotter.enable_anti_aliasing("msaa", multi_samples=8)
        except Exception:
            # Not all plotter backends support MSAA; safe to ignore.
            pass
        # Order-independent transparency: avoids back faces of transparent meshes
        # bleeding through the opaque ROIs inside.
        try:
            plotter.enable_depth_peeling(number_of_peels=6, occlusion_ratio=0.0)
        except Exception:
            pass

    # -- Template shells -----------------------------------------------------

    def add_template(self, template_id: str, opacity: float | None = None) -> None:
        """Add a template shell to the scene. No-op if already present (updates opacity)."""
        if template_id in self.template_shells:
            if opacity is not None:
                self.update_template(template_id, opacity=opacity)
            return

        tpl = self.templates.get_template(template_id)
        op = config.DEFAULT_TEMPLATE_OPACITY if opacity is None else opacity
        actor = self.plotter.add_mesh(
            tpl.mesh,
            color=(0.85, 0.85, 0.90),
            opacity=op,
            specular=0.3,
            specular_power=15,
            smooth_shading=True,
            name=f"__template_{template_id}__",
        )
        self._apply_shell_cull(actor)

        shell = TemplateShell(
            id=template_id, name=tpl.name, mesh=tpl.mesh,
            opacity=op, visible=True, actor=actor,
        )
        self.template_shells[template_id] = shell
        self._apply_effective_visibility(shell)
        self._render()

    def set_shell_backface_culling(self, enabled: bool) -> None:
        """Toggle backface culling on every template shell actor."""
        self._cull_backfaces = enabled
        for shell in self.template_shells.values():
            self._apply_shell_cull(shell.actor)
        self._render()

    @staticmethod
    def _apply_effective_visibility(shell: "TemplateShell") -> None:
        """A shell is shown only if visible AND opacity > 0 — a zero-opacity
        actor still participates in depth peeling and can create line artifacts
        when stacked with another shell, so hide it outright at opacity == 0."""
        effective = shell.visible and shell.opacity > 0.0
        shell.actor.SetVisibility(effective)

    def _apply_shell_cull(self, actor: Any) -> None:
        try:
            actor.prop.SetBackfaceCulling(bool(self._cull_backfaces))
        except Exception:
            pass

    def remove_template(self, template_id: str) -> None:
        shell = self.template_shells.pop(template_id, None)
        if shell is None:
            return
        self.plotter.remove_actor(shell.actor, render=False)
        self._render()

    def update_template(
        self,
        template_id: str,
        opacity: float | None = None,
        visible: bool | None = None,
    ) -> None:
        shell = self.template_shells.get(template_id)
        if shell is None:
            return
        if opacity is not None:
            shell.opacity = opacity
            shell.actor.prop.opacity = opacity
        if visible is not None:
            shell.visible = visible
        # Recompute effective visibility whenever opacity or visibility changes.
        self._apply_effective_visibility(shell)
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
        visible: bool | None = None,
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
                if not layer.visible:
                    layer.label_actor.SetVisibility(False)
            else:
                if layer.label_actor is not None:
                    self.plotter.remove_actor(layer.label_actor, render=False)
                    layer.label_actor = None
        if visible is not None and visible != layer.visible:
            layer.visible = visible
            layer.mesh_actor.SetVisibility(visible)
            if layer.label_actor is not None:
                layer.label_actor.SetVisibility(visible)
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
        try:
            off.enable_depth_peeling(number_of_peels=6, occlusion_ratio=0.0)
        except Exception:
            pass

        for shell in self.template_shells.values():
            if not shell.visible or shell.opacity <= 0.0:
                continue
            tpl_actor = off.add_mesh(
                shell.mesh,
                color=(0.85, 0.85, 0.90),
                opacity=shell.opacity,
                specular=0.3,
                specular_power=15,
                smooth_shading=True,
            )
            try:
                tpl_actor.prop.SetBackfaceCulling(bool(self._cull_backfaces))
            except Exception:
                pass

        # Scale font size with target width so labels stay legible at all sizes.
        font_px = max(14, int(round(28 * target_w / base_w)))

        for layer in self.layers.values():
            if not layer.visible:
                continue
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
