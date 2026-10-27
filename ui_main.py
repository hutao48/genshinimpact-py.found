# -*- coding: utf-8 -*-
"""原神乐器演奏检测器 —— PySide6 界面"""
import sys
import time

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QSpinBox, QSlider, QTableWidget,
    QTableWidgetItem, QGroupBox, QSplitter, QMessageBox, QHeaderView,
    QFrame,
)

import pyqtgraph as pg

from instruments import all_instruments, midi_to_name
from detection import NoteDetector, END_REASON_TEXT
from audio_capture import AudioCapture, list_sources, default_loopback_id
from app_version import APP_NAME, APP_VERSION
import diag


def _resource_path(name):
    """打包后资源在 PyInstaller 解压目录（sys._MEIPASS），源码运行时在 packaging/ 下"""
    import os
    base = getattr(sys, "_MEIPASS", None)
    if base and os.path.exists(os.path.join(base, name)):
        return os.path.join(base, name)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "packaging", name)

# ---------------------------------------------------------------- 主题色
C_BG = "#1c1d21"
C_PANEL = "#26282d"
C_ACCENT = "#f5a623"
C_ACCENT2 = "#4aa3ff"
C_TEXT = "#e8e8e8"
C_DIM = "#9aa0a6"
C_GREEN = "#34c759"
C_RED = "#ff5a52"

DARK_QSS = f"""
QWidget {{ background-color: {C_BG}; color: {C_TEXT}; font-family: "Microsoft YaHei UI"; font-size: 13px; }}
QGroupBox {{ background-color: {C_PANEL}; border: 1px solid #3a3d42; border-radius: 8px; margin-top: 10px; padding: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; color: {C_DIM}; }}
QLabel {{ background: transparent; }}
QPushButton {{ background-color: #34363c; border: 1px solid #45484f; border-radius: 6px; padding: 6px 14px; }}
QPushButton:hover {{ background-color: #3e4148; }}
QPushButton:checked {{ background-color: {C_ACCENT}; color: #15161a; font-weight: bold; border-color: {C_ACCENT}; }}
QPushButton#startBtn {{ background-color: {C_GREEN}; color: #0f1215; font-weight: bold; }}
QPushButton#startBtn:checked {{ background-color: {C_RED}; color: white; }}
QComboBox, QSpinBox {{ background-color: #34363c; border: 1px solid #45484f; border-radius: 6px; padding: 3px 8px; }}
QComboBox QAbstractItemView {{ background-color: #2a2c31; selection-background-color: #45484f; }}
QSlider::groove:horizontal {{ height: 5px; background: #45484f; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {C_ACCENT}; width: 16px; margin: -6px 0; border-radius: 8px; }}
QTableWidget {{ background-color: #222429; gridline-color: #33363c; border: none; }}
QHeaderView::section {{ background-color: #2e3136; color: {C_DIM}; border: none; padding: 4px; }}
QTableWidget::item {{ padding: 2px 6px; }}
"""


# ================================================================ 键位面板
class KeyPanel(QWidget):
    """按乐器布局绘制琴键网格，检测到发音时高亮"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.inst = None
        self.grid = QGridLayout(self)
        self.grid.setSpacing(8)
        self.grid.setContentsMargins(6, 6, 6, 6)
        self.buttons = {}

    def set_instrument(self, inst):
        self.inst = inst
        # 清空
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.buttons.clear()

        key_map = {k[0]: k for k in inst.keys}
        rows = []
        if inst.name == "悠可琴":
            rows = [("和弦键", "QWERTYU"), ("高音", "ASDFGHJ"), ("低音", "ZXCVBNM")]
        elif inst.name == "晚风圆号":
            rows = [("高音", "QWERTYU"), ("低音", "ASDFGHJ")]
        else:
            rows = [("高音", "QWERTYU"), ("中音", "ASDFGHJ"), ("低音", "ZXCVBNM")]

        # 行标题
        for r, (title, _) in enumerate(rows):
            lab = QLabel(title)
            lab.setAlignment(Qt.AlignCenter)
            lab.setStyleSheet(f"color:{C_DIM}; font-size:12px;")
            self.grid.addWidget(lab, r * 2, 0)

        for r, (title, letters) in enumerate(rows):
            # 空白行占位（两行高度）
            for c, ch in enumerate(letters):
                entry = key_map[ch]
                label, midi, kind, extra = entry
                btn = QPushButton()
                btn.setCheckable(True)
                btn.setFocusPolicy(Qt.NoFocus)
                btn.setFixedSize(72, 54)
                if kind == "chord":
                    top, bottom = ch, f"{extra}"
                    btn.setToolTip(f"和弦键 {ch}：{extra}")
                    btn.setProperty("role", "chord")
                else:
                    top, bottom = ch, midi_to_name(midi)
                    btn.setToolTip(f"键 {ch} = {midi_to_name(midi)}")
                    btn.setProperty("role", "pitch")
                self._style_button(btn, False)
                btn.setText(f"{top}\n{bottom}")
                btn.setFont(QFont("Microsoft YaHei UI", 10))
                self.grid.addWidget(btn, r * 2 + 1, c + 1)
                self.buttons[ch] = btn

    @staticmethod
    def _style_button(btn, active):
        role = btn.property("role")
        if active:
            if role == "chord":
                btn.setStyleSheet(
                    "QPushButton{background-color:#2fbf71;color:#0e1210;border:2px solid #7ef0b0;"
                    "border-radius:6px;font-weight:bold;}")
            else:
                btn.setStyleSheet(
                    "QPushButton{background-color:#f5a623;color:#141519;border:2px solid #ffd98a;"
                    "border-radius:6px;font-weight:bold;}")
        else:
            if role == "chord":
                btn.setStyleSheet(
                    "QPushButton{background-color:#24463a;color:#9fdfc0;border:1px solid #3d6b57;"
                    "border-radius:6px;}")
            else:
                btn.setStyleSheet(
                    "QPushButton{background-color:#34363c;color:#c8ccd2;border:1px solid #45484f;"
                    "border-radius:6px;}")

    def set_active(self, labels):
        for ch, btn in self.buttons.items():
            act = ch in labels
            if btn.isChecked() != act:
                btn.setChecked(act)
                self._style_button(btn, act)


# ================================================================ 检测工作线程
class DetectWorker(QThread):
    sig_keys = Signal(object)      # set(active labels)
    sig_note = Signal(object)      # dict 音符事件
    sig_chord = Signal(str)
    sig_tonality = Signal(str)
    sig_bpm = Signal(float)
    sig_bpm_hist = Signal(object)  # [(t, bpm)]
    sig_status = Signal(str)
    sig_error = Signal(str)

    def __init__(self, inst, device_id, is_loopback, sensitivity, parent=None):
        super().__init__(parent)
        self.inst = inst
        self.device_id = device_id
        self.is_loopback = is_loopback
        self.sensitivity = sensitivity
        self._stop = False
        self._active_labels = set()
        self.detector = NoteDetector(inst)
        self.bpm_hist = []
        self._last_bpm = None
        self._last_bpm_t = 0.0
        self.t0 = time.time()

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

            if res["chord"]:
                self.sig_chord.emit(res["chord"])
            if res["tonality"]:
                self.sig_tonality.emit(res["tonality"])

            bpm = res["bpm"]
            if bpm is not None:
                changed = self._last_bpm is None or abs(bpm - self._last_bpm) >= 0.3
                interval_ok = now - self._last_bpm_t >= 0.6
                if changed and interval_ok:
                    self._last_bpm = bpm
                    self._last_bpm_t = now
                    self.sig_bpm.emit(bpm)
                    self.bpm_hist.append((round(now - self.t0, 1), bpm))
                    if len(self.bpm_hist) > 90:
                        self.bpm_hist = self.bpm_hist[-90:]
                    self.sig_bpm_hist.emit(list(self.bpm_hist))
        cap.close()
        self.sig_status.emit("已停止")


# ================================================================ 主窗口
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} — 按键 / 和弦 / 调性 / 音长 / BPM")
        self.resize(1180, 860)
        self.worker = None
        self.instruments = all_instruments()
        self._build_ui()
        self.refresh_devices()
        self.on_instrument_changed()
        self.statusBar().showMessage("就绪 — 选择乐器与采集设备后点击「开始监听」")
        self._bpm_txt = None

    # ------------------------------------------------------------ UI 构建
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # ---- 控制栏
        ctrl = QHBoxLayout()
        ctrl.setSpacing(10)
        ctrl.addWidget(self._lab("乐器："))
        self.cmb_instrument = QComboBox()
        for inst in self.instruments:
            self.cmb_instrument.addItem(inst.name)
        self.cmb_instrument.currentIndexChanged.connect(self.on_instrument_changed)
        ctrl.addWidget(self.cmb_instrument)

        ctrl.addWidget(self._lab("移调："))
        self.spin_transpose = QSpinBox()
        self.spin_transpose.setRange(-12, 12)
        self.spin_transpose.setValue(0)
        self.spin_transpose.setToolTip("音高基准校准（半音）。若检测出的八度与实际不符，用此项整体平移。")
        self.spin_transpose.valueChanged.connect(self.on_instrument_changed)
        ctrl.addWidget(self.spin_transpose)

        ctrl.addSpacing(10)
        ctrl.addWidget(self._lab("采集设备："))
        self.cmb_device = QComboBox()
        self.cmb_device.setMinimumWidth(320)
        ctrl.addWidget(self.cmb_device)
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.clicked.connect(self.refresh_devices)
        ctrl.addWidget(self.btn_refresh)

        ctrl.addSpacing(10)
        ctrl.addWidget(self._lab("灵敏度："))
        self.slider_sens = QSlider(Qt.Horizontal)
        self.slider_sens.setRange(10, 100)
        self.slider_sens.setValue(55)
        self.slider_sens.setFixedWidth(120)
        self.lab_sens = self._lab("55%")
        self.slider_sens.valueChanged.connect(lambda v: self.lab_sens.setText(f"{v}%"))
        ctrl.addWidget(self.slider_sens)
        ctrl.addWidget(self.lab_sens)

        ctrl.addSpacing(10)
        self.btn_start = QPushButton("▶ 开始监听")
        self.btn_start.setObjectName("startBtn")
        self.btn_start.setCheckable(True)
        self.btn_start.clicked.connect(self.on_start_stop)
        ctrl.addWidget(self.btn_start)

        self.btn_clear = QPushButton("清空记录")
        self.btn_clear.clicked.connect(self.on_clear)
        ctrl.addWidget(self.btn_clear)
        ctrl.addStretch(1)
        root.addLayout(ctrl)

        # ---- 中部：键位面板 + 信息面板
        mid = QHBoxLayout()
        mid.setSpacing(8)

        grp_keys = QGroupBox("琴键实时显示（高亮 = 正在发音）")
        vk = QVBoxLayout(grp_keys)
        self.key_panel = KeyPanel()
        vk.addWidget(self.key_panel)
        vk.addStretch(1)
        mid.addWidget(grp_keys, 3)

        grp_info = QGroupBox("实时检测")
        vi = QVBoxLayout(grp_info)
        self.lab_notes = self._big_label("—", 26, C_ACCENT2)
        self.lab_chord = self._big_label("—", 20, C_GREEN)
        self.lab_key = self._big_label("—", 20, C_ACCENT)
        self.lab_bpm = self._big_label("—", 40, C_ACCENT)
        vi.addWidget(self._lab("当前按键（音名）"))
        vi.addWidget(self.lab_notes)
        vi.addWidget(self._lab("检测到的和弦"))
        vi.addWidget(self.lab_chord)
        vi.addWidget(self._lab("当前调性"))
        vi.addWidget(self.lab_key)
        vi.addWidget(self._lab("当前 BPM"))
        vi.addWidget(self.lab_bpm)
        vi.addStretch(1)
        mid.addWidget(grp_info, 2)
        root.addLayout(mid, 1)

        # ---- BPM 条形图
        grp_bpm = QGroupBox("BPM 历史变化（条形图，最近 90 个采样点）")
        vb = QVBoxLayout(grp_bpm)
        self.plot = pg.PlotWidget(background="#1a1b1f")
        self.plot.setYRange(40, 240, padding=0.02)
        self.plot.setLabel("left", "BPM")
        self.plot.setLabel("bottom", "采样序号（时间）")
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.bar = pg.BarGraphItem(x=[], height=[], width=0.65,
                                   brush=pg.mkBrush(74, 163, 255, 200),
                                   pen=pg.mkPen(None))
        self.plot.addItem(self.bar)
        self.lab_bpm_hist = self._lab("尚未采集到 BPM 数据")
        vb.addWidget(self.lab_bpm_hist)
        vb.addWidget(self.plot)
        root.addWidget(grp_bpm, 2)

        # ---- 音符时长表
        grp_tab = QGroupBox("每个音的具体时长（最近 500 条）")
        vt = QVBoxLayout(grp_tab)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["开始时间(s)", "按键", "音名", "唱名", "时长(ms)", "间隔(ms)", "备注"])
        self.table.horizontalHeaderItem(4).setToolTip(
            "起音 → 结束。备注为「松键/截止」时即按键时长；「同键重按」时为到再次按下的时间；\n"
            "「自然衰减」表示拨弦类余音自然消失，松键时刻在声音里不可观测，此时长是余音长度")
        self.table.horizontalHeaderItem(5).setToolTip("与上一个起音的间隔（和弦算一次起音），BPM 由它计算")
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        vt.addWidget(self.table)
        root.addWidget(grp_tab, 3)

    # ------------------------------------------------------------ 小工具
    def _lab(self, text):
        lab = QLabel(text)
        lab.setStyleSheet(f"color:{C_DIM};")
        return lab

    def _big_label(self, text, size, color):
        lab = QLabel(text)
        lab.setAlignment(Qt.AlignCenter)
        lab.setStyleSheet(f"color:{color}; font-size:{size}px; font-weight:bold;")
        return lab

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
            self.btn_start.setText("▶ 开始监听")
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
        self.worker = DetectWorker(
            self._current_inst, dev_id, is_loop,
            self.slider_sens.value() / 100.0)
        self.worker.sig_keys.connect(self.on_keys)
        self.worker.sig_note.connect(self.on_note)
        self.worker.sig_chord.connect(lambda s: self.lab_chord.setText(s))
        self.worker.sig_tonality.connect(lambda s: self.lab_key.setText(s))
        self.worker.sig_bpm.connect(self.on_bpm)
        self.worker.sig_bpm_hist.connect(self.on_bpm_hist)
        self.worker.sig_status.connect(lambda s: self.statusBar().showMessage(s))
        self.worker.sig_error.connect(self.on_error)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()
        self.btn_start.setText("■ 停止监听")

    def stop_worker(self):
        if self.worker is not None:
            self.worker.stop()
            self.worker.wait(3000)
            self.worker = None
        self.key_panel.set_active(set())
        self.lab_notes.setText("—")
        self.lab_chord.setText("—")
        self.lab_bpm.setText("—")

    def restart_worker(self):
        if self.worker is not None:
            running = self.btn_start.isChecked()
            self.stop_worker()
            if running:
                self.btn_start.setChecked(True)
                self.start_worker()

    def on_worker_finished(self):
        if self.worker is not None:
            self.worker = None
        self.btn_start.setChecked(False)
        self.btn_start.setText("▶ 开始监听")

    def on_error(self, msg):
        self.stop_worker()
        QMessageBox.critical(self, "采集错误", msg)

    # ------------------------------------------------------------ 数据显示
    def on_keys(self, labels):
        self.key_panel.set_active(labels)
        names = []
        for ch in "QWERTYUIOPASDFGHJKLZXCVBNM":
            if ch in labels:
                entry = {k[0]: k for k in self._current_inst.keys}.get(ch)
                if entry and entry[2] == "pitch":
                    names.append(f"{ch}·{midi_to_name(entry[1])}")
                elif entry:
                    names.append(f"{ch}·{entry[3]}")
        self.lab_notes.setText("  ".join(names) if names else "—")

    def on_note(self, ev):
        row = 0
        self.table.insertRow(row)
        notes = []
        if ev.get("end"):
            notes.append(END_REASON_TEXT.get(ev["end"], ev["end"]))
        if ev.get("approx"):
            notes.append("≈吸附")
        ioi = ev.get("ioi_ms")
        vals = [
            f"{ev['t']:.3f}", ev["key"], ev["name"], ev["solfege"] or "—",
            f"{ev['dur_ms']:.0f}",
            "—" if ioi is None else f"{ioi:.0f}",
            " · ".join(notes),
        ]
        for c, v in enumerate(vals):
            item = QTableWidgetItem(v)
            if c == 4:
                item.setForeground(QColor(C_ACCENT))
            self.table.setItem(row, c, item)
        while self.table.rowCount() > 500:
            self.table.removeRow(self.table.rowCount() - 1)

    def on_bpm(self, bpm):
        self.lab_bpm.setText(f"{bpm:.1f}")

    def on_bpm_hist(self, hist):
        if not hist:
            return
        xs = [i for i in range(len(hist))]
        ys = [b for _, b in hist]
        self.bar.setOpts(x=xs, height=ys, width=0.65)
        cur = ys[-1]
        self.lab_bpm_hist.setText(
            f"当前 BPM：{cur:.1f}　|　最低 {min(ys):.1f}　|　最高 {max(ys):.1f}　"
            f"|　采样 {len(hist)} 个　|　时间跨度 {hist[0][0]:.0f}s → {hist[-1][0]:.0f}s")
        # 用颜色区分快慢（BarGraphItem 无 setBrush，用 setOpts 更新）
        if cur >= 120:
            self.bar.setOpts(brush=pg.mkBrush(255, 90, 82, 220))
        elif cur >= 80:
            self.bar.setOpts(brush=pg.mkBrush(245, 166, 35, 230))
        else:
            self.bar.setOpts(brush=pg.mkBrush(52, 199, 89, 220))

    def on_clear(self):
        self.key_panel.set_active(set())
        self.lab_notes.setText("—")
        self.lab_chord.setText("—")
        self.lab_key.setText("—")
        self.lab_bpm.setText("—")
        self.lab_bpm_hist.setText("尚未采集到 BPM 数据")
        self.bar.setOpts(x=[], height=[])
        self.table.setRowCount(0)
        if self.worker is not None:
            self.worker.detector.reset()
        self.statusBar().showMessage("记录已清空")


def main():
    import os
    from PySide6.QtGui import QIcon
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    icon_path = _resource_path("app.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    app.setStyleSheet(DARK_QSS)
    w = MainWindow()
    w.show()
    # 诊断/自动化支持：设置 GID_AUTOSTART=1 时自动开始监听（供测试与远程排查用）
    if os.environ.get("GID_AUTOSTART") == "1":
        QTimer.singleShot(600, w.start_worker)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
