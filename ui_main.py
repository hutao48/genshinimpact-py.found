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

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QAbstractTableModel, QModelIndex, QRectF, QSize
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QIcon, QPainter, QPen, QBrush, QLinearGradient
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QSpinBox, QSlider, QTableView, QHeaderView,
    QFrame, QSplitter, QMessageBox, QSizePolicy, QButtonGroup, QFileDialog, QAbstractItemView, QStackedWidget,
)

import pyqtgraph as pg

from instruments import all_instruments, midi_to_name
from detection import NoteDetector, END_REASON_TEXT
from screening import Screener, LEVEL_LIMIT, LEVEL_SUSPECT, LEVEL_TEXT, KIND_TEXT
from audio_capture import AudioCapture, list_sources, default_loopback_id
from app_version import APP_NAME, APP_VERSION
import diag


def _resource_path(name):
    """打包后资源在 PyInstaller 解压目录（sys._MEIPASS），源码运行时在 packaging/ 下"""
    base = getattr(sys, "_MEIPASS", None)
    if base and os.path.exists(os.path.join(base, name)):
        return os.path.join(base, name)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "packaging", name)


# ---------------------------------------------------------------- 主题
C = {
    "bg": "#0f1116", "card": "#161921", "tile": "#1b1f29", "border": "#252a36", "border_hi": "#333a4a",
    "input": "#12151c", "text": "#e8eaf0", "dim": "#8b93a7", "faint": "#5d6478",
    "gold": "#f6b73c", "cyan": "#4cc9f0", "green": "#34d399", "violet": "#a78bfa", "red": "#f87171",
}
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
QLabel#pill[state="on"] {{ color: {c['green']}; background: rgba(52, 211, 153, 28); border-color: rgba(52, 211, 153, 90); }}
QLabel#pill[state="err"] {{ color: {c['red']}; background: rgba(248, 113, 113, 28); border-color: rgba(248, 113, 113, 90); }}
QPushButton#pillBtn {{ font-size: 12px; color: {c['dim']}; background: {c['tile']}; border: 1px solid {c['border']};
                      border-radius: 13px; padding: 4px 14px; }}
QPushButton#pillBtn:hover {{ border-color: #46506a; }}
QPushButton#pillBtn[state="warn"] {{ color: {c['gold']}; background: rgba(246, 183, 60, 26); border-color: rgba(246, 183, 60, 90); }}
QPushButton#pillBtn[state="bad"] {{ color: {c['red']}; background: rgba(248, 113, 113, 28); border-color: rgba(248, 113, 113, 100); }}
QFrame#tabs {{ background: {c['input']}; border: 1px solid {c['border']}; border-radius: 9px; }}
QFrame#tabs QPushButton {{ background: transparent; border: none; border-radius: 7px; padding: 5px 14px;
                           color: {c['dim']}; font-size: 13px; font-weight: 600; }}
QFrame#tabs QPushButton:hover {{ color: {c['text']}; }}
QFrame#tabs QPushButton:checked {{ background: #262c3a; color: {c['text']}; }}
QLabel#screenSummary {{ font-size: 12px; color: {c['dim']}; background: {c['tile']}; border: 1px solid {c['border']};
                        border-radius: 8px; padding: 8px 12px; }}
QPushButton {{ background: {c['tile']}; color: {c['text']}; border: 1px solid {c['border_hi']}; border-radius: 8px;
               padding: 7px 16px; font-size: 13px; }}
QPushButton:hover {{ background: #232836; border-color: #46506a; }}
QPushButton:pressed {{ background: #181c25; }}
QPushButton:disabled {{ color: {c['faint']}; }}
QPushButton#primary {{ background: {c['gold']}; color: #1d1505; border: none; font-weight: 700; padding: 8px 22px; }}
QPushButton#primary:hover {{ background: #ffc75a; }}
QPushButton#primary:checked {{ background: {c['red']}; color: #ffffff; }}
QPushButton#primary:checked:hover {{ background: #fb8a8a; }}
QFrame#seg {{ background: {c['input']}; border: 1px solid {c['border']}; border-radius: 8px; }}
QFrame#seg QPushButton {{ background: transparent; border: none; border-radius: 6px; padding: 4px 12px;
                          color: {c['dim']}; font-size: 12px; }}
QFrame#seg QPushButton:hover {{ color: {c['text']}; }}
QFrame#seg QPushButton:checked {{ background: #262c3a; color: {c['gold']}; font-weight: 600; }}
QComboBox, QSpinBox {{ background: {c['input']}; border: 1px solid {c['border_hi']}; border-radius: 8px;
                       padding: 5px 10px; min-height: 20px; font-size: 13px; }}
QComboBox:hover, QSpinBox:hover {{ border-color: #46506a; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {c['tile']}; border: 1px solid {c['border_hi']}; padding: 4px;
                               selection-background-color: #2b3242; outline: none; }}
QSpinBox::up-button, QSpinBox::down-button {{ border: none; background: transparent; width: 16px; }}
QSlider::groove:horizontal {{ height: 4px; background: #2a3040; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {c['gold']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: #ffffff; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
QTableView {{ background: transparent; border: none; gridline-color: transparent; outline: none;
              alternate-background-color: #1a1d26; selection-background-color: #243049;
              selection-color: {c['text']}; font-size: 13px; }}
QTableView::item {{ padding: 0 10px; border: none; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: transparent; color: {c['faint']}; border: none;
                        border-bottom: 1px solid {c['border']}; padding: 6px 10px; font-size: 12px; font-weight: 600; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #2c3342; border-radius: 4px; min-height: 32px; }}
QScrollBar::handle:vertical:hover {{ background: #3b4457; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QSplitter::handle:vertical {{ height: 10px; background: transparent; }}
QStatusBar {{ background: {c['bg']}; color: {c['faint']}; font-size: 12px; }}
QStatusBar::item {{ border: none; }}
QToolTip {{ background: {c['tile']}; color: {c['text']}; border: 1px solid {c['border_hi']}; padding: 6px 8px; }}
QMessageBox, QFileDialog {{ background: {c['card']}; }}
"""


def _pick_font(cands):
    fams = set(QFontDatabase.families())
    for f in cands:
        if f in fams:
            return f
    return cands[-1]


def apply_theme(app):
    """字体 + 样式表（需在 QApplication 创建之后调用）"""
    global UI_FONT, NUM_FONT
    UI_FONT = _pick_font(["Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Segoe UI"])
    NUM_FONT = _pick_font(["Bahnschrift", "Segoe UI Semibold", "Segoe UI", UI_FONT])
    f = QFont(UI_FONT)
    f.setPixelSize(13)
    app.setFont(f)
    app.setStyleSheet(_qss())
    pg.setConfigOptions(antialias=True)


def _repolish(w):
    w.style().unpolish(w)
    w.style().polish(w)


def _num_font(px, bold=True):
    f = QFont(NUM_FONT)
    f.setPixelSize(max(6, int(px)))
    f.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
    return f


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

    def __init__(self, caption, color, big=False, mono=False, parent=None):
        super().__init__(parent)
        self.setObjectName("tile")
        self.color, self.big, self.mono = color, big, mono
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 14, 10)
        v.setSpacing(2)
        cap = QLabel(f"<span style='color:{color}'>●</span>&nbsp;&nbsp;{caption}")
        cap.setObjectName("tileCap")
        cap.setTextFormat(Qt.TextFormat.RichText)
        self.val = QLabel("—")
        self.val.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.val.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.sub = QLabel("")
        self.sub.setObjectName("tileSub")
        v.addWidget(cap)
        v.addWidget(self.val, 1)
        v.addWidget(self.sub)
        self.setMinimumHeight(72)
        self._px = 0

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
            color = C["faint"] if self.val.text() == "—" else self.color
            self.val.setStyleSheet(f"color:{color}; font-family:'{fam}'; font-size:{px}px; font-weight:600;")


# ================================================================ 键位面板
class KeyTile(QWidget):
    """单个琴键：自绘圆角方块（大号键位字母 + 小号音名），发音时金色/绿色高亮"""

    def __init__(self, letter, sub, role, tip, parent=None):
        super().__init__(parent)
        self.letter, self.sub, self.role = letter, sub, role
        self.active = False
        self.setToolTip(tip)
        self.setMinimumSize(42, 34)
        self.setMaximumSize(132, 92)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def sizeHint(self):
        return QSize(68, 56)

    def set_active(self, a):
        if a != self.active:
            self.active = a
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        rad = min(12.0, r.height() * 0.22)
        chord = self.role == "chord"
        if self.active:
            g = QLinearGradient(r.topLeft(), r.bottomLeft())
            if chord:
                g.setColorAt(0, QColor("#5eead4"))
                g.setColorAt(1, QColor("#10b981"))
                glow = QColor(52, 211, 153, 70)
            else:
                g.setColorAt(0, QColor("#ffd479"))
                g.setColorAt(1, QColor("#f59e0b"))
                glow = QColor(246, 183, 60, 70)
            p.setPen(QPen(glow, 5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(-1, -1, 1, 1), rad + 1, rad + 1)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            fg, fg2 = QColor("#1b1405") if not chord else QColor("#062019"), QColor(0, 0, 0, 150)
        else:
            p.setPen(QPen(QColor("#24473c" if chord else "#2a3142"), 1))
            p.setBrush(QColor("#152824" if chord else "#1c212c"))
            fg, fg2 = QColor("#bfe9da" if chord else "#e3e6ee"), QColor("#6fae98" if chord else "#7c859b")
        p.drawRoundedRect(r, rad, rad)
        h = r.height()
        top = QRectF(r.left(), r.top() + h * 0.10, r.width(), h * 0.50)
        bot = QRectF(r.left(), r.top() + h * 0.58, r.width(), h * 0.32)
        p.setPen(fg)
        p.setFont(_num_font(h * 0.36))
        p.drawText(top, Qt.AlignmentFlag.AlignCenter, self.letter)
        p.setPen(fg2)
        f2 = QFont(UI_FONT)
        f2.setPixelSize(max(10, int(h * 0.22)))
        p.setFont(f2)
        p.drawText(bot, Qt.AlignmentFlag.AlignCenter, self.sub)
        p.end()


class KeyPanel(QWidget):
    """按乐器布局排列琴键，检测到发音时高亮；琴键大小随区域自适应"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.inst = None
        self.grid = QGridLayout(self)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(8)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.buttons = {}

    def set_instrument(self, inst):
        self.inst = inst
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                # 立即从面板上移除（deleteLater 要等回到事件循环才删除，期间新旧琴键会叠在一起）
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self.buttons.clear()
        for r in range(4):
            self.grid.setRowStretch(r, 0)
        key_map = {k[0]: k for k in inst.keys}
        if inst.name == "悠可琴":
            rows = [("和弦", "QWERTYU"), ("高音", "ASDFGHJ"), ("低音", "ZXCVBNM")]
        elif inst.name == "晚风圆号":
            rows = [("高音", "QWERTYU"), ("低音", "ASDFGHJ")]
        else:
            rows = [("高音", "QWERTYU"), ("中音", "ASDFGHJ"), ("低音", "ZXCVBNM")]
        for r, (title, letters) in enumerate(rows):
            lab = QLabel(title)
            lab.setObjectName("rowLabel")
            lab.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.grid.addWidget(lab, r, 0)
            for c, ch in enumerate(letters):
                label, midi, kind, extra = key_map[ch]
                if kind == "chord":
                    tile = KeyTile(ch, str(extra), "chord", f"和弦键 {ch}：{extra}")
                else:
                    tile = KeyTile(ch, midi_to_name(midi), "pitch", f"键 {ch} = {midi_to_name(midi)}")
                self.grid.addWidget(tile, r, c + 1)
                self.buttons[ch] = tile
            self.grid.setRowStretch(r, 1)
        for c in range(1, 8):
            self.grid.setColumnStretch(c, 1)
        self.grid.setColumnMinimumWidth(0, 30)

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
            lab = QLabel(f"{key}  —")
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
            b = QPushButton(name)
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
        self.empty_text = pg.TextItem("开始演奏后，这里会实时画出 BPM 随时间的变化", color=C["faint"], anchor=(0.5, 0.5))
        f = QFont(UI_FONT)
        f.setPixelSize(13)
        self.empty_text.setFont(f)
        pi.addItem(self.empty_text, ignoreBounds=True)
        self._proxy = pg.SignalProxy(self.plot.scene().sigMouseMoved, rateLimit=40, slot=self._on_move)
        lay.addWidget(self.plot, 1)
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
                lab.setText(f"{k}  —")
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
        self.chips["当前"].setText(f"当前  {cur:.1f}")
        self.chips["平均"].setText(f"平均  {avg:.1f}")
        self.chips["最低"].setText(f"最低  {min(seg_v):.1f}")
        self.chips["最高"].setText(f"最高  {max(seg_v):.1f}")
        name = next(n for n, s in self.RANGES if s == self.window)
        self.stats_changed.emit(f"{'全程' if self.window is None else '近 ' + name.replace(' ', '')} "
                                f"{min(seg_v):.0f} – {max(seg_v):.0f}")

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
    END_COLOR = {"release": C["cyan"], "retrig": C["violet"], "decay": C["dim"]}

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
                return QColor(self.END_COLOR.get(row["end"], C["dim"]))
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
            return self.HEAD[section]
        if role == Qt.ItemDataRole.ToolTipRole:
            return self.TIPS.get(section)
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
    LEVEL_COLOR = {LEVEL_LIMIT: C["red"], LEVEL_SUSPECT: C["gold"]}

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
                return QColor(self.LEVEL_COLOR.get(row["f"]["level"], C["dim"]))
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
            return self.HEAD[section]
        if role == Qt.ItemDataRole.ToolTipRole:
            return self.TIPS.get(section)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return None

    def upsert(self, key, f, t_off):
        """新增或更新一条发现；返回 True = 新增"""
        disp = [_fmt_time(f["t"] + t_off), KIND_TEXT.get(f["kind"], f["kind"]), LEVEL_TEXT.get(f["level"], ""),
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
        self.sig_status.emit("正在初始化采集设备…")
        cap = AudioCapture(device_id=self.device_id, is_loopback=self.is_loopback)
        try:
            cap.open()
        except Exception as e:
            self.sig_error.emit(f"打开采集设备失败：{e}\n请检查设备是否被占用，或点击「刷新」重选设备。")
            return
        mode = "扬声器输出(回环)" if self.is_loopback else "麦克风"
        self.sig_status.emit(f"正在监听【{mode}】… 请演奏乐器")
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
                    self.sig_error.emit("连续读取音频失败，采集已中断。请刷新设备后重试。")
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
        cap.close()
        self.sig_status.emit("已停止")


# ================================================================ 主窗口
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.worker = None
        self.instruments = all_instruments()
        self._t_offset = 0.0         # 多次开始/停止：时间接着上一次往后记
        self._build_ui()
        self._fit_to_screen()
        self.refresh_devices()
        self.on_instrument_changed()
        self.statusBar().showMessage("就绪 — 选择乐器与采集设备后点击「开始监听」")
        self._chart_timer = QTimer(self)
        self._chart_timer.setInterval(400)
        self._chart_timer.timeout.connect(self._tick_chart)
        self._chart_timer.start()

    def showEvent(self, e):
        super().showEvent(e)
        if not self._split_init:
            # 首次显示时按实际高度分配三块区域：琴键/指标 30%、BPM 图 30%、时长表 40%
            self._split_init = True
            h = max(300, self.split.height())
            self.split.setSizes([int(h * 0.30), int(h * 0.30), int(h * 0.40)])

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
        title = QLabel(APP_NAME)
        title.setObjectName("appTitle")
        top.addWidget(title)
        ver = QLabel(f"v{APP_VERSION}")
        ver.setObjectName("appVer")
        top.addWidget(ver, 0, Qt.AlignmentFlag.AlignBottom)
        top.addSpacing(12)
        self.pill = QLabel("○  未在监听")
        self.pill.setObjectName("pill")
        self.pill.setProperty("state", "off")
        top.addWidget(self.pill)
        self.btn_screen = QPushButton("排查  未发现异常")
        self.btn_screen.setObjectName("pillBtn")
        self.btn_screen.setProperty("state", "ok")
        self.btn_screen.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_screen.setToolTip("边界值排查：找出超出人手极限的操作（点击查看）")
        self.btn_screen.clicked.connect(lambda: self._set_page(1))
        top.addWidget(self.btn_screen)
        top.addStretch(1)
        self.btn_export = QPushButton("导出记录")
        self.btn_export.setToolTip("把每个音的时长表、BPM 随时间的记录、边界值排查结果导出为 CSV（Excel 可直接打开）")
        self.btn_export.clicked.connect(self.on_export)
        top.addWidget(self.btn_export)
        self.btn_clear = QPushButton("清空记录")
        self.btn_clear.clicked.connect(self.on_clear)
        top.addWidget(self.btn_clear)
        self.btn_start = QPushButton("▶  开始监听")
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
        bl.addWidget(self._field("乐器"))
        self.cmb_instrument = QComboBox()
        for inst in self.instruments:
            self.cmb_instrument.addItem(inst.name)
        self.cmb_instrument.setMinimumWidth(130)
        self.cmb_instrument.currentIndexChanged.connect(self.on_instrument_changed)
        bl.addWidget(self.cmb_instrument)
        bl.addSpacing(8)
        bl.addWidget(self._field("移调"))
        self.spin_transpose = QSpinBox()
        self.spin_transpose.setRange(-12, 12)
        self.spin_transpose.setValue(0)
        self.spin_transpose.setFixedWidth(66)
        self.spin_transpose.setToolTip("音高基准校准（半音）。若检测出的八度与实际不符，用此项整体平移。")
        self.spin_transpose.valueChanged.connect(self.on_instrument_changed)
        bl.addWidget(self.spin_transpose)
        bl.addSpacing(8)
        bl.addWidget(self._field("采集设备"))
        self.cmb_device = QComboBox()
        self.cmb_device.setMinimumWidth(260)
        self.cmb_device.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        bl.addWidget(self.cmb_device, 1)
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.setToolTip("重新扫描扬声器 / 麦克风")
        self.btn_refresh.clicked.connect(self.refresh_devices)
        bl.addWidget(self.btn_refresh)
        bl.addSpacing(8)
        bl.addWidget(self._field("灵敏度"))
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
        keys_card = Card("琴键", "高亮 = 正在发音")
        self.key_panel = KeyPanel()
        keys_card.body.addWidget(self.key_panel, 1)
        tr.addWidget(keys_card, 3)

        info = QWidget()
        ig = QGridLayout(info)
        ig.setContentsMargins(0, 0, 0, 0)
        ig.setSpacing(10)
        self.lab_notes = MetricTile("当前按键", C["cyan"])
        self.lab_chord = MetricTile("和弦", C["green"])
        self.lab_key = MetricTile("调性", C["violet"])
        self.lab_bpm = MetricTile("当前 BPM", C["gold"], big=True, mono=True)
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

        chart_card = Card("BPM 变化", "每 0.5 秒一个点，纵轴随数据自动缩放，鼠标悬停看具体读数")
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
        for i, name in enumerate(("每个音的时长", "边界值排查")):
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

    SCREEN_HELP = ("检查两类超出人手极限的操作：① 同时按下超过 10 个键（人只有 10 根手指）；"
                   "② 很长一段连续音的间隔完全一致（机器级精度）。原神的声音按约 21 ms 一块发出，"
                   "短的轮指人手也会显得完全一致，所以只报很长的段。结果是证据而非定论。")

    def _set_page(self, i):
        self.page_btns[i].setChecked(True)
        self.pages.setCurrentIndex(i)
        self._update_table_hint()

    def _update_screen(self):
        lim, sus = self.findings.counts()
        if lim:
            text, state = f"排查  ⚠ 超出人手极限 {lim} 处" + (f" · 疑似 {sus} 处" if sus else ""), "bad"
        elif sus:
            text, state = f"排查  ⚠ 疑似机械操作 {sus} 处", "warn"
        else:
            text, state = "排查  未发现异常", "ok"
        self.btn_screen.setText(text)
        self.btn_screen.setProperty("state", state)
        _repolish(self.btn_screen)
        n = lim + sus
        self.page_btns[1].setText(f"边界值排查  {n}" if n else "边界值排查")
        head = self._screen_text or "还没有数据。"
        self.screen_summary.setText(f"<b>{head}</b><br>{self.SCREEN_HELP}")
        self._update_table_hint()

    def on_finding(self, f):
        new = self.findings.upsert((self._worker_serial, f["id"]), f, self._t_offset)
        self._update_screen()
        if new:
            self.statusBar().showMessage(f"边界值排查：{_fmt_time(f['t'] + self._t_offset)}  {f['title']}"
                                         f"（{LEVEL_TEXT.get(f['level'], '')}）", 15000)

    def on_screen_summary(self, s):
        self._screen_text = s
        self._update_screen()

    def _update_table_hint(self):
        if getattr(self, "pages", None) is not None and self.pages.currentIndex() == 1:
            self.tab_hint.setText("最新在上 · 鼠标停在一行上看完整说明")
            return
        n = self.notes.rowCount()
        self.page_btns[0].setText(f"每个音的时长  {n}" if n else "每个音的时长")
        self.tab_hint.setText(f"最新在上，最多保留 {NOTES_KEEP} 条" if n else "演奏后逐条记录每个音")

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
            tag = "（扬声器输出·回环）" if kind == "loopback" else "（麦克风）"
            self.cmb_device.addItem(f"{name} {tag}", (dev_id, kind == "loopback"))
            if dev_id == default_id:
                sel = i
        if self.cmb_device.count() == 0:
            self.cmb_device.addItem("（未找到可用采集设备）", (None, True))
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
            self.btn_start.setText("▶  开始监听")
            return
        self.start_worker()

    def start_worker(self):
        if self.cmb_device.count() == 0:
            QMessageBox.warning(self, "提示", "未找到可用采集设备。")
            self.btn_start.setChecked(False)
            return
        dev_id, is_loop = self.cmb_device.currentData()
        if dev_id is None:
            QMessageBox.warning(self, "提示", "请先刷新并选择采集设备。")
            self.btn_start.setChecked(False)
            return
        # 接着已有记录往后计时（停止后再开始、换乐器重启时，表格与 BPM 图不会从 0 重叠）
        last_note = self.notes.rows[-1]["raw"][0] if self.notes.rows else 0.0
        self._t_offset = max(self.chart.last_time(), last_note) + (1.0 if (self.notes.rows or self.chart.t) else 0.0)
        self.worker = DetectWorker(
            self._current_inst, dev_id, is_loop,
            self.slider_sens.value() / 100.0)
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
        self.worker.start()
        self.btn_start.setChecked(True)
        self.btn_start.setText("■  停止监听")
        self._set_pill("●  正在启动…", "on")

    def _on_status(self, s):
        self.statusBar().showMessage(s)
        if s.startswith("正在监听"):
            self._set_pill("●  " + s.split("…")[0], "on")
        elif s == "已停止":
            self._set_pill("○  未在监听", "off")

    def stop_worker(self):
        if self.worker is not None:
            self.worker.stop()
            self.worker.wait(3000)
            self.worker = None
        self.key_panel.set_active(set())
        self.lab_notes.setText("—")
        self.lab_chord.setText("—")
        self.lab_bpm.setText("—")
        self._set_pill("○  未在监听", "off")

    def restart_worker(self):
        if self.worker is not None:
            running = self.btn_start.isChecked()
            self.stop_worker()
            if running:
                self.btn_start.setChecked(True)
                self.start_worker()

    def on_worker_finished(self):
        if self.worker is not None and self.worker.isFinished():
            self.worker = None
        if self.worker is None:
            self.btn_start.setChecked(False)
            self.btn_start.setText("▶  开始监听")
            if self.pill.property("state") != "err":
                self._set_pill("○  未在监听", "off")

    def on_error(self, msg):
        self.stop_worker()
        self._set_pill("●  采集出错", "err")
        QMessageBox.critical(self, "采集错误", msg)

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
            notes.append(END_REASON_TEXT.get(ev["end"], ev["end"]))
        if ev.get("approx"):
            notes.append("≈吸附")
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
            QMessageBox.information(self, "导出记录", "还没有记录可以导出。")
            return
        base_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(base_dir):
            base_dir = os.path.expanduser("~")
        default = os.path.join(base_dir, f"演奏记录_{time.strftime('%Y%m%d_%H%M%S')}.csv")
        path, _ = QFileDialog.getSaveFileName(self, "导出记录", default, "CSV 表格 (*.csv)")
        if not path:
            return
        root, ext = os.path.splitext(path)
        if not ext:
            path = root + ".csv"
        bpm_path = os.path.splitext(path)[0] + "_BPM.csv"
        scr_path = os.path.splitext(path)[0] + "_排查.csv"
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["开始时间(s)", "按键", "音名", "唱名", "时长(ms)", "间隔(ms)", "结束方式"])
                for r in self.notes.rows:
                    t, key, name, sol, dur, ioi, end = r["raw"]
                    w.writerow([f"{t:.3f}", key, name, sol, f"{dur:.0f}", "" if ioi is None else f"{ioi:.0f}", end])
            with open(bpm_path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["时间(s)", "BPM"])
                for t, v in zip(self.chart.t, self.chart.v):
                    w.writerow([f"{t:.1f}", f"{v:.1f}"])
            with open(scr_path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["时间(s)", "检查项", "结论", "现象", "说明"])
                for r in self.findings.rows:
                    ff = r["f"]
                    w.writerow([f"{r['t']:.3f}", KIND_TEXT.get(ff["kind"], ff["kind"]), LEVEL_TEXT.get(ff["level"], ""),
                                ff.get("title", ""), ff.get("text", "")])
                if self._screen_text:
                    w.writerow([])
                    w.writerow(["总结", self._screen_text])
        except OSError as e:
            QMessageBox.critical(self, "导出失败", f"写入文件失败：{e}")
            return
        self.statusBar().showMessage(f"已导出：{os.path.basename(path)}、{os.path.basename(bpm_path)}、"
                                     f"{os.path.basename(scr_path)}（{os.path.dirname(path)}）", 10000)

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
        self.statusBar().showMessage("记录已清空")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    icon_path = _resource_path("app.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    apply_theme(app)
    w = MainWindow()
    w.show()
    # 诊断/自动化支持：设置 GID_AUTOSTART=1 时自动开始监听（供测试与远程排查用）
    if os.environ.get("GID_AUTOSTART") == "1":
        QTimer.singleShot(600, w.start_worker)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
