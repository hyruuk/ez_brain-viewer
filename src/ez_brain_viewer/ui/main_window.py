"""Main application window: QtInteractor central, dockable control panel on the left."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from pyvistaqt import QtInteractor

from ..atlases import AtlasRegistry
from ..external_atlases import EXTERNAL_ENTRIES
from ..icons import get_app_icon
from ..meshing import MeshBuilder
from ..scene import SceneManager
from ..templates import TemplateRegistry
from .control_panel import ControlPanel


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Brain viewer")
        self.setWindowIcon(get_app_icon())
        self.resize(1400, 900)

        # 3D viewer as central widget.
        self.viewer = QtInteractor(self)
        self.setCentralWidget(self.viewer)

        # Core services.
        self.atlases = AtlasRegistry()
        self.atlases.register_external(EXTERNAL_ENTRIES)
        self.templates = TemplateRegistry()
        self.mesh_builder = MeshBuilder()
        self.scene = SceneManager(
            self.viewer, self.atlases, self.templates, self.mesh_builder
        )

        # Left dock: control panel.
        self.control_panel = ControlPanel(
            self.scene, self.atlases, self.templates, parent=self
        )
        dock = QtWidgets.QDockWidget("Controls", self)
        dock.setWidget(self.control_panel)
        dock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
        dock.setFeatures(
            QtWidgets.QDockWidget.DockWidgetMovable | QtWidgets.QDockWidget.DockWidgetFloatable
        )
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock)
        dock.setMinimumWidth(320)

        # Menu.
        file_menu = self.menuBar().addMenu("&File")
        export_action = QtGui.QAction("Export PNG…", self)
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(self.control_panel._open_export_dialog)
        file_menu.addAction(export_action)
        file_menu.addSeparator()
        quit_action = QtGui.QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        # Ensure VTK resources are released cleanly.
        try:
            self.viewer.close()
        except Exception:
            pass
        super().closeEvent(event)
