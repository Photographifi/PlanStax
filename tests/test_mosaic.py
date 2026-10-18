import os
import shutil
import time

import cv2
import numpy as np
import pytest
import tifffile

from planstax.batch import list_images, make_mosaics, mosaic_paths
from planstax.cli import main as cli_main
from planstax.core import mosaic as mz
from planstax.core.mosaic import plan_mosaic, render_mosaic
from planstax.io import read_image, save_image
from planstax.io.images import read_raw
from planstax.io.ser import COLOR_MONO, write_ser
from planstax.synth import cut_tiles, make_moon, make_planet, make_sequence


@pytest.fixture(scope="module")
def moon():
    scene = make_moon(1000, 1000, seed=5)
    tiles, truths = cut_tiles(scene, 460, 270, seed=2)  # 3 × 3 fields, 40 % overlap
    return scene, tiles, truths


def _write(folder, tiles, name="lune"):
    paths = []
    for k, tile in enumerate(tiles):
        path = os.path.join(str(folder), f"{name}_{k + 1}.tif")
        save_image(path, tile)
        paths.append(path)
    return paths


def test_mosaic_places_every_field(tmp_path, moon):
    scene, tiles, truths = moon
    plan = plan_mosaic(_write(tmp_path, tiles))
    assert len(plan.groups) == 1 and sorted(plan.groups[0].indices) == list(range(9))
    assert not plan.isolated and not plan.duplicates and not plan.excluded
    g = plan.groups[0]
    # Each field, where it lies, must agree with a single scene → mosaic similarity.
    pts = np.array([[x, y] for x in range(20, 460, 70) for y in range(20, 460, 70)], float)
    scene_pts = np.vstack([mz._apply(truths[i], pts) for i in g.indices])
    mosaic_pts = np.vstack([mz._apply(m, pts) for m in g.matrices])
    common, _ = cv2.estimateAffinePartial2D(scene_pts.astype(np.float32), mosaic_pts.astype(np.float32),
                                            method=cv2.LMEDS)
    err = np.linalg.norm(mz._apply(common, scene_pts) - mosaic_pts, axis=1)
    assert err.max() < 0.5 and err.mean() < 0.15
    assert g.rms < 1.0

    out = str(tmp_path / "mosaique.tif")
    preview = render_mosaic(g, out)
    mosaic = read_image(out)
    assert mosaic.shape == (g.height, g.width) and preview.ndim == 2
    ref = cv2.warpAffine(scene, mz._compose(g.matrices[0], mz._invert(truths[g.indices[0]])),
                         (g.width, g.height), flags=cv2.INTER_CUBIC)
    lit = (mosaic > 0.05) & (ref > 0.05)
    gain = float(np.median(mosaic[lit] / ref[lit]))
    err = np.abs(mosaic - ref * gain)[lit]
    assert 0.85 < gain < 1.15
    assert err.mean() < 0.01 and np.percentile(err, 99) < 0.04  # brightness equalised, no seams


def test_bands_and_tiled_tiff_give_the_same_mosaic(tmp_path, moon, monkeypatch):
    _, tiles, _ = moon
    plan = plan_mosaic(_write(tmp_path, [tiles[k] for k in (0, 1, 3, 4)]))
    g = plan.groups[0]
    whole = str(tmp_path / "entiere.tif")
    render_mosaic(g, whole)
    monkeypatch.setattr(mz, "BAND_BYTES", 1)          # bands of 256 rows
    monkeypatch.setattr(mz, "IN_MEMORY_PIXELS", 0)    # written tile by tile
    banded = str(tmp_path / "bandes.tif")
    render_mosaic(g, banded)
    with tifffile.TiffFile(banded) as tif:
        assert tif.pages[0].is_tiled
    a, b = read_raw(whole).astype(int), read_raw(banded).astype(int)
    assert a.shape == b.shape and np.abs(a - b).max() <= 2


def test_cancelled_mosaic_keeps_the_previous_one(tmp_path, moon, monkeypatch):
    import threading
    from planstax.core import Cancelled
    _, tiles, _ = moon
    g = plan_mosaic(_write(tmp_path, tiles[:2])).groups[0]
    out = tmp_path / "mosaique.tif"
    out.write_bytes(b"mosaique d'hier")
    monkeypatch.setattr(mz, "BAND_BYTES", 1)
    monkeypatch.setattr(mz, "IN_MEMORY_PIXELS", 0)
    stop = threading.Event()
    with pytest.raises(Cancelled):
        render_mosaic(g, str(out), progress=lambda f, m: stop.set(), cancel=stop)
    assert out.read_bytes() == b"mosaique d'hier"
    assert sorted(os.listdir(tmp_path)) == ["lune_1.tif", "lune_2.tif", "mosaique.tif"]


def test_mosaic_groups_isolated_duplicates(tmp_path, moon):
    _, tiles, _ = moon
    others, _ = cut_tiles(make_moon(700, 700, seed=11, limb=False), 460, 240, seed=4)
    paths = _write(tmp_path, [tiles[0], tiles[1]], "a") + _write(tmp_path, [others[0], others[1]], "b")
    planet = str(tmp_path / "planete.png")
    save_image(planet, make_planet(256))
    copy = str(tmp_path / "copie.tif")
    shutil.copy(paths[0], copy)
    broken = str(tmp_path / "abimee.tif")
    with open(broken, "wb") as fh:
        fh.write(b"II*\0pas une image")
    plan = plan_mosaic(paths + [planet, copy, broken])
    assert [sorted(g.indices) for g in plan.groups] == [[0, 1], [2, 3]]
    assert plan.isolated == [4]
    assert plan.duplicates == [(5, 0)]
    assert [k for k, _ in plan.excluded] == [6]
    assert plan.state(0) == "Mosaïque 1" and plan.state(3) == "Mosaïque 2"
    text = plan.explain()
    assert "Mosaïque 2 : 2 images" in text and "planete.png" in text and "copie.tif (comme a_1.tif)" in text
    result = make_mosaics(plan.paths, str(tmp_path / "sortie"), "png", 8)
    assert [os.path.basename(p) for p in result.outputs] == ["mosaique_1.png", "mosaique_2.png"]
    assert all(os.path.isfile(p) for p in result.outputs)


def test_list_images_and_mosaic_names(tmp_path):
    for name in ("lune_2.tif", "lune_10.tif", "lune_2_brut.tif", "mosaique.tif", "mosaique_1_brut.tif",
                 "Mosaique_brut.png", "mosaique_lune.tif", "notes.txt"):
        (tmp_path / name).write_bytes(b"")
    names = lambda paths: [os.path.basename(p) for p in paths]  # noqa: E731
    assert names(list_images(str(tmp_path))) == ["lune_2.tif", "lune_10.tif", "mosaique_lune.tif"]
    assert names(list_images(str(tmp_path), raw=True)) == ["lune_2_brut.tif"]
    assert list_images(str(tmp_path / "absent")) == []
    assert mosaic_paths("o", 1) == [os.path.join("o", "mosaique.tif")]
    assert mosaic_paths("o", 2, "png", suffix="_brut") == [os.path.join("o", "mosaique_1_brut.png"),
                                                           os.path.join("o", "mosaique_2_brut.png")]


def test_plan_needs_two_images(tmp_path, moon):
    _, tiles, _ = moon
    plan = plan_mosaic(_write(tmp_path, tiles[:1]))
    assert not plan.groups and "au moins deux images" in plan.explain()


@pytest.fixture(scope="module")
def moon_videos(tmp_path_factory):
    """Four overlapping fields of the Moon, filmed through a little turbulence."""
    folder = tmp_path_factory.mktemp("lune") / "input"
    folder.mkdir()
    scene = make_moon(640, 640, seed=7, limb=False)
    tiles, _ = cut_tiles(scene, 380, 260, seed=3, noise=0.0)
    for k, tile in enumerate(tiles):
        frames, _, _ = make_sequence(tile, n=8, seed=k, max_shift=2.0, distortion=0.3,
                                     blur=(0.3, 0.8), noise=0.004)
        data = [(np.clip(f, 0, 1) * 65535 + 0.5).astype(np.uint16) for f in frames]
        write_ser(str(folder / f"lune_{k + 1}.ser"), data, color_id=COLOR_MONO)
    return str(folder)


def test_cli_batch_mosaic_then_mosaic_command(tmp_path, moon_videos):
    out = str(tmp_path / "output")
    assert cli_main(["batch", moon_videos, out, "--raw-only", "--mosaic", "--workers", "2"]) == 0
    assert sorted(os.listdir(out)) == ["lune_1_brut.tif", "lune_2_brut.tif", "lune_3_brut.tif",
                                       "lune_4_brut.tif", "mosaique_brut.tif"]
    assert min(read_image(os.path.join(out, "mosaique_brut.tif")).shape) > 500
    target = str(tmp_path / "lune.png")
    assert cli_main(["mosaic", out, "--brut", "-o", target]) == 0
    assert read_image(target).shape == read_image(os.path.join(out, "mosaique_brut.tif")).shape
    assert cli_main(["mosaic", os.path.join(out, "lune_1_brut.tif")]) == 1  # a single image


def test_cli_demo_fields(tmp_path):
    folder = str(tmp_path / "champs lune")
    assert cli_main(["demo", folder, "--mosaic"]) == 0
    assert len(list_images(folder)) == 9
    assert cli_main(["mosaic", folder, "-f", "jpg"]) == 0
    assert os.path.isfile(os.path.join(folder, "mosaique.jpg"))


def _wait(app, dialog, attr="worker", timeout=180):
    end = time.time() + timeout
    while getattr(dialog, attr) is not None and time.time() < end:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()


def test_mosaic_dialog(tmp_path, moon):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtCore import QSettings
    from planstax.gui.mosaic import COL_STATE, MosaicDialog

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _, tiles, _ = moon
    _write(tmp_path, [tiles[k] for k in (0, 1, 3, 4)])
    opened = []
    qs = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    qs.setValue("mosaic/folder", str(tmp_path))
    dlg = MosaicDialog(qs, opened.append)
    dlg.show()
    assert dlg.table.rowCount() == 4 and dlg.start_btn.isEnabled()
    dlg.start()
    _wait(app, dlg)
    assert [dlg.table.item(r, COL_STATE).text() for r in range(4)] == ["Placée"] * 4
    assert os.path.isfile(tmp_path / "mosaique.tif")
    assert dlg.preview.pixmap() is not None and not dlg.preview.pixmap().isNull()
    assert "Mosaïque : 4 images" in dlg.report.toPlainText()
    assert dlg.open_btn.isEnabled()
    dlg._open_result()
    assert opened == [str(tmp_path / "mosaique.tif")]
    dlg.refresh()
    assert dlg.table.rowCount() == 4  # the mosaic itself is not listed


def test_batch_dialog_mosaic(tmp_path, moon_videos):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtCore import QSettings
    from planstax.gui.batch import BatchDialog
    from planstax.settings import Settings

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    out = str(tmp_path / "output")
    qs = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    qs.setValue("batch/input", moon_videos)
    qs.setValue("batch/output", out)
    qs.setValue("batch/mosaic", True)
    dlg = BatchDialog(lambda: Settings(), qs)
    dlg.show()
    assert dlg.mosaic_check.isChecked()
    dlg.start()
    _wait(app, dlg)
    assert os.path.isfile(os.path.join(out, "mosaique.tif"))
    assert "Mosaïque : mosaique.tif (4 images)" in dlg.summary.text()
    assert dlg.mosaic_report.isVisibleTo(dlg) and "4 images" in dlg.mosaic_report.toPlainText()
    # Everything is done: the button stays available to assemble the mosaic again.
    dlg.refresh()
    assert dlg.start_btn.isEnabled()
    dlg.mosaic_check.setChecked(False)
    assert not dlg.start_btn.isEnabled()
    dlg.reject()
