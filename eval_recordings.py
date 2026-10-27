# -*- coding: utf-8 -*-
"""
真实录音回归：新旧检测引擎在仓库自带录音上的起音精度与 BPM 对比。

录音没有逐音真值，这里用一个与检测引擎无关的离线算法给出"参考起音"：
1024 点窗 / 128 点帧移（2.7 ms）的 log 谱通量 + 频率最大值滤波 + 自适应阈值峰值拾取。
参考 BPM = 参考起音间隔中最密集的 ±6% 簇的中位数换算。

用法： python eval_recordings.py            （需要 git，用于取出 HEAD 版本作对比）
"""
import wave

import numpy as np

import benchmark_timing as B
from instruments import build_lyre21

FILES = [("web_test1.wav", 0, 99), ("web_test3.wav", 0, 99), ("web_test5.wav", 0, 99),
         ("web_test8.wav", 0, 99), ("v2_lowhigh.wav", 0, 99), ("score_test.wav", 39.0, 61.0)]
SR = 48000


def load(fn):
    wf = wave.open(fn, "rb")
    x = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32767
    if wf.getnchannels() > 1:
        x = x.reshape(-1, wf.getnchannels()).mean(axis=1)
    return x


def reference_onsets(x, sr=SR, n=1024, hop=128):
    win = np.hanning(n)
    pad = np.concatenate([np.zeros(n), x, np.zeros(n)])
    fr = np.lib.stride_tricks.sliding_window_view(pad, n)[::hop]
    S = np.abs(np.fft.rfft(fr * win, axis=1))
    f = np.fft.rfftfreq(n, 1 / sr)
    L = np.log1p(100.0 * S[:, (f > 60) & (f < 8000)])
    Lm = np.maximum(np.maximum(L, np.roll(L, 1, axis=1)), np.roll(L, -1, axis=1))
    d = np.zeros(len(L))
    d[2:] = np.sum(np.maximum(L[2:] - Lm[:-2], 0.0), axis=1)
    t = (np.arange(len(L)) * hop + n / 2 - n) / sr
    w, wl = max(1, int(round(0.03 * sr / hop))), max(1, int(round(0.25 * sr / hop)))
    delta = 0.08 * d.max()
    out, last = [], -1e9
    for i in range(w, len(d) - w):
        if d[i] == d[i - w:i + w + 1].max() and d[i] > np.median(d[max(0, i - wl):i + w + 1]) + delta:
            if t[i] - last >= 0.06:
                out.append(t[i])
                last = t[i]
    return out


def run(mod, x):
    det = mod.NoteDetector(build_lyre21("风物之诗琴"), sr=SR, sensitivity=0.55, sim_clock=True)
    bpm = None
    for i in range(len(x) // 2048):
        r = det.feed(x[i * 2048:(i + 1) * 2048])
        if r["bpm"] is not None:
            bpm = r["bpm"]
    ons = sorted(o[0] for o in det.onsets if len(o) < 3 or o[2] > 0)
    merged = []
    for t in ons:                      # 旧版不合并和弦：统一按 35 ms 合并后再比
        if not merged or t - merged[-1] >= 0.035:
            merged.append(t)
    return merged, bpm


def match(ref, det, tol=0.05):
    used, errs = set(), []
    for r in ref:
        cands = [(abs(d - r), j) for j, d in enumerate(det) if j not in used and abs(d - r) <= tol]
        if cands:
            e, j = min(cands)
            used.add(j)
            errs.append(e)
    tp = len(errs)
    p = tp / len(det) if det else 0.0
    rc = tp / len(ref) if ref else 0.0
    f1 = 2 * p * rc / (p + rc) if p + rc else 0.0
    return p, rc, f1, (1000 * float(np.mean(errs)) if errs else float("nan"))


def ref_bpm(ref):
    ioi = np.diff(ref)
    if len(ioi) < 3:
        return None
    best = max((ioi[np.abs(ioi / c - 1) < 0.06] for c in ioi), key=len)
    return 60.0 / float(np.median(best))


def main():
    old_mod, new_mod = B.load_detector_module(True), B.load_detector_module(False)
    print(f"{'录音':16s} {'参考起音':>6s} | {'旧版 P/R/F1':>15s} {'误差ms':>6s} {'BPM':>7s} |"
          f" {'新版 P/R/F1':>15s} {'误差ms':>6s} {'BPM':>7s} | {'参考BPM':>7s}")
    for fn, t0, t1 in FILES:
        x = load(fn)
        ref = [a for a in reference_onsets(x) if t0 <= a <= t1]
        s0 = int(max(0.0, t0 - 0.5) * SR)
        xs = x[s0:int(min(len(x) / SR, t1) * SR)]
        cols = []
        for mod in (old_mod, new_mod):
            ons, bpm = run(mod, xs)
            p, rc, f1, mae = match(ref, [o + s0 / SR for o in ons])
            cols.append(f"{p:.2f}/{rc:.2f}/{f1:.2f}   {mae:6.1f} {('—' if bpm is None else f'{bpm:.1f}'):>7s}")
        rb = ref_bpm(np.array(ref))
        print(f"{fn:16s} {len(ref):6d} | {cols[0]} | {cols[1]} | {('—' if rb is None else f'{rb:.1f}'):>7s}")


if __name__ == "__main__":
    main()
