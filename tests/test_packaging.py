import importlib.util
import os
import stat
import sys
import tomllib
import zipfile

import pytest

from planstax import __version__
from planstax import settings as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_requirements_match_pyproject():
    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as fh:
        deps = tomllib.load(fh)["project"]["dependencies"]
    with open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8") as fh:
        reqs = [l.strip() for l in fh if l.strip() and not l.startswith("#")]
    assert reqs == deps


@pytest.mark.parametrize("target, launcher, readme", [
    ("Linux", "planstax.sh", "LISEZ-MOI-Linux.txt"),
    ("Mac", "PlanStax.command", "LISEZ-MOI-Mac.txt"),
])
def test_source_archive(tmp_path, target, launcher, readme):
    spec = importlib.util.spec_from_file_location(
        "build_source_zips", os.path.join(ROOT, "packaging", "build_source_zips.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = module.build(str(tmp_path), target)
    assert os.path.basename(path) == f"PlanStax-{__version__}-{target}.zip"
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        assert "PlanStax/planstax/__main__.py" in names
        assert "PlanStax/planstax/resources/planstax.ico" in names
        assert "PlanStax/requirements.txt" in names
        assert not any("__pycache__" in n or ".venv" in n or n.endswith(".lnk") for n in names)
        script = zf.getinfo(f"PlanStax/{launcher}")
        assert stat.S_IMODE(script.external_attr >> 16) == 0o755
        data = zf.read(script)
        assert data.startswith(b"#!/") and b"\r\n" not in data
        assert __version__ in zf.read(f"PlanStax/{readme}").decode("utf-8")


def test_settings_folder_per_platform(tmp_path, monkeypatch):
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "darwin")
    assert st.config_dir() == os.path.join(str(tmp_path), "Library", "Application Support", "PlanStax")
    monkeypatch.setattr(sys, "platform", "linux")
    assert st.config_dir() == os.path.join(str(tmp_path), ".config", "PlanStax")


def test_debayer_with_older_opencv_names(monkeypatch):
    import cv2
    import numpy as np
    from planstax.io.sources import debayer
    mosaic = (np.arange(64 * 64, dtype=np.uint16).reshape(64, 64) % 4096).astype(np.uint16)
    expected = debayer(mosaic, "RGGB")
    for name in ("COLOR_BayerRGGB2RGB", "COLOR_BayerRGGB2RGB_EA"):  # absent from OpenCV 4.x
        monkeypatch.delattr(cv2, name, raising=False)
    assert np.array_equal(debayer(mosaic, "RGGB"), expected)
