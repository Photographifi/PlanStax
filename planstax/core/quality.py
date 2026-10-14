"""Frame quality estimation and object detection.

Quality is the energy of the Laplacian-of-Gaussian (fine detail) over the object, divided by
the squared mean brightness so that changes in transparency do not bias frame ranking.
The Gaussian pre-blur (`noise` sigma) keeps sensor noise from passing for detail.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class FrameStats:
    quality: float
    centroid: tuple[float, float]
    brightness: float
    coverage: float  # fraction of the frame covered by the object


def smooth(lum: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0:
        return lum
    return cv2.GaussianBlur(lum, (0, 0), sigma, borderType=cv2.BORDER_REFLECT)


def log_energy(blurred: np.ndarray) -> np.ndarray:
    lap = cv2.Laplacian(blurred, cv2.CV_32F, ksize=3, borderType=cv2.BORDER_REFLECT)
    return lap * lap


def object_threshold(blurred: np.ndarray) -> float:
    step = max(1, blurred.shape[0] // 256)
    sample = blurred[::step, ::step]
    lo, hi = np.percentile(sample, (5.0, 99.9))
    return float(lo + 0.2 * (hi - lo))


def analyze_frame(lum: np.ndarray, noise: float = 1.5) -> FrameStats:
    g = smooth(lum, noise)
    thr = object_threshold(g)
    mask = g > thr
    coverage = float(mask.mean())
    if coverage < 1e-4 or coverage > 0.6:
        mask = None  # surface / full-disc views: use the whole frame
    energy = log_energy(g)
    if mask is None:
        mean = float(g.mean())
        q = float(energy.mean())
        weights = g
    else:
        mean = float(g[mask].mean())
        q = float(energy[mask].mean())
        weights = np.where(mask, g - thr, 0.0).astype(np.float32)
    m = cv2.moments(weights)
    if m["m00"] > 0:
        cx, cy = m["m10"] / m["m00"], m["m01"] / m["m00"]
    else:
        cx, cy = (lum.shape[1] - 1) / 2.0, (lum.shape[0] - 1) / 2.0
    return FrameStats(quality=q / (mean * mean + 1e-12), centroid=(cx, cy),
                      brightness=mean, coverage=coverage)


def detect_surface(lum: np.ndarray) -> bool:
    """True when the object fills the frame (lunar/solar surface) rather than a disc on black sky."""
    g = smooth(lum, 2.0)
    mask = g > object_threshold(g)
    if mask.mean() > 0.5:
        return True
    border = np.concatenate([mask[0], mask[-1], mask[:, 0], mask[:, -1]])
    return bool(border.mean() > 0.25)
