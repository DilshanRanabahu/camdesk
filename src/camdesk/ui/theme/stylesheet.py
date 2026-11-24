"""Builds the app-wide Qt stylesheet (QSS) from the design tokens.

Widgets choose a look with object names / dynamic properties instead of their own colors:
- QPushButton[variant="primary" | "ghost" | "window" | "window-close" | "pill" | "link"]
- QLabel[role="title" | "secondary" | "caption" | "error" | "mono"]
- QFrame#Card, QWidget#TitleBar, QWidget#StatusBar
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from camdesk.ui.theme import tokens as t


def apply(app: QApplication) -> None:
    """Dark palette (for things QSS can't reach, like placeholder text) + the stylesheet."""
    palette = app.palette()
    roles = {
        QPalette.ColorRole.Window: t.BG_BASE,
        QPalette.ColorRole.Base: t.BG_ELEVATED,
        QPalette.ColorRole.Text: t.TEXT_PRIMARY,
        QPalette.ColorRole.WindowText: t.TEXT_PRIMARY,
        QPalette.ColorRole.ButtonText: t.TEXT_PRIMARY,
        QPalette.ColorRole.PlaceholderText: t.TEXT_DISABLED,
        QPalette.ColorRole.Highlight: t.ACCENT,
        QPalette.ColorRole.HighlightedText: t.TEXT_ON_ACCENT,
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    font = QFont(t.FONT_UI)
    font.setFamilies([t.FONT_UI, t.FONT_UI_FALLBACK])
    font.setPixelSize(t.SIZE_BODY)
    app.setFont(font)
    app.setStyleSheet(build())


def build() -> str:
    font = f'"{t.FONT_UI}", "{t.FONT_UI_FALLBACK}"'
    mono = f'"{t.FONT_MONO}", "{t.FONT_MONO_FALLBACK}"'
    return f"""
* {{
    font-family: {font};
    font-size: {t.SIZE_BODY}px;
    color: {t.TEXT_PRIMARY};
    outline: none;
}}
QMainWindow, QWidget#Root, QStackedWidget, QWidget#ConnectPage {{
    background: {t.BG_BASE};
}}
QToolTip {{
    background: {t.BORDER};
    color: {t.TEXT_PRIMARY};
    border: none;
    padding: {t.SPACE_1}px {t.SPACE_2}px;
    font-size: {t.SIZE_LABEL}px;
}}

/* -- title bar & status bar --------------------------------------------- */
QWidget#TitleBar {{
    background: {t.BG_SURFACE};
    border-bottom: 1px solid {t.BORDER};
}}
QWidget#StatusBar {{
    background: {t.BG_SURFACE};
    border-top: 1px solid {t.BORDER};
}}
QWidget#StatusBar QLabel {{
    color: {t.TEXT_SECONDARY};
    font-size: {t.SIZE_CAPTION}px;
}}
QLabel#AppName {{
    font-size: {t.SIZE_TITLE}px;
    font-weight: 600;
}}

/* -- labels ----------------------------------------------------------------- */
QLabel[role="title"] {{ font-size: {t.SIZE_TITLE}px; font-weight: 600; }}
QLabel[role="secondary"] {{ color: {t.TEXT_SECONDARY}; }}
QLabel[role="label"] {{ color: {t.TEXT_SECONDARY}; font-size: {t.SIZE_LABEL}px; font-weight: 500; }}
QLabel[role="caption"] {{ color: {t.TEXT_SECONDARY}; font-size: {t.SIZE_CAPTION}px; }}
QLabel[role="error"] {{ color: {t.DANGER}; font-size: {t.SIZE_LABEL}px; }}
QLabel[role="mono"] {{ font-family: {mono}; font-size: {t.SIZE_MONO}px; }}

/* -- card -------------------------------------------------------------------- */
QFrame#Card {{
    background: {t.BG_SURFACE};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_MD}px;
}}

/* -- inputs -------------------------------------------------------------------- */
QLineEdit {{
    background: {t.BG_ELEVATED};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_SM}px;
    padding: 0 {t.SPACE_3}px;
    min-height: {t.CONTROL_HEIGHT - 2}px;
    selection-background-color: {t.ACCENT};
}}
QLineEdit:hover {{ border-color: {t.BG_HOVER}; }}
QLineEdit:focus {{ border: 2px solid {t.ACCENT}; padding: 0 {t.SPACE_3 - 1}px; }}
QLineEdit[invalid="true"] {{ border: 2px solid {t.DANGER}; padding: 0 {t.SPACE_3 - 1}px; }}

/* -- buttons ------------------------------------------------------------------- */
QPushButton {{
    border: none;
    border-radius: {t.RADIUS_SM}px;
    padding: 0 {t.SPACE_4}px;
    min-height: {t.CONTROL_HEIGHT}px;
    background: transparent;
}}
QPushButton:disabled {{ color: {t.TEXT_DISABLED}; }}
QPushButton[variant="primary"] {{
    background: {t.ACCENT};
    color: {t.TEXT_ON_ACCENT};
    font-weight: 600;
}}
QPushButton[variant="primary"]:hover {{ background: {t.ACCENT_HOVER}; }}
QPushButton[variant="primary"]:pressed {{ background: {t.ACCENT}; padding-top: 1px; }}
QPushButton[variant="ghost"] {{ background: {t.BG_ELEVATED}; }}
QPushButton[variant="ghost"]:hover {{ background: {t.BG_HOVER}; }}
QPushButton[variant="link"] {{
    min-height: 0;
    padding: {t.SPACE_1}px 0;
    color: {t.TEXT_SECONDARY};
    text-align: left;
}}
QPushButton[variant="link"]:hover {{ color: {t.TEXT_PRIMARY}; }}
QPushButton[variant="recent"] {{
    text-align: left;
    padding: 0 {t.SPACE_3}px;
    background: {t.BG_ELEVATED};
}}
QPushButton[variant="recent"]:hover {{ background: {t.BG_HOVER}; }}
QPushButton[variant="icon"] {{
    min-height: 0;
    padding: {t.SPACE_1}px;
    border-radius: {t.RADIUS_SM}px;
}}
QPushButton[variant="icon"]:hover {{ background: {t.BG_HOVER}; }}

/* window buttons: square, full title-bar height */
QPushButton[variant="window"], QPushButton[variant="window-close"] {{
    min-height: {t.TITLEBAR_HEIGHT - 1}px;
    max-height: {t.TITLEBAR_HEIGHT - 1}px;
    min-width: {t.WINDOW_BUTTON_WIDTH}px;
    max-width: {t.WINDOW_BUTTON_WIDTH}px;
    padding: 0;
    border-radius: 0;
}}
QPushButton[variant="window"]:hover {{ background: {t.BG_HOVER}; }}
QPushButton[variant="window-close"]:hover {{ background: {t.DANGER}; }}

/* camera selector pill */
QPushButton[variant="pill"] {{
    background: {t.BG_ELEVATED};
    border: 1px solid {t.BORDER};
    border-radius: {t.CONTROL_HEIGHT // 2 - 4}px;
    min-height: {t.CONTROL_HEIGHT - 8}px;
    max-height: {t.CONTROL_HEIGHT - 8}px;
    padding: 0 {t.SPACE_3}px;
}}
QPushButton[variant="pill"]:hover {{ background: {t.BG_HOVER}; }}

/* -- menus ---------------------------------------------------------------------- */
QMenu {{
    background: {t.BG_ELEVATED};
    border: 1px solid {t.BORDER};
    border-radius: {t.RADIUS_SM}px;
    padding: {t.SPACE_1}px;
}}
QMenu::item {{
    padding: {t.SPACE_2}px {t.SPACE_6}px {t.SPACE_2}px {t.SPACE_3}px;
    border-radius: {t.RADIUS_SM - 2}px;
}}
QMenu::item:selected {{ background: {t.BG_HOVER}; }}
QMenu::item:disabled {{ color: {t.TEXT_DISABLED}; }}
QMenu::separator {{ height: 1px; background: {t.BORDER}; margin: {t.SPACE_1}px {t.SPACE_2}px; }}

/* -- overlays on the video ------------------------------------------------------- */
QWidget#ConnectionOverlay {{ background: transparent; }}
QWidget#ConnectionOverlay[dim="true"] {{ background: {t.DIM_OVERLAY}; }}
QFrame#OverlayPanel {{
    background: {t.BG_OVERLAY};
    border-radius: {t.RADIUS_MD}px;
}}
"""
