from __future__ import annotations

from pathlib import Path

from platformdirs import user_cache_dir

APP_NAME = "ezbv"

CACHE_DIR: Path = Path(user_cache_dir(APP_NAME))
MESH_CACHE_DIR: Path = CACHE_DIR / "meshes"
TEMPLATE_CACHE_DIR: Path = CACHE_DIR / "templates"
ATLAS_CACHE_DIR: Path = CACHE_DIR / "atlases"

for _d in (MESH_CACHE_DIR, TEMPLATE_CACHE_DIR, ATLAS_CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Fixed off-screen base size for exports; `image_scale` multiplies this.
EXPORT_BASE_SIZE: tuple[int, int] = (1600, 1200)

# 10-color default palette (ColorBrewer-ish, high contrast on a neutral background)
DEFAULT_PALETTE: tuple[tuple[float, float, float], ...] = (
    (0.894, 0.102, 0.110),  # red
    (0.216, 0.494, 0.722),  # blue
    (0.302, 0.686, 0.290),  # green
    (0.596, 0.306, 0.639),  # purple
    (1.000, 0.498, 0.000),  # orange
    (1.000, 1.000, 0.200),  # yellow
    (0.651, 0.337, 0.157),  # brown
    (0.969, 0.506, 0.749),  # pink
    (0.400, 0.761, 0.647),  # teal
    (0.600, 0.600, 0.600),  # grey
)

# Camera presets: (position, focal_point, view_up) — pyvista sets these directly.
# Distances are rough; pyvista `reset_camera()` adjusts zoom after.
CAMERA_PRESETS: dict[str, tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]] = {
    "left":      ((-400,    0,   0), (0, 0, 0), (0, 0, 1)),
    "right":     (( 400,    0,   0), (0, 0, 0), (0, 0, 1)),
    "anterior":  ((   0,  400,   0), (0, 0, 0), (0, 0, 1)),
    "posterior": ((   0, -400,   0), (0, 0, 0), (0, 0, 1)),
    "superior":  ((   0,    0, 400), (0, 0, 0), (0, 1, 0)),
    "inferior":  ((   0,    0,-400), (0, 0, 0), (0, 1, 0)),
    "oblique":   (( 300,  300, 200), (0, 0, 0), (0, 0, 1)),
}

# Default template opacity for the "glass" shell.
DEFAULT_TEMPLATE_OPACITY: float = 0.15

# Taubin smoothing parameters for ROI and template meshes.
ROI_SMOOTH_ITERS: int = 20
TEMPLATE_SMOOTH_ITERS: int = 30
