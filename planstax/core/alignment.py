"""Global (whole-frame) alignment.

Shift convention used throughout PlanStax: a frame's displacement d means
frame(x) ≈ reference(x - d), i.e. the object sits at reference position + d.
Sampling the frame at x + d puts it back on the reference grid.
"""

from __future__ import annotations

import cv2
import numpy as np

from .quality import object_threshold, smooth


def sample_shifted(img: np.ndarray, x0: float, y0: float, width: int, height: int,
                   scale: float = 1.0, interpolation: int = cv2.INTER_CUBIC) -> np.ndarray:
    """Return the (height x width) window whose top-left output pixel samples img at (x0, y0),
    with an optional zoom (`scale` output pixels per input pixel)."""
    inv = 1.0 / scale
    m = np.array([[inv, 0.0, x0], [0.0, inv, y0]], dtype=np.float64)
    return cv2.warpAffine(img, m, (int(width), int(height)),
                          flags=interpolation | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_REFLECT)


def object_bbox(lum: np.ndarray) -> tuple[int, int, int, int]:
    """Bounding box (x, y, w, h) of the bright object in a frame."""
    g = smooth(lum, 2.0)
    mask = (g > object_threshold(g)).astype(np.uint8)
    pts = cv2.findNonZero(mask)
    if pts is None:
        return 0, 0, lum.shape[1], lum.shape[0]
    return cv2.boundingRect(pts)


def coarse_factor(width: int, height: int) -> int:
    """Downsampling factor that brings a frame to about 512 px for coarse alignment."""
    return max(1, int(np.ceil(max(width, height) / 512)))


def _tukey(n: int, alpha: float) -> np.ndarray:
    """1-D Tukey window: flat in the middle, cosine taper over alpha/2 of each end."""
    x = np.linspace(0.0, 1.0, n)
    w = np.ones(n)
    a = alpha / 2.0
    lo, hi = x < a, x > 1.0 - a
    w[lo] = 0.5 * (1.0 + np.cos(np.pi * (x[lo] / a - 1.0)))
    w[hi] = 0.5 * (1.0 + np.cos(np.pi * ((x[hi] - 1.0) / a + 1.0)))
    return w.astype(np.float32)


class StabilityMap:
    """Accumulates already-aligned frames and tells, per region, whether the scene stays put
    (land, buildings, lunar relief: close to 1) or changes from frame to frame (water,
    swaying foliage: close to 0). Computed at coarse scale, from the reference frames."""

    def __init__(self, width: int, height: int) -> None:
        self.f = coarse_factor(width, height)
        self.n = 0
        self.mean: np.ndarray | None = None
        self.m2: np.ndarray | None = None

    def add(self, aligned: np.ndarray) -> None:
        c = _downsample(smooth(aligned.astype(np.float32), 1.0), self.f).astype(np.float64)
        self.n += 1
        if self.mean is None:
            self.mean, self.m2 = c.copy(), np.zeros_like(c)
            return
        delta = c - self.mean
        self.mean += delta / self.n
        self.m2 += delta * (c - self.mean)

    def result(self) -> np.ndarray | None:
        if self.n < 3:
            return None
        temporal_var = self.m2 / (self.n - 1)
        mean = self.mean.astype(np.float32)
        local_mean = cv2.blur(mean, (5, 5))
        texture_var = np.clip(cv2.blur(mean * mean, (5, 5)) - local_mean ** 2, 0.0, None)
        # Detail that survives averaging, compared with how much each frame departs from it.
        stab = texture_var / (texture_var + temporal_var.astype(np.float32) + 1e-12)
        return cv2.GaussianBlur(stab.astype(np.float32), (0, 0), 2.0)


def _downsample(img: np.ndarray, factor: int) -> np.ndarray:
    if factor <= 1:
        return img
    h, w = img.shape[:2]
    return cv2.resize(img, (max(1, w // factor), max(1, h // factor)), interpolation=cv2.INTER_AREA)


def _pad_size(n: int, limit: int) -> int:
    return min(cv2.getOptimalDFTSize(n), limit)


class GlobalAligner:
    """Measures the whole-frame displacement of each frame relative to a reference.

    Disc on black sky: centroid, then phase correlation on a region around the disc, then ECC
    sub-pixel refinement (OpenCV's phase-correlation sub-pixel peak is biased by up to ~0.3 px).
    Surface: phase correlation on the whole downsampled frame, then ECC on the whole, slightly
    blurred frame, kept only if it agrees with the coarse estimate. An optional `stability` map
    (see StabilityMap) restricts both to what stays put from frame to frame — land rather than
    water in a terrestrial view."""

    ECC_MAX = 512
    _ECC_CRITERIA = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 1e-4)
    _SURFACE_ECC_CRITERIA = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 40, 1e-4)

    def __init__(self, reference: np.ndarray, surface: bool, ref_centroid: tuple[float, float],
                 search: int = 32, max_roi: int = 1024, stability: np.ndarray | None = None) -> None:
        self.surface = surface
        self.search = search
        self.ref_centroid = np.asarray(ref_centroid, dtype=np.float64)
        h, w = reference.shape
        ref = smooth(reference.astype(np.float32), 1.0)
        if surface:
            self._init_surface(ref, stability)
            return

        bx, by, bw, bh = object_bbox(reference)
        margin = search + 16
        rw = _pad_size(bw + 2 * margin, w)
        rh = _pad_size(bh + 2 * margin, h)
        rx = int(round(bx + bw / 2 - rw / 2))
        ry = int(round(by + bh / 2 - rh / 2))
        self.roi = (rx, ry, int(rw), int(rh))
        self.window = cv2.createHanningWindow((int(rw), int(rh)), cv2.CV_32F)
        raw = sample_shifted(ref, rx, ry, rw, rh, interpolation=cv2.INTER_LINEAR)
        self.ref_roi = self._prep(raw)
        # Central crop used for the ECC sub-pixel refinement (bounded for speed).
        ew, eh = min(int(rw), self.ECC_MAX), min(int(rh), self.ECC_MAX)
        self._ecc_box = ((int(rw) - ew) // 2, (int(rh) - eh) // 2, ew, eh)
        ex, ey = self._ecc_box[:2]
        self._ecc_ref = np.ascontiguousarray(raw[ey:ey + eh, ex:ex + ew])

    # ------------------------------------------------------------------ surface (Moon, Sun, landscapes)
    # The whole frame is used, never a central crop: the middle of a terrestrial or lunar view may
    # hold nothing fixed (moving water, a uniform mare). Full-resolution phase correlation is
    # avoided too: video codecs leave a block pattern fixed to the frame that pulls it to zero.
    # The window is flat except near the frame edges (Tukey), so that a shoreline or hillside
    # along the top of the frame still counts.
    def _init_surface(self, ref: np.ndarray, stability: np.ndarray | None) -> None:
        h, w = ref.shape
        f = self.coarse_factor = coarse_factor(w, h)
        small = _downsample(ref, f)
        sh, sw = small.shape
        window = np.outer(_tukey(sh, 0.15), _tukey(sw, 0.15))
        self.ecc_factor = max(1, int(np.ceil(max(w, h) / 1024)))
        self.ecc_ref = self._ecc_prep(ref)
        self.ecc_mask = None
        if stability is not None:
            window = window * cv2.resize(stability, (sw, sh), interpolation=cv2.INTER_AREA)
            mask = cv2.resize(stability, self.ecc_ref.shape[::-1], interpolation=cv2.INTER_AREA) > 0.5
            if mask.mean() > 0.05:
                self.ecc_mask = mask.astype(np.uint8)
        self.coarse_window = window.astype(np.float32)
        self.coarse_ref = self._prep(small, self.coarse_window)

    def _ecc_prep(self, img: np.ndarray) -> np.ndarray:
        e = self.ecc_factor
        return _downsample(cv2.GaussianBlur(img, (0, 0), 0.6 * e if e > 1 else 0.8), e)

    def _measure_surface(self, g: np.ndarray) -> tuple[float, float, float]:
        f, e = self.coarse_factor, self.ecc_factor
        (cx, cy), response = cv2.phaseCorrelate(self.coarse_ref, self._prep(_downsample(g, f), self.coarse_window))
        d = np.array([cx * f, cy * f])
        warp = np.array([[1, 0, d[0] / e], [0, 1, d[1] / e]], dtype=np.float32)
        try:
            _, warp = cv2.findTransformECC(self.ecc_ref, self._ecc_prep(g), warp, cv2.MOTION_TRANSLATION,
                                           self._SURFACE_ECC_CRITERIA, self.ecc_mask, 1)
            refined = np.array([warp[0, 2] * e, warp[1, 2] * e])
            # The refinement must agree with the coarse estimate (within ~one coarse pixel).
            if np.all(np.isfinite(refined)) and np.all(np.abs(refined - d) <= 1.5 * max(f, 2)):
                d = refined
        except cv2.error:
            pass  # did not converge (cloud, blank frame): keep the coarse estimate
        return float(d[0]), float(d[1]), float(response)

    # ------------------------------------------------------------------
    def _prep(self, roi: np.ndarray, window: np.ndarray | None = None) -> np.ndarray:
        roi = roi - float(roi.mean())
        return roi * (self.window if window is None else window)

    def measure(self, lum: np.ndarray, centroid: tuple[float, float] | None) -> tuple[float, float, float]:
        """Return (dx, dy, response) for one frame (luminance, float32)."""
        g = smooth(lum.astype(np.float32, copy=False), 1.0)
        if self.surface:
            return self._measure_surface(g)
        d = np.asarray(centroid, dtype=np.float64) - self.ref_centroid

        rx, ry, rw, rh = self.roi
        roi = sample_shifted(g, rx + d[0], ry + d[1], rw, rh, interpolation=cv2.INTER_LINEAR)
        (sx, sy), response = cv2.phaseCorrelate(self.ref_roi, self._prep(roi))
        if not (abs(sx) <= self.search and abs(sy) <= self.search):
            sx = sy = 0.0  # implausible correction of the centroid estimate: ignore it

        ex, ey, ew, eh = self._ecc_box
        crop = sample_shifted(g, rx + d[0] + ex, ry + d[1] + ey, ew, eh, interpolation=cv2.INTER_LINEAR)
        warp = np.array([[1, 0, sx], [0, 1, sy]], dtype=np.float32)
        try:
            _, warp = cv2.findTransformECC(self._ecc_ref, crop, warp, cv2.MOTION_TRANSLATION,
                                           self._ECC_CRITERIA, None, 1)
            if abs(warp[0, 2] - sx) < 2.0 and abs(warp[1, 2] - sy) < 2.0:
                sx, sy = float(warp[0, 2]), float(warp[1, 2])
        except cv2.error:
            pass  # ECC did not converge (cloud, blank frame): keep the phase-correlation result
        return float(d[0] + sx), float(d[1] + sy), float(response)
