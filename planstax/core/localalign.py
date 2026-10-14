"""Alignment points (AP) placement and local (per-point) alignment.

Each AP is a small box on the reference image. In every frame, the box is searched
around its globally-aligned position with normalised cross-correlation, refined to
sub-pixel precision; a local sharpness score is measured at the same time so that
the stacker can keep, for each AP, only the frames where that region was sharp.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ..settings import AlignSettings
from .quality import log_energy, smooth

MIN_CORRELATION = 0.25
REMAP_MAX_ROWS = 32767  # cv2.remap asserts map and source sizes are below SHRT_MAX


@dataclass
class PlacementReport:
    """Why grid positions were kept or dropped — shown to the user when points are missing."""

    candidates: int = 0           # grid positions far enough from the frame edges
    too_dark: int = 0
    too_bright: int = 0
    low_detail: int = 0
    over_limit: int = 0           # dropped by the maximum number of points
    placed: int = 0
    frame_too_small: bool = False
    brightness: tuple[float, float, float] | None = None  # min, median, max box brightness (0-255)

    def explain(self, s: AlignSettings) -> str:
        if self.frame_too_small:
            return ("Aucun point : l'image est trop petite pour la taille des boîtes, le rayon de "
                    "recherche et la marge au bord choisis.")
        lines = [f"{self.placed} point(s) d'alignement."]
        dropped = []
        if self.too_bright:
            dropped.append(f"{self.too_bright} zones plus claires que {s.max_brightness}")
        if self.too_dark:
            dropped.append(f"{self.too_dark} zones plus sombres que {s.min_brightness}")
        if self.low_detail:
            dropped.append(f"{self.low_detail} zones sans assez de détail")
        if self.over_limit:
            dropped.append(f"{self.over_limit} au-delà du maximum de {s.max_points}")
        if dropped:
            lines.append("Écartées : " + ", ".join(dropped) + ".")
        if self.brightness:
            lo, med, hi = self.brightness
            lines.append(f"Luminosité des zones : {lo:.0f} à {hi:.0f} sur 255 (médiane {med:.0f}).")
        if self.placed == 0 and self.brightness:
            lo, _, hi = self.brightness
            if self.too_bright >= max(self.too_dark, self.low_detail):
                lines.append(f"→ Montez « Luminosité max. » au-dessus de {hi:.0f}.")
            elif self.too_dark >= self.low_detail:
                lines.append(f"→ Descendez « Luminosité min. » sous {lo:.0f}.")
            else:
                lines.append("→ Baissez « Détail minimal ».")
        return "\n".join(lines)


def place_points(reference: np.ndarray, s: AlignSettings) -> np.ndarray:
    """Return an (N, 2) int array of AP centres (x, y) on a regular grid over the object."""
    return place_points_with_report(reference, s)[0]


def place_points_with_report(reference: np.ndarray, s: AlignSettings) -> tuple[np.ndarray, PlacementReport]:
    """Like place_points, plus a report of why positions were dropped.

    Brightness limits are absolute, on the 0-255 scale of the image (as in RegiStax), and
    apply to the mean brightness of each box."""
    report = PlacementReport()
    none = np.zeros((0, 2), dtype=np.int32)
    h, w = reference.shape
    box = int(s.ap_box_size)
    half = box // 2
    spacing = max(4, int(s.ap_spacing))
    margin = max(int(s.edge_margin), int(s.search_radius)) + half
    if w - 2 * margin <= 0 or h - 2 * margin <= 0:
        report.frame_too_small = True
        return none, report

    g = smooth(reference.astype(np.float32), 1.0)
    integ = cv2.integral(g, sdepth=cv2.CV_64F)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    integ_grad = cv2.integral(np.sqrt(gx * gx + gy * gy), sdepth=cv2.CV_64F)

    def box_mean(ii: np.ndarray, x0: int, y0: int) -> float:
        return float(ii[y0 + box, x0 + box] - ii[y0, x0 + box] - ii[y0 + box, x0] + ii[y0, x0]) / (box * box)

    # Centre the grid on the frame so points are symmetric.
    xs = np.arange(margin, w - margin, spacing)
    ys = np.arange(margin, h - margin, spacing)
    xs = xs + (w - 1 - margin - xs[-1]) // 2
    ys = ys + (h - 1 - margin - ys[-1]) // 2

    lo, hi = s.min_brightness / 255.0, s.max_brightness / 255.0
    cands, scores, levels = [], [], []
    for y in ys:
        for x in xs:
            x0, y0 = int(x) - half, int(y) - half
            if x0 < 0 or y0 < 0 or x0 + box > w or y0 + box > h:
                continue
            b = box_mean(integ, x0, y0)
            levels.append(b)
            if b < lo:
                report.too_dark += 1
                continue
            if b > hi:
                report.too_bright += 1
                continue
            cands.append((int(x), int(y)))
            scores.append(box_mean(integ_grad, x0, y0) / (b + 1e-6))
    report.candidates = len(levels)
    if levels:
        lv = np.asarray(levels) * 255.0
        report.brightness = (float(lv.min()), float(np.median(lv)), float(lv.max()))
    if not cands:
        return none, report
    pts = np.asarray(cands, dtype=np.int32)
    scores = np.asarray(scores)
    keep = scores >= s.min_structure * scores.max()
    report.low_detail = int((~keep).sum())
    pts, scores = pts[keep], scores[keep]
    if len(pts) > s.max_points:
        report.over_limit = len(pts) - int(s.max_points)
        best = np.argsort(scores)[::-1][: int(s.max_points)]
        pts = pts[np.sort(best)]
    report.placed = len(pts)
    return pts, report


def _subpixel(c: np.ndarray, x: int, y: int) -> tuple[float, float]:
    """Parabolic peak refinement around integer maximum (x, y) of correlation map c."""
    def vertex(a: float, b: float, d: float) -> float:
        den = a - 2.0 * b + d
        return 0.0 if abs(den) < 1e-12 else float(np.clip(0.5 * (a - d) / den, -0.5, 0.5))
    dx = vertex(c[y, x - 1], c[y, x], c[y, x + 1])
    dy = vertex(c[y - 1, x], c[y, x], c[y + 1, x])
    return dx, dy


class LocalAligner:
    """Two-stage local matcher.

    1. Integer search: normalised cross-correlation of the reference box over the search area.
    2. Sub-pixel refinement: vectorised Lucas-Kanade on all boxes at once. The 2x2 normal
       equations are lightly regularised towards the global shift, so along a lone edge
       (planet limb), where the image carries no information, the point keeps the global
       displacement instead of sliding along the edge.
    """

    LK_ITERATIONS = 3
    LK_REGULARISATION = 0.005

    def __init__(self, reference: np.ndarray, points: np.ndarray, box: int, radius: int,
                 noise: float = 1.5) -> None:
        self.points = np.asarray(points, dtype=np.int32).reshape(-1, 2)
        self.box = int(box)
        self.half = self.box // 2
        self.radius = max(1, int(radius))
        self.noise = noise
        ref = smooth(reference.astype(np.float32), 1.0)
        gy, gx = np.gradient(ref)
        b, h = self.box, self.half

        def crop(a: np.ndarray, x: int, y: int) -> np.ndarray:
            return np.ascontiguousarray(a[y - h:y - h + b, x - h:x - h + b])

        self.templates = [crop(ref, x, y) for x, y in self.points]
        n = len(self.points)
        if n == 0:
            return
        t = np.stack(self.templates).astype(np.float64)
        tx = np.stack([crop(gx, x, y) for x, y in self.points]).astype(np.float64)
        ty = np.stack([crop(gy, x, y) for x, y in self.points]).astype(np.float64)
        # Gaussian weighting so the box edges, which leave and enter the box, matter less.
        u = np.arange(b) - (b - 1) / 2.0
        g1 = np.exp(-0.5 * (u / (b / 3.0)) ** 2)
        self._win = np.outer(g1, g1)[None]
        self._t = t - t.mean(axis=(1, 2), keepdims=True)
        self._t_std = self._t.std(axis=(1, 2)) + 1e-9
        self._tx, self._ty = tx, ty
        w = self._win
        hxx = (w * tx * tx).sum(axis=(1, 2))
        hyy = (w * ty * ty).sum(axis=(1, 2))
        hxy = (w * tx * ty).sum(axis=(1, 2))
        mu = self.LK_REGULARISATION * (hxx + hyy) + 1e-12
        a, d, c = hxx + mu, hyy + mu, hxy
        det = a * d - c * c
        self._mu = mu
        self._inv = np.stack([d / det, -c / det, -c / det, a / det], axis=1).reshape(n, 2, 2)
        oy, ox = np.mgrid[0:b, 0:b].astype(np.float32)
        self._ox, self._oy = ox - h, oy - h

    def _refine(self, g: np.ndarray, d: np.ndarray, d_global: np.ndarray, idx: np.ndarray) -> np.ndarray:
        """Lucas-Kanade refinement of displacements d[idx] (in place) on smoothed frame g."""
        # All boxes are sampled with one cv2.remap call per batch, stacked vertically; remap
        # rejects maps with 32767 rows or more, so batch the points to stay under that.
        per_batch = max(1, (REMAP_MAX_ROWS - 1) // self.box)
        for start in range(0, len(idx), per_batch):
            self._refine_batch(g, d, d_global, idx[start:start + per_batch])
        return d

    def _refine_batch(self, g: np.ndarray, d: np.ndarray, d_global: np.ndarray, idx: np.ndarray) -> None:
        if not len(idx):
            return
        b = self.box
        pts = self.points[idx].astype(np.float32)
        for _ in range(self.LK_ITERATIONS):
            cx = (pts[:, 0] + d[idx, 0])[:, None, None]
            cy = (pts[:, 1] + d[idx, 1])[:, None, None]
            map_x = (cx + self._ox[None]).reshape(-1, b).astype(np.float32)
            map_y = (cy + self._oy[None]).reshape(-1, b).astype(np.float32)
            warped = cv2.remap(g, map_x, map_y, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
            warped = warped.reshape(-1, b, b).astype(np.float64)
            warped -= warped.mean(axis=(1, 2), keepdims=True)
            scale = self._t_std[idx] / (warped.std(axis=(1, 2)) + 1e-9)
            r = self._t[idx] - warped * scale[:, None, None]
            w = self._win
            bx = (w * self._tx[idx] * r).sum(axis=(1, 2))
            by = (w * self._ty[idx] * r).sum(axis=(1, 2))
            mu = self._mu[idx]
            bx += mu * (d_global[0] - d[idx, 0])
            by += mu * (d_global[1] - d[idx, 1])
            inv = self._inv[idx]
            ex = inv[:, 0, 0] * bx + inv[:, 0, 1] * by
            ey = inv[:, 1, 0] * bx + inv[:, 1, 1] * by
            step = np.stack([ex, ey], axis=1)
            norm = np.linalg.norm(step, axis=1, keepdims=True)
            step = np.where(norm > 1.0, step / np.maximum(norm, 1e-12), step)  # at most 1 px per step
            d[idx] += step.astype(d.dtype)

    def measure(self, lum: np.ndarray, d_global: tuple[float, float]):
        """Return (shifts (N,2) float32 — total displacement of each AP, valid (N,) bool,
        quality (N,) float32)."""
        n = len(self.points)
        shifts = np.zeros((n, 2), dtype=np.float32)
        valid = np.zeros(n, dtype=bool)
        quality = np.zeros(n, dtype=np.float32)
        if n == 0:
            return shifts, valid, quality

        lum = lum.astype(np.float32, copy=False)
        g1 = smooth(lum, 1.0)
        gq = smooth(lum, self.noise)
        integ_e = cv2.integral(log_energy(gq), sdepth=cv2.CV_64F)
        integ_b = cv2.integral(gq, sdepth=cv2.CV_64F)
        h, w = lum.shape
        b, r, half = self.box, self.radius, self.half
        area = float(b * b)
        dgx, dgy = float(d_global[0]), float(d_global[1])

        for i, (px, py) in enumerate(self.points):
            cx, cy = int(round(px + dgx)), int(round(py + dgy))
            x0, y0 = cx - half - r, cy - half - r
            if x0 < 0 or y0 < 0 or x0 + b + 2 * r > w or y0 + b + 2 * r > h:
                shifts[i] = (cx - px, cy - py)
                continue
            region = g1[y0:y0 + b + 2 * r, x0:x0 + b + 2 * r]
            c = cv2.matchTemplate(region, self.templates[i], cv2.TM_CCOEFF_NORMED)
            _, peak, _, (u, v) = cv2.minMaxLoc(c)
            if 0 < u < 2 * r and 0 < v < 2 * r:
                du, dv = _subpixel(c, u, v)
                ok = peak >= MIN_CORRELATION
            else:
                du = dv = 0.0
                ok = False  # peak on the search border: probably a wrong match
            shifts[i] = (cx - r + u + du - px, cy - r + v + dv - py)
            valid[i] = ok and np.isfinite(peak)
            # Local sharpness at the matched position, via integral images.
            qx, qy = x0 + u, y0 + v
            e = integ_e[qy + b, qx + b] - integ_e[qy, qx + b] - integ_e[qy + b, qx] + integ_e[qy, qx]
            m = (integ_b[qy + b, qx + b] - integ_b[qy, qx + b] - integ_b[qy + b, qx] + integ_b[qy, qx]) / area
            quality[i] = (e / area) / (m * m + 1e-12)

        idx = np.flatnonzero(valid)
        dg = np.array([dgx, dgy], dtype=np.float32)
        self._refine(g1, shifts, dg, idx)
        # A refinement that wandered outside the search area did not converge.
        valid &= np.all(np.abs(shifts - dg) <= r + 1.0, axis=1)
        return shifts, valid, quality
