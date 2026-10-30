# -*- coding: utf-8 -*-
"""
实时音高/节奏/调性检测引擎（纯 NumPy，无外部 DSP 依赖）
- 复音检测：FFT 峰值拾取 + 抛物线插值 + 谐波过滤 + 多帧确认，可同时识别多个音（和弦）
- 时间基准：统一用"已接收样本数 / 采样率"的音频时钟，帧时间取窗中心。
  实时与离线结果一致，不受读块抖动、线程调度、同一块内多帧共用时间戳的影响。
- 起音精修：1024 点窗 / 256 点帧移（≈5.3 ms）的 log 谱通量（SuperFlux 式频率最大值滤波），
  把每个音的开始时间对齐到真实敲击瞬间（原先取"连续 4 帧确认"那一刻，系统性偏晚 30~70 ms）。
- 落音定位：按该音自身的幅度轨迹定位结束时刻，不再把落音迟滞(grace)帧计入时长：
    release —— 急速截止（松键止音 / 被截断）：-6 dB 半幅点，再按截止陡峭度（-6→-12 dB 用时）
               查表扣除释放尾音造成的偏差，得到松键时刻；
    retrig  —— 同键重按：上一音在新起音处结束（若重按前已截止，则取截止时刻）；
    decay   —— 自然衰减到不可辨：取最后一次可见的帧时刻（拨弦类余音，松键时刻在音频中不可观测）。
- 同键重按：起音前后整窗幅度比较（新发声回到该音"刚按下"时的电平且上升 ≥2 dB），
  连按同一键会被拆成多个音（原先重触发被禁用，连按全部合并成一个超长音）。
- 时长抗噪（游戏环境底噪 / 短促音效 / 背景音乐下不再频繁切断时长、拆出碎片）：
    开新音、同键重按都要求本音频点像真实按键那样上升且持续到起音后 130 ms（_press_ok、_eval_retrig）；
    已在响的音只由精确音高的峰维持；判"松键/截止"时排除随后回升的干涉凹陷、电平起伏大时要求更深的跌落、
    趋势线不可靠时要求截止式的急速跌落（_end_time）。
- BPM（1.0.4 起为拍子级）：对候选拍周期 0.27~1.5 s 打分（拍点 / 细分点上的起音、和弦加重、拍点覆盖率、
  以 120 BPM 为中心的速度先验）起拍，之后锁相跟拍：细分音（八分、十六分、三连音）不改变速度，
  真的变速经两次复查确认后才换（见 _current_bpm 上方说明）。
- 谐波：谐律键琴这类低音区谐波比基频还强的乐器按实测音色（TIMBRES）去掉整数倍频的谐波误检。
- 调性：Krumhansl-Schmuckler 键位相关性分析（24 调）
- 和弦：音级集合 → 和弦模板匹配
"""
import bisect
import threading
import time
from collections import deque

import numpy as np
from instruments import (Instrument, midi_to_name, midi_to_solfege,
                         CHORD_TEMPLATES, NOTE_NAMES)

# Krumhansl-Schmuckler 调性轮廓（大调/小调 12 音级权重）
KS_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KS_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

CHORD_SUFFIX = {
    "maj": "", "min": "m", "dim": "dim", "aug": "aug", "sus2": "sus2", "sus4": "sus4",
    "5": "(5)", "maj7": "maj7", "7": "7", "m7": "m7", "m7b5": "m7b5",
    "dim7": "dim7", "6": "6", "m6": "m6", "add9": "add9", "madd9": "madd9",
}
# 和弦命名的简洁度先验：同样能解释这些音时，优先常见、简单的和弦（三和弦 > 属七/七和弦 > 六、加九等）
CHORD_PRIOR = {
    "maj": 0.06, "min": 0.06, "7": 0.03, "m7": 0.02, "maj7": 0.02, "dim": 0.0, "sus4": 0.0,
    "sus2": -0.01, "aug": -0.02, "m7b5": -0.01, "dim7": -0.02, "6": -0.03, "m6": -0.03,
    "add9": -0.03, "madd9": -0.04,
}
MAJOR_SCALE = (0, 2, 4, 5, 7, 9, 11)

# 逐帧记录复数谱的 MIDI 范围（覆盖全部乐器 ±12 半音移调）
_TRACK_LO, _TRACK_HI = 34, 98

# 各乐器的音色：各次谐波相对基频的电平（dB），按音区（低 < C4 ≤ 中 < C5 ≤ 高）。
# 用于判断"比某个更低的音高出整数倍的峰"是那个音的谐波还是另一个真按下的键（见 _drop_timbre_harmonics / _dedup_harmonics）。
# 数值来自游戏录像：按界面上的按键高亮找出（前后 0.12 s 内）单独按下的音，用与检测器相同的 4096 点窗量各次谐波，
# 取 min(P90, 中位 + 8 dB)（eval_game_video.py --timbre；对比过 P90 / 中位 + 6 dB，这种取法的平均 F1 最高）。
# 只列谐波强、按实测音色判断确实更准的乐器：
#   谐律键琴  低音区二次谐波常比基频还强，三~五次谐波与基频相当；两段录像精确率 58% / 49% → 80% / 68%；
#   跃律琴    低音区二次谐波比基频强十几 dB；精确率 46% → 62%（召回 46% → 39%）。
# 风物之诗琴、悠可琴谐波弱，固定规则已足够；晚风圆号用音色表反而更差（它最低的显著分音在键位音高下方一个八度，见 build_horn）；
# 镜花之琴基频极弱（能量集中在 3~6 次谐波），需要另做按音色模板的音高识别，音色表帮不上。
TIMBRES = {
    "谐律键琴": {
        "low": {2: 4.7, 3: 3.6, 4: 2.0, 5: -0.8, 6: -5.4, 7: -4.1, 8: -11.9},
        "mid": {2: 1.6, 3: -4.2, 4: -5.8, 5: -12.6, 6: -20.6, 7: -20.3, 8: -28.3},
        "high": {2: -10.6, 3: -13.3, 4: -21.8, 5: -20.2, 6: -24.9, 7: -45.0, 8: -56.2},
    },
    "跃律琴": {
        "low": {2: 16.1, 3: 7.4, 4: 7.5, 5: 5.5, 6: -11.2, 7: 1.3, 8: -18.2},
        "mid": {2: 3.1, 3: 6.6, 4: -3.4, 5: -0.9, 6: -23.4, 7: -22.4, 8: -46.4},
        "high": {2: -10.7, 3: -13.7, 4: -29.7, 5: -44.1, 6: -60.8, 7: -78.6, 8: -85.3},
    },
}
HARM_MARGIN_DB = 2.0
# 各乐器的谐波判定余量（dB）：谐律键琴用 0——余量 2 dB 时同时按下的八度常被当成谐波丢掉（游戏录像：召回 +2.6%，精确率不降）；
# 跃律琴 0 dB 时多检变多，仍用 2 dB
HARM_MARGIN_BY_INST = {"谐律键琴": 0.0}

# 按音色模板改判键位（1.0.7）：起音后 8~93 ms 的频谱减去起音前的频谱，对候选键（检测到的音高是它的
# 1~8 次谐波、且模板里这次谐波不弱于 -20 dB）按"各次谐波幅度 × 模板权重"求和，取最高的键。
# 模板 = 游戏录像里单独按下（前后 0.15 s 没有别的按键）的音各次谐波相对最强谐波的中位电平（dB）。
# 用录像前半段学模板、后半段评测：镜花之琴 精确率 12% → 56%、召回 11% → 42%；晚风圆号 30% → 47% / 29% → 34%；
# 谐律键琴 76% → 83% / 66% → 68%。风物之诗琴、悠可琴基频本来就最强，跃律琴改判后召回下降，不用。
KEY_TEMPLATES = {
    "镜花之琴": {
        "low": (-55.3, -40.8, -26.9, -2.2, -3.2, -2.4, -8.2, -10.2),
        "mid": (-37.4, -17.8, -5.4, -1.9, -7.6, -6.7, -4.4, -6.2),
        "high": (-37.4, -17.8, -5.4, -1.9, -7.6, -6.7, -4.4, -6.2),
    },
    "晚风圆号": {
        "low": (-3.4, 0.0, -18.1, -26.6, -27.8, -38.1, -41.8, -49.6),
        "mid": (-3.4, 0.0, -18.1, -26.6, -27.8, -38.1, -41.8, -49.6),
        "high": (0.0, -20.1, -24.2, -29.2, -36.9, -41.4, -42.4, -57.4),
    },
    "谐律键琴": {      # 两段录像的平均
        "low": (-2.4, -4.9, -6.7, -7.0, -10.8, -16.0, -11.6, -24.5),
        "mid": (0.0, -7.2, -12.5, -14.1, -20.9, -28.9, -31.6, -41.2),
        "high": (0.0, -16.1, -20.4, -32.3, -30.0, -32.0, -60.6, -73.2),
    },
}


def timbre_register(midi):
    return "low" if midi < 60 else ("mid" if midi < 72 else "high")


# 结束原因（UI 备注用）
END_REASON_TEXT = {
    "release": "松键/截止",
    "retrig": "同键重按",
    "decay": "余音自然衰减",
}


# 截止定位校正表（4096 Hann 窗 / 1024 帧移下对"稳态音 + 硬截止 / 指数释放 τ=5~240 ms"仿真标定）：
#   Δ    = t(-12 dB 交越) - t(-6 dB 交越)：截止陡峭程度（硬截止 ≈11 ms，τ 越大 Δ 越大）
#   bias = t(-6 dB 交越) - 真实松键时刻
# 松键时刻 = t(-6 dB) - bias(Δ)：对硬截止与各种释放尾音长度都无偏。
_REL_DELTA_MS = np.array([11.3, 11.7, 13.1, 16.9, 22.0, 28.1, 41.5, 55.3, 82.9, 110.5, 165.8])
_REL_BIAS_MS = np.array([-1.6, 3.4, 8.0, 16.2, 23.5, 30.3, 43.6, 56.9, 84.0, 111.4, 166.4])


def _release_bias(delta_s):
    """由 Δ（秒）查表得到 -6 dB 交越相对松键时刻的偏差（秒）"""
    if delta_s is None:
        return 0.0
    d = delta_s * 1000.0
    if d >= _REL_DELTA_MS[-1]:
        return (d + 0.6) / 1000.0
    return float(np.interp(d, _REL_DELTA_MS, _REL_BIAS_MS)) / 1000.0


def _midi_freq(m):
    return 440.0 * 2.0 ** ((m - 69) / 12.0)


def _db(x):
    return 20.0 * np.log10(np.abs(x) + 1e-12)


# ======================================================================
# BPM：起音时间 → 起音周期
# ======================================================================
def estimate_ioi_period(times, weights=None, p_min=0.20, p_max=1.60):
    """由（已合并和弦的）起音时间估计起音周期（秒）。

    1) 一阶/二阶/三阶起音间隔 D（权重 1 / 0.5 / 0.25），在对数等距候选周期 p 上打分：
         score(p) = Σ w · G((D - k·p)/σ) / √k ，k = round(D/p) ∈ [1, 4]
       —— 软高斯核取代原来的"|k-round(k)|<0.16 计数"：不再出现"平台最左端获胜"的偏快偏差；
       —— 1/√k 降权：半周期 p/2 只能以 k=2 解释每个间隔，得分天然低于 p；
          倍周期 2p 无法解释一阶间隔，得分也低于 p。
    2) 选出 p0 后，把一阶间隔能被 p0 整数倍解释的连续起音划为"同相位段"，段内累计整数位置，
       对所有段做合并加权回归（各段独立截距、共用斜率）→ 精修周期：
       精度随起音数快速提高，且休止、拖拍、段落间停顿只会切断段，不会拉偏整体。
    返回 {"period", "conf", "n"} 或 None；conf = 被周期解释的一阶间隔（加权）占比。
    """
    t = np.asarray(times, dtype=np.float64)
    if t.size < 4:
        return None
    order = np.argsort(t)
    t = t[order]
    if weights is None:
        w = np.ones_like(t)
    else:
        w = np.maximum(np.asarray(weights, dtype=np.float64)[order], 1e-6)
    n = t.size
    span = t[-1] - t[0]
    if span <= p_min * 2:
        return None

    ds, ws = [], []
    for lag, lw in ((1, 1.0), (2, 0.5), (3, 0.25)):
        if n > lag:
            ds.append(t[lag:] - t[:-lag])
            ws.append(lw * np.sqrt(w[lag:] * w[:-lag]))
    D = np.concatenate(ds)
    WD = np.concatenate(ws)
    keep = (D >= 0.6 * p_min) & (D <= 4.5 * p_max)
    D, WD = D[keep], WD[keep]
    if D.size < 3:
        return None

    P = np.exp(np.arange(np.log(p_min), np.log(p_max) + 1e-12, 0.002))
    K = np.rint(D[None, :] / P[:, None])
    valid = (K >= 1) & (K <= 4)
    Ks = np.maximum(K, 1.0)
    resid = D[None, :] - Ks * P[:, None]
    sig = np.maximum(0.012, 0.035 * P)[:, None] * np.sqrt(Ks)
    G = np.exp(-0.5 * (resid / sig) ** 2) * valid / np.sqrt(Ks)
    score = (G * WD[None, :]).sum(axis=1)
    # 极弱的速度先验（以 120 BPM 为中心、σ=1.5 八度），只在得分几乎相同时打破平局
    prior = np.exp(-0.5 * (np.log2((60.0 / P) / 120.0) / 1.5) ** 2)
    score = score * (0.92 + 0.08 * prior)
    i_best = int(np.argmax(score))
    p0 = float(P[i_best])

    # ---- 分段同相位网格精修
    d1 = np.diff(t)
    k1 = np.rint(d1 / p0)
    tol = np.maximum(0.025, 0.08 * p0) * np.sqrt(np.maximum(k1, 1.0))
    ok = (k1 >= 1) & (k1 <= 4) & (np.abs(d1 - k1 * p0) <= tol)
    pos = np.zeros(n)
    run = np.zeros(n, dtype=int)
    r = 0
    for i in range(1, n):
        if ok[i - 1]:
            pos[i] = pos[i - 1] + k1[i - 1]
        else:
            r += 1
        run[i] = r
    period = p0
    for _ in range(2):
        num = den = 0.0
        for rr in range(r + 1):
            sel = run == rr
            if sel.sum() < 2:
                continue
            tw, tt, pp = w[sel], t[sel], pos[sel]
            tm = np.sum(tw * tt) / np.sum(tw)
            pm = np.sum(tw * pp) / np.sum(tw)
            num += np.sum(tw * (pp - pm) * (tt - tm))
            den += np.sum(tw * (pp - pm) ** 2)
        if den <= 1e-9:
            break
        cand = num / den
        if not (0.97 * p0 <= cand <= 1.03 * p0):
            break
        period = cand
        # 剔除离群起音（相对段内网格残差过大），再拟合一次
        res = np.zeros(n)
        for rr in range(r + 1):
            sel = run == rr
            if sel.sum() < 2:
                continue
            tw, tt, pp = w[sel], t[sel], pos[sel]
            a = np.sum(tw * (tt - period * pp)) / np.sum(tw)
            res[sel] = tt - (a + period * pp)
        mad = np.median(np.abs(res[res != 0])) if np.any(res != 0) else 0.0
        bad = np.abs(res) > max(0.015, 4.5 * mad)
        if not bad.any():
            break
        w = np.where(bad, w * 1e-3, w)

    w1 = np.sqrt(w[1:] * w[:-1]) if n > 1 else np.ones(0)
    conf = float(np.sum(w1 * ok) / max(np.sum(w1), 1e-9))
    return {"period": float(period), "conf": conf, "n": int(n)}


# ======================================================================
class NoteDetector:
    OF_N = 1024            # 起音函数窗长 ≈ 21 ms
    OF_HOP = 256           # 起音函数帧移 ≈ 5.3 ms
    OF_GAMMA = 100.0       # log 压缩系数
    OF_MIN = 8.0           # 起音峰最小绝对强度
    OF_OFFSET = 0.0        # 起音峰时间 → 真实敲击时刻的固定校正（秒；基准实测偏差 <5 ms，无需校正）

    def __init__(self, instrument: Instrument, sr: int = 48000,
                 sensitivity: float = 0.55, bpm_window: float = 12.0,
                 sim_clock: bool = False):
        self.instrument = instrument
        self.timbre = TIMBRES.get(instrument.name)
        self.key_tmpl = self._make_key_tmpl(instrument.name)
        self.harm_margin = HARM_MARGIN_BY_INST.get(instrument.name, HARM_MARGIN_DB)
        self.sr = sr
        self.fft_size = 4096          # 实际窗长 ≈ 85 ms
        self.fft_n = 16384            # 零填充到 16384 提升插值精度
        self.hop = 1024               # 帧移 ≈ 21 ms
        self.sensitivity = sensitivity  # 0~1
        self.bpm_window = bpm_window
        # 兼容保留：时间基准已统一为音频样本时钟（实时/离线行为一致），该参数不再影响计时
        self.sim_clock = sim_clock
        self.grace = 7                # 落音迟滞帧数：只决定事件何时发出，不计入时长
        self.confirm = 4              # 连续帧确认阈值
        self.min_note_s = 0.09        # 自然衰减类音符最短时长（更短视为瞬态杂音）
        self.min_cut_note_s = 0.035   # 截止/同键重按类音符最短时长

        self._win = np.hanning(self.fft_size)
        self._of_win = np.hanning(self.OF_N).astype(np.float32)
        # 分析窗的频率响应 |W(Δf)|/|W(0)|（Δf = 0~600 Hz，每 0.5 Hz）：估算一个音泄漏到别的键频点的电平
        df = np.arange(0.0, 600.0, 0.5)
        k = np.arange(self.fft_size)
        W = np.abs(np.exp(-2j * np.pi * np.outer(df, k) / sr) @ self._win)
        self._leak_db = 20.0 * np.log10(np.maximum(W / W[0], 1e-6))
        f_of = np.fft.rfftfreq(self.OF_N, 1.0 / sr)
        self._of_band = np.nonzero((f_of >= 60.0) & (f_of <= 8000.0))[0]
        midis = np.arange(_TRACK_LO, _TRACK_HI + 1)
        nb = self.fft_n // 2
        self._track_bins = np.array(
            [[min(nb, int(round(_midi_freq(m) * h * self.fft_n / sr))) for m in midis]
             for h in (1, 2)])
        self._lock = threading.RLock()
        self._t0 = time.time()
        self._reset_state()

    # ------------------------------------------------------------------
    @staticmethod
    def _make_key_tmpl(name):
        t = KEY_TEMPLATES.get(name)
        if t is None:
            return None
        return {r: (np.array(v, dtype=np.float64), 10.0 ** (np.array(v, dtype=np.float64) / 20.0))
                for r, v in t.items()}

    def set_instrument(self, inst: Instrument):
        with self._lock:
            self.timbre = TIMBRES.get(inst.name)
            self.key_tmpl = self._make_key_tmpl(inst.name)
            self.harm_margin = HARM_MARGIN_BY_INST.get(inst.name, HARM_MARGIN_DB)
            self.instrument = inst

    def set_sensitivity(self, s: float):
        self.sensitivity = max(0.0, min(1.0, s))

    def reset(self):
        # UI 线程可能在工作线程 feed() 期间调用：加锁避免状态被并发改动
        with self._lock:
            self._reset_state()

    def _reset_state(self):
        self._buf = np.zeros(0, dtype=np.float32)
        self._buf_pos = 0             # _buf[0] 在整条音频流中的样本序号
        self._raw = np.zeros(0, dtype=np.float32)   # 最近 1.5 s 原始音频（按音色模板改判键位用）
        self._raw_pos = 0
        self._relabel_cache = {}      # 起音时刻 → (起音后-起音前的频谱)
        self._group_keys = {}         # id(起音事件) → 这个起音已经改判出的键（同一起音两个音判成同一个键只留一个）
        self._n_in = 0                # 已接收样本总数（音频时钟）
        self._sim_t = 0.0             # 兼容旧字段（= 当前音频时钟）
        # 细分辨率起音函数。流开头补 2048 个"虚拟静音"样本：音频从第 0 个样本就有音时，
        # 首音的起音也能形成通量峰（否则首音会因缺少"之前"的参照帧而丢失）
        self._of_buf = np.zeros(2 * self.OF_N, dtype=np.float32)
        self._of_pos = -2 * self.OF_N
        self._of_prev = deque(maxlen=2)
        self._odf_t = []
        self._odf_v = []
        self._odf_e = []              # 每个细帧的宽带总功率 dB（区分起音与截止"咔哒"）
        self._odf_checked = 0
        self._odf_max = 0.0
        self._of_peaks = deque(maxlen=160)    # [(t, 强度)]
        self._off_peaks = deque(maxlen=64)    # 截止"咔哒"候选 [(t, 强度)]
        self._weak_peaks = deque(maxlen=128)  # 没过门限的起音函数局部峰 [(t, 强度)]
        self._pending = deque()               # 待做"同键重按"评估的起音时刻
        # 每帧各音基频 / 二次谐波处的复数谱
        self._hist_t = deque(maxlen=64)
        self._hist_X = deque(maxlen=64)
        # 音符跟踪
        self.active = {}              # midi -> 音符状态 dict
        self.active_frames = {}       # midi -> 连续缺席帧计数
        self._streak = {}             # midi -> 连续出现帧数
        self._miss = {}               # midi -> 连续缺席帧数
        self._first_seen = {}         # midi -> 本轮 streak 首次出现的帧中心时间
        self._last_start = {}         # midi -> 最近一次开音的起音时刻（后备判定不再用它之前的起音）
        self._fresh = {}              # midi -> 最近确认的按键"刚按下"时的电平（dB）
        self.fb_onset_ids = set()     # 只由后备判定开出的起音事件（id）
        self._attack = {}             # midi -> 攻击强度（首帧幅度/上帧同频幅度）
        self._attack_t = {}           # midi -> 攻击强度取得最大值的帧时刻
        self.onsets = []              # [[t, 强度, 音数, 最强音电平]] 音符起音（和弦合并），用于间隔/旁瓣判定
        self.beat_onsets = []         # [[t, 强度]] BPM 用起音：起音峰 + 音高证据（和弦合并）
        self._onsets_ver = 0
        self._prev_mag = None
        self._recent_peak = 0.0       # 近期最大帧峰值（指数衰减），用于相对门限
        self._floor = 1e-7            # 自适应噪声底
        # 只从确认过的按键起音学习电平，停顿时保持，不随余音/背景声一起降低。
        # 帧峰值的快速衰减仍用于结束已有音；不能拿它来决定多轻的声音也能开新音。
        self._press_levels = deque(maxlen=24)
        self._press_level = 0.0
        self._display_keys = {}
        self._bpm_key = None
        # BPM 跟踪状态（见 _current_bpm）：当前周期、速度段起点、停顿后的起点、变速候选、纠正候选
        self._bpm_reset()
        self.chroma_note_log = []     # [time, midi, dur_ms, amp] 用于调性与和弦
        # 和弦 / 调性的显示值与切换候选（防抖）
        self._chord_disp = ""
        self._chord_cand = None       # (候选文字, 首次出现时刻)
        self._key_disp = None         # (root, "maj"/"min")
        self._key_cand = None         # ((root, mode), 首次出现时刻)
        self._key_p = None            # (显示的调, 平滑后的置信度)

    # ------------------------------------------------------------------
    def _now(self):
        """音频时钟：已接收样本数 / 采样率（秒）"""
        return self._n_in / self.sr

    def feed(self, chunk: np.ndarray) -> dict:
        """输入一段单声道 float32 音频，返回本批检测结果"""
        with self._lock:
            chunk = np.asarray(chunk, dtype=np.float32).reshape(-1)
            self._n_in += chunk.size
            self._buf = np.concatenate([self._buf, chunk])
            if self.key_tmpl is not None:
                self._raw = np.concatenate([self._raw, chunk])
                cut = len(self._raw) - int(1.5 * self.sr)
                if cut > 0:
                    self._raw = self._raw[cut:]
                    self._raw_pos += cut
            self._of_buf = np.concatenate([self._of_buf, chunk])
            self._update_odf()
            out = {"keys": dict(self._display_keys), "note_events": [], "chord": "", "tonality": "",
                   "bpm": None, "t": 0.0}
            while len(self._buf) >= self.fft_size:
                frame = self._buf[:self.fft_size]
                t_c = (self._buf_pos + self.fft_size / 2.0) / self.sr   # 帧中心时刻
                self._buf = self._buf[self.hop:]
                self._buf_pos += self.hop
                res = self._process_frame(frame, t_c)
                # 当前按键是最后一帧的快照，不能并集，否则同批内已结束的键仍会亮着。
                self._display_keys = res["keys"]
                out["keys"] = dict(self._display_keys)
                out["note_events"].extend(res["note_events"])
            self._sim_t = self._now()
            out["t"] = self._sim_t
            out["chord"] = self._current_chord_text()
            out["tonality"] = self._current_tonality_text()
            out["bpm"] = self._current_bpm()
            return out

    # ------------------------------------------------------------------
    # 细分辨率起音函数（log 谱通量）与起音峰拾取
    # ------------------------------------------------------------------
    def _update_odf(self):
        n, hop = self.OF_N, self.OF_HOP
        buf = self._of_buf
        if len(buf) < n:
            return
        nfr = (len(buf) - n) // hop + 1
        idx = np.arange(nfr)[:, None] * hop + np.arange(n)[None, :]
        S = np.abs(np.fft.rfft(buf[idx] * self._of_win, axis=1))[:, self._of_band]
        Ls = np.log1p(self.OF_GAMMA * S)
        Lm = Ls.copy()
        Lm[:, 1:] = np.maximum(Lm[:, 1:], Ls[:, :-1])
        Lm[:, :-1] = np.maximum(Lm[:, :-1], Ls[:, 1:])
        # 线性总功率（dB）：截止"咔哒"的宽带溅射功率很小，起音则带来真实的功率上升
        E = 10.0 * np.log10(np.sum(S * S, axis=1) + 1e-12)
        for k in range(nfr):
            if len(self._of_prev) == 2:
                v = float(np.sum(np.maximum(Ls[k] - self._of_prev[0], 0.0)))
            else:
                v = 0.0
            self._of_prev.append(Lm[k])
            self._odf_t.append((self._of_pos + k * hop + n / 2.0) / self.sr)
            self._odf_v.append(v)
            self._odf_e.append(float(E[k]))
        self._of_buf = buf[nfr * hop:]
        self._of_pos += nfr * hop
        self._pick_odf_peaks()

    def _pick_odf_peaks(self):
        v, t, e = self._odf_v, self._odf_t, self._odf_e
        W = 2                                       # ±2 帧（≈±11 ms）局部最大：硬截止"咔哒"后 20 ms 的重按也能分开
        decay = 0.5 ** (self.OF_HOP / self.sr / 2.0)  # 近期最大值半衰期 2 s
        while self._odf_checked + W < len(v):
            i = self._odf_checked
            self._odf_checked += 1
            vi = v[i]
            self._odf_max = max(vi, self._odf_max * decay)
            if i < W or vi <= 0.0 or vi < max(v[i - W:i + W + 1]):
                continue
            lo = max(0, i - 64)                     # 近 ≈340 ms 中位数作背景
            med = float(np.median(v[lo:i]))
            thr = 1.4 * med + max(self.OF_MIN, 0.08 * self._odf_max)
            if vi < thr:
                if vi >= 0.3 * thr:
                    # 弱起音峰：密集段落里背景（近 340 ms 中位数）被抬高，真实按键的通量峰常过不了门限；
                    # 留作后备判定的起音时刻候选（背景音乐里渐强的长音没有这样的局部峰）
                    # （试过在弱峰 / 截止峰上也做"同键重按"评估：多检翻倍，不用）
                    self._weak_peaks.append((t[i], vi))
                continue
            # 截止（硬切/松键止音）瞬间的"咔哒"也有宽带通量，但其后总能量是下降的：
            # 不作为起音，单独记为"截止候选"（同键重按时用于定位上一音的结束）
            if (e[i + 1] + e[i + 2]) - (e[i - 2] + e[i - 1]) <= 0.0:
                self._off_peaks.append((t[i], vi))
                continue
            a_, c_ = v[i - 1], v[i + 1]
            den = a_ - 2.0 * vi + c_
            d = 0.5 * (a_ - c_) / den if den < -1e-12 else 0.0
            d = max(-0.5, min(0.5, d))
            T = t[i] + d * self.OF_HOP / self.sr + self.OF_OFFSET
            if self._of_peaks and T - self._of_peaks[-1][0] < 0.025:
                if vi > self._of_peaks[-1][1]:
                    old_T = self._of_peaks[-1][0]
                    self._of_peaks[-1] = (T, vi)
                    if self._pending and self._pending[-1] == old_T:
                        self._pending[-1] = T
                continue
            self._of_peaks.append((T, vi))
            self._pending.append(T)
        if len(v) > 1200:
            cut = len(v) - 600
            del v[:cut]
            del t[:cut]
            del e[:cut]
            self._odf_checked -= cut

    def _match_onset(self, t_anchor, after=None, lo=None):
        """在锚点帧附近找对应的起音峰 → (t, 强度) 或 None"""
        lo = t_anchor - 0.075 if lo is None else lo
        hi = t_anchor + 0.050
        if after is not None:
            lo = max(lo, after)
        best = None
        for T, h in reversed(self._of_peaks):
            if T < lo:
                break
            if T > hi:
                continue
            s = h * np.exp(-((T - (t_anchor + 0.005)) / 0.04) ** 2)
            if best is None or s > best[2]:
                best = (T, h, s)
        return None if best is None else (best[0], best[1])

    def _onset_strength_at(self, T):
        for t, h in reversed(self._of_peaks):
            if abs(t - T) < 1e-6:
                return h
            if t < T - 0.1:
                break
        return 0.0

    # ------------------------------------------------------------------
    def _process_frame(self, frame: np.ndarray, t_now: float) -> dict:
        events = []
        spec = np.fft.rfft(frame * self._win, n=self.fft_n)
        mag = np.abs(spec)
        peak = float(mag.max())
        # 逐帧记录各音基频 / 二次谐波处复数谱：用于落音定位与同键重按判定
        self._hist_t.append(t_now)
        self._hist_X.append(spec[self._track_bins].astype(np.complex64))

        # 自适应噪声底
        if peak > 1e-9:
            self._floor = 0.92 * self._floor + 0.08 * max(float(np.median(mag)) * 4.0, 1e-7)

        # 近期峰值（指数衰减）→ 相对门限：播放停止后迅速压制残留/噪声
        self._recent_peak = max(peak, self._recent_peak * np.exp(-self.hop / self.sr * 1.2))
        gate = max(self._floor * 4.0, 1.5e-4, 0.06 * self._recent_peak)

        # 能量门：过静音帧直接跳过（仍更新上一帧谱，避免静音后的新音被旧谱压低攻击比）
        if peak < gate:
            self._prev_mag = mag
            self._release_all(events, t_now)
            self._eval_pending(t_now, events)
            return {"keys": {}, "note_events": events}

        # 相对阈值：灵敏度越高越灵敏
        rel_thr = 0.16 - 0.13 * self.sensitivity          # 0.03 ~ 0.16
        abs_thr = max(self._floor * 2.0, peak * rel_thr)
        peaks = self._find_peaks(mag, abs_thr)
        # 帧内主导性：弱于最强峰 12% 的候选视为杂峰（如基频的弱副峰/拍频），剔除
        if peaks:
            top_amp = peaks[0][1]
            peaks = [p for p in peaks if p[1] >= 0.12 * top_amp]
        # 基频降级：若峰 f 的 f/k (k=2,3,4) 处有显著能量，则 f 是谐波，真正基频在更低处
        peaks = self._lower_fundamentals(peaks, mag)
        midis_all = self._peaks_to_notes(peaks, mag)

        # 谐波结构校验：新音必须带谐波；已活跃的音只要在峰中出现就保持（避免谐波闪烁导致长音被切）
        midis_new = [m for m in midis_all if self._has_harmonic_support(m, mag)]

        # 攻击强度记录：对比上一帧同频幅度，取近期（0.35 s 内）最大值，同时记下"骤起"发生的帧时刻。
        # 超过 0.35 s 的旧记录直接被新值覆盖（否则流开头的巨大比值会永久压住后来的真实骤起）
        for m in midis_new:
            idx = self._bin_of(m)
            prev_amp = float(self._prev_mag[idx]) if self._prev_mag is not None else 0.0
            cur_amp = self._amp_of(m, mag)
            ratio = cur_amp / max(prev_amp, 1e-9)
            if ratio > self._attack.get(m, 0.0) or t_now - self._attack_t.get(m, -1e9) > 0.35:
                self._attack[m] = ratio
                self._attack_t[m] = t_now
        self._prev_mag = mag

        # 谐波去重：整数倍频只保留基频；弱谐波去掉，强独立音保留
        amp_dict = {}
        for px, pamp in peaks:
            pf = px * self.sr / self.fft_n
            if 60 <= pf <= 5000:
                pm = int(round(69 + 12 * np.log2(pf / 440)))
                amp_dict[pm] = max(amp_dict.get(pm, 0), pamp)
        if self.timbre is not None:
            # 谐波强的乐器：更低的键正在发声（这一帧候选或已在响）但它的峰不在前 12 个峰里时，也用它来判谐波
            present = set(midis_all) | set(self.active.keys())
            midis_new = self._drop_timbre_harmonics(midis_new, amp_dict, mag, present)
            midis_all = self._drop_timbre_harmonics(midis_all, amp_dict, mag, present)
        midis_new = self._dedup_harmonics(midis_new, amp_dict)
        midis_all = self._dedup_harmonics(midis_all, amp_dict)

        # 范围过滤 + 吸附到乐器可用音（含移调）
        valid = self.instrument.valid_midis()
        lo, hi = valid[0] - 1, valid[-1] + 1
        # 按音色模板认键的乐器：基频弱、能量在高次谐波（镜花之琴中音区的 4~6 次谐波已高出琴的音域），
        # 音域以上的峰也保留下来跟踪，由 _relabel 换算回真正的键（换算不出来的不报）
        hi_x = valid[-1] + self.TMPL_EXTRA_HI if self.key_tmpl is not None else hi

        def snap(ms):
            out = []
            for m in ms:
                if lo <= m <= hi:
                    s = min(valid, key=lambda v: abs(v - m))
                    if s not in out:
                        out.append(s)
                elif hi < m <= hi_x and m not in out:
                    out.append(m)
            return out
        snapped_new = snap(midis_new)
        # raw：新音候选 ∪ 仍在峰中出现且幅度仍显著（≥15% 帧峰值）的已活跃音。
        # 已活跃音只认"精确命中"的峰（四舍五入后的音高就是它本身）：背景音乐/音效里的半音、
        # 非白键音被吸附到相邻琴键时，不应把一个已经结束的音一直撑着
        exact_all = set(midis_all)
        press_gate = self._press_gate()
        raw = {m for m in snapped_new if m not in self.active
               and self._amp_of(m, mag) >= press_gate}
        for m in self.active:
            # 背景声恰好落在同一个音高，也不能无限续住已衰减的琴音。
            if (m in exact_all and self._amp_of(m, mag) >=
                    max(0.15 * peak, 0.035 * self.active[m]["maxamp"])):
                raw.add(m)

        # 连续帧确认：连续缺席 2 帧才重置 streak
        streak, miss = self._streak, self._miss
        for m in list(streak.keys()):
            if m not in raw:
                miss[m] = miss.get(m, 0) + 1
                if miss[m] >= 2:
                    streak[m] = 0
                    self._attack.pop(m, None)
                    self._attack_t.pop(m, None)
        for m in raw:
            miss[m] = 0
            if streak.get(m, 0) == 0:
                self._first_seen[m] = t_now
            streak[m] = streak.get(m, 0) + 1
            if m in self.active:
                self.active[m]["last_raw"] = t_now
        current = {m for m, c in streak.items() if c >= self.confirm}

        # 起音/落音跟踪
        attack_min = max(1.3, 2.2 - self.sensitivity)
        for m in current:
            amp = self._amp_of(m, mag)
            a = self.active.get(m)
            if a is None:
                # 攻击门限：骤起才视为真实敲击（本音及 ±1 半音，起音帧可能识别到相邻音）。
                # 只认 0.35 s 内的攻击记录：非白键半音（如 C#）的攻击值永远不会随 streak 清除，
                # 原实现会被很久以前的陈旧攻击值误放行
                cand = [(self._attack.get(mm, 0.0), mm) for mm in range(m - 1, m + 2)
                        if t_now - self._attack_t.get(mm, -1e9) <= 0.35]
                t_first = self._first_seen.get(m, t_now)
                on = None
                if cand:
                    nearby_attack, m_att = max(cand)
                    if nearby_attack >= attack_min:
                        # 以"骤起"发生的帧为锚点找起音峰（该音可能早已以旁瓣形式出现，首次可见时刻不可靠）
                        t_att = self._attack_t.get(m_att, t_first)
                        on = self._match_onset(t_att, lo=min(t_first, t_att) - 0.075)
                        if on is not None and on[0] < t_first - 0.075:
                            on = None
                if on is not None:
                    ok = self._press_ok(m, on[0])
                    if ok is None:
                        continue          # 判定所需的帧还没到，下一帧再判
                    if ok:
                        r = self._rise_at(m, on[0])
                        if r is not None and r["la"] < 90.0:
                            self._fresh.setdefault(m, deque(maxlen=16)).append(r["la"])
                        self._open_note(m, min(on[0], t_now), t_now, amp, on[1])
                        continue
                # 后备判定：逐帧比值不够骤、附近没有起音峰、或在那个起音峰上不像按键。
                # 快段落里很常见——这个频点本来就有余音 / 邻键泄漏，逐帧比值上不去；密集处起音峰没被挑出来，
                # 或别的音同时截止、起音被当成了"截止咔哒"。直接找这个音高电平骤升的时刻，用更严的条件判定
                fb = self._fallback_press(m, t_first, t_now)
                if not fb:
                    continue          # None：所需的帧还没到；False：不像按键
                self._open_note(m, min(fb[0], t_now), t_now, amp, fb[1], fallback=True)
                continue
            if self.active_frames.get(m, 0) > 0:
                # 缺席后重新出现：有新起音且攻击骤起 → 同键重按；否则视为同一音短暂缺失
                t_first = self._first_seen.get(m, t_now)
                t_att = self._attack_t.get(m, t_first)
                fresh = t_now - t_att <= 0.35 and self._attack.get(m, 0.0) >= attack_min
                on = self._match_onset(t_att, after=a["last_raw_before_gap"] + 0.02,
                                       lo=min(t_first, t_att) - 0.075) if fresh else None
                h = a.get("h", 0)
                ref_db = float(_db(a["ref"][h])) if a.get("ref") is not None else None
                ok = self._press_ok(m, on[0], h, ref_db) if on is not None else False
                if ok is None:
                    continue          # 等判定所需的帧到达再判
                if ok:
                    old = self.active.pop(m)
                    end, reason = self._end_time(m, old, t_limit=on[0])
                    self._close_note(m, old, end, reason, events)
                    self._open_note(m, on[0], t_now, amp, on[1])
                    continue
                self.active_frames[m] = 0
            a["n"] += 1
            a["last"] = t_now
            a["maxamp"] = max(a["maxamp"], amp)
            a["amin"] = min(a["amin"], amp)
            a["amp"] = amp
        for m in list(self.active.keys()):
            if m not in current:
                a = self.active[m]
                if self.active_frames.get(m, 0) == 0:
                    a["last_raw_before_gap"] = a["last_raw"]
                self.active_frames[m] = self.active_frames.get(m, 0) + 1
                if self.active_frames[m] >= self.grace:
                    self.active.pop(m)
                    self.active_frames.pop(m, None)
                    end, reason = self._end_time(m, a)
                    self._close_note(m, a, end, reason, events)

        # 起音参考电平：起音后整窗（≥43 ms）的第一帧，作为"刚按下"时的电平
        X = self._hist_X[-1]
        for m, a in self.active.items():
            if self.key_tmpl is not None and "lab" not in a and t_now >= a["start"] + 0.1:
                self._relabel(m, a)
            if a["ref"] is None and t_now >= a["start"] + 0.043:
                j = m - _TRACK_LO
                if 0 <= j < X.shape[1]:
                    xs = np.abs(X[:, j])
                    a["ref"] = xs.astype(np.float64)
                    a["h"] = int(np.argmax(xs))
                    self._set_ref_db(a)

        self._eval_pending(t_now, events)

        keys = {}
        for m, a in self.active.items():
            lab = a.get("lab", m)
            if self.active_frames.get(m, 0) == 0 and lab is not None and lab >= 0 \
                    and lab in self.instrument.valid_midis():
                label, _ = self.instrument.label_of(lab)
                keys[label] = lab
        return {"keys": keys, "note_events": events}

    # ------------------------------------------------------------------
    # 起音确认（BPM 用）与同键重按：起音前后整窗比较
    # ------------------------------------------------------------------
    RETRIG_DELAY = 0.18      # 起音后多久评估（需要 T+130 ms 处的"持续性"帧）

    def _press_gate(self):
        """新按键最低电平：相对已确认起音的稳健电平，整体音量较小时同比降低。"""
        return self._press_level * (0.12 - 0.07 * self.sensitivity)

    def _eval_pending(self, t_now, events):
        while self._pending and self._pending[0] <= t_now - self.RETRIG_DELAY:
            T = self._pending.popleft()
            self._eval_retrig(T, t_now, events)

    def _frames_around(self, T):
        """起音 T 的参照帧下标：jb = 窗完全在 T 之前的最后一帧；ja = 窗完全在 T 之后的第一帧；
        j2 = 中心 ≥ T+130 ms 的第一帧（用于判断变化是否持续，排除短促的噪音音效）"""
        ts = np.fromiter(self._hist_t, dtype=np.float64)
        jb = int(np.searchsorted(ts, T - 0.043, side="right")) - 1
        ja = int(np.searchsorted(ts, T + 0.043, side="left"))
        j2 = int(np.searchsorted(ts, T + 0.130, side="left"))
        return ts, jb, ja, j2

    def _valid_track_idx(self):
        return np.array([m - _TRACK_LO for m in self.instrument.valid_midis()
                         if 0 <= m - _TRACK_LO < self._track_bins.shape[1]], dtype=int)

    def _rise_at(self, m, T, h=0):
        """本音频点（h=0 基频 / h=1 二次谐波）在起音 T 前后整窗的电平变化，用于判断"这是不是一次真实按键"。
        返回 dict：rise 本音上升 dB；med 乐器其它琴键基频频点上升的中位数（宽带噪音会让所有频点一起涨）；
        prom 起音后本音比其它琴键频点中位电平高多少 dB（真实乐音是突出的窄峰）；la 起音后本音电平 dB。
        起音后的整窗帧尚未到达时返回 None。"""
        if len(self._hist_t) < 4:
            return None
        ts, jb, ja, _ = self._frames_around(T)
        if ja >= len(ts):
            return None
        if jb < 0:
            # 起音就在音频流开头，之前没有任何声音可比：视为从静音中按下
            return {"rise": 99.0, "med": 0.0, "prom": 99.0, "la": 99.0}
        j = m - _TRACK_LO
        if not (0 <= j < self._track_bins.shape[1]):
            return {"rise": 99.0, "med": 0.0, "prom": 99.0, "la": 99.0}
        Xb, Xa = self._hist_X[jb], self._hist_X[ja]
        la = float(_db(Xa[h, j]))
        rise = la - float(_db(Xb[h, j]))
        jv = self._valid_track_idx()
        jv = jv[jv != j]
        if jv.size:
            la_o = _db(Xa[0, jv])
            med = float(np.median(la_o - _db(Xb[0, jv])))
            prom = la - float(np.median(la_o))
        else:
            med, prom = 0.0, 99.0
        return {"rise": rise, "med": med, "prom": prom, "la": la}

    @staticmethod
    def _is_fresh_press(r, ref_db=None):
        """起音前后本音频点的变化是否像一次真实按键（快速判定；不确定时由 _press_ok 等瞬态消退后再判）：
        - 本音上升 ≥4 dB（仍在响的余音被别的音的起音"重新检出"时几乎不上升）；
        - 且 本音上升明显高于其它频点的整体抬升，或 本音在起音后的频谱里是突出的窄峰
          （宽带噪音音效会把所有频点一起抬高、本音并不突出）；
        - 若是同一键再次按下：起音后要回到该音"刚按下"时的电平（原神乐器没有力度变化）——
          背景音乐同频干涉造成的凹陷回升只会回到衰减中的电平。"""
        if r["rise"] < 4.0:
            return False
        if r["rise"] - r["med"] < 3.0 and r["prom"] < 15.0:
            return False
        if ref_db is not None and r["la"] < ref_db - 3.0:
            return False
        return True

    def _persist_at(self, m, T, h=0):
        """起音后 130 ms（瞬态已消退）本音相对起音前的电平变化 rise2、其它琴键频点同期变化的中位数 med2，
        此时本音比其它琴键频点中位电平高多少 prom2，以及此时本音电平 l2。该帧尚未到达时返回 None。"""
        ts, jb, _, j2 = self._frames_around(T)
        if jb < 0 or j2 >= len(ts):
            return None
        j = m - _TRACK_LO
        if not (0 <= j < self._track_bins.shape[1]):
            return {"rise2": 99.0, "med2": 0.0, "prom2": 99.0, "l2": 99.0}
        Xb, X2 = self._hist_X[jb], self._hist_X[j2]
        l2 = float(_db(X2[h, j]))
        jv = self._valid_track_idx()
        jv = jv[jv != j]
        if jv.size:
            l2_o = _db(X2[0, jv])
            prom2 = l2 - float(np.median(l2_o))
            med2 = float(np.median(l2_o - _db(Xb[0, jv])))
        else:
            prom2, med2 = 99.0, 0.0
        return {"rise2": l2 - float(_db(Xb[h, j])), "med2": med2, "prom2": prom2, "l2": l2}

    def _press_ok(self, m, T, h=0, ref_db=None):
        """起音 T 是否是键 m 的一次真实按键：True / False / None（所需的帧还没到，下一帧再判）。
        先用起音后第一个整窗帧快速判定；不通过时等到起音后 130 ms 再判，原因有二：
        - 和弦（尤其低音和弦）同时起音时，宽带起音瞬态会把所有频点一起抬高 10 dB 以上；
        - 低音区相邻白键只差 10~18 Hz（在 4096 点窗主瓣内），邻键余音的泄漏与拍频会掩盖起音瞬间的上升，
          而移调到低音的采样起音也更慢。
        瞬态消退后：真实乐音仍明显高于起音前、且是突出的窄峰；仍在响的余音不会上升；噪音音效已落回原电平。"""
        r = self._rise_at(m, T, h)
        if r is None:
            return None
        if self._is_fresh_press(r, ref_db):
            return True
        p = self._persist_at(m, T, h)
        if p is None:
            return None
        if p["rise2"] < 4.0:
            return False
        if ref_db is not None and p["l2"] < ref_db - 4.5:
            return False
        return p["prom2"] >= 8.0 or p["rise2"] - p["med2"] >= 3.0

    FB_SKIP = ()             # 不用后备判定的乐器。1.0.6 时圆号在列（多检比救回的多）；1.0.8 有了按音色模板改判键位后，
                             # 圆号用后备判定：录像里召回 39% → 55%，F1 42 → 49
    FB_RISE = 6.0            # 后备判定：本音骤升至少这么多 dB
    FB_SEP = 6.0             # 且比其它琴键频点的整体抬升（中位数）高这么多 dB
    FB_PERSIST = 3.0         # 且起音后 130 ms 仍比起音前高这么多 dB
    FB_LEVEL = 4.0           # 且起音后的电平不低于这个键"刚按下"的典型电平这么多 dB
                             # （原神乐器没有力度变化，每次按下电平相同；背景音乐里的同音高长音通常弱得多、起得也慢）

    def _fresh_ref(self, m):
        """键 m "刚按下"时的典型电平（dB）：最近确认的按键的中位数；本键样本不够时用 ±5 半音内的键"""
        d = self._fresh.get(m)
        if d is not None and len(d) >= 3:
            return float(np.median(d))
        vals = [float(np.median(dd)) for mm, dd in self._fresh.items() if abs(mm - m) <= 5 and len(dd) >= 2]
        return float(np.median(vals)) if len(vals) >= 2 else None

    def _fallback_press(self, m, t_first, t_now):
        """后备按键判定 → (起音时刻, 强度) / False（不像按键）/ None（所需的帧还没到）。
        候选起音时刻：t_first 前 150 ms 到现在之前 40 ms 内的起音峰、截止峰、弱起音峰与各帧时刻（不早于 0.45 s 前，
        不早于这个键上一次开音后 200 ms），取本音骤升最多的那个；还要通过 _fb_explained（谐波 / 泄漏）与持续性检查。
        用游戏录像（界面按键高亮 = 真值）调过：救回的真按键约是多出来的误检的 3 倍"""
        if len(self._hist_t) < 6 or self.instrument.name in self.FB_SKIP:
            return False
        prev = self._last_start.get(m, -1e9)
        lo = max(t_first - 0.15, t_now - 0.45, prev + 0.2)
        hi = min(t_first + 0.02, t_now - 0.04)
        if hi < lo:
            return False
        # 大和弦（同一起音已经认出 ≥4 个音）里不用后备判定：密集的和弦里各音互相泄漏、拍频，
        # 后备判定开出的音起音时刻也不准，会把一次按下拆开（边界值排查数键会出错）
        if sum(1 for a in self.active.values() if abs(a["start"] - t_first) <= 0.1) >= 4:
            return False
        # 只差一个半音的相邻键（E-F、B-C）正在响、且不比 m 弱 6 dB 以上：两个频率落在同一个主瓣里互相拍频，
        # 电平忽高忽低，骤升不可信
        X = np.abs(self._hist_X[-1][0])
        j = m - _TRACK_LO
        for n in (m - 1, m + 1):
            jn = n - _TRACK_LO
            if n in self.active and 0 <= jn < X.shape[0] and 0 <= j < X.shape[0] and _db(X[jn]) >= _db(X[j]) - 6.0:
                return False
        ref = self._fresh_ref(m)
        if ref is None:
            return False              # 还不知道这个键（及附近的键）按下时有多响时不用后备判定
        cands = {}
        for T, h in self._of_peaks:
            if lo <= T <= hi:
                cands[round(T, 4)] = h
        for T, _h in self._off_peaks:
            if lo <= T <= hi:
                cands.setdefault(round(T, 4), 0.0)
        for T, _h in self._weak_peaks:
            if lo <= T <= hi:
                cands.setdefault(round(T, 4), 0.0)
        for c in self._hist_t:
            if lo <= c <= hi:
                cands.setdefault(round(c, 4), 0.0)
        best, pending = None, False
        for T, h in cands.items():
            r = self._rise_at(m, T)
            if r is None:
                pending = True
                continue
            # 这个键 1 s 内刚开过音：多半还在响（上一个音被提前判了结束），起伏更容易像"骤升"，要求更高
            need = self.FB_RISE + (4.0 if T - prev < 1.0 else 0.0)
            if r["rise"] < need or r["rise"] - r["med"] < self.FB_SEP:
                continue              # 别的音的起音瞬态会把所有频点一起抬高：必须明显高于整体抬升
            rr = self._robust_rise(m, T)
            if rr is None:
                pending = True
                continue
            if rr < need - 2.0:
                continue              # 相邻键同时在响时两者拍频，电平一起一伏：起音后两帧都要高于起音前两帧
            if r["la"] < ref - self.FB_LEVEL:
                continue              # 比这个键按下时的典型电平弱得多：多半是背景音乐里的同音高长音
            if best is None or r["rise"] > best[2]:
                best = (T, h, r["rise"], r["la"])
        if best is None:
            return None if pending else False
        if self._fb_explained(m, best[0], best[3]):
            return False
        p = self._persist_at(m, best[0])
        if p is None:
            return None
        if p["rise2"] < self.FB_PERSIST or (p["prom2"] < 8.0 and p["rise2"] - p["med2"] < 3.0):
            return False
        # 起音时刻对齐到前 80 ms ~ 后 30 ms 内最近的正式起音峰（多半是同一次按下的和弦起音；
        # 和弦里被遮住的低音电平起得慢，"骤升最多"的帧会偏晚）。帧网格上的时刻会把一个和弦拆成几次"按下"，
        # 边界值排查的按键计数会因此出错。对齐的前提是这个音在那个起音峰上也确实骤升了
        T, h = best[0], best[1]
        near = []
        for t, hh in self._of_peaks:
            if T - 0.08 <= t <= T + 0.03:
                rp = self._rise_at(m, t)
                if rp is not None and rp["rise"] >= self.FB_RISE - 2.0:
                    near.append((abs(t - T), t, hh))
        if near:
            _d, T, h = min(near)
        return T, max(h, self.OF_MIN)

    def _robust_rise(self, m, T):
        """起音后两帧电平的较小值 − 起音前两帧电平的较大值（dB）：相邻键拍频造成的电平起伏不算骤升；帧没到时 None"""
        ts, jb, ja, _ = self._frames_around(T)
        if jb < 1 or ja + 1 >= len(ts):
            return None
        j = m - _TRACK_LO
        if not (0 <= j < self._track_bins.shape[1]):
            return None
        after = min(abs(self._hist_X[ja][0, j]), abs(self._hist_X[ja + 1][0, j]))
        before = max(abs(self._hist_X[jb][0, j]), abs(self._hist_X[jb - 1][0, j]))
        return float(_db(after) - _db(before))

    def _leak_from_others(self, m, T):
        """起音 T 之后的帧里，其它琴键的基频（按各自电平与分析窗频率响应）泄漏到 m 基频频点的电平（dB）"""
        ts, jb, ja, _ = self._frames_around(T)
        if ja >= len(ts):
            return -999.0
        Xa = np.abs(self._hist_X[ja][0])
        fm = _midi_freq(m)
        tot = 0.0
        for n in self.instrument.valid_midis():
            j = n - _TRACK_LO
            if n == m or not (0 <= j < Xa.shape[0]):
                continue
            d = abs(_midi_freq(n) - fm)
            if d >= 599.0:
                continue
            tot += (Xa[j] * 10 ** (self._leak_db[int(round(d * 2.0))] / 20.0)) ** 2
        return 10.0 * np.log10(tot) if tot > 0 else -999.0

    def _fb_explained(self, m, T, la_m):
        """后备判定的候选 m 能否被别的键解释：只是更低的键的谐波（见 _fb_harmonic），
        或只是附近更响的键泄漏过来的（m 的电平不比按窗函数算出的泄漏高 6 dB 以上）"""
        if la_m <= self._leak_from_others(m, T) + 6.0:
            return True
        return self._fb_harmonic(m, T, la_m)

    def _fb_harmonic(self, m, T, la_m):
        """后备判定的候选 m 是否只是更低的键 n 的谐波：m ≈ h·n（h = 2~8，偏差 < 1.5%），
        n 正在响（包括刚被同键重按、还没认出来的）或 n 的基频在 T 也骤升 ≥4 dB，且 m 的电平不比 n 的基频高出
        max(3 dB, 该音区第 h 次谐波的实测电平 + 2 dB)。
        （重按一个还在响的键时，它的基频只回升 1~3 dB，衰减得更快的谐波却回升很多，单看 m 像一次新按键）"""
        fm = _midi_freq(m)
        for n in self.instrument.valid_midis():
            if n >= m:
                break
            if m - n <= 2:
                # 相邻的白键（低音区相差不到一个频点主瓣）：新按下的邻键明显更响时，m 的骤升只是它的泄漏
                rn = self._rise_at(n, T)
                if rn is not None and rn["rise"] >= 6.0 and rn["la"] >= la_m + 6.0:
                    return True
                continue
            q = fm / _midi_freq(n)
            h = int(round(q))
            if h < 2 or h > 8 or abs(q / h - 1.0) > 0.015:
                continue
            rn = self._rise_at(n, T)
            if rn is None:
                continue
            if n not in self.active and rn["rise"] < 4.0:
                continue
            lv = 3.0
            if self.timbre is not None:
                tl = self.timbre[timbre_register(n)].get(h)
                if tl is not None:
                    lv = max(lv, tl + HARM_MARGIN_DB)
            if la_m <= rn["la"] + lv:
                return True
        for n in self.instrument.valid_midis():
            if m < n <= m + 2:
                rn = self._rise_at(n, T)
                if rn is not None and rn["rise"] >= 6.0 and rn["la"] >= la_m + 6.0:
                    return True
        return False

    def _onset_influence(self, c):
        """帧中心 c 的分析窗（±43 ms）是否覆盖了某个起音后 100 ms 内的起音瞬态"""
        for T, _h in reversed(self._of_peaks):
            if T > c + 0.043:
                continue
            return T >= c - 0.143
        return False

    def _add_beat_onset(self, T, strength):
        """BPM 用起音事件：起音峰 + 音高证据（与音符跟踪解耦，同键连按/漏开的音也能计入）"""
        for e in reversed(self.beat_onsets[-8:]):
            if abs(e[0] - T) < 0.035:
                e[0] = min(e[0], T)
                e[1] = max(e[1], strength)
                self._onsets_ver += 1
                return
        i = len(self.beat_onsets)
        while i > 0 and self.beat_onsets[i - 1][0] > T:
            i -= 1
        self.beat_onsets.insert(i, [T, strength])
        if len(self.beat_onsets) > 2000:
            self.beat_onsets = self.beat_onsets[-1000:]
        self._onsets_ver += 1

    @staticmethod
    def _related(dm, h):
        """新音 n 与被判音 m（dm = m - n）是否会把能量泄漏到 m 的第 h 个谐波频点"""
        if abs(dm) <= 2:
            return True
        if h == 0:
            return dm in (12, 19, 24, 28, 31)
        return dm in (-12, 7, 12, 16, 19, -10, -11, -13, -14)

    def _eval_retrig(self, T, t_now, events):
        """起音 T 处：记 BPM 用的起音，并判断正在响的键是不是被同键重按了"""
        if len(self._hist_t) < 4:
            return
        ts, jb, ja, j2 = self._frames_around(T)
        if jb < 0 or ja >= len(ts):
            return
        j2 = min(j2, len(ts) - 1)
        Xb, Xa, X2 = self._hist_X[jb], self._hist_X[ja], self._hist_X[j2]
        strength = self._onset_strength_at(T)
        jv = self._valid_track_idx()
        if jv.size:
            la_v, lb_v = _db(Xa[0, jv]), _db(Xb[0, jv])
            # 音高证据：乐器某个可用音的基频频点上升 ≥2 dB，且不是很弱的分量 → 这是一次真实按键（BPM 用）
            if np.any((la_v - lb_v >= 2.0) & (la_v >= la_v.max() - 20.0)
                      & (np.abs(Xa[0, jv]) >= self._press_gate())):
                self._add_beat_onset(T, strength)
        if not self.active:
            return
        new_notes = [n for n, a in self.active.items() if abs(a["start"] - T) < 0.05]
        for m in list(self.active.keys()):
            a = self.active[m]
            if a["start"] > T - 0.08 or a["ref"] is None:
                continue
            if self.active_frames.get(m, 0) > 0:
                continue
            j = m - _TRACK_LO
            if not (0 <= j < Xb.shape[1]):
                continue
            ref = a["ref"]
            hit = False
            lb0, la0, l20 = _db(Xb[0, j]), _db(Xa[0, j]), _db(X2[0, j])
            for h in (0, 1):
                if ref[h] < 0.1 * ref.max():
                    continue          # 该谐波太弱，不可靠
                if h == 1:
                    # 用二次谐波作证据时，基频必须同向变化（真正重按时所有分音一起回升）：
                    # 弱谐波（比最强分音低 12 dB 以上）绝对电平低，一点噪音就能让它"上升"，要求基频也上升并持续；
                    # 强谐波至少要求基频没有下降
                    if ref[1] < 0.25 * ref.max():
                        if not (la0 - lb0 >= 2.0 and l20 - lb0 >= 1.0):
                            continue
                    elif la0 < lb0 - 0.5:
                        continue
                lb, la, l2, lref = _db(Xb[h, j]), _db(Xa[h, j]), _db(X2[h, j]), _db(ref[h])
                # 重按 = 起音后电平回到该音"刚按下"时的水平，且相对起音前有上升。
                # 余音衰减慢（-8~-13 dB/s）时连按 0.3 s 只回升约 2 dB，故分两档：
                #   回到刚按下电平 ±1.5 dB 且上升 ≥1 dB；或回到 -3 dB 内且上升 ≥2 dB
                rise = la - lb
                if not ((rise >= 1.0 and la >= lref - 1.5) or (rise >= 2.0 and la >= lref - 3.0)):
                    continue
                # 抗噪：上升要持续——起音后 130 ms 仍明显高于起音前（游戏里的短促音效、别的音的起音瞬态
                # 20~120 ms 就过去了，电平会落回原来的衰减轨迹）
                if l2 - lb < max(0.5, 0.3 * rise):
                    continue
                blocked = False
                for nn in new_notes:
                    if nn != m and self._related(m - nn, h):
                        jn = nn - _TRACK_LO
                        la_n = _db(np.max(np.abs(Xa[:, jn]))) if 0 <= jn < Xa.shape[1] else -999
                        if la < la_n - 3.0:
                            blocked = True
                            break
                if not blocked:
                    hit = True
                    break
            if not hit and self.instrument.name not in self.FB_SKIP:
                # 电平几乎没回升（上一次按下后还没怎么衰减）：看基频相位是否在起音处"重置"
                hit = self._phase_repress(m, a, ts, jb, ja, Xb, Xa, new_notes)
            if not hit:
                continue
            old = self.active.pop(m)
            # 重按前若已松键止音（有急速截止），上一音在截止处结束；否则在新起音处结束
            end, reason = self._end_time(m, old, t_limit=T)
            if not (reason == "release" and end < T - 0.008):
                click = self._click_before(old, T)
                end, reason = (click, "release") if click is not None else (T, "retrig")
            self._close_note(m, old, end, reason, events)
            self._open_note(m, T, t_now, old["amp"], strength)
            na = self.active[m]
            na["last_raw"] = old["last_raw"]
            # 沿用上一次"刚按下"的参考电平：原神乐器没有力度变化，每次按下电平相同；
            # 若改用本次测得的电平，一次被噪音抬高的误判会把参考越抬越高、引发连锁误判
            na["ref"] = old["ref"].copy()
            na["h"] = old["h"]
            self._set_ref_db(na)

    PH_JUMP = 1.6            # 同键重按的相位证据：起音前后基频相位偏离稳态漂移的量（弧度）
    PH_STEADY = 1.0          # 起音前、后两段各自的相位漂移相差不超过这么多（弧度）才算稳态、相位可信

    def _phase_repress(self, m, a, ts, jb, ja, Xb, Xa, new_notes):
        """同键重按、但电平几乎没回升（上一次按下后衰减不多）时的相位证据：游戏重按时重新播放采样，
        这个键基频处的相位相对稳态漂移会跳变。用游戏录像调过：只在正式起音峰上用，要求起音前后各自是稳态、
        相位跳 ≥1.6 弧度、电平不低于"刚按下"时 3 dB 以上、二次谐波的回升不低于整体抬升，且同一起音没有
        与它有泄漏关系的新音（别的音的泄漏也会扰动相位）"""
        s = ja - jb
        if s < 1 or jb - s < 0 or ja + s >= len(ts):
            return False
        for nn in new_notes:
            if nn != m and self._related(m - nn, 0):
                return False
        j = m - _TRACK_LO
        if not (0 <= j < Xa.shape[1]):
            return False
        if _db(Xa[0, j]) < _db(a["ref"][0]) - 3.0:
            return False
        jv = self._valid_track_idx()
        jv = jv[jv != j]
        if jv.size:
            med = float(np.median(_db(Xa[0, jv]) - _db(Xb[0, jv])))
            if (_db(Xa[1, j]) - _db(Xb[1, j])) - med < 0.0:
                return False
        w = 2.0 * np.pi * _midi_freq(m)
        ph = lambda k: float(np.angle(self._hist_X[k][0, j]))
        wrap = lambda v: (v + np.pi) % (2.0 * np.pi) - np.pi
        d_before = wrap(ph(jb) - ph(jb - s) - w * (ts[jb] - ts[jb - s]))
        d_after = wrap(ph(ja + s) - ph(ja) - w * (ts[ja + s] - ts[ja]))
        if abs(wrap(d_after - d_before)) > self.PH_STEADY:
            return False
        d_ref = float(np.angle(np.exp(1j * d_before) + np.exp(1j * d_after)))
        d_cross = wrap(ph(ja) - ph(jb) - w * (ts[ja] - ts[jb]))
        return abs(wrap(d_cross - d_ref)) >= self.PH_JUMP

    def _set_ref_db(self, a):
        """记录音符"刚按下"电平，并更新所属起音事件中最强音的电平（用于识别起音旁瓣）"""
        a["ref_db"] = float(_db(np.max(a["ref"])))
        self._press_levels.append(float(np.max(a["ref"])))
        self._press_level = float(np.median(self._press_levels))
        ev = a.get("ev")
        if ev is not None:
            ev[3] = max(ev[3], a["ref_db"])

    # ------------------------------------------------------------------
    # 落音定位
    # ------------------------------------------------------------------
    # 按住发声的乐器（圆号）：松键时刻 = 电平跌出"按住时的平台"。平台趋势线 = 起音后 60 ms 起、前 30 帧（≈0.64 s）
    # 拟合（斜率钳在 -40~0 dB/s，截距取 75% 分位，之后固定）；之后连续 8 帧低于平台 8 dB 的第一处跌落，
    # 取它的 -6 dB 交越，按 -6 → -12 dB 用时查截止校正表扣除释放尾音。
    # 游戏录像里圆号键面在按住期间一直变色，对照 ~90 个音：|误差| 中位 323 → 231 ms（琴类规则对圆号不适用：
    # 圆号起伏大、松键跌落慢，-6 / -12 dB 的截止条件常被相邻音、颤音触发，或一直等不到而记成"余音衰减"）。
    # 合成基准（理想的平稳持续音）时长 MAE 0.7 → 10.6 ms。
    TMPL_SAME_ONSET_H = 2     # 音域以上的峰是同一起音另一个音的 2~这么多次谐波时不另报（_harm_of_same_onset；
                              # 录像里 2 次最好：镜花之琴的高次谐波本身就能换算出真按下的键，限到 8 次会把它们一起去掉）
    TMPL_EXTRA_HI = 19        # 按模板认键的乐器：音域以上多跟踪这么多半音的峰（见 _process_frame；录像里 12/19/24 中 19 最好）
    HOLD_INSTR = ("晚风圆号",)
    HOLD_DROP, HOLD_SUS, HOLD_BIAS, HOLD_PLAT = 8.0, 8, 0.0, 30

    def _hold_end(self, m, a, t_limit=None):
        j = m - _TRACK_LO
        ts = np.fromiter(self._hist_t, dtype=np.float64)
        X = np.array([x[:, j] for x in self._hist_X])
        L = _db(np.max(np.abs(X), axis=1))
        i0 = int(np.searchsorted(ts, a["start"] + 0.06))
        i1 = len(ts) if t_limit is None else int(np.searchsorted(ts, t_limit))
        if i1 - i0 < 3:
            return None
        plat = None
        tt = ts - ts[i0]
        for i in range(i0, i1):
            if plat is None:
                # 平台趋势线：起音后的帧拟合（斜率钳在 -40~0 dB/s，自然衰减的音不会被当成松键），
                # 截距取残差的 75% 分位；用满 HOLD_PLAT 帧后固定
                seg = slice(i0, i + 1)
                if i - i0 >= 3:
                    c1 = float(np.polyfit(tt[seg], L[seg], 1)[0])
                    c1 = min(0.0, max(-40.0, c1))
                else:
                    c1 = 0.0
                c0 = float(np.percentile(L[seg] - c1 * tt[seg], 75))
                if i - i0 >= self.HOLD_PLAT - 1:
                    plat = (c0, c1)
            else:
                c0, c1 = plat
            ref = lambda k: c0 + c1 * tt[k]
            if i - i0 < 2:
                continue
            w = L[i:i + self.HOLD_SUS]
            if len(w) < 4:
                break
            if (w < np.array([ref(k) for k in range(i, i + len(w))]) - self.HOLD_DROP).all():
                # 松键时刻 = 相对平台的 -6 dB 交越，再按 -6 → -12 dB 用时查截止校正表扣除释放尾音（与 _end_time 相同）
                k = i
                while k > i0 + 1 and L[k - 1] < ref(k - 1) - 6.0:
                    k -= 1
                y0, y1 = L[k - 1] - (ref(k - 1) - 6.0), L[k] - (ref(k) - 6.0)
                c6 = ts[k - 1] + (y0 / (y0 - y1) if y0 > 0 > y1 else 1.0) * (ts[k] - ts[k - 1])
                c12 = None
                for q in range(k, min(len(L), k + 12)):
                    z0, z1 = L[q - 1] - (ref(q - 1) - 12.0), L[q] - (ref(q) - 12.0)
                    if z1 < 0.0:
                        c12 = ts[q - 1] + (z0 / (z0 - z1) if z0 > 0 else 0.0) * (ts[q] - ts[q - 1])
                        break
                t = c6 - _release_bias(None if c12 is None else c12 - c6) - self.HOLD_BIAS
                t = max(a["start"] + 0.02, t)
                if t_limit is not None:
                    t = min(t, t_limit)
                return t, "release"
        return None

    def _end_time(self, m, a, t_limit=None):
        """返回 (结束时刻, 原因)。
        自起音后逐帧扫描该音自身电平：相对"截止前趋势线"首次跌破 -6 dB、随后持续低于趋势线且
        跌够深 → 急速截止，用 -6/-12 dB 交越时间差查表扣除释放尾音偏差得松键时刻；
        否则为自然衰减，取最后一次可见的帧时刻。t_limit：结束时刻上限（同键重按的新起音）。
        抗噪：截止必须是"最终的"——凹陷后 0.35 s 内电平又回升到趋势线附近（背景音乐同频干涉的拍频、
        噪音造成的凹陷），就不算松键，继续向后找。"""
        t_last = a.get("last_raw", a["last"])
        if t_limit is not None:
            t_last = min(t_last, t_limit)
        fb_t = max(a["start"], t_last + 0.5 * self.hop / self.sr)
        if t_limit is not None and fb_t >= t_limit:
            fallback = (t_limit, "retrig")
        else:
            fallback = (fb_t, "decay")
        j_m = m - _TRACK_LO
        if not (0 <= j_m < self._track_bins.shape[1]) or len(self._hist_t) < 6:
            return fallback
        if self.instrument.name in self.HOLD_INSTR:
            r = self._hold_end(m, a, t_limit)
            return r if r is not None else fallback
        ts = np.fromiter(self._hist_t, dtype=np.float64)
        L = _db(np.array([x[a.get("h", 0), j_m] for x in self._hist_X]))
        n_fr = len(ts)
        t_hi = t_last + 0.07
        if t_limit is not None:
            t_hi = min(t_hi, t_limit + 0.02)
        i_ref0 = int(np.searchsorted(ts, a["start"] + 0.043))     # 窗完全落在起音后的首帧
        i_any0 = int(np.searchsorted(ts, a["start"] + 0.021))
        i_end = int(np.searchsorted(ts, t_hi, side="right")) - 1
        # 趋势线只用"电平到顶之后"的帧拟合：起音后电平还要爬升几十毫秒（高音、和弦更明显），
        # 把上升段算进去会让拟合斜率被钳成 0，快衰减的音就会被误判为"截止"
        i_pk_hi = int(np.searchsorted(ts, a["start"] + 0.25, side="right"))
        if i_pk_hi > i_ref0:
            i_ref0 = i_ref0 + int(np.argmax(L[i_ref0:i_pk_hi]))
        # "是否回升"只看到同键重按之前（重按后的电平属于新音）
        k_stop = n_fr if t_limit is None else int(np.searchsorted(ts, t_limit - 0.025, side="right"))
        for i in range(max(1, i_any0 + 1), i_end + 1):
            pre = [k for k in range(i_ref0, i - 2) if ts[k] >= ts[i] - 0.30]
            # 趋势线不可靠：拟合帧不足（音刚开始）或自然衰减比 -40 dB/s 还快（高音、拍频）——
            # 此时自然衰减本身就可能跌破 -6 dB，候选必须表现出"截止式"的急速跌落才算松键
            unreliable = len(pre) < 3
            # 截止前电平起伏大（与相邻键泄漏/背景音乐同频分量发生拍频干涉、或噪音）：干涉凹陷可达 10~17 dB，
            # 此时要求更深的跌落（≥18 dB）才算松键
            turbulent = False
            if len(pre) >= 3:
                tp, lp = ts[pre], L[pre]
                tm, lm = tp.mean(), lp.mean()
                vt = float(np.sum((tp - tm) ** 2))
                c1 = float(np.sum((tp - tm) * (lp - lm)) / vt) if vt > 0 else 0.0
                unreliable = c1 < -40.0
                turbulent = c1 > 5.0           # 余音电平在上升：只可能是干涉拍频
                c1 = min(0.0, max(c1, -40.0))
                c0 = float(lm - c1 * tm)
                turbulent = turbulent or float(np.std(lp - (c0 + c1 * tp))) > 2.5
            else:
                seg = list(range(i_any0, i - 1))
                if not seg:
                    continue
                c1, c0 = 0.0, float(np.max(L[seg]))
            r_prev = c0 + c1 * ts[i - 1]
            r_cur = c0 + c1 * ts[i]
            y0 = L[i - 1] - (r_prev - 6.0)
            y1 = L[i] - (r_cur - 6.0)
            # 第一个低于（本帧所用）趋势线 -6 dB 的帧即候选交越。不要求上一帧在同一条线之上：
            # 趋势线随 i 逐帧重拟合，交越可能恰好落在两次拟合"之间"，那样会被整个跳过
            if y1 >= 0.0:
                continue
            y0 = max(y0, 0.0)
            # 凹陷段：从交越帧起、电平仍低于趋势线 3 dB 的连续帧（遇到重按的新起音即停）
            run = []
            for k in range(i, min(n_fr, i + 6)):
                if t_limit is not None and ts[k] > t_limit - 0.025:
                    break
                if L[k] >= (c0 + c1 * ts[k]) - 3.0:
                    break
                run.append(k)
            if not run:
                continue
            depth = max((c0 + c1 * ts[k]) - L[k] for k in run)
            cut_by_repress = (t_limit is not None and run[-1] + 1 < n_fr
                              and ts[run[-1] + 1] > t_limit - 0.025)
            if cut_by_repress:
                ok = depth >= 9.0                  # 紧接着同键重按：凹陷被新音提前填平
            elif turbulent:
                ok = depth >= 18.0 and len(run) >= 2
            else:
                ok = depth >= 12.0 and (len(run) >= 2 or depth >= 18.0)
            if not ok:
                continue          # 只是干涉/拍频造成的短暂凹陷，继续向后找
            # 回升检验：凹陷之后 0.35 s 内，电平又回到截止前电平 -6 dB 以上、且比凹陷底部回弹 ≥8 dB → 不是松键。
            # 截止前电平按温和斜率（至多 -12 dB/s，琴类余音的典型衰减）外推——用拟合的陡斜率外推 0.3 s 后
            # 阈值会低到被相邻键的泄漏"冒充"成回升。
            # 别的音起音瞬态（起音后 100 ms 内）覆盖到的帧不算回升：那是它的宽带瞬态漏到了本音频点
            l_min = float(min(L[k] for k in run))
            r_i = c0 + c1 * ts[i]
            c_rec = max(c1, -12.0)
            recovered = False
            for k in range(run[-1] + 1, k_stop):
                if ts[k] > ts[i] + 0.35:
                    break
                if self._onset_influence(ts[k]):
                    continue
                if L[k] >= r_i + c_rec * (ts[k] - ts[i]) - 6.0 and L[k] >= l_min + 8.0:
                    recovered = True
                    break
            if recovered:
                continue
            cross6 = ts[i - 1] + (y0 / (y0 - y1) if y0 != y1 else 0.0) * (ts[i] - ts[i - 1])
            cross12 = None
            for k in range(i, run[-1] + 1):
                if k > i and L[k] > L[k - 1] + 0.5:
                    break         # 电平回升：被其它音的起音污染，不再用于估计截止陡峭度
                z0 = L[k - 1] - ((c0 + c1 * ts[k - 1]) - 12.0)
                z1 = L[k] - ((c0 + c1 * ts[k]) - 12.0)
                if z1 < 0.0 <= z0:
                    cross12 = ts[k - 1] + (z0 / (z0 - z1) if z0 != z1 else 0.0) * (ts[k] - ts[k - 1])
                    break
            delta = None if cross12 is None else cross12 - cross6
            if unreliable and not cut_by_repress and (delta is None or delta > 0.06):
                continue          # 跌落不够急（-6→-12 dB 用时 >60 ms，即慢于 100 dB/s）：是快速自然衰减，不是松键
            t_rel = cross6 - _release_bias(delta)
            # 截止（硬切/松键止音的起点）会在细分辨率通量上留下能量下降型"咔哒"：若咔哒与本音电平的
            # 跌落区间吻合，以它为准（±3 ms 级精度，不受下一个音起音泄漏的干扰）。
            # 跌落区间：4096 Hann 窗下，电平仍在趋势线 1.5 dB 内的帧说明截止晚于其中心 +16 ms；
            # 已跌到 -18 dB 以下的帧说明截止早于其中心 -18 ms——区间外的咔哒（噪音）不用
            k_full = next((k for k in range(i - 1, max(-1, i - 8), -1)
                           if L[k] >= (c0 + c1 * ts[k]) - 1.5), None)
            k_empty = next((k for k in run if L[k] <= (c0 + c1 * ts[k]) - 18.0), None)
            c_lo = (ts[k_full] + 0.016 if k_full is not None else cross6 - 0.06) - 0.010
            c_hi = (ts[k_empty] - 0.018 if k_empty is not None else cross6 + 0.06) + 0.010
            for tc, _h in reversed(self._off_peaks):
                if tc < c_lo:
                    break
                if a["start"] + 0.03 <= tc <= c_hi:
                    t_rel = tc
                    break
            t_rel = max(a["start"], t_rel)
            if t_limit is not None:
                t_rel = min(t_rel, t_limit)
            return t_rel, "release"
        return fallback

    def _click_before(self, a, T):
        """同键重按前紧挨着的截止"咔哒"（能量下降型通量峰）：硬截止后 ≤60 ms 内又按下同一键时，
        4096 点帧看不到电平跌落，只能靠咔哒定位上一音的结束。更早的咔哒与本音无关（噪音），不用"""
        best = None
        for t, h in reversed(self._off_peaks):
            if t < max(a["start"] + 0.03, T - 0.06):
                break
            if t <= T - 0.008 and (best is None or t > best):
                best = t
        return best

    # ------------------------------------------------------------------
    def _add_onset(self, t, strength):
        """同一起音（和弦各音相距 <35 ms）合并为一个事件 [t, 强度, 音数, 最强音电平dB]"""
        for e in reversed(self.onsets[-12:]):
            if abs(e[0] - t) < 0.035:
                e[0] = min(e[0], t)
                e[1] = max(e[1], strength)
                e[2] += 1
                self._onsets_ver += 1
                return e
        e = [t, strength, 1, -999.0]
        i = len(self.onsets)
        while i > 0 and self.onsets[i - 1][0] > t:
            i -= 1
        self.onsets.insert(i, e)
        if len(self.onsets) > 2000:
            self.onsets = self.onsets[-1000:]
        self._onsets_ver += 1
        return e

    def _drop_onset(self, e):
        if e is None:
            return
        e[2] -= 1
        if e[2] <= 0:
            for i in range(len(self.onsets) - 1, -1, -1):
                if self.onsets[i] is e:
                    self.onsets.pop(i)
                    break
        self._onsets_ver += 1

    def _onset_dspec(self, T):
        """起音后 8~93 ms 的幅度谱减去起音前同长度窗的幅度谱（之前还在响的音）；音频还没到 / 已丢弃 → None"""
        key = round(T, 3)
        d = self._relabel_cache.get(key)
        if d is not None:
            return d
        n = self.fft_size
        a = int(round((T + 0.008) * self.sr)) - self._raw_pos
        b = a - n - int(0.016 * self.sr)
        if a + n > len(self._raw) or a < 0:
            return None
        s = np.abs(np.fft.rfft(self._raw[a:a + n] * self._win, n=self.fft_n))
        if b >= 0:
            s = np.maximum(s - np.abs(np.fft.rfft(self._raw[b:b + n] * self._win, n=self.fft_n)), 0.0)
        if len(self._relabel_cache) > 64:
            self._relabel_cache.clear()
        self._relabel_cache[key] = s
        return s

    def _harm_amps(self, d, m):
        f0 = _midi_freq(m)
        out = np.zeros(8)
        for h in range(1, 9):
            fb = h * f0 * self.fft_n / self.sr
            lo, hi = int(fb * 2 ** (-0.4 / 12)), int(np.ceil(fb * 2 ** (0.4 / 12))) + 1
            if hi >= len(d):
                break
            out[h - 1] = d[lo:hi].max()
        return out

    def _relabel(self, m, a):
        """按音色模板改判键位（KEY_TEMPLATES）：返回改判后的 MIDI；音频还不够 → None"""
        if self.key_tmpl is None:
            return m
        if "lab" in a:
            return a["lab"]
        d = self._onset_dspec(a["start"])
        if d is None:
            return None
        valid = self.instrument.valid_midis()
        cands = []
        for k in valid:
            r = 2.0 ** ((m - k) / 12.0)
            h = int(round(r))
            if 1 <= h <= 8 and abs(r / h - 1.0) < 0.02 and \
                    self.key_tmpl[timbre_register(k - self.instrument.transpose)][0][h - 1] > -20.0:
                cands.append(k)
        if not cands:
            # 换算不出可用的键：琴音域以上的峰（谐波）不报（-1），音域内的照旧
            a["lab"] = m if m in valid else -1
            return a["lab"]
        best = max(cands, key=lambda k: float(np.dot(
            self.key_tmpl[timbre_register(k - self.instrument.transpose)][1], self._harm_amps(d, k))))
        a["lab"] = best
        return best

    def _harm_of_same_onset(self, m, a, ev):
        """音域以上的峰 m 是否是同一起音（±35 ms）里另一个音（原始音高或改判后的键）的 2~8 次谐波"""
        others = set(self._group_keys.get(id(ev), set())) if ev is not None else set()
        for n, b in self.active.items():
            if b is not a and abs(b["start"] - a["start"]) < 0.035:
                others.add(n)
                if b.get("lab") is not None and b["lab"] >= 0:
                    others.add(b["lab"])
        for k in others:
            if k >= m:
                continue
            r = 2.0 ** ((m - k) / 12.0)
            h = int(round(r))
            if 2 <= h <= self.TMPL_SAME_ONSET_H and abs(r / h - 1.0) < 0.02:
                return True
        return False

    def _open_note(self, m, start, t_now, amp, strength, fallback=False):
        start = max(0.0, start)       # 流开头补的是虚拟静音，插值可能略早于 0
        self._last_start[m] = start
        entry = [start, m, 0.0, amp]
        self.active[m] = {"start": start, "last": t_now, "last_raw": t_now,
                          "last_raw_before_gap": t_now, "amp": amp, "amin": amp,
                          "maxamp": amp, "n": 0, "ref": None, "h": 0,
                          "ev": self._add_onset(start, strength), "chroma": entry}
        if fallback and self.active[m]["ev"][2] == 1:
            # 只由后备判定开出来的起音：边界值排查不拿它学"单独按下"的音色（快段落里它常和别的音叠在一起）
            self.fb_onset_ids.add(id(self.active[m]["ev"]))
            if len(self.fb_onset_ids) > 4000:
                live = {id(e) for e in self.onsets}
                self.fb_onset_ids &= live
        self.active_frames[m] = 0
        self.chroma_note_log.append(entry)
        if len(self.chroma_note_log) > 4000:
            self.chroma_note_log = self.chroma_note_log[-2000:]

    def _close_note(self, m, a, t_end, reason, events):
        """落音：过短的瞬态、起音瞬态旁瓣不产生事件、不计入起音/调性"""
        dur = t_end - a["start"]
        min_d = self.min_cut_note_s if reason in ("release", "retrig") else self.min_note_s
        ev = a.get("ev")
        # 起音瞬态旁瓣：与更强的音同一起音出现、比它弱 ≥6 dB、0.25 s 内就消失
        # （原神乐器无力度变化，同一和弦各音电平相近；真实琴音的敲击噪声会在邻近频点形成短暂"假音"）
        sideband = (reason != "retrig" and dur < 0.25 and ev is not None and ev[2] >= 2
                    and a.get("ref_db") is not None and a["ref_db"] < ev[3] - 6.0)
        if dur < min_d or sideband:
            self._drop_onset(ev)
            entry = a.get("chroma")
            for i in range(len(self.chroma_note_log) - 1, -1, -1):
                if self.chroma_note_log[i] is entry:
                    self.chroma_note_log.pop(i)
                    break
            return
        dur_ms = dur * 1000.0
        mo = m
        if self.key_tmpl is not None:
            mo = self._relabel(m, a)
            mo = (m if m in self.instrument.valid_midis() else -1) if mo is None else mo
            if mo >= 0 and m not in self.instrument.valid_midis() and self._harm_of_same_onset(m, a, ev):
                mo = -1               # 音域以上的峰是同一起音另一个音的整数倍谐波：不另报一个键
            if mo < 0:
                # 琴音域以上、换算不出可用键的峰：不报、不计入起音
                self._drop_onset(ev)
                entry = a.get("chroma")
                for i in range(len(self.chroma_note_log) - 1, -1, -1):
                    if self.chroma_note_log[i] is entry:
                        self.chroma_note_log.pop(i)
                        break
                return
            if ev is not None:
                g = self._group_keys.setdefault(id(ev), set())
                if len(self._group_keys) > 256:
                    live = {id(e) for e in self.onsets[-64:]}
                    self._group_keys = {k: v for k, v in self._group_keys.items() if k in live}
                    g = self._group_keys.setdefault(id(ev), g)
                if mo in g:
                    # 同一起音的另一个音已经改判成这个键（它的谐波）：不重复报
                    entry = a.get("chroma")
                    for i in range(len(self.chroma_note_log) - 1, -1, -1):
                        if self.chroma_note_log[i] is entry:
                            self.chroma_note_log.pop(i)
                            break
                    return
                g.add(mo)
        events.append(self._make_note_event(mo, a, dur_ms, reason))
        entry = a.get("chroma")
        if entry is not None:
            entry[1] = mo
            entry[2] = dur_ms

    def _release_all(self, events, t_now):
        """静音帧：所有候选记为缺席；活跃音缺席满 grace 帧后落音"""
        for m in list(self._streak.keys()):
            self._miss[m] = self._miss.get(m, 0) + 1
            if self._miss[m] >= 2:
                self._streak[m] = 0
                self._attack.pop(m, None)
                self._attack_t.pop(m, None)
        for m in list(self.active.keys()):
            a = self.active[m]
            if self.active_frames.get(m, 0) == 0:
                a["last_raw_before_gap"] = a["last_raw"]
            self.active_frames[m] = self.active_frames.get(m, 0) + 1
            if self.active_frames[m] >= self.grace:
                self.active.pop(m)
                self.active_frames.pop(m, None)
                end, reason = self._end_time(m, a)
                self._close_note(m, a, end, reason, events)

    # ------------------------------------------------------------------
    def _find_peaks(self, mag: np.ndarray, abs_thr: float):
        """局部极大值 + 抛物线插值 → [(bin_float, amp)]（向量化，结果与逐点扫描一致）"""
        n = len(mag)
        if n < 8:
            return []
        c = mag[3:n - 4]
        cand = np.nonzero((c > abs_thr) & (c >= mag[2:n - 5]) & (c >= mag[4:n - 3]))[0] + 3
        out = []
        nxt = 0
        for i in cand:
            if i < nxt:
                continue
            a, b, cc = float(mag[i - 1]), float(mag[i]), float(mag[i + 1])
            denom = a - 2 * b + cc
            d = 0.5 * (a - cc) / denom if abs(denom) > 1e-12 else 0.0
            out.append((i + d, b - 0.25 * (a - cc) * d))
            nxt = i + 4
        out.sort(key=lambda p: p[1], reverse=True)
        return out[:16]               # 最多 16 个峰（12 个时密集和弦里较弱的真音常被挤掉）

    def _lower_fundamentals(self, peaks, mag):
        """基频降级：对每个峰 (bin, amp)，若 f/k 本身也是一个局部峰（真实存在的音），
        则 f 是它的谐波，将峰移到 f/k。但 f/k 对应已活跃音时不降级（两个独立音）。"""
        rules = [(4, 0.18), (3, 0.22), (2, 0.35)]
        active_midis = set(self.active.keys())
        out = []
        for x, amp in peaks:
            best_x, best_amp = x, amp
            # 只对 <400Hz 的峰做基频降级：高音区基频总是最强，不需要降级
            peak_freq = x * self.sr / self.fft_n
            if peak_freq > 400.0:
                out.append((best_x, best_amp))
                continue
            for k, thr in rules:
                sub_bin = x / k
                sub_freq = sub_bin * self.sr / self.fft_n
                sub_midi = int(round(69.0 + 12.0 * np.log2(sub_freq / 440.0)))
                if sub_midi in active_midis:
                    continue
                sub_is_peak = any(abs(px - sub_bin) < 3.0 for px, _ in peaks)
                if not sub_is_peak:
                    continue
                bi = int(round(sub_bin))
                lo, hi = max(0, bi - 2), min(len(mag), bi + 3)
                sub_amp = float(mag[lo:hi].max()) if hi > lo else 0.0
                if sub_amp > thr * amp:
                    best_x = sub_bin
                    best_amp = max(amp, sub_amp)
                    break
            out.append((best_x, best_amp))
        return out

    def _peaks_to_notes(self, peaks, mag):
        midis = []
        for x, amp in peaks:
            freq = x * self.sr / self.fft_n
            if freq < 60.0 or freq > 5000.0:
                continue
            midi_f = 69.0 + 12.0 * np.log2(freq / 440.0)
            midis.append(int(round(midi_f)))
        return midis

    def _has_harmonic_support(self, midi, mag):
        """真实乐器音必须带谐波分量。高音(>450Hz)的2次谐波在>900Hz常被衰减，跳过校验。"""
        freq = _midi_freq(midi)
        if freq > 450.0:
            return True
        base = int(freq * self.fft_n / self.sr)
        if not (0 <= base < len(mag)):
            return False
        base_amp = float(mag[max(0, base - 2):min(len(mag), base + 3)].max())
        if base_amp <= 0:
            return False
        for k in (2, 3, 4):
            target = base * k
            if target >= len(mag):
                break
            lo, hi = max(0, target - 3), min(len(mag), target + 4)
            if float(mag[lo:hi].max()) > 0.03 * base_amp:
                return True
        return False

    def _drop_timbre_harmonics(self, midis, amp_dict, mag, present):
        """按乐器实测音色去掉谐波：候选 m 若是某个正在发声的更低键 k 的第 h 次谐波（h = 2~8，频率比偏差 < 1.5%），
        且 m 处的幅度不超过 k 的基频幅度 × 该音区第 h 次谐波的 P90 电平（+2 dB）→ 是 k 的谐波，不是另一个键"""
        if not midis:
            return list(midis)
        valid = self.instrument.valid_midis()
        out = []
        for m in midis:
            fm = _midi_freq(m)
            amp_m = max(amp_dict.get(m, 0.0), self._peak_amp(m, mag))
            harmonic = False
            for k in present:
                if k >= m or k not in valid:
                    continue
                r = fm / _midi_freq(k)
                h = int(round(r))
                if h < 2 or h > 8 or abs(r / h - 1.0) > 0.015:
                    continue
                lv = self.timbre[timbre_register(k)].get(h)
                if lv is None:
                    continue
                amp_k = self._peak_amp(k, mag)
                if amp_k > 0 and amp_m <= amp_k * 10 ** ((lv + self.harm_margin) / 20.0):
                    harmonic = True
                    break
            if not harmonic:
                out.append(m)
        return out

    def _dedup_harmonics(self, midis, amp_dict=None):
        """整数倍频去重：低频优先保留，高频谐波剔除。
        若高频音幅度 < 阈值 × 低频音幅度，视为谐波去掉；否则保留为独立音。阈值默认 50%；
        有实测音色的乐器（TIMBRES）按低频音所在音区的该次谐波电平（+2 dB 余量）定，且不低于 50%"""
        if len(midis) < 2:
            return list(midis)
        amp_dict = amp_dict or {}
        kept = []
        for m in sorted(set(midis)):
            freq = _midi_freq(m)
            is_harmonic = False
            for km in kept:
                ratio = freq / _midi_freq(km)
                if 1.7 <= ratio <= 8.5:
                    r = round(ratio)
                    if abs(ratio - r) < 0.08:
                        amp_m = amp_dict.get(m, 0)
                        amp_k = amp_dict.get(km, 0)
                        thr = 0.50
                        if self.timbre is not None:
                            lv = self.timbre[timbre_register(km)].get(int(r))
                            if lv is not None:
                                thr = max(thr, 10 ** ((lv + self.harm_margin) / 20.0))
                        if amp_k > 0 and amp_m < thr * amp_k:
                            is_harmonic = True
                        elif amp_k == 0:
                            is_harmonic = True
                        break
            if not is_harmonic:
                kept.append(m)
        return kept

    def _bin_of(self, midi):
        i = int(_midi_freq(midi) * self.fft_n / self.sr)
        if 0 <= i < self.fft_n // 2:
            return i
        return 0

    def _peak_amp(self, midi, mag):
        """该音基频附近 ±2 个频点内的最大幅度"""
        i = int(round(_midi_freq(midi) * self.fft_n / self.sr))
        lo, hi = max(0, i - 2), min(len(mag), i + 3)
        return float(mag[lo:hi].max()) if hi > lo else 0.0

    def _amp_of(self, midi, mag):
        i = int(_midi_freq(midi) * self.fft_n / self.sr)
        if 0 <= i < len(mag):
            return float(mag[i])
        return 0.0

    # ------------------------------------------------------------------
    def _make_note_event(self, midi, a, dur_ms, reason="decay"):
        label, approx = self.instrument.label_of(midi)
        name = midi_to_name(midi)
        if approx:
            target = self.instrument.pitch_keys()
            if target:
                nearest = min(target, key=lambda k: abs(k[1] - (midi - self.instrument.transpose)))
                name = f"≈{midi_to_name(nearest[1] + self.instrument.transpose)}"
        ioi = None
        # 优先用 BPM 起音序列（起音峰 + 音高证据，更完整：音符跟踪漏拆的同键连按也在其中）
        bo = self.beat_onsets
        for i in range(len(bo) - 1, 0, -1):
            if bo[i][0] < a["start"] - 0.035:
                break
            if abs(bo[i][0] - a["start"]) < 0.035:
                ioi = round((bo[i][0] - bo[i - 1][0]) * 1000.0, 1)
                break
        ev = a.get("ev")
        if ioi is None and ev is not None:
            prev = None
            for e in self.onsets:
                if e is ev:
                    break
                if e[2] > 0:
                    prev = e
            if prev is not None:
                ioi = round((ev[0] - prev[0]) * 1000.0, 1)
        return {
            "t": a["start"],
            "key": label,
            "midi": midi,
            "name": name,
            "solfege": midi_to_solfege(midi),
            "dur_ms": round(dur_ms, 1),
            "approx": approx,
            "end": reason,            # release / retrig / decay
            "ioi_ms": ioi,            # 与上一个起音（和弦算一次）的间隔
        }

    # ------------------------------------------------------------------
    # BPM：节拍级速度跟踪
    # ------------------------------------------------------------------
    # 显示的是"拍子"的速度（乐曲的 BPM），而不是最密音符的速度：弹八分、十六分、三连音时读数不跟着翻倍。
    #   1) 起拍：最近 ≥5 个起音（跨度 ≥1.2 s）对候选拍周期 0.27~1.5 s 打分——落在拍点上的起音记 1 分，
    #      落在半拍 / 三分 / 四分 / 六分拍上的记 0.5 / 0.4 / 0.35 / 0.25 分（和弦按音数加重），
    #      乘以速度先验（以 120 BPM 为中心、σ = 1 个倍频程），取最高分的拍周期与相位；
    #   2) 跟拍：之后每个起音按预测的拍点归类——在拍上（±16% 拍长）就锁相并修正周期，
    #      在细分上就忽略（音符变密/变稀不改变速度），两者都不是才算"对不上"；
    #      显示值由本速度段内拍点的加权回归给出（稳定速度下精确，变速时由锁相环先跟上）；
    #   3) 变速：拍上起音的偏差持续变大、或起音频频对不上时，用最近 7 个起音重新估计；新拍周期与当前相差 > 8%、
    #      明显更好（得分高 20%）且隔 0.8 s 再查仍一致才换（小于 8% 的快慢由锁相环逐渐跟上，不会跳）；
    #      演奏中连续 3 个预测拍点都没有起音（或连续 6 个起音对不上）则直接用最近 2.5 s 的起音重新起拍；
    #   4) 每 2 s 复核一次拍子层级（半速 / 倍速 / 3:2），别的层级明显更好（≥1.12 倍）且连续两次才换；
    #   5) 停顿 > 2.5 s（且 > 4 拍）后保持速度、下一个起音重新对齐拍点；12 s 内没有起音时清空显示。
    BEAT_MIN, BEAT_MAX = 0.27, 1.5           # 拍周期范围（约 40~222 BPM）
    BEAT_CENTER, BEAT_SPREAD = 0.5, 1.0      # 速度先验：中心 120 BPM，σ = 1 个倍频程
    BEAT_SUBS = ((2, 0.5), (3, 0.35), (4, 0.35), (6, 0.2))   # 拍内细分及其得分（二分细分优先）
    BEAT_TOL = 0.07                          # 打分时的拍点容差（拍长的比例；细分点按细分间距再收紧）
    BEAT_HIT = 0.16                          # 跟拍：离预测拍点这么近（拍长的比例）算在拍上
    BEAT_SUB_HIT = 0.12                      # 跟拍：离细分点这么近（细分间距的比例）算在细分上
    BEAT_INIT_N = 5
    BEAT_LOST = 3                            # 演奏中连续这么多个预测拍点都没有起音 → 速度变了
    BEAT_MISS = 6                            # 或连续这么多个起音既不在拍上也不在细分上
    BEAT_GAP = 2.5
    BEAT_CHECK = 1.0                         # 层级复核间隔（秒；1.0.8 由 2 s 改为 1 s，快速轮指起拍锁错时更快纠正）
    BEAT_DRIFT = 0.07                        # 最近 4 个拍上起音的平均偏差（拍长的比例）超过它 → 可能变速了
    BEAT_SWITCH = 0.08                       # 最近起音的最佳拍周期与当前相差超过 8%、且得分高 15% → 换
    BEAT_LEVEL_GAIN = 1.12                   # 层级复核：别的层级得分高这么多倍（且连续两次）才换
    BEAT_WIDE_GAIN = 1.05                    # 层级复核也考虑任意拍周期：得分高这么多倍才作为候选（0 = 不考虑；1.0.8）

    def _bpm_reset(self):
        self._bpm_P = None            # 当前拍周期（秒）
        self._beat_b = None           # 最近一个拍点的时刻
        self._beat_k = 0              # 最近拍点的拍号（本速度段内）
        self._beat_pts = []           # [(拍号, 时刻)]：落在拍点上的起音（回归求周期）
        self._beat_buf = []           # [(时刻, 重音)]：最近的起音（起拍 / 复核用）
        self._beat_miss = 0
        self._beat_empty = 0          # 演奏中连续没有起音的预测拍点数
        self._beat_counted = 0        # 最近拍点之后已计入的预测拍点数
        self._beat_hist = deque(maxlen=12)   # 最近的起音能否被拍点或细分解释
        self._beat_err = deque(maxlen=4)     # 最近拍上起音的偏差（拍长的比例）
        self._beat_cand = None               # 变速候选（拍周期, 首次提出的时刻）
        self._beat_quick_t = -1e9            # 上次定期复查的时刻
        self._beat_last = -1e9
        self._beat_check_t = 0.0
        self._beat_alt = None
        self._bpm_val = None
        self.bpm_confidence = 0.0

    def _beat_score(self, ts, acc, periods):
        """每个候选拍周期的得分（对 24 个相位取最大）与对应的拍点相位（某个拍点的时刻）"""
        ts = np.asarray(ts, dtype=float)
        acc = np.asarray(acc, dtype=float)
        t0 = ts[0]
        out = np.zeros(len(periods))
        phase = np.zeros(len(periods))
        for j, T in enumerate(periods):
            ph = np.linspace(0.0, T, 24, endpoint=False)
            u = (ts[None, :] - t0 - ph[:, None]) / T
            sc = np.exp(-0.5 * ((u - np.round(u)) / self.BEAT_TOL) ** 2)
            for L, wl in self.BEAT_SUBS:
                uL = u * L
                sig = min(self.BEAT_TOL, 0.25 / L)
                sc = np.maximum(sc, wl * np.exp(-0.5 * (((uL - np.round(uL)) / L) / sig) ** 2))
            tot = (sc * acc[None, :]).sum(axis=1) / acc.sum()
            # 拍点覆盖率：跨度内有多少拍点上真有起音。只按得分，取半拍周期也能让同样的起音"都在拍上"
            # （每隔一拍一个音）；覆盖率低的层级轻度降分（音乐里本来就有休止和长音，所以只降到 75%）
            near = np.abs(u - np.round(u)) <= self.BEAT_HIT
            ks = np.round(u)
            span = ks.max(axis=1) - ks.min(axis=1) + 1.0
            cov = np.array([len(np.unique(ks[r][near[r]])) for r in range(len(ph))]) / np.maximum(span, 1.0)
            tot = tot * (0.75 + 0.25 * np.minimum(1.0, cov))
            k = int(np.argmax(tot))
            out[j] = tot[k]
            phase[j] = t0 + ph[k]
        prior = np.exp(-0.5 * (np.log2(np.asarray(periods) / self.BEAT_CENTER) / self.BEAT_SPREAD) ** 2)
        return out * prior, phase

    def _beat_estimate(self, ts, acc, lo=None, hi=None):
        """→ (拍周期, 拍点相位, 得分, 次优得分)。次优 = 与最佳相差 8% 以上的周期里的最高分（用来判断是否还分不清）"""
        lo = self.BEAT_MIN if lo is None else lo
        hi = self.BEAT_MAX if hi is None else hi
        periods = np.exp(np.linspace(np.log(lo), np.log(hi), 110))
        sc, ph = self._beat_score(ts, acc, periods)
        j = int(np.argmax(sc))
        far = np.abs(np.log(periods / periods[j])) > np.log(1.08)
        second = float(sc[far].max()) if far.any() else 0.0
        fine = periods[j] * np.linspace(0.985, 1.015, 31)
        sc2, ph2 = self._beat_score(ts, acc, fine)
        k = int(np.argmax(sc2))
        return float(fine[k]), float(ph2[k]), float(sc2[k]), second

    def _accent(self, t):
        """起音的重音：同时按下的音越多越重（检测器的起音事件里记着音数）"""
        for e in reversed(self.onsets[-24:]):
            if abs(e[0] - t) < 0.04:
                return 1.0 + 0.4 * min(3, max(0, e[2] - 1))
        return 1.0

    def _beat_explained(self, t, b, T):
        """起音相对拍点 b、周期 T 的位置：('beat', 隔了几拍, 偏差) / ('sub', 0, 0) / ('miss', 0, 0)"""
        u = (t - b) / T
        n = int(round(u))
        r = u - n
        if n >= 1 and abs(r) <= self.BEAT_HIT:
            return "beat", n, r
        for L, _ in self.BEAT_SUBS:
            uL = u * L
            if abs(uL - round(uL)) <= self.BEAT_SUB_HIT and int(round(uL)) % L != 0:
                return "sub", 0, 0.0
        if n == 0 and abs(r) <= self.BEAT_HIT:
            return "sub", 0, 0.0          # 紧挨着上一个拍点（分解和弦、装饰音）
        return "miss", 0, 0.0

    def _beat_period(self, fallback):
        """本速度段内拍点的加权回归周期（拍点少于 4 个、或与锁相环估计相差 > 8% 时用锁相环的）"""
        pts = self._beat_pts
        if len(pts) < 4:
            return fallback
        k = np.array([p[0] for p in pts], dtype=float)
        t = np.array([p[1] for p in pts])
        tau = min(6.0, max(1.5, 0.35 * (t[-1] - t[0])))
        w = np.exp(-(t[-1] - t) / tau)
        km = (w * k).sum() / w.sum()
        tm = (w * t).sum() / w.sum()
        den = (w * (k - km) ** 2).sum()
        if den <= 1e-9:
            return fallback
        T = float((w * (k - km) * (t - tm)).sum() / den)
        return T if abs(T / fallback - 1.0) <= 0.08 else fallback

    def _beat_set(self, T):
        self._bpm_P = T
        self._bpm_val = round(60.0 / T, 1)
        self.bpm_confidence = float(np.mean(self._beat_hist)) if self._beat_hist else 0.0

    def _beat_init(self, seg, lo=None, hi=None, need_margin=False):
        """用一段起音（重新）起拍；起音太少或太乱时不改变当前显示。
        need_margin：还分不清拍子（别的拍周期得分与最佳相差 < 8%）时先不定，等更多起音"""
        if len(seg) < 5:
            return False
        ts = np.array([s[0] for s in seg])
        acc = np.array([s[1] for s in seg])
        T, ph, sc, second = self._beat_estimate(ts, acc, lo, hi)
        if sc < 0.35:
            return False
        if need_margin and second >= sc / 1.08:
            return False
        u = (ts - ph) / T
        n = np.round(u)
        on = np.abs(u - n) <= self.BEAT_HIT
        if int(on.sum()) < 2:
            return False
        k0 = n[on]
        self._beat_pts = [(int(k - k0[0]), float(t)) for k, t in zip(k0, ts[on])]
        self._beat_k = self._beat_pts[-1][0]
        self._beat_b = self._beat_pts[-1][1]
        self._beat_miss = 0
        self._beat_empty = 0
        self._beat_counted = 0
        self._beat_alt = None
        self._beat_err.clear()
        self._beat_hist.clear()
        for t in ts:
            kind = self._beat_explained(t, ph, T) if t > ph else ("beat", 0, 0.0)
            self._beat_hist.append(0.0 if kind[0] == "miss" else 1.0)
        self._beat_set(self._beat_period(T))
        return True

    def _beat_add(self, t, a):
        buf = self._beat_buf
        T = self._bpm_P
        if buf and t - buf[-1][0] > max(self.BEAT_GAP, 4.0 * (T or 0.0)):
            buf.clear()
            if T is not None:
                # 停顿后：速度保持，这个起音当作新的拍点
                self._beat_b, self._beat_k, self._beat_pts, self._beat_miss = t, 0, [(0, t)], 0
                self._beat_empty = self._beat_counted = 0
                buf.append((t, a))
                return
        buf.append((t, a))
        if len(buf) > 40:
            del buf[0]
        if T is None:
            # 第一次给出读数：起音够多（≥8 个、跨度 ≥2 s）或拍子层级已明显分得清；最多等到 16 个起音
            n, span = len(buf), buf[-1][0] - buf[0][0]
            if n >= self.BEAT_INIT_N and span >= 1.2:
                sure = n >= 16 or (n >= 8 and span >= 2.0)
                self._beat_init(buf[-16:], need_margin=not sure)
            return
        kind, n, r = self._beat_explained(t, self._beat_b, T)
        # 上一个拍点之后，已经过去、却没有起音落在上面的预测拍点（只在演奏没停时计：起音间隔 ≤ 2 拍）
        prev_t = buf[-2][0] if len(buf) >= 2 else t
        upto = (n - 1) if kind == "beat" else int(np.floor((t - self._beat_b) / T - self.BEAT_HIT))
        newly = max(0, upto - self._beat_counted)
        self._beat_counted = max(self._beat_counted, upto)
        if t - prev_t <= 2.0 * T:
            self._beat_empty += newly
        else:
            self._beat_empty = 0
        if kind == "beat":
            err = t - (self._beat_b + n * T)
            self._beat_k += n
            self._beat_b = self._beat_b + n * T + 0.7 * err
            self._beat_pts.append((self._beat_k, t))
            if len(self._beat_pts) > 64:
                del self._beat_pts[0]
            self._beat_miss = 0
            self._beat_empty = 0
            self._beat_counted = 0
            self._beat_hist.append(1.0)
            self._beat_err.append(abs(r))
            self._beat_set(self._beat_period(T * (1.0 + 0.2 * err / (n * T))))
            if (len(self._beat_err) >= 4 and float(np.mean(self._beat_err)) > self.BEAT_DRIFT) or \
                    (self._beat_cand is not None and t - self._beat_cand[1] >= 0.8) or t - self._beat_quick_t >= 0.6:
                self._beat_quick_t = t
                self._beat_reconsider(t)
            return
        if kind == "sub":
            self._beat_miss = 0
            self._beat_hist.append(1.0)
        else:
            self._beat_miss += 1
            self._beat_hist.append(0.0)
        self.bpm_confidence = float(np.mean(self._beat_hist))
        if self._beat_empty >= self.BEAT_LOST or self._beat_miss >= self.BEAT_MISS:
            # 拍点上连续没有起音（或起音一直对不上）：速度变了，用最近 2.5 s 的起音重新起拍
            seg = [x for x in buf if x[0] >= t - max(2.5, 5.0 * T)]
            if self._beat_init(seg[-12:]):
                self._beat_miss = 0
                self._beat_empty = 0
        elif len(self._beat_hist) >= 6 and sum(1 for v in list(self._beat_hist)[-6:] if v == 0.0) >= 3:
            self._beat_reconsider(t)
        elif self._beat_cand is not None and t - self._beat_cand[1] >= 0.8:
            self._beat_reconsider(t)              # 已有变速候选：到时间就复查确认
        elif t - self._beat_quick_t >= 0.6:
            self._beat_quick_t = t                # 定期用最近几个起音复查一次（细分音能"解释"变速后的起音，
            self._beat_reconsider(t)              # 光看对不上的起音发现不了变速）

    def _beat_reconsider(self, t):
        """可能变速了：用最近 7 个起音（跨度 ≥1.2 s）重新估计拍周期。与当前相差 > 8%、得分高 20%、
        没有别的候选与它不相上下，并且隔 ≥0.8 s 的下一次复查仍指向同一速度（±5%）才换——
        一小段复杂节奏不至于让读数跳一下"""
        T = self._bpm_P
        seg = self._beat_buf[-7:]
        if len(seg) < 6 or seg[-1][0] - seg[0][0] < 1.2:
            return
        ts = np.array([s[0] for s in seg])
        acc = np.array([s[1] for s in seg])
        Tn, ph, sc, second = self._beat_estimate(ts, acc)
        if abs(Tn / T - 1.0) <= self.BEAT_SWITCH:
            self._beat_err.clear()
            self._beat_cand = None
            return
        cur, _ = self._beat_score(ts, acc, T * np.linspace(0.97, 1.03, 13))
        if not (sc >= 1.2 * float(cur.max()) and second < sc / 1.05):
            self._beat_cand = None
            return
        c = self._beat_cand
        if c is not None and abs(Tn / c[0] - 1.0) <= 0.05 and t - c[1] >= 0.8:
            self._beat_cand = None
            self._beat_init(seg, Tn * 0.97, Tn * 1.03)
        elif c is None or abs(Tn / c[0] - 1.0) > 0.05:
            self._beat_cand = (Tn, t)

    def _beat_recheck(self, now):
        """复核拍子层级：最近 8 s 的起音里，半速 / 倍速 / 3:2 的层级明显更好（≥1.3 倍）且连续两次才换"""
        seg = [s for s in self._beat_buf if s[0] >= now - 8.0]
        if len(seg) < 8:
            return
        ts = np.array([s[0] for s in seg])
        acc = np.array([s[1] for s in seg])
        T = self._bpm_P
        best = {}
        for f in (0.5, 2.0 / 3.0, 1.0, 1.5, 2.0):
            c = T * f
            if not (self.BEAT_MIN * 0.96 <= c <= self.BEAT_MAX * 1.04):
                continue
            fine = c * np.linspace(0.96, 1.04, 17)
            sc, _ = self._beat_score(ts, acc, fine)
            j = int(np.argmax(sc))
            best[f] = (float(sc[j]), float(fine[j]))
        cur = best.get(1.0, (0.0, T))[0]
        alt = max((f for f in best if f != 1.0), key=lambda f: best[f][0], default=None)
        if self.BEAT_WIDE_GAIN:
            # 不限于整数比的层级：最近 8 s 的起音重新估计的最佳拍周期与当前相差 > 8%、得分高 BEAT_WIDE_GAIN 倍、
            # 且没有别的周期与它不相上下 → 也作为候选（同样要连续两次一致才换）。
            # 起拍时起音少，可能锁在一个"差不多能解释"的速度上，之后只靠整数比的层级复核改不过来
            Tw, _, scw, secw = self._beat_estimate(ts, acc)
            # 只在速度稳定时用：最近 4 s 单独估计也指向同一周期（±4%）。渐变速时 8 s 窗的估计落后于当前速度，
            # 会把已经跟上的锁相环拉回去
            half = ts >= now - 4.0
            steady = False
            if half.sum() >= 6:
                Th, _, _, _ = self._beat_estimate(ts[half], acc[half])
                steady = abs(Th / Tw - 1.0) <= 0.04
            if steady and abs(Tw / T - 1.0) > self.BEAT_SWITCH and scw > self.BEAT_WIDE_GAIN * cur \
                    and secw < scw / 1.03 and (alt is None or scw > best[alt][0]):
                best[-1.0] = (scw * self.BEAT_LEVEL_GAIN / self.BEAT_WIDE_GAIN, Tw)
                alt = -1.0
        if alt is not None and best[alt][0] > self.BEAT_LEVEL_GAIN * cur:
            Tn = best[alt][1]
            if self._beat_alt is not None and abs(self._beat_alt / Tn - 1.0) <= 0.05:
                self._beat_init(seg, Tn * 0.97, Tn * 1.03)
            else:
                self._beat_alt = Tn
        else:
            self._beat_alt = None

    def _current_bpm(self):
        """当前拍速（BPM，节拍级；见上方说明）。没有足够的起音时为 None"""
        now = self._now()
        bo = self.beat_onsets
        if not bo or now - bo[-1][0] > self.bpm_window:
            if self._bpm_val is not None or self._bpm_P is not None or self._beat_buf:
                self._bpm_reset()
            return None
        new = []
        for e in reversed(bo):
            if e[0] <= self._beat_last + 0.03:
                break
            new.append(e[0])
        for t in sorted(new):
            self._beat_last = t
            self._beat_add(t, self._accent(t))
        if self._bpm_P is not None and now - self._beat_check_t >= self.BEAT_CHECK:
            self._beat_check_t = now
            self._beat_recheck(now)
        return self._bpm_val

    # ------------------------------------------------------------------
    # 调性
    # ------------------------------------------------------------------
    KEY_WINDOW = 20.0        # 用最近 20 s 内的音
    KEY_MIN_NOTES = 6        # 至少 6 个音才给结论
    KEY_SWITCH_S = 2.5       # 新的调持续领先 2.5 s 才切换显示
    KEY_TEMP = 0.03          # 相关系数差 → 置信度的温度（差 0.03 ≈ 73%，差 0.1 ≈ 96%）

    def _key_candidates(self):
        """候选调：乐器只有一套七声音阶（原神这几种琴都只有白键）时，曲子用的永远是这 7 个音，
        真正要判断的只是主音——只在该音阶的大调与关系小调之间选（白键 = C 大调 / A 小调），
        不会报出琴上弹不出来的调（如需要 F# 的 G 大调）。其它情况 24 个调都可能。"""
        S = {m % 12 for m in self.instrument.valid_midis()}
        for r in range(12):
            if {(r + i) % 12 for i in MAJOR_SCALE} == S:
                return [(r, "maj"), ((r + 9) % 12, "min")]
        return [(r, md) for r in range(12) for md in ("maj", "min")]

    @staticmethod
    def _key_name(key):
        return f"{NOTE_NAMES[key[0]]} 大调" if key[1] == "maj" else f"{NOTE_NAMES[key[0]]} 小调"

    def _key_chroma(self, now):
        """最近 KEY_WINDOW 秒的音级分布。每个音按"占时"（到下一个起音的时间，封顶 1 s）而不是余音长度加权
        （拨弦低音余音长，按余音加权会被放大）；低音、句尾（其后有停顿）的音多加权——主音常出现在这两处"""
        grp = self._onset_groups(e for e in self.chroma_note_log if 0.0 <= now - e[0] <= self.KEY_WINDOW)
        rel = {id(e): w for g in grp for e, w in g}
        log = [e for g in grp for e, _ in g]
        if len(log) < self.KEY_MIN_NOTES:
            return None
        starts = [e[0] for e in log]
        pitches = sorted(e[1] for e in log)
        med_p = pitches[len(pitches) // 2]
        occ = []
        for i, e in enumerate(log):
            j = bisect.bisect_right(starts, e[0] + 0.06, lo=i)
            nxt = starts[j] if j < len(starts) else now
            occ.append(min(1.0, max(0.12, nxt - e[0])))
        med_occ = sorted(occ)[len(occ) // 2]
        chroma = np.zeros(12)
        for i, e in enumerate(log):
            w = occ[i] * np.exp(-(now - e[0]) / 8.0) * rel[id(e)]
            # 同时按下的一组里最低、且明显低于整体音区的音 = 低音
            grp_lo = min(x[1] for x in log if abs(x[0] - e[0]) < 0.06)
            if e[1] == grp_lo and e[1] <= med_p - 5:
                w *= 1.5
            j = bisect.bisect_right(starts, e[0] + 0.06, lo=i)
            gap = (starts[j] if j < len(starts) else now) - e[0]
            if gap >= max(0.6, 2.5 * med_occ):
                w *= 1.6
            chroma[e[1] % 12] += w
        return chroma / (chroma.sum() + 1e-9)

    def _current_tonality_text(self):
        """Krumhansl-Schmuckler 调性轮廓匹配，候选限定在乐器能弹的调；
        置信度 = 第一名相对第二名的把握（看领先多少，而不是相关系数本身的高低）；新调持续领先才切换"""
        now = self._now()
        chroma = self._key_chroma(now)
        if chroma is None:
            if self._key_disp is None:
                return "分析中…（音符不足）"
            return self._key_name(self._key_disp)
        cands = self._key_candidates()
        sc = []
        for key in cands:
            prof = KS_MAJOR if key[1] == "maj" else KS_MINOR
            sc.append((float(np.corrcoef(np.roll(prof, key[0]), chroma)[0, 1]), key))
        sc.sort(key=lambda x: -x[0])
        (c1, best), (c2, _) = sc[0], sc[1]
        p_best = 1.0 / (1.0 + np.exp(-(c1 - c2) / self.KEY_TEMP))
        if self._key_disp is None:
            self._key_disp = best
        elif best != self._key_disp:
            c = self._key_cand
            if p_best >= 0.65:
                if c is None or c[0] != best:
                    self._key_cand = (best, now)
                elif now - c[1] >= self.KEY_SWITCH_S:
                    self._key_disp = best
                    self._key_cand = None
            else:
                self._key_cand = None
        else:
            self._key_cand = None
        disp = self._key_disp
        c_disp = next(c for c, k in sc if k == disp)
        c_other = max(c for c, k in sc if k != disp)
        p_now = 1.0 / (1.0 + np.exp(-(c_disp - c_other) / self.KEY_TEMP))
        # 显示的置信度做平滑（约 0.5 s），避免数字每帧跳动；换调时重新开始
        if self._key_p is None or self._key_p[0] != disp:
            self._key_p = (disp, p_now)
        else:
            self._key_p = (disp, 0.9 * self._key_p[1] + 0.1 * p_now)
        p = self._key_p[1]
        name = self._key_name(disp)
        if p < 0.6:
            other = next(k for c, k in sc if k != disp)
            return f"{name}（与 {self._key_name(other)} 难分）"
        return f"{name}（置信 {int(5 * round(20 * p))}%）"

    # ------------------------------------------------------------------
    # 和弦
    # ------------------------------------------------------------------
    @staticmethod
    def _onset_groups(entries):
        """按起音时刻分组（相差 < 60 ms 算同时按下）→ [[(记录, 权重), ...], ...]。
        真实琴音的敲击会在相邻频点产生"假音"（比真音弱 10~25 dB）；但和弦里的低音有时也只有 -14 dB 左右，
        单靠电平分不开。规则：组内电平 ≥ 最强音 -8 dB 的是"强音"（权重 1）；-8~-16 dB 的弱音只有在
        同一组已有 ≥2 个强音（确实是同时按下的和弦）时才保留、按相对电平加权；更弱的一律视为假音"""
        groups = []
        for e in sorted(entries, key=lambda e: e[0]):
            if groups and e[0] - groups[-1][-1][0] < 0.06:
                groups[-1].append(e)
            else:
                groups.append([e])
        out = []
        for g in groups:
            amax = max(e[3] for e in g) or 1.0
            strong = [(e, 1.0) for e in g if e[3] >= 0.4 * amax]
            weak = [(e, e[3] / amax) for e in g if 0.15 * amax <= e[3] < 0.4 * amax]
            out.append(strong + (weak if len(strong) >= 2 else []))
        return out

    def _harmony_window(self, now):
        """当前和声窗口 → ([(midi, 权重)], 低音 midi, 类型) 或 None；类型：
          "block"  最近 2 s 内有一组同时按下（起音相差 < 60 ms）、≥3 个不同音级的音，且之后没有新的低音
                   → 就用这一组：之前弹过还在响的音（拨弦余音 1~3 s）、之后在和弦上弹的旋律音都不改变和弦；
          "bass"   分解和弦：从最近一个低音（比最近 2 s 内整体音区低 5 个半音以上、且是之后最低的音）累积到现在；
          "arp"    没有低音：用最近约 2.5 个起音周期（0.8~1.8 s）的音，要求全是同一个三和弦/七和弦的音。
        后两种情况下，若低音之上的音多数是级进（相邻两音只差 1~2 个半音）→ 这是旋律，不报和弦。
        窗口里没有新音时，若最后一组同时按下的音仍在发声（圆号按住、琴的和弦余音）→ 仍是那个和弦"""
        rec = sorted((e for e in self.chroma_note_log[-96:] if 0.0 <= now - e[0] <= 2.0), key=lambda e: e[0])
        if not rec:
            act = sorted(((a["start"], m, 0.0, a.get("amp", 1.0)) for m, a in self.active.items()), key=lambda e: e[0])
            if not act:
                return None
            last_t = act[-1][0]
            grp = [e for e in act if last_t - e[0] < 0.06]
            if len({e[1] % 12 for e in grp}) < 3:
                return None
            rec = grp
        groups = [g for g in self._onset_groups(rec) if g]
        if not groups:
            return None
        rec = [e for g in groups for e, _ in g]
        pitches = sorted(e[1] for e in rec)
        med_all = pitches[len(pitches) // 2]
        # 最近的低音起点
        bass_gi = None
        for gi in range(len(groups) - 1, -1, -1):
            lo = min(e[1] for e, _ in groups[gi])
            after = [e[1] for g in groups[gi + 1:] for e, _ in g]
            if lo <= med_all - 5 and all(m > lo for m in after):
                bass_gi = gi
                break
        # 最近的块和弦（同时按下 ≥3 个音级），且之后没有新的低音
        for gi in range(len(groups) - 1, -1, -1):
            if len({e[1] % 12 for e, _ in groups[gi]}) >= 3:
                if bass_gi is None or bass_gi <= gi:
                    g = groups[gi]
                    # 低音：强音里最低的；弱音只有在它的音级没被强音占着时才可能是低音
                    # （和强音同音级的弱音多半是低八度的假音，不应把和弦变成转位）
                    strong_pcs = {e[1] % 12 for e, w in g if w >= 1.0}
                    bass = min(e[1] for e, w in g if w >= 1.0 or e[1] % 12 not in strong_pcs)
                    return [(e[1], w) for e, w in g], bass, "block"
                break
        if bass_gi is not None:
            notes = [(e, w) for g in groups[bass_gi:] for e, w in g]
            kind = "bass"
        else:
            P = self._bpm_P or 0.5                    # 拍周期：分解和弦窗口约 1.25 拍
            win = min(1.8, max(0.8, 1.25 * P))
            notes = [(e, w) for g in groups for e, w in g if now - e[0] <= win]
            if not notes:
                return None
            kind = "arp"
        lo = min(e[1] for e, _ in notes)
        upper = [e[1] for e, _ in notes if e[1] != lo]
        steps = [abs(b - a) for a, b in zip(upper, upper[1:]) if b != a]
        if len(steps) >= 2 and sum(1 for d in steps if d <= 2) > 0.4 * len(steps):
            return None                         # 低音之上是级进的旋律，不是分解和弦
        ws = [(e[1], w * (1.2 if e[1] == lo else 1.0)) for e, w in notes]
        return ws, lo, kind

    @staticmethod
    def _name_chord(ws, bass, kind):
        """加权模板匹配：覆盖率（窗口里的音有多少能被这个和弦解释）+ 简洁度先验 + 低音是根音加分。
        返回和弦名；None = 不是和弦（旋律）；"?" = 还判断不了（分解和弦刚开始，音还不够）。
        - 少于 3 个不同音级不判和弦；但分解和弦里"低音 + 其上大/小三度"已足以暗示以低音为根的三和弦；
        - 分解和弦只认三和弦/七和弦且不允许省略音（挂留、加九、六和弦多半是旋律经过音凑出来的），
          同时按下的块和弦才允许全部模板、七和弦可省略五音；
        - 覆盖率不够（旋律经过音太多）不判"""
        w = {}
        for m, x in ws:
            w[m % 12] = w.get(m % 12, 0.0) + x
        bass_pc = bass % 12
        if len(w) < 3:
            if kind == "bass" and len(w) == 2:
                other = next(pc for pc in w if pc != bass_pc) if bass_pc in w else None
                if other is not None and (other - bass_pc) % 12 in (3, 4):
                    return NOTE_NAMES[bass_pc] + ("" if (other - bass_pc) % 12 == 4 else "m")
                return "?"
            return "?" if kind == "bass" else None
        total = sum(w.values())
        allowed = CHORD_TEMPLATES if kind == "block" else {
            k: v for k, v in CHORD_TEMPLATES.items() if k in ("maj", "min", "dim", "aug", "7", "m7", "maj7", "m7b5", "dim7")}
        best = None
        for root in range(12):
            for name, tpl in allowed.items():
                if name == "5":
                    continue
                tset = {(root + i) % 12 for i in tpl}
                missing = tset - set(w)
                if missing and not (kind == "block" and len(tset) == 4 and missing == {(root + 7) % 12}):
                    continue                  # 只有同时按下的七和弦允许省略五音
                cover = sum(x for pc, x in w.items() if pc in tset) / total
                score = cover - 0.04 * (len(tset) - 3) + CHORD_PRIOR.get(name, 0.0)
                if missing:
                    score -= 0.08
                if bass_pc == root:
                    score += 0.08
                elif bass_pc in tset:
                    score += 0.02
                if best is None or score > best[0]:
                    best = (score, root, name, cover, tset)
        if best is None:
            return None
        _, root, name, cover, tset = best
        if cover < {"block": 0.75, "bass": 0.85, "arp": 0.97}[kind]:
            return None
        text = NOTE_NAMES[root] + CHORD_SUFFIX[name]
        if bass_pc != root and bass_pc in tset:
            text += "/" + NOTE_NAMES[bass_pc]          # 转位：低音不是根音
        return text

    def _current_chord_text(self):
        """当前和弦（无和弦时为空字符串）。同时按下的块和弦立即显示；其它变化要连续保持 0.15 s
        （变为"无和弦"要 0.4 s），避免分解和弦、经过音造成的闪烁"""
        now = self._now()
        hw = self._harmony_window(now)
        cand, block = "", False
        if hw is not None:
            ws, bass, kind = hw
            block = kind == "block"
            ck = self.instrument.match_chord_key(sorted({m % 12 for m, _ in ws})) if block else None
            cand = f"{ck[1]}（键 {ck[0]}）" if ck else (self._name_chord(ws, bass, kind) or "")
            if cand == "?":
                return self._chord_disp           # 新的分解和弦刚开始、音还不够：先保持原来的显示
        if cand == self._chord_disp:
            self._chord_cand = None
        elif block and cand:
            self._chord_disp = cand
            self._chord_cand = None
        else:
            c = self._chord_cand
            if c is None or c[0] != cand:
                self._chord_cand = (cand, now)
            elif now - c[1] >= (0.15 if cand else 0.4):
                self._chord_disp = cand
                self._chord_cand = None
        return self._chord_disp
