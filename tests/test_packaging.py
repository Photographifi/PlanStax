import importlib.util
import os
import stat
import tomllib
import zipfile

from planstax import __version__

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_requirements_match_pyproject():
    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as fh:
        deps = tomllib.load(fh)["project"]["dependencies"]
    with open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8") as fh:
        reqs = [l.strip() for l in fh if l.strip() and not l.startswith("#")]
    assert reqs == deps


def test_linux_archive(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "build_linux_zip", os.path.join(ROOT, "packaging", "build_linux_zip.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = module.build(str(tmp_path))
    assert os.path.basename(path) == f"PlanStax-{__version__}-Linux.zip"
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        assert "PlanStax/planstax/__main__.py" in names
        assert "PlanStax/planstax/resources/planstax.ico" in names
        assert "PlanStax/requirements.txt" in names
        assert not any("__pycache__" in n or ".venv" in n or n.endswith(".lnk") for n in names)
        script = zf.getinfo("PlanStax/planstax.sh")
        assert stat.S_IMODE(script.external_attr >> 16) == 0o755
        data = zf.read(script)
        assert data.startswith(b"#!/usr/bin/env bash\n") and b"\r\n" not in data
        assert __version__ in zf.read("PlanStax/LISEZ-MOI-Linux.txt").decode("utf-8")
