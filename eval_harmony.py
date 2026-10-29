# -*- coding: utf-8 -*-
"""和弦 / 调性算法评测（与 git HEAD 版本对比）

为了只比较和弦/调性逻辑本身（不受音高检测误差影响），直接把已知的音符按时间放进检测器的音符记录：
每个音在起音后约 90 ms 被"确认"（与真实检测的确认延迟相当），琴类余音 2.5 s / 圆号 1 s 后结束。
指标：
  和弦准确 —— 每段开始 0.3 s 之后，显示的和弦（去掉转位）与真值一致的时间占比；单音旋律的真值是"无和弦"；
  和弦变化次数 —— 越接近真值的和弦变化次数越好（多出来的就是闪烁）；
  调性正确 —— 4 s 之后显示的调与真值一致的时间占比；调性变化次数。
用法：python eval_harmony.py
"""
import numpy as np

import benchmark_timing as B
from instruments import build_lyre21, build_horn

OPEN_DELAY = 0.09      # 检测器确认一个音约需 4 帧
STEP = 0.05


def block(seq, dur, start=0.5):
    """[(和弦名, (midi...)), ...] 每个和弦 dur 秒，同时按下"""
    notes, segs, t = [], [], start
    for name, ms in seq:
        for m in ms:
            notes.append((t, m))
        segs.append((t, t + dur, name))
        t += dur
    return notes, segs


def arpeggio(seq, dur, start=0.5, step=0.3):
    """低音 + 分解三和弦"""
    notes, segs, t = [], [], start
    for name, bass, tri in seq:
        notes.append((t, bass))
        for j, m in enumerate(tri + (tri[1],)):
            notes.append((t + step * j, m))
        segs.append((t, t + dur, name))
        t += dur
    return notes, segs


def melody(ms, ioi, start=0.5):
    notes = [(start + i * ioi, m) for i, m in enumerate(ms)]
    return notes, [(start, start + len(ms) * ioi, "")]


def chords_with_melody(seq, dur, mel_per_bar, start=0.5):
    """每小节开头按下和弦（低音 + 三和弦），小节内再弹 4 个旋律音"""
    notes, segs, t = [], [], start
    for (name, ms), mel in zip(seq, mel_per_bar):
        for m in ms:
            notes.append((t, m))
        for j, m in enumerate(mel):
            notes.append((t + dur * (j + 1) / (len(mel) + 1), m))
        segs.append((t, t + dur, name))
        t += dur
    return notes, segs


C, Am, F, G, Dm, Em, G7 = ((48, 52, 55), (57, 60, 64), (53, 57, 60), (55, 59, 62), (50, 53, 57), (52, 55, 59), (55, 59, 62, 65))
CASES = [
    ("柱式和弦 C-Am-F-G ×2", *block([("C", C), ("Am", Am), ("F", F), ("G", G)] * 2, 1.2), "C 大调", "lyre", 0.3),
    ("分解和弦 C-G-Am-F ×2", *arpeggio([("C", 48, (60, 64, 67)), ("G", 55, (59, 62, 67)), ("Am", 57, (60, 64, 69)),
                                     ("F", 53, (60, 65, 69))] * 2, 1.2), "C 大调", "lyre", 0.3),
    ("和弦 + 旋律 C-Am-F-G ×2", *chords_with_melody([("C", (48,) + C[1:] ), ("Am", (45 + 12,) + (60, 64)), ("F", F), ("G", G)] * 2, 1.6,
                                                [(64, 62, 60, 62), (64, 64, 62, 60), (65, 64, 62, 60), (62, 64, 65, 67)] * 2),
     "C 大调", "lyre", 0.32),
    ("小调柱式 Am-Dm-Em-Am ×2", *block([("Am", (45 + 12, 60, 64)), ("Dm", Dm), ("Em", Em), ("Am", (45 + 12, 60, 64))] * 2, 1.2),
     "A 小调", "lyre", 0.3),
    ("C 大调音阶（单音旋律）", *melody([60, 62, 64, 65, 67, 69, 71, 72, 71, 69, 67, 65, 64, 62, 60] * 2, 0.3), "C 大调", "lyre", 0.3),
    ("小星星（单音旋律）", *melody([60, 60, 67, 67, 69, 69, 67, 65, 65, 64, 64, 62, 62, 60] * 2, 0.45), "C 大调", "lyre", 0.45),
    ("A 小调旋律（单音）", *melody([69, 72, 76, 74, 72, 71, 69, 64, 69, 71, 72, 74, 76, 72, 71, 69, 57, 69] * 2, 0.35),
     "A 小调", "lyre", 0.35),
    ("圆号柱式 C-F-G7-C", *block([("C", (60, 64, 67)), ("F", (65, 69, 72)), ("G7", (67, 71, 74, 77)), ("C", (60, 64, 67))] * 2, 1.2),
     "C 大调", "horn", 0.3),
]


def evaluate(mod, notes, segs, key_truth, inst_key, period, ring=2.5):
    inst = build_lyre21("x") if inst_key == "lyre" else build_horn()
    det = mod.NoteDetector(inst, sr=48000, sensitivity=0.55, sim_clock=True)
    det._bpm_P = period
    notes = sorted(notes)
    t_end = max(b for a, b, _ in segs) + 0.5
    ends = []
    for i, (t, m) in enumerate(notes):
        nxt = [u for u, mm in notes[i + 1:] if mm == m]
        e = t + (1.0 if inst_key == "horn" else ring)
        if nxt:
            e = min(e, nxt[0])
        ends.append(e)
    opened = [False] * len(notes)
    entries = [None] * len(notes)
    chords, keys = [], []
    t = 0.0
    while t < t_end:
        t += STEP
        det._n_in = int(round(t * 48000))
        for i, (ts, m) in enumerate(notes):
            if not opened[i] and t >= ts + OPEN_DELAY:
                opened[i] = True
                ent = [ts, m, 0.0, 1.0]
                entries[i] = ent
                det.chroma_note_log.append(ent)
                det.active[m] = {"start": ts, "amp": 1.0, "chroma": ent}
            if opened[i] and entries[i] is not None and t >= ends[i]:
                entries[i][2] = 1000.0 * (ends[i] - ts)
                if det.active.get(m, {}).get("chroma") is entries[i]:
                    det.active.pop(m, None)
                entries[i] = None
        chords.append((t, det._current_chord_text()))
        keys.append((t, det._current_tonality_text()))
    # 和弦准确率：每段开始 0.3 s 之后
    ok = n = 0
    for tt, c in chords:
        for a, b, name in segs:
            if a + 0.3 <= tt < b:
                shown = c.split("（")[0].split("/")[0]
                ok += int(shown == name)
                n += 1
    changes = sum(1 for (_, c0), (_, c1) in zip(chords, chords[1:]) if c0 != c1)
    t4 = 4.0
    kk = [(tt, k.split("（")[0]) for tt, k in keys if tt >= t4]
    k_ok = 100.0 * np.mean([k == key_truth for _, k in kk]) if kk else 0.0
    k_changes = sum(1 for (_, k0), (_, k1) in zip(keys, keys[1:]) if k0.split("（")[0] != k1.split("（")[0])
    return 100.0 * ok / max(1, n), changes, k_ok, k_changes, keys[-1][1]


if __name__ == "__main__":
    mods = {"old": B.load_detector_module(True), "new": B.load_detector_module(False)}
    exp_changes = lambda segs: sum(1 for (_, _, a), (_, _, b) in zip(segs, segs[1:]) if a != b) + (1 if segs[0][2] else 0)
    print(f"{'用例':22s} | {'old 和弦准确/变化次数':>20s} {'调性正确/变化':>14s} | {'new 和弦准确/变化次数':>20s} {'调性正确/变化':>14s} | 结尾调性(new)")
    tot = {k: [] for k in mods}
    for name, notes, segs, key_truth, inst, period in CASES:
        cells = []
        last = ""
        for k, mod in mods.items():
            acc, ch, kacc, kch, klast = evaluate(mod, notes, segs, key_truth, inst, period)
            tot[k].append((acc, kacc))
            cells.append(f"{acc:6.1f}% / {ch:3d}次     {kacc:6.1f}% / {kch:2d}次")
            last = klast
        print(f"{name:22s} | {cells[0]} | {cells[1]} | {last}   （真值 {key_truth}，和弦应变化约 {exp_changes(segs)} 次）")
    for k, rows in tot.items():
        a = np.array(rows)
        print(f"平均 {k}: 和弦准确 {a[:, 0].mean():.1f}%   调性正确 {a[:, 1].mean():.1f}%")
