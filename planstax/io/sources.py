"""Frame sources: a uniform random-access interface over SER, AVI and image sequences.

Every source returns float32 frames in [0, 1], either HxW (mono) or HxWx3 (RGB).
"""

from __future__ import annotations

import ctypes
import os
import re
import threading

import cv2
import numpy as np

from .images import IMAGE_EXTENSIONS, read_raw, to_float
from .ser import SerFile

VIDEO_EXTENSIONS = (".ser", ".avi", ".mp4", ".mov", ".mkv", ".m4v", ".wmv")
NO_BAYER = "NONE"  # bayer_override value that forces mono even if the file declares a Bayer matrix


def _bayer_choice(override: str | None, declared: str | None) -> str | None:
    if override == NO_BAYER:
        return None
    return override or declared

BAYER_PATTERNS = ("RGGB", "GRBG", "GBRG", "BGGR")


def debayer(raw: np.ndarray, pattern: str) -> np.ndarray:
    """Demosaic a uint8/uint16 Bayer mosaic into RGB with edge-aware interpolation."""
    pattern = pattern.upper()
    if pattern not in BAYER_PATTERNS:
        raise ValueError(f"Matrice de Bayer inconnue : {pattern}")
    try:
        return cv2.cvtColor(raw, getattr(cv2, f"COLOR_Bayer{pattern}2RGB_EA"))
    except (AttributeError, cv2.error):
        return cv2.cvtColor(raw, getattr(cv2, f"COLOR_Bayer{pattern}2RGB"))


def luminance(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 2:
        return frame
    return cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)


class FrameSource:
    """Base class. Subclasses implement `_read(index)` returning a float32 frame."""

    name: str = ""
    path: str = ""
    thread_safe: bool = True
    bit_depth: int = 8
    bayer: str | None = None

    def __init__(self) -> None:
        self._count = 0
        self._shape: tuple[int, ...] = (0, 0)

    def __len__(self) -> int:
        return self._count

    @property
    def height(self) -> int:
        return self._shape[0]

    @property
    def width(self) -> int:
        return self._shape[1]

    @property
    def is_color(self) -> bool:
        return len(self._shape) == 3

    def frame(self, index: int) -> np.ndarray:
        if not 0 <= index < self._count:
            raise IndexError(index)
        return self._read(index)

    def _read(self, index: int) -> np.ndarray:  # pragma: no cover - abstract
        raise NotImplementedError

    def describe(self) -> str:
        kind = f"Bayer {self.bayer}" if self.bayer else ("couleur" if self.is_color else "mono")
        return (f"{self.name} — {len(self)} images, {self.width}×{self.height}, "
                f"{self.bit_depth} bits, {kind}")

    def close(self) -> None:
        pass


class SerSource(FrameSource):
    def __init__(self, path: str, bayer_override: str | None = None) -> None:
        super().__init__()
        self.path = path
        self.name = os.path.basename(path)
        self.ser = SerFile(path)
        h = self.ser.header
        self._count = len(self.ser)
        self.bit_depth = h.pixel_depth if 0 < h.pixel_depth <= 16 else (8 if h.bytes_per_sample == 1 else 16)
        self.bayer = _bayer_choice(bayer_override, h.bayer_pattern)
        color = h.planes == 3 or self.bayer is not None
        self._shape = (h.height, h.width, 3) if color else (h.height, h.width)
        # Some cameras write 12/14-bit data MSB-aligned while declaring 12/14 bits.
        if h.bytes_per_sample == 2 and self.bit_depth < 16:
            probe = self.ser.frame(self._count // 2)
            if int(probe.max()) >= (1 << self.bit_depth):
                self.bit_depth = 16
        self.timestamps = self.ser.timestamps

    def _read(self, index: int) -> np.ndarray:
        raw = self.ser.frame(index)
        if self.bayer:
            raw = debayer(raw, self.bayer)
        return to_float(raw, self.bit_depth)

    def close(self) -> None:
        self.ser.close()


def _short_path(path: str) -> str:
    """OpenCV's FFmpeg backend cannot always open Unicode paths on Windows; the 8.3 short
    path is plain ASCII."""
    if os.name != "nt" or path.isascii():
        return path
    buf = ctypes.create_unicode_buffer(1024)
    if ctypes.windll.kernel32.GetShortPathNameW(path, buf, 1024):
        return buf.value
    return path


class VideoSource(FrameSource):
    """AVI and other containers via OpenCV/FFmpeg. Not thread-safe: reads are serialised."""

    thread_safe = False

    def __init__(self, path: str, bayer_override: str | None = None) -> None:
        super().__init__()
        self.path = path
        self.name = os.path.basename(path)
        self._lock = threading.Lock()
        self._cap = cv2.VideoCapture(_short_path(path))
        if not self._cap.isOpened():
            raise ValueError(f"Impossible d'ouvrir la vidéo : {path}")
        self._next = 0
        first = self._grab(0)
        if first is None:
            raise ValueError("La vidéo ne contient aucune image lisible")
        self._first = first
        self.bit_depth = 16 if first.dtype == np.uint16 else 8
        self.bayer = _bayer_choice(bayer_override, None)
        self._mono_source = first.ndim == 2 or self._channels_equal(first)
        count = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if count <= 0:
            count = self._count_frames()
        self._count = count
        h, w = first.shape[:2]
        self._shape = (h, w, 3) if (self.bayer or not self._mono_source) else (h, w)

    @staticmethod
    def _channels_equal(img: np.ndarray) -> bool:
        if img.ndim != 3:
            return True
        step = max(1, img.shape[0] // 64)
        a = img[::step]
        return bool(np.array_equal(a[..., 0], a[..., 1]) and np.array_equal(a[..., 1], a[..., 2]))

    def _count_frames(self) -> int:
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        n = 0
        while self._cap.grab():
            n += 1
        self._next = n
        return n

    def _grab(self, index: int) -> np.ndarray | None:
        if index != self._next:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, img = self._cap.read()
        self._next = index + 1
        if not ok or img is None:
            return None
        if img.ndim == 3 and img.shape[2] == 1:
            img = img[..., 0]
        return img

    def _read(self, index: int) -> np.ndarray:
        with self._lock:
            raw = self._grab(index)
        if raw is None:
            raise IOError(f"Lecture impossible de l'image {index}")
        if raw.ndim == 3:
            if self._mono_source or self.bayer:
                raw = raw[..., 0]
            else:
                raw = cv2.cvtColor(raw, cv2.COLOR_BGR2RGB)
        if self.bayer:
            raw = debayer(raw, self.bayer)
        return to_float(raw)

    def close(self) -> None:
        self._cap.release()


def _natural_key(path: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", os.path.basename(path))]


class ImageSequenceSource(FrameSource):
    def __init__(self, paths: list[str], bayer_override: str | None = None) -> None:
        super().__init__()
        if not paths:
            raise ValueError("Aucune image sélectionnée")
        self.paths = sorted(paths, key=_natural_key)
        self.path = self.paths[0]
        self.name = (os.path.basename(self.paths[0]) if len(self.paths) == 1
                     else f"{os.path.basename(self.paths[0])} … ({len(self.paths)} fichiers)")
        self.bayer = _bayer_choice(bayer_override, None)
        first = read_raw(self.paths[0])
        self.bit_depth = 8 if first.dtype == np.uint8 else 16
        self._count = len(self.paths)
        h, w = first.shape[:2]
        self._shape = (h, w, 3) if (first.ndim == 3 or self.bayer) else (h, w)

    def _read(self, index: int) -> np.ndarray:
        raw = read_raw(self.paths[index])
        if raw.shape[:2] != self._shape[:2]:
            raise ValueError(f"Taille différente pour {os.path.basename(self.paths[index])}")
        if self.bayer and raw.ndim == 2:
            if raw.dtype not in (np.uint8, np.uint16):
                raw = (to_float(raw) * 65535).astype(np.uint16)
            raw = debayer(raw, self.bayer)
        img = to_float(raw)
        if img.ndim == 2 and self.is_color:
            img = np.repeat(img[..., None], 3, axis=2)
        return img


def open_source(paths: str | list[str], bayer_override: str | None = None) -> FrameSource:
    """Open a SER/AVI video or a list of still images as a FrameSource."""
    if isinstance(paths, str):
        paths = [paths]
    if not paths:
        raise ValueError("Aucun fichier sélectionné")
    ext = os.path.splitext(paths[0])[1].lower()
    if len(paths) == 1 and ext == ".ser":
        return SerSource(paths[0], bayer_override)
    if len(paths) == 1 and ext in VIDEO_EXTENSIONS:
        return VideoSource(paths[0], bayer_override)
    if all(os.path.splitext(p)[1].lower() in IMAGE_EXTENSIONS for p in paths):
        return ImageSequenceSource(list(paths), bayer_override)
    raise ValueError("Format non reconnu (attendu : SER, AVI ou une série d'images)")
