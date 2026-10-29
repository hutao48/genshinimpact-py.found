"""停顿背景声、静音清屏及恢复演奏的回归测试（合成音频，无需音频设备）。"""
import unittest

import numpy as np

from detection import NoteDetector
from instruments import build_lyre21
from test_detection import SR, play_sequence, synth_note


def run_audio(audio, block=2048):
    det = NoteDetector(build_lyre21("风物之诗琴"), sensitivity=0.55)
    trace, events = [], []
    for i in range(0, len(audio), block):
        res = det.feed(audio[i:i + block])
        trace.append((res["t"], set(res["keys"])))
        events.extend(res["note_events"])
    return det, trace, events


class StopKeysTest(unittest.TestCase):
    def test_quiet_pitched_background_does_not_become_new_keys(self):
        # 停顿后背景声本身有音高、谐波和起音，不能只靠"有谱峰"就继续亮键。
        song = play_sequence([(m, 0.3) for m in [60, 64, 67, 72, 74, 76]])
        background = 0.025 * play_sequence([(m, 0.4) for m in [55, 59, 72, 57] * 4])
        resume = play_sequence([(m, 0.3) for m in [69, 65, 62, 60]])
        for gain in (1.0, 0.01):
            with self.subTest(gain=gain):
                audio = gain * np.concatenate([song, background, resume, np.zeros(SR)])
                _, trace, events = run_audio(audio)
                start, end = len(song) / SR, (len(song) + len(background)) / SR
                self.assertTrue(all(not keys for t, keys in trace if start + 0.25 < t < end))
                self.assertFalse([e for e in events if start + 0.1 < e["t"] < end - 0.1])
                for m in [69, 65, 62, 60]:
                    self.assertTrue(any(e["midi"] == m and e["t"] >= end - 0.05 for e in events))

    def test_background_at_same_pitch_cannot_hold_finished_note(self):
        signal = np.concatenate([synth_note(60, 0.5), 0.003 * synth_note(60, 4.0, decay=0)])
        _, trace, events = run_audio(np.concatenate([signal, np.zeros(SR)]))
        self.assertTrue(all(not keys for t, keys in trace if t > 0.8))
        self.assertEqual(len(events), 1)
        self.assertLess(events[0]["dur_ms"], 650)

    def test_large_batch_reports_current_keys_and_keeps_finished_events(self):
        audio = np.concatenate([synth_note(60, 0.5), np.zeros(SR)])
        det = NoteDetector(build_lyre21("风物之诗琴"))
        res = det.feed(audio)
        self.assertFalse(res["keys"])
        self.assertEqual([e["midi"] for e in res["note_events"]], [60])
        self.assertFalse(det.active)

    def test_small_batch_keeps_current_snapshot_until_next_analysis_frame(self):
        det = NoteDetector(build_lyre21("风物之诗琴"))
        audio = synth_note(60, 0.5, decay=0)
        for i in range(0, len(audio), 2048):
            res = det.feed(audio[i:i + 2048])
        self.assertIn("A", res["keys"])
        self.assertEqual(det.feed(audio[:128])["keys"], res["keys"])
        self.assertFalse(det.feed(np.zeros(SR))["keys"])

    def test_quieter_real_note_and_low_volume_stream_remain_detectable(self):
        # 容许正常音色/音域的电平差；门限按输入同比缩放，不依赖固定系统音量。
        for gain in (1.0, 0.01):
            song = play_sequence([(60, 0.4), (64, 0.4), (67, 0.4)])
            song = np.concatenate([song, 0.15 * synth_note(72, 0.4), np.zeros(SR)])
            _, _, events = run_audio(gain * song)
            self.assertTrue(any(e["midi"] == 72 for e in events))


if __name__ == "__main__":
    unittest.main()
