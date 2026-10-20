"""Batch processing window: every video of the input folder → one image in the output folder."""

from __future__ import annotations

import os
import threading
import traceback

from PySide6.QtCore import QFileSystemWatcher, QSettings, QSignalBlocker, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog,
                               QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..batch import (FORMATS, BatchOptions, is_done, list_videos, make_mosaics, mosaic_sources,
                     mosaic_suffix, process_video)
from ..core import Cancelled
from ..i18n import megabytes, tr
from ..paths import default_batch_folders
from ..settings import Settings, list_presets, load_preset

COL_NAME, COL_SIZE, COL_STATE = range(3)


class BatchWorker(QThread):
    fileStarted = Signal(int)
    fileProgress = Signal(int, float, str)
    fileDone = Signal(int, object)
    fileFailed = Signal(int, str)
    mosaicStarted = Signal(int)
    mosaicProgress = Signal(float, str)
    mosaicDone = Signal(object)
    mosaicFailed = Signal(str)

    def __init__(self, jobs: list[tuple[int, str]], settings: Settings, out_dir: str,
                 opts: BatchOptions, videos: list[str] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.jobs, self.settings, self.out_dir, self.opts = jobs, settings, out_dir, opts
        self.videos = videos if videos is not None else [p for _, p in jobs]
        self.cancel_event = threading.Event()

    def run(self) -> None:
        for row, path in self.jobs:
            if self.cancel_event.is_set():
                return
            self.fileStarted.emit(row)
            try:
                result = process_video(path, self.settings, self.out_dir, self.opts,
                                       lambda f, m, r=row: self.fileProgress.emit(r, float(f), str(m)),
                                       self.cancel_event)
            except Cancelled:
                return
            except MemoryError:
                self.fileFailed.emit(row, tr("mémoire insuffisante"))
            except Exception as exc:  # noqa: BLE001 - one bad video must not stop the batch
                traceback.print_exc()
                self.fileFailed.emit(row, str(exc) or type(exc).__name__)
            else:
                self.fileDone.emit(row, result)
        if self.opts.mosaic and not self.cancel_event.is_set():
            self._mosaic()

    def _mosaic(self) -> None:
        paths = mosaic_sources(self.videos, self.out_dir, self.opts)
        self.mosaicStarted.emit(len(paths))
        if len(paths) < 2:
            self.mosaicFailed.emit(tr("il faut au moins deux images"))
            return
        try:
            result = make_mosaics(paths, self.out_dir, self.opts.fmt, self.opts.bits,
                                  suffix=mosaic_suffix(self.opts),
                                  progress=lambda f, m: self.mosaicProgress.emit(float(f), str(m)),
                                  cancel=self.cancel_event,
                                  settings=self.settings if self.opts.save_final else None,
                                  auto_rgb=self.opts.auto_rgb)
        except Cancelled:
            return
        except MemoryError:
            self.mosaicFailed.emit(tr("mémoire insuffisante"))
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self.mosaicFailed.emit(str(exc) or type(exc).__name__)
        else:
            self.mosaicDone.emit(result)


class BatchDialog(QDialog):
    """`current_settings` returns the main window's settings (used when "Réglages actuels" is
    chosen)."""

    def __init__(self, current_settings, qsettings: QSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Traitement par lot"))
        self.resize(820, 560)
        self._current_settings = current_settings
        self.qs = qsettings
        self.worker: BatchWorker | None = None
        self._paths: list[str] = []
        self._done = self._failed = self._total = self._videos = self._mosaic_finished = 0
        self._in_mosaic = False
        self._mosaic_text = ""

        default_in, default_out = default_batch_folders()
        self.in_edit = QLineEdit(str(self.qs.value("batch/input", default_in)))
        self.out_edit = QLineEdit(str(self.qs.value("batch/output", default_out)))

        form = QFormLayout()
        form.addRow(tr("Vidéos à traiter :"), self._folder_row(self.in_edit, tr("Dossier des vidéos")))
        form.addRow(tr("Images produites :"), self._folder_row(self.out_edit, tr("Dossier des images")))
        self.preset_combo = QComboBox()
        self.preset_combo.addItem(tr("Réglages actuels de la fenêtre principale"), None)
        for name in list_presets():
            self.preset_combo.addItem(tr("Préréglage « {name} »", name=name), name)
        self.preset_combo.setCurrentIndex(max(0, self.preset_combo.findData(self.qs.value("batch/preset"))))
        form.addRow(tr("Réglages :"), self.preset_combo)
        self.format_combo = QComboBox()
        for label, ext, bits in FORMATS:
            self.format_combo.addItem(tr(label), (ext, bits))
        self.format_combo.setCurrentIndex(max(0, int(self.qs.value("batch/format", 0))))
        form.addRow(tr("Format :"), self.format_combo)

        self.final_check = QCheckBox(tr("Image traitée (ondelettes et finitions)"))
        self.raw_check = QCheckBox(tr("Empilement brut (suffixe « _brut »)"))
        self.rgb_check = QCheckBox(tr("Alignement RVB automatique pour chaque vidéo couleur"))
        self.skip_check = QCheckBox(tr("Ignorer les vidéos déjà traitées"))
        self.mosaic_check = QCheckBox(tr("Assembler les images en une mosaïque (Lune, Soleil, paysage…)"))
        self.mosaic_check.setToolTip(tr(
            "À la fin du lot, les images qui se recouvrent sont assemblées dans « mosaique.tif ».\n"
            "La mosaïque part des empilements bruts (enregistrés aussi) : les ondelettes sont appliquées\n"
            "image par image, mais les niveaux et les couleurs une seule fois, à la mosaïque entière,\n"
            "après égalisation : un ciel n'est pas brûlé dans une image et pas dans sa voisine."))
        for chk, key, default in ((self.final_check, "final", True), (self.raw_check, "raw", False),
                                  (self.rgb_check, "rgb", True), (self.skip_check, "skip", True),
                                  (self.mosaic_check, "mosaic", False)):
            chk.setChecked(str(self.qs.value(f"batch/{key}", default)).lower() == "true")
        checks = QWidget()
        cl = QVBoxLayout(checks)
        cl.setContentsMargins(0, 0, 0, 0)
        for chk in (self.final_check, self.raw_check, self.rgb_check, self.skip_check, self.mosaic_check):
            cl.addWidget(chk)
            chk.toggled.connect(self.refresh)
        form.addRow(tr("Enregistrer :"), checks)
        self._raw_wanted = self.raw_check.isChecked()
        self.raw_check.toggled.connect(self._remember_raw)
        self.mosaic_check.toggled.connect(self._sync_raw)
        self._sync_raw()

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr("Vidéo"), tr("Taille"), tr("État")])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(COL_SIZE, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(COL_STATE, QHeaderView.ResizeMode.Stretch)

        self.summary = QLabel("")
        self.mosaic_report = QPlainTextEdit()
        self.mosaic_report.setReadOnly(True)
        self.mosaic_report.setMaximumHeight(90)
        self.mosaic_report.hide()
        self.overall = QProgressBar()
        self.overall.setRange(0, 1000)
        self.current = QProgressBar()
        self.current.setRange(0, 1000)
        self.current.setFormat("")

        self.start_btn = QPushButton(tr("Démarrer"))
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self.start)
        self.cancel_btn = QPushButton(tr("Annuler"))
        self.cancel_btn.clicked.connect(self.cancel)
        self.cancel_btn.setEnabled(False)
        refresh_btn = QPushButton(tr("Actualiser"))
        refresh_btn.clicked.connect(self.refresh)
        open_out = QPushButton(tr("Ouvrir le dossier des images"))
        open_out.clicked.connect(lambda: self._open_folder(self.out_edit.text()))
        close_btn = QPushButton(tr("Fermer"))
        close_btn.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(refresh_btn)
        buttons.addWidget(open_out)
        buttons.addStretch(1)
        buttons.addWidget(self.start_btn)
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(close_btn)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.table, 1)
        lay.addWidget(self.summary)
        lay.addWidget(self.mosaic_report)
        lay.addWidget(self.current)
        lay.addWidget(self.overall)
        lay.addLayout(buttons)
        self._inputs = [self.in_edit, self.out_edit, self.preset_combo, self.format_combo,
                        self.final_check, self.raw_check, self.rgb_check, self.skip_check,
                        self.mosaic_check]

        # Refresh the list when videos are dropped into the input folder.
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(lambda _: self._refresh_timer.start())
        self._refresh_timer = QTimer(self, singleShot=True, interval=500)
        self._refresh_timer.timeout.connect(self.refresh)
        self.in_edit.editingFinished.connect(self.refresh)
        self.out_edit.editingFinished.connect(self.refresh)
        self.format_combo.currentIndexChanged.connect(self.refresh)
        self.refresh()

    # ------------------------------------------------------------------ helpers
    def _folder_row(self, edit: QLineEdit, title: str) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        browse = QPushButton(tr("Parcourir…"))
        browse.clicked.connect(lambda: self._browse(edit, title))
        show = QPushButton(tr("Ouvrir"))
        show.clicked.connect(lambda: self._open_folder(edit.text()))
        h.addWidget(edit, 1)
        h.addWidget(browse)
        h.addWidget(show)
        return w

    def _browse(self, edit: QLineEdit, title: str) -> None:
        folder = QFileDialog.getExistingDirectory(self, title, edit.text())
        if folder:
            edit.setText(os.path.normpath(folder))
            self.refresh()

    def _open_folder(self, folder: str) -> None:
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _remember_raw(self, checked: bool) -> None:
        if not self.mosaic_check.isChecked():
            self._raw_wanted = checked

    def _sync_raw(self) -> None:
        """The mosaic is made from the raw stacks: they are saved whenever it is asked for."""
        mosaic = self.mosaic_check.isChecked()
        with QSignalBlocker(self.raw_check):
            self.raw_check.setChecked(mosaic or self._raw_wanted)
        self.raw_check.setEnabled(not mosaic and self.worker is None)
        self.raw_check.setToolTip(tr("Nécessaire à la mosaïque") if mosaic else "")

    def options(self) -> BatchOptions:
        ext, bits = self.format_combo.currentData()
        return BatchOptions(save_final=self.final_check.isChecked(), save_raw=self.raw_check.isChecked(),
                            fmt=ext, bits=bits, auto_rgb=self.rgb_check.isChecked(),
                            skip_existing=self.skip_check.isChecked(),
                            mosaic=self.mosaic_check.isChecked())

    def _can_start(self, todo: int, opts: BatchOptions) -> bool:
        """Videos to process, or only the mosaic of images already made."""
        if not (opts.save_final or opts.save_raw):
            return False
        return todo > 0 or (opts.mosaic and len(mosaic_sources(self._paths, self.out_edit.text().strip(), opts)) >= 2)

    def _set_state(self, row: int, text: str) -> None:
        item = self.table.item(row, COL_STATE)
        if item is not None:
            item.setText(text)

    # ------------------------------------------------------------------ list
    def refresh(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        in_dir, out_dir = self.in_edit.text().strip(), self.out_edit.text().strip()
        if self.watcher.directories():
            self.watcher.removePaths(self.watcher.directories())
        if os.path.isdir(in_dir):
            self.watcher.addPath(in_dir)
        self._paths = list_videos(in_dir)
        opts = self.options()
        self.table.setRowCount(len(self._paths))
        todo = 0
        for row, path in enumerate(self._paths):
            done = opts.skip_existing and is_done(path, out_dir, opts)
            todo += not done
            for col, text in ((COL_NAME, os.path.basename(path)),
                              (COL_SIZE, megabytes(os.path.getsize(path))),
                              (COL_STATE, tr("Déjà traitée") if done else tr("À traiter"))):
                item = QTableWidgetItem(text)
                if col == COL_SIZE:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col, item)
        if not os.path.isdir(in_dir):
            self.summary.setText(tr("Le dossier des vidéos n'existe pas."))
        elif not self._paths:
            self.summary.setText(tr("Aucune vidéo (SER, AVI…) dans ce dossier : déposez-y vos captures."))
        else:
            self.summary.setText(tr("{videos} vidéo(s), dont {todo} à traiter.", videos=len(self._paths), todo=todo)
                                 + (tr(" Puis assemblage de la mosaïque.") if opts.mosaic else ""))
        self.start_btn.setEnabled(self._can_start(todo, opts))

    # ------------------------------------------------------------------ run
    def _settings(self) -> Settings | None:
        name = self.preset_combo.currentData()
        if name is None:
            return self._current_settings().copy()
        try:
            return load_preset(name)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, self.windowTitle(), tr("Préréglage illisible :\n{error}", error=exc))
            return None

    def _save_choices(self) -> None:
        self.qs.setValue("batch/input", self.in_edit.text().strip())
        self.qs.setValue("batch/output", self.out_edit.text().strip())
        self.qs.setValue("batch/preset", self.preset_combo.currentData())
        self.qs.setValue("batch/format", self.format_combo.currentIndex())
        for chk, key in ((self.final_check, "final"), (self.rgb_check, "rgb"),
                         (self.skip_check, "skip"), (self.mosaic_check, "mosaic")):
            self.qs.setValue(f"batch/{key}", chk.isChecked())
        self.qs.setValue("batch/raw", self._raw_wanted)  # not the box ticked because of the mosaic
        self.qs.sync()

    def start(self) -> None:
        self.refresh()
        out_dir = self.out_edit.text().strip()
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, self.windowTitle(), tr("Dossier des images inutilisable :\n{error}", error=exc))
            return
        settings = self._settings()
        if settings is None:
            return
        opts = self.options()
        jobs = [(row, p) for row, p in enumerate(self._paths)
                if not (opts.skip_existing and is_done(p, out_dir, opts))]
        if not self._can_start(len(jobs), opts):
            return
        self._save_choices()
        self._videos, self._done, self._failed = len(jobs), 0, 0
        self._total = len(jobs) + opts.mosaic
        self._mosaic_finished, self._in_mosaic, self._mosaic_text = 0, False, ""
        self.mosaic_report.clear()
        self.mosaic_report.hide()
        for row, _ in jobs:
            self._set_state(row, tr("En attente"))
        self.worker = BatchWorker(jobs, settings, out_dir, opts, list(self._paths), parent=self)
        self.worker.fileStarted.connect(lambda r: self._set_state(r, tr("En cours…")))
        self.worker.fileProgress.connect(self._on_progress)
        self.worker.fileDone.connect(self._on_done)
        self.worker.fileFailed.connect(self._on_failed)
        self.worker.mosaicStarted.connect(self._on_mosaic_started)
        self.worker.mosaicProgress.connect(self._on_mosaic_progress)
        self.worker.mosaicDone.connect(self._on_mosaic_done)
        self.worker.mosaicFailed.connect(self._on_mosaic_failed)
        self.worker.finished.connect(self._on_finished)
        for w in self._inputs:
            w.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.overall.setValue(0)
        self._update_overall(0.0)
        self.worker.start()

    def _update_overall(self, current_fraction: float) -> None:
        finished = self._done + self._failed + self._mosaic_finished
        self.overall.setValue(int(1000 * (finished + current_fraction) / max(self._total, 1)))
        self.overall.setFormat(tr("Mosaïque") if self._in_mosaic else
                               tr("Vidéo {index} / {videos}", index=min(self._done + self._failed + 1, self._videos),
                                  videos=self._videos))

    def _on_mosaic_started(self, count: int) -> None:
        self._in_mosaic = True
        self.current.setValue(0)
        self.current.setFormat(tr("Mosaïque de {n} image(s)", n=count))
        self._update_overall(0.0)

    def _on_mosaic_progress(self, fraction: float, message: str) -> None:
        self.current.setValue(int(fraction * 1000))
        self.current.setFormat(message)
        self._update_overall(fraction)

    def _on_mosaic_done(self, result) -> None:
        self._mosaic_finished = 1
        self._mosaic_text = tr("Mosaïque : {summary}", summary=result.summary())
        self.mosaic_report.setPlainText(
            "\n".join([result.plan.explain()] + [tr("Enregistrée : {path}", path=p) for p in result.outputs]))
        self.mosaic_report.show()

    def _on_mosaic_failed(self, message: str) -> None:
        self._mosaic_finished = 1
        self._mosaic_text = tr("Mosaïque impossible : {error}", error=message)
        self.mosaic_report.setPlainText(self._mosaic_text)
        self.mosaic_report.show()

    def _on_progress(self, row: int, fraction: float, message: str) -> None:
        self.current.setValue(int(fraction * 1000))
        self.current.setFormat(message)
        self._set_state(row, tr("En cours… {percent} %", percent=f"{fraction * 100:.0f}"))
        self._update_overall(fraction)

    def _on_done(self, row: int, result) -> None:
        self._done += 1
        names = ", ".join(os.path.basename(o) for o in result.outputs)
        if result.points:
            self._set_state(row, tr("✓ {stacked}/{frames} images, {points} points, {seconds} s → {names}",
                                    stacked=result.stacked, frames=result.frames, points=result.points,
                                    seconds=f"{result.seconds:.0f}", names=names))
        else:  # stacked with the global alignment only: worth checking the brightness limits
            self._set_state(row, tr("⚠ {stacked}/{frames} images, aucun point d'alignement "
                                    "(vérifiez Luminosité min./max.) → {names}",
                                    stacked=result.stacked, frames=result.frames, names=names))
        self._update_overall(0.0)

    def _on_failed(self, row: int, message: str) -> None:
        self._failed += 1
        self._set_state(row, tr("✗ Erreur : {error}", error=message))
        self._update_overall(0.0)

    def _on_finished(self) -> None:
        cancelled = self.worker is not None and self.worker.cancel_event.is_set()
        self.worker = None
        for w in self._inputs:
            w.setEnabled(True)
        self._sync_raw()
        self.cancel_btn.setEnabled(False)
        self.current.setValue(0)
        self.current.setFormat("")
        text = tr("Terminé : {n} image(s) produite(s)", n=self._done)
        if self._failed:
            text += tr(", {n} vidéo(s) en erreur", n=self._failed)
        if self._mosaic_text:
            text += ". " + self._mosaic_text
        if cancelled:
            text = tr("Traitement annulé.") + " " + text
        self._in_mosaic = False
        self.overall.setFormat(text)
        if not cancelled:
            self.overall.setValue(1000)
        # Keep the per-video states visible; only re-evaluate the start button.
        opts = self.options()
        out_dir = self.out_edit.text().strip()
        remaining = sum(not (opts.skip_existing and is_done(p, out_dir, opts)) for p in self._paths)
        self.start_btn.setEnabled(self._can_start(remaining, opts))
        self.summary.setText(text + ".")

    def cancel(self) -> None:
        if self.worker is not None:
            self.worker.cancel_event.set()
            self.cancel_btn.setEnabled(False)
            self.current.setFormat(tr("Annulation…"))

    def _confirm_stop(self) -> bool:
        """False if a batch is running and the user wants it to continue."""
        if self.worker is None or not self.worker.isRunning():
            return True
        answer = QMessageBox.question(self, self.windowTitle(), tr("Un traitement est en cours. L'interrompre ?"))
        if answer != QMessageBox.StandardButton.Yes:
            return False
        self.worker.cancel_event.set()
        self.worker.wait(30000)
        return True

    def reject(self) -> None:  # Échap, « Fermer » and the window's close button all end here
        if self._confirm_stop():
            self._save_choices()
            super().reject()

    def closeEvent(self, event) -> None:
        if not self._confirm_stop():
            event.ignore()
            return
        super().closeEvent(event)  # QDialog calls reject()
