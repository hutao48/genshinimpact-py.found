# -*- coding: utf-8 -*-
"""原神乐器演奏检测器 —— PySide6 界面（深色卡片式主题）

布局：顶栏（标题 / 监听状态 / 操作按钮）→ 设置条 → [琴键 | 实时指标] → BPM 变化图 → 每个音的时长表。
三块区域之间的分隔条可上下拖动；窗口缩放时琴键、指标字号、图表和表格都随之自适应。
BPM 每 0.5 s 记录一个点（最多保留 4 小时），图表可切换显示最近 30 秒 / 1 分钟 / 5 分钟 / 全部，
纵轴按当前显示的数据自动缩放；时长表最多保留 20000 条；两者都可以导出为 CSV。
"""
import bisect
import csv
import math
import os
import sys
import time

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QAbstractTableModel, QModelIndex, QRectF, QSize, QUrl, QProcess, QPointF, QByteArray
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QFontMetrics, QIcon, QPainter, QPen, QBrush,
    QLinearGradient, QDesktopServices, QPixmap, QPainterPath, QImage,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QSpinBox, QSlider, QTableView, QHeaderView,
    QFrame, QSplitter, QMessageBox, QSizePolicy, QButtonGroup, QFileDialog,
    QAbstractItemView, QStackedWidget, QDialog, QGroupBox, QCheckBox,
    QProgressDialog,
)

import pyqtgraph as pg

import settings
import i18n
from i18n import T
from updater import UpdateChecker, UpdateDownloader, valid_release_url
from instruments import all_instruments, midi_to_name, midi_to_solfege, DIATONIC_OFFSETS
from detection import NoteDetector, end_reason_text
from screening import (
    Screener, LEVEL_LIMIT, LEVEL_SUSPECT, level_text, kind_text,
)
from audio_capture import AudioCapture, list_sources, default_loopback_id
from app_version import APP_NAME, APP_VERSION, APP_URL, APP_REPO
import diag


def _resource_path(name):
    """打包后资源在 PyInstaller 解压目录（sys._MEIPASS），源码运行时在 packaging/ 下"""
    base = getattr(sys, "_MEIPASS", None)
    if base and os.path.exists(os.path.join(base, name)):
        return os.path.join(base, name)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "packaging", name)


# ---------------------------------------------------------------- 主题
# 两套配色；C 在运行期原地更新，所有绘制代码都读同一个 dict
PALETTES = {
    "dark": {
        "bg": "#0f1116", "card": "#161921", "tile": "#1b1f29", "border": "#252a36",
        "border_hi": "#333a4a", "input": "#12151c", "text": "#e8eaf0", "dim": "#8b93a7",
        "faint": "#5d6478", "gold": "#f6b73c", "cyan": "#4cc9f0", "green": "#34d399",
        "violet": "#a78bfa", "red": "#f87171",
        "btn_hover": "#232836", "btn_pressed": "#181c25", "hover_border": "#46506a",
        "seg_active": "#262c3a", "menu_sel": "#2b3242", "slider_groove": "#2a3040",
        "slider_handle": "#ffffff", "slider_handle_border": "#ffffff",
        "row_alt": "#1a1d26", "sel_bg": "#243049", "scroll": "#2c3342", "scroll_hover": "#3b4457",
        "primary_hover": "#ffc75a", "primary_text": "#1d1505", "danger_hover": "#fb8a8a",
        "ok_bg": "rgba(52, 211, 153, 28)", "ok_border": "rgba(52, 211, 153, 90)",
        "err_bg": "rgba(248, 113, 113, 28)", "err_border": "rgba(248, 113, 113, 100)",
        "warn_bg": "rgba(246, 183, 60, 26)", "warn_border": "rgba(246, 183, 60, 90)",
        "key_bg": "#1c212c", "key_border": "#2a3142", "key_fg": "#e3e6ee", "key_sub": "#7c859b",
        "chord_bg": "#152824", "chord_border": "#24473c", "chord_fg": "#bfe9da",
        "chord_sub": "#6fae98",
    },
    "light": {
        "bg": "#f3f5f9", "card": "#ffffff", "tile": "#f7f8fb", "border": "#e1e5ee",
        "border_hi": "#c9d0dd", "input": "#ffffff", "text": "#1b1f27", "dim": "#5b6475",
        "faint": "#858d9e", "gold": "#c8870f", "cyan": "#0b7fa5", "green": "#0f9d6e",
        "violet": "#7656d6", "red": "#d64545",
        "btn_hover": "#eef1f7", "btn_pressed": "#e6eaf2", "hover_border": "#9aa6bd",
        "seg_active": "#e9edf4", "menu_sel": "#e6eefb", "slider_groove": "#d8dee9",
        "slider_handle": "#ffffff", "slider_handle_border": "#aab3c5",
        "row_alt": "#f8f9fc", "sel_bg": "#e3ebfa", "scroll": "#c9d2e3", "scroll_hover": "#aeb9ce",
        "primary_hover": "#e0a52e", "primary_text": "#1d1505", "danger_hover": "#e46b6b",
        "ok_bg": "rgba(15, 157, 110, 20)", "ok_border": "rgba(15, 157, 110, 90)",
        "err_bg": "rgba(214, 69, 69, 18)", "err_border": "rgba(214, 69, 69, 90)",
        "warn_bg": "rgba(200, 135, 15, 20)", "warn_border": "rgba(200, 135, 15, 80)",
        "key_bg": "#ffffff", "key_border": "#d7dce6", "key_fg": "#20242c", "key_sub": "#6b7385",
        "chord_bg": "#e9f7f2", "chord_border": "#b7e3d5", "chord_fg": "#0f513f",
        "chord_sub": "#3f7f6d",
    },
}
C = dict(PALETTES["dark"])
THEME_MODE = "system"
THEME_EFFECTIVE = "dark"
_APP = None
UI_FONT = "Microsoft YaHei UI"      # apply_theme() 里按系统已安装字体确定
NUM_FONT = "Segoe UI"               # 数字字体：优先 Bahnschrift（Windows 10+ 自带）

BPM_SAMPLE_S = 0.5                  # BPM 记录间隔
BPM_KEEP = int(4 * 3600 / BPM_SAMPLE_S)
NOTES_KEEP = 20000


def _qss():
    c = C
    return f"""
QMainWindow, QWidget#root {{ background: {c['bg']}; }}
QWidget {{ color: {c['text']}; }}
QLabel {{ background: transparent; }}
QFrame#card {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 12px; }}
QFrame#tile {{ background: {c['tile']}; border: 1px solid {c['border']}; border-radius: 10px; }}
QLabel#cardTitle {{ font-size: 14px; font-weight: 600; color: {c['text']}; }}
QLabel#cardHint, QLabel#tileCap {{ font-size: 12px; color: {c['faint']}; }}
QLabel#tileSub {{ font-size: 12px; color: {c['dim']}; }}
QLabel#appTitle {{ font-size: 18px; font-weight: 700; color: {c['text']}; }}
QLabel#appVer {{ font-size: 12px; color: {c['faint']}; }}
QLabel#field {{ font-size: 12px; color: {c['dim']}; }}
QLabel#rowLabel {{ font-size: 12px; color: {c['faint']}; }}
QLabel#chip {{ font-size: 12px; color: {c['dim']}; background: {c['input']}; border: 1px solid {c['border']};
               border-radius: 8px; padding: 3px 10px; }}
QLabel#pill {{ font-size: 12px; color: {c['dim']}; background: {c['tile']}; border: 1px solid {c['border']};
               border-radius: 13px; padding: 4px 14px; }}
QLabel#pill[state="on"] {{ color: {c['green']}; background: {c['ok_bg']}; border-color: {c['ok_border']}; }}
QLabel#pill[state="err"] {{ color: {c['red']}; background: {c['err_bg']}; border-color: {c['err_border']}; }}
QPushButton#pillBtn {{ font-size: 12px; color: {c['dim']}; background: {c['tile']}; border: 1px solid {c['border']};
                      border-radius: 13px; padding: 4px 14px; }}
QPushButton#pillBtn:hover {{ border-color: {c['hover_border']}; }}
QPushButton#pillBtn:checked {{ color: {c['gold']}; background: {c['warn_bg']}; border-color: {c['warn_border']}; font-weight: 700; }}
QPushButton#pillBtn[state="warn"] {{ color: {c['gold']}; background: {c['warn_bg']}; border-color: {c['warn_border']}; }}
QPushButton#pillBtn[state="bad"] {{ color: {c['red']}; background: {c['err_bg']}; border-color: {c['err_border']}; }}
QFrame#tabs {{ background: {c['input']}; border: 1px solid {c['border']}; border-radius: 9px; }}
QFrame#tabs QPushButton {{ background: transparent; border: none; border-radius: 7px; padding: 5px 14px;
                           color: {c['dim']}; font-size: 13px; font-weight: 600; }}
QFrame#tabs QPushButton:hover {{ color: {c['text']}; }}
QFrame#tabs QPushButton:checked {{ background: {c['seg_active']}; color: {c['text']}; }}
QLabel#screenSummary {{ font-size: 12px; color: {c['dim']}; background: {c['tile']}; border: 1px solid {c['border']};
                        border-radius: 8px; padding: 8px 12px; }}
QPushButton {{ background: {c['tile']}; color: {c['text']}; border: 1px solid {c['border_hi']}; border-radius: 8px;
               padding: 7px 16px; font-size: 13px; }}
QPushButton:hover {{ background: {c['btn_hover']}; border-color: {c['hover_border']}; }}
QPushButton:pressed {{ background: {c['btn_pressed']}; }}
QPushButton:disabled {{ color: {c['faint']}; }}
QPushButton#primary {{ background: {c['gold']}; color: {c['primary_text']}; border: none; font-weight: 700; padding: 8px 22px; }}
QPushButton#primary:hover {{ background: {c['primary_hover']}; }}
QPushButton#primary:checked {{ background: {c['red']}; color: #ffffff; }}
QPushButton#primary:checked:hover {{ background: {c['danger_hover']}; }}
QFrame#seg {{ background: {c['input']}; border: 1px solid {c['border']}; border-radius: 8px; }}
QFrame#seg QPushButton {{ background: transparent; border: none; border-radius: 6px; padding: 4px 12px;
                          color: {c['dim']}; font-size: 12px; }}
QFrame#seg QPushButton:hover {{ color: {c['text']}; }}
QFrame#seg QPushButton:checked {{ background: {c['seg_active']}; color: {c['gold']}; font-weight: 600; }}
QComboBox, QSpinBox, QLineEdit {{ background: {c['input']}; border: 1px solid {c['border_hi']}; border-radius: 8px;
                       padding: 5px 10px; min-height: 20px; font-size: 13px; }}
QComboBox:hover, QSpinBox:hover, QLineEdit:hover {{ border-color: {c['hover_border']}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {c['tile']}; border: 1px solid {c['border_hi']}; padding: 4px;
                               selection-background-color: {c['menu_sel']}; outline: none; }}
QSpinBox::up-button, QSpinBox::down-button {{ border: none; background: transparent; width: 16px; }}
QSlider::groove:horizontal {{ height: 4px; background: {c['slider_groove']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {c['gold']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {c['slider_handle']}; border: 1px solid {c['slider_handle_border']};
                              width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
QTableView {{ background: transparent; border: none; gridline-color: transparent; outline: none;
              alternate-background-color: {c['row_alt']}; selection-background-color: {c['sel_bg']};
              selection-color: {c['text']}; font-size: 13px; }}
QTableView::item {{ padding: 0 10px; border: none; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: transparent; color: {c['faint']}; border: none;
                        border-bottom: 1px solid {c['border']}; padding: 6px 10px; font-size: 12px; font-weight: 600; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['scroll']}; border-radius: 4px; min-height: 32px; }}
QScrollBar::handle:vertical:hover {{ background: {c['scroll_hover']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QSplitter::handle:vertical {{ height: 10px; background: transparent; }}
QStatusBar {{ background: {c['bg']}; color: {c['faint']}; font-size: 12px; }}
QStatusBar::item {{ border: none; }}
QToolTip {{ background: {c['tile']}; color: {c['text']}; border: 1px solid {c['border_hi']}; padding: 6px 8px; }}
QMessageBox, QFileDialog, QDialog {{ background: {c['card']}; }}
QGroupBox {{ border: 1px solid {c['border']}; border-radius: 10px; margin-top: 16px; padding: 12px;
             font-size: 13px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 5px; color: {c['dim']}; }}
QGroupBox QLabel {{ font-weight: 400; }}
QCheckBox {{ color: {c['text']}; font-size: 13px; spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {c['border_hi']}; border-radius: 4px;
                        background: {c['input']}; }}
QCheckBox::indicator:checked {{ background: {c['gold']}; border-color: {c['gold']}; }}
"""


def _pick_font(cands):
    fams = set(QFontDatabase.families())
    for f in cands:
        if f in fams:
            return f
    return cands[-1]


def _fonts_for_language():
    code = i18n.current()
    if code in ("zh-Hant", "zh-TW"):
        return ["Microsoft JhengHei UI", "Microsoft JhengHei", "Noto Sans CJK TC",
                "PingFang TC", "Segoe UI"]
    if code == "ja":
        return ["Yu Gothic UI", "Meiryo UI", "Noto Sans CJK JP", "MS UI Gothic", "Segoe UI"]
    if code == "en":
        return ["Segoe UI", "Microsoft YaHei UI", "Noto Sans CJK SC"]
    return ["Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC", "PingFang SC", "Segoe UI"]


def effective_theme(mode=None):
    """system → 跟随 Windows/Qt 的深色设置；无法判断时保持深色。"""
    mode = mode or THEME_MODE
    if mode in ("dark", "light"):
        return mode
    try:
        hints = QApplication.instance().styleHints()
        scheme = hints.colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return "dark"
        if scheme == Qt.ColorScheme.Light:
            return "light"
    except Exception:
        pass
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            light = winreg.QueryValueEx(k, "AppsUseLightTheme")[0]
        return "light" if int(light) else "dark"
    except Exception:
        return "dark"


def apply_theme(app, mode="system"):
    """字体 + 样式表（需在 QApplication 创建之后调用）。C 原地更新，绘制代码无需重新绑定。"""
    global UI_FONT, NUM_FONT, THEME_MODE, THEME_EFFECTIVE, _APP
    _APP = app
    THEME_MODE = mode if mode in ("system", "dark", "light") else "system"
    eff = effective_theme(THEME_MODE)
    THEME_EFFECTIVE = eff
    C.clear()
    C.update(PALETTES[eff])
    UI_FONT = _pick_font(_fonts_for_language())
    NUM_FONT = _pick_font(["Bahnschrift", "Segoe UI Semibold", "Segoe UI", UI_FONT])
    f = QFont(UI_FONT)
    f.setPixelSize(13)
    app.setFont(f)
    app.setStyleSheet(_qss())
    pg.setConfigOptions(antialias=True)
    return eff


def set_theme_mode(app, mode):
    """切换主题并立即重绘；返回实际生效的 dark/light。"""
    return apply_theme(app, mode)



def _repolish(w):
    w.style().unpolish(w)
    w.style().polish(w)


def _num_font(px, bold=True):
    f = QFont(NUM_FONT)
    f.setPixelSize(max(6, int(px)))
    f.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
    return f


def _gear_icon(color: str, size: int = 20) -> QIcon:
    """自绘齿轮图标：不依赖系统是否装有所需符号字体。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.translate(size / 2.0, size / 2.0)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    for i in range(8):
        p.save()
        p.rotate(i * 45)
        p.drawRoundedRect(QRectF(-1.7, -size * 0.44, 3.4, size * 0.20), 0.8, 0.8)
        p.restore()
    p.drawEllipse(QRectF(-size * 0.33, -size * 0.33, size * 0.66, size * 0.66))
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    p.drawEllipse(QRectF(-size * 0.14, -size * 0.14, size * 0.28, size * 0.28))
    p.end()
    return QIcon(pm)


def _fmt_time(t):
    t = max(0.0, float(t))
    m, s = divmod(t, 60.0)
    return f"{int(m)}:{s:06.3f}"


# ================================================================ 通用卡片
class Card(QFrame):
    def __init__(self, title=None, hint=None, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 12, 16, 14)
        self.body.setSpacing(10)
        self.head = QHBoxLayout()
        self.head.setSpacing(10)
        self.hint = None
        if title:
            t = QLabel(title)
            t.setObjectName("cardTitle")
            self.head.addWidget(t)
            self.hint = QLabel(hint or "")
            self.hint.setObjectName("cardHint")
            self.head.addWidget(self.hint)
            self.head.addStretch(1)
            self.body.addLayout(self.head)


class MetricTile(QFrame):
    """实时指标：小标题 + 大号数值（字号随卡片大小自适应，过长时自动缩小）+ 可选副标题"""

    def __init__(self, caption, color_key, big=False, mono=False, parent=None):
        super().__init__(parent)
        self.setObjectName("tile")
        self.color_key, self.big, self.mono = color_key, big, mono
        self.caption = caption
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 14, 10)
        v.setSpacing(2)
        self.cap = QLabel()
        self.cap.setObjectName("tileCap")
        self.cap.setTextFormat(Qt.TextFormat.RichText)
        self._update_caption()
        self.val = QLabel("—")
        self.val.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.val.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.sub = QLabel("")
        self.sub.setObjectName("tileSub")
        v.addWidget(self.cap)
        v.addWidget(self.val, 1)
        v.addWidget(self.sub)
        self.setMinimumHeight(72)
        self._px = 0

    def _color(self):
        return C.get(self.color_key, self.color_key)

    def _update_caption(self):
        self.cap.setText(f"<span style='color:{self._color()}'>●</span>&nbsp;&nbsp;{self.caption}")

    def apply_theme(self):
        self._update_caption()
        self._px = 0
        self._fit()

    def setText(self, s):
        self.val.setText(s if s else "—")
        self._px = 0
        self._fit()

    def text(self):
        return self.val.text()

    def setSub(self, s):
        self.sub.setText(s)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def _fit(self):
        h = max(20, self.val.height())
        w = max(40, self.val.width())
        px = min(h * (0.78 if self.big else 0.62), 56 if self.big else 30)
        fam = NUM_FONT if self.mono else UI_FONT
        f = QFont(fam)
        while px > 12:
            f.setPixelSize(int(px))
            f.setWeight(QFont.Weight.DemiBold)
            if QFontMetrics(f).horizontalAdvance(self.val.text()) <= w - 4:
                break
            px -= 1
        px = int(px)
        if px != self._px:
            self._px = px
            color = C["faint"] if self.val.text() == "—" else self._color()
            self.val.setStyleSheet(f"color:{color}; font-family:'{fam}'; font-size:{px}px; font-weight:600;")


# ================================================================ 键位面板
KEY_STYLES = {
    "风物之诗琴": {"accent": "#63aea7", "accent2": "#4f8f88", "chord": "#3f7f79",
                   "dark": ("#082d3d", "#0f4659"), "light": ("#dceff4", "#c3e2ec")},
    "镜花之琴": {"accent": "#c08a52", "accent2": "#8f5c32", "chord": "#a86f3c",
                 "dark": ("#102b40", "#163d55"), "light": ("#f3e6d5", "#e6d1b8")},
    "跃律琴": {"accent": "#45bdd4", "accent2": "#218fa8", "chord": "#2a9fb5",
               "dark": ("#0a2c44", "#11465f"), "light": ("#d8eef8", "#bcdff0")},
    "谐律键琴": {"accent": "#d6ad55", "accent2": "#a87a2e", "chord": "#b5863a",
                 "dark": ("#112b44", "#1a405f"), "light": ("#f5ecd5", "#e8d6ae")},
    "晚风圆号": {"accent": "#e0a34a", "accent2": "#b87624", "chord": "#c07d2e",
                 "dark": ("#14283f", "#203c58"), "light": ("#f6e6d3", "#e9cfae")},
    "悠可琴": {"accent": "#5b8fe0", "accent2": "#3566b8", "chord": "#2f5fa8",
               "dark": ("#10264a", "#183c68"), "light": ("#dce9fb", "#c2d8f5")},
}
KEY_STYLE_DEFAULT = KEY_STYLES["风物之诗琴"]


def _key_style(instrument_name: str) -> dict:
    return KEY_STYLES.get(instrument_name, KEY_STYLE_DEFAULT)


def _draw_note_glyph(p: QPainter, cx: float, cy: float, r: float, degree: int, color: QColor):
    """游戏键面的音级符号：粗圆环 + 位置不同的短横/竖线（do–ti 各不相同）。"""
    pen = QPen(color, max(1.8, r * 0.24))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if degree % 7 in (3, 5):
        # fa / la：竖向的窄环，上下横线（la 多一条底线）
        p.drawEllipse(QRectF(cx - r * 0.56, cy - r * 0.78, r * 1.12, r * 1.56))
    else:
        # do/re/mi/so/la/ti：横向略宽的圆环
        p.drawEllipse(QRectF(cx - r * 0.78, cy - r * 0.64, r * 1.56, r * 1.28))
    a = r * 1.0
    b = r * 0.92
    shapes = {
        0: [(cx - a, cy, cx + a, cy)],
        1: [(cx - a, cy + b, cx + a, cy + b)],
        2: [(cx - a, cy - b, cx + a, cy - b)],
        3: [(cx - a, cy - b, cx + a, cy - b),
            (cx - a, cy + b, cx + a, cy + b)],
        4: [(cx - a, cy - b, cx + a, cy - b),
            (cx - a, cy, cx + a, cy),
            (cx - a, cy + b, cx + a, cy + b)],
        5: [(cx - a, cy - b, cx + a, cy - b),
            (cx - a, cy + b, cx + a, cy + b),
            (cx - a, cy + b * 1.35, cx + a, cy + b * 1.35)],
        6: [(cx - a, cy - b, cx + a, cy - b),
            (cx - a, cy, cx + a, cy),
            (cx - a, cy + b, cx + a, cy + b),
            (cx - a, cy + b * 1.35, cx + a, cy + b * 1.35)],
    }
    for x1, y1, x2, y2 in shapes.get(degree % 7, shapes[0]):
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


_KEY_FACE_PIXMAP = None
_GLYPH_PIXMAPS = {}


def _key_face_pixmap():
    global _KEY_FACE_PIXMAP
    if _KEY_FACE_PIXMAP is None:
        pm = QPixmap(_resource_path(os.path.join("ui_assets", "key_face.png")))
        _KEY_FACE_PIXMAP = pm if not pm.isNull() else None
    return _KEY_FACE_PIXMAP


def _glyph_pixmap(degree: int, color: QColor):
    """优先用游戏 UI 的字形蒙版（像素级）；SVG 矢量路径作为后备。"""
    degree %= 7
    key = (degree, color.name())
    if key in _GLYPH_PIXMAPS:
        return _GLYPH_PIXMAPS[key]
    pix = QPixmap(_resource_path(os.path.join("ui_assets", f"glyph_{degree}.png")))
    if pix.isNull():
        svg_path = _resource_path(os.path.join("ui_assets", f"glyph_{degree}.svg"))
        try:
            with open(svg_path, "rb") as fh:
                renderer = QSvgRenderer(QByteArray(fh.read()))
            if renderer.isValid():
                img = QImage(256, 256, QImage.Format.Format_ARGB32)
                img.fill(Qt.GlobalColor.transparent)
                pp = QPainter(img)
                renderer.render(pp, QRectF(0, 0, 256, 256))
                pp.end()
                pix = QPixmap.fromImage(img)
        except Exception:
            pix = QPixmap()
    if pix.isNull():
        _GLYPH_PIXMAPS[key] = None
        return None
    tinted = QPixmap(pix.size())
    tinted.fill(Qt.GlobalColor.transparent)
    pp = QPainter(tinted)
    pp.drawPixmap(0, 0, pix)
    pp.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    pp.fillRect(tinted.rect(), color)
    pp.end()
    _GLYPH_PIXMAPS[key] = tinted
    return tinted


class RowIcon(QWidget):
    """行首图标：高音/中音/低音谱号，或悠可琴的和弦指板。"""

    CLEFS = {"treble": "\U0001D11E", "alto": "\U0001D121", "bass": "\U0001D122"}

    def __init__(self, role, style, label, parent=None):
        super().__init__(parent)
        self.role, self.style = role, style
        self.setFixedWidth(46)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setToolTip(label)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        accent = QColor(self.style["accent2"] if THEME_EFFECTIVE == "light" else self.style["accent"])
        if self.role == "chord":
            w, h = 20, 30
            x, y = (self.width() - w) / 2, (self.height() - h) / 2
            p.setPen(QPen(accent, 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(x, y, w, h), 3, 3)
            for i in (1, 2, 3):
                p.drawLine(QPointF(x + w * i / 4, y), QPointF(x + w * i / 4, y + h))
            for i in (1, 2, 3):
                p.drawLine(QPointF(x, y + h * i / 4), QPointF(x + w, y + h * i / 4))
            p.setBrush(accent)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x + w * 0.25, y + h * 0.5), 1.7, 1.7)
            p.drawEllipse(QPointF(x + w * 0.75, y + h * 0.25), 1.7, 1.7)
        else:
            f = QFont("Segoe UI Symbol")
            f.setPixelSize(max(16, min(34, int(self.height() * 0.58))))
            p.setFont(f)
            p.setPen(accent)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.CLEFS[self.role])
        p.end()


class KeyTile(QWidget):
    """单个琴键：奶油色圆盘 + 音级符号 + 唱名 + 小号键位字母；发音时按乐器主色高亮。"""

    def __init__(self, letter, role, style, tip="", solfege="", chord="", note="", degree=0, parent=None):
        super().__init__(parent)
        self.letter, self.role, self.style = letter, role, style
        self.solfege, self.chord, self.note, self.degree = solfege, chord, note, degree
        self.active = False
        self.show_hint = True
        self.setToolTip(tip)
        self.setMinimumSize(36, 36)
        self.setMaximumSize(140, 140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def sizeHint(self):
        return QSize(76, 76)

    def set_active(self, a):
        if a != self.active:
            self.active = a
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height()) - 2
        if side < 18:
            p.end()
            return
        cx, cy = self.width() / 2.0, self.height() / 2.0
        r = side / 2.0
        accent = QColor(self.style["accent"])
        accent2 = QColor(self.style["accent2"])
        cream = QColor("#fff9ef")
        if self.role == "chord":
            fg = cream if THEME_EFFECTIVE == "dark" else accent2
            if self.active:
                grad = QLinearGradient(cx, cy - r, cx, cy + r)
                grad.setColorAt(0.0, accent.lighter(112))
                grad.setColorAt(1.0, accent2)
                p.setBrush(grad)
                p.setPen(QPen(QColor(255, 255, 255, 150), max(1.0, side * 0.014)))
            else:
                p.setBrush(QColor("#24466f") if THEME_EFFECTIVE == "dark" else QColor("#dce9fb"))
                p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 130), 1))
            p.drawEllipse(QRectF(cx - r, cy - r, side, side))
            f = QFont(UI_FONT)
            f.setPixelSize(max(10, int(side * 0.25)))
            f.setBold(True)
            p.setFont(f)
            p.setPen(fg)
            p.drawText(QRectF(cx - r, cy - side * 0.30, side, side * 0.36),
                       Qt.AlignmentFlag.AlignCenter, self.chord)
            f2 = QFont(UI_FONT)
            f2.setPixelSize(max(8, int(side * 0.15)))
            p.setFont(f2)
            p.drawText(QRectF(cx - r, cy + side * 0.10, side, side * 0.24),
                       Qt.AlignmentFlag.AlignCenter, self.letter)
            p.end()
            return

        # 游戏内键面来自 1:1 截取：奶油盘、米色花瓣环、居中的音级字形
        if self.active:
            glow = QColor(accent)
            glow.setAlpha(60)
            p.setPen(QPen(glow, max(3.0, side * 0.10)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - r + 2, cy - r + 2, side - 4, side - 4))
        face = _key_face_pixmap()
        if face is not None:
            p.drawPixmap(QRectF(cx - r, cy - r, side, side), face,
                         QRectF(0, 0, face.width(), face.height()))
        else:
            p.setBrush(cream)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(cx - r, cy - r, side, side))
        if self.active:
            p.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 34))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(cx - r, cy - r, side, side))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(accent, max(2.0, side * 0.045)))
            p.drawEllipse(QRectF(cx - r + 2, cy - r + 2, side - 4, side - 4))
            fg = accent2
        else:
            fg = accent
        glyph = _glyph_pixmap(self.degree, fg)
        if glyph is not None:
            box = side * (110.0 / 154.0)
            p.drawPixmap(QRectF(cx - box / 2.0, cy - box / 2.0, box, box), glyph,
                         QRectF(0, 0, glyph.width(), glyph.height()))
        else:
            _draw_note_glyph(p, cx, cy, side * 0.280, self.degree, fg)
        # 键位提示：小标签放在左上角的花边上，不遮挡音级符号
        if self.role != "chord" and self.show_hint and side >= 52:
            br = max(7.0, side * 0.105)
            bx, by = cx - r * 0.72, cy - r * 0.72
            if self.active:
                p.setBrush(cream)
                p.setPen(QPen(accent2, 1))
                p.setPen(Qt.PenStyle.NoPen)
                letter_color = accent2
            else:
                p.setBrush(QColor(37, 47, 48, 215))
                p.setPen(Qt.PenStyle.NoPen)
                letter_color = cream
            p.drawEllipse(QPointF(bx, by), br, br)
            f2 = QFont(NUM_FONT)
            f2.setPixelSize(max(8, int(br * 1.12)))
            f2.setBold(True)
            p.setFont(f2)
            p.setPen(letter_color)
            p.drawText(QRectF(bx - br, by - br, br * 2, br * 2),
                       Qt.AlignmentFlag.AlignCenter, self.letter)
        p.end()


class KeyPanel(QWidget):
    """按乐器排列圆形琴键；行首为谱号/和弦指板，背景随乐器与主题变化。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.inst = None
        self.style = KEY_STYLE_DEFAULT
        self._rows = 0
        self.show_hints = True
        self.grid = QGridLayout(self)
        self.grid.setHorizontalSpacing(4)
        self.grid.setVerticalSpacing(0)
        self.grid.setContentsMargins(4, 4, 6, 4)
        self.buttons = {}

    def sizeHint(self):
        return QSize(760, 260)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0, 0, -1, -1)
        g = QLinearGradient(0, 0, 0, self.height())
        if THEME_EFFECTIVE == "light":
            g.setColorAt(0, QColor(self.style["light"][0]))
            g.setColorAt(1, QColor(self.style["light"][1]))
            line = QColor(30, 80, 110, 34)
        else:
            g.setColorAt(0, QColor(self.style["dark"][0]))
            g.setColorAt(1, QColor(self.style["dark"][1]))
            line = QColor(255, 255, 255, 22)
        p.setBrush(g)
        p.setPen(QPen(QColor(255, 255, 255, 20), 1))
        p.drawRoundedRect(rect, 12, 12)
        # 五线谱：每行键后画 5 条很淡的横线
        p.setPen(QPen(line, 1))
        for r in range(self._rows):
            cr = self.grid.cellRect(r, 1)
            if cr.isValid() and cr.height() > 10:
                for k in range(5):
                    y = cr.top() + cr.height() * (0.31 + k * 0.095)
                    p.drawLine(QPointF(cr.left() - 38, y), QPointF(cr.right() + 8, y))
        # 细小的星点，避免大面积纯色
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 55 if THEME_EFFECTIVE == "dark" else 90))
        for fx, fy in ((0.05, 0.18), (0.17, 0.78), (0.31, 0.12), (0.46, 0.86),
                       (0.62, 0.20), (0.77, 0.72), (0.90, 0.30), (0.96, 0.84)):
            p.drawEllipse(QPointF(self.width() * fx, self.height() * fy), 1.4, 1.4)
        p.end()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit_grid()

    def _fit_grid(self):
        """让键面按游戏内的方形格子居中：横向留白，而不是把圆键拉成大间隙。"""
        if not self._rows or self.width() < 80 or self.height() < 40:
            return
        row_h = max(24.0, (self.height() - 8.0) / self._rows)
        cell = row_h / 0.90
        keys_w = 7.0 * cell
        icon_w = 46.0
        margin = max(4, int((self.width() - icon_w - keys_w) / 2.0))
        self.grid.setContentsMargins(margin, 4, margin, 4)

    def set_hints(self, on):
        self.show_hints = bool(on)
        for tile in self.buttons.values():
            tile.show_hint = self.show_hints
            tile.update()

    def set_instrument(self, inst):
        self.inst = inst
        self.style = _key_style(inst.name)
        self.update()
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self.buttons.clear()
        for r in range(5):
            self.grid.setRowStretch(r, 0)
        for c in range(1, 8):
            self.grid.setColumnStretch(c, 0)
        key_map = {k[0]: k for k in inst.keys}
        if inst.name == "悠可琴":
            rows = [("chord", "QWERTYU", T("和弦")),
                    ("treble", "ASDFGHJ", T("高音")),
                    ("alto", "ZXCVBNM", T("低音"))]
        elif inst.name == "晚风圆号":
            rows = [("treble", "QWERTYU", T("高音")),
                    ("bass", "ASDFGHJ", T("低音"))]
        else:
            rows = [("treble", "QWERTYU", T("高音")),
                    ("alto", "ASDFGHJ", T("中音")),
                    ("bass", "ZXCVBNM", T("低音"))]
        self._rows = len(rows)
        self._fit_grid()
        for r, (role, letters, label) in enumerate(rows):
            icon = RowIcon(role, self.style, label)
            self.grid.addWidget(icon, r, 0)
            for c, ch in enumerate(letters):
                key_label, midi, kind, extra = key_map[ch]
                if kind == "chord":
                    tile = KeyTile(ch, "chord", self.style,
                                   tip=T("和弦键 {key}：{chord}", key=ch, chord=extra),
                                   chord=str(extra))
                else:
                    try:
                        degree = DIATONIC_OFFSETS.index(midi % 12)
                    except ValueError:
                        degree = 0
                    sol = midi_to_solfege(midi)
                    note = midi_to_name(midi)
                    tile = KeyTile(ch, "pitch", self.style,
                                   tip=T("键 {key} = {note}", key=ch, note=note),
                                   solfege=sol or note, note=note, degree=degree)
                tile.show_hint = self.show_hints
                self.grid.addWidget(tile, r, c + 1)
                self.buttons[ch] = tile
            self.grid.setRowStretch(r, 1)
        for c in range(1, 8):
            self.grid.setColumnStretch(c, 1)
        self.grid.setColumnMinimumWidth(0, 46)

    def set_active(self, labels):
        for ch, tile in self.buttons.items():
            tile.set_active(ch in labels)


# ================================================================ BPM 变化图
class TimeAxis(pg.AxisItem):
    """横轴：开始监听后的时间，显示为 分:秒；刻度取整秒/整分（5 s、10 s、30 s、1 min、5 min、10 min…）"""
    STEPS = (1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200)

    def tickSpacing(self, minVal, maxVal, size):
        span = max(1e-6, maxVal - minVal)
        target = max(2.0, size / 110.0)            # 约每 110 像素一个主刻度
        major = next((s for s in self.STEPS if span / s <= target), self.STEPS[-1])
        minor = next((s for s in reversed(self.STEPS) if s < major and major % s == 0), major)
        return [(float(major), 0.0), (float(minor), 0.0)]

    def tickStrings(self, values, scale, spacing):
        out = []
        for v in values:
            v = int(round(max(0.0, v)))
            h, rem = divmod(v, 3600)
            m, s = divmod(rem, 60)
            out.append(f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}")
        return out


def _heat(u):
    """0~1 → 青 → 金 → 珊瑚红（慢 → 快）"""
    stops = [(0.0, (76, 201, 240)), (0.5, (246, 183, 60)), (1.0, (248, 113, 113))]
    u = min(1.0, max(0.0, u))
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if u <= b:
            k = (u - a) / (b - a)
            return tuple(int(ca[i] + (cb[i] - ca[i]) * k) for i in range(3))
    return stops[-1][1]


class BpmChart(QWidget):
    """BPM 随时间的条形图：纵轴按当前显示的数据自动缩放，条形按快慢着色，鼠标悬停显示该时刻的读数"""
    RANGES = [("30 秒", 30.0), ("1 分钟", 60.0), ("5 分钟", 300.0), ("全部", None)]
    stats_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.t, self.v = [], []
        self.window = 60.0
        self.dirty = False
        self._shown = ([], [])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(6)
        self.chips = {}
        for key in ("当前", "平均", "最低", "最高"):
            lab = QLabel(f"{T(key)}  —")
            lab.setObjectName("chip")
            head.addWidget(lab)
            self.chips[key] = lab
        head.addStretch(1)
        seg = QFrame()
        seg.setObjectName("seg")
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(3, 3, 3, 3)
        sl.setSpacing(2)
        self.range_group = QButtonGroup(self)
        self.range_group.setExclusive(True)
        for i, (name, sec) in enumerate(self.RANGES):
            b = QPushButton(T(name))
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setChecked(sec == self.window)
            self.range_group.addButton(b, i)
            sl.addWidget(b)
        self.range_group.idClicked.connect(self._on_range)
        head.addWidget(seg)
        lay.addLayout(head)

        self.plot = pg.PlotWidget(axisItems={"bottom": TimeAxis(orientation="bottom")})
        self.plot.setBackground(C["card"])
        self.plot.setMinimumHeight(90)
        pi = self.plot.getPlotItem()
        pi.hideButtons()
        pi.setMenuEnabled(False)
        pi.setMouseEnabled(x=False, y=False)
        pi.showGrid(x=False, y=True, alpha=0.10)
        tick_font = _num_font(11, bold=False)
        for name in ("left", "bottom"):
            ax = pi.getAxis(name)
            ax.setPen(pg.mkPen(C["border_hi"]))
            ax.setTextPen(pg.mkPen(C["dim"]))
            ax.setStyle(tickFont=tick_font, tickLength=-4)
        pi.getAxis("left").setWidth(46)
        self.bars = pg.BarGraphItem(x=[], height=[], width=0.4, pen=None, brush=pg.mkBrush(C["gold"]))
        pi.addItem(self.bars)
        self.cur_line = pg.InfiniteLine(angle=0, movable=False,
                                        pen=pg.mkPen(QColor(246, 183, 60, 150), width=1, style=Qt.PenStyle.DashLine))
        pi.addItem(self.cur_line)
        self.cur_line.hide()
        self.hover_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(QColor(232, 234, 240, 70), width=1))
        pi.addItem(self.hover_line, ignoreBounds=True)
        self.hover_line.hide()
        self.hover_text = pg.TextItem("", color=C["text"], anchor=(0, 0),
                                      fill=pg.mkBrush(27, 31, 41, 235), border=pg.mkPen(C["border_hi"]))
        self.hover_text.setFont(_num_font(12, bold=False))
        pi.addItem(self.hover_text, ignoreBounds=True)
        self.hover_text.hide()
        self.empty_text = pg.TextItem(T("开始演奏后，这里会实时画出 BPM 随时间的变化"),
                                      color=C["faint"], anchor=(0.5, 0.5))
        f = QFont(UI_FONT)
        f.setPixelSize(13)
        self.empty_text.setFont(f)
        pi.addItem(self.empty_text, ignoreBounds=True)
        self._proxy = pg.SignalProxy(self.plot.scene().sigMouseMoved, rateLimit=40, slot=self._on_move)
        lay.addWidget(self.plot, 1)
        self.refresh()

    def apply_theme(self):
        """主题切换后同步 pyqtgraph 自绘元素（QSS 管不到它们）。"""
        pi = self.plot.getPlotItem()
        self.plot.setBackground(C["card"])
        for name in ("left", "bottom"):
            ax = pi.getAxis(name)
            ax.setPen(pg.mkPen(C["border_hi"]))
            ax.setTextPen(pg.mkPen(C["dim"]))
        self.bars.setOpts(brush=pg.mkBrush(C["gold"]))
        gold = QColor(C["gold"])
        gold.setAlpha(150)
        self.cur_line.setPen(pg.mkPen(gold, width=1, style=Qt.PenStyle.DashLine))
        dim = QColor(C["text"])
        dim.setAlpha(70)
        self.hover_line.setPen(pg.mkPen(dim, width=1))
        try:
            self.empty_text.setColor(C["faint"])
        except Exception:
            pass
        self.refresh()

    # ---------------------------------------------------------- 数据
    def add(self, t, v):
        if self.t and t <= self.t[-1]:
            return
        self.t.append(float(t))
        self.v.append(float(v))
        if len(self.t) > BPM_KEEP:
            del self.t[:len(self.t) - BPM_KEEP]
            del self.v[:len(self.v) - BPM_KEEP]
        self.dirty = True

    def clear(self):
        self.t, self.v = [], []
        self.dirty = True
        self.refresh()

    def last_time(self):
        return self.t[-1] if self.t else 0.0

    def _on_range(self, idx):
        self.window = self.RANGES[idx][1]
        self.refresh()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.dirty = True

    # ---------------------------------------------------------- 绘制
    def refresh(self):
        self.dirty = False
        pi = self.plot.getPlotItem()
        if not self.t:
            self.bars.setOpts(x=[], height=[], brushes=None)
            self.cur_line.hide()
            self.hover_line.hide()
            self.hover_text.hide()
            pi.setXRange(0, 60, padding=0)
            pi.setYRange(0, 300, padding=0)
            self.empty_text.setPos(30, 150)
            self.empty_text.show()
            for k, lab in self.chips.items():
                lab.setText(f"{T(k)}  —")
            self._shown = ([], [])
            self.stats_changed.emit("")
            return
        self.empty_text.hide()
        t_last = self.t[-1]
        if self.window is None:
            x0, x1 = self.t[0], max(t_last, self.t[0] + 10.0)
        else:
            x1 = max(t_last, self.t[0] + self.window)
            x0 = x1 - self.window
        i0 = bisect.bisect_left(self.t, x0)
        ts, vs = self.t[i0:], self.v[i0:]
        # 条形数量与图表宽度相适应：太密时按时间分桶取平均
        max_bars = max(30, int(self.plot.width() / 5))
        step = BPM_SAMPLE_S
        if len(ts) > max_bars:
            span = max(x1 - x0, step)
            step = span / max_bars
            bt, bv = [], []
            k0 = 0
            for b in range(max_bars):
                hi_t = x0 + (b + 1) * step
                k1 = bisect.bisect_left(ts, hi_t, lo=k0)
                if k1 > k0:
                    bt.append(x0 + (b + 0.5) * step)
                    bv.append(sum(vs[k0:k1]) / (k1 - k0))
                k0 = k1
            ts, vs = bt, bv
        lo, hi = min(vs), max(vs)
        span = max(hi - lo, 0.15 * hi, 20.0)
        y0 = max(0.0, lo - 0.25 * span)
        y1 = hi + 0.15 * span
        mag = 10 ** math.floor(math.log10(max(1.0, y1 - y0)))
        unit = mag if (y1 - y0) / mag > 3 else mag / 2
        y0 = math.floor(y0 / unit) * unit
        y1 = math.ceil(y1 / unit) * unit
        den = max(1e-6, hi - lo)
        brushes = [pg.mkBrush(*_heat((b - lo) / den if hi > lo else 0.5), 225) for b in vs]
        self.bars.setOpts(x=ts, height=[b - y0 for b in vs], y0=y0, width=step * 0.72, brushes=brushes)
        pi.setXRange(x0 - step, x1 + step, padding=0)
        pi.setYRange(y0, y1, padding=0)
        cur = self.v[-1]
        self.cur_line.setValue(cur)
        self.cur_line.show()
        self._shown = (ts, vs)
        seg_v = self.v[i0:]
        avg = sum(seg_v) / len(seg_v)
        self.chips["当前"].setText(T("当前  {value}", value=f"{cur:.1f}"))
        self.chips["平均"].setText(T("平均  {value}", value=f"{avg:.1f}"))
        self.chips["最低"].setText(T("最低  {value}", value=f"{min(seg_v):.1f}"))
        self.chips["最高"].setText(T("最高  {value}", value=f"{max(seg_v):.1f}"))
        name = next(n for n, s in self.RANGES if s == self.window)
        if self.window is None:
            self.stats_changed.emit(T("全程 {lo} – {hi}", lo=f"{min(seg_v):.0f}", hi=f"{max(seg_v):.0f}"))
        else:
            self.stats_changed.emit(T("近 {range} {lo} – {hi}", range=T(name),
                                      lo=f"{min(seg_v):.0f}", hi=f"{max(seg_v):.0f}"))

    def _on_move(self, evt):
        pos = evt[0]
        pi = self.plot.getPlotItem()
        ts, vs = self._shown
        if not ts or not pi.vb.sceneBoundingRect().contains(pos):
            self.hover_line.hide()
            self.hover_text.hide()
            return
        p = pi.vb.mapSceneToView(pos)
        k = bisect.bisect_left(ts, p.x())
        cand = [i for i in (k - 1, k) if 0 <= i < len(ts)]
        i = min(cand, key=lambda j: abs(ts[j] - p.x()))
        x, v = ts[i], vs[i]
        m, s = divmod(int(round(x)), 60)
        self.hover_line.setValue(x)
        self.hover_line.show()
        self.hover_text.setText(f" {m}:{s:02d}   {v:.1f} BPM ")
        (vx0, vx1), (vy0, vy1) = pi.vb.viewRange()
        self.hover_text.setAnchor((1, 0) if x > (vx0 + vx1) / 2 else (0, 0))
        self.hover_text.setPos(x, vy1)
        self.hover_text.show()


# ================================================================ 音符时长表
class NotesView(QTableView):
    """列宽按比例随表格宽度自适应"""
    WEIGHTS = (1.25, 0.8, 0.9, 0.9, 1.0, 1.0, 1.7)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        w = self.viewport().width()
        tot = sum(self.WEIGHTS)
        used = 0
        for i, k in enumerate(self.WEIGHTS[:-1]):
            cw = int(w * k / tot)
            self.setColumnWidth(i, cw)
            used += cw
        self.setColumnWidth(len(self.WEIGHTS) - 1, max(60, w - used))


class NotesModel(QAbstractTableModel):
    HEAD = ["开始时间", "按键", "音名", "唱名", "时长(ms)", "间隔(ms)", "结束方式"]
    TIPS = {
        0: "开始监听后的时间（分:秒.毫秒），对齐到敲击瞬间",
        4: "起音 → 结束。结束方式为「松键/截止」时即按键时长；「同键重按」时为到再次按下的时间；\n"
           "「余音自然衰减」表示拨弦类余音自然消失，松键时刻在声音里不可观测，此时长是余音长度",
        5: "与上一个起音的间隔（和弦算一次起音），BPM 由它计算",
    }
    END_COLOR = {"release": "cyan", "retrig": "violet", "decay": "dim"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []          # 旧 → 新；显示时最新的在最上面

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEAD)

    def _row(self, r):
        return self.rows[len(self.rows) - 1 - r]

    def data(self, idx, role=Qt.ItemDataRole.DisplayRole):
        if not idx.isValid():
            return None
        row = self._row(idx.row())
        c = idx.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return row["disp"][c]
        if role == Qt.ItemDataRole.ForegroundRole:
            if c == 4:
                return QColor(C["gold"])
            if c == 6:
                return QColor(C.get(self.END_COLOR.get(row["end"], "dim"), C["dim"]))
            if c in (0, 5):
                return QColor(C["dim"])
            return None
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if c in (0, 4, 5):
                return int(Qt.AlignmentFlag.AlignCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.FontRole and c in (0, 4, 5):
            return _num_font(13, bold=False)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return T(self.HEAD[section])
        if role == Qt.ItemDataRole.ToolTipRole:
            return T(self.TIPS[section]) if section in self.TIPS else None
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if section in (0, 4, 5):
                return int(Qt.AlignmentFlag.AlignCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return None

    def add(self, raw, disp, end):
        self.beginInsertRows(QModelIndex(), 0, 0)
        self.rows.append({"raw": raw, "disp": disp, "end": end})
        self.endInsertRows()
        extra = len(self.rows) - NOTES_KEEP
        if extra > 0:
            n = len(self.rows)
            self.beginRemoveRows(QModelIndex(), n - extra, n - 1)
            del self.rows[:extra]
            self.endRemoveRows()

    def clear(self):
        self.beginResetModel()
        self.rows = []
        self.endResetModel()


class FindingsView(NotesView):
    WEIGHTS = (0.85, 0.85, 1.0, 1.5, 4.6)


class FindingsModel(QAbstractTableModel):
    """边界值排查的发现（最新在上；同一发现延长时原地更新）"""
    HEAD = ["时间", "检查项", "结论", "现象", "说明"]
    TIPS = {
        2: "超出人手极限：人做不到（例如同时按下超过 10 个键）\n疑似机械操作：人极难做到，需结合其它证据判断",
    }
    LEVEL_COLOR = {LEVEL_LIMIT: "red", LEVEL_SUSPECT: "gold"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []          # 旧 → 新：{"key", "f", "disp"}
        self._pos = {}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEAD)

    def _row(self, r):
        return self.rows[len(self.rows) - 1 - r]

    def data(self, idx, role=Qt.ItemDataRole.DisplayRole):
        if not idx.isValid():
            return None
        row = self._row(idx.row())
        c = idx.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return row["disp"][c]
        if role == Qt.ItemDataRole.ToolTipRole and c in (3, 4):
            return row["f"].get("text", "")
        if role == Qt.ItemDataRole.ForegroundRole:
            if c == 2:
                return QColor(C.get(self.LEVEL_COLOR.get(row["f"]["level"], "dim"), C["dim"]))
            if c in (0, 4):
                return QColor(C["dim"])
            return None
        if role == Qt.ItemDataRole.FontRole and c == 0:
            return _num_font(13, bold=False)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return T(self.HEAD[section])
        if role == Qt.ItemDataRole.ToolTipRole:
            return T(self.TIPS[section]) if section in self.TIPS else None
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return None

    def upsert(self, key, f, t_off):
        """新增或更新一条发现；返回 True = 新增"""
        disp = [_fmt_time(f["t"] + t_off), kind_text(f["kind"]), level_text(f["level"]),
                f.get("title", ""), f.get("text", "")]
        if key in self._pos:
            i = self._pos[key]
            self.rows[i] = {"key": key, "f": f, "disp": disp, "t": f["t"] + t_off}
            r = len(self.rows) - 1 - i
            self.dataChanged.emit(self.index(r, 0), self.index(r, len(self.HEAD) - 1))
            return False
        self.beginInsertRows(QModelIndex(), 0, 0)
        self._pos[key] = len(self.rows)
        self.rows.append({"key": key, "f": f, "disp": disp, "t": f["t"] + t_off})
        self.endInsertRows()
        return True

    def counts(self):
        lim = sum(1 for r in self.rows if r["f"]["level"] == LEVEL_LIMIT)
        return lim, len(self.rows) - lim

    def clear(self):
        self.beginResetModel()
        self.rows = []
        self._pos = {}
        self.endResetModel()


# ================================================================ 检测工作线程
class DetectWorker(QThread):
    sig_keys = Signal(object)      # set(active labels)
    sig_note = Signal(object)      # dict 音符事件
    sig_chord = Signal(str)
    sig_tonality = Signal(str)
    sig_bpm = Signal(float)        # 当前 BPM（变化时发；nan = 暂无）
    sig_bpm_sample = Signal(float, float)   # (音频时刻 s, BPM)：每 0.5 s 一个点，供 BPM 变化图
    sig_status = Signal(str)
    sig_error = Signal(str)
    sig_finding = Signal(object)   # 边界值排查的新发现 / 更新（dict）
    sig_screen = Signal(str)       # 边界值排查的一句话总结

    def __init__(self, inst, device_id, is_loopback, sensitivity, parent=None):
        super().__init__(parent)
        self.inst = inst
        self.device_id = device_id
        self.is_loopback = is_loopback
        self.sensitivity = sensitivity
        self._stop = False
        self._active_labels = set()
        self.detector = NoteDetector(inst)
        self.screener = Screener(inst)
        self._last_screen = None
        self._last_bpm = None
        self._last_bpm_t = 0.0
        self._last_chord = None
        self._last_key = None
        self._last_sample_t = -1e9

    def stop(self):
        self._stop = True

    # ------------------------------------------------------------
    def run(self):
        self.sig_status.emit(T("正在初始化采集设备…"))
        cap = AudioCapture(device_id=self.device_id, is_loopback=self.is_loopback)
        try:
            cap.open()
        except Exception as e:
            self.sig_error.emit(T("打开采集设备失败：{error}\n请检查设备是否被占用，或点击「刷新」重选设备。",
                                  error=e))
            return
        try:
            mode = T("扬声器输出(回环)") if self.is_loopback else T("麦克风")
            self.sig_status.emit(T("正在监听【{mode}】… 请演奏乐器", mode=mode))
            diag.dbg(f"audio_started device={self.device_id} loopback={self.is_loopback} mode={mode}")
            err_count = 0
            last_keys_emit = 0.0
            blocks = 0
            notes_total = 0
            while not self._stop:
                self.detector.set_sensitivity(self.sensitivity)
                block = cap.read_block()
                if block is None:
                    err_count += 1
                    if err_count > 40:
                        self.sig_error.emit(T("连续读取音频失败，采集已中断。请刷新设备后重试。"))
                        break
                    continue
                err_count = 0
                blocks += 1
                res = self.detector.feed(block)
                for f in self.screener.process(block, self.detector):
                    self.sig_finding.emit(dict(f))
                if blocks % 24 == 0:
                    summ = self.screener.summary()
                    if summ != self._last_screen:
                        self._last_screen = summ
                        self.sig_screen.emit(summ)
                notes_total += len(res["note_events"])
                if blocks % 240 == 0:
                    diag.dbg(f"alive blocks={blocks} active={len(self._active_labels)} notes_total={notes_total}")
                now = time.time()

                # 活跃键位（去抖后发射）
                new_active = set(res["keys"].keys())
                if new_active != self._active_labels or (now - last_keys_emit > 0.12 and new_active):
                    self._active_labels = new_active
                    last_keys_emit = now
                    self.sig_keys.emit(set(new_active))

                for ev in res["note_events"]:
                    self.sig_note.emit(ev)

                if res["chord"] != self._last_chord:
                    # 和弦变化（包括"没有和弦"）都要发出：否则弹旋律时会一直挂着上一个和弦
                    self._last_chord = res["chord"]
                    self.sig_chord.emit(res["chord"])
                if res["tonality"] and res["tonality"] != self._last_key:
                    self._last_key = res["tonality"]
                    self.sig_tonality.emit(res["tonality"])

                bpm = res["bpm"]
                if bpm is None:
                    if self._last_bpm is not None:
                        self._last_bpm = None
                        self.sig_bpm.emit(float("nan"))
                else:
                    if (self._last_bpm is None or abs(bpm - self._last_bpm) >= 0.05) and now - self._last_bpm_t >= 0.25:
                        self._last_bpm = bpm
                        self._last_bpm_t = now
                        self.sig_bpm.emit(bpm)
                    t_audio = res["t"]
                    if t_audio - self._last_sample_t >= BPM_SAMPLE_S:
                        self._last_sample_t = t_audio
                        self.sig_bpm_sample.emit(t_audio, bpm)
        except Exception as e:
            diag.dbg(f"audio_loop_error {e!r}")
            self.sig_error.emit(T("采集线程异常：{error}", error=e))
        finally:
            try:
                cap.close()
            except Exception:
                pass
            self.sig_status.emit(T("已停止"))


# ================================================================ 主窗口
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = settings.load()
        self._update_info = None
        self._update_checker = None
        self._update_downloader = None
        self._update_dialog = None
        self._settings_dialog = None
        self.setWindowTitle(f"{T('原神乐器演奏检测器')} v{APP_VERSION}")
        self.worker = None
        self.instruments = all_instruments()
        self._t_offset = 0.0         # 多次开始/停止：时间接着上一次往后记
        self._build_ui()
        self._fit_to_screen()
        self.refresh_devices()
        self.on_instrument_changed()
        self.statusBar().showMessage(T("就绪 — 选择乐器与采集设备后点击「开始监听」"))
        self._chart_timer = QTimer(self)
        self._chart_timer.setInterval(400)
        self._chart_timer.timeout.connect(self._tick_chart)
        self._chart_timer.start()
        if self.cfg.get("check_updates", "1") == "1" and not os.environ.get("GID_NO_UPDATE"):
            QTimer.singleShot(1800, lambda: self.check_updates(silent=True))

    def showEvent(self, e):
        super().showEvent(e)
        if not self._split_init:
            # 首次显示时按实际高度分配三块区域：琴键/指标 30%、BPM 图 30%、时长表 40%
            self._split_init = True
            h = max(300, self.split.height())
            self.split.setSizes([int(h * 0.44), int(h * 0.25), int(h * 0.31)])

    def _fit_to_screen(self):
        self.setMinimumSize(1000, 700)
        scr = QApplication.primaryScreen()
        if scr is not None:
            g = scr.availableGeometry()
            self.resize(min(1360, int(g.width() * 0.92)), min(920, int(g.height() * 0.92)))
        else:
            self.resize(1360, 920)

    # ------------------------------------------------------------ UI 构建
    def _build_ui(self):
        central = QWidget()
        central.setObjectName("root")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 12, 16, 6)
        root.setSpacing(10)

        # ---- 顶栏：标题 / 监听状态 / 操作
        top = QHBoxLayout()
        top.setSpacing(10)
        icon_path = _resource_path("app.ico")
        if os.path.exists(icon_path):
            logo = QLabel()
            logo.setPixmap(QIcon(icon_path).pixmap(26, 26))
            top.addWidget(logo)
        title = QLabel(T("原神乐器演奏检测器"))
        title.setObjectName("appTitle")
        top.addWidget(title)
        ver = QLabel(f"v{APP_VERSION}")
        ver.setObjectName("appVer")
        top.addWidget(ver, 0, Qt.AlignmentFlag.AlignBottom)
        top.addSpacing(12)
        self.pill = QLabel(T("○  未在监听"))
        self.pill.setObjectName("pill")
        self.pill.setProperty("state", "off")
        top.addWidget(self.pill)
        self.btn_screen = QPushButton(T("排查  未发现异常"))
        self.btn_screen.setObjectName("pillBtn")
        self.btn_screen.setProperty("state", "ok")
        self.btn_screen.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_screen.setToolTip(T("边界值排查：找出超出人手极限的操作（点击查看）"))
        self.btn_screen.clicked.connect(lambda: self._set_page(1))
        top.addWidget(self.btn_screen)
        self.btn_update = QPushButton("")
        self.btn_update.setObjectName("pillBtn")
        self.btn_update.setProperty("state", "warn")
        self.btn_update.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_update.clicked.connect(self._open_release_page)
        self.btn_update.hide()
        top.addWidget(self.btn_update)
        top.addStretch(1)
        self.btn_settings = QPushButton()
        self.btn_settings.setObjectName("pillBtn")
        self.btn_settings.setIcon(_gear_icon(C["dim"]))
        self.btn_settings.setIconSize(QSize(19, 19))
        self.btn_settings.setFixedWidth(38)
        self.btn_settings.setToolTip(T("设置"))
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.clicked.connect(self.open_settings)
        top.addWidget(self.btn_settings)
        self.btn_export = QPushButton(T("导出记录"))
        self.btn_export.setToolTip(T("把每个音的时长表、BPM 随时间的记录、边界值排查结果导出为 CSV（Excel 可直接打开）"))
        self.btn_export.clicked.connect(self.on_export)
        top.addWidget(self.btn_export)
        self.btn_clear = QPushButton(T("清空记录"))
        self.btn_clear.clicked.connect(self.on_clear)
        top.addWidget(self.btn_clear)
        self.btn_start = QPushButton(T("▶  开始监听"))
        self.btn_start.setObjectName("primary")
        self.btn_start.setCheckable(True)
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.clicked.connect(self.on_start_stop)
        top.addWidget(self.btn_start)
        root.addLayout(top)

        # ---- 设置条
        bar = Card()
        bl = QHBoxLayout()
        bl.setSpacing(10)
        bar.body.setContentsMargins(16, 10, 16, 10)
        bar.body.addLayout(bl)
        bl.addWidget(self._field(T("乐器")))
        self.cmb_instrument = QComboBox()
        for inst in self.instruments:
            self.cmb_instrument.addItem(T(inst.name))
        self.cmb_instrument.setMinimumWidth(130)
        self.cmb_instrument.currentIndexChanged.connect(self.on_instrument_changed)
        bl.addWidget(self.cmb_instrument)
        bl.addSpacing(8)
        bl.addWidget(self._field(T("移调")))
        self.spin_transpose = QSpinBox()
        self.spin_transpose.setRange(-12, 12)
        self.spin_transpose.setValue(0)
        self.spin_transpose.setFixedWidth(66)
        self.spin_transpose.setToolTip(T("音高基准校准（半音）。若检测出的八度与实际不符，用此项整体平移。"))
        self.spin_transpose.valueChanged.connect(self.on_instrument_changed)
        bl.addWidget(self.spin_transpose)
        bl.addSpacing(8)
        bl.addWidget(self._field(T("采集设备")))
        self.cmb_device = QComboBox()
        self.cmb_device.setMinimumWidth(260)
        self.cmb_device.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        bl.addWidget(self.cmb_device, 1)
        self.btn_refresh = QPushButton(T("刷新"))
        self.btn_refresh.setToolTip(T("重新扫描扬声器 / 麦克风"))
        self.btn_refresh.clicked.connect(self.refresh_devices)
        bl.addWidget(self.btn_refresh)
        bl.addSpacing(8)
        bl.addWidget(self._field(T("灵敏度")))
        self.slider_sens = QSlider(Qt.Orientation.Horizontal)
        self.slider_sens.setRange(10, 100)
        self.slider_sens.setValue(55)
        self.slider_sens.setFixedWidth(130)
        self.lab_sens = self._field("55%")
        self.lab_sens.setMinimumWidth(34)
        self.slider_sens.valueChanged.connect(self._on_sens)
        bl.addWidget(self.slider_sens)
        bl.addWidget(self.lab_sens)
        root.addWidget(bar)

        # ---- 主体：三块可拖动调整大小
        split = QSplitter(Qt.Orientation.Vertical)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(10)

        top_row = QWidget()
        tr = QHBoxLayout(top_row)
        tr.setContentsMargins(0, 0, 0, 0)
        tr.setSpacing(10)
        keys_card = Card(T("琴键"), T("高亮 = 正在发音"))
        self.btn_hints = QPushButton(T("键位提示"))
        self.btn_hints.setObjectName("pillBtn")
        self.btn_hints.setCheckable(True)
        self.btn_hints.setChecked(True)
        self.btn_hints.setToolTip(T("在琴键左上角显示电脑键盘字母，关闭后只保留游戏内键面。"))
        self.btn_hints.toggled.connect(lambda on: self.key_panel.set_hints(on))
        keys_card.head.addWidget(self.btn_hints)
        keys_card.body.setContentsMargins(10, 6, 10, 8)
        self.key_panel = KeyPanel()
        self.key_panel.setMinimumHeight(150)
        keys_card.body.addWidget(self.key_panel, 1)
        tr.addWidget(keys_card, 3)

        info = QWidget()
        ig = QGridLayout(info)
        ig.setContentsMargins(0, 0, 0, 0)
        ig.setSpacing(10)
        self.lab_notes = MetricTile(T("当前按键"), "cyan")
        self.lab_chord = MetricTile(T("和弦"), "green")
        self.lab_key = MetricTile(T("调性"), "violet")
        self.lab_bpm = MetricTile(T("当前 BPM"), "gold", big=True, mono=True)
        ig.addWidget(self.lab_notes, 0, 0)
        ig.addWidget(self.lab_chord, 0, 1)
        ig.addWidget(self.lab_key, 1, 0)
        ig.addWidget(self.lab_bpm, 1, 1)
        ig.setRowStretch(0, 1)
        ig.setRowStretch(1, 1)
        ig.setColumnStretch(0, 1)
        ig.setColumnStretch(1, 1)
        tr.addWidget(info, 2)
        split.addWidget(top_row)

        chart_card = Card(T("BPM 变化"), T("每 0.5 秒一个点，纵轴随数据自动缩放，鼠标悬停看具体读数"))
        self.chart = BpmChart()
        self.chart.stats_changed.connect(self.lab_bpm.setSub)
        chart_card.body.addWidget(self.chart, 1)
        split.addWidget(chart_card)

        tab_card = Card()
        th = QHBoxLayout()
        th.setSpacing(10)
        tabs = QFrame()
        tabs.setObjectName("tabs")
        tl = QHBoxLayout(tabs)
        tl.setContentsMargins(3, 3, 3, 3)
        tl.setSpacing(2)
        self.page_group = QButtonGroup(self)
        self.page_group.setExclusive(True)
        self.page_btns = []
        for i, name in enumerate((T("每个音的时长"), T("边界值排查"))):
            b = QPushButton(name)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setChecked(i == 0)
            self.page_group.addButton(b, i)
            tl.addWidget(b)
            self.page_btns.append(b)
        self.page_group.idClicked.connect(self._set_page)
        th.addWidget(tabs)
        self.tab_hint = QLabel("")
        self.tab_hint.setObjectName("cardHint")
        th.addWidget(self.tab_hint)
        th.addStretch(1)
        tab_card.body.addLayout(th)
        self.pages = QStackedWidget()
        self.notes = NotesModel(self)
        self.table = NotesView()
        self.table.setModel(self.notes)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(30)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        hh.setHighlightSections(False)
        hh.setStretchLastSection(False)
        self.pages.addWidget(self.table)

        page = QWidget()
        pv = QVBoxLayout(page)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(8)
        self.screen_summary = QLabel("")
        self.screen_summary.setObjectName("screenSummary")
        self.screen_summary.setWordWrap(True)
        pv.addWidget(self.screen_summary)
        self.findings = FindingsModel(self)
        self.ftable = FindingsView()
        self.ftable.setModel(self.findings)
        self.ftable.setAlternatingRowColors(True)
        self.ftable.setShowGrid(False)
        self.ftable.setWordWrap(False)
        self.ftable.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.ftable.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.ftable.verticalHeader().setVisible(False)
        self.ftable.verticalHeader().setDefaultSectionSize(30)
        fh = self.ftable.horizontalHeader()
        fh.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        fh.setHighlightSections(False)
        fh.setStretchLastSection(False)
        pv.addWidget(self.ftable, 1)
        self.pages.addWidget(page)
        tab_card.body.addWidget(self.pages, 1)
        split.addWidget(tab_card)
        self._screen_text = ""
        self._worker_serial = 0
        self._update_table_hint()
        self._update_screen()

        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 3)
        split.setStretchFactor(2, 4)
        self.split = split
        self._split_init = False
        root.addWidget(split, 1)
        self.statusBar().setSizeGripEnabled(False)

    # ------------------------------------------------------------ 小工具
    @staticmethod
    def _field(text):
        lab = QLabel(text)
        lab.setObjectName("field")
        return lab

    def _on_sens(self, v):
        self.lab_sens.setText(f"{v}%")
        if self.worker is not None:
            self.worker.sensitivity = v / 100.0

    def _set_pill(self, text, state):
        self.pill.setText(text)
        self.pill.setProperty("state", state)
        _repolish(self.pill)

    def _screen_help(self):
        return T("检查两类超出人手极限的操作：① 同时按下超过 10 个键（人只有 10 根手指）；"
                 "② 很长一段连续音的间隔完全一致（机器级精度）。原神的声音按约 21 ms 一块发出，"
                 "短的轮指人手也会显得完全一致，所以只报很长的段。结果是证据而非定论。")

    def _set_page(self, i):
        self.page_btns[i].setChecked(True)
        self.pages.setCurrentIndex(i)
        self._update_table_hint()

    def _update_screen(self):
        lim, sus = self.findings.counts()
        if lim:
            text = T("排查  ⚠ 超出人手极限 {n} 处", n=lim)
            if sus:
                text += T(" · 疑似 {n} 处", n=sus)
            state = "bad"
        elif sus:
            text, state = T("排查  ⚠ 疑似机械操作 {n} 处", n=sus), "warn"
        else:
            text, state = T("排查  未发现异常"), "ok"
        self.btn_screen.setText(text)
        self.btn_screen.setProperty("state", state)
        _repolish(self.btn_screen)
        n = lim + sus
        self.page_btns[1].setText(T("边界值排查  {n}", n=n) if n else T("边界值排查"))
        head = self._screen_text or T("还没有数据。")
        self.screen_summary.setText(f"<b>{head}</b><br>{self._screen_help()}")
        self._update_table_hint()

    def on_finding(self, f):
        new = self.findings.upsert((self._worker_serial, f["id"]), f, self._t_offset)
        self._update_screen()
        if new:
            self.statusBar().showMessage(
                T("边界值排查：{time}  {title}（{level}）",
                  time=_fmt_time(f['t'] + self._t_offset), title=f['title'], level=level_text(f['level'])),
                15000)

    def on_screen_summary(self, s):
        self._screen_text = s
        self._update_screen()

    def _update_table_hint(self):
        if getattr(self, "pages", None) is not None and self.pages.currentIndex() == 1:
            self.tab_hint.setText(T("最新在上 · 鼠标停在一行上看完整说明"))
            return
        n = self.notes.rowCount()
        self.page_btns[0].setText(T("每个音的时长  {n}", n=n) if n else T("每个音的时长"))
        self.tab_hint.setText(T("最新在上，最多保留 {n} 条", n=NOTES_KEEP) if n
                              else T("演奏后逐条记录每个音"))

    def _tick_chart(self):
        if self.chart.dirty:
            self.chart.refresh()

    def refresh_chart(self):
        self.chart.refresh()

    # ------------------------------------------------------------ 事件
    def refresh_devices(self):
        self.cmb_device.blockSignals(True)
        self.cmb_device.clear()
        sources = list_sources()
        default_id = default_loopback_id()
        sel = 0
        for i, (dev_id, name, kind) in enumerate(sources):
            tag = T("（扬声器输出·回环）") if kind == "loopback" else T("（麦克风）")
            self.cmb_device.addItem(f"{name} {tag}", (dev_id, kind == "loopback"))
            if dev_id == default_id:
                sel = i
        if self.cmb_device.count() == 0:
            self.cmb_device.addItem(T("（未找到可用采集设备）"), (None, True))
        self.cmb_device.setCurrentIndex(min(sel, self.cmb_device.count() - 1))
        self.cmb_device.blockSignals(False)

    def on_instrument_changed(self):
        idx = self.cmb_instrument.currentIndex()
        transpose = self.spin_transpose.value()
        base = self.instruments[idx]
        # 用同一布局但带移调的新乐器对象
        from instruments import build_lyre21, build_horn, build_youko
        if base.name == "晚风圆号":
            inst = build_horn(transpose=transpose)
        elif base.name == "悠可琴":
            inst = build_youko(transpose=transpose)
        else:
            inst = build_lyre21(base.name, transpose=transpose)
        inst.note = base.note
        self.key_panel.set_instrument(inst)
        self._current_inst = inst
        if self.worker is not None:
            self.restart_worker()

    def on_start_stop(self):
        if self.worker is not None:
            self.stop_worker()
            self.btn_start.setChecked(False)
            self.btn_start.setText(T("▶  开始监听"))
            return
        self.start_worker()

    def start_worker(self):
        if self.worker is not None:
            return
        if self.cmb_device.count() == 0:
            QMessageBox.warning(self, T("提示"), T("未找到可用采集设备。"))
            self.btn_start.setChecked(False)
            return
        dev_id, is_loop = self.cmb_device.currentData()
        if dev_id is None:
            QMessageBox.warning(self, T("提示"), T("请先刷新并选择采集设备。"))
            self.btn_start.setChecked(False)
            return
        # 接着已有记录往后计时（停止后再开始、换乐器重启时，表格与 BPM 图不会从 0 重叠）
        last_note = self.notes.rows[-1]["raw"][0] if self.notes.rows else 0.0
        self._t_offset = max(self.chart.last_time(), last_note) + (1.0 if (self.notes.rows or self.chart.t) else 0.0)
        self.worker = DetectWorker(
            self._current_inst, dev_id, is_loop,
            self.slider_sens.value() / 100.0, parent=self)
        self.worker.sig_keys.connect(self.on_keys)
        self.worker.sig_note.connect(self.on_note)
        self.worker.sig_chord.connect(self.lab_chord.setText)
        self.worker.sig_tonality.connect(self.lab_key.setText)
        self.worker.sig_bpm.connect(self.on_bpm)
        self.worker.sig_bpm_sample.connect(self.on_bpm_sample)
        self._worker_serial += 1
        self.worker.sig_finding.connect(self.on_finding)
        self.worker.sig_screen.connect(self.on_screen_summary)
        self.worker.sig_status.connect(self._on_status)
        self.worker.sig_error.connect(self.on_error)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()
        self.btn_start.setChecked(True)
        self.btn_start.setText(T("■  停止监听"))
        self._set_pill(T("●  正在启动…"), "on")

    def _on_status(self, s):
        self.statusBar().showMessage(s)
        if s.startswith(T("正在监听")):
            self._set_pill("●  " + T("正在监听"), "on")
        elif s == T("已停止"):
            self._set_pill(T("○  未在监听"), "off")

    def stop_worker(self):
        w = self.worker
        if w is not None:
            w.stop()
            if not w.wait(5000):
                # 采集后端卡住时不能直接丢掉 QThread：先终止，再等待退出。
                w.terminate()
                w.wait(2000)
            if w.isFinished():
                self.worker = None
            else:
                diag.dbg("worker_still_running_after_stop")
        self.key_panel.set_active(set())
        self.lab_notes.setText("—")
        self.lab_chord.setText("—")
        self.lab_bpm.setText("—")
        self._set_pill(T("○  未在监听"), "off")

    def restart_worker(self):
        if self.worker is not None:
            running = self.btn_start.isChecked()
            self.stop_worker()
            if running:
                self.btn_start.setChecked(True)
                self.start_worker()

    def on_worker_finished(self):
        w = self.sender()
        if self.worker is not None and w is self.worker and self.worker.isFinished():
            self.worker = None
        if self.worker is None:
            self.btn_start.setChecked(False)
            self.btn_start.setText(T("▶  开始监听"))
            if self.pill.property("state") != "err":
                self._set_pill(T("○  未在监听"), "off")

    def closeEvent(self, e):
        if self.worker is not None:
            w = self.worker
            w.stop()
            if not w.wait(5000):
                w.terminate()
                w.wait(2000)
            if w.isFinished():
                self.worker = None
        super().closeEvent(e)

    def on_error(self, msg):
        self.stop_worker()
        self._set_pill(T("●  采集出错"), "err")
        QMessageBox.critical(self, T("采集错误"), msg)

    # ------------------------------------------------------------ 数据显示
    def on_keys(self, labels):
        self.key_panel.set_active(labels)
        names = []
        key_map = {k[0]: k for k in self._current_inst.keys}
        for ch in "QWERTYUIOPASDFGHJKLZXCVBNM":
            if ch in labels:
                entry = key_map.get(ch)
                if entry and entry[2] == "pitch":
                    names.append(f"{ch}·{midi_to_name(entry[1])}")
                elif entry:
                    names.append(f"{ch}·{entry[3]}")
        self.lab_notes.setText("  ".join(names) if names else "—")

    def on_note(self, ev):
        t = ev["t"] + self._t_offset
        notes = []
        if ev.get("end"):
            notes.append(end_reason_text(ev["end"]))
        if ev.get("approx"):
            notes.append(T("≈吸附"))
        ioi = ev.get("ioi_ms")
        end_text = " · ".join(notes)
        raw = (t, ev["key"], ev["name"], ev["solfege"] or "", ev["dur_ms"], ioi, end_text)
        disp = [_fmt_time(t), ev["key"], ev["name"], ev["solfege"] or "—", f"{ev['dur_ms']:.0f}",
                "—" if ioi is None else f"{ioi:.0f}", end_text]
        self.notes.add(raw, disp, ev.get("end") or "")
        self._update_table_hint()

    def on_bpm(self, bpm):
        self.lab_bpm.setText("—" if math.isnan(bpm) else f"{bpm:.1f}")

    def on_bpm_sample(self, t, bpm):
        self.chart.add(t + self._t_offset, bpm)

    def on_export(self):
        if not self.notes.rows and not self.chart.t and not self.findings.rows:
            QMessageBox.information(self, T("导出记录"), T("还没有记录可以导出。"))
            return
        base_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(base_dir):
            base_dir = os.path.expanduser("~")
        stamp = time.strftime("%Y%m%d_%H%M%S")
        default = os.path.join(base_dir, T("演奏记录_{timestamp}.csv", timestamp=stamp))
        path, _ = QFileDialog.getSaveFileName(self, T("导出记录"), default, T("CSV 表格 (*.csv)"))
        if not path:
            return
        root, ext = os.path.splitext(path)
        if not ext:
            path = root + ".csv"
        bpm_path = os.path.splitext(path)[0] + "_BPM.csv"
        scr_path = os.path.splitext(path)[0] + T("_排查.csv")
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow([T("开始时间(s)"), T("按键"), T("音名"), T("唱名"),
                            T("时长(ms)"), T("间隔(ms)"), T("结束方式")])
                for r in self.notes.rows:
                    t, key, name, sol, dur, ioi, end = r["raw"]
                    w.writerow([f"{t:.3f}", key, name, sol, f"{dur:.0f}", "" if ioi is None else f"{ioi:.0f}", end])
            with open(bpm_path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow([T("时间(s)"), "BPM"])
                for t, v in zip(self.chart.t, self.chart.v):
                    w.writerow([f"{t:.1f}", f"{v:.1f}"])
            with open(scr_path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow([T("时间(s)"), T("检查项"), T("结论"), T("现象"), T("说明")])
                for r in self.findings.rows:
                    ff = r["f"]
                    w.writerow([f"{r['t']:.3f}", kind_text(ff["kind"]), level_text(ff["level"]),
                                ff.get("title", ""), ff.get("text", "")])
                if self._screen_text:
                    w.writerow([])
                    w.writerow([T("总结"), self._screen_text])
        except OSError as e:
            QMessageBox.critical(self, T("导出失败"), T("写入文件失败：{error}", error=e))
            return
        files = T("、").join([os.path.basename(path), os.path.basename(bpm_path), os.path.basename(scr_path)])
        self.statusBar().showMessage(T("已导出：{files}（{dir}）", files=files, dir=os.path.dirname(path)), 10000)

    def on_clear(self):
        self.key_panel.set_active(set())
        for tile in (self.lab_notes, self.lab_chord, self.lab_key, self.lab_bpm):
            tile.setText("—")
        self.lab_bpm.setSub("")
        self.chart.clear()
        self.notes.clear()
        self.findings.clear()
        self._screen_text = ""
        self._update_table_hint()
        self._update_screen()
        self._t_offset = 0.0
        if self.worker is not None:
            self.worker.detector.reset()
            self.worker.screener.reset()
            self.worker._last_screen = None
            self.worker._last_sample_t = -1e9
        self.statusBar().showMessage(T("记录已清空"))

    # ------------------------------------------------------------ 设置 / 主题 / 更新
    def apply_theme_change(self):
        """主题切换后刷新自绘元素与指标卡。"""
        self.chart.apply_theme()
        for tile in (self.lab_notes, self.lab_chord, self.lab_key, self.lab_bpm):
            tile.apply_theme()
        self.table.viewport().update()
        self.ftable.viewport().update()
        self.key_panel.update()
        self.btn_settings.setIcon(_gear_icon(C["dim"]))
        self.update()

    def set_theme(self, mode):
        eff = set_theme_mode(QApplication.instance(), mode)
        self.cfg["theme"] = mode
        self.apply_theme_change()
        return eff

    def on_system_theme_changed(self):
        if THEME_MODE == "system":
            apply_theme(QApplication.instance(), "system")
            self.apply_theme_change()

    def open_settings(self):
        dlg = SettingsDialog(self)
        self._settings_dialog = dlg
        dlg.exec()
        self._settings_dialog = None

    def check_updates(self, silent=False):
        if self._update_checker is not None:
            return
        if not silent:
            self.statusBar().showMessage(T("正在检查更新…"))
        self._update_checker = UpdateChecker(self)
        self._update_checker.done.connect(lambda p: self._on_update_result(p, silent))
        self._update_checker.check()

    def _on_update_result(self, payload, silent):
        self._update_checker = None
        if not payload.get("ok"):
            if not silent:
                self.statusBar().showMessage(
                    T("检查更新失败：{error}", error=update_error_text(payload)), 12000)
            return
        if payload.get("update"):
            self._update_info = payload
            self.btn_update.setText(T("更新 v{version}", version=payload.get("latest", "")))
            self.btn_update.show()
            if not silent:
                self.statusBar().showMessage(
                    T("发现新版本 v{version}", version=payload.get("latest", "")), 12000)
            if self.cfg.get("auto_update", "0") == "1":
                QTimer.singleShot(0, lambda: self.start_auto_update(payload))
        else:
            self._update_info = None
            self.btn_update.hide()
            if not silent:
                self.statusBar().showMessage(T("已是最新版本。"), 8000)

    def _open_release_page(self):
        url = (self._update_info or {}).get("url") or f"{APP_URL}/releases/latest"
        if valid_release_url(url):
            QDesktopServices.openUrl(QUrl(url))
        else:
            QDesktopServices.openUrl(QUrl(f"{APP_URL}/releases/latest"))

    def start_auto_update(self, payload):
        """下载并校验安装包，然后静默启动安装程序。只在打包后的 exe 中执行。"""
        if self._update_downloader is not None:
            return
        if not getattr(sys, "frozen", False):
            self.statusBar().showMessage(T("当前为源码运行模式，已为你打开下载页面。"), 12000)
            self._open_release_page()
            return
        latest = payload.get("latest", "")
        name = f"GenshinInstrumentDetector-{latest}-win64-setup.exe"
        setup = next((a for a in payload.get("assets", []) if a.get("name") == name), None)
        if setup is None or not setup.get("sha256"):
            QMessageBox.warning(self, T("更新"), T("未找到适用于当前版本的安装包。"))
            return
        self._update_dialog = QProgressDialog(T("正在下载更新…"), T("取消"), 0, 100, self)
        self._update_dialog.setWindowTitle(T("更新"))
        self._update_dialog.setMinimumDuration(0)
        self._update_dialog.setAutoClose(False)
        self._update_dialog.setAutoReset(False)
        self._update_dialog.setValue(0)
        self._update_dialog.canceled.connect(self._cancel_update)
        self._update_dialog.show()
        self._update_downloader = UpdateDownloader(
            setup["url"], setup["sha256"], int(setup.get("size") or 0), self)
        self._update_downloader.progress.connect(self._update_dialog.setValue)
        self._update_downloader.done.connect(self._on_update_downloaded)
        self._update_downloader.failed.connect(self._on_update_failed)
        self._update_downloader.start()

    def _cancel_update(self):
        if self._update_downloader is not None:
            self._update_downloader.cancel()
            self._update_downloader.deleteLater()
            self._update_downloader = None
        self._close_update_dialog()
        self.statusBar().showMessage(T("已取消更新。"), 8000)

    def _close_update_dialog(self):
        if self._update_dialog is not None:
            self._update_dialog.close()
            self._update_dialog.deleteLater()
            self._update_dialog = None

    def _on_update_downloaded(self, path):
        if self._update_downloader is not None:
            self._update_downloader.deleteLater()
            self._update_downloader = None
        self._close_update_dialog()
        if not getattr(sys, "frozen", False):
            QMessageBox.information(self, T("更新"), T("更新已下载，请手动运行安装程序。"))
            return
        args = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]
        try:
            res = QProcess.startDetached(path, args)
            ok = res[0] if isinstance(res, tuple) else bool(res)
        except Exception:
            ok = False
        if not ok:
            QMessageBox.critical(self, T("更新"), T("安装程序启动失败。"))
            return
        self.statusBar().showMessage(T("正在安装更新…"), 5000)
        QTimer.singleShot(150, QApplication.quit)

    def _on_update_failed(self, error):
        if self._update_downloader is not None:
            self._update_downloader.deleteLater()
            self._update_downloader = None
        self._close_update_dialog()
        QMessageBox.warning(self, T("更新"),
                            T("更新下载失败：{error}", error=download_error_text(error)))

    def restart_app(self):
        if self.worker is not None:
            self.stop_worker()
        if getattr(sys, "frozen", False):
            program, args = sys.executable, sys.argv[1:]
        else:
            program = sys.executable
            args = [os.path.abspath(sys.argv[0])] + sys.argv[1:]
        try:
            res = QProcess.startDetached(program, args)
            ok = res[0] if isinstance(res, tuple) else bool(res)
        except Exception:
            ok = False
        if not ok:
            QMessageBox.critical(self, T("设置"), T("重启失败，请手动重新打开程序。"))
            return
        QApplication.quit()


def update_error_text(payload: dict) -> str:
    code = payload.get("error")
    if code == "timeout":
        return T("请求超时。")
    if code == "network":
        return T("网络请求失败，请检查网络连接或代理设置。")
    if code == "http":
        return T("GitHub 返回了异常响应（HTTP {code}）。", code=payload.get("code"))
    if code in ("json", "version"):
        return T("更新信息格式不正确。")
    if code == "too_large":
        return T("更新信息格式不正确。")
    return T("未知错误。")


def download_error_text(error: str) -> str:
    mapping = {
        "invalid": T("更新信息格式不正确。"),
        "io": T("无法写入更新临时文件。"),
        "timeout": T("请求超时。"),
        "network": T("网络请求失败，请检查网络连接或代理设置。"),
        "http": T("下载更新失败（HTTP 错误）。"),
        "too_large": T("更新安装包过大，已取消下载。"),
        "size": T("更新文件大小不正确，已取消安装。"),
        "checksum": T("更新文件校验失败，已取消安装。"),
        "format": T("更新文件格式不正确，已取消安装。"),
    }
    return mapping.get(error, T("未知错误。"))


class SettingsDialog(QDialog):
    """设置窗口：语言、主题、更新检查、关于。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle(T("设置"))
        self.setModal(True)
        self.setMinimumWidth(560)
        self._orig_theme = parent.cfg.get("theme", "system") if parent else "system"
        self._release_url = ""
        self._checker = None

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(12)

        # 语言
        lang_box = QGroupBox(T("语言"))
        lv = QVBoxLayout(lang_box)
        lv.setContentsMargins(14, 16, 14, 12)
        self.cmb_lang = QComboBox()
        for code, label in i18n.LANGUAGES:
            self.cmb_lang.addItem(label, code)
        cur = i18n.current()
        idx = self.cmb_lang.findData(cur)
        if idx >= 0:
            self.cmb_lang.setCurrentIndex(idx)
        lv.addWidget(self.cmb_lang)
        self.lab_lang_note = QLabel(T("语言更改需要重启应用后生效。"))
        self.lab_lang_note.setObjectName("cardHint")
        lv.addWidget(self.lab_lang_note)
        root.addWidget(lang_box)

        # 主题
        theme_box = QGroupBox(T("主题"))
        tv = QVBoxLayout(theme_box)
        tv.setContentsMargins(14, 16, 14, 12)
        self.cmb_theme = QComboBox()
        for mode, label in (("system", T("跟随系统")), ("dark", T("深色")), ("light", T("浅色"))):
            self.cmb_theme.addItem(label, mode)
        idx = self.cmb_theme.findData(self._orig_theme)
        self.cmb_theme.setCurrentIndex(max(0, idx))
        self.cmb_theme.currentIndexChanged.connect(self._preview_theme)
        tv.addWidget(self.cmb_theme)
        root.addWidget(theme_box)

        # 更新
        upd_box = QGroupBox(T("更新"))
        uv = QVBoxLayout(upd_box)
        uv.setContentsMargins(14, 16, 14, 12)
        uv.setSpacing(8)
        self.lab_cur = QLabel(T("当前版本：{version}", version=APP_VERSION))
        uv.addWidget(self.lab_cur)
        self.chk_updates = QCheckBox(T("自动检查更新"))
        self.chk_updates.setChecked((parent.cfg.get("check_updates", "0") if parent else "0") == "1")
        uv.addWidget(self.chk_updates)
        self.chk_auto = QCheckBox(T("发现新版本后自动下载并安装"))
        self.chk_auto.setChecked((parent.cfg.get("auto_update", "0") if parent else "0") == "1")
        self.chk_auto.setToolTip(T("自动下载安装包并用 SHA-256 校验，校验通过后静默安装并重启应用。"))
        uv.addWidget(self.chk_auto)
        row = QHBoxLayout()
        self.btn_check = QPushButton(T("检查更新"))
        self.btn_check.clicked.connect(self._check_updates)
        self.btn_open = QPushButton(T("打开下载页面"))
        self.btn_open.clicked.connect(self._open_release)
        self.btn_open.hide()
        row.addWidget(self.btn_check)
        row.addWidget(self.btn_open)
        row.addStretch(1)
        uv.addLayout(row)
        self.lab_upd = QLabel(T("更新检查由 GitHub Releases 提供。"))
        self.lab_upd.setObjectName("cardHint")
        self.lab_upd.setWordWrap(True)
        uv.addWidget(self.lab_upd)
        root.addWidget(upd_box)

        # 关于
        about_box = QGroupBox(T("关于"))
        av = QHBoxLayout(about_box)
        av.setContentsMargins(14, 16, 14, 12)
        av.addWidget(QLabel(f"{T('原神乐器演奏检测器')}  v{APP_VERSION}"))
        av.addStretch(1)
        self.btn_home = QPushButton(T("打开项目主页"))
        self.btn_home.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(APP_URL)))
        av.addWidget(self.btn_home)
        root.addWidget(about_box)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_cancel = QPushButton(T("取消"))
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton(T("保存"))
        self.btn_save.setObjectName("primary")
        self.btn_save.clicked.connect(self._save)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_save)
        root.addLayout(btns)

    def _preview_theme(self):
        if self.parent_window is not None:
            self.parent_window.set_theme(self.cmb_theme.currentData())

    def _check_updates(self):
        self.btn_check.setEnabled(False)
        self.btn_open.hide()
        self.lab_upd.setText(T("正在检查更新…"))
        self._checker = UpdateChecker(self)
        self._checker.done.connect(self._on_update)
        self._checker.check()

    def _on_update(self, payload):
        self.btn_check.setEnabled(True)
        if not payload.get("ok"):
            self.lab_upd.setText(T("检查更新失败：{error}", error=update_error_text(payload)))
            return
        if payload.get("update"):
            self._release_url = payload.get("url", "")
            self.lab_upd.setText(T("发现新版本 v{version}", version=payload.get("latest", "")))
            self.btn_open.show()
            if (self.parent_window is not None
                    and self.parent_window.cfg.get("auto_update", "0") == "1"):
                self.accept()
                QTimer.singleShot(0, lambda: self.parent_window.start_auto_update(payload))
                return
        else:
            self._release_url = ""
            self.btn_open.hide()
            self.lab_upd.setText(T("已是最新版本。"))

    def _open_release(self):
        if valid_release_url(self._release_url):
            QDesktopServices.openUrl(QUrl(self._release_url))
        else:
            QDesktopServices.openUrl(QUrl(f"{APP_URL}/releases/latest"))

    def _save(self):
        lang = self.cmb_lang.currentData()
        theme = self.cmb_theme.currentData()
        auto = "1" if self.chk_updates.isChecked() else "0"
        auto_install = "1" if self.chk_auto.isChecked() else "0"
        ok = settings.save({"language": lang, "theme": theme,
                            "check_updates": auto, "auto_update": auto_install})
        if not ok:
            QMessageBox.warning(self, T("设置"), T("设置保存失败，请检查目录权限。"))
        if self.parent_window is not None:
            self.parent_window.cfg.update({"language": lang, "theme": theme,
                                           "check_updates": auto, "auto_update": auto_install})
        changed = lang != i18n.current()
        self.accept()
        if changed and self.parent_window is not None:
            box = QMessageBox(self.parent_window)
            box.setWindowTitle(T("设置"))
            box.setText(T("语言更改需要重启应用后生效。"))
            restart = box.addButton(T("立即重启"), QMessageBox.ButtonRole.AcceptRole)
            box.addButton(T("稍后"), QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is restart:
                self.parent_window.restart_app()

    def reject(self):
        if self.parent_window is not None:
            self.parent_window.set_theme(self._orig_theme)
        super().reject()


def main():
    i18n.init()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    icon_path = _resource_path("app.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    cfg = settings.load()
    mode = os.environ.get("GID_THEME") or cfg.get("theme", "system")
    apply_theme(app, mode)
    w = MainWindow()
    w.show()
    try:
        app.styleHints().colorSchemeChanged.connect(lambda _: w.on_system_theme_changed())
    except Exception:
        pass
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
