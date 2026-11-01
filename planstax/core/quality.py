"""Frame quality estimation and object detection.

Quality is the energy of the Laplacian-of-Gaussian (fine detail) over the object, divided by
the squared mean brightness so that changes in transparency do not bias frame ranking.
The Gaussian pre-blur (`noise` sigma) keeps sensor noise from passing for detail.

Frames that cannot be ranked that way are left out beforehand (`reject_frames`): nearly black
frames, whose noise the brightness normalisation turns into a soaring score, frames damaged on
their way from the camera (wrong colours), and frames where the planet is cut by the frame edge.
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
    cut: bool = False  # the object reaches the frame edge
    colour: tuple[float, float, float] | None = None  # mean colour of the object, r + g + b = 1


# Why a frame is left out of the stack (see reject_frames).
KEEP, DARK, CUT, COLOUR = 0, 1, 2, 3


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


def analyze_frame(lum: np.ndarray, noise: float = 1.5, rgb: np.ndarray | None = None) -> FrameStats:
    """Statistics of one frame from its luminance; `rgb`, the colour frame, adds its colour."""
    g = smooth(lum, noise)
    thr = object_threshold(g)
    mask = g > thr
    coverage = float(mask.mean())
    if coverage < 1e-4 or coverage > 0.6:
        mask = None  # surface / full-disc views: use the whole frame
    cut = mask is not None and touches_edge(mask)
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
    colour = None
    if rgb is not None and rgb.ndim == 3:
        c = np.array(cv2.mean(rgb, None if mask is None else mask.astype(np.uint8))[:3])
        colour = tuple(float(v) for v in c / max(float(c.sum()), 1e-12))
    return FrameStats(quality=q / (mean * mean + 1e-12), centroid=(cx, cy),
                      brightness=mean, coverage=coverage, cut=cut, colour=colour)


def touches_edge(mask: np.ndarray) -> bool:
    """True when the main object — the largest bright blob, not a moon or a hot pixel — reaches
    the frame edge: a planet cut by the border or drifting out of the field."""
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    if n <= 1:
        return False
    x, y, w, h = stats[1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA])), :4]
    return bool(x == 0 or y == 0 or x + w == mask.shape[1] or y + h == mask.shape[0])


def reject_frames(brightness: np.ndarray, cut: np.ndarray, colour: np.ndarray | None = None,
                  dark: float = 0.3, colour_jump: float = 0.1, window: int = 25) -> np.ndarray:
    """Why each frame is left out of the stack: KEEP for the usable ones, DARK, CUT or COLOUR.

    DARK: much darker than the typical frame (empty field, planet gone out of view); their
    quality, divided by the squared brightness, would soar on noise and rank them first.
    CUT: the planet reaches the frame edge (tracking, wind): part of it is missing and its
    centroid is off. Not applied when most frames are cut: the framing is just tight, and
    these are the frames there are.
    COLOUR (colour videos, `colour` given): the colour of the object departs by more than
    `colour_jump` (summed over r, g, b) from that of the frames around it. A frame shifted by
    one row on its way from the camera has its colour matrix read a row off: green and blue
    swap, and the maze pattern this leaves passes for fine detail. Compared with the `window`
    remaining frames on either side, so that the slow drift of an automatic white balance is
    not taken for it; the frames already left out (a sliver of planet has a colour of its own)
    take no part."""
    reason = np.full(len(brightness), KEEP, dtype=np.int8)
    reason[brightness < dark * np.median(brightness)] = DARK
    cut = np.asarray(cut, dtype=bool) & (reason == KEEP)
    if np.count_nonzero(cut) <= 0.5 * np.count_nonzero(reason == KEEP):
        reason[cut] = CUT
    if colour is not None:
        reason[_colour_jumps(np.asarray(colour, dtype=np.float64), reason == KEEP, colour_jump, window)] = COLOUR
    return reason


def _colour_jumps(colour: np.ndarray, valid: np.ndarray, threshold: float, window: int) -> np.ndarray:
    """Frames (among `valid`) whose colour departs by more than `threshold` from the median
    colour of the valid frames around them."""
    idx = np.flatnonzero(valid)
    jumps = np.zeros(len(colour), dtype=bool)
    if len(idx) < 3:
        return jumps
    h = min(window, len(idx) - 1)
    c = np.pad(colour[idx], ((h, h), (0, 0)), mode="reflect")
    local = np.median(np.lib.stride_tricks.sliding_window_view(c, 2 * h + 1, axis=0), axis=-1)
    jumps[idx] = np.abs(colour[idx] - local).sum(axis=1) > threshold
    return jumps


def detect_surface(lum: np.ndarray) -> bool:
    """True when the object fills the frame (lunar/solar surface) rather than a disc on black sky."""
    g = smooth(lum, 2.0)
    mask = g > object_threshold(g)
    if mask.mean() > 0.5:
        return True
    border = np.concatenate([mask[0], mask[-1], mask[:, 0], mask[:, -1]])
    return bool(border.mean() > 0.25)
