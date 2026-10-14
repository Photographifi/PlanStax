"""Small reusable widgets: slider+spinbox pair, quality curve, form helpers."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QSizePolicy, QSlider, QSpinBox, QWidget)


class ValueSlider(QWidget):
    """Horizontal slider coupled to a spin box. Emits valueChanged(float)."""

    valueChanged = Signal(float)

    def __init__(self, minimum: float, maximum: float, step: float, value: float,
                 decimals: int = 2, parent=None) -> None:
        super().__init__(parent)
        self._min, self._max, self._step = minimum, maximum, step
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, int(round((maximum - minimum) / step)))
        self.spin = QDoubleSpinBox()
        self.spin.setRange(minimum, maximum)
        self.spin.setSingleStep(step)
        self.spin.setDecimals(decimals)
        self.spin.setKeyboardTracking(False)
        self.spin.setFixedWidth(72)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.spin)
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)
        self.setValue(value)

    def value(self) -> float:
        return float(self.spin.value())

    def setValue(self, v: float) -> None:
        with QSignalBlocker(self.spin), QSignalBlocker(self.slider):
            self.spin.setValue(v)
            self.slider.setValue(int(round((v - self._min) / self._step)))

    def _from_slider(self, pos: int) -> None:
        v = self._min + pos * self._step
        with QSignalBlocker(self.spin):
            self.spin.setValue(v)
        self.valueChanged.emit(self.value())

    def _from_spin(self, v: float) -> None:
        with QSignalBlocker(self.slider):
            self.slider.setValue(int(round((v - self._min) / self._step)))
        self.valueChanged.emit(float(v))


def spin(minimum: int, maximum: int, value: int, suffix: str = "", step: int = 1) -> QSpinBox:
    s = QSpinBox()
    s.setRange(minimum, maximum)
    s.setValue(value)
    s.setSingleStep(step)
    s.setKeyboardTracking(False)
    if suffix:
        s.setSuffix(suffix)
    return s


def dspin(minimum: float, maximum: float, value: float, step: float = 0.1, decimals: int = 2,
          suffix: str = "") -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(minimum, maximum)
    s.setDecimals(decimals)
    s.setSingleStep(step)
    s.setValue(value)
    s.setKeyboardTracking(False)
    if suffix:
        s.setSuffix(suffix)
    return s


def group(title: str) -> tuple[QGroupBox, QFormLayout]:
    box = QGroupBox(title)
    form = QFormLayout(box)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    return box, form


def hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setProperty("hint", True)
    lbl.setStyleSheet("color: palette(mid); font-size: 9pt;")
    return lbl


class QualityPlot(QWidget):
    """Frame qualities sorted best → worst, with the selection cut-off.
    Clicking sets the cut-off (emits cutoffRequested(fraction of frames kept))."""

    cutoffRequested = Signal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._q = np.zeros(0)
        self._keep = 0
        self.setMinimumHeight(140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setToolTip("Cliquez pour choisir combien d'images garder")

    def set_data(self, quality: np.ndarray | None, keep: int) -> None:
        if quality is None or not len(quality):
            self._q = np.zeros(0)
        else:
            q = np.sort(np.asarray(quality, dtype=float))[::-1]
            self._q = q / max(q[0], 1e-12)
        self._keep = keep
        self.update()

    def _plot_rect(self) -> QRectF:
        return QRectF(36, 8, max(10, self.width() - 44), max(10, self.height() - 28))

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        r = self._plot_rect()
        p.fillRect(self.rect(), pal.base())
        p.setPen(QPen(pal.mid().color(), 1))
        p.drawRect(r)
        p.setPen(pal.text().color())
        font = p.font()
        font.setPointSizeF(max(7.0, font.pointSizeF() - 1.5))
        p.setFont(font)
        p.drawText(QRectF(0, r.top() - 6, 32, 14), Qt.AlignmentFlag.AlignRight, "100%")
        p.drawText(QRectF(0, r.bottom() - 8, 32, 14), Qt.AlignmentFlag.AlignRight, "0%")
        n = len(self._q)
        if n == 0:
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "Pas encore d'analyse")
            return
        p.drawText(QRectF(r.left(), r.bottom() + 2, r.width(), 16), Qt.AlignmentFlag.AlignLeft,
                   "meilleure")
        p.drawText(QRectF(r.left(), r.bottom() + 2, r.width(), 16), Qt.AlignmentFlag.AlignRight,
                   f"pire (n = {n})")
        xs = r.left() + np.arange(n) / max(n - 1, 1) * r.width()
        ys = r.bottom() - np.clip(self._q, 0, 1) * r.height()
        kept_x = r.left() + (self._keep - 0.5) / max(n - 1, 1) * r.width()
        p.fillRect(QRectF(r.left(), r.top(), max(0.0, kept_x - r.left()), r.height()),
                   QColor(80, 160, 255, 40))
        path = QPainterPath(QPointF(xs[0], ys[0]))
        step = max(1, n // 800)
        for x, y in zip(xs[::step], ys[::step]):
            path.lineTo(QPointF(x, y))
        path.lineTo(QPointF(xs[-1], ys[-1]))
        p.setPen(QPen(QColor(90, 170, 255), 1.6))
        p.drawPath(path)
        p.setPen(QPen(QColor(255, 120, 80), 1.4, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(kept_x, r.top()), QPointF(kept_x, r.bottom()))

    def mousePressEvent(self, event) -> None:
        r = self._plot_rect()
        if len(self._q) and r.width() > 0:
            frac = (event.position().x() - r.left()) / r.width()
            self.cutoffRequested.emit(float(np.clip(frac, 0.0, 1.0)))
