"""Left-hand control panel: template / atlas / regions / layers / camera / export."""

from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from .. import config
from ..atlases import AtlasRegistry
from ..icons import get_app_icon
from ..scene import SceneManager
from ..templates import TemplateRegistry
from .. import custom_atlases
from .custom_atlas_dialog import CustomAtlasDialog
from .export_dialog import ExportDialog, ExportSettings
from .layer_row import LayerRow
from .template_row import TemplateRow


DEFAULT_STARTING_TEMPLATE = "mni152_detailed"
DEFAULT_STARTING_ATLAS = "harvard_oxford_cort"


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
        self._template_rows: dict[str, TemplateRow] = {}
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
        box = QtWidgets.QGroupBox("Template shells")
        v = QtWidgets.QVBoxLayout(box)

        add_row = QtWidgets.QHBoxLayout()
        self.template_combo = QtWidgets.QComboBox()
        for tid, name in self.templates.list_templates():
            self.template_combo.addItem(name, tid)
        add_row.addWidget(self.template_combo, 1)

        add_btn = QtWidgets.QPushButton("Add shell")
        add_btn.clicked.connect(self._add_selected_template)
        add_row.addWidget(add_btn)
        v.addLayout(add_row)

        self.cull_backfaces_check = QtWidgets.QCheckBox("Cull back faces of shells")
        self.cull_backfaces_check.setToolTip(
            "On: draw only the near-camera side of each shell (cleaner interior).\n"
            "Off: draw both sides (you'll see the back of the brain through the front)."
        )
        self.cull_backfaces_check.setChecked(True)
        self.cull_backfaces_check.toggled.connect(self.scene.set_shell_backface_culling)
        v.addWidget(self.cull_backfaces_check)

        # Scrollable stack of active shells.
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(90)
        container = QtWidgets.QWidget()
        self._templates_vbox = QtWidgets.QVBoxLayout(container)
        self._templates_vbox.setContentsMargins(0, 0, 0, 0)
        self._templates_vbox.setSpacing(2)
        self._templates_vbox.addStretch(1)
        scroll.setWidget(container)
        v.addWidget(scroll)

        return box

    def _build_atlas_group(self) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("Atlas")
        v = QtWidgets.QVBoxLayout(box)

        atlas_row = QtWidgets.QHBoxLayout()
        self.atlas_combo = QtWidgets.QComboBox()
        self._repopulate_atlas_combo(select_id=None)
        self.atlas_combo.currentIndexChanged.connect(self._on_atlas_changed)
        atlas_row.addWidget(self.atlas_combo, 1)

        self.add_custom_atlas_btn = QtWidgets.QPushButton("+")
        self.add_custom_atlas_btn.setFixedWidth(26)
        self.add_custom_atlas_btn.setToolTip("Add custom atlas (NIfTI file or URL)")
        self.add_custom_atlas_btn.clicked.connect(self._open_custom_atlas_dialog)
        atlas_row.addWidget(self.add_custom_atlas_btn)

        self.remove_custom_atlas_btn = QtWidgets.QPushButton("✕")
        self.remove_custom_atlas_btn.setFixedWidth(26)
        self.remove_custom_atlas_btn.setToolTip("Remove the currently selected custom atlas")
        self.remove_custom_atlas_btn.clicked.connect(self._remove_current_custom_atlas)
        self.remove_custom_atlas_btn.setEnabled(False)
        atlas_row.addWidget(self.remove_custom_atlas_btn)
        v.addLayout(atlas_row)

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
        btn = QtWidgets.QPushButton("Export figure…")
        btn.clicked.connect(self._open_export_dialog)
        v.addWidget(btn)
        return box

    # ---- Behaviour ----------------------------------------------------------

    def _init_defaults(self) -> None:
        # Auto-add the default starting shell.
        for i in range(self.template_combo.count()):
            if self.template_combo.itemData(i) == DEFAULT_STARTING_TEMPLATE:
                self.template_combo.setCurrentIndex(i)
                break
        self._add_selected_template()
        if self.atlas_combo.count() > 0:
            for i in range(self.atlas_combo.count()):
                if self.atlas_combo.itemData(i) == DEFAULT_STARTING_ATLAS:
                    self.atlas_combo.setCurrentIndex(i)
                    break
            self._on_atlas_changed(self.atlas_combo.currentIndex())

    def _add_selected_template(self) -> None:
        tid = self.template_combo.currentData()
        if not tid or tid in self._template_rows:
            return
        display_name = self.template_combo.currentText()
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            self.scene.add_template(tid, opacity=config.DEFAULT_TEMPLATE_OPACITY)
        except Exception as exc:
            QtWidgets.QApplication.restoreOverrideCursor()
            QtWidgets.QMessageBox.warning(
                self, "Template load failed", f"Could not load template {tid!r}:\n{exc}"
            )
            return
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self._add_template_row(tid, display_name, config.DEFAULT_TEMPLATE_OPACITY, True)

    def _add_template_row(
        self,
        template_id: str,
        display_name: str,
        opacity: float,
        visible: bool,
    ) -> None:
        row = TemplateRow(template_id, display_name, opacity, visible)
        row.visibilityToggled.connect(
            lambda tid, v: self.scene.update_template(tid, visible=v)
        )
        row.opacityChanged.connect(
            lambda tid, o: self.scene.update_template(tid, opacity=o)
        )
        row.removeRequested.connect(self._remove_template)
        self._templates_vbox.insertWidget(self._templates_vbox.count() - 1, row)
        self._template_rows[template_id] = row

    def _remove_template(self, template_id: str) -> None:
        self.scene.remove_template(template_id)
        row = self._template_rows.pop(template_id, None)
        if row is not None:
            row.setParent(None)
            row.deleteLater()

    def _repopulate_atlas_combo(self, select_id: str | None) -> None:
        """Rebuild the atlas dropdown (preserves or switches selection)."""
        self.atlas_combo.blockSignals(True)
        try:
            self.atlas_combo.clear()
            for aid, name in self.atlases.list_atlases():
                self.atlas_combo.addItem(name, aid)
            if select_id is not None:
                for i in range(self.atlas_combo.count()):
                    if self.atlas_combo.itemData(i) == select_id:
                        self.atlas_combo.setCurrentIndex(i)
                        break
        finally:
            self.atlas_combo.blockSignals(False)

    def _on_atlas_changed(self, _index: int) -> None:
        aid = self.atlas_combo.currentData()
        if hasattr(self, "remove_custom_atlas_btn"):
            self.remove_custom_atlas_btn.setEnabled(
                bool(aid) and aid.startswith(custom_atlases.CUSTOM_ID_PREFIX)
            )
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

    def _open_custom_atlas_dialog(self) -> None:
        dialog = CustomAtlasDialog(self)
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return
        data = dialog.input()
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            spec = custom_atlases.add_custom_atlas(
                data.display_name,
                data.volume_source,
                data.labels_source,
            )
        except Exception as exc:
            QtWidgets.QApplication.restoreOverrideCursor()
            QtWidgets.QMessageBox.critical(
                self, "Add atlas failed", f"Could not register custom atlas:\n{exc}"
            )
            return
        QtWidgets.QApplication.restoreOverrideCursor()

        self._repopulate_atlas_combo(select_id=spec.id)
        # Trigger loading the region list for the newly selected atlas.
        self._on_atlas_changed(self.atlas_combo.currentIndex())

    def _remove_current_custom_atlas(self) -> None:
        aid = self.atlas_combo.currentData()
        if not aid or not aid.startswith(custom_atlases.CUSTOM_ID_PREFIX):
            return
        label = self.atlas_combo.currentText()
        reply = QtWidgets.QMessageBox.question(
            self,
            "Remove custom atlas",
            f"Remove {label!r}?\n\nThis deletes its cached NIfTI and labels from disk.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        custom_atlases.remove_custom_atlas(aid)
        self.atlases.invalidate(aid)
        self._repopulate_atlas_combo(select_id=None)
        self._on_atlas_changed(self.atlas_combo.currentIndex())

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
        row = LayerRow(layer_id, display_name, color, opacity, show_label, visible=True)
        row.colorChanged.connect(
            lambda lid, c: self.scene.update_layer(lid, color=c)
        )
        row.opacityChanged.connect(
            lambda lid, o: self.scene.update_layer(lid, opacity=o)
        )
        row.labelToggled.connect(
            lambda lid, v: self.scene.update_layer(lid, show_label=v)
        )
        row.visibilityToggled.connect(
            lambda lid, v: self.scene.update_layer(lid, visible=v)
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

    # ---- Scene save / load --------------------------------------------------

    def _reapply_window_icon(self) -> None:
        """Some Linux Qt platforms (xdg-desktop-portal paths) drop the window
        icon after a modal QFileDialog closes — re-set it to be safe."""
        window = self.window()
        if window is None:
            return
        icon = get_app_icon()
        window.setWindowIcon(icon)
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.setWindowIcon(icon)

    def save_scene_to_file(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save scene",
            str(Path.home() / "scene.ezbv.json"),
            "ezbv scene (*.ezbv.json *.json)",
        )
        self._reapply_window_icon()
        if not path:
            return
        if not path.lower().endswith((".json", ".ezbv.json")):
            path += ".ezbv.json"
        try:
            saved = self.scene.save_scene(path)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Save failed", str(exc))
            return
        QtWidgets.QMessageBox.information(
            self, "Scene saved", f"Wrote:\n{saved}"
        )

    def open_scene_from_file(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open scene",
            str(Path.home()),
            "ezbv scene (*.ezbv.json *.json);;All files (*)",
        )
        self._reapply_window_icon()
        if not path:
            return
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            warnings = self.scene.load_scene(path)
        except Exception as exc:
            QtWidgets.QApplication.restoreOverrideCursor()
            QtWidgets.QMessageBox.critical(self, "Open failed", str(exc))
            return
        QtWidgets.QApplication.restoreOverrideCursor()

        self._rebuild_rows_from_scene()

        if warnings:
            QtWidgets.QMessageBox.warning(
                self,
                "Scene loaded with warnings",
                "Some items could not be restored:\n\n" + "\n".join(warnings),
            )

    def _rebuild_rows_from_scene(self) -> None:
        """Tear down and re-create left-panel rows to match current scene state."""
        # Clear template rows.
        for tid in list(self._template_rows.keys()):
            row = self._template_rows.pop(tid)
            row.setParent(None)
            row.deleteLater()
        # Clear layer rows.
        for lid in list(self._layer_rows.keys()):
            row = self._layer_rows.pop(lid)
            row.setParent(None)
            row.deleteLater()

        # Sync cull-backfaces checkbox (without re-triggering the scene handler).
        self.cull_backfaces_check.blockSignals(True)
        self.cull_backfaces_check.setChecked(bool(self.scene._cull_backfaces))
        self.cull_backfaces_check.blockSignals(False)

        # Rebuild template rows from scene state.
        for tid, shell in self.scene.template_shells.items():
            self._add_template_row(tid, shell.name, shell.opacity, shell.visible)

        # Rebuild layer rows from scene state.
        for lid, layer in self.scene.layers.items():
            self._add_layer_row(
                lid, layer.label_name, layer.color, layer.opacity, layer.show_label
            )
            if not layer.visible:
                # Reflect hidden state in the row without re-triggering scene.update_layer.
                row = self._layer_rows[lid]
                row.visible_checkbox.blockSignals(True)
                row.visible_checkbox.setChecked(False)
                row.name_label.setEnabled(False)
                row.swatch.setEnabled(False)
                row.opacity_slider.setEnabled(False)
                row.label_checkbox.setEnabled(False)
                row.visible_checkbox.blockSignals(False)

    def _run_export(self, s: ExportSettings) -> None:
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            if s.format == "gif":
                path = self.scene.export_gif(
                    s.path,
                    width_px=s.width_px,
                    rotation_axis=s.rotation_axis,
                    rotation_deg=s.rotation_deg,
                    n_frames=s.n_frames,
                    cycle_duration_s=s.cycle_duration_s,
                )
            else:
                path = self.scene.export_png(
                    s.path, width_px=s.width_px, dpi=s.dpi, transparent=s.transparent
                )
        except Exception as exc:
            QtWidgets.QApplication.restoreOverrideCursor()
            QtWidgets.QMessageBox.critical(self, "Export failed", str(exc))
            return
        QtWidgets.QApplication.restoreOverrideCursor()
        QtWidgets.QMessageBox.information(self, "Export complete", f"Saved to:\n{path}")
