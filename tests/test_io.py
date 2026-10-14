import os
from datetime import datetime, timedelta

import numpy as np
import pytest

from planstax.io import open_source, read_image, save_image
from planstax.io.fits import read_fits, write_fits
from planstax.io.ser import (COLOR_BAYER_RGGB, COLOR_BGR, COLOR_MONO, COLOR_RGB,
                                HEADER_SIZE, SerFile, write_ser)
from planstax.io.sources import debayer


def _gradient(h=40, w=60, dtype=np.uint8, maxv=255):
    y, x = np.mgrid[0:h, 0:w]
    return ((x + y) / (h + w) * maxv).astype(dtype)


def test_ser_mono8_roundtrip(tmp_path):
    frames = [_gradient() + i for i in range(5)]
    t0 = datetime(2026, 8, 12, 20, 0, 0)
    stamps = [t0 + timedelta(milliseconds=10 * i) for i in range(5)]
    path = str(tmp_path / "a.ser")
    write_ser(path, frames, observer="Moi", timestamps=stamps)
    ser = SerFile(path)
    assert len(ser) == 5
    assert ser.header.observer == "Moi"
    assert np.array_equal(ser.frame(3), frames[3])
    assert abs((ser.timestamp(2) - stamps[2]).total_seconds()) < 1e-5
    ser.close()


def test_ser_mono16_big_endian_detected(tmp_path):
    frame = _gradient(dtype=np.uint16, maxv=60000)
    path = str(tmp_path / "be.ser")
    write_ser(path, [frame, frame])
    # Rewrite the pixel data big-endian, as some capture programs do.
    with open(path, "r+b") as fh:
        fh.seek(HEADER_SIZE)
        fh.write(frame.astype(">u2").tobytes() * 2)
    ser = SerFile(path)
    assert ser.byteorder == ">"
    assert np.array_equal(ser.frame(1), frame)


def test_ser_rgb_and_bgr(tmp_path):
    rgb = np.dstack([_gradient(), np.full((40, 60), 100, np.uint8), np.zeros((40, 60), np.uint8)])
    for cid in (COLOR_RGB, COLOR_BGR):
        path = str(tmp_path / f"c{cid}.ser")
        write_ser(path, [rgb], color_id=cid)
        assert np.array_equal(SerFile(path).frame(0), rgb)


def test_ser_truncated_capture(tmp_path):
    path = str(tmp_path / "t.ser")
    write_ser(path, [_gradient()] * 4)
    with open(path, "r+b") as fh:
        fh.truncate(HEADER_SIZE + 40 * 60 * 3 + 10)
    assert len(SerFile(path)) == 3


def test_debayer_rggb_red_square():
    rgb = np.zeros((32, 32, 3), np.uint8)
    rgb[8:24, 8:24, 0] = 200  # red square
    mosaic = np.zeros((32, 32), np.uint8)
    mosaic[0::2, 0::2] = rgb[0::2, 0::2, 0]   # R
    mosaic[0::2, 1::2] = rgb[0::2, 1::2, 1]   # G
    mosaic[1::2, 0::2] = rgb[1::2, 0::2, 1]   # G
    mosaic[1::2, 1::2] = rgb[1::2, 1::2, 2]   # B
    out = debayer(mosaic, "RGGB")
    centre = out[14:18, 14:18].reshape(-1, 3).mean(axis=0)
    assert centre[0] > 150 and centre[1] < 30 and centre[2] < 30


def test_bayer_ser_source_is_colour(tmp_path):
    path = str(tmp_path / "bayer.ser")
    write_ser(path, [_gradient()] * 3, color_id=COLOR_BAYER_RGGB)
    src = open_source(path)
    assert src.is_color and src.bayer == "RGGB"
    assert src.frame(0).shape == (40, 60, 3)


def test_fits_roundtrip(tmp_path):
    mono = _gradient(dtype=np.uint16, maxv=65535)
    write_fits(str(tmp_path / "m.fits"), mono, {"OBJECT": "Jupiter"})
    data, header = read_fits(str(tmp_path / "m.fits"))
    assert data.dtype == np.uint16 and np.array_equal(data, mono)
    assert header["OBJECT"] == "Jupiter"

    col = np.random.default_rng(0).random((20, 30, 3)).astype(np.float32)
    write_fits(str(tmp_path / "c.fit"), col)
    data, _ = read_fits(str(tmp_path / "c.fit"))
    assert data.shape == (20, 30, 3)
    assert np.allclose(data, col)


@pytest.mark.parametrize("ext", [".tif", ".png", ".fits"])
def test_save_and_read_unicode_path(tmp_path, ext):
    folder = tmp_path / "Éclipse été"
    folder.mkdir()
    img = np.random.default_rng(1).random((24, 32, 3)).astype(np.float32)
    path = str(folder / f"résultat{ext}")
    save_image(path, img, bits=16)
    back = read_image(path)
    assert back.shape == img.shape
    assert np.abs(back - img).max() < 1e-4


@pytest.mark.parametrize("dtype", [np.uint8, np.uint16])
def test_read_lzw_tiff_like_registax(tmp_path, dtype):
    import cv2
    rng = np.random.default_rng(2)
    rgb = (rng.random((30, 40, 3)) * np.iinfo(dtype).max).astype(dtype)
    path = tmp_path / "Mak2P1006397_pipp.tif"
    ok, buf = cv2.imencode(".tif", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
                           [cv2.IMWRITE_TIFF_COMPRESSION, 5])  # 5 = LZW
    assert ok
    buf.tofile(str(path))
    back = read_image(str(path))
    assert back.shape == (30, 40, 3)
    assert np.allclose(back, rgb / np.iinfo(dtype).max, atol=1e-6)


def test_image_sequence_natural_order(tmp_path):
    for i in (1, 2, 10):
        save_image(str(tmp_path / f"img{i}.png"), np.full((8, 8), i / 20, np.float32), bits=8)
    src = open_source([str(tmp_path / f) for f in os.listdir(tmp_path)])
    assert [os.path.basename(p) for p in src.paths] == ["img1.png", "img2.png", "img10.png"]
    assert not src.is_color
