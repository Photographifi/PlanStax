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


def make_moon(height: int = 1200, width: int = 1200, seed: int = 5, limb: bool = True) -> np.ndarray:
    """A lunar landscape lit from the side: craters of every size on rolling ground, darker
    maria, and the limb of the disc against the black sky."""
    rng = np.random.default_rng(seed)
    h, w = height, width
    relief = np.zeros((h, w), np.float32)
    for sigma, amp in ((30.0, 40.0), (8.0, 6.0), (2.0, 0.8)):
        relief += cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), sigma) * amp
    for _ in range(int(h * w / 2500)):
        r = float(min(90.0, 3.0 / rng.uniform(0.03, 1.0)))  # many small craters, a few large ones
        cx, cy = rng.uniform(0, w), rng.uniform(0, h)
        x0, x1 = int(max(0, cx - 1.6 * r)), int(min(w, cx + 1.6 * r + 1))
        y0, y1 = int(max(0, cy - 1.6 * r)), int(min(h, cy + 1.6 * r + 1))
        if x1 <= x0 or y1 <= y0:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / r
        bowl = np.where(d < 1.0, (d * d - 1.0) * 0.35 * r, 0.0)
        rim = np.exp(-((d - 1.0) / 0.18) ** 2) * 0.12 * r
        relief[y0:y1, x0:x1] += (bowl + rim).astype(np.float32)
    gy, gx = np.gradient(relief)
    shade = 0.55 + 0.4 * np.tanh(0.6 * (0.8 * gx + 0.45 * gy))
    maria = cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), min(h, w) / 8)
    albedo = 0.8 - 0.25 * (maria > np.percentile(maria, 70))
    albedo = cv2.GaussianBlur(albedo.astype(np.float32), (0, 0), 6.0)
    img = shade * albedo
    if limb:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        r = np.hypot(xx - w * 0.55, yy - h * 0.5) / (0.62 * max(h, w))
        img *= np.clip((1.0 - r) * 60.0, 0.0, 1.0)
    return np.clip(img, 0.0, 1.0).astype(np.float32)


def cut_tiles(scene: np.ndarray, size: int, step: int, seed: int = 0, rotation: float = 2.0,
              gain: float = 0.12, noise: float = 0.005, colour: float = 0.0, vignetting: float = 0.0):
    """Overlapping fields of `scene` on a grid, as a mosaic session would record them: each
    with a random shift, field rotation (degrees), brightness, colour cast (per-channel
    spread, colour scenes), vignetting (darkening of the corners) and noise. Returns the tiles
    and, for each, the 2×3 matrix tile pixel → scene pixel."""
    rng = np.random.default_rng(seed)
    h, w = scene.shape[:2]
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    r2 = ((xx - (size - 1) / 2) ** 2 + (yy - (size - 1) / 2) ** 2) / (2 * ((size - 1) / 2) ** 2)
    shade = (1.0 - vignetting * r2)[..., None] if scene.ndim == 3 else 1.0 - vignetting * r2
    tiles, truths = [], []
    for y in range(0, h - size + 1, step):
        for x in range(0, w - size + 1, step):
            angle = np.radians(rng.uniform(-rotation, rotation))
            cx = x + size / 2 + rng.uniform(-0.04, 0.04) * size
            cy = y + size / 2 + rng.uniform(-0.04, 0.04) * size
            c, s = np.cos(angle), np.sin(angle)
            half = (size - 1) / 2.0
            m = np.array([[c, -s, cx - (c * half - s * half)],
                          [s, c, cy - (s * half + c * half)]])  # tile pixel → scene pixel
            tile = cv2.warpAffine(scene, m, (size, size), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                                  borderMode=cv2.BORDER_REFLECT)
            tile = tile * rng.uniform(1.0 - gain, 1.0 + gain) * shade
            if scene.ndim == 3 and colour:
                tile = tile * rng.uniform(1.0 - colour, 1.0 + colour, 3).astype(np.float32)
            tile = tile + rng.normal(0, noise, tile.shape).astype(np.float32)
            tiles.append(np.clip(tile, 0.0, 1.0).astype(np.float32))
            truths.append(m)
    return tiles, truths


def write_demo_ser(path: str, n: int = 200, size: int = 320, color: bool = False,
                   seed: int = 3) -> None:
    from .io.ser import COLOR_MONO, COLOR_RGB, write_ser
    truth = make_planet(size, color=color, seed=seed)
    frames, _, _ = make_sequence(truth, n=n, seed=seed)
    data = [(np.clip(f, 0, 1) * 255 + 0.5).astype(np.uint8) for f in frames]
    write_ser(path, data, color_id=COLOR_RGB if color else COLOR_MONO,
              telescope="PlanStax démo")
