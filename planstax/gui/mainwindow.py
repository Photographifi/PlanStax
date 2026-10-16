"""Main window."""

from __future__ import annotations

import dataclasses
import json
import os
import sys

import numpy as np
from PySide6.QtCore import QSettings, QSignalBlocker, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                               QHBoxLayout, QInputDialog, QLabel, QMainWindow, QMessageBox,
                               QProgressBar, QPushButton, QScrollArea, QSlider, QSpinBox,
                               QSplitter, QTabWidget, QToolBar, QToolButton, QVBoxLayout, QWidget)

from .. import APP_NAME, __version__
from ..core import Pipeline, auto_balance, estimate_rgb_shifts, finish
from ..core.postprocess import apply_post, apply_pre
from ..core.wavelets import WaveletProcessor
from ..io import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, open_source, read_image, save_image
from ..io.sources import NO_BAYER
from ..settings import (Settings, config_dir, import_all_registax, list_presets, load_preset,
                        presets_dir, registax_wavelet_positions, save_preset)
from . import theme
from .imageview import ImageView
from .widgets import QualityPlot, ValueSlider, dspin, group, hint, spin
from .workers import PreviewWorker, Task

TAB_ALIGN, TAB_SELECT, TAB_STACK, TAB_WAVELETS, TAB_POST = range(5)
# Qt turns the Ctrl of shortcuts and modifier clicks into the Command key on macOS: say so in texts.
CMD = "⌘" if sys.platform == "darwin" else "Ctrl"

def _file_filter(label: str, extensions) -> str:
    # Both cases: file dialogs match patterns case-sensitively on Linux (P1006397.MP4, JUPITER.SER).
    patterns = [f"*{e}" for e in extensions] + [f"*{e.upper()}" for e in extensions]
    return f"{label} ({' '.join(patterns)})"


VIDEO_FILTER = _file_filter("Vidéos", VIDEO_EXTENSIONS)
IMAGE_FILTER = _file_filter("Images", IMAGE_EXTENSIONS)
SAVE_FILTERS = {
    "TIFF 16 bits (*.tif)": (".tif", 16),
    "PNG 16 bits (*.png)": (".png", 16),
    "FITS 32 bits flottant (*.fits)": (".fits", 32),
    "FITS 16 bits (*.fit)": (".fit", 16),
    "JPEG (*.jpg)": (".jpg", 8),
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setAcceptDrops(True)
        # Interface state lives next to the presets in %APPDATA%\PlanStax (not the registry).
        self.qsettings = QSettings(os.path.join(config_dir(), "interface.ini"), QSettings.Format.IniFormat)
        self.settings = self._load_last_settings()

        self.source = None
        self.pipeline: Pipeline | None = None
        self.stacked: np.ndarray | None = None
        self.final: np.ndarray | None = None
        self._stack_version = 0
        self._preview_token = 0
        self._task: Task | None = None
        self._bindings: list = []
        self._view_mode = "frame"
        self._show_before = False

        self.preview = PreviewWorker(self._compute_preview, self)
        self.preview.ready.connect(self._on_preview)
        self._pre_key = None
        self._pre_wp = WaveletProcessor()
        self.preview.start()
        self._preview_timer = QTimer(self, singleShot=True, interval=40)
        self._preview_timer.timeout.connect(self._submit_preview)

        self._build_ui()
        self._settings_to_widgets()
        self._update_enabled()
        geo = self.qsettings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        else:
            self.resize(1280, 820)
        theme.apply(QApplication.instance(), self.qsettings.value("theme", "dark"))
        self._apply_overlay_color()

    # =================================================================== UI construction
    def _build_ui(self) -> None:
        self.view = ImageView()
        self.view.addPointRequested.connect(self._add_point)
        self.view.removePointRequested.connect(self._remove_point)
        self.view.zoomChanged.connect(lambda z: self.zoom_label.setText(f"{z * 100:.0f} %"))

        # Frame navigation bar under the image.
        self.frame_bar = QWidget()
        fb = QHBoxLayout(self.frame_bar)
        fb.setContentsMargins(6, 2, 6, 2)
        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.valueChanged.connect(self._on_frame_slider)
        self.frame_spin = QSpinBox()  # 1-based for display; the slider is 0-based
        self.frame_spin.setKeyboardTracking(False)
        self.frame_spin.valueChanged.connect(lambda v: self.frame_slider.setValue(v - 1))
        self.frame_order = QComboBox()
        self.frame_order.addItem("Ordre chronologique", "time")
        self.frame_order.addItem("Par qualité (meilleures d'abord)", "quality")
        self.frame_order.currentIndexChanged.connect(lambda _: self._on_frame_slider(self.frame_slider.value()))
        self.frame_info = QLabel()
        self.frame_info.setMinimumWidth(220)
        fb.addWidget(QLabel("Image :"))
        fb.addWidget(self.frame_slider, 1)
        fb.addWidget(self.frame_spin)
        fb.addWidget(self.frame_order)
        fb.addWidget(self.frame_info)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)
        ll.addWidget(self.view, 1)
        ll.addWidget(self.frame_bar)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._scroll(self._tab_align()), "1 · Alignement")
        self.tabs.addTab(self._scroll(self._tab_select()), "2 · Sélection")
        self.tabs.addTab(self._scroll(self._tab_stack()), "3 · Empilement")
        self.tabs.addTab(self._scroll(self._tab_wavelets()), "4 · Ondelettes")
        self.tabs.addTab(self._scroll(self._tab_post()), "5 · Finitions")
        self.tabs.currentChanged.connect(self._on_tab)
        self.tabs.setMinimumWidth(380)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(self.tabs)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        split.setSizes([900, 400])
        self.setCentralWidget(split)

        self._build_actions()
        self._build_statusbar()

    def _scroll(self, w: QWidget) -> QScrollArea:
        sa = QScrollArea()
        sa.setWidget(w)
        sa.setWidgetResizable(True)
        sa.setFrameShape(QScrollArea.Shape.NoFrame)
        return sa

    def _build_actions(self) -> None:
        def act(text, slot, shortcut=None, tip=None, checkable=False):
            a = QAction(text, self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            if tip:
                a.setStatusTip(tip)
                a.setToolTip(tip)
            a.setCheckable(checkable)
            return a

        self.act_open = act("Ouvrir une vidéo…", self.open_video, "Ctrl+O",
                            "Ouvrir une vidéo SER/AVI ou une série d'images")
        self.act_open_img = act("Ouvrir une image à traiter…", self.open_image, "Ctrl+I",
                                "Ouvrir une image déjà empilée pour les ondelettes")
        self.act_batch = act("Traitement par lot…", self.open_batch, "Ctrl+L",
                             "Traiter toutes les vidéos du dossier « input » : une image par vidéo dans « output »")
        self.act_save = act("Enregistrer l'image…", self.save_final, "Ctrl+S",
                            "Enregistrer le résultat (ondelettes et finitions comprises)")
        self.act_save_raw = act("Enregistrer l'empilement brut…", self.save_stacked, "Ctrl+Shift+S",
                                "Enregistrer l'empilement sans ondelettes ni finitions")
        self.act_doall = act("▶  Tout faire", self.do_all, "F5",
                             "Analyse, alignement, sélection et empilement en une fois")
        self.act_before = act("Avant / après", self._toggle_before, "B",
                              "Comparer avec l'empilement non traité", checkable=True)
        self.act_points = act("Afficher les points", lambda on: self.view.show_points(on), "P",
                              checkable=True)
        self.act_points.setChecked(True)
        self.act_fit = act("Ajuster à la fenêtre", self.view.fit, "F")
        self.act_100 = act("Taille réelle (100 %)", lambda: self.view.zoom_to(1.0), "1")
        self.act_200 = act("Zoom 200 %", lambda: self.view.zoom_to(2.0), "2")

        mb = self.menuBar()
        m = mb.addMenu("&Fichier")
        for a in (self.act_open, self.act_open_img, self.act_batch):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.act_save)
        m.addAction(self.act_save_raw)
        m.addSeparator()
        m.addAction(act("Quitter", self.close, "Ctrl+Q"))

        self.presets_menu = mb.addMenu("&Préréglages")
        self.presets_menu.aboutToShow.connect(self._fill_presets_menu)

        m = mb.addMenu("&Affichage")
        for a in (self.act_fit, self.act_100, self.act_200):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.act_points)
        m.addAction(self.act_before)
        m.addSeparator()
        tm = m.addMenu("Thème")
        for key, label in (("dark", "Sombre"), ("light", "Clair"), ("night", "Nuit (rouge, préserve la vision nocturne)")):
            tm.addAction(act(label, lambda _=False, k=key: self._set_theme(k)))

        m = mb.addMenu("&Aide")
        m.addAction(act("Guide rapide", self._show_help, "F1"))
        if os.name == "nt":
            m.addAction(act("Créer un raccourci sur le Bureau", self._desktop_shortcut))
        m.addAction(act("À propos de PlanStax", self._show_about))

        tb = QToolBar("Outils")
        tb.setObjectName("main_toolbar")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(tb)
        tb.addAction(self.act_open)
        tb.addAction(self.act_doall)
        tb.addAction(self.act_save)
        tb.addAction(self.act_batch)
        tb.addSeparator()
        tb.addAction(self.act_before)
        tb.addSeparator()
        tb.addAction(self.act_fit)
        tb.addAction(self.act_100)
        self.zoom_label = QLabel("")
        self.zoom_label.setMinimumWidth(60)
        tb.addWidget(self.zoom_label)
        doall_btn = tb.widgetForAction(self.act_doall)
        if isinstance(doall_btn, QToolButton):
            doall_btn.setObjectName("primary")

    def _build_statusbar(self) -> None:
        sb = self.statusBar()
        self.status_label = QLabel(f"Ouvrez une vidéo ({CMD}+O) ou glissez-la dans la fenêtre.")
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setMaximumWidth(260)
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.cancel_btn = QPushButton("Annuler")
        self.cancel_btn.hide()
        self.cancel_btn.clicked.connect(self._cancel_task)
        sb.addWidget(self.status_label, 1)
        sb.addPermanentWidget(self.progress)
        sb.addPermanentWidget(self.cancel_btn)

    # ------------------------------------------------------------------ bindings
    def _bind(self, widget, read, write, on_change=None) -> None:
        self._bindings.append((widget, read, write))

        def changed(*_):
            write(_widget_value(widget))
            if on_change:
                on_change()

        if isinstance(widget, QCheckBox):
            widget.toggled.connect(changed)
        elif isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(changed)
        else:
            widget.valueChanged.connect(changed)

    def _bind_attr(self, widget, getter, attr: str, on_change=None) -> None:
        self._bind(widget, lambda: getattr(getter(), attr),
                   lambda v: setattr(getter(), attr, v), on_change)

    def _settings_to_widgets(self) -> None:
        for widget, read, _ in self._bindings:
            with QSignalBlocker(widget):
                _set_widget_value(widget, read())
        self._on_limit_changed()
        self._on_layer_toggled()

    # ------------------------------------------------------------------ tab 1: alignment
    def _tab_align(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        A = lambda: self.settings.align  # noqa: E731

        box, form = group("Source")
        self.source_label = QLabel("Aucune vidéo ouverte")
        self.source_label.setWordWrap(True)
        form.addRow(self.source_label)
        self.bayer_combo = QComboBox()
        for label, data in (("Automatique (selon le fichier)", None), ("Aucune (mono)", NO_BAYER),
                            ("RGGB", "RGGB"), ("GRBG", "GRBG"), ("GBRG", "GBRG"), ("BGGR", "BGGR")):
            self.bayer_combo.addItem(label, data)
        self.bayer_combo.currentIndexChanged.connect(self._on_bayer_changed)
        form.addRow("Matrice de Bayer :", self.bayer_combo)
        lay.addWidget(box)

        box, form = group("Objet")
        self.mode_combo = QComboBox()
        for label, data in (("Automatique", "auto"), ("Planète (disque sur fond noir)", "planet"),
                            ("Surface (Lune, Soleil)", "surface")):
            self.mode_combo.addItem(label, data)
        self._bind_attr(self.mode_combo, A, "mode", self._invalidate_analysis)
        form.addRow("Type :", self.mode_combo)
        self.noise_spin = dspin(0.0, 5.0, 1.5, 0.25, 2)
        self.noise_spin.setToolTip("Lissage appliqué avant la mesure de netteté : augmentez-le pour "
                                   "des vidéos bruitées afin que le bruit ne passe pas pour du détail.")
        self._bind_attr(self.noise_spin, A, "quality_noise", self._invalidate_analysis)
        form.addRow("Robustesse au bruit :", self.noise_spin)
        self.ref_spin = spin(0, 500, 0)
        self.ref_spin.setSpecialValueText("auto")
        self.ref_spin.setToolTip("Nombre de meilleures images moyennées pour la référence (auto = 10 %, 3 à 50)")
        self._bind_attr(self.ref_spin, A, "reference_frames", self._invalidate_reference)
        form.addRow("Images de référence :", self.ref_spin)
        lay.addWidget(box)

        box, form = group("Points d'alignement")
        self.ap_spacing = spin(8, 400, 30, " px")
        self._bind_attr(self.ap_spacing, A, "ap_spacing", self._replace_points)
        form.addRow("Espacement :", self.ap_spacing)
        self.ap_box = spin(8, 400, 35, " px")
        self._bind_attr(self.ap_box, A, "ap_box_size", self._replace_points)
        form.addRow("Taille des boîtes :", self.ap_box)
        self.ap_radius = spin(1, 100, 10, " px")
        self.ap_radius.setToolTip("Déplacement local maximal recherché autour de chaque point")
        self._bind_attr(self.ap_radius, A, "search_radius", self._replace_points)
        form.addRow("Rayon de recherche :", self.ap_radius)
        self.ap_min = spin(0, 255, 30)
        self._bind_attr(self.ap_min, A, "min_brightness", self._replace_points)
        form.addRow("Luminosité min. :", self.ap_min)
        self.ap_max = spin(0, 255, 255)
        self._bind_attr(self.ap_max, A, "max_brightness", self._replace_points)
        form.addRow("Luminosité max. :", self.ap_max)
        self.ap_edge = spin(0, 500, 20, " px")
        self._bind_attr(self.ap_edge, A, "edge_margin", self._replace_points)
        form.addRow("Marge au bord :", self.ap_edge)
        self.ap_maxn = spin(1, 5000, 500)
        self._bind_attr(self.ap_maxn, A, "max_points", self._replace_points)
        form.addRow("Nombre maximal :", self.ap_maxn)
        self.ap_struct = dspin(0.0, 100.0, 5.0, 1.0, 0, " %")
        self.ap_struct.setToolTip("Écarte les zones sans détail (moins de x % du détail de la meilleure zone)")
        self._bind(self.ap_struct, lambda: self.settings.align.min_structure * 100.0,
                   lambda v: setattr(self.settings.align, "min_structure", v / 100.0), self._replace_points)
        form.addRow("Détail minimal :", self.ap_struct)
        self.points_btn = QPushButton("Placer les points")
        self.points_btn.clicked.connect(self.place_points)
        form.addRow(self.points_btn)
        self.points_label = QLabel("")
        self.points_label.setWordWrap(True)
        form.addRow(self.points_label)
        form.addRow(hint(f"{CMD} + clic sur l'image : ajouter un point · Maj + clic : supprimer · "
                         "molette : zoom · glisser : déplacer"))
        lay.addWidget(box)

        self.align_btn = QPushButton("Aligner")
        self.align_btn.setObjectName("primary")
        self.align_btn.clicked.connect(self.align)
        lay.addWidget(self.align_btn)
        self.align_label = QLabel("")
        self.align_label.setWordWrap(True)
        lay.addWidget(self.align_label)
        lay.addStretch(1)
        return w

    # ------------------------------------------------------------------ tab 2: selection
    def _tab_select(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        L = lambda: self.settings.limit  # noqa: E731
        box, form = group("Garder les meilleures images")
        self.limit_method = QComboBox()
        for label, data in (("Pourcentage", "percent"), ("Nombre d'images", "count"),
                            ("Qualité minimale", "quality")):
            self.limit_method.addItem(label, data)
        self._bind_attr(self.limit_method, L, "method", self._on_limit_changed)
        form.addRow("Méthode :", self.limit_method)
        self.limit_percent = dspin(0.1, 100.0, 80.0, 5.0, 1, " %")
        self._bind_attr(self.limit_percent, L, "percent", self._on_limit_changed)
        form.addRow("Pourcentage :", self.limit_percent)
        self.limit_count = spin(1, 1_000_000, 100)
        self._bind_attr(self.limit_count, L, "count", self._on_limit_changed)
        form.addRow("Nombre :", self.limit_count)
        self.limit_quality = dspin(0.0, 100.0, 50.0, 5.0, 1, " %")
        self.limit_quality.setToolTip("En pourcentage de la qualité de la meilleure image")
        self._bind_attr(self.limit_quality, L, "min_quality", self._on_limit_changed)
        form.addRow("Qualité minimale :", self.limit_quality)
        lay.addWidget(box)

        box, form = group("Qualité des images")
        self.quality_plot = QualityPlot()
        self.quality_plot.cutoffRequested.connect(self._on_plot_cutoff)
        form.addRow(self.quality_plot)
        self.select_label = QLabel("")
        form.addRow(self.select_label)
        form.addRow(hint("La barre sous l'image permet de parcourir la vidéo, dans l'ordre "
                         "chronologique ou de la meilleure à la pire image."))
        lay.addWidget(box)
        lay.addStretch(1)
        return w

    # ------------------------------------------------------------------ tab 3: stacking
    def _tab_stack(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        S = lambda: self.settings.stack  # noqa: E731
        box, form = group("Empilement")
        self.local_percent = dspin(1.0, 100.0, 100.0, 5.0, 0, " %")
        self.local_percent.setToolTip(
            "Pour chaque point d'alignement, ne garder que ce pourcentage des images retenues, "
            "les plus nettes à cet endroit précis (100 % = mêmes images partout, comme RegiStax).")
        self._bind_attr(self.local_percent, S, "local_percent")
        form.addRow("Sélection locale :", self.local_percent)
        self.scale_combo = QComboBox()
        for label, data in (("1× (taille d'origine)", 1.0), ("1,5×", 1.5), ("2×", 2.0), ("3×", 3.0)):
            self.scale_combo.addItem(label, data)
        self.scale_combo.setToolTip("Agrandissement pendant l'empilement (type « drizzle »)")
        self._bind_attr(self.scale_combo, S, "scale")
        form.addRow("Agrandissement :", self.scale_combo)
        self.norm_check = QCheckBox("Égaliser la luminosité des images")
        self.norm_check.setToolTip("Compense les variations de transparence (voiles, brume)")
        self._bind_attr(self.norm_check, S, "normalize_brightness")
        form.addRow(self.norm_check)
        self.weight_check = QCheckBox("Pondérer par la qualité")
        self._bind_attr(self.weight_check, S, "quality_weighting")
        form.addRow(self.weight_check)
        lay.addWidget(box)
        self.stack_btn = QPushButton("Empiler")
        self.stack_btn.setObjectName("primary")
        self.stack_btn.clicked.connect(self.stack)
        lay.addWidget(self.stack_btn)
        self.stack_label = QLabel("")
        self.stack_label.setWordWrap(True)
        lay.addWidget(self.stack_label)
        save = QPushButton("Enregistrer l'empilement brut…")
        save.clicked.connect(self.save_stacked)
        lay.addWidget(save)
        lay.addStretch(1)
        return w

    # ------------------------------------------------------------------ tab 4: wavelets
    def _tab_wavelets(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        W = lambda: self.settings.wavelet  # noqa: E731
        box, form = group("Méthode")
        self.wl_scheme = QComboBox()
        self.wl_scheme.addItem("B3-spline « à trous » (linéaire)", "b3spline")
        self.wl_scheme.addItem("Gaussienne", "gaussian")
        self._bind_attr(self.wl_scheme, W, "scheme", self._request_preview)
        form.addRow("Schéma :", self.wl_scheme)
        self.wl_step = QComboBox()
        self.wl_step.addItem("Dyadique (1, 2, 4, 8…)", "dyadic")
        self.wl_step.addItem("Linéaire (1, 2, 3, 4…)", "linear")
        self._bind_attr(self.wl_step, W, "step", self._request_preview)
        form.addRow("Progression :", self.wl_step)
        self.wl_initial = dspin(0.25, 8.0, 1.0, 0.25, 2, " px")
        self._bind_attr(self.wl_initial, W, "initial", self._request_preview)
        form.addRow("Taille de la 1ʳᵉ couche :", self.wl_initial)
        self.wl_target = QComboBox()
        self.wl_target.addItem("Canaux RVB", "rgb")
        self.wl_target.addItem("Luminance seulement", "luminance")
        self.wl_target.setToolTip("En luminance, l'accentuation n'amplifie pas le bruit de couleur")
        self._bind_attr(self.wl_target, W, "target", self._request_preview)
        form.addRow("Appliquer sur :", self.wl_target)
        lay.addWidget(box)

        box, form = group("Couches")
        self.layer_checks, self.layer_gain, self.layer_denoise = [], [], []
        for i in range(6):
            Li = lambda i=i: self.settings.wavelet.layers[i]  # noqa: E731
            chk = QCheckBox(f"Couche {i + 1}")
            self._bind_attr(chk, Li, "enabled", self._on_layer_toggled)
            gain = ValueSlider(0.0, 100.0, 0.1, 1.0, 1)
            gain.setToolTip("Accentuation : 1 = neutre, plus = plus de détail à cette échelle")
            self._bind_attr(gain, Li, "gain", self._request_preview)
            den = dspin(0.0, 1.0, 0.0, 0.05, 2)
            den.setToolTip("Débruitage de la couche (0 = aucun)")
            self._bind_attr(den, Li, "denoise", self._request_preview)
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.addWidget(gain, 1)
            rl.addWidget(QLabel("Débruit."))
            rl.addWidget(den)
            form.addRow(chk, row)
            self.layer_checks.append(chk)
            self.layer_gain.append(gain)
            self.layer_denoise.append(den)
        reset = QPushButton("Réinitialiser les couches")
        reset.clicked.connect(self._reset_wavelets)
        form.addRow(reset)
        form.addRow(hint("Couches 1-2 : détails fins (et bruit). Couches 3-4 : structures moyennes. "
                         "Couches 5-6 : grandes structures. Commencez par la couche 2 ou 3."))
        lay.addWidget(box)
        lay.addStretch(1)
        return w

    # ------------------------------------------------------------------ tab 5: finishing
    def _tab_post(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        P = lambda: self.settings.post  # noqa: E731

        box, form = group("Alignement des couleurs (dispersion atmosphérique)")
        btn = QPushButton("Alignement RVB automatique")
        btn.clicked.connect(self._auto_rgb_align)
        form.addRow(btn)
        self.shift_widgets = []
        for label, attr in (("Rouge", "shift_r"), ("Bleu", "shift_b")):
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            for k, axis in enumerate(("x", "y")):
                sp = dspin(-30.0, 30.0, 0.0, 0.1, 2, " px")
                self._bind(sp, lambda a=attr, k=k: getattr(self.settings.post, a)[k],
                           lambda v, a=attr, k=k: self._set_shift(a, k, v), self._request_preview)
                rl.addWidget(QLabel(axis))
                rl.addWidget(sp)
                self.shift_widgets.append(sp)
            form.addRow(f"{label} :", row)
        self.post_rgb_box = box
        lay.addWidget(box)

        box, form = group("Balance des couleurs")
        btn = QPushButton("Balance automatique")
        btn.clicked.connect(self._auto_balance)
        form.addRow(btn)
        for label, attr in (("Rouge", "gain_r"), ("Vert", "gain_g"), ("Bleu", "gain_b")):
            s = ValueSlider(0.2, 3.0, 0.01, 1.0, 2)
            self._bind_attr(s, P, attr, self._request_preview)
            form.addRow(f"{label} :", s)
        sat = ValueSlider(0.0, 3.0, 0.01, 1.0, 2)
        self._bind_attr(sat, P, "saturation", self._request_preview)
        form.addRow("Saturation :", sat)
        self.post_color_box = box
        lay.addWidget(box)

        box, form = group("Niveaux")
        for label, attr, lo, hi, step, val in (("Point noir", "black", 0.0, 0.5, 0.005, 0.0),
                                               ("Point blanc", "white", 0.3, 1.5, 0.005, 1.0),
                                               ("Gamma", "gamma", 0.2, 3.0, 0.01, 1.0),
                                               ("Luminosité", "brightness", -0.5, 0.5, 0.005, 0.0),
                                               ("Contraste", "contrast", 0.2, 3.0, 0.01, 1.0)):
            s = ValueSlider(lo, hi, step, val, 3)
            self._bind_attr(s, P, attr, self._request_preview)
            form.addRow(f"{label} :", s)
        btn = QPushButton("Étirement automatique")
        btn.clicked.connect(self._auto_levels)
        form.addRow(btn)
        lay.addWidget(box)

        box, form = group("Orientation")
        rot = QComboBox()
        for label, data in (("0°", 0), ("90° horaire", 90), ("180°", 180), ("90° antihoraire", 270)):
            rot.addItem(label, data)
        self._bind_attr(rot, P, "rotate", self._request_preview)
        form.addRow("Rotation :", rot)
        fh = QCheckBox("Miroir horizontal")
        self._bind_attr(fh, P, "flip_h", self._request_preview)
        fv = QCheckBox("Miroir vertical")
        self._bind_attr(fv, P, "flip_v", self._request_preview)
        form.addRow(fh)
        form.addRow(fv)
        lay.addWidget(box)

        reset = QPushButton("Réinitialiser les finitions")
        reset.clicked.connect(self._reset_post)
        lay.addWidget(reset)
        lay.addStretch(1)
        return w

    # =================================================================== file handling
    def _last_dir(self) -> str:
        return str(self.qsettings.value("last_dir", os.path.expanduser("~")))

    def open_video(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Ouvrir une vidéo ou une série d'images", self._last_dir(),
            f"{VIDEO_FILTER};;{IMAGE_FILTER};;Tous les fichiers (*)")
        if paths:
            self.load_source(paths)

    def open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir une image à traiter", self._last_dir(),
                                              f"{IMAGE_FILTER};;Tous les fichiers (*)")
        if path:
            self.load_image(path)

    def load_source(self, paths, bayer=None) -> None:
        if self._busy():
            return
        try:
            src = open_source(paths, bayer)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, APP_NAME, f"Impossible d'ouvrir le fichier :\n{exc}")
            return
        if self.source is not None:
            self.source.close()
        self.qsettings.setValue("last_dir", os.path.dirname(src.path))
        self.source = src
        self.pipeline = Pipeline(src, self.settings.copy())
        self.stacked = self.final = None
        self.view.set_points(None)
        self.source_label.setText(src.describe())
        with QSignalBlocker(self.bayer_combo):
            self.bayer_combo.setCurrentIndex(max(0, self.bayer_combo.findData(bayer)))
        self.setWindowTitle(f"{src.name} — {APP_NAME}")
        n = len(src)
        with QSignalBlocker(self.frame_slider), QSignalBlocker(self.frame_spin):
            self.frame_slider.setRange(0, n - 1)
            self.frame_spin.setRange(1, n)
            self.frame_slider.setValue(0)
            self.frame_spin.setValue(1)
        self.quality_plot.set_data(None, 0)
        self.points_label.setText("")
        self.align_label.setText("")
        self.stack_label.setText("")
        self.select_label.setText("")
        self.tabs.setCurrentIndex(TAB_ALIGN)
        self._view_mode = "frame"
        self._on_frame_slider(0, keep_view=False)
        self.status_label.setText(f"{src.describe()} — cliquez sur « Tout faire » (F5) ou procédez étape par étape.")
        self._update_enabled()

    def load_image(self, path: str) -> None:
        if self._busy():
            return
        try:
            img = read_image(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, APP_NAME, f"Impossible d'ouvrir l'image :\n{exc}")
            return
        self.qsettings.setValue("last_dir", os.path.dirname(path))
        if self.source is not None:
            self.source.close()
        self.source = None
        self.pipeline = None
        self._image_path = path
        self.setWindowTitle(f"{os.path.basename(path)} — {APP_NAME}")
        self.source_label.setText("Image seule (pas de vidéo)")
        self._set_stacked(img)
        self.tabs.setCurrentIndex(TAB_WAVELETS)
        self._update_enabled()

    def _on_bayer_changed(self) -> None:
        if self.source is None:
            return
        paths = getattr(self.source, "paths", None) or self.source.path
        self.load_source(paths, self.bayer_combo.currentData())

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if not paths:
            return
        ext = os.path.splitext(paths[0])[1].lower()
        if len(paths) == 1 and ext in IMAGE_EXTENSIONS:
            self.load_image(paths[0])
        else:
            self.load_source(paths)

    def _default_name(self, suffix: str) -> str:
        if self.source is not None:
            base, folder = os.path.splitext(self.source.name)[0], os.path.dirname(self.source.path)
        elif getattr(self, "_image_path", None):
            base, folder = os.path.splitext(os.path.basename(self._image_path))[0], os.path.dirname(self._image_path)
        else:
            base, folder = "planstax", self._last_dir()
        return os.path.join(folder, base.split(" … ")[0] + suffix)

    def _save(self, img: np.ndarray, suffix: str, title: str) -> None:
        filters = list(SAVE_FILTERS)
        last = str(self.qsettings.value("save_filter", filters[0]))
        path, chosen = QFileDialog.getSaveFileName(self, title, self._default_name(suffix + ".tif"),
                                                   ";;".join(filters), last if last in filters else filters[0])
        if not path:
            return
        ext, bits = SAVE_FILTERS.get(chosen, (".tif", 16))
        if not os.path.splitext(path)[1]:
            path += ext
        try:
            save_image(path, img, bits=bits)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, APP_NAME, f"Enregistrement impossible :\n{exc}")
            return
        self.qsettings.setValue("save_filter", chosen)
        self.status_label.setText(f"Enregistré : {path}")

    def save_final(self) -> None:
        if self.stacked is None:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            img = finish(self.stacked, self.settings)
        finally:
            QApplication.restoreOverrideCursor()
        self._save(img, "_planstax", "Enregistrer l'image traitée")

    def save_stacked(self) -> None:
        if self.stacked is not None:
            self._save(self.stacked, "_empilement", "Enregistrer l'empilement brut")

    # =================================================================== processing
    def _busy(self) -> bool:
        return self._task is not None and self._task.isRunning()

    def _run(self, fn, on_success, message: str) -> None:
        if self._busy():
            return
        self.pipeline.settings = self.settings.copy()
        task = Task(fn, self)
        task.progress.connect(self._on_progress)
        task.succeeded.connect(on_success)
        task.failed.connect(self._on_failed)
        task.cancelled.connect(lambda: self.status_label.setText("Traitement annulé."))
        task.finished.connect(self._on_task_finished)
        self._task = task
        self.status_label.setText(message)
        self.progress.setValue(0)
        self.progress.show()
        self.cancel_btn.show()
        self._update_enabled()
        task.start()

    def _on_progress(self, fraction: float, message: str) -> None:
        self.progress.setValue(int(fraction * 1000))
        self.status_label.setText(message)

    def _on_failed(self, message: str) -> None:
        self.status_label.setText("Erreur pendant le traitement.")
        QMessageBox.critical(self, APP_NAME, message)

    def _on_task_finished(self) -> None:
        self.progress.hide()
        self.cancel_btn.hide()
        self._task = None
        self._update_enabled()

    def _cancel_task(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self.status_label.setText("Annulation…")

    def _prepare_points(self, progress, cancel) -> None:
        p = self.pipeline
        if p.analysis is None:
            p.analyze(lambda f, m: progress(0.8 * f, m), cancel)
        if p.reference is None:
            p.build_reference(lambda f, m: progress(0.8 + 0.2 * f, m), cancel)
        if not len(p.points):
            p.place_points()

    def place_points(self) -> None:
        if self.pipeline is None:
            return

        def fn(progress, cancel):
            p = self.pipeline
            self._prepare_points(progress, cancel)
            p.place_points()

        self._run(fn, lambda _: self._after_points(), "Analyse de la vidéo…")

    def _after_points(self) -> None:
        self._update_analysis_views()
        self._view_mode = "reference"
        self._refresh_view(keep_view=False)
        if len(self.pipeline.points):
            self.status_label.setText(
                f"{len(self.pipeline.points)} points d'alignement placés. Ajustez-les si besoin puis cliquez sur « Aligner ».")
        else:
            self.status_label.setText("Aucun point d'alignement placé : l'explication est dans l'onglet Alignement.")

    def align(self) -> None:
        if self.pipeline is None:
            return

        def fn(progress, cancel):
            p = self.pipeline
            self._prepare_points(lambda f, m: progress(0.3 * f, m), cancel)
            p.align(lambda f, m: progress(0.3 + 0.7 * f, m), cancel)

        self._run(fn, lambda _: self._after_align(), "Alignement…")

    def _after_align(self) -> None:
        self._update_analysis_views()
        al = self.pipeline.alignment
        valid = float(al.local_valid.mean() * 100) if al.local_valid.size else 0.0
        self.align_label.setText(
            f"Alignement terminé : {len(self.source)} images, {len(self.pipeline.points)} points, "
            f"{valid:.0f} % des mesures locales fiables.")
        self.status_label.setText("Alignement terminé. Vérifiez la sélection puis empilez.")
        self.tabs.setCurrentIndex(TAB_SELECT)

    def stack(self) -> None:
        if self.pipeline is None:
            return

        def fn(progress, cancel):
            p = self.pipeline
            if p.alignment is None:
                self._prepare_points(lambda f, m: progress(0.2 * f, m), cancel)
                p.align(lambda f, m: progress(0.2 + 0.5 * f, m), cancel)
                return p.stack(lambda f, m: progress(0.7 + 0.3 * f, m), cancel)
            return p.stack(progress, cancel)

        self._run(fn, self._after_stack, "Empilement…")

    def do_all(self) -> None:
        if self.pipeline is None:
            if self.stacked is None:
                self.open_video()
            return

        def fn(progress, cancel):
            p = self.pipeline
            self._prepare_points(lambda f, m: progress(0.3 * f, m), cancel)
            p.align(lambda f, m: progress(0.3 + 0.45 * f, m), cancel)
            return p.stack(lambda f, m: progress(0.75 + 0.25 * f, m), cancel)

        self._run(fn, lambda img: self._after_stack(img, goto=TAB_WAVELETS), "Traitement complet…")

    def _after_stack(self, img: np.ndarray, goto: int | None = None) -> None:
        p = self.pipeline
        self._update_analysis_views()
        n_sel = len(p.selected)
        self.stack_label.setText(
            f"{n_sel} images empilées sur {len(self.source)}, {len(p.points)} points d'alignement, "
            f"{img.shape[1]}×{img.shape[0]} px.")
        self._set_stacked(img)
        if goto is not None:
            self.tabs.setCurrentIndex(goto)
        self.status_label.setText(f"Empilement terminé. Réglez les ondelettes puis enregistrez ({CMD}+S).")

    def _set_stacked(self, img: np.ndarray) -> None:
        self.stacked = img
        self.final = None
        self._stack_version += 1
        self._view_mode = "result"
        self._update_enabled()
        self._refresh_view(keep_view=False)
        self._request_preview()

    # ------------------------------------------------------------------ invalidation
    def _invalidate_analysis(self) -> None:
        if self.pipeline is not None:
            self.pipeline.analysis = None
            self.pipeline.reference = None
            self.pipeline.points = np.zeros((0, 2), dtype=np.int32)
            self.pipeline.alignment = None
            self.view.set_points(None)
            self.points_label.setText("Paramètres modifiés : cliquez sur « Placer les points ».")

    def _invalidate_reference(self) -> None:
        if self.pipeline is not None:
            self.pipeline.reference = None
            self.pipeline.points = np.zeros((0, 2), dtype=np.int32)
            self.pipeline.alignment = None
            self.view.set_points(None)
            self.points_label.setText("Paramètres modifiés : cliquez sur « Placer les points ».")

    def _replace_points(self) -> None:
        p = self.pipeline
        if p is None or p.reference is None or self._busy():
            return
        p.settings = self.settings.copy()
        p.place_points()
        self._update_points_overlay()

    def _add_point(self, x: float, y: float) -> None:
        p = self.pipeline
        if p is None or p.reference is None or self._busy() or self._view_mode != "reference":
            return
        half = self.settings.align.ap_box_size // 2 + self.settings.align.search_radius
        h, w = p.reference.shape
        xi, yi = int(round(x)), int(round(y))
        if not (half <= xi < w - half and half <= yi < h - half):
            self.status_label.setText("Trop près du bord pour placer un point ici.")
            return
        p.set_points(np.vstack([p.points, [[xi, yi]]]))
        self._update_points_overlay()

    def _remove_point(self, x: float, y: float) -> None:
        p = self.pipeline
        if p is None or not len(p.points) or self._busy() or self._view_mode != "reference":
            return
        d = np.hypot(p.points[:, 0] - x, p.points[:, 1] - y)
        i = int(np.argmin(d))
        if d[i] <= self.settings.align.ap_box_size:
            p.set_points(np.delete(p.points, i, axis=0))
            self._update_points_overlay()

    def _update_points_overlay(self) -> None:
        p = self.pipeline
        n = len(p.points) if p is not None else 0
        text = ""
        if p is not None and p.reference is not None:
            text = f"{n} point(s) d'alignement."
            if p.points_report is not None:
                # Placement explanation; the count reflects manual additions/removals.
                lines = p.points_report.explain(p.settings.align).split("\n")
                lines[0] = text
                text = "\n".join(l for l in lines if n == 0 or not l.startswith("→"))
        self.points_label.setText(text)
        if self._view_mode == "reference" and p is not None:
            self.view.set_points(p.points, self.settings.align.ap_box_size)
        else:
            self.view.set_points(None)

    # ------------------------------------------------------------------ selection
    def _on_limit_changed(self) -> None:
        method = self.settings.limit.method
        self.limit_percent.setEnabled(method == "percent")
        self.limit_count.setEnabled(method == "count")
        self.limit_quality.setEnabled(method == "quality")
        self._update_selection()

    def _update_selection(self) -> None:
        p = self.pipeline
        if p is None or p.analysis is None:
            self.quality_plot.set_data(None, 0)
            return
        p.settings.limit = dataclasses.replace(self.settings.limit)
        sel = p.select()
        self.quality_plot.set_data(p.analysis.quality, len(sel))
        n = len(self.source)
        self.select_label.setText(f"{len(sel)} images retenues sur {n} ({100 * len(sel) / n:.0f} %)")

    def _on_plot_cutoff(self, fraction: float) -> None:
        p = self.pipeline
        if p is None or p.analysis is None:
            return
        n = len(p.analysis.quality)
        keep = max(1, int(round(fraction * n)))
        lim = self.settings.limit
        if lim.method == "count":
            lim.count = keep
        elif lim.method == "quality":
            q = np.sort(p.analysis.quality)[::-1]
            lim.min_quality = float(q[keep - 1] / q[0] * 100.0)
        else:
            lim.percent = max(0.1, 100.0 * keep / n)
        self._settings_to_widgets()

    def _update_analysis_views(self) -> None:
        self._update_selection()
        self._update_points_overlay()

    # =================================================================== display
    def _on_tab(self, index: int) -> None:
        if index == TAB_ALIGN:
            self._view_mode = "reference" if (self.pipeline is not None and self.pipeline.reference is not None) else "frame"
        elif index == TAB_SELECT:
            self._view_mode = "frame"
        elif self.stacked is not None:
            self._view_mode = "result"
        self._refresh_view()
        self._update_enabled()

    def _refresh_view(self, keep_view: bool = True) -> None:
        self.frame_bar.setVisible(self.source is not None and self._view_mode == "frame")
        if self._view_mode == "frame" and self.source is not None:
            self._on_frame_slider(self.frame_slider.value(), keep_view)
        elif self._view_mode == "reference" and self.pipeline is not None and self.pipeline.reference is not None:
            self.view.set_image(self.pipeline.reference, keep_view)
            self._update_points_overlay()
        elif self._view_mode == "result" and self.stacked is not None:
            img = self.stacked if (self._show_before or self.final is None) else self.final
            self.view.set_image(img, keep_view)
            self.view.set_points(None)

    def _on_frame_slider(self, value: int, keep_view: bool = True) -> None:
        with QSignalBlocker(self.frame_spin):
            self.frame_spin.setValue(value + 1)
        if self.source is None or self._view_mode != "frame":
            return
        idx = value
        a = self.pipeline.analysis if self.pipeline else None
        if a is not None and self.frame_order.currentData() == "quality":
            idx = int(a.order[value])
        try:
            frame = self.source.frame(idx)
        except Exception as exc:  # noqa: BLE001
            self.frame_info.setText(f"Lecture impossible : {exc}")
            return
        self.view.set_image(frame, keep_view)
        self.view.set_points(None)
        info = f"n° {idx + 1}/{len(self.source)}"
        if a is not None:
            rank = int(np.flatnonzero(a.order == idx)[0]) + 1
            q = a.quality[idx] / max(a.quality.max(), 1e-12) * 100
            sel = self.pipeline.selected
            kept = bool(np.any(sel == idx)) if len(sel) else None
            info += f" · rang {rank} · qualité {q:.0f} %"
            if kept is not None:
                info += " · retenue" if kept else " · écartée"
        self.frame_info.setText(info)

    def _toggle_before(self, on: bool) -> None:
        self._show_before = on
        if self._view_mode == "result":
            self._refresh_view()

    # ------------------------------------------------------------------ preview
    def _request_preview(self) -> None:
        if self.stacked is not None:
            self._preview_timer.start()

    def _submit_preview(self) -> None:
        if self.stacked is None:
            return
        self._preview_token += 1
        self.preview.submit(self._preview_token, (self.stacked, self._stack_version, self.settings.copy()))

    def _compute_preview(self, payload):
        """Runs in the preview thread."""
        stacked, version, settings = payload
        key = (version, tuple(settings.post.shift_r), tuple(settings.post.shift_b))
        if key != self._pre_key:
            self._pre_wp.set_image(apply_pre(stacked, settings.post))
            self._pre_key = key
        img = self._pre_wp.render(settings.wavelet)
        return apply_post(img, settings.post)

    def _on_preview(self, img: np.ndarray, token: int) -> None:
        if token != self._preview_token:
            return  # a newer request is on its way
        self.final = img
        if self._view_mode == "result" and not self._show_before:
            self.view.set_image(img, keep_view=True)

    # ------------------------------------------------------------------ wavelet / post helpers
    def _on_layer_toggled(self) -> None:
        for chk, gain, den in zip(self.layer_checks, self.layer_gain, self.layer_denoise):
            gain.setEnabled(chk.isChecked())
            den.setEnabled(chk.isChecked())
        self._request_preview()

    def _reset_wavelets(self) -> None:
        from ..settings import WaveletSettings
        self.settings.wavelet = WaveletSettings()
        self._settings_to_widgets()
        self._request_preview()

    def _reset_post(self) -> None:
        from ..settings import PostSettings
        self.settings.post = PostSettings()
        self._settings_to_widgets()
        self._request_preview()

    def _set_shift(self, attr: str, k: int, v: float) -> None:
        cur = list(getattr(self.settings.post, attr))
        cur[k] = float(v)
        setattr(self.settings.post, attr, tuple(cur))

    def _auto_rgb_align(self) -> None:
        if self.stacked is None or self.stacked.ndim != 3:
            return
        (rx, ry), (bx, by) = estimate_rgb_shifts(self.stacked)
        self.settings.post.shift_r = (round(rx, 2), round(ry, 2))
        self.settings.post.shift_b = (round(bx, 2), round(by, 2))
        self._settings_to_widgets()
        self._request_preview()
        self.status_label.setText(f"Décalages mesurés — rouge : ({rx:+.2f}, {ry:+.2f}) px, bleu : ({bx:+.2f}, {by:+.2f}) px")

    def _auto_balance(self) -> None:
        if self.stacked is None or self.stacked.ndim != 3:
            return
        r, g, b = auto_balance(apply_pre(self.stacked, self.settings.post))
        p = self.settings.post
        p.gain_r, p.gain_g, p.gain_b = round(r, 2), round(g, 2), round(b, 2)
        self._settings_to_widgets()
        self._request_preview()

    def _auto_levels(self) -> None:
        if self.stacked is None:
            return
        from ..core.wavelets import apply_wavelets
        img = apply_wavelets(apply_pre(self.stacked, self.settings.post), self.settings.wavelet)
        lo, hi = np.percentile(img, (0.5, 99.95))
        p = self.settings.post
        p.black = float(np.clip(lo, 0.0, 0.5))
        p.white = float(np.clip(hi, p.black + 0.05, 1.5))
        self._settings_to_widgets()
        self._request_preview()

    # =================================================================== presets
    def _fill_presets_menu(self) -> None:
        m = self.presets_menu
        m.clear()
        names = list_presets()
        if names:
            for name in names:
                a = m.addAction(name)
                a.triggered.connect(lambda _=False, n=name: self._load_preset(n))
        else:
            a = m.addAction("(aucun préréglage)")
            a.setEnabled(False)
        m.addSeparator()
        m.addAction("Enregistrer les réglages actuels…", self._save_preset)
        m.addAction("Importer depuis RegiStax 6…", self._import_registax)
        m.addAction("Réglages par défaut", self._default_settings)
        m.addSeparator()
        m.addAction("Ouvrir le dossier des préréglages",
                    lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(presets_dir())))

    def _load_preset(self, name: str) -> None:
        try:
            self.settings = load_preset(name)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, APP_NAME, f"Préréglage illisible :\n{exc}")
            return
        self._apply_new_settings()
        self.status_label.setText(f"Préréglage « {name} » chargé.")

    def _default_settings(self) -> None:
        self.settings = Settings()
        self._apply_new_settings()

    def _apply_new_settings(self) -> None:
        self._settings_to_widgets()
        if self.pipeline is not None:
            self._invalidate_analysis()
            self.pipeline.settings = self.settings.copy()
        self._request_preview()

    def _save_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "Enregistrer un préréglage", "Nom du préréglage :")
        if ok and name.strip():
            save_preset(name.strip(), self.settings)
            self.status_label.setText(f"Préréglage « {name.strip()} » enregistré.")

    def _import_registax(self) -> None:
        default = r"C:\Program Files (x86)\RegiStax 6"
        folder = QFileDialog.getExistingDirectory(self, "Dossier de RegiStax 6",
                                                  default if os.path.isdir(default) else self._last_dir())
        if not folder:
            return
        imported = import_all_registax(folder)
        if imported:
            lines = []
            for name in imported:
                pos = registax_wavelet_positions(folder, name)
                if pos:
                    lines.append(f"  {name} : " + ", ".join(str(p) for p in pos))
            QMessageBox.information(
                self, APP_NAME,
                "Préréglages importés : " + ", ".join(imported) + ".\n\n"
                "Points d'alignement, sélection et type d'ondelettes sont repris tels quels. "
                "Les curseurs d'ondelettes, eux, ne peuvent pas être convertis (la formule de "
                "RegiStax n'est pas publique) : ils sont laissés au neutre, à régler à l'œil.\n\n"
                "Positions RegiStax d'origine (couches 1 à 6, 10 = neutre) :\n" + "\n".join(lines))
        else:
            QMessageBox.warning(self, APP_NAME, "Aucun fichier de réglages RegiStax (estimate-*.ini, "
                                                "wavelet-*.ini…) trouvé dans ce dossier.")

    def _load_last_settings(self) -> Settings:
        path = os.path.join(config_dir(), "last.json")
        try:
            with open(path, encoding="utf-8") as fh:
                return Settings.from_dict(json.load(fh))
        except (OSError, ValueError):
            return Settings()

    def _save_last_settings(self) -> None:
        try:
            with open(os.path.join(config_dir(), "last.json"), "w", encoding="utf-8") as fh:
                json.dump(self.settings.to_dict(), fh, indent=2, ensure_ascii=False)
        except OSError:
            pass

    # =================================================================== misc
    def _update_enabled(self) -> None:
        busy = self._busy()
        has_src = self.pipeline is not None
        has_img = self.stacked is not None
        for wdg in (self.points_btn, self.align_btn, self.stack_btn):
            wdg.setEnabled(has_src and not busy)
        self.act_doall.setEnabled(not busy)
        self.act_open.setEnabled(not busy)
        self.act_open_img.setEnabled(not busy)
        self.act_batch.setEnabled(not busy)
        self.act_save.setEnabled(has_img and not busy)
        self.act_save_raw.setEnabled(has_img and not busy)
        self.bayer_combo.setEnabled(has_src and not busy)
        # Processing settings are frozen while a task runs (the worker reads the pipeline).
        for i in (TAB_ALIGN, TAB_SELECT, TAB_STACK):
            self.tabs.widget(i).widget().setEnabled(has_src and not busy)
        for i in (TAB_WAVELETS, TAB_POST):
            self.tabs.widget(i).widget().setEnabled(has_img)
        color = has_img and self.stacked.ndim == 3
        self.post_rgb_box.setEnabled(color)
        self.post_color_box.setEnabled(color)

    def _set_theme(self, key: str) -> None:
        self.qsettings.setValue("theme", key)
        theme.apply(QApplication.instance(), key)
        self._apply_overlay_color()

    def _apply_overlay_color(self) -> None:
        night = self.qsettings.value("theme", "dark") == "night"
        self.view.set_point_color(QColor(255, 60, 40) if night else QColor(80, 220, 120))

    def _show_help(self) -> None:
        QMessageBox.information(self, "Guide rapide", (
            f"1. Ouvrez une vidéo SER ou AVI ({CMD}+O, ou glisser-déposer).\n"
            "2. Cliquez sur « Tout faire » (F5) : analyse de la qualité, image de référence, "
            "points d'alignement, alignement, sélection et empilement.\n"
            "3. Onglet Ondelettes : montez le gain des couches 1 à 3 pour faire ressortir les détails, "
            "et utilisez le débruitage des couches 1-2 si le bruit apparaît.\n"
            "4. Onglet Finitions : alignement RVB automatique, balance des couleurs, niveaux.\n"
            f"5. Enregistrez ({CMD}+S) en TIFF 16 bits.\n\n"
            "Plusieurs vidéos : déposez-les dans le dossier « input », puis Fichier → Traitement "
            f"par lot ({CMD}+L). Une image par vidéo est écrite dans le dossier « output ».\n\n"
            f"Pour affiner : réglez les points dans l'onglet Alignement ({CMD}+clic pour en ajouter, "
            "Maj+clic pour en retirer), le pourcentage d'images gardées dans l'onglet Sélection, "
            "et la sélection locale dans l'onglet Empilement.\n\n"
            "Touche B : avant/après · F : ajuster · 1 : 100 % · P : afficher les points."))

    def open_batch(self) -> None:
        if self._busy():
            return
        from .batch import BatchDialog
        dlg = BatchDialog(lambda: self.settings, self.qsettings, self)
        dlg.exec()
        dlg.deleteLater()

    def _desktop_shortcut(self) -> None:
        from .shortcut import create_desktop_shortcut
        try:
            path = create_desktop_shortcut()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, APP_NAME, f"Impossible de créer le raccourci :\n{exc}")
            return
        QMessageBox.information(self, APP_NAME, f"Raccourci créé sur le Bureau :\n{path}")

    def _show_about(self) -> None:
        QMessageBox.about(self, f"À propos de {APP_NAME}", (
            f"<b>{APP_NAME} {__version__}</b><br>"
            "Empilement « lucky imaging » et ondelettes pour l'imagerie planétaire.<br><br>"
            "Programme indépendant écrit de zéro, inspiré du déroulement de travail de RegiStax 6 "
            "(sans lien avec RegiStax ni son auteur) : alignement multipoints, sélection des "
            "meilleures images, empilement local, ondelettes à 6 couches.<br><br>"
            "Formats : SER, AVI, FITS, TIFF, PNG, JPEG.<br>Licence MIT. Copyright Bernard Allouche"))

    def closeEvent(self, event) -> None:
        if self._task is not None and self._task.isRunning():
            self._task.cancel()
            self._task.wait(5000)
        self.preview.stop()
        self._save_last_settings()
        self.qsettings.setValue("geometry", self.saveGeometry())
        self.qsettings.sync()  # the portable launcher ends the process right after the window closes
        if self.source is not None:
            self.source.close()
        super().closeEvent(event)


def _widget_value(w):
    if isinstance(w, QCheckBox):
        return w.isChecked()
    if isinstance(w, QComboBox):
        return w.currentData()
    if isinstance(w, QSpinBox):
        return int(w.value())
    if isinstance(w, (QDoubleSpinBox, ValueSlider)):
        return float(w.value())
    raise TypeError(type(w))


def _set_widget_value(w, v) -> None:
    if isinstance(w, QCheckBox):
        w.setChecked(bool(v))
    elif isinstance(w, QComboBox):
        i = w.findData(v)
        if i < 0 and isinstance(v, float):
            i = next((k for k in range(w.count()) if w.itemData(k) == v), -1)
        w.setCurrentIndex(max(0, i))
    elif isinstance(w, QSpinBox):
        w.setValue(int(v))
    else:
        w.setValue(float(v))
