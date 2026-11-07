"""Local-alignment stacking.

Two accumulators are fed for every frame:
  * a background stack: the whole frame aligned with its global shift;
  * one patch stack per alignment point: a window around the AP sampled at the AP's own
    displacement (this is what corrects seeing-induced local distortion).
Patches are finally blended with overlapping sin² windows; where AP coverage fades out
(sky, limb, frame edges) the background stack takes over smoothly.
Both are weighted pixel by pixel by the part of the frame that really covers them
(alignment.coverage): a frame that drifted adds nothing past its own edges.
"""

from __future__ import annotations

import threading

import cv2
import numpy as np

from ..i18n import tr
from .alignment import COVERAGE_FLOOR, coverage_ramps, sample_shifted


def patch_window(size: int) -> np.ndarray:
    t = np.sin(np.pi * (np.arange(size) + 0.5) / size) ** 2
    return np.outer(t, t).astype(np.float32)


class _Accum:
    def __init__(self, out_shape: tuple[int, ...], n_points: int, patch: int, channels: int) -> None:
        self.bg = np.zeros(out_shape, dtype=np.float32)
        self.bg_w = np.zeros(out_shape[:2], dtype=np.float32)  # per pixel: frames that cover it
        shape = (n_points, patch, patch) + ((channels,) if channels > 1 else ())
        self.patches = np.zeros(shape, dtype=np.float32)
        self.patch_cover = np.zeros((n_points, patch, patch), dtype=np.float32)
        self.patch_w = np.zeros(n_points, dtype=np.float64)  # all the frames used, covering or not


class Stacker:
    def __init__(self, height: int, width: int, channels: int, points: np.ndarray,
                 spacing: int, box: int, scale: float = 1.0) -> None:
        self.h, self.w, self.c = height, width, channels
        self.scale = float(scale)
        self.out_h = int(round(height * self.scale))
        self.out_w = int(round(width * self.scale))
        self.out_shape = (self.out_h, self.out_w) + ((channels,) if channels > 1 else ())
        self.points = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        # Patch side (reference pixels): twice the grid spacing so neighbouring windows overlap
        # by half and the sin² windows sum to one; never smaller than the alignment box.
        self.patch = max(2 * int(spacing), int(box), 8)
        self.patch_out = int(round(self.patch * self.scale))
        # Top-left corner of each patch on the output grid.
        self.origins = np.round((self.points - self.patch / 2.0) * self.scale).astype(np.int64)
        self._local = threading.local()
        self._accums: list[_Accum] = []
        self._lock = threading.Lock()

    def _acc(self) -> _Accum:
        acc = getattr(self._local, "acc", None)
        if acc is None:
            acc = _Accum(self.out_shape, len(self.points), self.patch_out, self.c)
            self._local.acc = acc
            with self._lock:
                self._accums.append(acc)
        return acc

    def _src_origin(self, ox: float, oy: float, dx: float, dy: float) -> tuple[float, float]:
        s = self.scale
        return (ox + 0.5) / s - 0.5 + dx, (oy + 0.5) / s - 0.5 + dy

    def _sample(self, frame: np.ndarray, x0: float, y0: float, width: int, height: int,
                weight: float, floor: float = 0.0) -> tuple[np.ndarray, np.ndarray | float]:
        """The window of `frame` sampled at (x0, y0), multiplied by its per-pixel weight, and
        that weight: `weight` where the frame covers the window, `floor` × `weight` past its
        edges (a plain number when the window lies well inside the frame)."""
        img = sample_shifted(frame, x0, y0, width, height, self.scale, border=cv2.BORDER_REPLICATE)
        ry, rx = coverage_ramps(self.w, self.h, x0, y0, width, height, self.scale)
        if ry.min() >= 1.0 and rx.min() >= 1.0:  # the usual case for a patch
            if weight != 1.0:
                img *= np.float32(weight)
            return img, weight
        cover = np.outer(ry, rx)
        if floor > 0.0:
            np.maximum(cover, np.float32(floor), out=cover)
        cover *= np.float32(weight)
        img *= cover[..., None] if img.ndim == 3 else cover
        return img, cover

    def add_background(self, frame: np.ndarray, d: tuple[float, float], weight: float = 1.0) -> None:
        acc = self._acc()
        x0, y0 = self._src_origin(0, 0, d[0], d[1])
        # The floor keeps a value for a pixel no frame covers, without weighing anywhere else.
        img, cover = self._sample(frame, x0, y0, self.out_w, self.out_h, weight, COVERAGE_FLOOR)
        acc.bg += img
        acc.bg_w += cover

    def add_patches(self, frame: np.ndarray, shifts: np.ndarray, use: np.ndarray,
                    weights: np.ndarray | None = None) -> None:
        acc = self._acc()
        size = self.patch_out
        for i in np.flatnonzero(use):
            ox, oy = self.origins[i]
            x0, y0 = self._src_origin(ox, oy, shifts[i, 0], shifts[i, 1])
            w = 1.0 if weights is None else float(weights[i])
            p, cover = self._sample(frame, x0, y0, size, size, w)
            acc.patches[i] += p
            acc.patch_cover[i] += cover
            acc.patch_w[i] += w

    def result(self) -> np.ndarray:
        if not self._accums:
            raise RuntimeError(tr("Aucune image n'a été empilée"))
        bg = np.zeros(self.out_shape, dtype=np.float64)
        bg_w = np.zeros(self.out_shape[:2], dtype=np.float64)
        patches = np.zeros(self._accums[0].patches.shape, dtype=np.float64)
        patch_cover = np.zeros(self._accums[0].patch_cover.shape, dtype=np.float64)
        patch_w = np.zeros(len(self.points), dtype=np.float64)
        for a in self._accums:
            bg += a.bg
            bg_w += a.bg_w
            patches += a.patches
            patch_cover += a.patch_cover
            patch_w += a.patch_w
        bg_w = np.maximum(bg_w, 1e-30)
        background = (bg / (bg_w[..., None] if self.c > 1 else bg_w)).astype(np.float32)
        if not len(self.points) or not np.any(patch_w > 0):
            return np.clip(background, 0.0, None)

        win = patch_window(self.patch_out)
        expand = (lambda a: a[..., None]) if self.c > 1 else (lambda a: a)
        num = np.zeros(self.out_shape, dtype=np.float64)
        den = np.zeros(self.out_shape[:2] + ((1,) if self.c > 1 else ()), dtype=np.float64)
        size = self.patch_out
        for i in np.flatnonzero(patch_w > 0):
            ox, oy = self.origins[i]
            # Clip the patch to the output frame.
            x0, y0 = max(0, ox), max(0, oy)
            x1, y1 = min(self.out_w, ox + size), min(self.out_h, oy + size)
            if x1 <= x0 or y1 <= y0:
                continue
            sl = (slice(y0 - oy, y1 - oy), slice(x0 - ox, x1 - ox))
            cover = patch_cover[i][sl]
            p = patches[i][sl] / expand(np.maximum(cover, 1e-12))
            # Where few of the patch's frames reached (frame edge), the background takes over.
            w = expand(win[sl] * (cover / patch_w[i]))
            num[y0:y1, x0:x1] += w * p
            den[y0:y1, x0:x1] += w
        bg_weight = np.clip(1.0 - den, 0.0, None)
        out = (num + bg_weight * background) / (den + bg_weight)
        return np.clip(out, 0.0, None).astype(np.float32)
