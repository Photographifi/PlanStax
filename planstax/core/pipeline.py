"""Processing pipeline: analyse → reference → alignment points → align → select → stack.

Each step can be re-run on its own (the GUI does that when a setting changes); `run_all`
chains them. Frame passes are parallelised with threads (OpenCV and NumPy release the GIL).
"""

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Callable

import numpy as np

from ..i18n import tr
from ..io.sources import FrameSource, luminance
from ..settings import Settings
from .alignment import GlobalAligner, StabilityMap, sample_shifted
from .localalign import LocalAligner, PlacementReport, place_points_with_report
from .quality import COLOUR, CUT, DARK, KEEP, analyze_frame, detect_surface, reject_frames
from .stacking import Stacker

Progress = Callable[[float, str], None]


class Cancelled(Exception):
    pass


def default_workers() -> int:
    return max(1, min(16, (os.cpu_count() or 2)))


def map_frames(source: FrameSource, indices, fn, *, workers: int, progress: Progress | None,
               cancel: threading.Event | None, label: str) -> list:
    """Run fn(index, frame) on every frame index in parallel; results are returned in order."""
    indices = list(indices)
    results: list = [None] * len(indices)
    if not indices:
        return results
    stop = threading.Event()

    def task(k: int) -> None:
        if stop.is_set() or (cancel is not None and cancel.is_set()):
            return
        i = indices[k]
        results[k] = fn(i, source.frame(i))

    n = len(indices)
    t_last = 0.0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        pending = {ex.submit(task, k) for k in range(n)}
        done_count = 0
        while pending:
            done, pending = wait(pending, timeout=0.2, return_when=FIRST_EXCEPTION)
            for f in done:
                exc = f.exception()
                if exc is not None:
                    stop.set()
                    for p in pending:
                        p.cancel()
                    raise exc
            done_count += len(done)
            if cancel is not None and cancel.is_set():
                stop.set()
                for p in pending:
                    p.cancel()
                raise Cancelled()
            now = time.monotonic()
            if progress and (now - t_last > 0.1 or not pending):
                progress(done_count / n, tr("{label} : {done}/{total}", label=label, done=done_count, total=n))
                t_last = now
    return results


@dataclass
class Analysis:
    quality: np.ndarray      # (n,) global quality, 0 for the rejected frames
    centroids: np.ndarray    # (n, 2)
    brightness: np.ndarray   # (n,)
    surface: bool
    rejected: np.ndarray     # (n,) why each frame is left out: KEEP, DARK, COLOUR or CUT (core.quality)

    @property
    def usable(self) -> np.ndarray:
        return self.rejected == KEEP

    @property
    def order(self) -> np.ndarray:
        """Frame indices sorted best first, the rejected frames last."""
        return np.lexsort((-self.quality, ~self.usable))

    def rejected_counts(self) -> tuple[int, int, int]:
        """(empty or dark frames, frames where the planet is cut, frames with wrong colours)."""
        return tuple(int(np.count_nonzero(self.rejected == r)) for r in (DARK, CUT, COLOUR))


@dataclass
class Alignment:
    global_shifts: np.ndarray   # (n, 2)
    responses: np.ndarray       # (n,)
    local_shifts: np.ndarray    # (n, n_points, 2) total displacement per AP
    local_valid: np.ndarray     # (n, n_points) bool
    local_quality: np.ndarray   # (n, n_points)


class Pipeline:
    def __init__(self, source: FrameSource, settings: Settings | None = None,
                 workers: int | None = None) -> None:
        self.source = source
        self.settings = settings or Settings()
        self.workers = workers or default_workers()
        self.analysis: Analysis | None = None
        self.reference: np.ndarray | None = None
        self.reference_index: int = 0
        self.points: np.ndarray = np.zeros((0, 2), dtype=np.int32)
        self.points_report: PlacementReport | None = None
        self.alignment: Alignment | None = None
        self.selected: np.ndarray = np.zeros(0, dtype=np.int64)
        self.stacked: np.ndarray | None = None
        self._aligner: GlobalAligner | None = None

    # ------------------------------------------------------------------ steps
    def analyze(self, progress: Progress | None = None, cancel: threading.Event | None = None) -> Analysis:
        s = self.settings.align

        def fn(i: int, frame: np.ndarray):
            st = analyze_frame(luminance(frame), s.quality_noise, frame)
            return st.quality, st.centroid, st.brightness, st.cut, st.colour

        res = map_frames(self.source, range(len(self.source)), fn, workers=self.workers,
                         progress=progress, cancel=cancel, label=tr("Analyse de la qualité"))
        quality = np.array([r[0] for r in res], dtype=np.float64)
        centroids = np.array([r[1] for r in res], dtype=np.float64)
        brightness = np.array([r[2] for r in res], dtype=np.float64)
        cut = np.array([r[3] for r in res], dtype=bool)
        colour = np.array([r[4] for r in res], dtype=np.float64) if self.source.is_color else None
        rejected = np.full(len(quality), KEEP, dtype=np.int8)
        if s.reject_frames:
            rejected = reject_frames(brightness, cut, colour)
        best = int(np.argmax(np.where(rejected == KEEP, quality, -np.inf)))
        surface = (s.mode == "surface") or (s.mode == "auto" and detect_surface(luminance(self.source.frame(best))))
        if surface and s.reject_frames:
            # A surface fills the frame: reaching its edge is the rule, no reason to leave a frame out.
            rejected = reject_frames(brightness, np.zeros_like(cut), colour)
        quality[rejected != KEEP] = 0.0
        self.analysis = Analysis(quality, centroids, brightness, surface, rejected)
        self.alignment = None
        return self.analysis

    def build_reference(self, progress: Progress | None = None, cancel: threading.Event | None = None) -> np.ndarray:
        """Average the best frames, globally aligned on the very best one."""
        if self.analysis is None:
            self.analyze(progress, cancel)
        a = self.analysis
        n = int(np.count_nonzero(a.usable))
        count = self.settings.align.reference_frames or int(np.clip(round(n * 0.1), 3, 50))
        count = int(max(1, min(count, n)))
        order = a.order
        best = int(order[0])
        best_lum = luminance(self.source.frame(best)).astype(np.float32)
        aligner = GlobalAligner(best_lum, a.surface, tuple(a.centroids[best]),
                                search=self.settings.align.search_radius)
        acc = np.zeros_like(best_lum, dtype=np.float64)
        h, w = best_lum.shape
        stability = StabilityMap(w, h) if a.surface else None
        for k, i in enumerate(order[:count]):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            lum = luminance(self.source.frame(int(i))).astype(np.float32)
            dx, dy, _ = aligner.measure(lum, tuple(a.centroids[i]))
            aligned = sample_shifted(lum, dx, dy, w, h)
            acc += aligned
            if stability is not None:
                stability.add(aligned)
            if progress:
                progress((k + 1) / count, tr("Image de référence : {done}/{total}", done=k + 1, total=count))
        self.reference = (acc / count).astype(np.float32)
        self.reference_index = best
        self._aligner = GlobalAligner(self.reference, a.surface, tuple(a.centroids[best]),
                                      search=self.settings.align.search_radius,
                                      stability=stability.result() if stability else None)
        self.alignment = None
        return self.reference

    def place_points(self) -> np.ndarray:
        if self.reference is None:
            self.build_reference()
        self.points, self.points_report = place_points_with_report(self.reference, self.settings.align)
        self.alignment = None
        return self.points

    def set_points(self, points: np.ndarray) -> None:
        self.points = np.asarray(points, dtype=np.int32).reshape(-1, 2)
        self.alignment = None

    def align(self, progress: Progress | None = None, cancel: threading.Event | None = None) -> Alignment:
        if self.reference is None:
            self.build_reference(progress, cancel)
        if self._aligner is None:
            raise RuntimeError("Référence non initialisée")
        s = self.settings.align
        local = LocalAligner(self.reference, self.points, s.ap_box_size, s.search_radius, s.quality_noise)
        a = self.analysis
        aligner = self._aligner

        def fn(i: int, frame: np.ndarray):
            lum = luminance(frame).astype(np.float32, copy=False)
            dx, dy, resp = aligner.measure(lum, tuple(a.centroids[i]))
            shifts, valid, quality = local.measure(lum, (dx, dy))
            return dx, dy, resp, shifts, valid, quality

        res = map_frames(self.source, range(len(self.source)), fn, workers=self.workers,
                         progress=progress, cancel=cancel, label=tr("Alignement"))
        n_pts = len(self.points)
        self.alignment = Alignment(
            global_shifts=np.array([[r[0], r[1]] for r in res], dtype=np.float64),
            responses=np.array([r[2] for r in res], dtype=np.float64),
            local_shifts=np.stack([r[3] for r in res]) if n_pts else np.zeros((len(res), 0, 2), np.float32),
            local_valid=np.stack([r[4] for r in res]) if n_pts else np.zeros((len(res), 0), bool),
            local_quality=np.stack([r[5] for r in res]) if n_pts else np.zeros((len(res), 0), np.float32),
        )
        return self.alignment

    def select(self) -> np.ndarray:
        """Global frame selection ("limit") from the quality ranking, among the usable frames."""
        if self.analysis is None:
            raise RuntimeError("Analyse non effectuée")
        lim = self.settings.limit
        q = self.analysis.quality
        n = int(np.count_nonzero(self.analysis.usable))
        order = self.analysis.order[:n]  # the rejected frames never enter the stack
        if lim.method == "count":
            k = int(np.clip(lim.count, 1, n))
        elif lim.method == "quality":
            k = int(max(1, np.count_nonzero(q[order] >= q.max() * lim.min_quality / 100.0)))
        else:
            k = int(np.clip(round(n * lim.percent / 100.0), 1, n))
        self.selected = np.sort(order[:k])
        return self.selected

    def stack(self, progress: Progress | None = None, cancel: threading.Event | None = None) -> np.ndarray:
        if self.alignment is None:
            self.align(progress, cancel)
        self.select()
        st = self.settings.stack
        al = self.alignment
        sel = self.selected
        n_pts = len(self.points)

        # Per-AP local selection among the globally selected frames.
        use = np.zeros((len(self.source), n_pts), dtype=bool)
        local_w = None
        if n_pts:
            lq = np.where(al.local_valid[sel], al.local_quality[sel], -np.inf)
            keep = max(1, int(round(len(sel) * st.local_percent / 100.0)))
            ranks = np.argsort(-lq, axis=0, kind="stable")[:keep]  # (keep, n_pts)
            sub = np.zeros_like(lq, dtype=bool)
            np.put_along_axis(sub, ranks, True, axis=0)
            sub &= np.isfinite(lq)
            use[sel] = sub
            if st.quality_weighting:
                best_local = np.max(np.where(np.isfinite(lq), lq, 0.0), axis=0)
                local_w = np.zeros((len(self.source), n_pts), dtype=np.float32)
                local_w[sel] = np.where(sub, np.clip(lq, 0, None) / np.maximum(best_local, 1e-12), 0.0)

        q = self.analysis.quality
        global_w = np.ones(len(self.source))
        if st.quality_weighting:
            global_w = q / max(q[sel].max(), 1e-12)
        gain = np.ones(len(self.source))
        if st.normalize_brightness:
            ref_b = float(np.median(self.analysis.brightness[sel]))
            gain = ref_b / np.maximum(self.analysis.brightness, 1e-6)

        channels = 3 if self.source.is_color else 1
        stacker = Stacker(self.source.height, self.source.width, channels, self.points,
                          self.settings.align.ap_spacing, self.settings.align.ap_box_size, st.scale)

        def fn(i: int, frame: np.ndarray):
            if gain[i] != 1.0:
                frame = frame * np.float32(gain[i])
            stacker.add_background(frame, tuple(al.global_shifts[i]), float(global_w[i]))
            if n_pts:
                stacker.add_patches(frame, al.local_shifts[i], use[i],
                                    None if local_w is None else local_w[i])

        map_frames(self.source, sel, fn, workers=self.workers, progress=progress,
                   cancel=cancel, label=tr("Empilement"))
        # Cubic resampling can overshoot slightly past saturated pixels; clip rather than rescale.
        self.stacked = np.clip(stacker.result(), 0.0, 1.0)
        return self.stacked

    # ------------------------------------------------------------------ all-in-one
    def run_all(self, progress: Progress | None = None, cancel: threading.Event | None = None) -> np.ndarray:
        steps = [(0.0, 0.25), (0.25, 0.30), (0.30, 0.70), (0.70, 1.0)]

        def sub(k: int) -> Progress | None:
            if progress is None:
                return None
            a, b = steps[k]
            return lambda f, msg: progress(a + (b - a) * f, msg)

        self.analyze(sub(0), cancel)
        self.build_reference(sub(1), cancel)
        self.place_points()
        self.align(sub(2), cancel)
        return self.stack(sub(3), cancel)
