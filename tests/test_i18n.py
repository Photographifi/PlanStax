import os
import string
import sys

import pytest

from planstax import i18n
from planstax.locales.catalog import TRANSLATIONS

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "packaging"))
from extract_texts import texts  # noqa: E402


def _fields(text):
    return sorted(f for _, f, _, _ in string.Formatter().parse(text) if f is not None)


def test_every_text_is_translated_with_the_same_placeholders():
    code = {t for t, _, _ in texts()}
    assert len(code) > 300
    assert sorted(code - set(TRANSLATIONS)) == []          # extract_texts.py --missing lists them
    assert sorted(set(TRANSLATIONS) - code) == []          # translations of texts no longer used
    for fr, translated in TRANSLATIONS.items():
        assert len(translated) == 2 and all(translated), fr
        for text in translated:
            assert _fields(text) == _fields(fr), (fr, text)


def test_language_choice(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert i18n.set_language("en") == "en" and i18n.tr("Empilement") == "Stacking"
    assert i18n.tr("{n} images", n=3) == "3 images"
    assert i18n.number(12345.67, 1) == "12,345.7" and i18n.megabytes(5 * 2 ** 20) == "5 MB"
    assert i18n.set_language("es") == "es" and i18n.tr("Empilement") == "Apilado"
    assert i18n.number(12345.67, 1) == "12 345,7"
    assert i18n.set_language("fr") == "fr" and i18n.tr("Empilement") == "Empilement"
    assert i18n.number(0.5, 1) == "0,5" and i18n.megabytes(1000) == "< 1 Mo"
    assert i18n.tr("Texte inconnu {x}", x=1) == "Texte inconnu 1"   # not translated: stays French
    assert i18n.set_language("de") == i18n.FALLBACK
    # Automatic: the variable, then the choice saved from the menu, then the system.
    monkeypatch.delenv("PLANSTAX_LANG")
    monkeypatch.setattr(i18n, "system_language", lambda: "es")
    assert i18n.set_language() == "es"
    os.makedirs(tmp_path / "PlanStax", exist_ok=True)
    (tmp_path / "PlanStax" / "interface.ini").write_text("[General]\nlanguage=en\n", encoding="utf-8")
    from planstax.settings import config_dir
    if os.path.normcase(config_dir()) == os.path.normcase(str(tmp_path / "PlanStax")):
        assert i18n.saved_language() == "en" and i18n.set_language() == "en"
    monkeypatch.setenv("PLANSTAX_LANG", "fr")
    assert i18n.set_language() == "fr"


@pytest.mark.parametrize("code", ["fr", "en", "es"])
def test_system_language_names(monkeypatch, code):
    names = {"fr": "fr_FR.UTF-8", "en": "en_GB", "es": "es_ES"}
    assert i18n._code(names[code]) == code
    assert i18n._code({"fr": "French_France", "en": "English_United States", "es": "Spanish_Spain"}[code]) == code
    assert i18n._code("de_DE") is None


def test_cli_language_option(tmp_path, capsys):
    from planstax.cli import main
    assert main(["--lang", "en", "demo", str(tmp_path / "a.ser")]) == 0
    assert "Demo video written" in capsys.readouterr().out
    assert main(["--lang=es", "demo", str(tmp_path / "b.ser")]) == 0
    assert "Vídeo de demostración escrito" in capsys.readouterr().out
    assert main(["demo", str(tmp_path / "c.ser")]) == 0          # PLANSTAX_LANG=fr (conftest)
    assert "Vidéo de démonstration écrite" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["--lang", "en", "--help"])
    assert "align and stack videos" in capsys.readouterr().out


def test_windows_in_each_language(monkeypatch, tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from planstax.gui import mainwindow
    from planstax.gui.batch import BatchDialog
    from planstax.gui.mosaic import MosaicDialog
    expected = {"fr": ("&Fichier", "5 · Finitions", "Rotation fine :", "Traitement par lot", "Assembler"),
                "en": ("&File", "5 · Finishing", "Fine rotation:", "Batch processing", "Assemble"),
                "es": ("&Archivo", "5 · Acabado", "Rotación fina:", "Procesamiento por lotes", "Montar")}
    for code, (menu, tab, label, batch, assemble) in expected.items():
        i18n.set_language(code)
        win = mainwindow.MainWindow()
        assert menu in [a.text() for a in win.menuBar().actions()]
        assert tab in [win.tabs.tabText(k) for k in range(win.tabs.count())]
        labels = [w.text() for w in win.findChildren(QtWidgets.QLabel)]
        assert label in labels
        dlg = BatchDialog(lambda: win.settings, win.qsettings, win)
        assert dlg.windowTitle() == batch
        mos = MosaicDialog(win.qsettings, win.load_image, lambda: win.settings, win)
        assert assemble in [b.text() for b in mos.findChildren(QtWidgets.QPushButton)]
        dlg.close()
        mos.close()
        win.close()
    app.processEvents()


def test_language_menu_saves_the_choice(monkeypatch, tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from planstax.gui import mainwindow
    shown = []
    monkeypatch.setattr(mainwindow.QMessageBox, "information", lambda parent, title, text: shown.append(text))
    win = mainwindow.MainWindow()
    win._set_language("es")
    assert win.language_actions["es"].isChecked() and not win.language_actions[None].isChecked()
    assert shown[-1] == "Reinicie PlanStax para cambiar de idioma.\n\nRedémarrez PlanStax pour changer de langue."
    assert i18n.language() == "fr"            # the window keeps its language until the next start
    assert i18n.saved_language() == "es"
    win._set_language(None)
    assert i18n.saved_language() is None and win.language_actions[None].isChecked()
    win.close()
