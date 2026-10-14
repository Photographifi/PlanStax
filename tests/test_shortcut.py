import os
import sys

from planstax.gui import shortcut


def test_icon_is_shipped_with_the_package():
    assert os.path.isfile(shortcut.ICON)


def test_launch_command_portable(monkeypatch, tmp_path):
    exe = str(tmp_path / "PlanStax.exe")
    monkeypatch.setattr(sys, "executable", exe)
    assert shortcut.launch_command() == (exe, "", str(tmp_path))


def test_launch_command_development(monkeypatch, tmp_path):
    (tmp_path / "pythonw.exe").write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))
    target, args, workdir = shortcut.launch_command()
    assert target == str(tmp_path / "pythonw.exe")
    assert args == "-m planstax"
    assert os.path.isdir(os.path.join(workdir, "planstax"))
