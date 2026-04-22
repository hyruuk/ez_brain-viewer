"""Left-hand control panel: template / atlas / regions / layers / camera / export."""

from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from .. import config
from ..atlases import AtlasRegistry
from ..scene import SceneManager
from ..templates import TemplateRegistry
from .export_dialog import ExportDialog, ExportSettings
from .layer_row import LayerRow


class ControlPanel(QtWidgets.QWidget):
    def __init__(
        self,
        scene: SceneManager,
        atlases: AtlasRegistry,
        templates: TemplateRegistry,
        parent=None,
    ):
        super().__init__(parent)
        self.scene = scene
        self.atlases = atlases
        self.templates = templates

        self._layer_rows: dict[str, LayerRow] = {}
        self._palette_idx: int = 0

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        outer.addWidget(self._build_template_group())
        outer.addWidget(self._build_atlas_group())
        outer.addWidget(self._build_layers_group(), 1)  # stretch
        outer.addWidget(self._build_camera_group())
        outer.addWidget(self._build_export_group())

        # Populate initial content once the widgets exist.
        QtCore.QTimer.singleShot(0, self._init_defaults)

    # ---- Sections -----------------------------------------------------------

    def _build_template_group(self) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("Template")
        form = QtWidgets.QFormLayout(box)

        self.template_combo = QtWidgets.QComboBox()
        for tid, name in self.templates.list_templates():
            self.template_combo.addItem(name, tid)
        self.template_combo.currentIndexChanged.connect(self._on_template_changed)
        form.addRow("Surface", self.template_combo)

        self.template_opacity_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.template_opacity_slider.setRange(0, 100)
        self.template_opacity_slider.setValue(int(config.DEFAULT_TEMPLATE_OPACITY * 100))
        self.template_opacity_slider.valueChanged.connect(
            lambda v: self.scene.set_template_opacity(v / 100.0)
        )
        form.addRow("Opacity", self.template_opacity_slider)

        self.template_visible_check = QtWidgets.QCheckBox("Show template")
        self.template_visible_check.setChecked(True)
        self.template_visible_check.toggled.connect(self.scene.set_template_visible)
        form.addRow(self.template_visible_check)

        return box

    def _build_atlas_group(self) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("Atlas")
        v = QtWidgets.QVBoxLayout(box)

        self.atlas_combo = QtWidgets.QComboBox()
        for aid, name in self.atlases.list_atlases():
            self.atlas_combo.addItem(name, aid)
        self.atlas_combo.currentIndexChanged.connect(self._on_atlas_changed)
        v.addWidget(self.atlas_combo)

        self.filter_edit = QtWidgets.QLineEdit()
        self.filter_edit.setPlaceholderText("Filter regions…")
        self.filter_edit.textChanged.connect(self._apply_region_filter)
        v.addWidget(self.filter_edit)

        self.region_list = QtWidgets.QListWidget()
        self.region_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.region_list.setMinimumHeight(160)
        self.region_list.itemDoubleClicked.connect(lambda _item: self._add_selected_regions())
        v.addWidget(self.region_list, 1)

        add_button = QtWidgets.QPushButton("Add selected region(s)")
        add_button.clicked.connect(self._add_selected_regions)
        v.addWidget(add_button)

        return box

    def _build_layers_group(self) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("Layers")
        v = QtWidgets.QVBoxLayout(box)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        container = QtWidgets.QWidget()
        self._layers_vbox = QtWidgets.QVBoxLayout(container)
        self._layers_vbox.setContentsMargins(0, 0, 0, 0)
        self._layers_vbox.setSpacing(2)
        self._layers_vbox.addStretch(1)
        scroll.setWidget(container)
        v.addWidget(scroll, 1)

        clear_button = QtWidgets.QPushButton("Clear all layers")
        clear_button.clicked.connect(self._clear_all_layers)
        v.addWidget(clear_button)

        return box

    def _build_camera_group(self) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("View")
        grid = QtWidgets.QGridLayout(box)
        grid.setSpacing(4)

        presets = [
            ("L",   "left"),
            ("R",   "right"),
            ("A",   "anterior"),
            ("P",   "posterior"),
            ("Sup", "superior"),
            ("Inf", "inferior"),
            ("Obl", "oblique"),
        ]
        for i, (label, preset_id) in enumerate(presets):
            btn = QtWidgets.QPushButton(label)
            btn.setToolTip(preset_id.capitalize())
            btn.clicked.connect(lambda _checked=False, p=preset_id: self.scene.set_camera_preset(p))
            grid.addWidget(btn, i // 4, i % 4)
        return box

    def _build_export_group(self) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("Export")
        v = QtWidgets.QVBoxLayout(box)
        btn = QtWidgets.QPushButton("Export PNG…")
        btn.clicked.connect(self._open_export_dialog)
        v.addWidget(btn)
        return box

    # ---- Behaviour ----------------------------------------------------------

    def _init_defaults(self) -> None:
        if self.template_combo.count() > 0:
            self._on_template_changed(self.template_combo.currentIndex())
        if self.atlas_combo.count() > 0:
            self._on_atlas_changed(self.atlas_combo.currentIndex())

    def _on_template_changed(self, _index: int) -> None:
        tid = self.template_combo.currentData()
        if not tid:
            return
        opacity = self.template_opacity_slider.value() / 100.0
        visible = self.template_visible_check.isChecked()
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            self.scene.set_template(tid, opacity=opacity, visible=visible)
        except Exception as exc:
            QtWidgets.QApplication.restoreOverrideCursor()
            QtWidgets.QMessageBox.warning(
                self, "Template load failed", f"Could not load template {tid!r}:\n{exc}"
            )
            return
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def _on_atlas_changed(self, _index: int) -> None:
        aid = self.atlas_combo.currentData()
        if not aid:
            return
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            atlas = self.atlases.get_atlas(aid)
        except Exception as exc:
            QtWidgets.QApplication.restoreOverrideCursor()
            self.region_list.clear()
            QtWidgets.QMessageBox.warning(
                self, "Atlas load failed",
                f"Could not load atlas {aid!r}:\n{exc}",
            )
            return
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

        self.region_list.clear()
        for label in atlas.labels:
            item = QtWidgets.QListWidgetItem(label.name)
            item.setData(QtCore.Qt.UserRole, label.index)
            self.region_list.addItem(item)
        self._apply_region_filter(self.filter_edit.text())

    def _apply_region_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for row in range(self.region_list.count()):
            item = self.region_list.item(row)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def _next_color(self) -> tuple[float, float, float]:
        color = config.DEFAULT_PALETTE[self._palette_idx % len(config.DEFAULT_PALETTE)]
        self._palette_idx += 1
        return color

    def _add_selected_regions(self) -> None:
        aid = self.atlas_combo.currentData()
        if not aid:
            return
        items = self.region_list.selectedItems()
        if not items:
            return
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            for item in items:
                label_index = int(item.data(QtCore.Qt.UserRole))
                color = self._next_color()
                try:
                    layer_id = self.scene.add_layer(
                        aid, label_index, color=color, opacity=1.0, show_label=False
                    )
                except ValueError as e:
                    QtWidgets.QMessageBox.warning(self, "Empty region", str(e))
                    continue
                self._add_layer_row(layer_id, item.text(), color, 1.0, False)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def _add_layer_row(
        self,
        layer_id: str,
        display_name: str,
        color: tuple[float, float, float],
        opacity: float,
        show_label: bool,
    ) -> None:
        row = LayerRow(layer_id, display_name, color, opacity, show_label)
        row.colorChanged.connect(
            lambda lid, c: self.scene.update_layer(lid, color=c)
        )
        row.opacityChanged.connect(
            lambda lid, o: self.scene.update_layer(lid, opacity=o)
        )
        row.labelToggled.connect(
            lambda lid, v: self.scene.update_layer(lid, show_label=v)
        )
        row.removeRequested.connect(self._remove_layer)
        self._layers_vbox.insertWidget(self._layers_vbox.count() - 1, row)
        self._layer_rows[layer_id] = row

    def _remove_layer(self, layer_id: str) -> None:
        self.scene.remove_layer(layer_id)
        row = self._layer_rows.pop(layer_id, None)
        if row is not None:
            row.setParent(None)
            row.deleteLater()

    def _clear_all_layers(self) -> None:
        for lid in list(self._layer_rows.keys()):
            self._remove_layer(lid)

    def _open_export_dialog(self) -> None:
        dialog = ExportDialog(self, default_dir=Path.home())
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            settings = dialog.settings()
            self._run_export(settings)

    def _run_export(self, s: ExportSettings) -> None:
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            path = self.scene.export_png(
                s.path, width_px=s.width_px, dpi=s.dpi, transparent=s.transparent
            )
        except Exception as exc:
            QtWidgets.QApplication.restoreOverrideCursor()
            QtWidgets.QMessageBox.critical(self, "Export failed", str(exc))
            return
        QtWidgets.QApplication.restoreOverrideCursor()
        QtWidgets.QMessageBox.information(self, "Export complete", f"Saved to:\n{path}")
