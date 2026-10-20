"""Mosaic window: overlapping images (the « output » folder of a batch…) → one large image."""

from __future__ import annotations

import os
import threading
import traceback

from PySide6.QtCore import QPointF, QSettings, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog,
                               QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSplitter,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..batch import FORMATS, MosaicResult, list_images, make_mosaics
from ..core import Cancelled
from ..i18n import megabytes, tr
from ..io import IMAGE_EXTENSIONS
from ..paths import default_batch_folders
from ..settings import list_presets, load_preset
from .imageview import to_qimage

COL_NAME, COL_SIZE, COL_STATE = range(3)
OPEN_LIMIT = 50e6  # px: larger mosaics would need too much memory for the wavelets


def _image_filter() -> str:
    patterns = [f"*{e}" for e in IMAGE_EXTENSIONS] + [f"*{e.upper()}" for e in IMAGE_EXTENSIONS]
    return f"{tr('Images')} ({' '.join(patterns)})"


def preview_pixmap(result: MosaicResult, index: int = 0, width: int = 0) -> QPixmap:
    """The reduced mosaic with the outline and number of every image."""
    img = result.previews[index]
    group = result.groups[index]
    pix = QPixmap.fromImage(to_qimage(img))
    if width and pix.width() > width:
        pix = pix.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
    s = pix.width() / group.width
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(255, 80, 60), 1))
    font = p.font()
    font.setPointSizeF(max(7.0, min(11.0, pix.width() / 60)))
    p.setFont(font)
    for k, n in enumerate(group.indices):
        corners = group.outline(k) * s
        p.drawPolygon(QPolygonF([QPointF(float(x), float(y)) for x, y in corners]))
        c = corners.mean(axis=0)
        p.drawText(QPointF(float(c[0]) - 6, float(c[1]) + 4), str(n + 1))
    p.end()
    return pix


class MosaicWorker(QThread):
    progressed = Signal(float, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, paths: list[str], out_dir: str, fmt: str, bits: int, suffix: str,
                 settings=None, parent=None) -> None:
        super().__init__(parent)
        self.paths, self.out_dir, self.fmt, self.bits, self.suffix = paths, out_dir, fmt, bits, suffix
        self.settings = settings
        self.cancel_event = threading.Event()

    def run(self) -> None:
        try:
            result = make_mosaics(self.paths, self.out_dir, self.fmt, self.bits, suffix=self.suffix,
                                  progress=lambda f, m: self.progressed.emit(float(f), str(m)),
                                  cancel=self.cancel_event, settings=self.settings)
        except Cancelled:
            return
        except MemoryError:
            self.failed.emit(tr("mémoire insuffisante"))
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self.failed.emit(str(exc) or type(exc).__name__)
        else:
            self.done.emit(result)


class MosaicDialog(QDialog):
    """`open_image(path)` loads a finished mosaic into the main window (for the wavelets);
    `current_settings()` returns the main window's settings."""

    def __init__(self, qsettings: QSettings, open_image=None, current_settings=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Assembler une mosaïque"))
        self.resize(980, 640)
        self.qs = qsettings
        self._open_image = open_image
        self._current_settings = current_settings
        self.worker: MosaicWorker | None = None
        self.result: MosaicResult | None = None
        self._paths: list[str] = []
        self._chosen: list[str] | None = None  # images picked one by one instead of a folder

        self.folder_edit = QLineEdit(str(self.qs.value("mosaic/folder", default_batch_folders()[1])))
        browse = QPushButton(tr("Parcourir…"))
        browse.clicked.connect(self._browse)
        pick = QPushButton(tr("Choisir des images…"))
        pick.clicked.connect(self._pick)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.folder_edit, 1)
        h.addWidget(browse)
        h.addWidget(pick)
        self.raw_check = QCheckBox(tr("Empilements bruts (images « _brut ») plutôt que les images traitées"))
        self.raw_check.setChecked(str(self.qs.value("mosaic/raw", False)).lower() == "true")
        self.raw_check.toggled.connect(self.refresh)
        self.format_combo = QComboBox()
        for label, ext, bits in FORMATS:
            self.format_combo.addItem(tr(label), (ext, bits))
        self.format_combo.setCurrentIndex(max(0, int(self.qs.value("mosaic/format", 0))))
        self.process_combo = QComboBox()
        self.process_combo.addItem(tr("Aucun : assembler les images telles quelles"), "")
        if current_settings is not None:
            self.process_combo.addItem(tr("Ondelettes et finitions des réglages actuels"), "*")
        for name in list_presets():
            self.process_combo.addItem(tr("Ondelettes et finitions du préréglage « {name} »", name=name), name)
        self.process_combo.setCurrentIndex(max(0, self.process_combo.findData(self.qs.value("mosaic/process", ""))))
        self.process_combo.setToolTip(tr(
            "Pour des empilements bruts : les ondelettes sont appliquées à chaque image, les niveaux\n"
            "et les couleurs une seule fois, à la mosaïque entière (un ciel brûlé dans une image et\n"
            "pas dans sa voisine laisserait des zones visibles)."))
        form = QFormLayout()
        form.addRow(tr("Images à assembler :"), row)
        form.addRow("", self.raw_check)
        form.addRow(tr("Traitement :"), self.process_combo)
        form.addRow(tr("Format :"), self.format_combo)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr("Image"), tr("Taille"), tr("État")])
        self.table.verticalHeader().hide()  # the names carry the numbers drawn on the preview
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(COL_SIZE, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(COL_STATE, QHeaderView.ResizeMode.Stretch)
        self.preview = QLabel(tr("L'aperçu de la mosaïque s'affichera ici."))
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(320, 320)
        split = QSplitter()
        split.addWidget(self.table)
        split.addWidget(self.preview)
        split.setSizes([520, 440])

        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setMaximumHeight(110)
        self.report.setPlaceholderText(tr(
            "Les images doivent se recouvrir d'environ 25 % et avoir été traitées avec les mêmes "
            "réglages. La mosaïque est enregistrée dans le dossier des images (mosaique.tif)."))
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setFormat("")

        self.start_btn = QPushButton(tr("Assembler"))
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self.start)
        self.cancel_btn = QPushButton(tr("Annuler"))
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel)
        self.open_btn = QPushButton(tr("Ouvrir dans PlanStax (ondelettes)"))
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self._open_result)
        folder_btn = QPushButton(tr("Ouvrir le dossier"))
        folder_btn.clicked.connect(self._open_folder)
        close_btn = QPushButton(tr("Fermer"))
        close_btn.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(folder_btn)
        buttons.addWidget(self.open_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.start_btn)
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(close_btn)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(split, 1)
        lay.addWidget(self.report)
        lay.addWidget(self.progress)
        lay.addLayout(buttons)
        self._inputs = [self.folder_edit, browse, pick, self.raw_check, self.process_combo, self.format_combo]
        self.folder_edit.editingFinished.connect(self._folder_mode)
        self.refresh()

    # ------------------------------------------------------------------ inputs
    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("Dossier des images"), self.folder_edit.text())
        if folder:
            self.folder_edit.setText(os.path.normpath(folder))
            self._folder_mode()

    def _pick(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Images à assembler"), self.folder_edit.text(),
                                                f"{_image_filter()};;{tr('Tous les fichiers (*)')}")
        if paths:
            self._chosen = [os.path.normpath(p) for p in paths]
            self.folder_edit.setText(os.path.dirname(self._chosen[0]))
            self.refresh()

    def _folder_mode(self) -> None:
        self._chosen = None
        self.refresh()

    def out_dir(self) -> str:
        return os.path.dirname(self._paths[0]) if self._chosen and self._paths else self.folder_edit.text().strip()

    def refresh(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        self.raw_check.setEnabled(self._chosen is None)
        if self._chosen is not None:
            self._paths = [p for p in self._chosen if os.path.isfile(p)]
        else:
            self._paths = list_images(self.folder_edit.text().strip(), raw=self.raw_check.isChecked())
        self.table.setRowCount(len(self._paths))
        for row, path in enumerate(self._paths):
            for col, text in ((COL_NAME, f"{row + 1}. {os.path.basename(path)}"),
                              (COL_SIZE, megabytes(os.path.getsize(path))),
                              (COL_STATE, "")):
                item = QTableWidgetItem(text)
                if col == COL_SIZE:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col, item)
        self.start_btn.setEnabled(len(self._paths) >= 2)
        if len(self._paths) < 2:
            self.progress.setFormat(tr("Il faut au moins deux images qui se recouvrent."))
        else:
            self.progress.setFormat(tr("{n} images", n=len(self._paths)))

    # ------------------------------------------------------------------ run
    def start(self) -> None:
        self.refresh()
        if len(self._paths) < 2:
            return
        ext, bits = self.format_combo.currentData()
        settings = self._processing()
        if settings is False:
            return
        self._save_choices()
        self.result = None
        self.open_btn.setEnabled(False)
        self.report.clear()
        raw = self._chosen is None and self.raw_check.isChecked()
        suffix = "_brut" if raw and settings is None else ""
        self.worker = MosaicWorker(self._paths, self.out_dir(), ext, bits, suffix, settings, self)
        self.worker.progressed.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_finished)
        for w in self._inputs:
            w.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.worker.start()

    def _processing(self):
        """Settings to apply (None: the images as they are; False: unreadable preset)."""
        choice = self.process_combo.currentData()
        if not choice:
            return None
        if choice == "*":
            return self._current_settings().copy()
        try:
            return load_preset(choice)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, self.windowTitle(), tr("Préréglage illisible :\n{error}", error=exc))
            return False

    def _on_progress(self, fraction: float, message: str) -> None:
        self.progress.setValue(int(fraction * 1000))
        self.progress.setFormat(message)

    def _on_done(self, result: MosaicResult) -> None:
        self.result = result
        plan = result.plan
        for row in range(len(self._paths)):
            self.table.item(row, COL_STATE).setText(plan.state(row))
        text = plan.explain()
        if result.outputs:
            text += "\n" + "\n".join(tr("Enregistrée : {path}", path=p) for p in result.outputs)
            self._show_preview()
            group = result.groups[0]
            processed = self.worker is not None and self.worker.settings is not None
            # A mosaic that already has its wavelets would get them a second time.
            self.open_btn.setEnabled(self._open_image is not None and group.pixels <= OPEN_LIMIT
                                     and not processed)
            if group.pixels > OPEN_LIMIT:
                text += "\n" + tr("Mosaïque de {mpx} Mpx : trop grande pour appliquer les ondelettes "
                                  "dans PlanStax (mémoire).", mpx=f"{group.pixels / 1e6:.0f}")
                if self.worker is not None and self.worker.suffix:
                    text += " " + tr("Choisissez plutôt un traitement dans la liste « Traitement » : les "
                                     "ondelettes seront appliquées image par image.")
        self.report.setPlainText(text)
        self.progress.setValue(1000)
        self.progress.setFormat(tr("Terminé en {seconds} s", seconds=f"{result.seconds:.0f}")
                                if result.outputs else tr("Aucune mosaïque"))

    def _show_preview(self) -> None:
        if self.result is None or not self.result.outputs:
            return
        pix = preview_pixmap(self.result, 0)
        self.preview.setPixmap(pix.scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._show_preview()

    def _on_failed(self, message: str) -> None:
        self.progress.setFormat(tr("Erreur"))
        QMessageBox.critical(self, self.windowTitle(), tr("Assemblage impossible :\n{error}", error=message))

    def _on_finished(self) -> None:
        cancelled = self.worker is not None and self.worker.cancel_event.is_set()
        self.worker = None
        for w in self._inputs:
            w.setEnabled(True)
        self.raw_check.setEnabled(self._chosen is None)
        self.cancel_btn.setEnabled(False)
        self.start_btn.setEnabled(len(self._paths) >= 2)
        if cancelled:
            self.progress.setValue(0)
            self.progress.setFormat(tr("Assemblage annulé"))

    def cancel(self) -> None:
        if self.worker is not None:
            self.worker.cancel_event.set()
            self.cancel_btn.setEnabled(False)
            self.progress.setFormat(tr("Annulation…"))

    def _open_result(self) -> None:
        if self.result and self.result.outputs and self._open_image is not None:
            path = self.result.outputs[0]
            self.accept()
            self._open_image(path)

    def _open_folder(self) -> None:
        folder = self.out_dir()
        if os.path.isdir(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _save_choices(self) -> None:
        self.qs.setValue("mosaic/folder", self.folder_edit.text().strip())
        self.qs.setValue("mosaic/raw", self.raw_check.isChecked())
        self.qs.setValue("mosaic/process", self.process_combo.currentData())
        self.qs.setValue("mosaic/format", self.format_combo.currentIndex())
        self.qs.sync()

    def _confirm_stop(self) -> bool:
        if self.worker is None or not self.worker.isRunning():
            return True
        if QMessageBox.question(self, self.windowTitle(), tr("Un assemblage est en cours. L'interrompre ?")) \
                != QMessageBox.StandardButton.Yes:
            return False
        self.worker.cancel_event.set()
        self.worker.wait(30000)
        return True

    def reject(self) -> None:
        if self._confirm_stop():
            self._save_choices()
            super().reject()

    def closeEvent(self, event) -> None:
        if not self._confirm_stop():
            event.ignore()
            return
        super().closeEvent(event)
