"""Synthetic planetary videos for tests and demos: a banded planet seen through turbulence."""

from __future__ import annotations

import cv2
import numpy as np


def make_planet(size: int = 256, radius: float | None = None, color: bool = False,
                seed: int = 1) -> np.ndarray:
    """A Jupiter-like disc: limb darkening, belts, ovals and fine turbulent detail."""
    rng = np.random.default_rng(seed)
    radius = radius or size * 0.32
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    cx = cy = (size - 1) / 2.0
    r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) / radius
    disc = np.clip(1.0 - r, 0.0, 1.0)
    limb = np.where(r < 1.0, np.sqrt(np.clip(1.0 - r * r, 0.0, 1.0)) ** 0.4, 0.0)
    lat = (y - cy) / radius
    bands = 0.75 + 0.12 * np.sin(lat * 9.0) + 0.08 * np.sin(lat * 23.0 + 1.0)
    detail = cv2.GaussianBlur(rng.normal(0, 1, (size, size)).astype(np.float32), (0, 0), 1.2)
    detail = cv2.GaussianBlur(detail, (0, 0), 0.6) * 0.25
    img = bands + detail * 0.35
    for _ in range(4):  # ovals
        ox, oy = rng.uniform(-0.5, 0.5, 2) * radius + (cx, cy)
        sx, sy = rng.uniform(3, 9), rng.uniform(2, 5)
        img += rng.choice([-0.25, 0.25]) * np.exp(-(((x - ox) / sx) ** 2 + ((y - oy) / sy) ** 2))
    img = np.clip(img * limb, 0, 1) * (disc > 0)
    img = cv2.GaussianBlur(img.astype(np.float32), (0, 0), 0.5)
    if color:
        tint = np.array([1.0, 0.88, 0.72], dtype=np.float32)
        hue = 0.06 * np.sin(lat * 9.0)[..., None]
        img = np.clip(img[..., None] * (tint + hue * np.array([1, 0, -1], dtype=np.float32)), 0, 1)
    return img.astype(np.float32)


def make_sequence(truth: np.ndarray, n: int = 60, seed: int = 0, max_shift: float = 12.0,
                  distortion: float = 1.5, blur: tuple[float, float] = (0.4, 2.5),
                  noise: float = 0.015):
    """Return (frames float32, global_shifts (n,2), blur_sigmas (n,)).

    Each frame = truth displaced by a global shift plus a smooth random distortion field,
    blurred by a random seeing sigma and with Gaussian noise added."""
    rng = np.random.default_rng(seed)
    h, w = truth.shape[:2]
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    frames, shifts, sigmas = [], [], []
    for _ in range(n):
        d = rng.uniform(-max_shift, max_shift, 2)
        field = rng.normal(0, distortion, (2, 4, 4)).astype(np.float32)
        fx = cv2.resize(field[0], (w, h), interpolation=cv2.INTER_CUBIC)
        fy = cv2.resize(field[1], (w, h), interpolation=cv2.INTER_CUBIC)
        # frame(x) = truth(x - d - field)
        map_x = (x - np.float32(d[0]) - fx).astype(np.float32)
        map_y = (y - np.float32(d[1]) - fy).astype(np.float32)
        img = cv2.remap(truth, map_x, map_y, cv2.INTER_CUBIC,
                        borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        sigma = rng.uniform(*blur)
        img = cv2.GaussianBlur(img, (0, 0), sigma)
        img = img + rng.normal(0, noise, img.shape).astype(np.float32)
        frames.append(np.clip(img, 0, 1).astype(np.float32))
        shifts.append(d)
        sigmas.append(sigma)
    return frames, np.array(shifts), np.array(sigmas)


def write_demo_ser(path: str, n: int = 200, size: int = 320, color: bool = False,
                   seed: int = 3) -> None:
    from .io.ser import COLOR_MONO, COLOR_RGB, write_ser
    truth = make_planet(size, color=color, seed=seed)
    frames, _, _ = make_sequence(truth, n=n, seed=seed)
    data = [(np.clip(f, 0, 1) * 255 + 0.5).astype(np.uint8) for f in frames]
    write_ser(path, data, color_id=COLOR_RGB if color else COLOR_MONO,
              telescope="PlanStax démo")
