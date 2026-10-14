"""Batch processing window: every video of the input folder → one image in the output folder."""

from __future__ import annotations

import os
import threading
import traceback

from PySide6.QtCore import QFileSystemWatcher, QSettings, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog,
                               QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMessageBox, QProgressBar, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..batch import FORMATS, BatchOptions, is_done, list_videos, process_video
from ..core import Cancelled
from ..paths import default_batch_folders
from ..settings import Settings, list_presets, load_preset

COL_NAME, COL_SIZE, COL_STATE = range(3)


class BatchWorker(QThread):
    fileStarted = Signal(int)
    fileProgress = Signal(int, float, str)
    fileDone = Signal(int, object)
    fileFailed = Signal(int, str)

    def __init__(self, jobs: list[tuple[int, str]], settings: Settings, out_dir: str,
                 opts: BatchOptions, parent=None) -> None:
        super().__init__(parent)
        self.jobs, self.settings, self.out_dir, self.opts = jobs, settings, out_dir, opts
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
                self.fileFailed.emit(row, "mémoire insuffisante")
            except Exception as exc:  # noqa: BLE001 - one bad video must not stop the batch
                traceback.print_exc()
                self.fileFailed.emit(row, str(exc) or type(exc).__name__)
            else:
                self.fileDone.emit(row, result)


class BatchDialog(QDialog):
    """`current_settings` returns the main window's settings (used when "Réglages actuels" is
    chosen)."""

    def __init__(self, current_settings, qsettings: QSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Traitement par lot")
        self.resize(820, 560)
        self._current_settings = current_settings
        self.qs = qsettings
        self.worker: BatchWorker | None = None
        self._paths: list[str] = []
        self._done = self._failed = self._total = 0

        default_in, default_out = default_batch_folders()
        self.in_edit = QLineEdit(str(self.qs.value("batch/input", default_in)))
        self.out_edit = QLineEdit(str(self.qs.value("batch/output", default_out)))

        form = QFormLayout()
        form.addRow("Vidéos à traiter :", self._folder_row(self.in_edit, "Dossier des vidéos"))
        form.addRow("Images produites :", self._folder_row(self.out_edit, "Dossier des images"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Réglages actuels de la fenêtre principale", None)
        for name in list_presets():
            self.preset_combo.addItem(f"Préréglage « {name} »", name)
        self.preset_combo.setCurrentIndex(max(0, self.preset_combo.findData(self.qs.value("batch/preset"))))
        form.addRow("Réglages :", self.preset_combo)
        self.format_combo = QComboBox()
        for label, ext, bits in FORMATS:
            self.format_combo.addItem(label, (ext, bits))
        self.format_combo.setCurrentIndex(max(0, int(self.qs.value("batch/format", 0))))
        form.addRow("Format :", self.format_combo)

        self.final_check = QCheckBox("Image traitée (ondelettes et finitions)")
        self.raw_check = QCheckBox("Empilement brut (suffixe « _brut »)")
        self.rgb_check = QCheckBox("Alignement RVB automatique pour chaque vidéo couleur")
        self.skip_check = QCheckBox("Ignorer les vidéos déjà traitées")
        for chk, key, default in ((self.final_check, "final", True), (self.raw_check, "raw", False),
                                  (self.rgb_check, "rgb", True), (self.skip_check, "skip", True)):
            chk.setChecked(str(self.qs.value(f"batch/{key}", default)).lower() == "true")
        checks = QWidget()
        cl = QVBoxLayout(checks)
        cl.setContentsMargins(0, 0, 0, 0)
        for chk in (self.final_check, self.raw_check, self.rgb_check, self.skip_check):
            cl.addWidget(chk)
            chk.toggled.connect(self.refresh)
        form.addRow("Enregistrer :", checks)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Vidéo", "Taille", "État"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(COL_SIZE, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(COL_STATE, QHeaderView.ResizeMode.Stretch)

        self.summary = QLabel("")
        self.overall = QProgressBar()
        self.overall.setRange(0, 1000)
        self.current = QProgressBar()
        self.current.setRange(0, 1000)
        self.current.setFormat("")

        self.start_btn = QPushButton("Démarrer")
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self.start)
        self.cancel_btn = QPushButton("Annuler")
        self.cancel_btn.clicked.connect(self.cancel)
        self.cancel_btn.setEnabled(False)
        refresh_btn = QPushButton("Actualiser")
        refresh_btn.clicked.connect(self.refresh)
        open_out = QPushButton("Ouvrir le dossier des images")
        open_out.clicked.connect(lambda: self._open_folder(self.out_edit.text()))
        close_btn = QPushButton("Fermer")
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
        lay.addWidget(self.current)
        lay.addWidget(self.overall)
        lay.addLayout(buttons)
        self._inputs = [self.in_edit, self.out_edit, self.preset_combo, self.format_combo,
                        self.final_check, self.raw_check, self.rgb_check, self.skip_check]

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
        browse = QPushButton("Parcourir…")
        browse.clicked.connect(lambda: self._browse(edit, title))
        show = QPushButton("Ouvrir")
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

    def options(self) -> BatchOptions:
        ext, bits = self.format_combo.currentData()
        return BatchOptions(save_final=self.final_check.isChecked(), save_raw=self.raw_check.isChecked(),
                            fmt=ext, bits=bits, auto_rgb=self.rgb_check.isChecked(),
                            skip_existing=self.skip_check.isChecked())

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
            size = os.path.getsize(path) / 2 ** 20
            done = opts.skip_existing and is_done(path, out_dir, opts)
            todo += not done
            for col, text in ((COL_NAME, os.path.basename(path)),
                              (COL_SIZE, f"{size:,.0f} Mo".replace(",", " ") if size >= 1 else "< 1 Mo"),
                              (COL_STATE, "Déjà traitée" if done else "À traiter")):
                item = QTableWidgetItem(text)
                if col == COL_SIZE:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col, item)
        if not os.path.isdir(in_dir):
            self.summary.setText("Le dossier des vidéos n'existe pas.")
        elif not self._paths:
            self.summary.setText("Aucune vidéo (SER, AVI…) dans ce dossier : déposez-y vos captures.")
        else:
            self.summary.setText(f"{len(self._paths)} vidéo(s), dont {todo} à traiter.")
        self.start_btn.setEnabled(todo > 0 and (opts.save_final or opts.save_raw))

    # ------------------------------------------------------------------ run
    def _settings(self) -> Settings | None:
        name = self.preset_combo.currentData()
        if name is None:
            return self._current_settings().copy()
        try:
            return load_preset(name)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Traitement par lot", f"Préréglage illisible :\n{exc}")
            return None

    def _save_choices(self) -> None:
        self.qs.setValue("batch/input", self.in_edit.text().strip())
        self.qs.setValue("batch/output", self.out_edit.text().strip())
        self.qs.setValue("batch/preset", self.preset_combo.currentData())
        self.qs.setValue("batch/format", self.format_combo.currentIndex())
        for chk, key in ((self.final_check, "final"), (self.raw_check, "raw"),
                         (self.rgb_check, "rgb"), (self.skip_check, "skip")):
            self.qs.setValue(f"batch/{key}", chk.isChecked())
        self.qs.sync()

    def start(self) -> None:
        self.refresh()
        out_dir = self.out_edit.text().strip()
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "Traitement par lot", f"Dossier des images inutilisable :\n{exc}")
            return
        settings = self._settings()
        if settings is None:
            return
        opts = self.options()
        jobs = [(row, p) for row, p in enumerate(self._paths)
                if not (opts.skip_existing and is_done(p, out_dir, opts))]
        if not jobs:
            return
        self._save_choices()
        self._total, self._done, self._failed = len(jobs), 0, 0
        for row, _ in jobs:
            self._set_state(row, "En attente")
        self.worker = BatchWorker(jobs, settings, out_dir, opts, self)
        self.worker.fileStarted.connect(lambda r: self._set_state(r, "En cours…"))
        self.worker.fileProgress.connect(self._on_progress)
        self.worker.fileDone.connect(self._on_done)
        self.worker.fileFailed.connect(self._on_failed)
        self.worker.finished.connect(self._on_finished)
        for w in self._inputs:
            w.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.overall.setValue(0)
        self._update_overall(0.0)
        self.worker.start()

    def _update_overall(self, current_fraction: float) -> None:
        finished = self._done + self._failed
        self.overall.setValue(int(1000 * (finished + current_fraction) / max(self._total, 1)))
        self.overall.setFormat(f"Vidéo {min(finished + 1, self._total)} / {self._total}")

    def _on_progress(self, row: int, fraction: float, message: str) -> None:
        self.current.setValue(int(fraction * 1000))
        self.current.setFormat(message)
        self._set_state(row, f"En cours… {fraction * 100:.0f} %")
        self._update_overall(fraction)

    def _on_done(self, row: int, result) -> None:
        self._done += 1
        names = ", ".join(os.path.basename(o) for o in result.outputs)
        if result.points:
            self._set_state(row, f"✓ {result.stacked}/{result.frames} images, {result.points} points, "
                                 f"{result.seconds:.0f} s → {names}")
        else:  # stacked with the global alignment only: worth checking the brightness limits
            self._set_state(row, f"⚠ {result.stacked}/{result.frames} images, aucun point d'alignement "
                                 f"(vérifiez Luminosité min./max.) → {names}")
        self._update_overall(0.0)

    def _on_failed(self, row: int, message: str) -> None:
        self._failed += 1
        self._set_state(row, f"✗ Erreur : {message}")
        self._update_overall(0.0)

    def _on_finished(self) -> None:
        cancelled = self.worker is not None and self.worker.cancel_event.is_set()
        self.worker = None
        for w in self._inputs:
            w.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.current.setValue(0)
        self.current.setFormat("")
        text = f"Terminé : {self._done} image(s) produite(s)"
        if self._failed:
            text += f", {self._failed} vidéo(s) en erreur"
        if cancelled:
            text = "Traitement annulé. " + text
        self.overall.setFormat(text)
        if not cancelled:
            self.overall.setValue(1000)
        # Keep the per-video states visible; only re-evaluate the start button.
        opts = self.options()
        out_dir = self.out_edit.text().strip()
        remaining = sum(not (opts.skip_existing and is_done(p, out_dir, opts)) for p in self._paths)
        self.start_btn.setEnabled(remaining > 0)
        self.summary.setText(text + ".")

    def cancel(self) -> None:
        if self.worker is not None:
            self.worker.cancel_event.set()
            self.cancel_btn.setEnabled(False)
            self.current.setFormat("Annulation…")

    def _confirm_stop(self) -> bool:
        """False if a batch is running and the user wants it to continue."""
        if self.worker is None or not self.worker.isRunning():
            return True
        answer = QMessageBox.question(self, "Traitement par lot",
                                      "Un traitement est en cours. L'interrompre ?")
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
