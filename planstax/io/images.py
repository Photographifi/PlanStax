"""Still-image loading and saving (TIFF, PNG, FITS, JPEG, BMP) with Unicode-safe paths."""

from __future__ import annotations

import os

import cv2
import numpy as np
import tifffile

from .fits import read_fits, write_fits

IMAGE_EXTENSIONS = (".tif", ".tiff", ".png", ".fit", ".fits", ".fts", ".jpg", ".jpeg", ".bmp")
FITS_EXTENSIONS = (".fit", ".fits", ".fts")


def _ext(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def _decode_with_opencv(path: str) -> np.ndarray:
    # cv2.imread() cannot open non-ASCII paths on Windows (e.g. "Bureau/Éclipse.png").
    buf = np.fromfile(path, dtype=np.uint8)
    data = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED | cv2.IMREAD_ANYDEPTH)
    if data is None:
        raise ValueError(f"Impossible de lire l'image : {path}")
    if data.ndim == 3:
        data = cv2.cvtColor(data, cv2.COLOR_BGRA2RGB if data.shape[2] == 4 else cv2.COLOR_BGR2RGB)
    return data


def read_raw(path: str) -> np.ndarray:
    """Load an image as stored (uint8/uint16/float), RGB channel order, HxW or HxWx3."""
    ext = _ext(path)
    if ext in FITS_EXTENSIONS:
        data, _ = read_fits(path)
    elif ext in (".tif", ".tiff"):
        try:
            data = tifffile.imread(path)
        except ValueError:
            # Compressions tifffile cannot decode without the optional imagecodecs package —
            # notably LZW, used by RegiStax and many other programs: OpenCV's libtiff can.
            data = _decode_with_opencv(path)
        if data.ndim == 3 and data.shape[0] in (3, 4) and data.shape[-1] not in (3, 4):
            data = np.moveaxis(data, 0, -1)  # planar TIFF
    else:
        data = _decode_with_opencv(path)
    if data.ndim == 3 and data.shape[2] == 4:
        data = data[..., :3]
    if data.ndim == 3 and data.shape[2] == 1:
        data = data[..., 0]
    return np.ascontiguousarray(data)


def to_float(data: np.ndarray, bit_depth: int | None = None) -> np.ndarray:
    """Convert raw samples to float32 in [0, 1]."""
    if data.dtype == np.uint8:
        return data.astype(np.float32) * (1.0 / 255.0)
    if data.dtype == np.uint16:
        scale = float((1 << bit_depth) - 1) if bit_depth and bit_depth < 16 else 65535.0
        return np.clip(data.astype(np.float32) * (1.0 / scale), 0.0, 1.0)
    if np.issubdtype(data.dtype, np.integer):
        info = np.iinfo(data.dtype)
        return ((data.astype(np.float32) - info.min) / float(info.max - info.min))
    data = data.astype(np.float32)
    peak = float(np.nanmax(data)) if data.size else 1.0
    if peak > 1.0:
        data = data / peak
    return np.nan_to_num(np.clip(data, 0.0, None), copy=False)


def read_image(path: str) -> np.ndarray:
    """Load an image as float32 in [0, 1]."""
    return to_float(read_raw(path))


def save_image(path: str, image: np.ndarray, bits: int = 16) -> None:
    """Save a float [0, 1] image. TIFF/PNG use `bits` (8 or 16), FITS keeps 32-bit float
    when bits == 32, JPEG is always 8-bit."""
    ext = _ext(path)
    img = np.clip(np.nan_to_num(image.astype(np.float32)), 0.0, 1.0)
    if ext in (".jpg", ".jpeg", ".bmp"):
        bits = 8

    if ext in FITS_EXTENSIONS:
        if bits == 32:
            write_fits(path, img)
        else:
            write_fits(path, _quantize(img, bits))
        return
    if bits not in (8, 16):
        bits = 16
    data = _quantize(img, bits)
    if ext in (".tif", ".tiff"):
        tifffile.imwrite(path, data, photometric="rgb" if data.ndim == 3 else "minisblack",
                         compression="zlib" if data.dtype == np.uint16 else None)
        return
    if data.ndim == 3:
        data = cv2.cvtColor(data, cv2.COLOR_RGB2BGR)
    params = [cv2.IMWRITE_JPEG_QUALITY, 95] if ext in (".jpg", ".jpeg") else []
    ok, buf = cv2.imencode(ext or ".png", data, params)
    if not ok:
        raise ValueError(f"Format d'image non pris en charge : {ext}")
    buf.tofile(path)


def _quantize(img: np.ndarray, bits: int) -> np.ndarray:
    if bits == 8:
        return (img * 255.0 + 0.5).astype(np.uint8)
    return (img * 65535.0 + 0.5).astype(np.uint16)
