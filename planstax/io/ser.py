"""Reader and writer for the SER video format (Lucam Recorder / FireCapture / ASICap / SharpCap).

Layout (public SER v3 specification):
    178-byte header, then FrameCount frames of Width*Height*Planes samples
    (1 byte per sample if PixelDepth <= 8, else 2), then an optional trailer of
    FrameCount int64 timestamps (UTC, 100 ns ticks since 0001-01-01).
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np

HEADER_SIZE = 178
FILE_ID = b"LUCAM-RECORDER"

COLOR_MONO = 0
COLOR_BAYER_RGGB = 8
COLOR_BAYER_GRBG = 9
COLOR_BAYER_GBRG = 10
COLOR_BAYER_BGGR = 11
COLOR_BAYER_CYYM = 16
COLOR_BAYER_YCMY = 17
COLOR_BAYER_YMCY = 18
COLOR_BAYER_MYYC = 19
COLOR_RGB = 100
COLOR_BGR = 101

BAYER_PATTERNS = {
    COLOR_BAYER_RGGB: "RGGB",
    COLOR_BAYER_GRBG: "GRBG",
    COLOR_BAYER_GBRG: "GBRG",
    COLOR_BAYER_BGGR: "BGGR",
}

_HEADER_STRUCT = struct.Struct("<14s7i40s40s40sqq")
assert _HEADER_STRUCT.size == HEADER_SIZE

_TICKS_EPOCH = datetime(1, 1, 1)


def ticks_to_datetime(ticks: int) -> datetime | None:
    if ticks <= 0:
        return None
    try:
        return _TICKS_EPOCH + timedelta(microseconds=ticks // 10)
    except OverflowError:
        return None


def datetime_to_ticks(dt: datetime) -> int:
    delta = dt - _TICKS_EPOCH
    return (delta.days * 86400 + delta.seconds) * 10_000_000 + delta.microseconds * 10


@dataclass
class SerHeader:
    color_id: int = COLOR_MONO
    width: int = 0
    height: int = 0
    pixel_depth: int = 8
    frame_count: int = 0
    lu_id: int = 0
    little_endian_flag: int = 0
    observer: str = ""
    instrument: str = ""
    telescope: str = ""
    date_time: int = 0
    date_time_utc: int = 0

    @property
    def planes(self) -> int:
        return 3 if self.color_id in (COLOR_RGB, COLOR_BGR) else 1

    @property
    def bytes_per_sample(self) -> int:
        return 1 if self.pixel_depth <= 8 else 2

    @property
    def frame_bytes(self) -> int:
        return self.width * self.height * self.planes * self.bytes_per_sample

    @property
    def bayer_pattern(self) -> str | None:
        return BAYER_PATTERNS.get(self.color_id)


def _decode(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("latin-1").strip()


def _encode(text: str) -> bytes:
    return text.encode("latin-1", "replace")[:40].ljust(40, b"\0")


@dataclass
class SerFile:
    """Memory-mapped SER file. Frames are returned as native numpy arrays (uint8/uint16)."""

    path: str
    header: SerHeader = field(init=False)
    byteorder: str = field(init=False, default="<")
    timestamps: np.ndarray | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        with open(self.path, "rb") as fh:
            raw = fh.read(HEADER_SIZE)
        if len(raw) < HEADER_SIZE:
            raise ValueError("Fichier SER tronqué (en-tête incomplet)")
        (file_id, lu_id, color_id, le_flag, width, height, depth, count,
         observer, instrument, telescope, dt, dt_utc) = _HEADER_STRUCT.unpack(raw)
        if not file_id.startswith(b"LUCAM"):
            raise ValueError("Ce fichier n'est pas une vidéo SER valide")
        self.header = SerHeader(
            color_id=color_id, width=width, height=height, pixel_depth=depth,
            frame_count=count, lu_id=lu_id, little_endian_flag=le_flag,
            observer=_decode(observer), instrument=_decode(instrument),
            telescope=_decode(telescope), date_time=dt, date_time_utc=dt_utc,
        )
        h = self.header
        if h.width <= 0 or h.height <= 0:
            raise ValueError("Dimensions d'image invalides dans l'en-tête SER")

        size = os.path.getsize(self.path)
        available = (size - HEADER_SIZE) // h.frame_bytes
        if available < h.frame_count or h.frame_count <= 0:
            # Capture interrupted before the header was finalised: trust the file size.
            h.frame_count = int(available)
        if h.frame_count <= 0:
            raise ValueError("Le fichier SER ne contient aucune image")

        shape = (h.frame_count, h.height, h.width) + ((3,) if h.planes == 3 else ())
        dtype = np.uint8 if h.bytes_per_sample == 1 else np.dtype("<u2")
        self._data = np.memmap(self.path, dtype=dtype, mode="r", offset=HEADER_SIZE, shape=shape)

        if h.bytes_per_sample == 2:
            self.byteorder = self._detect_byteorder()

        trailer_offset = HEADER_SIZE + h.frame_count * h.frame_bytes
        if size >= trailer_offset + 8 * h.frame_count:
            ts = np.fromfile(self.path, dtype="<i8", count=h.frame_count, offset=trailer_offset)
            if np.all(ts > 0):
                self.timestamps = ts

    def _detect_byteorder(self) -> str:
        """The SER 'LittleEndian' flag is used inconsistently by capture software, so we
        pick the byte order that gives the smoother image (real data has spatially
        correlated high bytes; the wrong order turns the low byte into noise)."""
        frame = np.asarray(self._data[self.header.frame_count // 2], dtype=np.uint16)
        sample = frame[:: max(1, frame.shape[0] // 256)]

        def roughness(a: np.ndarray) -> float:
            a = a.astype(np.float64)
            return float(np.mean(np.abs(np.diff(a, axis=1)))) / (float(a.std()) + 1e-9)

        swapped = sample.byteswap()
        return "<" if roughness(sample) <= roughness(swapped) else ">"

    def __len__(self) -> int:
        return self.header.frame_count

    def frame(self, index: int) -> np.ndarray:
        data = np.array(self._data[index])  # copy out of the memmap
        if self.byteorder == ">":
            data.byteswap(inplace=True)
        if self.header.color_id == COLOR_BGR:
            data = data[..., ::-1].copy()
        return data

    def timestamp(self, index: int) -> datetime | None:
        if self.timestamps is None:
            return None
        return ticks_to_datetime(int(self.timestamps[index]))

    def close(self) -> None:
        mm = getattr(self._data, "_mmap", None)
        if mm is not None:
            mm.close()


def write_ser(path: str, frames, color_id: int = COLOR_MONO, pixel_depth: int | None = None,
              observer: str = "", instrument: str = "", telescope: str = "",
              timestamps: list[datetime] | None = None) -> None:
    """Write frames (iterable of HxW or HxWx3 uint8/uint16 arrays, RGB order) to a SER file."""
    frames = list(frames)
    if not frames:
        raise ValueError("Aucune image à écrire")
    first = frames[0]
    height, width = first.shape[:2]
    if pixel_depth is None:
        pixel_depth = 8 if first.dtype == np.uint8 else 16
    dtype = np.uint8 if pixel_depth <= 8 else np.dtype("<u2")
    now = timestamps[0] if timestamps else datetime.now(timezone.utc).replace(tzinfo=None)
    header = _HEADER_STRUCT.pack(
        FILE_ID, 0, color_id, 0, width, height, pixel_depth, len(frames),
        _encode(observer), _encode(instrument), _encode(telescope),
        datetime_to_ticks(now), datetime_to_ticks(now),
    )
    with open(path, "wb") as fh:
        fh.write(header)
        for f in frames:
            if f.shape[:2] != (height, width):
                raise ValueError("Toutes les images doivent avoir la même taille")
            data = np.ascontiguousarray(f, dtype=dtype)
            if color_id == COLOR_BGR:
                data = np.ascontiguousarray(data[..., ::-1])
            fh.write(data.tobytes())
        if timestamps:
            fh.write(np.asarray([datetime_to_ticks(t) for t in timestamps], dtype="<i8").tobytes())
