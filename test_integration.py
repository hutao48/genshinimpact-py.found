"""检测引擎与多语言主界面/悬浮窗的回归测试；不使用真实音频设备或用户设置。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np


class IntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="gid-integration-")
        cls.env = patch.dict(os.environ, {"LOCALAPPDATA": cls.temp.name,
                                         "QT_QPA_PLATFORM": "offscreen", "GID_LANG": "",
                                         "GID_NO_UPDATE": "1", "GID_I18N_CHECK": "1"})
        cls.env.start()
        import i18n
        import ui_main
        from PySide6.QtWidgets import QApplication
        cls.i18n, cls.ui = i18n, ui_main
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        cls.temp.cleanup()

    def setUp(self):
        self.i18n.init("zh-CN")
        self.ui.apply_theme(self.app, "dark")
        self.window = self.ui.MainWindow(self_test=True)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_transposed_keys_and_floating_window_stay_in_sync(self):
        from instruments import midi_to_name
        self.window.show()
        self.window.show_float()
        for index, base in enumerate(self.window.instruments):
            self.window.cmb_instrument.setCurrentIndex(index)
            for transpose in (-12, 0, 12):
                self.window.spin_transpose.setValue(transpose)
                inst = self.window._current_inst
                main = self.window.key_panel
                floating = self.window.float_win.key_panel
                self.assertEqual(set(main.buttons), set(floating.buttons))
                self.assertEqual(len(main.buttons), 14 if base.name == "晚风圆号" else 21)
                for letter, midi, role, _ in inst.keys:
                    if role == "pitch":
                        expected = midi_to_name(midi + transpose)
                        self.assertEqual(main.buttons[letter].note, expected)
                        self.assertEqual(floating.buttons[letter].note, expected)
                        self.assertEqual(inst.label_of(midi + transpose)[0], letter)
                self.window.on_keys({"Q", "A"})
                self.assertTrue(main.buttons["Q"].active)
                self.assertTrue(floating.buttons["A"].active)
                self.window.on_keys(set())
                self.assertFalse(any(tile.active for tile in floating.buttons.values()))
        for mode in ("light", "dark", "system"):
            self.window.set_theme(mode)
            self.app.processEvents()
            self.assertFalse(self.window.grab().isNull())
            self.assertFalse(self.window.float_win.grab().isNull())

    def test_worker_delivers_finished_notes_to_horn_duration_screening(self):
        from instruments import build_horn
        worker = self.ui.DetectWorker(build_horn(), None, True, 0.55)
        events = [{"t": i * 0.5, "dur_ms": 240.0, "end": "release"} for i in range(16)]
        worker.detector.feed = Mock(return_value={"note_events": events, "keys": {},
                                                 "chord": None, "tonality": None,
                                                 "bpm": None, "t": 8.0})
        findings = []
        worker.sig_finding.connect(findings.append)
        cap = Mock()
        cap.read_block.side_effect = lambda: (worker.stop(), np.zeros(2048, dtype=np.float32))[1]
        with patch.object(self.ui, "AudioCapture", return_value=cap):
            worker.run()
        self.assertTrue(any(f["kind"] == "hold" and f["n"] == 16 for f in findings))
        cap.close.assert_called_once()

    def test_capture_exception_is_reported_and_device_closed(self):
        from instruments import build_lyre21
        worker = self.ui.DetectWorker(build_lyre21("风物之诗琴"), None, True, 0.55)
        cap = Mock()
        cap.read_block.side_effect = RuntimeError("test device failure")
        errors = []
        worker.sig_error.connect(errors.append)
        with patch.object(self.ui, "AudioCapture", return_value=cap):
            worker.run()
        self.assertTrue(any("test device failure" in message for message in errors))
        cap.close.assert_called_once()

    def test_new_findings_and_help_are_translated_in_all_languages(self):
        from instruments import build_horn, build_lyre21
        from screening import Q_BLOCK, Screener, kind_text
        for language in self.i18n.CODES:
            with self.subTest(language=language):
                self.i18n.init(language)
                self.i18n.MISSING.clear()
                horn = Screener(build_horn())
                events = [{"t": i * 0.5, "dur_ms": 240.0, "end": "release"} for i in range(16)]
                findings = horn._scan_holds(events)
                self.assertTrue(findings)
                self.assertNotIn("{", findings[0]["text"])
                kind_text("hold")
                grid = Screener(build_lyre21("风物之诗琴"))
                time = 0.0
                for i in range(180):
                    time += (1, 2, 3)[i % 3] * 0.22
                    grid._reg_add(round(time / Q_BLOCK) * Q_BLOCK)
                self.assertTrue(any(f.get("rhythm") for f in grid.findings))
                self.assertNotIn("{", grid.summary())
                self.window._screen_help()
                self.assertFalse(self.i18n.MISSING, sorted(self.i18n.MISSING))

    def test_gui_self_test_does_not_change_preferences_or_start_listening(self):
        root = Path(self.temp.name)/"self-test-profile"
        profile = root/"GenshinInstrumentDetector/settings.ini"
        profile.parent.mkdir(parents=True)
        original = b"[general]\nlanguage = en\ncheck_updates = 1\nfloat_window = 1\n"
        profile.write_bytes(original)
        report = root/"gui.json"
        env = {**os.environ, "LOCALAPPDATA": str(root), "GID_AUTOSTART": "1", "GID_LANG": "en"}
        p = subprocess.run([sys.executable, str(Path(__file__).with_name("main.py")),
                            "--self-test-gui", str(report)], env=env, timeout=30,
                           capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
        result = json.loads(report.read_text(encoding="utf-8"))
        self.assertTrue(result["ok"])
        self.assertEqual(result["language"], "en")
        self.assertFalse(result["frozen"])
        self.assertTrue(report.with_suffix(".png").is_file())
        self.assertEqual(profile.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
