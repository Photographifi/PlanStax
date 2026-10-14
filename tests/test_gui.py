import os
import time

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    from planstax.gui.mainwindow import MainWindow
    win = MainWindow()
    win.show()
    yield win
    win.close()


def _wait(app, win, extra=0.3):
    end = time.time() + 120
    while win._busy() and time.time() < end:
        app.processEvents()
        time.sleep(0.01)
    end = time.time() + extra
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def test_full_workflow(app, window, tmp_path):
    from planstax.synth import write_demo_ser
    demo = str(tmp_path / "démo.ser")
    write_demo_ser(demo, n=40, size=200, color=True)
    win = window
    win.load_source(demo)
    assert win.pipeline is not None and win.frame_spin.value() == 1

    win.place_points()
    _wait(app, win)
    assert len(win.pipeline.points) > 0
    n = len(win.pipeline.points)
    win._add_point(100, 100)
    win._remove_point(100, 100)
    assert len(win.pipeline.points) == n

    win.do_all()
    _wait(app, win)
    assert win.stacked is not None and win.stacked.shape == (200, 200, 3)
    assert "images empilées" in win.stack_label.text()

    win.layer_gain[0].spin.setValue(3.0)
    _wait(app, win, extra=1.0)
    assert win.final is not None
    assert np.abs(win.final - win.stacked).max() > 0.01

    # Selection follows the plot click.
    win._on_plot_cutoff(0.25)
    assert abs(win.settings.limit.percent - 25.0) < 0.1
    assert len(win.pipeline.selected) == 10


def test_settings_persist_between_sessions(app, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    from planstax.gui.mainwindow import MainWindow
    win = MainWindow()
    win.ap_spacing.setValue(44)
    win.close()
    win2 = MainWindow()
    assert win2.settings.align.ap_spacing == 44 and win2.ap_spacing.value() == 44
    win2.close()
