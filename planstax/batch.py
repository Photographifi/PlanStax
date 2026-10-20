"""Batch processing: every video of an input folder → one image per video in an output folder,
and optionally the mosaic of these images."""

from __future__ import annotations

import dataclasses
import os
import re
import threading
import time
from dataclasses import dataclass, field

import numpy as np

from .core import Pipeline, apply_pre, apply_wavelets, estimate_rgb_shifts, finish
from .core.mosaic import MosaicGroup, MosaicPlan, plan_mosaic, render_mosaic
from .core.pipeline import Progress
from .core.postprocess import apply_tone, has_tone
from .io import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, open_source, save_image
from .i18n import N_, tr
from .io.images import quantize, to_float
from .settings import Settings

# (label — translated where it is shown, extension, bits)
FORMATS = [(N_("TIFF 16 bits"), "tif", 16), (N_("PNG 16 bits"), "png", 16),
           (N_("FITS 32 bits flottant"), "fits", 32), (N_("JPEG"), "jpg", 8)]


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
    if opts.save_raw or opts.mosaic:  # the mosaic is assembled from the raw stacks
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
    """Images of these videos that make up the mosaic: their raw stacks. Wavelets are applied
    to each one, but levels and colours to the whole mosaic, once its brightness is evened
    out: applied image by image, a white point clips the sky of the brighter images and
    leaves zones that no correction can join any more."""
    paths = [output_paths(v, out_dir, dataclasses.replace(opts, mosaic=True))["raw"] for v in videos]
    return [p for p in paths if os.path.isfile(p)]


def mosaic_suffix(opts: BatchOptions) -> str:
    return opts.final_suffix if opts.save_final else opts.raw_suffix


def mosaic_processing(settings: Settings, auto_rgb: bool = True):
    """(prepare, finish) for render_mosaic: what the finishing of a single image does, split
    between each image (colour-channel alignment, wavelets) and the blended mosaic (colour
    balance, levels, gamma, contrast, saturation). The orientation is applied to the
    placement (MosaicGroup.oriented)."""
    s = settings.copy()

    def prepare(samples: np.ndarray) -> np.ndarray:
        img = to_float(samples)
        post = dataclasses.replace(s.post)
        if auto_rgb and img.ndim == 3:
            post.shift_r, post.shift_b = estimate_rgb_shifts(img)
        img = apply_wavelets(apply_pre(img, post), s.wavelet)
        return quantize(np.clip(img, 0.0, 1.0), 16)

    def finish_band(band: np.ndarray) -> np.ndarray:
        return apply_tone(band, s.post)

    return prepare, finish_band if has_tone(s.post) else None


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
    groups: list[MosaicGroup] = field(default_factory=list)   # as rendered (orientation applied)
    seconds: float = 0.0

    def summary(self) -> str:
        if not self.outputs:
            return tr("aucune mosaïque")
        parts = [tr("{name} ({n} images)", name=os.path.basename(p), n=len(g.paths))
                 for p, g in zip(self.outputs, self.groups)]
        return ", ".join(parts)


def make_mosaics(paths: list[str], out_dir: str, fmt: str = "tif", bits: int = 16,
                 name: str = MOSAIC_NAME, suffix: str = "", progress: Progress | None = None,
                 cancel: threading.Event | None = None, workers: int | None = None,
                 settings: Settings | None = None, auto_rgb: bool = True) -> MosaicResult:
    """Assemble the overlapping images of `paths`: one file per set of images that overlap
    each other (usually a single mosaic). With `settings`, the images are raw stacks that
    receive the wavelets and finishing of these settings (see mosaic_processing). Raises
    Cancelled."""
    t0 = time.time()
    report = progress or (lambda f, m: None)
    plan = plan_mosaic(paths, lambda f, m: report(0.4 * f, m), cancel, workers)
    result = MosaicResult(plan)
    if plan.groups:
        os.makedirs(out_dir, exist_ok=True)
    prepare = finish_band = None
    if settings is not None:
        prepare, finish_band = mosaic_processing(settings, auto_rgb)
    total = sum(g.pixels for g in plan.groups)
    done = 0
    for g, path in zip(plan.groups, mosaic_paths(out_dir, len(plan.groups), fmt, name, suffix)):
        start = done

        def part(f, m, start=start, size=g.pixels):
            report(0.4 + 0.6 * (start + f * size) / total, m)

        if settings is not None:
            p = settings.post
            g = g.oriented(p.rotate, p.flip_h, p.flip_v, p.angle)
        result.previews.append(render_mosaic(g, path, bits, part, cancel,
                                             prepare=prepare, finish=finish_band))
        result.outputs.append(path)
        result.groups.append(g)
        done += g.pixels
    result.seconds = time.time() - t0
    return result
