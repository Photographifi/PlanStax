import cv2
import numpy as np
import pytest

from planstax.core import finish
from planstax.core.alignment import GlobalAligner, StabilityMap, sample_shifted
from planstax.core.localalign import LocalAligner, place_points, place_points_with_report
from planstax.core.pipeline import Pipeline
from planstax.core.postprocess import estimate_rgb_shifts
from planstax.core.quality import analyze_frame
from planstax.core.wavelets import apply_wavelets
from planstax.io.ser import COLOR_MONO, COLOR_RGB, write_ser
from planstax.io.sources import open_source
from planstax.settings import AlignSettings, Settings, WaveletSettings
from planstax.synth import make_planet, make_sequence


def _shift(img, dx, dy):
    """frame(x) = img(x - d)"""
    h, w = img.shape[:2]
    return sample_shifted(img, -dx, -dy, w, h)


@pytest.mark.parametrize("surface", [False, True])
def test_global_alignment_recovers_shift(surface):
    truth = make_planet(256)
    if surface:
        truth = cv2.resize(truth[60:196, 60:196], (256, 256))  # fills the frame
    ref_c = analyze_frame(truth).centroid
    aligner = GlobalAligner(truth, surface, ref_c)
    for dx, dy in [(7.3, -4.6), (-12.25, 9.5), (0.4, 0.0)]:
        frame = _shift(truth, dx, dy)
        mx, my, _ = aligner.measure(frame, analyze_frame(frame).centroid)
        assert abs(mx - dx) < 0.06 and abs(my - dy) < 0.06


def test_surface_alignment_landscape_with_water_and_codec_blocks():
    # Terrestrial lucky imaging (the P1006397 case): hillside at the top, water that changes in
    # every frame below the shoreline, and an 8x8 block pattern fixed to the frame (video codec,
    # here a quarter of the scene's contrast). The centre holds nothing fixed and
    # full-resolution correlation is pulled to zero by the blocks: global alignment must still
    # find the true shifts.
    rng = np.random.default_rng(7)
    size = 1200
    land = cv2.GaussianBlur(rng.random((size, size)).astype(np.float32), (0, 0), 3.0)
    land = cv2.normalize(land, None, 0.3, 0.6, cv2.NORM_MINMAX)
    blocks = np.kron(rng.normal(0, land.std() / 4, (size // 8, size // 8)), np.ones((8, 8))).astype(np.float32)
    rows = np.arange(size, dtype=np.float32)[:, None]

    def frame(dx, dy):
        img = _shift(land, dx, dy)
        water = cv2.GaussianBlur(rng.random((size, size)).astype(np.float32), (0, 0), 1.2) * 0.5 + 0.4
        img = np.where(rows > size * 0.4 + dy, water, img)  # the shoreline moves with the view
        return np.clip(img + blocks, 0, 1).astype(np.float32)

    ref = frame(0, 0)
    aligner = GlobalAligner(ref, True, (size / 2, size / 2))
    for dx, dy in [(6.3, -1.2), (-4.5, 2.8), (11.0, 0.4)]:
        mx, my, _ = aligner.measure(frame(dx, dy), None)
        assert abs(mx - dx) < 1.0 and abs(my - dy) < 1.0, (dx, dy, mx, my)


def test_stability_map_handles_mostly_water():
    # Only 12 % of land at the top: the stability map built from the reference frames tells
    # land (static) from water (changing) and keeps the codec blocks from biasing the result.
    rng = np.random.default_rng(7)
    size = 2048
    land = cv2.GaussianBlur(rng.random((size, size)).astype(np.float32), (0, 0), 3.0)
    land = cv2.normalize(land, None, 0.3, 0.6, cv2.NORM_MINMAX)
    blocks = np.kron(rng.normal(0, land.std() / 4, (size // 8, size // 8)), np.ones((8, 8))).astype(np.float32)
    rows = np.arange(size, dtype=np.float32)[:, None]

    def frame(dx, dy):
        img = _shift(land, dx, dy)
        water = cv2.GaussianBlur(rng.random((size, size)).astype(np.float32), (0, 0), 1.2) * 0.5 + 0.4
        return np.clip(np.where(rows > size * 0.12 + dy, water, img) + blocks, 0, 1).astype(np.float32)

    stab, acc = StabilityMap(size, size), np.zeros((size, size))
    for _ in range(10):  # reference frames, already aligned
        d = rng.uniform(-3, 3, 2)
        aligned = sample_shifted(frame(*d), d[0], d[1], size, size)
        stab.add(aligned)
        acc += aligned
    smap = stab.result()
    land_rows = int(size * 0.12 / stab.f)
    assert smap[:land_rows - 3].mean() > 0.8 and smap[land_rows + 3:].mean() < 0.3
    aligner = GlobalAligner((acc / 10).astype(np.float32), True, (size / 2, size / 2), stability=smap)
    for dx, dy in [(6.3, -1.2), (-4.5, 2.8), (11.0, 0.4)]:
        mx, my, _ = aligner.measure(frame(dx, dy), None)
        assert abs(mx - dx) < 0.5 and abs(my - dy) < 0.5, (dx, dy, mx, my)


def test_quality_prefers_sharp_frames():
    truth = make_planet(200)
    q = [analyze_frame(cv2.GaussianBlur(truth, (0, 0), s)).quality for s in (0.5, 1.5, 3.0)]
    assert q[0] > q[1] > q[2]


def test_local_alignment_measures_local_shift():
    truth = make_planet(256)
    pts = place_points(truth, AlignSettings(ap_spacing=40, ap_box_size=32))
    assert len(pts) > 10
    # Shift the whole frame and check every AP sees it.
    frame = _shift(truth, 3.4, -2.2)
    la = LocalAligner(truth, pts, 32, 8)
    shifts, valid, quality = la.measure(frame, (3.0, -2.0))
    assert valid.mean() > 0.9
    assert np.abs(shifts[valid] - (3.4, -2.2)).max() < 0.25
    assert np.all(quality[valid] > 0)


def test_local_alignment_many_large_boxes():
    # Lunar-type surface: every point is valid, and points x box size (≈63 000 rows) exceeds
    # cv2.remap's 32 767-row limit, which used to abort the alignment.
    rng = np.random.default_rng(3)
    surface = cv2.GaussianBlur(rng.random((1400, 1400)).astype(np.float32), (0, 0), 3.0)
    surface = cv2.normalize(surface, None, 0.2, 0.9, cv2.NORM_MINMAX)
    ys, xs = np.mgrid[150:1250:37, 150:1250:37]
    pts = np.stack([xs.ravel(), ys.ravel()], axis=1)
    box = 70
    assert len(pts) * box > 32767
    la = LocalAligner(surface, pts, box, 8)
    shifts, valid, _ = la.measure(_shift(surface, 2.3, -1.6), (2.0, -2.0))
    assert valid.mean() > 0.95
    assert np.abs(shifts[valid] - (2.3, -1.6)).max() < 0.1


def test_points_respect_brightness_and_edges():
    truth = make_planet(256)
    s = AlignSettings(ap_spacing=20, ap_box_size=24, min_brightness=60, edge_margin=30)
    pts = place_points(truth, s)
    g = cv2.GaussianBlur(truth, (0, 0), 1.0)
    for x, y in pts:
        assert 30 <= x <= 256 - 30 and 30 <= y <= 256 - 30
        assert g[y - 12:y + 12, x - 12:x + 12].mean() >= 60 / 255 - 1e-6
    assert len(place_points(truth, AlignSettings(max_points=7))) == 7


def test_brightness_limits_are_absolute_and_explained():
    # Bright full-frame surface (levels ≈ 127–196 out of 255), like a lunar/solar video:
    # "Luminosité max. 150" means 150 on the image's 0-255 scale, as in RegiStax.
    rng = np.random.default_rng(1)
    texture = cv2.GaussianBlur(rng.random((600, 600)).astype(np.float32), (0, 0), 25.0)
    surface = cv2.normalize(texture, None, 127 / 255, 196 / 255, cv2.NORM_MINMAX)
    surface += cv2.GaussianBlur(rng.normal(0, 0.03, (600, 600)).astype(np.float32), (0, 0), 1.5)
    s = AlignSettings(ap_spacing=40, ap_box_size=40, min_brightness=15, max_brightness=150,
                      max_points=800, min_structure=0.1)
    pts, report = place_points_with_report(surface, s)
    g = cv2.GaussianBlur(surface, (0, 0), 1.0)
    assert 0 < len(pts) < report.candidates and report.too_bright > 0
    assert all(g[y - 20:y + 20, x - 20:x + 20].mean() <= 150 / 255 + 1e-6 for x, y in pts)
    lo, _, hi = report.brightness
    assert 120 < lo < 160 and 150 < hi < 200
    assert "plus claires que 150" in report.explain(s)

    s.max_brightness = 120  # everything is brighter: no point, and the fix is spelled out
    pts, report = place_points_with_report(surface, s)
    assert len(pts) == 0 and report.too_bright == report.candidates
    assert "Montez « Luminosité max. »" in report.explain(s)
    s.max_brightness = 255
    assert len(place_points(surface, s)) > 0


def test_wavelets_identity_and_sharpening():
    img = make_planet(128)
    for scheme in ("b3spline", "gaussian"):
        s = WaveletSettings(scheme=scheme)
        assert np.allclose(apply_wavelets(img, s), img, atol=1e-6)
        s.layers[0].gain = 3.0
        s.layers[1].gain = 2.0
        sharp = apply_wavelets(img, s)
        lap = lambda a: float(np.var(cv2.Laplacian(a, cv2.CV_32F)))
        assert lap(sharp) > lap(img) * 1.5


def test_wavelets_denoise_reduces_noise():
    rng = np.random.default_rng(0)
    clean = make_planet(128)
    noisy = np.clip(clean + rng.normal(0, 0.05, clean.shape).astype(np.float32), 0, 1)
    s = WaveletSettings()
    s.layers[0].denoise = 1.0
    s.layers[1].denoise = 0.5
    out = apply_wavelets(noisy, s)
    assert np.sqrt(np.mean((out - clean) ** 2)) < np.sqrt(np.mean((noisy - clean) ** 2)) * 0.8


def test_rgb_shift_estimation():
    g = make_planet(160)
    img = np.dstack([_shift(g, 1.5, -0.8), g, _shift(g, -1.2, 0.6)])
    (rx, ry), (bx, by) = estimate_rgb_shifts(img)
    assert abs(rx - 1.5) < 0.2 and abs(ry + 0.8) < 0.2
    assert abs(bx + 1.2) < 0.2 and abs(by - 0.6) < 0.2


def _register_rmse(img, truth):
    (dx, dy), _ = cv2.phaseCorrelate(truth.astype(np.float32), img.astype(np.float32))
    h, w = truth.shape[:2]
    back = sample_shifted(img, dx, dy, w, h)
    m = 20
    return float(np.sqrt(np.mean((back[m:-m, m:-m] - truth[m:-m, m:-m]) ** 2)))


@pytest.mark.parametrize("color", [False, True])
def test_pipeline_end_to_end(tmp_path, color):
    truth = make_planet(256, color=color, seed=5)
    frames, shifts, sigmas = make_sequence(truth, n=50, seed=2, distortion=1.2)
    path = str(tmp_path / "seq.ser")
    write_ser(path, [(f * 255 + 0.5).astype(np.uint8) for f in frames],
              color_id=COLOR_RGB if color else COLOR_MONO)
    src = open_source(path)
    s = Settings()
    s.align.ap_spacing = 24
    s.align.ap_box_size = 32
    s.limit.percent = 50
    s.stack.local_percent = 60
    pipe = Pipeline(src, s, workers=4)
    out = pipe.run_all()

    assert out.shape == truth.shape
    # The frames picked as best really are the least blurred ones.
    best = pipe.analysis.order[:10]
    assert np.median(sigmas[best]) < np.median(sigmas)
    lum = lambda a: a if a.ndim == 2 else cv2.cvtColor(a, cv2.COLOR_RGB2GRAY)
    stacked_err = _register_rmse(lum(out), lum(truth))
    best_frame_err = _register_rmse(lum(frames[int(pipe.analysis.order[0])]), lum(truth))
    assert stacked_err < best_frame_err
    # Final processing chain runs and keeps the range.
    s.wavelet.layers[0].gain = 2.0
    final = finish(out, s)
    assert final.shape == out.shape and final.min() >= 0 and final.max() <= 1
    src.close()


def test_pipeline_scale_2x(tmp_path):
    truth = make_planet(160, seed=7)
    frames, _, _ = make_sequence(truth, n=12, seed=4)
    path = str(tmp_path / "s.ser")
    write_ser(path, [(f * 255).astype(np.uint8) for f in frames])
    s = Settings()
    s.stack.scale = 2.0
    out = Pipeline(open_source(path), s, workers=2).run_all()
    assert out.shape == (320, 320)
