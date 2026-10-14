import os

from planstax.cli import main
from planstax.io import read_image
from planstax.synth import write_demo_ser


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
