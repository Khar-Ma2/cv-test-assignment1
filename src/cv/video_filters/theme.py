"""Темна тема: токени кольору + QSS."""

from PySide6.QtGui import QColor

TOKENS = {
    "bg": "#0e1116",
    "surface": "#161a22",
    "surface2": "#1d222c",
    "surface3": "#262c38",
    "border": "#2a303c",
    "text": "#e7eaf0",
    "muted": "#8a93a6",
    "accent": "#5b9dff",
    "accent_hover": "#7ab0ff",
    "accent_pressed": "#4684e6",
    "on_accent": "#0b1220",
    "danger": "#ff5c66",
    "danger_hover": "#ff7a82",
    "ok": "#4ade80",
}


def color(name: str) -> QColor:
    return QColor(TOKENS[name])


def stylesheet() -> str:
    t = TOKENS
    return f"""
* {{ font-size: 13px; }}
QMainWindow, QWidget#root {{ background: {t["bg"]}; }}
QWidget {{ color: {t["text"]}; }}
QLabel {{ background: transparent; }}

/* картки */
QFrame#card {{
    background: {t["surface"]};
    border: 1px solid {t["border"]};
    border-radius: 14px;
}}
QLabel#cardTitle {{
    color: {t["muted"]};
    font-size: 11px;
    font-weight: 600;
}}
QLabel#hint {{ color: {t["muted"]}; font-size: 12px; }}

/* сегментовані перемикачі */
QPushButton[seg="true"] {{
    background: {t["surface2"]};
    color: {t["muted"]};
    border: 1px solid {t["border"]};
    padding: 8px 10px;
    border-radius: 0px;
}}
QPushButton[seg="true"][pos="first"] {{
    border-top-left-radius: 9px; border-bottom-left-radius: 9px;
}}
QPushButton[seg="true"][pos="last"] {{
    border-top-right-radius: 9px; border-bottom-right-radius: 9px;
    border-left: none;
}}
QPushButton[seg="true"][pos="mid"] {{ border-left: none; }}
QPushButton[seg="true"]:hover:!checked {{ background: {t["surface3"]}; color: {t["text"]}; }}
QPushButton[seg="true"]:checked {{
    background: {t["accent"]};
    color: {t["on_accent"]};
    border-color: {t["accent"]};
    font-weight: 600;
}}
QPushButton[seg="true"]:disabled {{ color: #4b5263; background: {t["surface"]}; }}
QPushButton[seg="true"]:checked:disabled {{ background: #34486b; color: #7f8aa3; }}

/* кнопки дій */
QPushButton {{
    background: {t["surface2"]};
    border: 1px solid {t["border"]};
    border-radius: 10px;
    padding: 9px 14px;
}}
QPushButton:hover {{ background: {t["surface3"]}; }}
QPushButton:pressed {{ background: {t["border"]}; }}
QPushButton#step {{
    font-size: 20px; font-weight: 600; padding: 0px; min-width: 38px; max-width: 38px;
    min-height: 38px; max-height: 38px; border-radius: 19px;
}}
QPushButton#record[recording="true"] {{
    background: {t["danger"]}; color: white; border-color: {t["danger"]}; font-weight: 600;
}}
QPushButton#record[recording="true"]:hover {{ background: {t["danger_hover"]}; }}

/* слайдери */
QSlider::groove:horizontal {{ height: 6px; background: {t["surface3"]}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {t["accent"]}; border-radius: 3px; }}
QSlider::handle:horizontal {{
    width: 16px; height: 16px; margin: -7px 0; border-radius: 9px;
    background: white; border: 3px solid {t["accent"]};
}}
QSlider::handle:horizontal:hover {{ border-color: {t["accent_hover"]}; }}
QSlider::handle:horizontal:disabled {{ background: #6b7385; border-color: #3a4560; }}
QSlider::sub-page:horizontal:disabled {{ background: #3a4560; }}

/* випадний список */
QComboBox {{
    background: {t["surface2"]};
    border: 1px solid {t["border"]};
    border-radius: 10px;
    padding: 8px 12px;
}}
QComboBox:hover {{ border-color: {t["accent"]}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{
    background: {t["surface2"]};
    border: 1px solid {t["border"]};
    selection-background-color: {t["accent"]};
    selection-color: {t["on_accent"]};
    outline: none;
    padding: 4px;
}}

/* бейдж розміру вікна й «кейкапи» */
QLabel#sizeBadge {{ font-size: 34px; font-weight: 700; color: {t["text"]}; }}
QLabel#keycap {{
    background: {t["surface2"]};
    border: 1px solid {t["border"]};
    border-bottom: 3px solid {t["border"]};
    border-radius: 7px;
    padding: 2px 10px;
    font-family: monospace;
    font-weight: 700;
    color: {t["text"]};
}}

/* смуга прокрутки */
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {t["surface3"]}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #3a4252; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

QLabel#stats {{ color: {t["muted"]}; font-size: 12px; }}
QToolTip {{
    background: {t["surface3"]}; color: {t["text"]}; border: 1px solid {t["border"]};
    padding: 5px 8px;
}}
"""
