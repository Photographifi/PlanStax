"""Batch processing: every video of an input folder → one image per video in an output folder."""

from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass, field

from .core import Pipeline, estimate_rgb_shifts, finish
from .core.pipeline import Progress
from .io import VIDEO_EXTENSIONS, open_source, save_image
from .settings import Settings

# (label, extension, bits)
FORMATS = [("TIFF 16 bits", "tif", 16), ("PNG 16 bits", "png", 16),
           ("FITS 32 bits flottant", "fits", 32), ("JPEG", "jpg", 8)]


@dataclass
class BatchOptions:
    save_final: bool = True       # stacked + wavelets + finishing
    save_raw: bool = False        # stacked only
    fmt: str = "tif"
    bits: int = 16
    auto_rgb: bool = True         # measure the colour-channel shift of each video
    skip_existing: bool = True
    final_suffix: str = ""
    raw_suffix: str = "_brut"


@dataclass
class VideoResult:
    path: str
    outputs: list[str] = field(default_factory=list)
    frames: int = 0
    stacked: int = 0
    points: int = 0
    seconds: float = 0.0


def _natural_key(path: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", os.path.basename(path))]


def list_videos(folder: str) -> list[str]:
    """Videos directly inside `folder`, in natural order (jupiter_2 before jupiter_10)."""
    if not os.path.isdir(folder):
        return []
    files = [os.path.join(folder, f) for f in os.listdir(folder)
             if os.path.splitext(f)[1].lower() in VIDEO_EXTENSIONS
             and os.path.isfile(os.path.join(folder, f))]
    return sorted(files, key=_natural_key)


def output_paths(video: str, out_dir: str, opts: BatchOptions) -> dict[str, str]:
    stem = os.path.splitext(os.path.basename(video))[0]
    paths = {}
    if opts.save_final:
        paths["final"] = os.path.join(out_dir, f"{stem}{opts.final_suffix}.{opts.fmt}")
    if opts.save_raw:
        paths["raw"] = os.path.join(out_dir, f"{stem}{opts.raw_suffix}.{opts.fmt}")
    return paths


def is_done(video: str, out_dir: str, opts: BatchOptions) -> bool:
    paths = output_paths(video, out_dir, opts)
    return bool(paths) and all(os.path.isfile(p) for p in paths.values())


def process_video(path: str, settings: Settings, out_dir: str, opts: BatchOptions,
                  progress: Progress | None = None, cancel: threading.Event | None = None,
                  workers: int | None = None, bayer: str | None = None) -> VideoResult:
    """Stack one video and write the requested images. Raises on error (or Cancelled)."""
    t0 = time.time()
    result = VideoResult(path)
    src = open_source(path, bayer)
    try:
        result.frames = len(src)
        pipe = Pipeline(src, settings.copy(), workers=workers)
        stacked = pipe.run_all(progress, cancel)
        result.stacked, result.points = len(pipe.selected), len(pipe.points)
    finally:
        src.close()
    os.makedirs(out_dir, exist_ok=True)
    paths = output_paths(path, out_dir, opts)
    if "raw" in paths:
        save_image(paths["raw"], stacked, bits=opts.bits)
        result.outputs.append(paths["raw"])
    if "final" in paths:
        s = settings.copy()
        if opts.auto_rgb and stacked.ndim == 3:
            s.post.shift_r, s.post.shift_b = estimate_rgb_shifts(stacked)
        save_image(paths["final"], finish(stacked, s), bits=opts.bits)
        result.outputs.append(paths["final"])
    result.seconds = time.time() - t0
    return result
