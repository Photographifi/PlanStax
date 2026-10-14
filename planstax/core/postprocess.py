"""Final adjustments: RGB channel alignment, colour balance, levels, gamma, orientation."""

from __future__ import annotations

import cv2
import numpy as np

from ..settings import PostSettings
from .alignment import sample_shifted
from .quality import object_threshold, smooth


def estimate_rgb_shifts(img: np.ndarray) -> tuple[tuple[float, float], tuple[float, float]]:
    """Displacement of the red and blue channels relative to green (atmospheric dispersion)."""
    if img.ndim != 3:
        return (0.0, 0.0), (0.0, 0.0)
    h, w = img.shape[:2]
    win = cv2.createHanningWindow((w, h), cv2.CV_32F)

    def prep(ch: np.ndarray) -> np.ndarray:
        return (ch - float(ch.mean())) * win

    channels = [smooth(np.ascontiguousarray(img[..., c]).astype(np.float32), 0.7) for c in range(3)]
    g = prep(channels[1])

    def measure(ch: np.ndarray) -> tuple[float, float]:
        # Phase correlation gives a robust starting point but its sub-pixel estimate is biased
        # (up to ~0.3 px); ECC refines it and is insensitive to the channels' gain/offset.
        (sx, sy), _ = cv2.phaseCorrelate(g, prep(ch))
        warp = np.array([[1, 0, sx], [0, 1, sy]], dtype=np.float32)
        crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-6)
        try:
            _, warp = cv2.findTransformECC(channels[1], ch, warp, cv2.MOTION_TRANSLATION, crit, None, 3)
        except cv2.error:
            pass  # did not converge: keep the phase-correlation estimate
        return float(warp[0, 2]), float(warp[1, 2])

    return measure(channels[0]), measure(channels[2])


def auto_balance(img: np.ndarray) -> tuple[float, float, float]:
    """Channel gains that make the object neutral on average (grey-world on the object)."""
    if img.ndim != 3:
        return 1.0, 1.0, 1.0
    lum = cv2.cvtColor(img.astype(np.float32), cv2.COLOR_RGB2GRAY)
    mask = smooth(lum, 2.0) > object_threshold(smooth(lum, 2.0))
    if mask.sum() < 16:
        mask = np.ones_like(lum, dtype=bool)
    means = [float(img[..., c][mask].mean()) for c in range(3)]
    ref = means[1]
    return tuple(float(np.clip(ref / max(m, 1e-6), 0.2, 5.0)) for m in means)


def apply_pre(img: np.ndarray, p: PostSettings) -> np.ndarray:
    """Steps applied before wavelets: channel alignment."""
    if img.ndim != 3 or (p.shift_r == (0.0, 0.0) and p.shift_b == (0.0, 0.0)):
        return img
    h, w = img.shape[:2]
    out = img.copy()
    for c, (dx, dy) in ((0, p.shift_r), (2, p.shift_b)):
        if dx or dy:
            out[..., c] = sample_shifted(np.ascontiguousarray(img[..., c]), dx, dy, w, h)
    return out


def apply_post(img: np.ndarray, p: PostSettings) -> np.ndarray:
    """Steps applied after wavelets: balance, levels, gamma, brightness/contrast, saturation,
    orientation."""
    if p.is_neutral():
        return img
    out = img.astype(np.float32, copy=True)
    if out.ndim == 3 and (p.gain_r, p.gain_g, p.gain_b) != (1.0, 1.0, 1.0):
        out *= np.array([p.gain_r, p.gain_g, p.gain_b], dtype=np.float32)
    if p.black != 0.0 or p.white != 1.0:
        out = (out - p.black) / max(p.white - p.black, 1e-6)
    out = np.clip(out, 0.0, 1.0)
    if p.gamma != 1.0:
        out = np.power(out, 1.0 / max(p.gamma, 1e-3))
    if p.contrast != 1.0 or p.brightness != 0.0:
        out = (out - 0.5) * p.contrast + 0.5 + p.brightness
    if out.ndim == 3 and p.saturation != 1.0:
        grey = cv2.cvtColor(np.clip(out, 0, 1).astype(np.float32), cv2.COLOR_RGB2GRAY)[..., None]
        out = grey + (out - grey) * p.saturation
    out = np.clip(out, 0.0, 1.0)
    return orient(out, p)


def orient(img: np.ndarray, p: PostSettings) -> np.ndarray:
    k = (p.rotate // 90) % 4
    if k:
        img = np.rot90(img, -k)  # clockwise
    if p.flip_h:
        img = img[:, ::-1]
    if p.flip_v:
        img = img[::-1]
    return np.ascontiguousarray(img)
