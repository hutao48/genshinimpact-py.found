# -*- coding: utf-8 -*-
"""边界值排查评测：合成演奏走完整流程（渲染 → NoteDetector → Screener），看该报的报没报、不该报的有没有误报。

  1) 大和弦计数：同时按下 N 个键（诗琴 / 圆号），估计键数与是否报"超过 10 个"；和弦后面紧跟旋律时；有游戏噪音时
  2) 机械等间隔：脚本式轮指（时刻精确，经 21.33 ms 发声块量化）与人手轮指（计时模型 + 量化）
  3) 真实录音：不应有任何"超出人手极限"
用法：python eval_screening.py [--quick] [--only chords|regular|real]
"""
import os
import sys
import wave

import numpy as np

import benchmark_timing as B
import detection as D
from instruments import build_lyre21, build_horn
from screening import Screener, regular_need, Q_BLOCK

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 48000
QUICK = "--quick" in sys.argv
ONLY = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else ""


def run(audio, inst):
    det = D.NoteDetector(inst, sr=SR, sensitivity=0.55, sim_clock=True)
    scr = Screener(inst, sr=SR)
    found = {}
    blk = 2048
    for i in range(0, len(audio) - blk + 1, blk):
        b = audio[i:i + blk]
        det.feed(b)
        for f in scr.process(b, det):
            found[f["id"]] = f
    z = np.zeros(blk, dtype=np.float32)
    for _ in range(int(1.0 * SR / blk)):
        det.feed(z)
        for f in scr.process(z, det):
            found[f["id"]] = f
    for f in scr.process(z, det, final=True):
        found[f["id"]] = f
    return scr, list(found.values())


def grid(t, ph):
    """按键时刻 → 游戏发声时刻（下一个 21.33 ms 发声块）"""
    return np.ceil((np.asarray(t) - ph) / Q_BLOCK) * Q_BLOCK + ph


def chords_case(inst_key, N, rng, follow=None):
    inst = build_lyre21("风物之诗琴") if inst_key == "lyre" else build_horn()
    midis = inst.valid_midis()
    ph = rng.uniform(0, Q_BLOCK)
    notes, truth = [], []
    t = 0.5
    for i in range(10):
        notes.append((float(grid([t], ph)[0]), 0.3, int(rng.choice(midis))))
        t += 0.45
    t += 0.4
    for _ in range(3):
        keys = sorted(int(m) for m in rng.choice(midis, N, replace=False))
        tg = float(grid([t], ph)[0])
        for m in keys:
            notes.append((tg, 0.8, m))
        truth.append((tg, keys))
        if follow:
            for j in range(1, 4):
                notes.append((float(grid([t + follow * j], ph)[0]), 0.2, int(rng.choice(midis))))
        t += 1.6
    audio, _ = B.render(notes, inst_key, "ring")
    return inst, audio.astype(np.float32), truth


def human_times(n, p, rng, cv_c=0.025, sd_m=0.003, sd_drift=0.015, rho=0.9):
    d = np.zeros(n)
    for j in range(1, n):
        d[j] = rho * d[j - 1] + rng.normal(0, sd_drift * np.sqrt(1 - rho * rho))
    return 0.8 + np.cumsum(p * (1 + d) + rng.normal(0, cv_c * p, n)) + rng.normal(0, sd_m, n)


def tremolo_case(p, n, kind, rng):
    inst = build_lyre21("风物之诗琴")
    ph = rng.uniform(0, Q_BLOCK)
    if kind == "script":
        t = 0.8 + np.arange(n) * p + rng.uniform(-0.0005, 0.0005, n)
    else:
        t = human_times(n, p, rng, **({} if kind == "steady" else dict(cv_c=0.04, sd_m=0.005, sd_drift=0.03)))
    tg = grid(t, ph)
    keys = [67, 72, 71, 72]             # G4 C5 B4 C5 …（轮指）
    notes = [(float(x), min(0.25, 0.8 * p), keys[i % len(keys)]) for i, x in enumerate(tg)]
    audio, _ = B.render(notes, "lyre", "ring")
    return inst, audio.astype(np.float32)


def load_wav(path):
    with wave.open(path) as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def main():
    rng = np.random.default_rng(5)
    if ONLY in ("", "chords"):
        part_chords(rng)
    if ONLY in ("", "regular"):
        part_regular(rng)
    if ONLY in ("", "real"):
        part_real()


def part_chords(rng):
    trials = 2 if QUICK else 4
    print("=== 1) 大和弦：每个用例 3 次同时按下 ×", trials, "组（先弹 10 个单音，供学习音色的谐波）")
    print("  乐器  条件         真实键数 → 估计键数（每次按下）                        报出\"超过 10 个\"")
    fp = det_ = tot_lo = tot_hi = 0
    for inst_key in ("lyre", "horn"):
        for follow, label in ((None, "单独"), (0.15, "后接旋律")):
            for N in (4, 6, 8, 9, 10, 11, 12, 14):
                if inst_key == "horn" and N > 14:
                    continue
                ests, flags, sure = [], 0, 0
                for _ in range(trials):
                    inst, audio, truth = chords_case(inst_key, N, rng, follow)
                    scr, found = run(audio, inst)
                    for t0, keys in truth:
                        e = [b[1] for b in scr.burst_log if abs(b[0] - t0) < 0.05]
                        ests.append(e[0] if e else None)
                    flags += sum(1 for f in found if f["kind"] == "keys")
                    sure += sum(1 for f in found if f["kind"] == "keys" and f["level"] == "limit")
                n_ev = 3 * trials
                if N <= 10:
                    fp += flags
                    tot_lo += n_ev
                else:
                    det_ += flags
                    tot_hi += n_ev
                print(f"  {inst_key:5s} {label:8s} {N:2d} → {ests}   {flags}/{n_ev}（其中超出人手极限 {sure}）", flush=True)
    print(f"  合计：≤10 键报出 {fp}/{tot_lo}；≥11 键报出 {det_}/{tot_hi}", flush=True)


def part_regular(rng):
    print("\n=== 2) 机械等间隔（轮指 G4 C5 B4 C5…，长度 = 该速度所需最少音数 ×2：快速轮指里检测器会漏掉一部分起音）")
    print("  周期   需要   轮指音数  检出起音   脚本检出   很稳的人误报   一般的人误报")
    for p in (0.07, 0.09, 0.12, 0.16, 0.2, 0.3, 0.45, 0.7):
        need = regular_need(p)
        if need is None:
            print(f"  {p*1000:4.0f}ms  —  （这个速度不判断）")
            continue
        n = 2 * need
        res = {}
        frac = []
        for kind in ("script", "steady", "normal"):
            hit = 0
            k_tr = (2 if QUICK else 4) if kind == "script" else (3 if QUICK else 8)
            for _ in range(k_tr):
                inst, audio = tremolo_case(p, n, kind, rng)
                scr, found = run(audio, inst)
                hit += int(any(f["kind"] == "regular" for f in found))
                if kind == "script":
                    frac.append(scr.longest_regular[0])
            res[kind] = f"{hit}/{k_tr}"
        print(f"  {p*1000:4.0f}ms  {need:3d}    {n:4d}   最长段{max(frac):4d}    {res['script']:>5s}       {res['steady']:>5s}"
              f"         {res['normal']:>5s}", flush=True)


def part_real():
    print("\n=== 3) 真实录音（不应报出\"超出人手极限\"）")
    files = [os.path.join(HERE, f) for f in ("web_test1.wav", "web_test3.wav", "web_test5.wav", "web_test8.wav",
                                             "v2_lowhigh.wav", "score_test.wav")]
    extra = os.path.join(os.environ.get("TEMP", ""), "gid_bpm", "rec.wav")
    if os.path.exists(extra):
        files.append(extra)
    for path in files:
        if not os.path.exists(path):
            continue
        x, sr = load_wav(path)
        inst = build_lyre21("风物之诗琴")
        det = D.NoteDetector(inst, sr=sr, sensitivity=0.55, sim_clock=True)
        scr = Screener(inst, sr=sr)
        found = {}
        for i in range(0, len(x) - 2047, 2048):
            b = x[i:i + 2048]
            det.feed(b)
            for f in scr.process(b, det):
                found[f["id"]] = f
        z = np.zeros(2048, dtype=np.float32)
        for _ in range(24):
            det.feed(z)
            for f in scr.process(z, det):
                found[f["id"]] = f
        for f in scr.process(z, det, final=True):
            found[f["id"]] = f
        print(f"  {os.path.basename(path):16s} 发现 {len(found)} 处   {scr.summary()}")
        for f in found.values():
            print(f"      {f['t']:7.2f}s  {f['title']}")


if __name__ == "__main__":
    main()
