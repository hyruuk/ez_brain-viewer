"""One row in the template-shells list: visibility, name, opacity, remove."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class TemplateRow(QtWidgets.QFrame):
    visibilityToggled = QtCore.Signal(str, bool)   # template_id, visible
    opacityChanged = QtCore.Signal(str, float)     # template_id, opacity 0-1
    removeRequested = QtCore.Signal(str)           # template_id

    def __init__(
        self,
        template_id: str,
        display_name: str,
        opacity: float,
        visible: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.template_id = template_id
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setLineWidth(1)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        self.visible_checkbox = QtWidgets.QCheckBox()
        self.visible_checkbox.setChecked(visible)
        self.visible_checkbox.setToolTip("Show / hide this shell")
        self.visible_checkbox.toggled.connect(self._on_visibility_toggled)
        layout.addWidget(self.visible_checkbox)

        self.name_label = QtWidgets.QLabel(display_name)
        self.name_label.setToolTip(display_name)
        self.name_label.setMinimumWidth(120)
        self.name_label.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
        )
        layout.addWidget(self.name_label, 1)

        self.opacity_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(int(round(opacity * 100)))
        self.opacity_slider.setFixedWidth(100)
        self.opacity_slider.setToolTip("Opacity")
        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacityChanged.emit(self.template_id, v / 100.0)
        )
        layout.addWidget(self.opacity_slider)

        self.remove_button = QtWidgets.QPushButton("✕")
        self.remove_button.setFixedSize(22, 22)
        self.remove_button.setToolTip("Remove shell")
        self.remove_button.clicked.connect(
            lambda: self.removeRequested.emit(self.template_id)
        )
        layout.addWidget(self.remove_button)

    def _on_visibility_toggled(self, checked: bool) -> None:
        self.name_label.setEnabled(checked)
        self.opacity_slider.setEnabled(checked)
        self.visibilityToggled.emit(self.template_id, checked)

    def set_opacity(self, opacity: float) -> None:
        self.opacity_slider.blockSignals(True)
        self.opacity_slider.setValue(int(round(opacity * 100)))
        self.opacity_slider.blockSignals(False)
