# -*- coding: utf-8 -*-
"""原神乐器演奏检测器 —— 程序入口

用法：
  原神乐器演奏检测器.exe                         启动界面（实时监听）
  原神乐器演奏检测器.exe --analyze 录音.wav [结果.txt] [乐器名]
                                                 离线分析一段录音，结果写入文本文件
                                                 （默认写到录音旁边的「录音名_分析.txt」）
"""
import os
import sys
import threading
import traceback

from app_version import APP_VERSION


def _log_path():
    log_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                           "GenshinInstrumentDetector")
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, "app.log")


def _setup_logging():
    """将未捕获异常写入日志文件，便于排查问题"""
    try:
        log_path = _log_path()

        def hook(exc_type, exc_value, exc_tb):
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("=" * 60 + "\n")
                f.write("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
            sys.__excepthook__(exc_type, exc_value, exc_tb)

        sys.excepthook = hook

        def thread_hook(args):
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("=" * 60 + "\n[工作线程异常]\n")
                f.write("".join(traceback.format_exception(args.exc_type, args.exc_value,
                                                           args.exc_traceback)))

        threading.excepthook = thread_hook
    except Exception:
        pass


def _read_wav(path):
    """读 PCM WAV（8/16/24/32 位，任意声道/采样率）→ (单声道 float32, 采样率)"""
    import wave
    import numpy as np
    with wave.open(path, "rb") as wf:
        ch, sw, sr, n = wf.getnchannels(), wf.getsampwidth(), wf.getframerate(), wf.getnframes()
        raw = wf.readframes(n)
    if sw == 1:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sw == 2:
        x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sw == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        x = (np.where(v >= 1 << 23, v - (1 << 24), v)).astype(np.float32) / float(1 << 23)
    elif sw == 4:
        x = np.frombuffer(raw, dtype="<i4").astype(np.float32) / float(1 << 31)
    else:
        raise ValueError(f"不支持的采样位宽：{sw * 8} bit")
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x.astype(np.float32), sr


def analyze_file(wav_path, out_path=None, inst_name=None):
    """离线分析录音，返回写出的结果文件路径"""
    import numpy as np
    from instruments import all_instruments
    from detection import NoteDetector, END_REASON_TEXT

    insts = all_instruments()
    inst = next((i for i in insts if i.name == inst_name), insts[0])
    x, sr = _read_wav(wav_path)
    det = NoteDetector(inst, sr=sr, sensitivity=0.55)
    events, bpm_track, tonality = [], [], ""
    block = 2048
    for i in range(0, len(x), block):
        r = det.feed(x[i:i + block])
        events.extend(r["note_events"])
        if r["bpm"] is not None:
            bpm_track.append((r["bpm"], det.bpm_confidence))
        tonality = r["tonality"] or tonality
    r = det.feed(np.zeros(sr, dtype=np.float32))          # 补 1 s 静音让余音落音
    events.extend(r["note_events"])
    events.sort(key=lambda e: e["t"])
    # 报告演奏期间的 BPM：取最后一个高置信度读数（≥60% 的起音间隔能被同一周期解释）——
    # 录音结尾若只剩环境声/音效，那段时间的读数是被噪音起音带偏的低置信度值；
    # 结尾读数本身可信时与直接取最后读数相同
    bpm = None
    good = [b for b, c in bpm_track if c >= 0.6]
    if good:
        bpm = good[-1]
    elif bpm_track:
        bpm = bpm_track[-1][0]

    if out_path is None:
        out_path = os.path.splitext(wav_path)[0] + "_分析.txt"
    lines = [
        f"原神乐器演奏检测器 v{APP_VERSION} 离线分析",
        f"文件：{os.path.abspath(wav_path)}",
        f"时长：{len(x) / sr:.2f} s　采样率：{sr} Hz　乐器：{inst.name}",
        f"BPM：{'—' if bpm is None else f'{bpm:.1f}'}　调性：{tonality or '—'}　音符数：{len(events)}",
        "",
        "开始(s)\t按键\t音名\t时长(ms)\t间隔(ms)\t结束方式",
    ]
    for e in events:
        ioi = "—" if e.get("ioi_ms") is None else f"{e['ioi_ms']:.0f}"
        end = END_REASON_TEXT.get(e.get("end"), e.get("end") or "")
        lines.append(f"{e['t']:.3f}\t{e['key']}\t{e['name']}\t{e['dur_ms']:.0f}\t{ioi}\t{end}")
    with open(out_path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(lines) + "\n")
    return out_path


def main():
    _setup_logging()
    args = sys.argv[1:]
    if args and args[0] in ("--analyze", "-a"):
        if len(args) < 2:
            print(__doc__)
            sys.exit(2)
        try:
            out = analyze_file(args[1], args[2] if len(args) > 2 else None,
                               args[3] if len(args) > 3 else None)
        except Exception:
            # 窗口程序没有控制台：错误写入日志文件
            try:
                with open(_log_path(), "a", encoding="utf-8") as f:
                    f.write("=" * 60 + "\n[离线分析失败] " + " ".join(args) + "\n")
                    f.write(traceback.format_exc())
            except Exception:
                pass
            sys.exit(1)
        print(out)
        sys.exit(0)
    from ui_main import main as ui_main
    ui_main()


if __name__ == "__main__":
    main()
