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
- BPM：同一起音（和弦）合并为一个事件 → 一/二/三阶起音间隔在候选周期上做软核打分
  （按倍数 k 降权，天然抑制"取半周期/倍周期"）→ 分段同相位网格的合并回归精修周期
  （精度不受候选步长限制，休止/拖拍只影响局部）→ 小幅平滑 + 两次确认才跳变。
- 调性：Krumhansl-Schmuckler 键位相关性分析（24 调）
- 和弦：音级集合 → 和弦模板匹配
"""
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

# 逐帧记录复数谱的 MIDI 范围（覆盖全部乐器 ±12 半音移调）
_TRACK_LO, _TRACK_HI = 34, 98

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
    def set_instrument(self, inst: Instrument):
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
        self._attack = {}             # midi -> 攻击强度（首帧幅度/上帧同频幅度）
        self._attack_t = {}           # midi -> 攻击强度取得最大值的帧时刻
        self.onsets = []              # [[t, 强度, 音数, 最强音电平]] 音符起音（和弦合并），用于间隔/旁瓣判定
        self.beat_onsets = []         # [[t, 强度]] BPM 用起音：起音峰 + 音高证据（和弦合并）
        self._onsets_ver = 0
        self._prev_mag = None
        self._recent_peak = 0.0       # 近期最大帧峰值（指数衰减），用于相对门限
        self._floor = 1e-7            # 自适应噪声底
        self._bpm_smooth = None
        self._bpm_pending = None
        self._bpm_key = None
        self._bpm_val = None
        self.bpm_confidence = 0.0
        self.chroma_note_log = []     # [time, midi, dur_ms, amp] 用于调性

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
            self._of_buf = np.concatenate([self._of_buf, chunk])
            self._update_odf()
            out = {"keys": {}, "note_events": [], "chord": "", "tonality": "",
                   "bpm": None, "t": 0.0}
            while len(self._buf) >= self.fft_size:
                frame = self._buf[:self.fft_size]
                t_c = (self._buf_pos + self.fft_size / 2.0) / self.sr   # 帧中心时刻
                self._buf = self._buf[self.hop:]
                self._buf_pos += self.hop
                res = self._process_frame(frame, t_c)
                out["keys"].update(res["keys"])
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
        midis_new = self._dedup_harmonics(midis_new, amp_dict)
        midis_all = self._dedup_harmonics(midis_all, amp_dict)

        # 范围过滤 + 吸附到乐器可用音（含移调）
        valid = self.instrument.valid_midis()
        lo, hi = valid[0] - 1, valid[-1] + 1

        def snap(ms):
            out = []
            for m in ms:
                if lo <= m <= hi:
                    s = min(valid, key=lambda v: abs(v - m))
                    if s not in out:
                        out.append(s)
            return out
        snapped_new = snap(midis_new)
        # raw：新音候选 ∪ 仍在峰中出现且幅度仍显著（≥15% 帧峰值）的已活跃音。
        # 已活跃音只认"精确命中"的峰（四舍五入后的音高就是它本身）：背景音乐/音效里的半音、
        # 非白键音被吸附到相邻琴键时，不应把一个已经结束的音一直撑着
        exact_all = set(midis_all)
        raw = set(snapped_new)
        for m in self.active:
            if m in exact_all and self._amp_of(m, mag) >= 0.15 * peak:
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
                if not cand:
                    continue
                nearby_attack, m_att = max(cand)
                if nearby_attack < attack_min:
                    continue
                t_first = self._first_seen.get(m, t_now)
                # 以"骤起"发生的帧为锚点找起音峰（该音可能早已以旁瓣形式出现，首次可见时刻不可靠）
                t_att = self._attack_t.get(m_att, t_first)
                on = self._match_onset(t_att, lo=min(t_first, t_att) - 0.075)
                if on is None or on[0] < t_first - 0.075:
                    # 无对应起音峰：琴类每次按键都有明显敲击瞬态，没有起音峰的"新音"
                    # 几乎都是余音里的旁瓣/谐波误检，不开新音
                    continue
                ok = self._press_ok(m, on[0])
                if ok is None:
                    continue          # 判定所需的帧还没到，下一帧再判
                if not ok:
                    # 本音频点没有像真实按键那样骤升：多为仍在响的余音被重新检出、或噪音音效，不开新音
                    continue
                self._open_note(m, min(on[0], t_now), t_now, amp, on[1])
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
            if a["ref"] is None and t_now >= a["start"] + 0.043:
                j = m - _TRACK_LO
                if 0 <= j < X.shape[1]:
                    xs = np.abs(X[:, j])
                    a["ref"] = xs.astype(np.float64)
                    a["h"] = int(np.argmax(xs))
                    self._set_ref_db(a)

        self._eval_pending(t_now, events)

        keys = {}
        for m in self.active:
            if self.active_frames.get(m, 0) == 0:
                label, _ = self.instrument.label_of(m)
                keys[label] = m
        return {"keys": keys, "note_events": events}

    # ------------------------------------------------------------------
    # 起音确认（BPM 用）与同键重按：起音前后整窗比较
    # ------------------------------------------------------------------
    RETRIG_DELAY = 0.18      # 起音后多久评估（需要 T+130 ms 处的"持续性"帧）

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
            if np.any((la_v - lb_v >= 2.0) & (la_v >= la_v.max() - 20.0)):
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

    def _set_ref_db(self, a):
        """记录音符"刚按下"电平，并更新所属起音事件中最强音的电平（用于识别起音旁瓣）"""
        a["ref_db"] = float(_db(np.max(a["ref"])))
        ev = a.get("ev")
        if ev is not None:
            ev[3] = max(ev[3], a["ref_db"])

    # ------------------------------------------------------------------
    # 落音定位
    # ------------------------------------------------------------------
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

    def _open_note(self, m, start, t_now, amp, strength):
        start = max(0.0, start)       # 流开头补的是虚拟静音，插值可能略早于 0
        entry = [start, m, 0.0, amp]
        self.active[m] = {"start": start, "last": t_now, "last_raw": t_now,
                          "last_raw_before_gap": t_now, "amp": amp, "amin": amp,
                          "maxamp": amp, "n": 0, "ref": None, "h": 0,
                          "ev": self._add_onset(start, strength), "chroma": entry}
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
        events.append(self._make_note_event(m, a, dur_ms, reason))
        entry = a.get("chroma")
        if entry is not None:
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
        return out[:12]

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

    def _dedup_harmonics(self, midis, amp_dict=None):
        """整数倍频去重：低频优先保留，高频谐波剔除。
        若高频音幅度<50%低频音幅度，视为弱谐波去掉；否则保留为独立音。"""
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
                        if amp_k > 0 and amp_m < 0.50 * amp_k:
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
    def _current_bpm(self):
        """BPM 起音序列（起音峰 + 音高证据，和弦已合并）→ estimate_ioi_period；仅在起音集合变化时重算"""
        now = self._now()
        lo_t = now - self.bpm_window
        ev = [e for e in self.beat_onsets if e[0] > lo_t]
        key = (self._onsets_ver, len(ev), ev[0][0] if ev else None)
        if key == self._bpm_key:
            return self._bpm_val
        self._bpm_key = key
        if len(ev) < 5:
            self._bpm_val = None
            return None
        times = np.array([e[0] for e in ev])
        # 近期起音权重更高：变速后约 4~6 s 即可跟上
        w = np.exp(-(now - times) / (0.4 * self.bpm_window))
        est = estimate_ioi_period(times, w)
        if est is None:
            return self._bpm_val
        self.bpm_confidence = est["conf"]
        if est["conf"] < 0.35:
            return self._bpm_val
        bpm = 60.0 / est["period"]
        s = self._bpm_smooth
        if s is None:
            s = bpm
        elif abs(bpm - s) / s <= 0.03:
            s = 0.5 * s + 0.5 * bpm
            self._bpm_pending = None
        elif self._bpm_pending is not None and abs(bpm - self._bpm_pending) / self._bpm_pending <= 0.03:
            s = bpm                       # 连续两次给出相同的新速度：确认变速，直接跳变
            self._bpm_pending = None
        else:
            self._bpm_pending = bpm       # 单次离群：先记下，不立即采纳
        self._bpm_smooth = s
        self._bpm_val = round(s, 1)
        return self._bpm_val

    # ------------------------------------------------------------------
    def _current_tonality_text(self):
        """Krumhansl-Schmuckler：最近 14s 音符（时长加权、指数衰减）→ 最可能调"""
        now = self._now()
        chroma = np.zeros(12)
        weight_sum = 0.0
        for t, midi, dur, amp in self.chroma_note_log:
            age = now - t
            if age > 14.0:
                continue
            # 时长权重封顶，避免长尾音过度主导
            w = amp * max(0.25, min(1.0, dur / 450.0)) * np.exp(-age / 7.0)
            chroma[midi % 12] += w
            weight_sum += w
        if weight_sum < 3.0:
            return "分析中…（音符不足）"
        chroma = chroma / (weight_sum + 1e-9)

        best_key, best_corr = None, -2.0
        second_corr = -2.0
        for root in range(12):
            cm = np.corrcoef(np.roll(KS_MAJOR, root), chroma)[0, 1]
            cn = np.corrcoef(np.roll(KS_MINOR, root), chroma)[0, 1]
            for name, c in (("maj", cm), ("min", cn)):
                if c > best_corr:
                    second_corr = best_corr
                    best_corr = c
                    best_key = (root, name)
                elif c > second_corr:
                    second_corr = c
        if best_key is None:
            return "未知"
        root, mode = best_key
        text = f"{NOTE_NAMES[root]} 大调" if mode == "maj" else f"{NOTE_NAMES[root]} 小调"
        conf = int(round(100 * max(0.0, (best_corr - 0.25)) / 0.65))
        conf = max(5, min(99, conf))
        return f"{text}（置信 {conf}%）"

    # ------------------------------------------------------------------
    def _current_chord_text(self):
        pcs = sorted({m % 12 for m in self.active.keys()})
        if len(pcs) < 2:
            return ""
        ck = self.instrument.match_chord_key(pcs)
        if ck:
            return f"{ck[1]}（键 {ck[0]}）"
        best = None
        for root in range(12):
            for tname, tpl in CHORD_TEMPLATES.items():
                tset = {(root + i) % 12 for i in tpl}
                if tset <= set(pcs):
                    score = len(tset) - 0.2 * (len(pcs) - len(tset))
                    if best is None or score > best[0]:
                        best = (score, root, tname, tset)
        if best is None:
            return ""
        _, root, tname, _ = best
        return f"{NOTE_NAMES[root]}{CHORD_SUFFIX[tname]}"
