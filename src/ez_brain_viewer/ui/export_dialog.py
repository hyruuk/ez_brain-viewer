"""Dialog for configuring figure export.

Supports two formats:
  - **PNG** — single still frame, width + DPI + transparency.
  - **Animated GIF** — rotating-camera animation, with controls for rotation
    axis, total sweep, frame count, and playback FPS.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PySide6 import QtCore, QtWidgets


ExportFormat = Literal["png", "gif"]
RotationAxis = Literal["vertical", "horizontal", "roll"]


@dataclass
class ExportSettings:
    path: Path
    format: ExportFormat
    width_px: int
    dpi: int
    transparent: bool
    # GIF-only
    rotation_axis: RotationAxis
    rotation_deg: float
    n_frames: int
    cycle_duration_s: float


class ExportDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, default_dir: Path | None = None):
        super().__init__(parent)
        self.setWindowTitle("Export figure")
        self.setModal(True)

        self._default_dir = default_dir or Path.home()

        form = QtWidgets.QFormLayout()

        # Format selector ----------------------------------------------------
        self.format_combo = QtWidgets.QComboBox()
        self.format_combo.addItem("PNG (still image)", "png")
        self.format_combo.addItem("Animated GIF (rotating)", "gif")
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        form.addRow("Format", self.format_combo)

        # Path + browse ------------------------------------------------------
        self.path_edit = QtWidgets.QLineEdit(str(self._default_dir / "ezbv.png"))
        browse = QtWidgets.QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        path_row = QtWidgets.QHBoxLayout()
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)
        path_container = QtWidgets.QWidget()
        path_container.setLayout(path_row)
        form.addRow("File", path_container)

        # Width --------------------------------------------------------------
        self.width_spin = QtWidgets.QSpinBox()
        self.width_spin.setRange(400, 12000)
        self.width_spin.setSingleStep(200)
        self.width_spin.setValue(3200)
        self.width_spin.setSuffix(" px")
        form.addRow("Width", self.width_spin)

        # DPI (PNG-only metadata) --------------------------------------------
        self.dpi_label = QtWidgets.QLabel("DPI (metadata)")
        self.dpi_spin = QtWidgets.QSpinBox()
        self.dpi_spin.setRange(72, 1200)
        self.dpi_spin.setSingleStep(50)
        self.dpi_spin.setValue(300)
        form.addRow(self.dpi_label, self.dpi_spin)

        self.transparent_check = QtWidgets.QCheckBox("Transparent background")
        self.transparent_check.setChecked(True)
        form.addRow(self.transparent_check)

        # GIF-specific rotation group ---------------------------------------
        self.gif_group = QtWidgets.QGroupBox("Rotation (GIF only)")
        gif_form = QtWidgets.QFormLayout(self.gif_group)

        self.axis_combo = QtWidgets.QComboBox()
        self.axis_combo.addItem("Vertical (azimuth — spin around up axis)", "vertical")
        self.axis_combo.addItem("Horizontal (elevation — pitch up/down)", "horizontal")
        self.axis_combo.addItem("Roll (around line of sight)", "roll")
        gif_form.addRow("Axis", self.axis_combo)

        self.rotation_spin = QtWidgets.QDoubleSpinBox()
        self.rotation_spin.setRange(10.0, 3600.0)
        self.rotation_spin.setSingleStep(45.0)
        self.rotation_spin.setValue(360.0)
        self.rotation_spin.setDecimals(0)
        self.rotation_spin.setSuffix(" °")
        self.rotation_spin.setToolTip(
            "Total sweep angle across the full clip. 360° = seamless loop."
        )
        gif_form.addRow("Total rotation", self.rotation_spin)

        self.frames_spin = QtWidgets.QSpinBox()
        self.frames_spin.setRange(2, 360)
        self.frames_spin.setValue(36)
        self.frames_spin.setSingleStep(6)
        self.frames_spin.setToolTip(
            "Number of captured frames. More frames = smoother motion, larger file."
        )
        gif_form.addRow("Frames", self.frames_spin)

        self.cycle_duration_spin = QtWidgets.QDoubleSpinBox()
        self.cycle_duration_spin.setRange(0.5, 60.0)
        self.cycle_duration_spin.setSingleStep(0.5)
        self.cycle_duration_spin.setValue(3.0)
        self.cycle_duration_spin.setDecimals(1)
        self.cycle_duration_spin.setSuffix(" s")
        self.cycle_duration_spin.setToolTip(
            "Total playback time for one full rotation sweep. "
            "Per-frame duration = 1000 × duration / frames (ms)."
        )
        gif_form.addRow("Cycle duration", self.cycle_duration_spin)

        self.loop_check = QtWidgets.QCheckBox("Loop indefinitely")
        self.loop_check.setChecked(True)
        gif_form.addRow(self.loop_check)

        # Buttons ------------------------------------------------------------
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        outer = QtWidgets.QVBoxLayout(self)
        outer.addLayout(form)
        outer.addWidget(self.gif_group)
        outer.addWidget(buttons)
        self.resize(520, 420)

        # Initial visibility matches default format (PNG).
        self._on_format_changed(self.format_combo.currentIndex())

    # ---- Format switching --------------------------------------------------

    def _current_format(self) -> ExportFormat:
        return self.format_combo.currentData() or "png"

    def _on_format_changed(self, _index: int) -> None:
        fmt = self._current_format()
        is_gif = fmt == "gif"

        self.gif_group.setVisible(is_gif)
        self.dpi_label.setVisible(not is_gif)
        self.dpi_spin.setVisible(not is_gif)

        # GIF has no real alpha channel (1-bit palette transparency), so a
        # transparent background ends up bleeding through semi-transparent
        # shells. Disable the checkbox for GIF and make the reason visible.
        self.transparent_check.setEnabled(not is_gif)
        if is_gif:
            self.transparent_check.setToolTip(
                "GIF does not support real alpha — background is rendered on solid white."
            )
        else:
            self.transparent_check.setToolTip("")

        # Swap file extension to match the chosen format.
        current_path = Path(self.path_edit.text())
        new_ext = ".gif" if is_gif else ".png"
        if current_path.suffix.lower() != new_ext:
            self.path_edit.setText(str(current_path.with_suffix(new_ext)))

        # Lower the default width when switching to GIF — animated exports
        # blow up fast in both memory and file size.
        if is_gif and self.width_spin.value() > 1600:
            self.width_spin.setValue(1200)
        elif not is_gif and self.width_spin.value() < 1600:
            self.width_spin.setValue(3200)

        self.setWindowTitle("Export animated GIF" if is_gif else "Export PNG")

    # ---- Browse ------------------------------------------------------------

    def _browse(self) -> None:
        fmt = self._current_format()
        filt = "PNG Image (*.png)" if fmt == "png" else "Animated GIF (*.gif)"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            self.windowTitle(),
            self.path_edit.text(),
            filt,
        )
        if path:
            required_ext = ".png" if fmt == "png" else ".gif"
            if not path.lower().endswith(required_ext):
                path += required_ext
            self.path_edit.setText(path)

    # ---- Public ------------------------------------------------------------

    def settings(self) -> ExportSettings:
        return ExportSettings(
            path=Path(self.path_edit.text()).expanduser(),
            format=self._current_format(),
            width_px=int(self.width_spin.value()),
            dpi=int(self.dpi_spin.value()),
            transparent=bool(self.transparent_check.isChecked()),
            rotation_axis=self.axis_combo.currentData() or "vertical",
            rotation_deg=float(self.rotation_spin.value()),
            n_frames=int(self.frames_spin.value()),
            cycle_duration_s=float(self.cycle_duration_spin.value()),
        )
