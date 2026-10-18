"""Mosaics: stacked images of overlapping fields (Moon, Sun, distant landscapes) → one image.

At telescope focal lengths each field spans a fraction of a degree, so two neighbouring
images differ only by a shift, a small rotation (field rotation of alt-azimuth mounts) and
possibly a scale: a similarity, without the perspective corrections of wide-angle panoramas.

1. Overlaps: SIFT features of reduced copies are matched between every pair of images and
   checked with RANSAC; the pairs found are refined on larger copies.
2. Placement: the similarities of all the images are solved together by least squares over
   the matched points, so errors do not pile up along a chain; a pair that disagrees with
   the others is dropped. Images that overlap nothing are left aside, and disjoint sets of
   images become separate mosaics.
3. Brightness: a gain per image and channel equalises the overlaps (sky transparency and
   the height of the Moon change during a session).
4. Blending in two bands: brightness (low frequencies) is feathered across the whole
   overlap while fine detail switches over over a narrow seam, which hides the seams
   without blurring. The mosaic is rendered in horizontal bands, so its size is not
   limited by memory.
"""

from __future__ import annotations

import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import cv2
import numpy as np
import tifffile

from ..io.images import output_bits, quantize, read_raw, to_float, write_samples
from ..io.fits import write_fits
from .pipeline import Cancelled, Progress

COARSE_SIZE = 1000        # longest side of the copies matched pair by pair
FINE_SIZE = 2000          # longest side of the copies used to refine the pairs found
PHOTO_SIZE = 400          # longest side of the copies used to equalise the brightness
COARSE_FEATURES = 1500
FINE_FEATURES = 8000
RATIO = 0.75              # Lowe's ratio test
MIN_INLIERS = 12
MIN_OVERLAP = 0.02        # of the smaller image
DUPLICATE_OVERLAP = 0.9   # of both images
POINTS_PER_PAIR = 150     # matched points per pair kept for the global solution
MAX_RESIDUAL = 3.0        # px: a pair that disagrees more with the others is dropped
MAX_PIXELS = 1.5e9
MAX_SIDE = 65000          # JPEG and most viewers stop there
IN_MEMORY_PIXELS = 64e6   # larger TIFF mosaics are written tile by tile
TIFF_TILE = 256
BAND_BYTES = 256 * 2 ** 20
PREVIEW_SIZE = 1600


# ---------------------------------------------------------------------------------- geometry
def _apply(m: np.ndarray, pts: np.ndarray) -> np.ndarray:
    return pts @ m[:, :2].T + m[:, 2]


def _compose(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """a ∘ b: apply b, then a (2×3 matrices)."""
    return np.hstack([a[:, :2] @ b[:, :2], (a[:, :2] @ b[:, 2] + a[:, 2])[:, None]])


def _invert(m: np.ndarray) -> np.ndarray:
    return cv2.invertAffineTransform(np.asarray(m, np.float64))


def _scale(m: np.ndarray) -> float:
    return math.hypot(m[0, 0], m[1, 0])


def _outline(rect) -> np.ndarray:
    """Corners of the usable part of an image (pixel edges, pixel centres at integers)."""
    x0, y0, x1, y1 = rect
    return np.array([[x0 - 0.5, y0 - 0.5], [x1 - 0.5, y0 - 0.5],
                     [x1 - 0.5, y1 - 0.5], [x0 - 0.5, y1 - 0.5]], np.float64)


def _area(rect) -> float:
    x0, y0, x1, y1 = rect
    return float(max(0, x1 - x0) * max(0, y1 - y0))


def _overlap(rect_i, rect_j, m_ji: np.ndarray) -> float:
    """Area of image i covered by image j placed in i by m_ji."""
    area, _ = cv2.intersectConvexConvex(_outline(rect_i).astype(np.float32),
                                        _apply(m_ji, _outline(rect_j)).astype(np.float32))
    return float(area)


def _inside(pts: np.ndarray, rect, pad: float = 0.0) -> np.ndarray:
    x0, y0, x1, y1 = rect
    return ((pts[:, 0] >= x0 - pad) & (pts[:, 0] <= x1 - 1 + pad)
            & (pts[:, 1] >= y0 - pad) & (pts[:, 1] <= y1 - 1 + pad))


def _resize_matrix(sx: float, sy: float) -> np.ndarray:
    """Full-size pixel → pixel of a copy resized by (sx, sy) (OpenCV's pixel-centre convention)."""
    return np.array([[sx, 0.0, 0.5 * sx - 0.5], [0.0, sy, 0.5 * sy - 0.5]])


# ---------------------------------------------------------------------------------- images
def _read(path: str) -> np.ndarray:
    """Samples as stored when 8/16-bit integers (half or a quarter of the memory of float32),
    float32 in [0, 1] otherwise."""
    data = read_raw(path)
    return data if data.dtype in (np.uint8, np.uint16) else to_float(data)


def _as_float(data: np.ndarray) -> np.ndarray:
    if data.dtype == np.uint8:
        return data.astype(np.float32) * np.float32(1.0 / 255.0)
    if data.dtype == np.uint16:
        return data.astype(np.float32) * np.float32(1.0 / 65535.0)
    return data.astype(np.float32, copy=False)


def _luminance(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if img.ndim == 3 else img


def _usable_rect(lum: np.ndarray) -> tuple[int, int, int, int]:
    """Part of a stacked image worth using: without the black bands other programs leave
    after alignment, and without a margin along the edges, where the stack holds fewer
    frames (PlanStax mirrors the image there) and wavelets ring."""
    h, w = lum.shape
    rows = np.flatnonzero(lum.max(axis=1) > 0.002)
    cols = np.flatnonzero(lum.max(axis=0) > 0.002)
    if not len(rows) or not len(cols):
        return 0, 0, 0, 0
    m = max(4, int(round(0.02 * min(h, w))))
    x0, x1 = int(cols[0]) + m, int(cols[-1]) + 1 - m
    y0, y1 = int(rows[0]) + m, int(rows[-1]) + 1 - m
    if x1 - x0 < 16 or y1 - y0 < 16:
        return 0, 0, 0, 0
    return x0, y0, x1, y1


@dataclass
class _Features:
    pts: np.ndarray      # (n, 2) float32, full-size pixels
    desc: np.ndarray     # (n, 128) float32

    @staticmethod
    def empty() -> "_Features":
        return _Features(np.zeros((0, 2), np.float32), np.zeros((0, 128), np.float32))


def _stretch8(lum: np.ndarray) -> np.ndarray | None:
    sample = lum[::4, ::4] if lum.size > 4e6 else lum
    lo, hi = np.percentile(sample, (0.5, 99.5))
    if hi - lo < 1e-4:
        return None
    return np.clip((lum - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)


def _features(lum: np.ndarray, rect, size: int, count: int) -> _Features:
    h, w = lum.shape
    s = min(1.0, size / max(h, w))
    small = lum if s >= 1.0 else cv2.resize(lum, (max(1, round(w * s)), max(1, round(h * s))),
                                            interpolation=cv2.INTER_AREA)
    sy, sx = small.shape[0] / h, small.shape[1] / w
    u8 = _stretch8(small)
    if u8 is None:
        return _Features.empty()
    x0, y0, x1, y1 = rect
    mask = np.zeros(u8.shape, np.uint8)
    mask[math.ceil(y0 * sy):int(y1 * sy), math.ceil(x0 * sx):int(x1 * sx)] = 255
    kps, desc = cv2.SIFT_create(nfeatures=count, contrastThreshold=0.02).detectAndCompute(u8, mask)
    if desc is None or not kps:
        return _Features.empty()
    pts = np.array([k.pt for k in kps], np.float32)
    pts[:, 0] = (pts[:, 0] + 0.5) / sx - 0.5
    pts[:, 1] = (pts[:, 1] + 0.5) / sy - 0.5
    return _Features(pts, desc.astype(np.float32, copy=False))


@dataclass
class _Tile:
    path: str
    width: int
    height: int
    channels: int
    rect: tuple[int, int, int, int]
    coarse: _Features
    fine: _Features
    small: np.ndarray          # (h, w, channels) float32, for the brightness equalisation
    small_matrix: np.ndarray   # full-size pixel → small copy pixel


def _analyse(path: str) -> _Tile:
    img = _as_float(_read(path))
    lum = _luminance(img)
    h, w = lum.shape
    rect = _usable_rect(lum)
    coarse = _features(lum, rect, COARSE_SIZE, COARSE_FEATURES)
    fine = _features(lum, rect, FINE_SIZE, FINE_FEATURES)
    s = min(1.0, PHOTO_SIZE / max(h, w))
    sw, sh = max(1, round(w * s)), max(1, round(h * s))
    small = cv2.resize(img, (sw, sh), interpolation=cv2.INTER_AREA)
    if small.ndim == 2:
        small = small[..., None]
    return _Tile(path, w, h, 1 if img.ndim == 2 else img.shape[2], rect, coarse, fine,
                 small, _resize_matrix(sw / w, sh / h))


# ---------------------------------------------------------------------------------- pairs
@dataclass
class _Pair:
    i: int
    j: int
    m: np.ndarray           # 2×3, pixel of j → pixel of i
    pts_i: np.ndarray       # matched points (full-size pixels)
    pts_j: np.ndarray
    overlap: float          # area of i covered by j


def _ratio_matches(d1: np.ndarray, d2: np.ndarray, ratio: float) -> tuple[np.ndarray, np.ndarray]:
    if len(d1) < 2 or len(d2) < 2:
        return np.zeros(0, int), np.zeros(0, int)
    q, t = [], []
    for pair in cv2.BFMatcher(cv2.NORM_L2).knnMatch(d1, d2, k=2):
        if len(pair) == 2 and pair[0].distance < ratio * pair[1].distance:
            q.append(pair[0].queryIdx)
            t.append(pair[0].trainIdx)
    return np.array(q, int), np.array(t, int)


def _similarity(src: np.ndarray, dst: np.ndarray, threshold: float):
    if len(src) < MIN_INLIERS:
        return None, None
    m, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
                                         ransacReprojThreshold=threshold, maxIters=5000,
                                         confidence=0.999, refineIters=10)
    if m is None:
        return None, None
    inl = inl.ravel().astype(bool)
    return (m, inl) if inl.sum() >= MIN_INLIERS else (None, None)


def _match_pair(ti: _Tile, tj: _Tile, i: int, j: int) -> _Pair | None:
    """Do images i and j overlap? Coarse match of every pair, then refinement."""
    q, t = _ratio_matches(tj.coarse.desc, ti.coarse.desc, RATIO)
    if len(q) < MIN_INLIERS:
        return None
    pj, pi = tj.coarse.pts[q], ti.coarse.pts[t]
    full = max(ti.width, ti.height, tj.width, tj.height)
    coarse_px = max(1.0, full / COARSE_SIZE)
    m, inl = _similarity(pj, pi, 3.0 * coarse_px)
    if m is None or inl.sum() < 0.15 * len(q) or not 0.75 < _scale(m) < 1.33:
        return None
    overlap = _overlap(ti.rect, tj.rect, m)
    if overlap < MIN_OVERLAP * min(_area(ti.rect), _area(tj.rect)):
        return None
    hull = cv2.contourArea(cv2.convexHull(pi[inl].astype(np.float32)))
    if hull < 0.05 * overlap:
        return None  # the agreeing points crowd in a corner: a coincidence more than an overlap
    pts_i, pts_j = pi[inl], pj[inl]

    # Refinement on the larger copies, among the features of the predicted overlap.
    fi, fj = ti.fine, tj.fine
    fine_px = max(1.0, full / FINE_SIZE)
    sel_j = np.flatnonzero(_inside(_apply(m, fj.pts), ti.rect, 4 * coarse_px))
    sel_i = np.flatnonzero(_inside(_apply(_invert(m), fi.pts), tj.rect, 4 * coarse_px))
    q, t = _ratio_matches(fj.desc[sel_j], fi.desc[sel_i], 0.8)
    if len(q):
        fpj, fpi = fj.pts[sel_j[q]], fi.pts[sel_i[t]]
        near = np.hypot(*(_apply(m, fpj) - fpi).T) < 3.0 * coarse_px
        m2, inl2 = _similarity(fpj[near], fpi[near], 1.0 * fine_px)
        if m2 is not None and inl2.sum() >= len(pts_i) // 2:
            m, pts_i, pts_j = m2, fpi[near][inl2], fpj[near][inl2]
    if len(pts_i) > POINTS_PER_PAIR:
        keep = np.random.default_rng(i * 7919 + j).choice(len(pts_i), POINTS_PER_PAIR, replace=False)
        pts_i, pts_j = pts_i[keep], pts_j[keep]
    return _Pair(i, j, m.astype(np.float64), pts_i.astype(np.float64), pts_j.astype(np.float64),
                 _overlap(ti.rect, tj.rect, m))


# ---------------------------------------------------------------------------------- placement
def _components(nodes, pairs: list[_Pair]) -> list[list[int]]:
    parent = {k: k for k in nodes}

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    for p in pairs:
        parent[find(p.i)] = find(p.j)
    groups: dict[int, list[int]] = {}
    for k in nodes:
        groups.setdefault(find(k), []).append(k)
    return sorted((sorted(g) for g in groups.values()), key=lambda g: g[0])


def _solve(nodes: list[int], pairs: list[_Pair], tiles: dict[int, _Tile]) -> dict[int, np.ndarray]:
    """Similarity (image pixel → mosaic pixel) of every image of a connected set, by linear
    least squares over all the matched points. The best connected image is the reference."""
    weight = dict.fromkeys(nodes, 0)
    for p in pairs:
        weight[p.i] += len(p.pts_i)
        weight[p.j] += len(p.pts_i)
    ref = max(nodes, key=lambda k: (weight[k], -k))
    col = {k: 4 * n for n, k in enumerate(k for k in nodes if k != ref)}
    centre = {k: np.array([(tiles[k].width - 1) / 2.0, (tiles[k].height - 1) / 2.0]) for k in nodes}
    size = 4 * len(col)
    ata, atb = np.zeros((size, size)), np.zeros(size)
    for p in pairs:
        n = len(p.pts_i)
        a, b = np.zeros((2 * n, size)), np.zeros(2 * n)
        for k, pts, sign in ((p.i, p.pts_i, 1.0), (p.j, p.pts_j, -1.0)):
            x, y = (pts - centre[k]).T
            if k == ref:
                b[0::2] -= sign * x
                b[1::2] -= sign * y
                continue
            c = col[k]
            a[0::2, c], a[0::2, c + 1], a[0::2, c + 2] = sign * x, -sign * y, sign
            a[1::2, c], a[1::2, c + 1], a[1::2, c + 3] = sign * y, sign * x, sign
        ata += a.T @ a
        atb += a.T @ b
    sol = np.linalg.lstsq(ata, atb, rcond=None)[0]
    poses = {}
    for k in nodes:
        ca, cb, tx, ty = (1.0, 0.0, 0.0, 0.0) if k == ref else sol[col[k]:col[k] + 4]
        r = np.array([[ca, -cb], [cb, ca]])
        poses[k] = np.hstack([r, (np.array([tx, ty]) - r @ centre[k])[:, None]])
    return poses


def _residual(p: _Pair, poses: dict[int, np.ndarray]) -> float:
    d = _apply(poses[p.i], p.pts_i) - _apply(poses[p.j], p.pts_j)
    return float(np.sqrt(np.mean(np.sum(d * d, axis=1))))


def _gains(nodes: list[int], pairs: list[_Pair], tiles: dict[int, _Tile],
           poses: dict[int, np.ndarray], channels: int) -> dict[int, np.ndarray]:
    """One gain per image and channel so that overlaps match (least squares, pulled
    towards 1 so that the whole mosaic keeps its brightness)."""
    sigma_n, sigma_g = 0.02, 0.1  # relative brightness noise of an overlap, spread of the gains
    index = {k: n for n, k in enumerate(nodes)}
    a = np.zeros((channels, len(nodes), len(nodes)))
    b = np.zeros((channels, len(nodes)))
    for p in pairs:
        ti, tj = tiles[p.i], tiles[p.j]
        rel = _compose(_invert(poses[p.i]), poses[p.j])                 # j → i, full size
        m = _compose(ti.small_matrix, _compose(rel, _invert(tj.small_matrix)))
        hi, wi = ti.small.shape[:2]
        warped = cv2.warpAffine(tj.small, m, (wi, hi), flags=cv2.INTER_LINEAR)
        warped = warped.reshape(hi, wi, -1)
        valid_j = cv2.warpAffine(_rect_mask(tj), m, (wi, hi), flags=cv2.INTER_LINEAR) > 0.99
        both = valid_j & (_rect_mask(ti) > 0)
        for img in (ti.small, warped):
            lum = img.mean(axis=2)
            both &= (lum > 0.03) & (img.max(axis=2) < 0.97)  # neither sky nor saturated
        both = cv2.erode(both.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        n = int(both.sum())
        if n < 30:
            continue
        si = _expand(ti.small[both], channels).mean(axis=0)
        sj = _expand(warped[both], channels).mean(axis=0)
        u, v = index[p.i], index[p.j]
        for c in range(channels):
            mean = 0.5 * (si[c] + sj[c])
            if mean <= 1e-4:
                continue
            w = n / (sigma_n * mean) ** 2
            prior = n / sigma_g ** 2
            a[c, u, u] += w * si[c] ** 2 + prior
            a[c, v, v] += w * sj[c] ** 2 + prior
            a[c, u, v] -= w * si[c] * sj[c]
            a[c, v, u] -= w * si[c] * sj[c]
            b[c, u] += prior
            b[c, v] += prior
    gains = np.ones((len(nodes), channels))
    for c in range(channels):
        diag = np.diag(a[c]) == 0
        a[c][diag, diag] = 1.0  # images without a usable overlap keep a gain of 1
        b[c][diag] = 1.0
        gains[:, c] = np.clip(np.linalg.solve(a[c], b[c]), 0.5, 2.0)
    return {k: gains[index[k]].astype(np.float32) for k in nodes}


def _rect_mask(tile: _Tile) -> np.ndarray:
    h, w = tile.small.shape[:2]
    corners = _apply(tile.small_matrix, _outline(tile.rect))
    (x0, y0), (x1, y1) = corners[0], corners[2]
    mask = np.zeros((h, w), np.float32)
    mask[max(0, math.ceil(y0 + 0.5)):max(0, int(y1 + 0.5)), max(0, math.ceil(x0 + 0.5)):max(0, int(x1 + 0.5))] = 1.0
    return mask


def _expand(values: np.ndarray, channels: int) -> np.ndarray:
    """(n, c) samples → (n, channels): a mono image joins a colour mosaic as grey."""
    return np.repeat(values, channels, axis=1) if values.shape[1] < channels else values


# ---------------------------------------------------------------------------------- results
@dataclass
class MosaicGroup:
    """One mosaic: the images it gathers and where each one goes."""
    paths: list[str]
    indices: list[int]            # positions in MosaicPlan.paths
    matrices: list[np.ndarray]    # 2×3, image pixel → mosaic pixel
    rects: list[tuple[int, int, int, int]]
    gains: list[np.ndarray]
    channels: int
    width: int
    height: int
    rms: float                    # px, disagreement of the matched points once placed

    def outline(self, k: int) -> np.ndarray:
        """Corners of image k in the mosaic (4×2)."""
        return _apply(self.matrices[k], _outline(self.rects[k]))

    @property
    def pixels(self) -> int:
        return self.width * self.height


@dataclass
class MosaicPlan:
    paths: list[str]
    groups: list[MosaicGroup] = field(default_factory=list)
    isolated: list[int] = field(default_factory=list)
    duplicates: list[tuple[int, int]] = field(default_factory=list)   # (left aside, kept)
    excluded: list[tuple[int, str]] = field(default_factory=list)     # (image, reason)
    seconds: float = 0.0

    def state(self, k: int) -> str:
        """Short French description of what became of image k."""
        for n, g in enumerate(self.groups):
            if k in g.indices:
                return f"Mosaïque {n + 1}" if len(self.groups) > 1 else "Placée"
        for dropped, kept in self.duplicates:
            if dropped == k:
                return f"Même champ que {os.path.basename(self.paths[kept])}"
        for i, reason in self.excluded:
            if i == k:
                return reason[:1].upper() + reason[1:]
        if k in self.isolated:
            return "Aucun recouvrement trouvé"
        return ""

    def explain(self) -> str:
        names = lambda ks: ", ".join(os.path.basename(self.paths[k]) for k in ks)  # noqa: E731
        lines = []
        if len(self.paths) < 2:
            return "Il faut au moins deux images pour une mosaïque."
        if not self.groups:
            lines.append("Aucune mosaïque : aucune image ne recouvre une autre.")
        for n, g in enumerate(self.groups):
            title = f"Mosaïque {n + 1}" if len(self.groups) > 1 else "Mosaïque"
            spread = max(abs(float(x) - 1.0) for gain in g.gains for x in gain) * 100
            lines.append(f"{title} : {len(g.paths)} images, {g.width} × {g.height} px, "
                         f"écart moyen aux raccords {_fr(g.rms, 2)} px, "
                         f"luminosité corrigée de {_fr(spread, 0)} % au plus.")
        if self.isolated:
            lines.append(f"Laissées de côté, sans recouvrement trouvé : {names(self.isolated)}. "
                         "Il faut environ 25 % de recouvrement entre voisines et assez de détails "
                         "(un ciel uni ou une mer lisse ne suffisent pas).")
        if self.duplicates:
            lines.append("Laissées de côté car elles montrent le même champ qu'une autre : "
                         + ", ".join(f"{os.path.basename(self.paths[d])} "
                                     f"(comme {os.path.basename(self.paths[k])})"
                                     for d, k in self.duplicates) + ".")
        for k, reason in self.excluded:
            lines.append(f"{os.path.basename(self.paths[k])} : {reason}.")
        return "\n".join(lines)


def _fr(value: float, digits: int) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


# ---------------------------------------------------------------------------------- planning
def plan_mosaic(paths: list[str], progress: Progress | None = None,
                cancel: threading.Event | None = None, workers: int | None = None) -> MosaicPlan:
    """Find how the images overlap and where each one goes (nothing is written)."""
    t0 = time.time()
    report = progress or (lambda f, m: None)
    plan = MosaicPlan(list(paths))
    if len(paths) < 2:
        return plan
    workers = workers or max(1, min(4, (os.cpu_count() or 2) // 2))

    def check():
        if cancel is not None and cancel.is_set():
            raise Cancelled()

    tiles: dict[int, _Tile] = {}
    with ThreadPoolExecutor(workers) as pool:
        futures = [pool.submit(_analyse, p) for p in paths]
        for k, fut in enumerate(futures):
            try:
                check()
                tiles[k] = fut.result()
            except Cancelled:
                for f in futures:
                    f.cancel()
                raise
            except MemoryError:
                plan.excluded.append((k, "mémoire insuffisante pour la lire"))
            except Exception as exc:  # noqa: BLE001 - one unreadable image must not stop the rest
                plan.excluded.append((k, f"illisible ({exc})"))
            report(0.6 * (k + 1) / len(paths), f"Recherche des détails : image {k + 1}/{len(paths)}")
    for k in sorted(tiles):
        if _area(tiles[k].rect) == 0:
            plan.excluded.append((k, "image vide"))
            del tiles[k]
    if tiles:
        median = float(np.median([tiles[k].width * tiles[k].height for k in tiles]))
        for k in sorted(tiles):
            if tiles[k].width * tiles[k].height > 4 * median and len(tiles) > 2:
                plan.excluded.append((k, "bien plus grande que les autres (déjà une mosaïque ?)"))
                del tiles[k]
    plan.excluded.sort()

    keys = sorted(tiles)
    candidates = [(i, j) for n, i in enumerate(keys) for j in keys[n + 1:]]
    pairs: list[_Pair] = []
    with ThreadPoolExecutor(workers) as pool:
        for n, result in enumerate(pool.map(lambda ij: _match_pair(tiles[ij[0]], tiles[ij[1]], *ij),
                                            candidates)):
            check()
            if result is not None:
                pairs.append(result)
            if n % 16 == 0 or n == len(candidates) - 1:
                report(0.6 + 0.35 * (n + 1) / len(candidates),
                       f"Recherche des recouvrements : {len(pairs)} trouvés")

    # The same field twice (an image and its copy, the same video processed twice…).
    dropped: dict[int, int] = {}
    for p in pairs:
        if p.i in dropped or p.j in dropped:
            continue
        if (p.overlap >= DUPLICATE_OVERLAP * _area(tiles[p.i].rect)
                and p.overlap >= DUPLICATE_OVERLAP * _area(tiles[p.j].rect)):
            dropped[p.j] = p.i
    plan.duplicates = sorted(dropped.items())
    nodes = [k for k in keys if k not in dropped]
    pairs = [p for p in pairs if p.i not in dropped and p.j not in dropped]

    # Global placement; a pair that disagrees with the others (a repeated pattern matched at
    # the wrong place) is dropped and the placement solved again.
    report(0.96, "Placement des images")
    while True:
        check()
        groups = [g for g in _components(nodes, pairs) if len(g) > 1]
        poses: dict[int, np.ndarray] = {}
        worst: tuple[float, _Pair] | None = None
        for g in groups:
            members = set(g)
            gp = [p for p in pairs if p.i in members]
            poses.update(_solve(g, gp, tiles))
            res = [_residual(p, poses) for p in gp]
            limit = max(MAX_RESIDUAL, 6.0 * float(np.median(res)))
            for r, p in zip(res, gp):
                if r > limit and (worst is None or r > worst[0]):
                    worst = (r, p)
        if worst is None:
            break
        pairs.remove(worst[1])

    placed = set()
    for g in groups:
        members = set(g)
        gp = [p for p in pairs if p.i in members]
        channels = max(tiles[k].channels for k in g)
        gains = _gains(g, gp, tiles, poses, channels)
        corners = np.vstack([_apply(poses[k], _outline(tiles[k].rect)) for k in g])
        x0, y0 = np.ceil(corners.min(axis=0))
        x1, y1 = np.floor(corners.max(axis=0))
        width, height = int(x1 - x0) + 1, int(y1 - y0) + 1
        if width > MAX_SIDE or height > MAX_SIDE or width * height > MAX_PIXELS:
            for k in g:
                plan.excluded.append((k, f"placement incohérent (mosaïque de {width} × {height} px)"))
            continue
        shift = np.array([[0.0, 0.0, -x0], [0.0, 0.0, -y0]])
        n_points = sum(len(p.pts_i) for p in gp)
        rms = math.sqrt(sum(_residual(p, poses) ** 2 * len(p.pts_i) for p in gp) / max(1, n_points))
        plan.groups.append(MosaicGroup(
            paths=[tiles[k].path for k in g], indices=list(g),
            matrices=[poses[k] + shift for k in g], rects=[tiles[k].rect for k in g],
            gains=[gains[k] for k in g], channels=channels, width=width, height=height, rms=rms))
        placed.update(g)
    plan.excluded.sort()
    plan.isolated = [k for k in nodes if k not in placed and all(k != e for e, _ in plan.excluded)]
    plan.seconds = time.time() - t0
    report(1.0, "Placement terminé")
    return plan


# ---------------------------------------------------------------------------------- rendering
def _lowpass(img: np.ndarray, mask: np.ndarray, sigma: float, q: int) -> np.ndarray:
    """Gaussian blur restricted to `mask` (the outside does not darken the edges), computed
    on a copy q times smaller: the result is smooth anyway."""
    h, w = mask.shape
    num, den = img, mask
    if q > 1:
        size = (w // q, h // q)  # the caller makes w and h multiples of q
        num = cv2.resize(img, size, interpolation=cv2.INTER_AREA)
        den = cv2.resize(mask, size, interpolation=cv2.INTER_AREA)
    s = sigma / q
    num = cv2.GaussianBlur(num, (0, 0), s, borderType=cv2.BORDER_CONSTANT).reshape(den.shape + (-1,))
    den = cv2.GaussianBlur(den, (0, 0), s, borderType=cv2.BORDER_CONSTANT)
    low = num / np.maximum(den, 1e-6)[..., None]
    if q > 1:
        low = cv2.resize(low, (w, h), interpolation=cv2.INTER_LINEAR).reshape(h, w, -1)
    return low


def _edge_distance(inverse: np.ndarray, rect, scale: float, x0: int, y0: int,
                   w: int, h: int) -> np.ndarray:
    """Distance (mosaic pixels, 0 outside) from each pixel of the mosaic region (x0, y0, w, h)
    to the edge of the usable part `rect` of an image placed by the inverse of `inverse`."""
    xs = np.arange(x0, x0 + w, dtype=np.float32)
    ys = np.arange(y0, y0 + h, dtype=np.float32)
    rx0, ry0, rx1, ry1 = (float(v) - 0.5 for v in rect)
    dist = None
    for row, lo, hi in ((inverse[0], rx0, rx1), (inverse[1], ry0, ry1)):
        # Image coordinate along this axis = a·x + b·y + c (a plane over the region).
        along_x = (row[0] * xs + row[2]).astype(np.float32)
        along_y = (row[1] * ys).astype(np.float32)
        for sign, edge in ((1.0, lo), (-1.0, hi)):
            d = sign * (along_x - edge)[None, :] + sign * along_y[:, None]
            dist = d if dist is None else np.minimum(dist, d, out=dist)
    dist *= np.float32(scale)
    return np.maximum(dist, 0.0, out=dist)


def _bands(group: MosaicGroup, progress: Progress, cancel: threading.Event | None,
           workers: int | None = None):
    """Yield (top row, float32 band of the mosaic) from top to bottom."""
    W, H, C = group.width, group.height, group.channels
    n = len(group.paths)
    scales = [_scale(m) for m in group.matrices]
    side = float(np.median([min(r[2] - r[0], r[3] - r[1]) * s for r, s in zip(group.rects, scales)]))
    sigma = max(2.0, 0.01 * side)          # brightness band / detail band
    q = max(1, int(sigma // 3))
    margin = int(math.ceil(4.0 * sigma)) + 3 * q  # reach of the blur (OpenCV cuts it at 4 σ)
    seam = np.float32(1.0 / (0.5 * side))  # distance scale of the detail weights
    band = max(TIFF_TILE, (BAND_BYTES // (W * (2 * C + 2) * 4)) // TIFF_TILE * TIFF_TILE)
    inverse = [_invert(m) for m in group.matrices]
    boxes = []
    for k in range(n):
        corners = group.outline(k)
        x0, y0 = np.floor(corners.min(axis=0)).astype(int)
        x1, y1 = np.ceil(corners.max(axis=0)).astype(int) + 1
        boxes.append((max(0, x0), max(0, y0), min(W, x1), min(H, y1)))
    cache: dict[int, np.ndarray] = {}
    lock = threading.Lock()

    def contribute(k, by0, by1, ey0, ey1, acc_low, w_low, acc_high, w_high):
        bx0, bt, bx1, bb = boxes[k]
        # Region of the band (with its margin) covered by image k, aligned on q so that every
        # band reduces the same pixels together (no visible band limits).
        rx0, ry0 = bx0 // q * q, max(ey0, bt // q * q)
        rx1 = rx0 + -(-(bx1 - rx0) // q) * q
        ry1 = ry0 + -(-(min(ey1, bb) - ry0) // q) * q
        rw, rh = rx1 - rx0, ry1 - ry0
        m = group.matrices[k].copy()
        m[:, 2] -= (rx0, ry0)
        img = _as_float(cv2.warpAffine(cache[k], m, (rw, rh), flags=cv2.INTER_CUBIC,
                                       borderMode=cv2.BORDER_CONSTANT)).reshape(rh, rw, -1)
        if img.shape[2] < C:
            img = np.repeat(img, C, axis=2)
        img *= group.gains[k]
        dist = _edge_distance(inverse[k], group.rects[k], scales[k], rx0, ry0, rw, rh)
        mask = (dist > 0).astype(np.float32)
        img *= mask[..., None]
        low = _lowpass(img, mask, sigma, q)
        low *= mask[..., None]
        # Only the rows of the band proper are kept.
        a, b = max(by0, ry0), min(by1, ry1)
        c1 = min(W, rx1)
        if b <= a:
            return
        src, dst, cols = slice(a - ry0, b - ry0), slice(a - by0, b - by0), slice(rx0, c1)
        span = slice(0, c1 - rx0)
        img, low, dist = img[src, span], low[src, span], dist[src, span]
        high = np.subtract(img, low, out=img)
        wh = dist * seam
        wh *= wh
        wh *= wh                     # (distance / seam)⁴: detail switches over a narrow seam
        low *= dist[..., None]
        high *= wh[..., None]
        with lock:
            acc_low[dst, cols] += low
            w_low[dst, cols] += dist
            acc_high[dst, cols] += high
            w_high[dst, cols] += wh

    with ThreadPoolExecutor(workers or max(1, min(4, os.cpu_count() or 1))) as pool:
        for by0 in range(0, H, band):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            by1 = min(H, by0 + band)
            ey0 = max(0, (by0 - margin) // q * q)
            ey1 = by1 + margin
            active = [k for k in range(n)
                      if boxes[k][3] > ey0 and boxes[k][1] < ey1 and boxes[k][2] > boxes[k][0]]
            missing = [k for k in active if k not in cache]
            for k, data in zip(missing, pool.map(lambda k: _read(group.paths[k]), missing)):
                cache[k] = data
            acc_low = np.zeros((by1 - by0, W, C), np.float32)
            acc_high = np.zeros_like(acc_low)
            w_low = np.zeros((by1 - by0, W), np.float32)
            w_high = np.zeros_like(w_low)
            for fut in [pool.submit(contribute, k, by0, by1, ey0, ey1, acc_low, w_low, acc_high, w_high)
                        for k in active]:
                fut.result()
            next_top = (by1 - margin) // q * q
            for k in [k for k in cache if boxes[k][3] <= next_top]:
                del cache[k]  # not needed by the next bands
            # Uncovered pixels have zero sums: they stay black.
            acc_low /= np.maximum(w_low, 1e-12)[..., None]
            acc_high /= np.maximum(w_high, 1e-30)[..., None]
            acc_low += acc_high
            np.clip(acc_low, 0.0, 1.0, out=acc_low)
            del acc_high, w_low, w_high
            progress(by1 / H, f"Assemblage : {by1 * 100 // H} %")
            yield by0, acc_low if C > 1 else acc_low[..., 0]


def render_mosaic(group: MosaicGroup, path: str, bits: int = 16, progress: Progress | None = None,
                  cancel: threading.Event | None = None, preview_size: int = PREVIEW_SIZE) -> np.ndarray:
    """Blend the images of `group` and write the mosaic to `path` (format from its extension).
    Returns a reduced copy for display."""
    report = progress or (lambda f, m: None)
    W, H = group.width, group.height
    bits = output_bits(path, bits)
    sp = min(1.0, preview_size / max(W, H))
    pw = max(1, round(W * sp))
    previews = []

    def keep_preview(bands):
        for y0, band in bands:
            r0, r1 = round(y0 * sp), round((y0 + band.shape[0]) * sp)
            if r1 > r0:
                previews.append(cv2.resize(band, (pw, r1 - r0), interpolation=cv2.INTER_AREA))
            yield y0, band

    bands = keep_preview(_bands(group, report, cancel))
    # Written under a temporary name: a cancelled or failed assembly (disk full…) leaves neither
    # a half-written file nor a damaged previous mosaic.
    root, ext = os.path.splitext(path)
    partial = f"{root}.partiel{ext}"
    try:
        _write_bands(bands, partial, W, H, group.channels, bits)
        os.replace(partial, path)
    except BaseException:
        try:
            os.remove(partial)
        except OSError:
            pass
        raise
    return np.vstack(previews) if previews else np.zeros((1, pw), np.float32)


def _write_bands(bands, path: str, W: int, H: int, channels: int, bits: int) -> None:
    shape = (H, W, channels) if channels > 1 else (H, W)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".tif", ".tiff") and W * H > IN_MEMORY_PIXELS:
        dtype = np.uint8 if bits == 8 else np.uint16

        def tiles():
            for _, band in bands:
                samples = quantize(band, bits)
                for ty in range(0, samples.shape[0], TIFF_TILE):
                    for tx in range(0, W, TIFF_TILE):
                        yield samples[ty:ty + TIFF_TILE, tx:tx + TIFF_TILE]

        size = W * H * channels * np.dtype(dtype).itemsize
        tifffile.imwrite(path, tiles(), shape=shape, dtype=dtype, tile=(TIFF_TILE, TIFF_TILE),
                         photometric="rgb" if channels > 1 else "minisblack",
                         compression="zlib", bigtiff=size > 3 * 2 ** 30)
        return
    out = np.zeros(shape, np.float32 if bits == 32 else (np.uint8 if bits == 8 else np.uint16))
    for y0, band in bands:
        out[y0:y0 + band.shape[0]] = band if bits == 32 else quantize(band, bits)
    if bits == 32:
        write_fits(path, out)
    else:
        write_samples(path, out)
