"""Zoomable image viewer with an alignment-point overlay."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView


def to_qimage(img: np.ndarray) -> QImage:
    """float [0,1] (HxW or HxWx3) → 8-bit QImage (copied, owns its memory)."""
    data = np.clip(img, 0.0, 1.0)
    data = np.ascontiguousarray((data * 255.0 + 0.5).astype(np.uint8))
    h, w = data.shape[:2]
    if data.ndim == 2:
        q = QImage(data.data, w, h, w, QImage.Format.Format_Grayscale8)
    else:
        q = QImage(data.data, w, h, 3 * w, QImage.Format.Format_RGB888)
    return q.copy()


class PointsItem(QGraphicsItem):
    """Draws all alignment boxes in one item (hundreds of QGraphicsRectItems would be slow)."""

    def __init__(self) -> None:
        super().__init__()
        self.points = np.zeros((0, 2))
        self.box = 32
        self.bounds = QRectF()
        self.color = QColor(80, 220, 120)
        self.setZValue(10)

    def set_points(self, points: np.ndarray, box: int, bounds: QRectF) -> None:
        self.prepareGeometryChange()
        self.points = np.asarray(points, dtype=float).reshape(-1, 2)
        self.box = box
        self.bounds = bounds
        self.update()

    def boundingRect(self) -> QRectF:
        return self.bounds.adjusted(-self.box, -self.box, self.box, self.box)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        pen = QPen(self.color)
        pen.setCosmetic(True)
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        h = self.box / 2.0
        for x, y in self.points:
            painter.drawRect(QRectF(x - h + 0.5, y - h + 0.5, self.box, self.box))


class ImageView(QGraphicsView):
    addPointRequested = Signal(float, float)
    removePointRequested = Signal(float, float)
    zoomChanged = Signal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self._pixmap = QGraphicsPixmapItem()
        self._pixmap.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.scene().addItem(self._pixmap)
        self._points = PointsItem()
        self.scene().addItem(self._points)
        self._fit = True
        self._has_image = False
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setBackgroundBrush(QColor(18, 18, 20))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)

    # ------------------------------------------------------------ content
    def set_image(self, img: np.ndarray | None, keep_view: bool = True) -> None:
        if img is None:
            self._pixmap.setPixmap(QPixmap())
            self._has_image = False
            return
        size_changed = (not self._has_image or self._pixmap.pixmap().width() != img.shape[1]
                        or self._pixmap.pixmap().height() != img.shape[0])
        self._pixmap.setPixmap(QPixmap.fromImage(to_qimage(img)))
        self._has_image = True
        self.scene().setSceneRect(QRectF(0, 0, img.shape[1], img.shape[0]))
        if size_changed or not keep_view or self._fit:
            self.fit()

    def set_points(self, points: np.ndarray | None, box: int = 32) -> None:
        if points is None:
            points = np.zeros((0, 2))
        self._points.set_points(points, box, self.scene().sceneRect())

    def show_points(self, visible: bool) -> None:
        self._points.setVisible(visible)

    def set_point_color(self, color: QColor) -> None:
        self._points.color = color
        self._points.update()

    # ------------------------------------------------------------ zoom
    def fit(self) -> None:
        if not self._has_image:
            return
        self._fit = True
        self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.zoomChanged.emit(self.transform().m11())

    def zoom_to(self, factor: float) -> None:
        self._fit = False
        self.resetTransform()
        self.scale(factor, factor)
        self.zoomChanged.emit(factor)

    def zoom_by(self, factor: float) -> None:
        current = self.transform().m11()
        target = min(32.0, max(0.05, current * factor))
        self._fit = False
        self.scale(target / current, target / current)
        self.zoomChanged.emit(target)

    def wheelEvent(self, event) -> None:
        if not self._has_image:
            return
        self.zoom_by(1.25 if event.angleDelta().y() > 0 else 0.8)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fit:
            self.fit()

    def mouseDoubleClickEvent(self, event) -> None:
        self.fit()

    # ------------------------------------------------------------ point editing
    def mousePressEvent(self, event) -> None:
        mods = event.modifiers()
        if self._has_image and event.button() == Qt.MouseButton.LeftButton and (
                mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)):
            p: QPointF = self.mapToScene(event.position().toPoint())
            if mods & Qt.KeyboardModifier.ShiftModifier:
                self.removePointRequested.emit(p.x(), p.y())
            else:
                self.addPointRequested.emit(p.x(), p.y())
            event.accept()
            return
        super().mousePressEvent(event)
