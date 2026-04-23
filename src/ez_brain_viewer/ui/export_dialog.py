"""Dialog for configuring PNG export: width, DPI, transparent background, path."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6 import QtCore, QtWidgets


@dataclass
class ExportSettings:
    path: Path
    width_px: int
    dpi: int
    transparent: bool


class ExportDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, default_dir: Path | None = None):
        super().__init__(parent)
        self.setWindowTitle("Export PNG")
        self.setModal(True)

        self._default_dir = default_dir or Path.home()

        form = QtWidgets.QFormLayout()

        self.path_edit = QtWidgets.QLineEdit(str(self._default_dir / "ez_brain_viewer.png"))
        browse = QtWidgets.QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        path_row = QtWidgets.QHBoxLayout()
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)
        path_container = QtWidgets.QWidget()
        path_container.setLayout(path_row)
        form.addRow("File", path_container)

        self.width_spin = QtWidgets.QSpinBox()
        self.width_spin.setRange(400, 12000)
        self.width_spin.setSingleStep(200)
        self.width_spin.setValue(3200)
        self.width_spin.setSuffix(" px")
        form.addRow("Width", self.width_spin)

        self.dpi_spin = QtWidgets.QSpinBox()
        self.dpi_spin.setRange(72, 1200)
        self.dpi_spin.setSingleStep(50)
        self.dpi_spin.setValue(300)
        form.addRow("DPI (metadata)", self.dpi_spin)

        self.transparent_check = QtWidgets.QCheckBox("Transparent background")
        self.transparent_check.setChecked(True)
        form.addRow(self.transparent_check)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        outer = QtWidgets.QVBoxLayout(self)
        outer.addLayout(form)
        outer.addWidget(buttons)
        self.resize(480, 200)

    def _browse(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export PNG",
            self.path_edit.text(),
            "PNG Image (*.png)",
        )
        if path:
            if not path.lower().endswith(".png"):
                path += ".png"
            self.path_edit.setText(path)

    def settings(self) -> ExportSettings:
        return ExportSettings(
            path=Path(self.path_edit.text()).expanduser(),
            width_px=int(self.width_spin.value()),
            dpi=int(self.dpi_spin.value()),
            transparent=bool(self.transparent_check.isChecked()),
        )
