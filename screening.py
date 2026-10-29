# -*- coding: utf-8 -*-
"""边界值排查：从声音里找出超出人手极限的操作，作为判断"是不是自动演奏脚本"的证据

只给证据、不下结论，分两级：
  超出人手极限 —— 人做不到：同时按下超过 10 个键（人只有 10 根手指）；
  疑似机械操作 —— 人极难做到：很长一段连续音的间隔完全一致（机器级精度）。

1) 同时按键数
   起音相差 ≤ 45 ms（约 2 个发声块）的算同一次按下。在这次按下前后各取一段等长的长窗
   （最长 341 ms，频率分辨率足以分开最低音区的半音），按每个键基频处"新出现的谱峰"计数：
     - 峰必须落在这个键的音高 ±0.25 半音以内（相邻键的裙边不算），并且比按下前高 ≥ 6 dB；
     - 比这次最强的新峰弱 14 dB 以上的不算，比相邻（±2 半音内）已计入的键弱 8 dB 以上的也不算
       （敲击/采样在相邻频点产生的"假音"；原神没有力度变化，同时按下的真音电平相近）；
     - 能被更低的、已计入的键的谐波解释的不算。各次谐波的相对电平从录音里单独按下的音学出来
       （乐器音色不同：诗琴的二次谐波约 -18 dB，圆号约 -5 dB）；学够之前用偏保守（偏强）的默认值。
   后面紧跟着下一个音时，后窗截到下一个音之前（不足 128 ms 时不计数）；检测器漏掉的紧随其后的音
   这样排除：把后窗分成前后两半，后一半比前一半还响 6 dB 以上的键是后来才响起的，不算
   （跟着这次按下一起响起的音只会衰减或保持；半窗分不开的相邻键之间不做这项，以免互相干扰误删）。
   长窗（≥ 256 ms）计数误差约 ±1 个键：估计 11 个报"疑似"，≥ 12 个报"超出人手极限"；
   短窗（后面紧跟着别的音）误差更大，只在估计 ≥ 12 个时报"疑似"。
   悠可琴有和弦键（一个键发出好几个音），不做这项。
   注意：电脑键盘上一根手指可以同时压住两个相邻的键，所以这是很强的证据，但不是铁证。

2) 机械等间隔
   原神的声音按 1024 样本（48 kHz 下 21.33 ms）一块发出，按键时刻被对齐到块上：
   人手十几毫秒以内的误差在录音里看不见，一段短的轮指人弹出来也是"间隔完全一致"。
   所以只看很长的等间隔连续音：连续 N 个起音全部落在宽 ≤ 1 块的等间隔带内（发声块量化后
   与完美等间隔的时序完全相同——不按帧读输入的脚本一定满足），且 N 达到按速度标定的长度才报"疑似"。
   标定（SCREEN_REGULAR_TABLE）：用人手计时模型（Wing-Kristofferson：时钟 CV 2.5%、动作噪声 3 ms、
   缓慢速度漂移 1.5%）模拟"很稳的人"弹 240 个音的长轮指（任意一段连续 N 个音都算），
   经发声块量化后被误判的概率 < 0.5%。
   速度接近发声块整数倍时（如 64 ms = 3 块）人手误差最不容易显现，需要更长的段，个别速度不做判断。
   若游戏逐帧读取按键，脚本的时序也会被帧打乱，这项会漏报——但不会因此多冤枉人。
"""
import math
import threading
from collections import deque

import numpy as np

Q_BLOCK = 1024 / 48000.0          # 原神发声块（秒）

LEVEL_LIMIT = "limit"
LEVEL_SUSPECT = "suspect"
LEVEL_TEXT = {LEVEL_LIMIT: "超出人手极限", LEVEL_SUSPECT: "疑似机械操作"}
KIND_TEXT = {"keys": "同时按键", "regular": "机械等间隔"}

# 谐波相对基频的电平（dB），用于判断一个新峰是不是更低的键的谐波。录音里有足够多单独按下的音后改用实测值
HARM_PLUCK = {2: -18.0, 3: -22.0, 4: -30.0, 5: -30.0, 6: -29.0, 7: -28.0}   # 实测：风物之诗琴采样
HARM_HORN = {2: -5.0, 3: -9.0, 4: -15.0, 5: -20.0, 6: -40.0, 7: -40.0}
HARM_STRONG = {2: -5.0, 3: -9.0, 4: -13.0, 5: -16.0, 6: -19.0, 7: -22.0}   # 未实测的乐器：按谐波偏强处理（只会少数）
HARMS = (2, 3, 4, 5, 6, 7)

# (周期 ms, 需要的最少连续起音数；None = 这个速度下判断不了)。由 regularity_calib2 模拟得到：
# 每个速度模拟 250 段"很稳的人"弹的 240 音长轮指，取其中最长的"完全等间隔"段 + 1
SCREEN_REGULAR_TABLE = [
    (40.0, 63), (42.0, None), (44.1, 82), (46.3, 64), (48.6, 74), (51.1, 90), (53.6, 142), (56.3, 85),
    (59.1, 74), (62.1, 78), (65.2, 137), (68.4, 64), (71.8, 64), (75.4, 92), (79.2, 65), (83.2, 75),
    (87.3, 97), (91.7, 69), (96.3, 84), (101.1, 53), (106.1, 148), (111.4, 55), (117.0, 66), (122.9, 47),
    (129.0, 128), (135.5, 54), (142.2, 49), (149.3, 128), (156.8, 45), (164.6, 44), (172.9, 78), (181.5, 50),
    (190.6, 108), (200.1, 45), (210.1, 65), (220.6, 40), (231.7, 73), (243.3, 48), (255.4, 57), (268.2, 37),
    (281.6, 51), (295.7, 52), (310.5, 38), (326.0, 49), (342.3, 48), (359.4, 61), (377.4, 40), (396.2, 39),
    (416.1, 34), (436.9, 36), (458.7, 33), (481.6, 33), (505.7, 32), (531.0, 45), (557.5, 33), (585.4, 27),
    (614.7, 25), (645.4, 26), (677.7, 26), (711.6, 26), (747.2, 21), (784.5, 23), (823.8, 19), (864.9, 20),
    (908.2, 20), (953.6, 18), (1001.3, 19), (1051.3, 18), (1103.9, 17), (1159.1, 18), (1217.1, 16),
]


def strip_width(x, k):
    """点 (x[i], k[i])（x 递增）的最小竖直带宽 min_p [max(k − p·x) − min(k − p·x)] 及对应斜率 p。
    带宽是 p 的凸分段线性函数，最小值一定在上/下凸包某条边的斜率处取到"""
    n = len(k)
    if n <= 2:
        return 0.0, (float(k[-1] - k[0]) / max(1e-9, float(x[-1] - x[0]))) if n == 2 else 0.0
    lower, upper = [], []
    for i in range(n):
        xi, y = float(x[i]), float(k[i])
        while len(lower) >= 2 and (lower[-1][0] - lower[-2][0]) * (y - lower[-2][1]) - \
                (lower[-1][1] - lower[-2][1]) * (xi - lower[-2][0]) <= 0:
            lower.pop()
        lower.append((xi, y))
        while len(upper) >= 2 and (upper[-1][0] - upper[-2][0]) * (y - upper[-2][1]) - \
                (upper[-1][1] - upper[-2][1]) * (xi - upper[-2][0]) >= 0:
            upper.pop()
        upper.append((xi, y))
    U = np.array(upper)
    L = np.array(lower)
    best, best_s = math.inf, 0.0
    for h in (lower, upper):
        for a, b in zip(h, h[1:]):
            s = (b[1] - a[1]) / (b[0] - a[0])
            w = float((U[:, 1] - s * U[:, 0]).max() - (L[:, 1] - s * L[:, 0]).min())
            if w < best:
                best, best_s = w, s
    return best, best_s


def regular_need(period_s):
    """这个周期下判为"机械等间隔"所需的最少连续起音数（取 ±6% 内标定点的最大值，保守）；None = 不判断"""
    p = period_s * 1000.0
    near = [n for pm, n in SCREEN_REGULAR_TABLE if abs(pm / p - 1.0) <= 0.06]
    if not near or any(n is None for n in near):
        return None
    return max(near)


class KeyCounter:
    """按下前后两段等长音频 → 新按下的键（MIDI 列表）"""
    NW = 16384            # 长窗（341 ms）
    NF = 32768
    MIN_LEN = 6144        # 后窗至少 128 ms
    RELIABLE = 12288      # 后窗 ≥ 256 ms 时计数误差约 ±1
    LATE_DB = 6.0         # 后窗后一半比前一半还响这么多 → 后来才响起的键
    GAP = 0.008           # 窗与起音之间留的间隔（秒）
    RISE_DB = 6.0
    REL_DB = -14.0
    HARM_MARGIN_DB = 4.0

    def __init__(self, midis, sr=48000):
        self.sr = sr
        self.midis = sorted(midis)
        f0 = np.array([440.0 * 2 ** ((m - 69) / 12.0) for m in self.midis])
        self.f0 = f0
        b = f0 * self.NF / sr
        self.lo = np.floor(b * 2 ** (-0.55 / 12)).astype(int)
        self.hi = np.ceil(b * 2 ** (0.55 / 12)).astype(int)
        self.plo = b * 2 ** (-0.25 / 12)
        self.phi = b * 2 ** (0.25 / 12)
        self.ctr = np.round(b).astype(int)
        # harm_of[i] = [(j, h)]：更低的键 j 的第 h 次谐波落在键 i 上（±0.3 半音）
        self.harm_of = []
        for i in range(len(f0)):
            rel = []
            for j in range(i):
                r = f0[i] / f0[j]
                h = int(round(r))
                if h in HARMS and abs(12 * math.log2(r / h)) <= 0.3:
                    rel.append((j, h))
            self.harm_of.append(rel)

    def spectrum(self, x):
        return np.abs(np.fft.rfft(x * np.hanning(len(x)), n=self.NF))

    def _levels(self, S):
        """幅度谱 → 各键基频处的电平、是否为该键音高上的峰"""
        A = np.empty(len(self.midis))
        pk = np.zeros(len(self.midis), dtype=bool)
        for i in range(len(self.midis)):
            k = self.lo[i] + int(np.argmax(S[self.lo[i]:self.hi[i] + 1]))
            if self.plo[i] <= k <= self.phi[i]:
                A[i] = S[k]
                pk[i] = True
            else:
                A[i] = S[self.ctr[i]]
        return A, pk

    def count(self, before, after, harm):
        """before / after：等长音频；harm：{谐波次数: 相对基频 dB}"""
        A, pk = self._levels(self.spectrum(after))
        B, _ = self._levels(self.spectrum(before))
        LA = 20 * np.log10(A + 1e-12)
        rise = LA - 20 * np.log10(B + 1e-12)
        cand = pk & (rise >= self.RISE_DB)
        if len(after) >= 2 * 4096:
            # 后窗后一半比前一半还响：后来才响起的键（检测器漏掉了紧随其后的那个音的起音），不算。
            # 半窗的频率分辨率低：与另一个候选键相距不到 3 个半窗频点的键，电平会被对方的主瓣干扰，不做这项
            h = len(after) // 2
            A1, _ = self._levels(self.spectrum(after[:h]))
            A2, _ = self._levels(self.spectrum(after[h:2 * h]))
            late = 20 * np.log10(A2 + 1e-12) - 20 * np.log10(A1 + 1e-12) >= self.LATE_DB
            res = 3.0 * self.sr / h
            idx = np.nonzero(cand)[0]
            for i in idx:
                if late[i] and all(abs(self.f0[i] - self.f0[j]) >= res for j in idx if j != i):
                    cand[i] = False
        if not cand.any():
            return []
        cand &= LA >= LA[cand].max() + self.REL_DB
        keys = []
        for i in np.nonzero(cand)[0]:                   # 从低到高
            pred = sum(A[j] * 10 ** (harm[h] / 20.0) for j, h in self.harm_of[i] if j in keys)
            if pred > 0 and A[i] <= pred * 10 ** (self.HARM_MARGIN_DB / 20.0):
                continue
            keys.append(i)
        # 假音：比相邻（±2 半音内）已计入的键弱 8 dB 以上
        ghost = {i for i in keys for j in keys
                 if j != i and abs(self.midis[i] - self.midis[j]) <= 2 and LA[j] - LA[i] >= 8.0}
        return [self.midis[i] for i in keys if i not in ghost]

    def single_harmonics(self, before, after):
        """单独按下的一个音 → {谐波次数: 相对基频 dB}（只取起音后新增的能量）；判断不了时返回 None"""
        Sa, Sb = self.spectrum(after), self.spectrum(before)
        A, pk = self._levels(Sa)
        B, _ = self._levels(Sb)
        rise = 20 * np.log10(A + 1e-12) - 20 * np.log10(B + 1e-12)
        ok = pk & (rise >= 12.0)
        if not ok.any():
            return None
        i = int(np.argmax(np.where(ok, A, 0.0)))
        f0 = 440.0 * 2 ** ((self.midis[i] - 69) / 12.0)
        d = np.maximum(Sa - Sb, 0.0)
        b0 = f0 * self.NF / self.sr
        a0 = d[int(b0 * 2 ** (-0.3 / 12)):int(np.ceil(b0 * 2 ** (0.3 / 12))) + 1].max()
        if a0 <= 0:
            return None
        out = {}
        for h in HARMS:
            bh = h * b0
            if bh * 2 ** (0.3 / 12) >= len(d) - 1 or h * f0 > 8000:
                break
            ah = d[int(bh * 2 ** (-0.3 / 12)):int(np.ceil(bh * 2 ** (0.3 / 12))) + 1].max()
            out[h] = 20 * math.log10(max(ah, 1e-12) / a0)
        return out


class Screener:
    """边界值排查（与 NoteDetector 并行：每次 det.feed(block) 之后调用 process(block, det)）"""
    MAX_FINGERS = 10
    BURST_GAP = 0.045       # 起音相差 ≤ 45 ms 算同一次按下
    BURST_SPAN = 0.09       # 一次按下最多跨 90 ms（再长就是快速连奏/刮奏，不是同时）
    SETTLE = 0.6            # 起音 0.6 s 后再处理：后窗完整、检测器对音符的确认/剔除已完成
    MIN_DET_NOTES = 3       # 检测器在这次按下里至少认出 3 个音才计数（大和弦检测器往往只认出 4~8 个）
    REG_W = 1.0             # 等间隔带宽阈值（发声块）：完美等间隔经发声块量化后带宽 < 1
    REG_MIN_P, REG_MAX_P = 0.040, 1.25
    REG_BREAK = 1.5         # 两个起音相隔超过 1.5 s 视为断开
    REG_MAX_WIN = 400
    GRID_R = 0.55           # 起音落在发声块网格上的集中度 ≥ 0.55 → 按块计（游戏原声）
    RAW_Q = 0.010           # 不在网格上（不是游戏原声）：按 10 ms 带宽、至少 32 个起音判断
    RAW_NEED = 32

    def __init__(self, instrument, sr=48000):
        self.sr = sr
        self._lock = threading.Lock()
        self.set_instrument(instrument)
        self.reset()

    def set_instrument(self, inst):
        self.instrument = inst
        self.count_enabled = inst.name != "悠可琴"
        self.harm_default = {"风物之诗琴": HARM_PLUCK, "晚风圆号": HARM_HORN}.get(inst.name, HARM_STRONG)
        self.counter = KeyCounter(inst.valid_midis(), self.sr)

    def reset(self):
        with self._lock:
            self._buf = np.zeros(0, dtype=np.float32)
            self._buf_start = 0
            self._burst_t = -1e9
            self._reg_t = -1e9
            self._reg_ts = []
            self._run = []
            self._reg_grid = None
            self._reg_ph = 0.0
            self._reg_slope = 1.0
            self._reg_skipped = False
            self._reg_find = None
            self.findings = []
            self.max_keys = 0
            self.max_keys_t = None
            self.longest_regular = (0, None, None)     # (音数, 周期 s, 起始时刻)
            self.burst_log = deque(maxlen=400)          # [(时刻, 估计键数, [MIDI])]：每次做过计数的按下（调试/评测）
            self._harm_obs = {h: deque(maxlen=40) for h in HARMS}   # 单独按下的音实测的谐波电平
            self._next_id = 1

    # ------------------------------------------------------------------
    def process(self, block, det, final=False):
        """喂入与 det 相同的音频块；返回本次新增或更新的发现（dict 列表，同一发现 id 不变）"""
        with self._lock:
            self._append(np.asarray(block, dtype=np.float32).reshape(-1))
            now = det._now()
            out = self._scan_bursts(det, now, final)
            out += self._scan_regular(det, now, final)
            return out

    def _append(self, x):
        self._buf = np.concatenate([self._buf, x])
        keep = int(3.0 * self.sr)
        if len(self._buf) > keep + self.sr:
            drop = len(self._buf) - keep
            self._buf = self._buf[drop:]
            self._buf_start += drop

    def _segment(self, a, n):
        out = np.zeros(n, dtype=np.float32)
        s0 = max(a, self._buf_start)
        s1 = min(a + n, self._buf_start + len(self._buf))
        if s1 > s0:
            out[s0 - a:s1 - a] = self._buf[s0 - self._buf_start:s1 - self._buf_start]
        return out

    def _new_id(self):
        i = self._next_id
        self._next_id += 1
        return i

    # ------------------------------------------------------------------ 同时按键数
    def _scan_bursts(self, det, now, final):
        if not self.count_enabled:
            return []
        cutoff = now - (0.36 if final else self.SETTLE)
        new = []
        for e in reversed(det.onsets):
            if e[0] <= self._burst_t:
                break
            if e[0] <= cutoff:
                new.append((e[0], e[2]))
        if not new:
            return []
        new.sort()
        bursts = []
        for t, c in new:
            if bursts and t - bursts[-1][1] <= self.BURST_GAP and t - bursts[-1][0] <= self.BURST_SPAN:
                bursts[-1][1] = t
                bursts[-1][2] += c
            else:
                bursts.append([t, t, c])
        if not final and cutoff - bursts[-1][1] < self.BURST_GAP + 0.005:
            bursts.pop()                        # 可能还没收齐，下次再处理
        out = []
        for t0, t1, c in bursts:
            self._burst_t = t1
            if c >= self.MIN_DET_NOTES:
                f = self._count_burst(det, t0, t1)
                if f is not None:
                    out.append(f)
            elif c == 1:
                self._learn_single(det, t0, t1)
        return out

    def harm_profile(self):
        """当前用于"谐波解释"的各次谐波电平：每次谐波攒够 6 个单独按下的音后用实测中位数（不低于 -45 dB）"""
        prof = dict(self.harm_default)
        for h, obs in self._harm_obs.items():
            if len(obs) >= 6:
                prof[h] = float(min(-3.0, max(-45.0, np.median(obs))))
        return prof

    def _learn_single(self, det, t0, t1):
        win = self._windows(det, t0, t1)
        if win is None:
            return
        before, after, _ = win
        hs = self.counter.single_harmonics(before, after)
        if hs:
            for h, v in hs.items():
                self._harm_obs[h].append(v)

    def _windows(self, det, t0, t1):
        """这次按下前后等长的两段音频 (before, after, 按下的末尾时刻)；后面紧跟着下一个音、窗太短时返回 None"""
        # 这次按下的末尾：并入 45 ms 内的细分辨率起音峰；下一个起音（检测器起音或起音峰）之前截止
        peaks = sorted([p[0] for p in det._of_peaks] + [e[0] for e in det.onsets[-24:]])
        end = t1
        for p in peaks:
            if t0 - 0.01 <= p <= end + self.BURST_GAP and p - t0 <= self.BURST_SPAN:
                end = max(end, p)
        t_next = next((p for p in peaks if p > end + 0.005), None)
        g = self.counter.GAP
        L = self.counter.NW
        if t_next is not None:
            L = min(L, int((t_next - g - (end + g)) * self.sr))
        if L < self.counter.MIN_LEN:
            return None
        after = self._segment(int(round((end + g) * self.sr)), L)
        before = self._segment(int(round((t0 - g) * self.sr)) - L, L)
        return before, after, end

    def _count_burst(self, det, t0, t1):
        win = self._windows(det, t0, t1)
        if win is None:
            return None
        before, after, end = win
        keys = self.counter.count(before, after, self.harm_profile())
        n = len(keys)
        reliable = len(after) >= self.counter.RELIABLE
        self.burst_log.append((t0, n, keys, len(after)))
        if n > self.max_keys:
            self.max_keys, self.max_keys_t = n, t0
        if n <= self.MAX_FINGERS or (not reliable and n < self.MAX_FINGERS + 2):
            return None
        labels = [self.instrument.label_of(m)[0] for m in keys]
        # 长窗计数误差约 ±1：估计 11 个可能其实是 10 个 → 只算"疑似"；≥12 个才算超出人手极限。
        # 短窗（后面紧跟着别的音）误差更大：最多算"疑似"
        sure = reliable and n >= self.MAX_FINGERS + 2
        f = {"id": self._new_id(), "kind": "keys", "level": LEVEL_LIMIT if sure else LEVEL_SUSPECT,
             "t": t0, "t_end": end, "n": n, "keys": labels,
             "title": f"同时按下约 {n} 个键",
             "text": (f"同时按下约 {n} 个键（{' '.join(labels)}），超过人的 10 根手指"
                      if sure else f"同时按下约 {n} 个键（{' '.join(labels)}），可能超过 10 根手指"
                                   f"（计数误差约 ±{1 if reliable else 2} 个）")
                     + "；电脑键盘上一根手指能压住两个相邻键，属强证据而非铁证"}
        self.findings.append(f)
        return f

    # ------------------------------------------------------------------ 机械等间隔
    # 当前等间隔段：_run = [[起音时刻, 拍号]]。快速轮指里检测器会漏掉一些起音，
    # 所以按"拍号"对齐（相邻起音隔了几拍：间隔 ≈ 1~4 个周期），而不是要求每一拍都有起音；
    # 段内起音数按实际检测到的计（比"每拍都有"更保守）
    def _scan_regular(self, det, now, final):
        cutoff = now - (0.25 if final else self.SETTLE)
        new = []
        for e in reversed(det.beat_onsets):
            if e[0] <= self._reg_t:
                break
            if e[0] <= cutoff:
                new.append(e[0])
        out = []
        for t in sorted(new):
            self._reg_t = t
            out += self._reg_add(t)
        if final:
            out += self._reg_close()
        return out

    def _reg_close(self):
        f = self._reg_find
        self._reg_find = None
        return [f] if f is not None else []

    def _reg_coords(self, ts):
        if self._reg_grid:
            return np.round((np.asarray(ts) - self._reg_ph) / Q_BLOCK)
        return (np.asarray(ts) - ts[0]) / self.RAW_Q

    def _reg_point(self, t):
        """把一个起音并入当前等间隔段（按拍号对齐、去掉段首直到带宽 ≤ 阈值）。
        返回 (段是否被打断重来, 带宽)"""
        run = self._run
        if not run:
            run.append([t, 0])
            return False, 0.0
        thr = self.REG_W if self._reg_grid else 1.0
        k = self._reg_coords([r[0] for r in run] + [t])
        xs = [r[1] for r in run]
        if len(run) >= 4:
            p_hat = self._reg_slope
        elif len(run) >= 2:
            p_hat = (k[-2] - k[0]) / max(1, xs[-1] - xs[0])
        else:
            p_hat = k[-1] - k[-2]
        r = (k[-1] - k[-2]) / max(p_hat, 1e-9)
        m = int(round(r))
        if m < 1 or m > 4 or abs(r - m) > 0.35:
            if len(run) >= 8 and not self._reg_skipped:
                self._reg_skipped = True              # 一个不在拍上的起音（多检的）：先跳过，看下一个
                return False, None
            last = run[-1][0]                         # 节奏变了：从上一个起音重新开始
            run.clear()
            run.append([last, 0])
            run.append([t, 1])
            self._reg_skipped = False
            kk = self._reg_coords([last, t])
            self._reg_slope = float(kk[1] - kk[0])
            return True, 0.0
        self._reg_skipped = False
        run.append([t, xs[-1] + m])
        if len(run) > self.REG_MAX_WIN:
            del run[0]
        while True:
            k = self._reg_coords([r[0] for r in run])
            w, sl = strip_width([r[1] for r in run], k)
            if w <= thr + 1e-9 or len(run) <= 3:
                break
            del run[0]
        self._reg_slope = sl
        return False, w

    def _reg_add(self, t):
        out = []
        hist = self._reg_ts
        if hist and t - hist[-1] < 0.03:
            return out
        if hist and t - hist[-1] > self.REG_BREAK:
            out += self._reg_close()                  # 停顿：重新开始
            self._run.clear()
        hist.append(t)
        if len(hist) > 256:
            del hist[:128]
        recent = np.asarray(hist[-64:])
        z = np.exp(2j * np.pi * recent / Q_BLOCK).mean()
        grid = len(recent) >= 8 and abs(z) >= self.GRID_R
        self._reg_ph = float(np.angle(z)) / (2 * np.pi) * Q_BLOCK
        if grid != self._reg_grid:
            # 坐标系变了（攒够起音后发现落在游戏发声网格上）：用最近的起音按新坐标重建当前段
            out += self._reg_close()
            self._reg_grid = grid
            seg = [x for x in hist[:-1] if not self._run or x >= self._run[0][0]]
            self._run.clear()
            self._reg_skipped = False
            for x in seg:
                self._reg_point(x)
        broke, w = self._reg_point(t)
        if broke:
            out += self._reg_close()
        if w is None:
            return out
        run = self._run
        unit = Q_BLOCK if grid else self.RAW_Q
        n = len(run)
        period = self._reg_slope * unit
        if n < 3 or not (self.REG_MIN_P <= period <= self.REG_MAX_P):
            out += self._reg_close()
            return out
        if n > self.longest_regular[0]:
            self.longest_regular = (n, period, run[0][0])
        need = regular_need(period) if grid else self.RAW_NEED
        if need is None or n < need:
            out += self._reg_close()
            return out
        f = self._reg_find
        if f is None:
            f = {"id": self._new_id(), "kind": "regular", "level": LEVEL_SUSPECT, "t": run[0][0], "n": n - 1}
            self._reg_find = f
            self.findings.append(f)
        f["n"] += 1
        cnt = f["n"]
        dur = t - f["t"]
        tol_ms = 0.5 * w * unit * 1000.0
        f.update({"t_end": t, "period_ms": period * 1000.0,
                  "title": f"连续 {cnt} 个音间隔完全一致",
                  "text": f"约 {period * 1000:.0f} ms 一个音、持续 {dur:.1f} 秒，全部落在完美等间隔 ±{max(tol_ms, 1):.0f} ms 以内"
                          f"（游戏发声精度）；很稳的人连续这么多音也会偏出（按计时模型模拟，误判概率 < 0.5%），"
                          f"可能是脚本，也可能是极稳的人，需结合其它证据"})
        out.append(f)
        return out

    # ------------------------------------------------------------------
    def summary(self):
        """一句话总结（报告 / 界面用）"""
        lim = sum(1 for f in self.findings if f["level"] == LEVEL_LIMIT)
        sus = sum(1 for f in self.findings if f["level"] == LEVEL_SUSPECT)
        parts = []
        if lim or sus:
            parts.append("发现 " + "、".join(x for x in (f"超出人手极限 {lim} 处" if lim else "",
                                                        f"疑似机械操作 {sus} 处" if sus else "") if x))
        else:
            parts.append("未发现超出人手极限的操作")
        extra = []
        if self.count_enabled:
            extra.append(f"最多同时按下约 {self.max_keys} 个键" if self.max_keys else "没有 3 个键以上的同时按下")
        n, p, _ = self.longest_regular
        if n >= 8 and p:
            extra.append(f"最长的等间隔连续音 {n} 个（约 {p * 1000:.0f} ms 一个）")
        return "；".join(parts + extra)
