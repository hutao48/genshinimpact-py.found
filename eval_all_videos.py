# -*- coding: utf-8 -*-
"""7 段游戏录像一次评测（并行）：每段的精确率 / 召回率 / BPM 逐窗 / 圆号时长，以及合计。
用法：python eval_all_videos.py [录像目录] [--only 乐器名,...]
录像与键位网格见 VIDEOS；逐帧颜色、真值缓存在临时目录（eval_game_video 的缓存）。"""
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

DIR = r"D:\360MoveData\Users\12849\Desktop\实测视频"
G1 = (133.0, 403.0, 69.6, 58.0)
G2 = (115.0, 433.0, 69.67, 56.0)
VIDEOS = [
    ("bandicam 2026-10-29 21-13-23-537.mp4", "谐律键琴", G1),
    ("bandicam 2026-10-29 21-18-54-289.mp4", "谐律键琴", G1),
    ("bandicam 2026-10-29 22-29-55-616.mp4", "风物之诗琴", G2),
    ("bandicam 2026-10-29 22-32-22-562.mp4", "镜花之琴", G2),
    ("bandicam 2026-10-29 22-34-16-447.mp4", "跃律琴", G2),
    ("bandicam 2026-10-29 22-36-38-723.mp4", "晚风圆号", (115.0, 490.0, 69.67, 56.0)),
    ("bandicam 2026-10-29 22-40-06-246.mp4", "悠可琴", G2),
]


def run_one(args):
    path, name, grid = args
    import eval_game_video as E
    import detection as D
    from instruments import all_instruments
    inst = next(i for i in all_instruments() if i.name == name)
    key_midi = {k[0]: k[1] + inst.transpose for k in inst.keys if k[2] == "pitch"}
    rgb, keys, chord, fps = E.key_colors(path, E.layout(name), *grid)
    gt = E.presses(rgb, keys, chord, fps)
    x, sr = E.load_audio(path)
    dt, bpm = E.detect(D, x, sr, inst)
    ev = E.detect.last_events
    r = E.score(dt, gt, key_midi)
    dur = len(x) / sr
    pairs = []
    for a in np.arange(8.0, dur, 4.0):
        g = E.beat_bpm(gt, a - 8.0, a)
        rd = [b for t, b in bpm if a - 0.5 <= t - r["off"] <= a + 0.5 and b]
        if g and rd:
            pairs.append((g, float(np.median(rd))))
    rel2 = [min(abs(b / (g * f) - 1) for f in (0.5, 1.0, 2.0)) for g, b in pairs]
    hold = None
    if name == "晚风圆号":
        e = E.hold_errors(rgb, keys, chord, fps, gt, ev, r["off"])
        hold = (float(np.median(np.abs(e))), float(np.mean(np.abs(e) <= 0.1)), len(e))
    return {"video": os.path.basename(path), "inst": name, "ok": r["ok"], "n_dt": r["n_dt"], "n_gt": r["n_gt"],
            "harm": sum(1 for f in r["fp"] if f[2]), "bpm5": float(np.mean(np.array(rel2) <= 0.05)) if rel2 else None,
            "hold": hold}


def main():
    argv = sys.argv[1:]
    only = None
    if "--only" in argv:
        i = argv.index("--only")
        only = set(argv[i + 1].split(","))
        del argv[i:i + 2]
    d = argv[0] if argv else DIR
    jobs = [(os.path.join(d, v), n, g) for v, n, g in VIDEOS if only is None or n in only]
    with ProcessPoolExecutor(max_workers=min(7, os.cpu_count() or 2)) as ex:
        res = list(ex.map(run_one, jobs))
    T = {"ok": 0, "n_dt": 0, "n_gt": 0}
    for r in res:
        for k in T:
            T[k] += r[k]
        p = r["ok"] / max(1, r["n_dt"])
        rc = r["ok"] / max(1, r["n_gt"])
        f1 = 2 * p * rc / max(1e-9, p + rc)
        line = (f"{r['inst']:<6}{r['video'][20:28]}  P {p * 100:5.1f}%  R {rc * 100:5.1f}%  F1 {f1 * 100:5.1f}  "
                f"检 {r['n_dt']:4d} 对 {r['ok']:4d} 真 {r['n_gt']:4d} 谐波多检 {r['harm']:3d}")
        if r["bpm5"] is not None:
            line += f"  BPM±5% {r['bpm5'] * 100:4.0f}%"
        if r["hold"]:
            line += f"  时长|e|中位 {r['hold'][0] * 1000:.0f}ms ≤100ms {r['hold'][1] * 100:.0f}% (n={r['hold'][2]})"
        print(line)
    p = T["ok"] / max(1, T["n_dt"])
    rc = T["ok"] / max(1, T["n_gt"])
    print(f"合计  P {p * 100:.1f}%  R {rc * 100:.1f}%  F1 {2 * p * rc / (p + rc) * 100:.1f}  "
          f"（检 {T['n_dt']} 对 {T['ok']} 真 {T['n_gt']}）")


if __name__ == "__main__":
    main()
