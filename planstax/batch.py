"""Batch processing: every video of an input folder → one image per video in an output folder,
and optionally the mosaic of these images."""

from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass, field

import numpy as np

from .core import Pipeline, estimate_rgb_shifts, finish
from .core.mosaic import MosaicPlan, plan_mosaic, render_mosaic
from .core.pipeline import Progress
from .io import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, open_source, save_image
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
    mosaic: bool = False          # assemble the images of the batch into a mosaic at the end
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


# ---------------------------------------------------------------------------------- mosaics
MOSAIC_NAME = "mosaique"
_MOSAIC_FILE = re.compile(rf"^{MOSAIC_NAME}(_\d+)?(_brut)?(\.partiel)?$", re.IGNORECASE)


def mosaic_sources(videos: list[str], out_dir: str, opts: BatchOptions) -> list[str]:
    """Images of these videos that make up the mosaic: the processed images when the batch
    writes them, otherwise the raw stacks."""
    key = "final" if opts.save_final else "raw"
    paths = [output_paths(v, out_dir, opts).get(key) for v in videos]
    return [p for p in paths if p and os.path.isfile(p)]


def mosaic_suffix(opts: BatchOptions) -> str:
    return opts.final_suffix if opts.save_final else opts.raw_suffix


def list_images(folder: str, raw: bool = False, raw_suffix: str = "_brut") -> list[str]:
    """Images of `folder` to assemble, in natural order, without the mosaics already made:
    only the raw stacks (« _brut ») when `raw`, otherwise everything but them."""
    if not os.path.isdir(folder):
        return []
    files = []
    for f in os.listdir(folder):
        stem, ext = os.path.splitext(f)
        path = os.path.join(folder, f)
        if ext.lower() not in IMAGE_EXTENSIONS or not os.path.isfile(path) or _MOSAIC_FILE.match(stem):
            continue
        if stem.lower().endswith(raw_suffix.lower()) == raw:
            files.append(path)
    return sorted(files, key=_natural_key)


def mosaic_paths(out_dir: str, count: int, fmt: str = "tif", name: str = MOSAIC_NAME,
                 suffix: str = "") -> list[str]:
    if count == 1:
        return [os.path.join(out_dir, f"{name}{suffix}.{fmt}")]
    return [os.path.join(out_dir, f"{name}_{k + 1}{suffix}.{fmt}") for k in range(count)]


@dataclass
class MosaicResult:
    plan: MosaicPlan
    outputs: list[str] = field(default_factory=list)
    previews: list[np.ndarray] = field(default_factory=list)
    seconds: float = 0.0

    def summary(self) -> str:
        if not self.outputs:
            return "aucune mosaïque"
        parts = [f"{os.path.basename(p)} ({len(g.paths)} images)" for p, g in zip(self.outputs, self.plan.groups)]
        return ", ".join(parts)


def make_mosaics(paths: list[str], out_dir: str, fmt: str = "tif", bits: int = 16,
                 name: str = MOSAIC_NAME, suffix: str = "", progress: Progress | None = None,
                 cancel: threading.Event | None = None, workers: int | None = None) -> MosaicResult:
    """Assemble the overlapping images of `paths`: one file per set of images that overlap
    each other (usually a single mosaic). Raises Cancelled."""
    t0 = time.time()
    report = progress or (lambda f, m: None)
    plan = plan_mosaic(paths, lambda f, m: report(0.4 * f, m), cancel, workers)
    result = MosaicResult(plan)
    if plan.groups:
        os.makedirs(out_dir, exist_ok=True)
    total = sum(g.pixels for g in plan.groups)
    done = 0
    for g, path in zip(plan.groups, mosaic_paths(out_dir, len(plan.groups), fmt, name, suffix)):
        start = done

        def part(f, m, start=start, size=g.pixels):
            report(0.4 + 0.6 * (start + f * size) / total, m)

        result.previews.append(render_mosaic(g, path, bits, part, cancel))
        result.outputs.append(path)
        done += g.pixels
    result.seconds = time.time() - t0
    return result
