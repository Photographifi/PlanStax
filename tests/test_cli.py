import os

from planstax.__main__ import CLI_COMMANDS
from planstax.cli import build_parser, main
from planstax.io import read_image
from planstax.synth import write_demo_ser


def test_every_command_is_routed_to_the_cli():
    sub = next(a for a in build_parser()._actions if a.dest == "command")
    assert set(sub.choices) <= CLI_COMMANDS  # otherwise `python -m planstax <command>` opens the GUI


def test_language_option_before_the_command(tmp_path, monkeypatch, capsys):
    import sys

    from planstax import __main__ as entry
    from planstax.gui import app
    monkeypatch.setenv("PLANSTAX_LANG", "fr")  # given back after the test
    monkeypatch.setattr(sys, "argv", ["planstax", "--lang", "en", "demo", str(tmp_path / "a.ser")])
    assert entry.main() == 0
    assert "Demo video written" in capsys.readouterr().out
    opened = []
    monkeypatch.setattr(app, "main", lambda argv: opened.append((argv, os.environ["PLANSTAX_LANG"])) or 0)
    monkeypatch.setattr(sys, "argv", ["planstax", "--lang=es", "video.ser"])
    assert entry.main() == 0
    assert opened == [(["planstax", "video.ser"], "es")]


def test_cli_stack_into_new_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    demo = str(tmp_path / "jupiter.ser")
    write_demo_ser(demo, n=20, size=160)
    out = tmp_path / "résultats"
    assert main(["stack", demo, "-o", str(out), "--wavelets", "--workers", "2"]) == 0
    assert sorted(os.listdir(out)) == ["jupiter_ondelettes.tif", "jupiter_stack.tif"]
    assert read_image(str(out / "jupiter_stack.tif")).shape == (160, 160)


def test_cli_explicit_file_and_wavelets_sibling(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    demo = str(tmp_path / "mars.ser")
    write_demo_ser(demo, n=12, size=120)
    target = tmp_path / "final.png"
    assert main(["stack", demo, "-o", str(target), "--wavelets"]) == 0
    assert target.exists() and (tmp_path / "final_ondelettes.png").exists()
    # Batch over several files with a wildcard.
    write_demo_ser(str(tmp_path / "mars2.ser"), n=12, size=120)
    assert main(["stack", str(tmp_path / "mars*.ser"), "-o", str(tmp_path / "lot")]) == 0
    assert sorted(os.listdir(tmp_path / "lot")) == ["mars2_stack.tif", "mars_stack.tif"]
