"""App icon — generated once from the MNI152 brain mesh, then cached on disk."""

from __future__ import annotations

from pathlib import Path

from . import config


_ICON_SIZE = 256
_ICON_VERSION = "v1"
_ICON_CACHE: Path = config.CACHE_DIR / f"app_icon_{_ICON_VERSION}.png"


def get_app_icon():
    """Return a QIcon for the app, generating it on first call if needed."""
    from PySide6 import QtGui

    if not _ICON_CACHE.exists():
        try:
            _render_app_icon(_ICON_CACHE)
        except Exception:
            return QtGui.QIcon()
    return QtGui.QIcon(str(_ICON_CACHE))


def _render_app_icon(path: Path) -> None:
    import pyvista as pv
    from PIL import Image

    from .templates import TemplateRegistry

    tpl = TemplateRegistry().get_template("mni152_brain")

    plotter = pv.Plotter(off_screen=True, window_size=(_ICON_SIZE, _ICON_SIZE))
    try:
        plotter.enable_anti_aliasing("msaa", multi_samples=8)
    except Exception:
        pass
    plotter.add_mesh(
        tpl.mesh,
        color=(0.80, 0.55, 0.70),  # soft lilac-pink, reads as "brain tissue"
        opacity=1.0,
        smooth_shading=True,
        specular=0.35,
        specular_power=20,
        ambient=0.25,
    )
    # Tight framing: slight oblique to show gyri + both hemispheres.
    plotter.camera_position = [(250, 180, 140), (0, -10, 5), (0, 0, 1)]
    plotter.reset_camera()
    plotter.camera.zoom(1.15)

    arr = plotter.screenshot(transparent_background=True, return_img=True)
    plotter.close()

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr).save(str(path))
