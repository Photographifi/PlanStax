"""Multi-scale ("wavelet") sharpening and denoising, 6 layers.

The image is split into detail layers w1..w6 plus a residual:
    c0 = image, c_j = smooth_j(c_{j-1}) (or smooth_j(image) for the Gaussian scheme),
    w_j = c_{j-1} - c_j,   image = c_6 + Σ w_j   (exact reconstruction).
Each layer is soft-thresholded (denoise) and multiplied by its gain (sharpen), then the
layers are summed back. Gains of 1 and denoise 0 return the original image.
"""

from __future__ import annotations

import cv2
import numpy as np

from ..settings import WaveletSettings

_B3 = np.array([1.0, 4.0, 6.0, 4.0, 1.0], dtype=np.float32) / 16.0
N_LAYERS = 6


def layer_scale(settings: WaveletSettings, j: int) -> float:
    """Scale (in pixels) of layer j (1-based)."""
    base = max(0.25, float(settings.initial))
    return base * (2 ** (j - 1) if settings.step == "dyadic" else j)


def _atrous(img: np.ndarray, dilation: int) -> np.ndarray:
    k = np.zeros(4 * dilation + 1, dtype=np.float32)
    k[::dilation] = _B3
    return cv2.sepFilter2D(img, cv2.CV_32F, k, k, borderType=cv2.BORDER_REFLECT)


def decompose(img: np.ndarray, settings: WaveletSettings) -> tuple[list[np.ndarray], np.ndarray]:
    img = img.astype(np.float32, copy=False)
    layers = []
    prev = img
    for j in range(1, N_LAYERS + 1):
        scale = layer_scale(settings, j)
        if settings.scheme == "gaussian":
            cur = cv2.GaussianBlur(img, (0, 0), scale, borderType=cv2.BORDER_REFLECT)
        else:
            cur = _atrous(prev, max(1, int(round(scale))))
        layers.append(prev - cur)
        prev = cur
    return layers, prev


def noise_sigma(layer: np.ndarray) -> float:
    step = max(1, layer.shape[0] // 512)
    sample = np.abs(layer[::step, ::step])
    return float(np.median(sample)) * 1.4826


def _soft(w: np.ndarray, t: float) -> np.ndarray:
    if t <= 0:
        return w
    return np.sign(w) * np.maximum(np.abs(w) - t, 0.0)


def _luminance(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if img.ndim == 3 else img


class WaveletProcessor:
    """Caches the decomposition so moving a gain slider only recombines the layers."""

    def __init__(self) -> None:
        self._image: np.ndarray | None = None
        self._key = None
        self._layers: list[np.ndarray] = []
        self._residual: np.ndarray | None = None
        self._sigmas: list[float] = []

    def set_image(self, img: np.ndarray | None) -> None:
        self._image = None if img is None else img.astype(np.float32, copy=False)
        self._key = None

    def _ensure(self, s: WaveletSettings) -> None:
        key = (s.scheme, s.step, float(s.initial), s.target if self._image.ndim == 3 else "rgb")
        if key == self._key:
            return
        src = _luminance(self._image) if key[3] == "luminance" else self._image
        self._layers, self._residual = decompose(src, s)
        self._sigmas = [noise_sigma(l) for l in self._layers]
        self._key = key

    def layers(self, s: WaveletSettings) -> list[np.ndarray]:
        self._ensure(s)
        return self._layers

    def render(self, s: WaveletSettings) -> np.ndarray:
        if self._image is None:
            raise RuntimeError("Aucune image à traiter")
        if s.is_neutral():
            return self._image
        self._ensure(s)
        out = self._residual.copy()
        for layer, sigma, p in zip(self._layers, self._sigmas, s.layers):
            if not p.enabled:
                continue
            w = _soft(layer, 3.0 * float(p.denoise) * sigma)
            out += w * float(p.gain) if p.gain != 1.0 else w
        if self._key[3] == "luminance":
            out = self._image + (out - _luminance(self._image))[..., None]
        return np.clip(out, 0.0, 1.0)


def apply_wavelets(img: np.ndarray, settings: WaveletSettings) -> np.ndarray:
    proc = WaveletProcessor()
    proc.set_image(img)
    return proc.render(settings)
