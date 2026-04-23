"""One row in the layer list: color swatch, opacity slider, label toggle, remove button."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


class ColorSwatch(QtWidgets.QPushButton):
    colorPicked = QtCore.Signal(QtGui.QColor)

    def __init__(self, color: QtGui.QColor, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 22)
        self.setFlat(True)
        self._color = color
        self._apply_style()
        self.clicked.connect(self._open_dialog)

    def color(self) -> QtGui.QColor:
        return self._color

    def set_color(self, color: QtGui.QColor) -> None:
        self._color = color
        self._apply_style()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            f"QPushButton {{ background-color: {self._color.name()};"
            f" border: 1px solid #555; border-radius: 3px; }}"
        )

    def _open_dialog(self) -> None:
        color = QtWidgets.QColorDialog.getColor(self._color, self, "Pick region color")
        if color.isValid():
            self.set_color(color)
            self.colorPicked.emit(color)


class LayerRow(QtWidgets.QFrame):
    colorChanged = QtCore.Signal(str, tuple)      # layer_id, (r, g, b)
    opacityChanged = QtCore.Signal(str, float)    # layer_id, opacity 0–1
    labelToggled = QtCore.Signal(str, bool)       # layer_id, show_label
    visibilityToggled = QtCore.Signal(str, bool)  # layer_id, visible
    removeRequested = QtCore.Signal(str)          # layer_id

    def __init__(
        self,
        layer_id: str,
        display_name: str,
        color: tuple[float, float, float],
        opacity: float,
        show_label: bool,
        visible: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.layer_id = layer_id
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setLineWidth(1)

        qcolor = QtGui.QColor.fromRgbF(*color)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        self.visible_checkbox = QtWidgets.QCheckBox()
        self.visible_checkbox.setChecked(visible)
        self.visible_checkbox.setToolTip("Show / hide this layer")
        self.visible_checkbox.toggled.connect(self._on_visibility_toggled)
        layout.addWidget(self.visible_checkbox)

        self.swatch = ColorSwatch(qcolor)
        self.swatch.colorPicked.connect(self._on_color_picked)
        layout.addWidget(self.swatch)

        self.name_label = QtWidgets.QLabel(display_name)
        self.name_label.setToolTip(display_name)
        self.name_label.setMinimumWidth(120)
        self.name_label.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
        )
        layout.addWidget(self.name_label, 1)

        self.opacity_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.opacity_slider.setRange(5, 100)
        self.opacity_slider.setValue(int(round(opacity * 100)))
        self.opacity_slider.setFixedWidth(90)
        self.opacity_slider.setToolTip("Opacity")
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        layout.addWidget(self.opacity_slider)

        self.label_checkbox = QtWidgets.QCheckBox("label")
        self.label_checkbox.setChecked(show_label)
        self.label_checkbox.toggled.connect(self._on_label_toggled)
        layout.addWidget(self.label_checkbox)

        self.remove_button = QtWidgets.QPushButton("✕")
        self.remove_button.setFixedSize(22, 22)
        self.remove_button.setToolTip("Remove layer")
        self.remove_button.clicked.connect(lambda: self.removeRequested.emit(self.layer_id))
        layout.addWidget(self.remove_button)

    def _on_color_picked(self, qc: QtGui.QColor) -> None:
        self.colorChanged.emit(self.layer_id, (qc.redF(), qc.greenF(), qc.blueF()))

    def _on_opacity_changed(self, value: int) -> None:
        self.opacityChanged.emit(self.layer_id, value / 100.0)

    def _on_label_toggled(self, checked: bool) -> None:
        self.labelToggled.emit(self.layer_id, checked)

    def _on_visibility_toggled(self, checked: bool) -> None:
        # Dim the row when hidden so it's visually obvious from the list.
        self.name_label.setEnabled(checked)
        self.swatch.setEnabled(checked)
        self.opacity_slider.setEnabled(checked)
        self.label_checkbox.setEnabled(checked)
        self.visibilityToggled.emit(self.layer_id, checked)
