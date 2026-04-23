"""Entry point: `python -m ez_brain_viewer` boots the Qt app."""

from __future__ import annotations

import sys

from PySide6 import QtCore, QtWidgets


def main() -> int:
    QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
        QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setApplicationName("ez_brain_viewer")         # used by QSettings / QStandardPaths
    app.setApplicationDisplayName("EZ Brain Viewer")  # user-facing

    # Silence the xdg-desktop-portal DBus warning that fires when the session bus
    # is already bound to another app ID — harmless, but noisy on stdout.
    QtCore.QLoggingCategory.setFilterRules("qt.qpa.services.warning=false")

    # Delay heavy imports until after QApplication exists to avoid Qt platform issues.
    from .icons import get_app_icon
    from .ui.main_window import MainWindow

    app.setWindowIcon(get_app_icon())

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
