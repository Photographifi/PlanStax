"""Colour themes: dark (default), light, and a red night mode that preserves dark adaptation."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

_THEMES = {
    "dark": dict(window="#232428", base="#1a1b1e", alt="#26272b", text="#e6e6e6", button="#2e3035",
                 highlight="#3d7fd9", hl_text="#ffffff", mid="#8a8d93", accent="#3d7fd9"),
    "light": dict(window="#f2f2f4", base="#ffffff", alt="#f5f5f7", text="#1e1e1e", button="#e6e6ea",
                  highlight="#2f6fd0", hl_text="#ffffff", mid="#6d6f75", accent="#2f6fd0"),
    "night": dict(window="#120000", base="#0b0000", alt="#160000", text="#d23a2a", button="#1e0303",
                  highlight="#7a0d05", hl_text="#ff6a50", mid="#7a2a20", accent="#8a1206"),
}


def apply(app: QApplication, key: str) -> None:
    t = _THEMES.get(str(key), _THEMES["dark"])
    app.setStyle("Fusion")
    pal = QPalette()
    c = {k: QColor(v) for k, v in t.items()}
    pal.setColor(QPalette.ColorRole.Window, c["window"])
    pal.setColor(QPalette.ColorRole.WindowText, c["text"])
    pal.setColor(QPalette.ColorRole.Base, c["base"])
    pal.setColor(QPalette.ColorRole.AlternateBase, c["alt"])
    pal.setColor(QPalette.ColorRole.Text, c["text"])
    pal.setColor(QPalette.ColorRole.Button, c["button"])
    pal.setColor(QPalette.ColorRole.ButtonText, c["text"])
    pal.setColor(QPalette.ColorRole.Highlight, c["highlight"])
    pal.setColor(QPalette.ColorRole.HighlightedText, c["hl_text"])
    pal.setColor(QPalette.ColorRole.ToolTipBase, c["base"])
    pal.setColor(QPalette.ColorRole.ToolTipText, c["text"])
    pal.setColor(QPalette.ColorRole.Mid, c["mid"])
    pal.setColor(QPalette.ColorRole.PlaceholderText, c["mid"])
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, c["mid"])
    app.setPalette(pal)
    app.setStyleSheet(f"""
        QPushButton#primary, QToolButton#primary {{
            background: {t['accent']}; color: {t['hl_text']}; font-weight: 600;
            border: none; border-radius: 4px; padding: 6px 14px;
        }}
        QPushButton#primary:disabled, QToolButton#primary:disabled {{
            background: {t['button']}; color: {t['mid']};
        }}
        QGroupBox {{ font-weight: 600; margin-top: 10px; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 6px; padding: 0 3px; }}
        QGroupBox QLabel, QGroupBox QCheckBox {{ font-weight: normal; }}
        QTabBar::tab {{ padding: 6px 10px; }}
    """)
