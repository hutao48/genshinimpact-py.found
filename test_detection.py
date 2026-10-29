# -*- coding: utf-8 -*-
"""用合成音频验证检测引擎：音符、音长、BPM、调性、和弦（带断言的回归测试）

期望值说明：
  play_sequence 每个音合成 dur 秒（硬截止）后再接 0.02 s 静音，
  所以 起音间隔 IOI = dur + 0.02，BPM 期望 = 60 / IOI（例：0.45 s 音 → 0.47 s → 127.7 BPM）；
  每个音的时长期望 = dur。
"""
import sys
import numpy as np
from instruments import build_lyre21, build_horn, build_youko
from detection import NoteDetector
from screening import Screener

SR = 48000
GAP = 0.02


def synth_note(midi, dur_s, sr=SR, amp=0.5, decay=4.0):
    """模拟拨弦音：基频 + 前几个谐波 + 指数衰减"""
    f0 = 440.0 * 2 ** ((midi - 69) / 12.0)
    t = np.arange(int(dur_s * sr)) / sr
    env = np.exp(-decay * t)
    sig = np.zeros_like(t)
    for k, a in [(1, 1.0), (2, 0.45), (3, 0.2), (4, 0.1)]:
        sig += a * np.sin(2 * np.pi * f0 * k * t)
    return (amp * sig * env).astype(np.float32)


def play_sequence(events, sr=SR):
    """events: [(midi_or_list, dur_s)] → 连续音频（每音后接 GAP 秒静音）"""
    chunks = []
    for notes, dur in events:
        if isinstance(notes, int):
            notes = [notes]
        n = max(len(synth_note(m, dur)) for m in notes)
        mix = np.zeros(n, dtype=np.float32)
        for m in notes:
            s = synth_note(m, dur)
            mix[:len(s)] += s
        g = np.zeros(int(GAP * sr), dtype=np.float32)
        chunks += [mix, g]
    return np.concatenate(chunks)


def run_test(name, inst, events, expect_bpm=None, mono=True):
    det = NoteDetector(inst, sr=SR, sensitivity=0.6, sim_clock=True)
    audio = play_sequence(events)
    notes_detected = []
    bpm_vals = []
    block = 2048
    for i in range(0, len(audio) - block, block):
        res = det.feed(audio[i:i + block])
        notes_detected.extend(res["note_events"])
        if res["bpm"]:
            bpm_vals.append(res["bpm"])
    # 收尾（喂足够静音让所有音符落音）
    res = det.feed(np.zeros(int(1.0 * SR), dtype=np.float32))
    notes_detected.extend(res["note_events"])
    notes_detected.sort(key=lambda e: e["t"])

    print(f"\n===== {name} =====")
    seq = " ".join(f"{ev['key']}({ev['name']},{ev['dur_ms']:.0f}ms)" for ev in notes_detected)
    print("检测到的音符序列:", seq[:400])
    problems = []

    # 期望起音时刻与时长
    t, exp = 0.0, []
    for notes, dur in events:
        for m in ([notes] if isinstance(notes, int) else notes):
            exp.append((t, m, dur))
        t += dur + GAP
    errs_t, errs_d, missing = [], [], 0
    for t0, m, dur in exp:
        cands = [e for e in notes_detected if e["midi"] == m and abs(e["t"] - t0) < 0.06]
        if not cands:
            missing += 1
            continue
        e = min(cands, key=lambda e: abs(e["t"] - t0))
        errs_t.append(1000 * (e["t"] - t0))
        errs_d.append(e["dur_ms"] - 1000 * dur)
    if errs_d:
        print(f"起音误差 中位 {np.median(np.abs(errs_t)):.1f} ms｜时长误差 中位 {np.median(np.abs(errs_d)):.1f} ms"
              f"（最大 {np.max(np.abs(errs_d)):.0f} ms）｜漏检 {missing}/{len(exp)}")
    if missing:
        problems.append(f"{name}：漏检 {missing} 个音")
    if errs_d and np.median(np.abs(errs_d)) > 15.0:
        problems.append(f"{name}：时长中位误差 {np.median(np.abs(errs_d)):.1f} ms > 15 ms")
    if mono and len(notes_detected) != len(exp):
        problems.append(f"{name}：检出 {len(notes_detected)} 个音，应为 {len(exp)} 个（同键连按须拆开）")

    if bpm_vals:
        msg = f"BPM 估计: {bpm_vals[-1]:.1f}"
        if expect_bpm:
            err = 100.0 * (bpm_vals[-1] - expect_bpm) / expect_bpm
            msg += f"（期望 {expect_bpm:.1f}，误差 {err:+.2f}%）"
            if abs(err) > 1.0:
                problems.append(f"{name}：BPM 误差 {err:+.2f}% > 1%")
        print(msg)
    else:
        print("BPM 估计: 无")
        if expect_bpm:
            problems.append(f"{name}：没有给出 BPM")
    print("调性:", det._current_tonality_text())
    for p in problems:
        print("  ✗", p)
    return problems


def run_screen_test(name, inst, audio, expect):
    """边界值排查：expect = 应报出的发现类型集合（"keys" 同时按键 / "regular" 机械等间隔），空集合 = 不应有任何发现"""
    det = NoteDetector(inst, sr=SR, sensitivity=0.6, sim_clock=True)
    scr = Screener(inst, sr=SR)
    found = {}
    blk = 2048
    audio = np.concatenate([audio, np.zeros(SR, dtype=np.float32)])
    for i in range(0, len(audio) - blk + 1, blk):
        x = audio[i:i + blk]
        det.feed(x)
        for f in scr.process(x, det):
            found[f["id"]] = f
    for f in scr.process(np.zeros(0, dtype=np.float32), det, final=True):
        found[f["id"]] = f
    kinds = {f["kind"] for f in found.values()}
    print(f"\n===== {name} =====")
    print("排查:", scr.summary())
    for f in found.values():
        print(f"  {f['t']:.2f}s {f['title']}")
    if kinds != set(expect):
        return [f"{name}: 期望 {sorted(expect) or '无发现'}，实际 {sorted(kinds) or '无发现'}"]
    return []


if __name__ == "__main__":
    failed = []
    lyre = build_lyre21("风物之诗琴")
    # ---- 风物之诗琴：C 大调旋律（含同键连按 C4 C4），0.45 s 音 → IOI 0.47 s
    ev = [(m, 0.45) for m in [60, 62, 64, 60, 60, 62, 64, 60, 64, 65, 67]]
    failed += run_test("风物之诗琴 旋律含连按 (IOI 0.47s → 127.7 BPM)", lyre, ev, 60 / 0.47)

    # ---- 和弦测试：悠可琴（C / Am / Dm，均在 C4~B5 音域内；只检查和弦音是否齐全）
    youko = build_youko()
    ev = [([60, 64, 67], 0.6), ([60, 64, 69], 0.6), ([62, 65, 69], 0.6)]
    failed += run_test("悠可琴 三和弦(C, Am, Dm)", youko, ev, None, mono=False)

    # ---- 调性测试：A 小调旋律（A G F E D E G）
    ev = [(69, 0.4), (67, 0.4), (65, 0.4), (64, 0.4), (62, 0.4), (64, 0.4), (67, 0.8)]
    failed += run_test("A小调音阶片段 (IOI 0.42s → 142.9 BPM)", lyre, ev, 60 / 0.42)

    # ---- 晚风圆号测试
    horn = build_horn()
    ev = [(72, 0.3), (74, 0.3), (76, 0.3), (77, 0.3), (79, 0.3), (77, 0.3), (76, 0.3), (74, 0.3)]
    failed += run_test("晚风圆号 上行+下行 (IOI 0.32s → 187.5 BPM)", horn, ev, 60 / 0.32)

    # ---- BPM 精确测试：同一键连按 12 次，0.42 s 音 → IOI 0.44 s
    ev = [(60, 0.42)] * 12
    failed += run_test("同键连按 ×12 (IOI 0.44s → 136.4 BPM)", lyre, ev, 60 / 0.44)

    # ---- 边界值排查：先弹 10 个单音（学音色的谐波），再同时按下 13 个键 → 超过 10 根手指
    rng = np.random.default_rng(3)
    big = [48, 52, 55, 59, 60, 64, 67, 71, 72, 74, 76, 79, 83]
    ev = [(int(m), 0.3) for m in rng.choice(lyre.valid_midis(), 10)] + [(big, 1.2)]
    failed += run_screen_test("排查：同时按下 13 个键", lyre, play_sequence(ev), {"keys"})
    # ---- 6 个键的和弦 + 旋律：不应有任何发现
    ev = [(m, 0.3) for m in [60, 64, 67, 72, 71, 67]] + [([48, 55, 60, 64, 67, 72], 1.0)] + \
         [(m, 0.3) for m in [69, 67, 65, 64, 62, 60]]
    failed += run_screen_test("排查：6 键和弦 + 旋律（无发现）", lyre, play_sequence(ev), set())
    # ---- 精确等间隔（脚本式）40 个音 → 机械等间隔；同样的音加上人手的随机偏差 → 无发现
    ev = [([67, 72, 71, 72][i % 4], 0.2) for i in range(40)]
    failed += run_screen_test("排查：40 个音精确等间隔", lyre, play_sequence(ev), {"regular"})
    ev = [([67, 72, 71, 72][i % 4], 0.2 + float(rng.normal(0, 0.012))) for i in range(40)]
    failed += run_screen_test("排查：40 个音人手轮指（无发现）", lyre, play_sequence(ev), set())

    print("\n" + ("全部通过" if not failed else f"失败 {len(failed)} 项：\n  " + "\n  ".join(failed)))
    sys.exit(1 if failed else 0)
