import os
import time

import pytest

from planstax.batch import BatchOptions, is_done, list_videos, output_paths, process_video
from planstax.cli import main as cli_main
from planstax.io import read_image
from planstax.settings import Settings
from planstax.synth import write_demo_ser


@pytest.fixture
def folders(tmp_path):
    inp, out = tmp_path / "input", tmp_path / "output"
    inp.mkdir()
    write_demo_ser(str(inp / "jupiter_10.ser"), n=12, size=120, color=True)
    write_demo_ser(str(inp / "jupiter_2.ser"), n=12, size=120)
    (inp / "notes.txt").write_text("pas une vidéo")
    (inp / "abimée.ser").write_bytes(b"LUCAM-RECORDER" + b"\0" * 20)  # truncated header
    return str(inp), str(out)


def test_list_videos_natural_order(folders):
    inp, _ = folders
    assert [os.path.basename(p) for p in list_videos(inp)] == ["abimée.ser", "jupiter_2.ser",
                                                              "jupiter_10.ser"]
    assert list_videos(os.path.join(inp, "absent")) == []


def test_process_video_outputs_and_skip(folders):
    inp, out = folders
    video = os.path.join(inp, "jupiter_10.ser")
    opts = BatchOptions(save_raw=True, fmt="png")
    assert not is_done(video, out, opts)
    r = process_video(video, Settings(), out, opts, workers=2)
    assert sorted(os.path.basename(p) for p in r.outputs) == ["jupiter_10.png", "jupiter_10_brut.png"]
    assert r.frames == 12 and 0 < r.stacked <= 12
    assert read_image(output_paths(video, out, opts)["final"]).shape == (120, 120, 3)
    assert is_done(video, out, opts)
    assert not is_done(video, out, BatchOptions(fmt="tif"))  # another format is not done yet


def test_cli_batch_continues_after_a_bad_video_and_skips_done(folders):
    inp, out = folders
    assert cli_main(["batch", inp, out, "--workers", "2"]) == 1  # one video is damaged
    produced = sorted(os.listdir(out))
    assert produced == ["jupiter_10.tif", "jupiter_2.tif"]
    stamp = os.path.getmtime(os.path.join(out, "jupiter_2.tif"))
    time.sleep(0.05)
    os.remove(os.path.join(inp, "abimée.ser"))
    assert cli_main(["batch", inp, out]) == 0  # nothing left to do
    assert os.path.getmtime(os.path.join(out, "jupiter_2.tif")) == stamp


def test_batch_dialog(folders, tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtCore import QSettings
    from planstax.gui.batch import COL_STATE, BatchDialog

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    inp, out = folders
    qs = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    qs.setValue("batch/input", inp)
    qs.setValue("batch/output", out)
    dlg = BatchDialog(lambda: Settings(), qs)
    dlg.show()
    assert dlg.table.rowCount() == 3 and dlg.start_btn.isEnabled()
    dlg.start()
    end = time.time() + 120
    while dlg.worker is not None and time.time() < end:
        app.processEvents()
        time.sleep(0.02)
    states = [dlg.table.item(r, COL_STATE).text() for r in range(3)]
    assert states[0].startswith("✗") and states[1].startswith("✓") and states[2].startswith("✓")
    assert sorted(os.listdir(out)) == ["jupiter_10.tif", "jupiter_2.tif"]
    assert "2 image(s)" in dlg.summary.text() and "1 vidéo(s) en erreur" in dlg.summary.text()
    dlg.refresh()
    assert [dlg.table.item(r, COL_STATE).text() for r in (1, 2)] == ["Déjà traitée"] * 2
    dlg.reject()
    assert QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat).value("batch/input") == inp
