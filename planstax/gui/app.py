"""GUI entry point."""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QLibraryInfo, QLocale, QPointF, Qt, QTranslator
from PySide6.QtGui import QBrush, QColor, QIcon, QLinearGradient, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QApplication

from .. import APP_NAME, __version__


def make_icon_pixmap(size: int = 256) -> QPixmap:
    """A banded planet drawn with QPainter (no image file needed)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = size / 2.0
    r = size * 0.42
    grad = QLinearGradient(0, c - r, 0, c + r)
    stops = [(0.0, "#c9a27a"), (0.18, "#e9d2b0"), (0.30, "#a8724a"), (0.42, "#f1e1c6"),
             (0.55, "#b88358"), (0.68, "#ead6b6"), (0.82, "#9c6a45"), (1.0, "#d8bb96")]
    for pos, col in stops:
        grad.setColorAt(pos, QColor(col))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(grad))
    p.drawEllipse(QPointF(c, c), r, r)
    shade = QRadialGradient(QPointF(c - r * 0.35, c - r * 0.35), r * 1.5)
    shade.setColorAt(0.0, QColor(255, 255, 255, 40))
    shade.setColorAt(0.6, QColor(0, 0, 0, 0))
    shade.setColorAt(1.0, QColor(0, 0, 0, 170))
    p.setBrush(QBrush(shade))
    p.drawEllipse(QPointF(c, c), r, r)
    p.setBrush(QColor("#b5533a"))
    p.drawEllipse(QPointF(c + r * 0.3, c + r * 0.28), r * 0.17, r * 0.1)
    pen = QPen(QColor(255, 255, 255, 90))
    pen.setWidthF(size / 64)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(c, c), r, r)
    p.end()
    return pm


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    if os.name == "nt":
        # Own taskbar identity, so Windows shows our icon rather than the Python launcher's.
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PlanStax.PlanStax")
        except (AttributeError, OSError):
            pass
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(make_icon_pixmap()))
    # Qt's own texts (OK / Annuler in dialogs) in the system language.
    translator = QTranslator(app)
    if translator.load(QLocale.system(), "qtbase", "_",
                       QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)

    from .mainwindow import MainWindow
    win = MainWindow()
    win.show()
    files = [a for a in argv[1:] if os.path.exists(a)]
    if files:
        ext = os.path.splitext(files[0])[1].lower()
        from ..io import IMAGE_EXTENSIONS
        if len(files) == 1 and ext in IMAGE_EXTENSIONS:
            win.load_image(files[0])
        else:
            win.load_source(files)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
