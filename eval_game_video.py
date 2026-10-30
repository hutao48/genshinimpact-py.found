# -*- coding: utf-8 -*-
"""用游戏录像做"地面真值"评测：原神演奏界面上被按下的键会变色（变暗、泛青、泛黄……各乐器不同），
逐帧读出来就是真实按键；把录像的声音交给检测器，逐个对照 → 多检（检测到但没按）/ 漏检（按了没检测到）/ 谐波误检。

用法：python eval_game_video.py 录像.mp4 [乐器名] [--grid x0,y0,dx,dy] [--show] [--timbre] [--old] [--bpm] [--dur]
  输出：逐个对照的精确率 / 召回率；BPM 逐窗对照（每 4 s 的读数 vs 往前 8 s 真实按键算的拍速；--bpm 列出每个点）；
        圆号的按键时长对照（键面在按住期间一直变色；--dur 对其它乐器也算，但琴类读不出按了多久）。
  --grid    最上面一排第一个键（Q）的圆心坐标与水平 / 竖直间距（像素，按录像分辨率）。
            默认 133,403,69.6,58（1280×720 录像、游戏窗口在左上角时）。
            晚风圆号只有两排（QWERTYU / ASDFGHJ）；悠可琴最上面一排是和弦键（不计入，和弦键附近的检测也不算多检）。
  --timbre  另外统计"单独按下"（前后 0.45 s 内没有别的按键）的音的各次谐波电平（分低 / 中 / 高音区），
            用于给 detection.TIMBRES 填实测音色。
  --old     同时评测 git HEAD 版本的检测器做对比。
需要 ffmpeg（在 PATH 里，或 D:\\ffmpeg\\bin\\ffmpeg.exe）。逐帧颜色会缓存在临时目录里，重复评测很快。
"""
import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from collections import Counter

import numpy as np

import detection as D
from instruments import all_instruments

FF = shutil.which("ffmpeg") or r"D:\ffmpeg\bin\ffmpeg.exe"
FP = shutil.which("ffprobe") or r"D:\ffmpeg\bin\ffprobe.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(tempfile.gettempdir(), "gid_gt_cache")


def layout(inst_name):
    """各排键位（从上到下）与是否为和弦键排"""
    if inst_name == "晚风圆号":
        return [("QWERTYU", False), ("ASDFGHJ", False)]
    if inst_name == "悠可琴":
        return [("QWERTYU", True), ("ASDFGHJ", False), ("ZXCVBNM", False)]
    return [("QWERTYU", False), ("ASDFGHJ", False), ("ZXCVBNM", False)]


def key_colors(video, rows, x0, y0, dx, dy):
    """逐帧各键圆内平均颜色 → (帧数 × 键数 × 3, 键名, 是否和弦键, 帧率)"""
    tag = hashlib.md5(f"{os.path.abspath(video)}|{os.path.getmtime(video)}|{rows}|{x0},{y0},{dx},{dy}|rgb".encode()).hexdigest()
    os.makedirs(CACHE, exist_ok=True)
    cpath = os.path.join(CACHE, tag + ".npz")
    if os.path.exists(cpath):
        z = np.load(cpath)
        return z["rgb"], [str(k) for k in z["keys"]], [bool(c) for c in z["chord"]], float(z["fps"])
    X0, Y0 = int(x0 - 50) // 2 * 2, int(y0 - 40) // 2 * 2
    W = int(6 * dx + 100) // 2 * 2 + 2
    H = int((len(rows) - 1) * dy + 80) // 2 * 2 + 2           # 偶数尺寸（ffmpeg 裁剪要求）
    yy, xx = np.mgrid[0:H, 0:W]
    masks, keys, chord = [], [], []
    for r, (row, is_chord) in enumerate(rows):
        for c, k in enumerate(row):
            masks.append(np.hypot(xx - (x0 + c * dx - X0), yy - (y0 + r * dy - Y0)) <= 15)
            keys.append(k)
            chord.append(is_chord)
    proc = subprocess.Popen([FF, "-v", "error", "-i", video, "-vf", f"crop={W}:{H}:{X0}:{Y0}", "-f", "rawvideo",
                             "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    fsz = W * H * 3
    out = []
    while True:
        buf = proc.stdout.read(fsz * 64)
        if len(buf) < fsz:
            break
        n = len(buf) // fsz
        fr = np.frombuffer(buf[:n * fsz], dtype=np.uint8).reshape(n, H, W, 3).astype(np.float32)
        out.append(np.stack([fr[:, m].mean(axis=1) for m in masks], axis=1))
    proc.wait()
    rgb = np.concatenate(out, axis=0)
    rate = subprocess.run([FP, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                           "-of", "csv=p=0", video], capture_output=True, text=True).stdout.strip() or "60/1"
    num, den = (rate.split("/") + ["1"])[:2]
    fps = float(num) / float(den or 1)
    np.savez(cpath, rgb=rgb, keys=np.array(keys), chord=np.array(chord), fps=fps)
    return rgb, keys, chord, fps


def presses(rgb, keys, chord, fps, thr=22.0):
    """键面颜色偏离它平时的颜色（变暗 / 泛青 / 泛黄都算）且是突然出现的 → 一次按下。
    按下后要等颜色恢复（偏离降到阈值一半以下）才算下一次；仍在变色时只有再次骤变（> 2 倍阈值）才算重按；
    同一键 0.15 s 内的两次变色算一次（圆号按下时先闪一下、再变成按住的颜色，松键时也有动画）。
    整排键同时变色（界面淡入淡出）不算。
    → [(时刻, 键, 是否和弦键)]"""
    base = np.median(rgb, axis=0)
    d = np.linalg.norm(rgb - base[None, :, :], axis=2)          # 帧数 × 键数
    fade = (d > thr).sum(axis=1) >= 8
    out = []
    gap = int(round(0.15 * fps))          # 同一键 0.15 s 内的两次变色算一次（圆号按下时先闪一下、再变成按住的颜色）
    for j, k in enumerate(keys):
        v = d[:, j]
        on, start = False, -99
        for i in range(1, len(v)):
            rise = v[i] - v[i - 1]
            if not on:
                if v[i] > thr and rise > 0.6 * thr and not fade[max(0, i - 3):i + 4].any():
                    if i - start >= gap:
                        out.append((i / fps, k, bool(chord[j])))
                        start = i
                    on = True
            elif v[i] < 0.5 * thr:
                on = False
            elif rise > 2.0 * thr and i - start >= 6 and not fade[max(0, i - 3):i + 4].any():
                out.append((i / fps, k, bool(chord[j])))
                start = i
    return sorted(out)


def load_audio(video):
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "a.wav")
        subprocess.run([FF, "-v", "error", "-y", "-i", video, "-vn", "-ac", "1", "-ar", "48000", wav],
                       check=True, capture_output=True)
        with wave.open(wav) as w:
            sr = w.getframerate()
            x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    return x, sr


def detect(mod, x, sr, inst):
    det = mod.NoteDetector(inst, sr=sr, sensitivity=0.55, sim_clock=True)
    ev, bpm = [], []
    for i in range(0, len(x) - 2047, 2048):
        r = det.feed(x[i:i + 2048])
        ev += r["note_events"]
        bpm.append((det._now(), r["bpm"]))
    ev += det.feed(np.zeros(sr, np.float32))["note_events"]
    detect.last_events = ev
    return sorted((e["t"], e["key"], e["midi"]) for e in ev), bpm


def hold_held(rgb, keys, fps, gt, thr=22.0):
    """画面里每次按键按住了多久：从按下帧起，键面颜色一直偏离（中间 ≤3 帧的闪烁不算松开），到下一次同键按下为止。
    只有圆号的键面在按住期间一直变色（琴类按下后很快恢复，读不出按了多久）"""
    base = np.median(rgb, axis=0)
    d = np.linalg.norm(rgb - base[None, :, :], axis=2)
    out = []
    for t, k, ch in gt:
        if ch:
            continue
        j = keys.index(k)
        i0 = i = int(round(t * fps))
        nxt = min([g for g, kk, _ in gt if kk == k and g > t + 1e-6], default=1e9)
        while i < len(d) and i / fps < nxt and (d[i:i + 4, j] > 0.5 * thr).any():
            i += 1
        out.append((t, k, (i - i0) / fps))
    return out


def hold_errors(rgb, keys, chord, fps, gt, ev, off):
    """检测时长 - 画面按住时长（秒）"""
    held = hold_held(rgb, keys, fps, gt)
    err = []
    for e in ev:
        c = [(abs(e["t"] - g - off), h) for g, k, h in held if k == e["key"] and abs(e["t"] - g - off) <= 0.08]
        if c:
            err.append(e["dur_ms"] / 1000.0 - min(c)[1])
    return np.array(err) if err else None


def score(dt, gt, key_midi, off=None):
    """逐个对照 → 统计；off = 画面变色与声音之间的延迟（None 则自动取对上最多的偏移）"""
    pitch = [(g, k) for g, k, ch in gt if not ch]
    chords = [g for g, k, ch in gt if ch]
    if off is None:
        off = max((sum(1 for t, k, _ in dt if any(abs(t - g - o) <= 0.06 and gk == k for g, gk in pitch)), o)
                  for o in np.arange(-0.1, 0.6, 0.005))[1]
    used, fp, n_ok, n_chordzone = set(), [], 0, 0
    for t, k, m in dt:
        hit = [i for i, (g, gk) in enumerate(pitch) if abs(t - g - off) <= 0.08 and gk == k and i not in used]
        if hit:
            used.add(hit[0])
            n_ok += 1
            continue
        if any(abs(t - g - off) <= 0.1 for g in chords):
            n_chordzone += 1                     # 和弦键发出的音：不算多检
            continue
        fm = 440 * 2 ** ((m - 69) / 12)
        harm = [gk for g, gk in pitch if abs(t - g - off) <= 0.08 and gk in key_midi
                and (lambda r: r > 1.5 and abs(r - round(r)) < 0.06)(fm / (440 * 2 ** ((key_midi[gk] - 69) / 12)))]
        fp.append((t, k, harm))
    miss = [pitch[i] for i in range(len(pitch)) if i not in used]
    return {"off": off, "n_gt": len(pitch), "n_chord": len(chords), "n_dt": len(dt) - n_chordzone, "ok": n_ok,
            "fp": fp, "miss": miss}


def timbre_stats(x, sr, gt, key_midi, off, n=4096, iso=0.12):
    """（近似）单独按下的音 → 各音区各次谐波相对基频的电平（dB）。
    用与检测器相同的 4096 点窗（起音后 8~93 ms），前后 iso 秒内没有别的按键；减去起音前同长度窗的频谱（之前还在响的音）"""
    pitch = [(g, k) for g, k, ch in gt if not ch]
    rows = {"low": [], "mid": [], "high": []}
    for i, (t, k) in enumerate(pitch):
        if k not in key_midi or any(-iso < g - t < iso for j, (g, _) in enumerate(pitch) if j != i):
            continue
        a = int((t + off + 0.008) * sr)
        seg = x[a:a + n].astype(np.float64)
        b = x[max(0, a - n - int(0.016 * sr)):a - int(0.016 * sr)].astype(np.float64)
        if len(seg) < n or len(b) < n:
            continue
        S = np.abs(np.fft.rfft(seg * np.hanning(n), 2 * n))
        Sb = np.abs(np.fft.rfft(b * np.hanning(n), 2 * n))
        d = np.maximum(S - Sb, 0)
        m = key_midi[k]
        f0 = 440 * 2 ** ((m - 69) / 12)
        lv = []
        for h in range(1, 9):
            fb = h * f0 * 2 * n / sr
            lo, hi = int(fb * 2 ** (-0.45 / 12)), int(np.ceil(fb * 2 ** (0.45 / 12))) + 1
            if hi >= len(d) or h * f0 > 8000:
                break
            lv.append(d[lo:hi].max())
        if len(lv) < 3 or lv[0] <= 0:
            continue
        rows[D.timbre_register(m)].append(20 * np.log10(np.maximum(np.array(lv), 1e-12) / lv[0]))
    return rows


def load_old():
    """git HEAD 版本的 detection.py（对比用）"""
    src = subprocess.run(["git", "-C", HERE, "show", "HEAD:detection.py"], capture_output=True, check=True).stdout
    d = tempfile.mkdtemp(prefix="gid_old_")
    path = os.path.join(d, "detection_old.py")
    open(path, "wb").write(src)
    sys.path.insert(0, HERE)
    spec = importlib.util.spec_from_file_location("detection_old", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def beat_bpm(gt, t0, t1):
    """按真实按键（画面）算的拍速：与检测器同一套拍子打分"""
    grp = []
    for t, k, ch in gt:
        if t0 <= t <= t1:
            if grp and t - grp[-1][0] <= 0.035:
                grp[-1][1] += 1
            else:
                grp.append([t, 1])
    if len(grp) < 8:
        return None
    det = D.NoteDetector(next(iter(all_instruments())), sr=48000)
    ts = np.array([g[0] for g in grp])
    acc = np.array([1 + 0.4 * min(3, g[1] - 1) for g in grp])
    T, _, _, _ = det._beat_estimate(ts, acc)
    return 60.0 / T


def report(name, r, key_midi, bpm=None):
    fp, miss = r["fp"], r["miss"]
    p = 100 * r["ok"] / max(1, r["n_dt"])
    rc = 100 * r["ok"] / max(1, r["n_gt"])
    print(f"  [{name}] 检测到 {r['n_dt']} 个音：正确 {r['ok']}（精确率 {p:.0f}%，召回率 {rc:.0f}%）；"
          f"多检 {len(fp)}（其中是同时按下的键的谐波 {sum(1 for f in fp if f[2])}）；漏检 {len(miss)}")
    reg = Counter(D.timbre_register(key_midi[k]) for _, k in miss if k in key_midi)
    print("      漏检按音区：" + "，".join(f"{x} {reg[x]}" for x in ("low", "mid", "high")))
    if bpm:
        vals = [b for _, b in bpm if b is not None]
        jumps = sum(1 for (_, a), (_, b) in zip(bpm, bpm[1:]) if a and b and abs(b / a - 1) > 0.1)
        if vals:
            print(f"      BPM 读数：中位 {np.median(vals):.1f}，范围 {min(vals):.0f}–{max(vals):.0f}，跳变（>10%）{jumps} 次")


def main():
    argv = sys.argv[1:]
    grid = (133.0, 403.0, 69.6, 58.0)
    if "--grid" in argv:
        i = argv.index("--grid")
        grid = tuple(float(v) for v in argv[i + 1].split(","))
        del argv[i:i + 2]
    if "--transpose" in argv:
        i = argv.index("--transpose")
        tr_arg = argv[i + 1]
        del argv[i:i + 2]
        argv += ["--transpose", tr_arg]
        args = [a for a in argv[:-2] if not a.startswith("--")]
    else:
        args = [a for a in argv if not a.startswith("--")]
    video = args[0]
    inst_name = args[1] if len(args) > 1 else "谐律键琴"
    inst = next(i for i in all_instruments() if i.name == inst_name)
    if "--transpose" in argv:
        from instruments import build_lyre21, build_horn, build_youko
        tr = int(argv[argv.index("--transpose") + 1])
        note = inst.note
        inst = (build_horn(transpose=tr) if inst_name == "晚风圆号" else build_youko(transpose=tr) if inst_name == "悠可琴"
                else build_lyre21(inst_name, transpose=tr))
        inst.note = note
    key_midi = {k[0]: k[1] + inst.transpose for k in inst.keys if k[2] == "pitch"}
    rgb, keys, chord, fps = key_colors(video, layout(inst_name), *grid)
    gt = presses(rgb, keys, chord, fps)
    x, sr = load_audio(video)
    dt_new, bpm_new = detect(D, x, sr, inst)
    dt_ev_new = detect.last_events
    res_new = score(dt_new, gt, key_midi)
    grp = []
    for t, k, ch in gt:
        if grp and t - grp[-1][0] <= 0.045:
            grp[-1][1] += 1
        else:
            grp.append([t, 1])
    dur = len(x) / sr
    ref = [beat_bpm(gt, a, a + 8.0) for a in np.arange(0.0, max(1.0, dur - 8.0), 4.0)]
    ref = [b for b in ref if b]
    print(f"{os.path.basename(video)}（{inst_name}）：游戏里按键 {res_new['n_gt']} 次"
          + (f"（另有和弦键 {res_new['n_chord']} 次）" if res_new["n_chord"] else "")
          + f"，最多同时按 {max((g[1] for g in grp), default=0)} 个键，画面→声音 {res_new['off'] * 1000:.0f} ms"
          + (f"；按真实按键算的拍速（8 s 窗）中位 {np.median(ref):.0f}，范围 {min(ref):.0f}–{max(ref):.0f}" if ref else ""))
    if "--old" in argv:
        dt_old, bpm_old = detect(load_old(), x, sr, inst)
        report("旧版", score(dt_old, gt, key_midi, res_new["off"]), key_midi, bpm_old)
    report("新版" if "--old" in argv else "检测", res_new, key_midi, bpm_new)
    # BPM 逐窗对照：每 4 s 取一次读数，与按真实按键（往前 8 s）算的拍速比
    pairs = []
    for a in np.arange(8.0, dur, 4.0):
        g = beat_bpm(gt, a - 8.0, a)
        rd = [b for t, b in bpm_new if a - 0.5 <= t - res_new["off"] <= a + 0.5 and b]
        if g and rd:
            pairs.append((g, float(np.median(rd))))
    if pairs:
        rel = np.array([abs(b / g - 1) for g, b in pairs])
        rel2 = np.array([min(abs(b / (g * f) - 1) for f in (0.5, 1.0, 2.0)) for g, b in pairs])
        print(f"      BPM 逐窗（{len(pairs)} 个 4 s 点）：与真实拍速相差 ≤5% {np.mean(rel <= 0.05) * 100:.0f}%，"
              f"≤10% {np.mean(rel <= 0.10) * 100:.0f}%，平均误差 {np.mean(np.minimum(rel, 1.0)) * 100:.1f}%；"
              f"允许半速 / 倍速时 ≤5% {np.mean(rel2 <= 0.05) * 100:.0f}%")
        if "--bpm" in argv:
            print("      " + "  ".join(f"{g:.0f}/{b:.0f}" for g, b in pairs))
    if inst_name == "晚风圆号" or "--dur" in argv:
        e = hold_errors(rgb, keys, chord, fps, gt, dt_ev_new, res_new["off"])
        if e is not None:
            print(f"      按键时长（画面里按住的时长 vs 检测时长，{len(e)} 个音）：|误差| 中位 {np.median(np.abs(e)) * 1000:.0f} ms，"
                  f"≤100 ms {np.mean(np.abs(e) <= 0.1) * 100:.0f}%，偏差中位 {np.median(e) * 1000:+.0f} ms")
    if "--show" in argv:
        for t, k, harm in res_new["fp"][:40]:
            print(f"      多检 {t:7.2f}s {k}  {'（' + '、'.join(harm) + ' 的谐波）' if harm else ''}")
    if "--timbre" in argv:
        rows = timbre_stats(x, sr, gt, key_midi, res_new["off"])
        for reg in ("low", "mid", "high"):
            rr = rows[reg]
            if not rr:
                continue
            L = min(len(v) for v in rr)
            arr = np.array([v[:L] for v in rr])
            print(f"      音色 {reg}（单独按下 {len(rr)} 次）：" + " ".join(
                f"h{h + 1} {np.median(arr[:, h]):+.0f}/P90 {np.percentile(arr[:, h], 90):+.0f}" for h in range(1, L)))


if __name__ == "__main__":
    main()
