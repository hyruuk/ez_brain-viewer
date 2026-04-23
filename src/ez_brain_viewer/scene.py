"""Scene orchestration: owns the plotter, template actor, and ROI layers.

Works with both `pyvista.Plotter` (headless tests, exports) and
`pyvistaqt.QtInteractor` (GUI) — they share the relevant API surface.
"""

from __future__ import annotations

import json
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

    # -- Scene save / load ---------------------------------------------------

    SCENE_FORMAT: str = "ezbv.scene"
    SCENE_VERSION: int = 1

    def scene_snapshot(self) -> dict[str, Any]:
        """Return a JSON-serialisable snapshot of the editable scene state."""
        try:
            cam = self.plotter.camera
            camera = {
                "position": [float(x) for x in cam.position],
                "focal_point": [float(x) for x in cam.focal_point],
                "view_up": [float(x) for x in cam.up],
            }
        except Exception:
            camera = None

        return {
            "format": self.SCENE_FORMAT,
            "version": self.SCENE_VERSION,
            "shell_backface_cull": bool(self._cull_backfaces),
            "templates": [
                {
                    "id": shell.id,
                    "opacity": float(shell.opacity),
                    "visible": bool(shell.visible),
                }
                for shell in self.template_shells.values()
            ],
            "layers": [
                {
                    "atlas_id": layer.atlas_id,
                    "label_index": int(layer.label_index),
                    "label_name": layer.label_name,
                    "color": [float(c) for c in layer.color],
                    "opacity": float(layer.opacity),
                    "show_label": bool(layer.show_label),
                    "visible": bool(layer.visible),
                }
                for layer in self.layers.values()
            ],
            "camera": camera,
        }

    def save_scene(self, path: str | Path) -> Path:
        path = Path(path)
        path.write_text(json.dumps(self.scene_snapshot(), indent=2))
        return path

    def apply_scene_snapshot(self, data: dict[str, Any]) -> list[str]:
        """Restore the scene from `data`. Returns a list of non-fatal warnings
        (e.g. missing atlases or templates that could not be restored)."""
        fmt = data.get("format")
        # Accept the legacy "ez_brain_viewer.scene" format string so scenes saved
        # before the app was renamed continue to load cleanly.
        if fmt not in (self.SCENE_FORMAT, "ez_brain_viewer.scene"):
            raise ValueError(f"Not an ezbv scene file (format={fmt!r}).")
        version = int(data.get("version", 0))
        if version > self.SCENE_VERSION:
            raise ValueError(
                f"Scene version {version} is newer than this app supports "
                f"({self.SCENE_VERSION}). Upgrade ezbv."
            )

        warnings: list[str] = []

        # Tear down current state first so failures don't leave a half-merged scene.
        self.clear_layers()
        for tid in list(self.template_shells.keys()):
            self.remove_template(tid)

        self.set_shell_backface_culling(bool(data.get("shell_backface_cull", True)))

        for tpl in data.get("templates", []) or []:
            tid = tpl.get("id")
            if not tid:
                continue
            try:
                self.add_template(tid, opacity=float(tpl.get("opacity", config.DEFAULT_TEMPLATE_OPACITY)))
                if not bool(tpl.get("visible", True)):
                    self.update_template(tid, visible=False)
            except Exception as exc:
                warnings.append(f"Template {tid!r} could not be restored: {exc}")

        for rec in data.get("layers", []) or []:
            aid = rec.get("atlas_id")
            idx = rec.get("label_index")
            if not aid or idx is None:
                continue
            color = tuple(rec.get("color", (0.6, 0.6, 0.6)))
            opacity = float(rec.get("opacity", 1.0))
            show_label = bool(rec.get("show_label", False))
            visible = bool(rec.get("visible", True))
            try:
                layer_id = self.add_layer(
                    aid, int(idx), color=color, opacity=opacity, show_label=show_label
                )
                if not visible:
                    self.update_layer(layer_id, visible=False)
            except Exception as exc:
                name = rec.get("label_name") or f"label {idx}"
                warnings.append(f"Layer {name!r} in atlas {aid!r} could not be restored: {exc}")

        cam_state = data.get("camera")
        if isinstance(cam_state, dict):
            try:
                cam = self.plotter.camera
                cam.position = tuple(float(x) for x in cam_state["position"])
                cam.focal_point = tuple(float(x) for x in cam_state["focal_point"])
                cam.up = tuple(float(x) for x in cam_state["view_up"])
                try:
                    self.plotter.reset_camera_clipping_range()
                except Exception:
                    pass
                self._render()
            except Exception as exc:
                warnings.append(f"Camera could not be restored: {exc}")

        return warnings

    def load_scene(self, path: str | Path) -> list[str]:
        path = Path(path)
        data = json.loads(path.read_text())
        return self.apply_scene_snapshot(data)

    # -- Export --------------------------------------------------------------

    def _build_offscreen_plotter(self, target_w: int, target_h: int) -> pv.Plotter:
        """Create an off-screen plotter mirroring the current scene (shells + layers + labels).

        Camera is copied from the live plotter so the export matches what the user sees.
        """
        base_w, _ = config.EXPORT_BASE_SIZE

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
        return off

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
        off = self._build_offscreen_plotter(target_w, target_h)
        arr = off.screenshot(transparent_background=transparent, return_img=True)
        off.close()

        mode = "RGBA" if arr.shape[2] == 4 else "RGB"
        Image.fromarray(arr, mode=mode).save(str(path), dpi=(dpi, dpi))
        return path

    def export_gif(
        self,
        path: str | Path,
        width_px: int,
        rotation_axis: Literal["vertical", "horizontal", "roll"] = "vertical",
        rotation_deg: float = 360.0,
        n_frames: int = 36,
        cycle_duration_s: float = 3.0,
        loop: bool = True,
        height_px: int | None = None,
    ) -> Path:
        """Render a rotating-camera animation to an animated GIF.

        rotation_axis:
          - "vertical"   → camera azimuth around the scene's up axis (classic spin)
          - "horizontal" → camera elevation (pitches up/down)
          - "roll"       → rolls around the line-of-sight
        rotation_deg: total sweep angle across the whole clip (360° = seamless loop).
        n_frames: number of captured frames; angular step = rotation_deg / n_frames.
        cycle_duration_s: total playback length of one full sweep. Per-frame duration
            derives from this (`1000 * cycle_duration_s / n_frames` ms).

        Frames are always rendered on solid white — GIF supports only 1-bit
        palette transparency, which bleeds through any semi-transparent shell or
        layer and produces a tinted mess. For alpha-correct output, use PNG.
        """
        if n_frames < 2:
            raise ValueError("n_frames must be >= 2")
        if cycle_duration_s <= 0.0:
            raise ValueError("cycle_duration_s must be > 0")
        if rotation_axis not in ("vertical", "horizontal", "roll"):
            raise ValueError(f"unknown rotation_axis: {rotation_axis!r}")

        path = Path(path)
        base_w, base_h = config.EXPORT_BASE_SIZE
        target_w = int(width_px)
        target_h = int(height_px) if height_px else int(round(base_h * (target_w / base_w)))

        off = self._build_offscreen_plotter(target_w, target_h)

        # VTK camera rotations are applied *incrementally* to the current orientation,
        # so we build frames by nudging the camera by a constant delta each step.
        # Use the PascalCase vtkCamera methods (inherited by pyvista.Camera) because
        # pyvista's lowercase `azimuth`/`elevation`/`roll` are *properties* in recent
        # releases, not callable methods.
        step_deg = float(rotation_deg) / float(n_frames)
        vtk_cam = off.camera
        rotate = {
            "vertical":   vtk_cam.Azimuth,
            "horizontal": vtk_cam.Elevation,
            "roll":       vtk_cam.Roll,
        }[rotation_axis]

        # GIFs only support 1-bit palette transparency, so semi-transparent
        # shells/layers can't be encoded honestly — any backdrop color would
        # bleed through. Always render on solid white; the `transparent`
        # parameter is ignored for GIF exports.
        frames_rgb: list[Image.Image] = []
        try:
            for i in range(n_frames):
                if i > 0:
                    rotate(step_deg)
                    # Force a fresh render so the rotated camera state is reflected
                    # in the next screenshot — pyvista doesn't always flush dirty
                    # vtkCamera state between consecutive screenshot calls.
                    try:
                        off.render()
                    except Exception:
                        pass
                arr = off.screenshot(transparent_background=False, return_img=True)
                img = Image.fromarray(arr, mode="RGBA" if arr.shape[2] == 4 else "RGB").convert("RGB")
                frames_rgb.append(img)
        finally:
            off.close()

        # Quantize each frame independently so palettes stay local to the frame.
        p_frames = [
            f.convert("P", palette=Image.Palette.ADAPTIVE, colors=256) for f in frames_rgb
        ]
        duration_ms = max(20, int(round(1000.0 * float(cycle_duration_s) / float(n_frames))))
        p_frames[0].save(
            str(path),
            format="GIF",
            save_all=True,
            append_images=p_frames[1:],
            duration=duration_ms,
            loop=0 if loop else 1,
            disposal=2,
            optimize=False,
        )
        return path

    # -- Internals -----------------------------------------------------------

    def _render(self) -> None:
        render = getattr(self.plotter, "render", None)
        if render is not None:
            render()
