# -*- coding: utf-8 -*-
"""
时间精度评测基准（带真值）：起音时间 / 按键时长 / 同键连按 / BPM

音色（全部 48 kHz 合成，按键时间、松键时间完全已知）：
  synth  —— test_detection.py 同款加法合成音，按 dur 硬截止（真值时长 = dur）
  lyre   —— 从 web_test7.wav 提取的真实琴音采样（C4）重采样移调，余音 3~4 s 自然衰减
             mode="ring"  ：松键不止音（拨弦类），时长真值不可观测，只评起音/BPM/连按
             mode="damp"  ：松键后 30 ms 指数止音（真值时长 = 按键时长）
  horn   —— 持续音（25 ms 起音、按住持续、松键 40 ms 释放），真值时长 = 按键时长

用法：
  python benchmark_timing.py               # 评测当前 detection.py
  python benchmark_timing.py --old         # 同时评测 git HEAD 版本做对比
  python benchmark_timing.py --noise --old # 游戏噪音场景（底噪/音效/背景音乐）下时长模块的敏感度对比
  python benchmark_timing.py --tempo --old # 频繁变速：BPM 读数多快跟上新速度、稳定速度时是否乱跳
"""
import argparse
import importlib.util
import json
import os
import subprocess
import tempfile
import wave

import numpy as np

from instruments import build_lyre21, build_horn

SR = 48000
BLOCK = 2048
HERE = os.path.dirname(os.path.abspath(__file__))

# 键位 → MIDI（21 键琴）
LYRE_KEYS = {k: m for k, m, kind, _ in build_lyre21("风物之诗琴").keys}


# ---------------------------------------------------------------- 音色
def _load_sample():
    path = os.path.join(HERE, "web_test7.wav")
    wf = wave.open(path, "rb")
    x = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float64) / 32767
    i0 = int(np.nonzero(np.abs(x) > 3e-4)[0][0])
    s = x[i0:i0 + 4 * SR].copy()
    s *= 0.45 / np.abs(s).max()
    fade = int(0.2 * SR)
    s[-fade:] *= np.linspace(1, 0, fade)
    return s


_SAMPLE = None


def lyre_voice(midi, n_total):
    """采样移调：C4 原样，其余按 2^(Δ/12) 重采样"""
    global _SAMPLE
    if _SAMPLE is None:
        _SAMPLE = _load_sample()
    r = 2.0 ** ((midi - 60) / 12.0)
    n = min(n_total, int(len(_SAMPLE) / r) - 1)
    pos = np.arange(n) * r
    return np.interp(pos, np.arange(len(_SAMPLE)), _SAMPLE)


def synth_voice(midi, dur):
    f0 = 440.0 * 2 ** ((midi - 69) / 12.0)
    t = np.arange(int(dur * SR)) / SR
    sig = sum(a * np.sin(2 * np.pi * f0 * k * t) for k, a in ((1, 1.0), (2, 0.45), (3, 0.2), (4, 0.1)))
    return 0.5 * sig * np.exp(-4.0 * t)


def horn_voice(midi, hold, rel=0.04):
    f0 = 440.0 * 2 ** ((midi - 69) / 12.0)
    n = int((hold + 8 * rel) * SR)
    t = np.arange(n) / SR
    env = np.minimum(1.0, t / 0.025) * np.exp(-0.6 * t)
    env = np.where(t < hold, env, env * np.exp(-(t - hold) / rel))
    sig = sum(a * np.sin(2 * np.pi * f0 * k * t + k) for k, a in
              ((1, 1.0), (2, 0.55), (3, 0.35), (4, 0.18), (5, 0.1)))
    return 0.3 * sig * env


def render(notes, timbre, mode="ring", tail=1.5, noise_db=-72.0, seed=0, steal=True):
    """notes: [(t_on, hold, midi)] → (audio, truth)
    truth: [(t_on, dur_true_or_None, midi)]
    steal=True：同键再次按下时旧发声 10 ms 内淡出（采样器常见的同键换声部）；
    steal=False：旧发声继续衰减、新发声叠加（检验重触发在干涉下的鲁棒性）"""
    end = max(t + h for t, h, _ in notes) + tail + (4.0 if timbre == "lyre" else 0.5)
    out = np.zeros(int(end * SR))
    truth = []
    by_key = {}
    for t_on, hold, midi in sorted(notes):
        by_key.setdefault(midi, []).append((t_on, hold))
    for midi, lst in by_key.items():
        for idx, (t_on, hold) in enumerate(lst):
            nxt = lst[idx + 1][0] if idx + 1 < len(lst) else None
            i0 = int(round(t_on * SR))
            if timbre == "synth":
                v = synth_voice(midi, hold)
                dur_true = hold
            elif timbre == "horn":
                v = horn_voice(midi, hold)
                dur_true = hold
            else:
                v = lyre_voice(midi, len(out) - i0)
                if mode == "damp":
                    tt = np.arange(len(v)) / SR
                    v = v * np.where(tt < hold, 1.0, np.exp(-(tt - hold) / 0.03))
                    dur_true = hold
                else:
                    dur_true = None
            # 同键再次按下
            if nxt is not None and steal:
                cut = int(round((nxt - t_on) * SR))
                if cut < len(v):
                    f = min(int(0.01 * SR), len(v) - cut)
                    v = v.copy()
                    v[cut:cut + f] *= np.linspace(1, 0, f)
                    v[cut + f:] = 0.0
                # 余音被同键重按截断：真值时长 = 到下一次按下为止。
                # 只在 0.65 s 内重按时计入评测——更久之后余音已被别的音掩蔽，"何时结束"在感知上不明确
                if dur_true is None:
                    dur_true = (nxt - t_on) if nxt - t_on <= 0.65 else None
                else:
                    dur_true = min(dur_true, nxt - t_on)
            elif nxt is not None and dur_true is not None:
                dur_true = min(dur_true, nxt - t_on)
            seg = v[:len(out) - i0]
            out[i0:i0 + len(seg)] += seg
            truth.append((t_on, dur_true, midi))
    rng = np.random.default_rng(seed)
    out += rng.standard_normal(len(out)) * (10 ** (noise_db / 20))
    truth.sort(key=lambda r: (r[0], r[2]))
    return out.astype(np.float32), truth


# ---------------------------------------------------------------- 序列
def seq_twinkle(ioi=0.5, hold=0.45):
    mel = [60, 60, 67, 67, 69, 69, 67, 65, 65, 64, 64, 62, 62, 60]
    lens = [1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 1, 1, 2]
    t, out = 0.5, []
    for m, L in zip(mel, lens):
        out.append((t, hold * L if L == 1 else hold + ioi, m))
        t += ioi * L
    return out


def seq_repeat(ioi=0.3, hold=0.25, n=12, midi=67):
    return [(0.5 + i * ioi, hold, midi) for i in range(n)]


def seq_score(overhead=0.008):
    """score_seq.json（脚本自动演奏实际用的序列）：keyDown→sleep(hold)→keyUp，每步固定开销"""
    seq = json.load(open(os.path.join(HERE, "score_seq.json")))
    t, out = 0.5, []
    for s in seq[:90]:
        if s["keys"]:
            for k in s["keys"]:
                out.append((t, s["hold"], LYRE_KEYS[k]))
        t += s["hold"] + overhead
    return out


def seq_human(seed=1, base=0.42, n=40):
    rng = np.random.default_rng(seed)
    scale = [60, 62, 64, 65, 67, 69, 71, 72, 74, 76]
    t, out = 0.5, []
    pattern = [1, 1, 2, 1, 1, 1, 1, 2]
    for i in range(n):
        L = pattern[i % len(pattern)]
        m = scale[int(rng.integers(0, len(scale)))]
        hold = float(rng.uniform(0.12, 0.35)) * L
        if i % 8 == 0:   # 和弦：人手先后有 0~25 ms 散布
            for j, mm in enumerate((m - 12, m - 8, m - 5)):
                if mm >= 48:
                    out.append((t + float(rng.uniform(0, 0.025)), hold, mm))
        else:
            out.append((t + float(rng.normal(0, 0.012)), hold, m))
        t += base * L
    return out


def seq_tempo_change():
    out, t = [], 0.5
    mel = [60, 64, 67, 72, 67, 64]
    for i in range(24):
        out.append((t, 0.3, mel[i % 6]))
        t += 0.6          # 100 BPM
    for i in range(30):
        out.append((t, 0.25, [62, 65, 69, 74, 69, 65][i % 6]))   # 全部为琴上可弹的白键
        t += 60 / 140.0   # 140 BPM
    return out


def seq_mixed(q=0.6):
    """四分 + 八分混合（约一半拍子被细分）"""
    out, t = [], 0.5
    pat = [(1,), (0.5, 0.5), (1,), (1,), (0.5, 0.5), (1,), (0.5, 0.5), (1,)]
    mel = [60, 62, 64, 65, 67, 65, 64, 62, 60, 64, 67]
    i = 0
    for rep in range(3):
        for beat in pat:
            for frac in beat:
                out.append((t, 0.8 * frac * q, mel[i % len(mel)]))
                t += frac * q
                i += 1
    return out


def seq_horn():
    """圆号：按住时长各不相同（演奏法：长短音交替）"""
    holds = [0.30, 0.15, 0.45, 0.20, 0.60, 0.25, 0.10, 0.35, 0.50, 0.18, 0.28, 0.40]
    mel = [72, 74, 76, 77, 79, 77, 76, 74, 72, 76, 79, 81]
    out, t = [], 0.5
    for h, m in zip(holds, mel):
        out.append((t, h, m))
        t += 0.75
    return out


CASES = [
    # name, notes, timbre, mode, instrument, bpm_true, steal
    ("synth 小星星 (IOI 0.5s, 120BPM)", seq_twinkle(), "synth", "ring", "lyre", 120.0, True),
    ("synth 同键连按 ×12 (IOI 0.3s)", seq_repeat(hold=0.28), "synth", "ring", "lyre", 200.0, True),
    ("lyre  小星星 余音 (120BPM)", seq_twinkle(), "lyre", "ring", "lyre", 120.0, True),
    ("lyre  同键连按 ×12 余音", seq_repeat(), "lyre", "ring", "lyre", 200.0, True),
    ("lyre  同键连按 ×12 叠加不截断", seq_repeat(), "lyre", "ring", "lyre", 200.0, False),
    ("lyre  松键止音 小星星", seq_twinkle(hold=0.3), "lyre", "damp", "lyre", 120.0, True),
    ("lyre  脚本谱 score_seq (和弦+连按)", seq_score(), "lyre", "ring", "lyre", 60 / 0.308, True),
    ("lyre  人手演奏 (抖动±12ms)", seq_human(), "lyre", "ring", "lyre", 60 / 0.42, True),
    ("lyre  变速 100→140", seq_tempo_change(), "lyre", "ring", "lyre", 140.0, True),
    # BPM 口径：起音周期（最常见的规则起音间隔单位），与原版及 test_detection.py 的期望一致
    ("lyre  四分+八分混合 (周期 0.3s)", seq_mixed(), "lyre", "ring", "lyre", 200.0, True),
    ("horn  圆号 按住时长各异", seq_horn(), "horn", "ring", "horn", 80.0, True),
]


# ---------------------------------------------------------------- 运行与打分
def load_detector_module(old=False):
    if not old:
        spec = importlib.util.spec_from_file_location("det_new", os.path.join(HERE, "detection.py"))
    else:
        src = subprocess.run(["git", "show", "HEAD:detection.py"], cwd=HERE, capture_output=True,
                             check=True).stdout
        path = os.path.join(tempfile.gettempdir(), "detection_head_baseline.py")
        with open(path, "wb") as f:
            f.write(src)
        spec = importlib.util.spec_from_file_location("det_old", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_detector(mod, inst, audio, sens=0.55):
    det = mod.NoteDetector(inst, sr=SR, sensitivity=sens, sim_clock=True)
    events, bpms = [], []
    n = len(audio) // BLOCK
    for i in range(n):
        r = det.feed(audio[i * BLOCK:(i + 1) * BLOCK])
        events.extend(r["note_events"])
        bpms.append(((i + 1) * BLOCK / SR, r["bpm"]))
    for _ in range(40):
        r = det.feed(np.zeros(BLOCK, dtype=np.float32))
        events.extend(r["note_events"])
    return events, bpms


def score_case(events, truth, bpms, bpm_true, tol=0.12):
    used = set()
    errs, derrs, matched = [], [], 0
    for t_on, dur, midi in truth:
        best, bi = None, None
        for i, ev in enumerate(events):
            if i in used or ev["midi"] != midi:
                continue
            dt = ev["t"] - t_on
            if abs(dt) <= tol and (best is None or abs(dt) < abs(best)):
                best, bi = dt, i
        if bi is not None:
            used.add(bi)
            matched += 1
            errs.append(best)
            if dur is not None:
                derrs.append(events[bi]["dur_ms"] / 1000.0 - dur)
    n_true, n_det = len(truth), len(events)
    rec = matched / n_true if n_true else 0
    prec = matched / n_det if n_det else 0
    f1 = 2 * rec * prec / (rec + prec) if rec + prec else 0
    # BPM：最后一个真值起音后 0.5 s 时的读数，以及后半段读数中位数
    t_last = truth[-1][0]
    t_first = truth[0][0]
    vals = [(t, b) for t, b in bpms if b is not None]
    at_end = None
    for t, b in vals:
        if t <= t_last + 0.5:
            at_end = b
    half = [b for t, b in vals if (t_first + t_last) / 2 <= t <= t_last + 0.5]
    med = float(np.median(half)) if half else None

    def pct(v):
        return None if v is None else 100.0 * (v - bpm_true) / bpm_true
    return {
        "n_true": n_true, "n_det": n_det, "recall": rec, "precision": prec, "f1": f1,
        "on_mae_ms": 1000 * float(np.mean(np.abs(errs))) if errs else None,
        "on_bias_ms": 1000 * float(np.median(errs)) if errs else None,
        "dur_mae_ms": 1000 * float(np.mean(np.abs(derrs))) if derrs else None,
        "dur_bias_ms": 1000 * float(np.median(derrs)) if derrs else None,
        "bpm_end": at_end, "bpm_end_err": pct(at_end), "bpm_med_err": pct(med),
    }


def fmt(v, f="{:6.1f}"):
    return "   —  " if v is None else f.format(v)


# ---------------------------------------------------------------- 游戏噪音场景（--noise）
def _pink(n, rng):
    X = np.fft.rfft(rng.standard_normal(n))
    f = np.arange(len(X), dtype=float)
    f[0] = 1.0
    y = np.fft.irfft(X / np.sqrt(f), n)
    return y / (np.std(y) + 1e-12)


def make_noise(n, kind, rng):
    """ambient：粉红噪声（风声/水声类稳态底噪）；sfx：每秒 ~3 个 20~120 ms 的短促音效
    （宽带噪声 + 随机频率的音调分量，指数衰减后截断）；bgm：背景音乐（每 2 s 换 3 个持续音，带谐波、淡入淡出）"""
    if kind == "ambient":
        return _pink(n, rng)
    if kind == "sfx":
        y = np.zeros(n)
        k = 0.0
        while True:
            k += rng.exponential(1 / 3.0)
            i0 = int(k * SR)
            if i0 >= n:
                break
            L = int(rng.uniform(0.02, 0.12) * SR)
            idx = np.arange(L)
            env = np.exp(-idx / (rng.uniform(0.008, 0.04) * SR))
            fc = rng.uniform(250, 3500)
            burst = (0.6 * rng.standard_normal(L)
                     + rng.uniform(0, 1) * np.sin(2 * np.pi * fc * idx / SR + rng.uniform(0, 6.28))) * env
            burst *= 10 ** (rng.uniform(-8, 0) / 20)
            y[i0:i0 + L] += burst[:n - i0]
        return y / (np.abs(y).max() + 1e-12)
    if kind == "bgm":
        y = np.zeros(n)
        seg = int(2.0 * SR)
        for s in range(0, n, seg):
            L = min(seg + int(0.4 * SR), n - s)
            tt = np.arange(L) / SR
            env = np.clip(np.minimum(tt / 0.25, (L / SR - tt) / 0.3), 0, 1)
            for _ in range(3):
                f0 = 440 * 2 ** ((rng.uniform(45, 80) - 69) / 12)
                for h, a in ((1, 1.0), (2, 0.4), (3, 0.2)):
                    y[s:s + L] += a * env * np.sin(2 * np.pi * f0 * h * tt + rng.uniform(0, 6.28))
        return y / (np.std(y) + 1e-12)
    raise ValueError(kind)


def add_noise(audio, cond, seed=7):
    """cond: [(kind, level_db)]；ambient/bgm 电平相对演奏 RMS，sfx 相对演奏峰值"""
    rng = np.random.default_rng(seed)
    x = audio.astype(np.float64)
    act = np.abs(x) > 1e-3
    rms = np.sqrt(np.mean(x[act] ** 2)) if act.any() else 0.1
    pk = np.abs(x).max()
    out = x.copy()
    for kind, lvl in cond:
        out += make_noise(len(x), kind, rng) * (pk if kind == "sfx" else rms) * 10 ** (lvl / 20)
    return out.astype(np.float32)


NOISE_CONDS = [
    ("干净", []),
    ("底噪-20dB", [("ambient", -20)]),
    ("底噪-10dB", [("ambient", -10)]),
    ("音效", [("sfx", -6)]),
    ("BGM-12dB", [("bgm", -12)]),
    ("混合", [("ambient", -20), ("sfx", -8), ("bgm", -15)]),
]
NOISE_CASES = [
    # name, notes, timbre, mode, instrument, ring(余音型：发声到同键再次按下或采样结束)
    ("lyre 松键止音", seq_twinkle(hold=0.3), "lyre", "damp", "lyre", False),
    ("horn 按住时长各异", seq_horn(), "horn", "ring", "horn", False),
    ("synth 硬截止", seq_twinkle(), "synth", "ring", "lyre", False),
    ("lyre 余音 脚本谱", seq_score(), "lyre", "ring", "lyre", True),
    ("lyre 余音 人手", seq_human(), "lyre", "ring", "lyre", True),
]


def score_noise(events, truth, ring):
    """时长模块在噪音下的"敏感度"指标：
    时长MAE —— 有真值的音（松键止音/圆号/硬截止/同键重按）的时长误差；
    碎片    —— 同一个真实音还在响，却被另开出一行（时长被切断）；
    误判截止 —— 报告"松键/截止""同键重按"，但那一刻真实声音并没有结束；
    伪音    —— 对不上任何真实音、也不是碎片的多余行（噪音被当成按键）。"""
    used, derrs, frag, false_cut, matched = set(), [], 0, 0, 0
    by_m = {}
    for t, d, m in truth:
        by_m.setdefault(m, []).append(t)

    def true_end(m, t_on):
        nxt = [t for t in by_m[m] if t > t_on + 1e-6]
        voice_end = t_on + (4.0 - 0.1) / (2.0 ** ((m - 60) / 12.0))   # 余音采样长度 4 s / 移调比
        return min(nxt[0], voice_end) if nxt else voice_end

    for t_on, dur, m in truth:
        c = [(abs(e["t"] - t_on), i) for i, e in enumerate(events)
             if i not in used and e["midi"] == m and abs(e["t"] - t_on) <= 0.06]
        if not c:
            continue
        i = min(c)[1]
        used.add(i)
        matched += 1
        e = events[i]
        if dur is not None:
            derrs.append(e["dur_ms"] - 1000 * dur)
        if ring and e["end"] in ("release", "retrig"):
            if abs(e["t"] + e["dur_ms"] / 1000 - true_end(m, t_on)) > 0.10:
                false_cut += 1
    for i, e in enumerate(events):
        if i in used:
            continue
        ts = [t for t in by_m.get(e["midi"], []) if t < e["t"] - 0.06]
        if ts and e["t"] < true_end(e["midi"], ts[-1]):
            frag += 1
    return {"recall": matched / len(truth), "dur_mae": float(np.mean(np.abs(derrs))) if derrs else None,
            "frag": frag, "extra": len(events) - matched - frag, "false_cut": false_cut, "n": len(truth)}


def main_noise(impls):
    insts = {"lyre": build_lyre21("风物之诗琴"), "horn": build_horn()}
    tot = {}
    print("用例               噪音        impl  召回  时长MAE  碎片  伪音  误判截止")
    for name, notes, timbre, mode, ik, ring in NOISE_CASES:
        audio, truth = render(notes, timbre, mode)
        for cname, cond in NOISE_CONDS:
            a = add_noise(audio, cond) if cond else audio
            for iname, mod in impls:
                evs, _ = run_detector(mod, insts[ik], a)
                s = score_noise(evs, truth, ring)
                dm = "   —  " if s["dur_mae"] is None else f"{s['dur_mae']:6.1f}"
                print(f"{name:16s} {cname:10s} {iname:4s} {s['recall']:.2f}  {dm}  {s['frag']:4d}  {s['extra']:4d}"
                      f"   {s['false_cut']:3d}/{s['n']}")
                t = tot.setdefault((iname, "干净" if not cond else "有噪音"),
                                   {"rec": [], "dur": [], "frag": 0, "extra": 0, "fc": 0, "n": 0})
                t["rec"].append(s["recall"])
                if s["dur_mae"] is not None:
                    t["dur"].append(s["dur_mae"])
                t["frag"] += s["frag"]
                t["extra"] += s["extra"]
                t["fc"] += s["false_cut"]
                t["n"] += s["n"]
    print("\n=== 汇总")
    for (iname, k), t in sorted(tot.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        print(f"  {k:4s} {iname:4s} 召回={np.mean(t['rec']):.3f}  时长MAE={np.mean(t['dur']):5.1f}ms  碎片={t['frag']:3d}"
              f"  伪音={t['extra']:3d}  误判截止={t['fc']:3d}  （真值音 {t['n']}）")


# ---------------------------------------------------------------- 频繁变速（--tempo）
QUANT = 1024 / 48000.0      # 原神音频按 1024 样本（21.3 ms）一块调度发声：起音时间落在这个网格上


def seq_segments(segments, seed=1, jitter=0.008):
    """按段生成演奏：segments = [(时长 s, 起音周期 s 或 None=停顿, 节奏型)]，节奏型为以周期为单位的音长（循环）。
    人手抖动 + 原神 21.3 ms 发声网格量化。返回 (音符, 各段 (起, 止, BPM))"""
    rng = np.random.default_rng(seed)
    mel = [60, 62, 64, 65, 67, 69, 71, 72, 74, 76, 77, 79]
    t, notes, segs = 0.5, [], []
    q0 = float(rng.uniform(0, QUANT))
    i = 0
    for dur, p, pat in segments:
        t0 = t
        segs.append((t0, t0 + dur, None if p is None else 60.0 / p))
        if p is None:
            t += dur
            continue
        j = 0
        while t < t0 + dur - 1e-9:
            L = pat[j % len(pat)]
            ton = t + float(rng.normal(0, jitter))
            ton = q0 + round((ton - q0) / QUANT) * QUANT
            notes.append((ton, min(0.3, 0.8 * L * p), mel[(i * 5) % len(mel)]))
            t += L * p
            i += 1
            j += 1
    return notes, segs


TEMPO_CASES = [
    ("频繁变速（仿实际演奏）", [(6, 0.213, [1]), (4, 0.14, [1]), (5, 0.085, [1]), (3, None, None),
                       (6, 0.245, [1, 1, 2]), (3, 0.12, [1]), (4, 0.17, [1, 1, 1, 2]), (8, 0.30, [1, 2, 1]),
                       (4, 0.17, [1]), (4, 0.15, [1, 1, 2]), (4, 0.21, [1]), (4, 0.23, [1, 2])]),
    ("整数倍变速 200→400→200→100→200", [(6, 0.30, [1]), (5, 0.15, [1]), (5, 0.30, [1]), (6, 0.60, [1]), (6, 0.30, [1])]),
    ("渐变 100→160→90", [(1.2, 0.6 - 0.025 * k, [1]) for k in range(9)] +
                      [(1.2, 0.375 + 0.03 * k, [1]) for k in range(10)]),
    ("稳定速度 四分+八分混合", [(24, 0.30, [2, 1, 1, 2, 2, 1, 1, 2])]),
]


def main_tempo(impls):
    """BPM 跟随变速的速度：每段从开始到读数进入并保持在真值 ±5% 内的时间（"跟上"），
    以及允许 1 s 固有延迟时读数在 ±5% 内的时间占比；稳定速度用例看读数是否乱跳"""
    lyre = build_lyre21("风物之诗琴")
    for name, segments in TEMPO_CASES:
        notes, segs = seq_segments(segments)
        audio, _ = render(notes, "lyre", "ring")
        print(f"\n=== {name}")
        rows = {}
        for iname, mod in impls:
            _, bpms = run_detector(mod, lyre, audio)
            settle, within, n_all = [], 0, 0
            for a, b, bpm in segs:
                if bpm is None:
                    continue
                ts = [(t, v) for t, v in bpms if a <= t < b]
                st = None
                for k, (t, v) in enumerate(ts):
                    if all(vv is not None and abs(vv / bpm - 1) <= 0.05 for _, vv in ts[k:]):
                        st = t - a
                        break
                settle.append(st)
                for t, v in bpms:
                    if a <= t - 1.0 < b:
                        n_all += 1
                        within += int(v is not None and abs(v / bpm - 1) <= 0.05)
            jumps = sum(1 for (_, v0), (_, v1) in zip(bpms, bpms[1:])
                        if v0 is not None and v1 is not None and abs(v1 / v0 - 1) > 0.10)
            rows[iname] = (settle, 100.0 * within / max(1, n_all), jumps)
        print("  段（BPM）      " + "   ".join(f"{iname:>8s}" for iname in rows))
        for k, (a, b, bpm) in enumerate([s for s in segs if s[2] is not None]):
            cells = []
            for iname in rows:
                st = rows[iname][0][k]
                cells.append("  未跟上 " if st is None else f"{st:6.1f} s")
            print(f"  {a:5.1f}-{b:5.1f}s {bpm:6.1f}   " + "   ".join(cells))
        for iname, (_, w, j) in rows.items():
            print(f"  {iname:4s} 读数在 ±5% 内（容许 1 s 延迟）{w:5.1f}%   跳变（>10%）{j} 次")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", action="store_true", help="同时评测 git HEAD 版本")
    ap.add_argument("--only", default="", help="只跑名称包含该子串的用例")
    ap.add_argument("--noise", action="store_true", help="游戏噪音场景（底噪/音效/背景音乐）下时长模块的敏感度")
    ap.add_argument("--tempo", action="store_true", help="频繁变速：BPM 读数多快跟上新速度、稳定时是否乱跳")
    args = ap.parse_args()
    impls = [("new", load_detector_module(False))]
    if args.old:
        impls.insert(0, ("old", load_detector_module(True)))
    if args.noise:
        main_noise(impls)
        return
    if args.tempo:
        main_tempo(impls)
        return
    insts = {"lyre": build_lyre21("风物之诗琴"), "horn": build_horn()}
    summary = {name: [] for name, _ in impls}
    for name, notes, timbre, mode, inst_key, bpm_true, steal in CASES:
        if args.only and args.only not in name:
            continue
        audio, truth = render(notes, timbre, mode, steal=steal)
        print(f"\n=== {name}   (真值 {len(truth)} 音, BPM {bpm_true:.1f})")
        print("  impl  召回  精确   F1   起音MAE 起音偏差  时长MAE 时长偏差   BPM末值  末值误差% 中位误差%")
        for iname, mod in impls:
            evs, bpms = run_detector(mod, insts[inst_key], audio)
            s = score_case(evs, truth, bpms, bpm_true)
            summary[iname].append(s)
            print(f"  {iname:4s} {s['recall']:5.2f} {s['precision']:5.2f} {s['f1']:5.2f}"
                  f"  {fmt(s['on_mae_ms'])}  {fmt(s['on_bias_ms'], '{:+6.1f}')}"
                  f"   {fmt(s['dur_mae_ms'])}  {fmt(s['dur_bias_ms'], '{:+6.1f}')}"
                  f"   {fmt(s['bpm_end'], '{:7.1f}')}  {fmt(s['bpm_end_err'], '{:+7.2f}')}"
                  f"  {fmt(s['bpm_med_err'], '{:+7.2f}')}")
    print("\n=== 汇总（各用例平均）")
    for iname, rows in summary.items():
        def avg(key, absval=False):
            v = [abs(r[key]) if absval else r[key] for r in rows if r[key] is not None]
            return float(np.mean(v)) if v else None
        print(f"  {iname:4s} F1={avg('f1'):.3f}  起音MAE={fmt(avg('on_mae_ms'))}ms"
              f"  时长MAE={fmt(avg('dur_mae_ms'))}ms  |BPM末值误差|={fmt(avg('bpm_end_err', True), '{:.2f}')}%"
              f"  |BPM中位误差|={fmt(avg('bpm_med_err', True), '{:.2f}')}%")


if __name__ == "__main__":
    main()
