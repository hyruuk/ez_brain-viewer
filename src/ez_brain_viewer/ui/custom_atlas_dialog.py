"""Dialog for registering a custom atlas (NIfTI volume + optional labels)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6 import QtCore, QtWidgets


@dataclass
class CustomAtlasInput:
    display_name: str
    volume_source: str
    labels_source: str | None


class CustomAtlasDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add custom atlas")
        self.setModal(True)

        form = QtWidgets.QFormLayout()

        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Insula subparcellation (Brainnetome)")
        form.addRow("Display name", self.name_edit)

        self.volume_edit = QtWidgets.QLineEdit()
        self.volume_edit.setPlaceholderText("/path/to/atlas.nii.gz  or  https://…")
        vol_browse = QtWidgets.QPushButton("Browse…")
        vol_browse.clicked.connect(
            lambda: self._browse(
                self.volume_edit,
                "Volume NIfTI",
                "NIfTI (*.nii *.nii.gz);;All files (*)",
            )
        )
        vol_row = QtWidgets.QHBoxLayout()
        vol_row.addWidget(self.volume_edit, 1)
        vol_row.addWidget(vol_browse)
        vol_container = QtWidgets.QWidget()
        vol_container.setLayout(vol_row)
        form.addRow("Volume (file or URL)", vol_container)

        self.labels_edit = QtWidgets.QLineEdit()
        self.labels_edit.setPlaceholderText("optional — CSV/TSV/TXT/JSON")
        lbl_browse = QtWidgets.QPushButton("Browse…")
        lbl_browse.clicked.connect(
            lambda: self._browse(
                self.labels_edit,
                "Labels file",
                "Tables (*.csv *.tsv *.txt *.json);;All files (*)",
            )
        )
        lbl_row = QtWidgets.QHBoxLayout()
        lbl_row.addWidget(self.labels_edit, 1)
        lbl_row.addWidget(lbl_browse)
        lbl_container = QtWidgets.QWidget()
        lbl_container.setLayout(lbl_row)
        form.addRow("Labels (optional)", lbl_container)

        tip = QtWidgets.QLabel(
            "Volume must be in MNI152 space to align with the template shells.\n"
            "Labels file: CSV/TSV with 'index' + 'name' columns, JSON dict, or\n"
            "plain text 'index name' lines (FSL LUT style). If omitted, regions\n"
            "are auto-named 'Label N' from the unique integer values in the volume.\n"
            "4D NIfTIs are treated as probabilistic (one channel per region)."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #555; font-size: 11px;")

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.button(QtWidgets.QDialogButtonBox.Ok).setText("Add atlas")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        outer = QtWidgets.QVBoxLayout(self)
        outer.addLayout(form)
        outer.addWidget(tip)
        outer.addWidget(buttons)
        self.resize(560, 260)

    def _browse(self, edit: QtWidgets.QLineEdit, caption: str, file_filter: str) -> None:
        start = edit.text() or str(Path.home())
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, caption, start, file_filter)
        if path:
            edit.setText(path)

    def _on_accept(self) -> None:
        if not self.name_edit.text().strip():
            QtWidgets.QMessageBox.warning(self, "Missing field", "Display name is required.")
            return
        if not self.volume_edit.text().strip():
            QtWidgets.QMessageBox.warning(self, "Missing field", "Volume source is required.")
            return
        self.accept()

    def input(self) -> CustomAtlasInput:
        labels = self.labels_edit.text().strip()
        return CustomAtlasInput(
            display_name=self.name_edit.text().strip(),
            volume_source=self.volume_edit.text().strip(),
            labels_source=labels or None,
        )
