"""Entry point: `python -m brain_viewer` boots the Qt app."""

from __future__ import annotations

import sys

from PySide6 import QtCore, QtWidgets


def main() -> int:
    QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
        QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setApplicationName("brain_viewer")
    app.setApplicationDisplayName("brain_viewer")
    app.setDesktopFileName("brain_viewer")

    # Delay heavy imports until after QApplication exists to avoid Qt platform issues.
    from .icons import get_app_icon
    from .ui.main_window import MainWindow

    app.setWindowIcon(get_app_icon())

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
