"""Local-alignment stacking.

Two accumulators are fed for every frame:
  * a background stack: the whole frame aligned with its global shift;
  * one patch stack per alignment point: a window around the AP sampled at the AP's own
    displacement (this is what corrects seeing-induced local distortion).
Patches are finally blended with overlapping sin² windows; where AP coverage fades out
(sky, limb, frame edges) the background stack takes over smoothly.
"""

from __future__ import annotations

import threading

import cv2
import numpy as np

from .alignment import sample_shifted


def patch_window(size: int) -> np.ndarray:
    t = np.sin(np.pi * (np.arange(size) + 0.5) / size) ** 2
    return np.outer(t, t).astype(np.float32)


class _Accum:
    def __init__(self, out_shape: tuple[int, ...], n_points: int, patch: int, channels: int) -> None:
        self.bg = np.zeros(out_shape, dtype=np.float32)
        self.bg_w = 0.0
        shape = (n_points, patch, patch) + ((channels,) if channels > 1 else ())
        self.patches = np.zeros(shape, dtype=np.float32)
        self.patch_w = np.zeros(n_points, dtype=np.float64)


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

    def add_background(self, frame: np.ndarray, d: tuple[float, float], weight: float = 1.0) -> None:
        acc = self._acc()
        x0, y0 = self._src_origin(0, 0, d[0], d[1])
        img = sample_shifted(frame, x0, y0, self.out_w, self.out_h, self.scale)
        if weight != 1.0:
            img *= weight
        acc.bg += img
        acc.bg_w += weight

    def add_patches(self, frame: np.ndarray, shifts: np.ndarray, use: np.ndarray,
                    weights: np.ndarray | None = None) -> None:
        acc = self._acc()
        size = self.patch_out
        for i in np.flatnonzero(use):
            ox, oy = self.origins[i]
            x0, y0 = self._src_origin(ox, oy, shifts[i, 0], shifts[i, 1])
            p = sample_shifted(frame, x0, y0, size, size, self.scale)
            w = 1.0 if weights is None else float(weights[i])
            if w != 1.0:
                p *= w
            acc.patches[i] += p
            acc.patch_w[i] += w

    def result(self) -> np.ndarray:
        if not self._accums:
            raise RuntimeError("Aucune image n'a été empilée")
        bg = np.zeros(self.out_shape, dtype=np.float64)
        bg_w = 0.0
        patches = np.zeros(self._accums[0].patches.shape, dtype=np.float64)
        patch_w = np.zeros(len(self.points), dtype=np.float64)
        for a in self._accums:
            bg += a.bg
            bg_w += a.bg_w
            patches += a.patches
            patch_w += a.patch_w
        background = (bg / max(bg_w, 1e-12)).astype(np.float32)
        if not len(self.points) or not np.any(patch_w > 0):
            return np.clip(background, 0.0, None)

        win = patch_window(self.patch_out)
        if self.c > 1:
            win = win[..., None]
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
            p = patches[i][sl] / patch_w[i]
            num[y0:y1, x0:x1] += win[sl] * p
            den[y0:y1, x0:x1] += win[sl]
        bg_weight = np.clip(1.0 - den, 0.0, None)
        out = (num + bg_weight * background) / (den + bg_weight)
        return np.clip(out, 0.0, None).astype(np.float32)
