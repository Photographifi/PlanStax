from planstax import settings as st
from planstax.settings import (Settings, import_registax, registax_preset_names,
                                  registax_wavelet_positions)


def test_settings_dict_roundtrip():
    s = Settings()
    s.align.ap_spacing = 42
    s.wavelet.layers[2].gain = 7.5
    s.post.shift_r = (0.5, -1.0)
    back = Settings.from_dict(s.to_dict())
    assert back == s


def test_from_dict_tolerates_unknown_and_missing():
    s = Settings.from_dict({"align": {"ap_spacing": "25", "bogus": 1}, "unknown": {}})
    assert s.align.ap_spacing == 25
    assert s.limit.percent == Settings().limit.percent


def test_presets_saved_in_appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    s = Settings()
    s.limit.percent = 33
    st.save_preset("Mak/2", s)
    assert "Mak_2" in st.list_presets()
    assert st.load_preset("Mak_2").limit.percent == 33
    st.delete_preset("Mak_2")
    assert st.list_presets() == []


def test_settings_taken_over_from_former_name(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    old = tmp_path / "PlanetStack" / "presets"
    old.mkdir(parents=True)
    s = Settings()
    s.limit.percent = 42
    (old / "Mak2.json").write_text(__import__("json").dumps(s.to_dict()), encoding="utf-8")
    assert "Mak2" in st.list_presets()            # copied on first use of the new name
    assert st.load_preset("Mak2").limit.percent == 42
    assert (old / "Mak2.json").exists()           # the former folder is kept as a backup


def test_import_registax_files(tmp_path):
    (tmp_path / "registax6.ini").write_text("[Form]\nblocksize_Value=35\n", encoding="latin-1")
    (tmp_path / "estimate-Mak2.ini").write_text(
        "[ESTIMATE]\nDist_Value=30\nLowIntensity_Value=30\nHighIntensity_Value=230\n"
        "MatrixEdgesetting_Value=20\nNoOfPoints_Value=500\n", encoding="latin-1")
    (tmp_path / "limit-Mak2.ini").write_text("[LIMIT]\nLimitNoOfFrames_Value=80\n", encoding="latin-1")
    (tmp_path / "wavelet-Mak2.ini").write_text(
        "[WAVELET]\nWaveletscheme_ItemIndex=1\nLayer1Slider_Position=10\nLayer2slider_Position=10\n"
        "Layer3slider_Position=200\nlayer4slider_Position=400\nLayer5slider_Position=600\n"
        "Layer6slider_Position=400\nBlurLayer1_Value=0\n", encoding="latin-1")
    (tmp_path / "macro-Mak2.ini").write_text("Estimate-Mak2\nAlign-Mak2\n", encoding="latin-1")

    assert registax_preset_names(str(tmp_path)) == ["Mak2"]
    s = import_registax(str(tmp_path), "Mak2")
    assert s.align.ap_box_size == 35 and s.align.ap_spacing == 30
    assert s.align.min_brightness == 30 and s.align.max_brightness == 230
    assert s.limit.percent == 80
    assert s.wavelet.scheme == "gaussian"
    # Gains are not convertible: they stay neutral, the original positions are reported.
    assert all(l.gain == 1.0 for l in s.wavelet.layers)
    assert registax_wavelet_positions(str(tmp_path), "Mak2") == [10, 10, 200, 400, 600, 400]

    # A macro-only set borrows the other steps from the sets its macro names.
    (tmp_path / "wavelet-Mak3.ini").write_text(
        "[WAVELET]\nLayer1Slider_Position=80\n", encoding="latin-1")
    (tmp_path / "macro-Mak3.ini").write_text(  # RegiStax writes macros in UTF-16 with a BOM
        "Estimate-Mak2\r\nLimit0-Mak2\r\nWavelet-Mak3\r\n", encoding="utf-16")
    assert registax_preset_names(str(tmp_path)) == ["Mak2", "Mak3"]
    s3 = import_registax(str(tmp_path), "Mak3")
    assert s3.align.max_brightness == 230 and s3.limit.percent == 80
