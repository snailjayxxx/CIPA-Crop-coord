"""Run with Python 3.11 and QT_QPA_PLATFORM=offscreen; uses the original Worker."""
import os
import faulthandler
import gc
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer, QEventLoop, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from cipa_crop_coord.image_to_video import create_video_from_images
from cipa_crop_coord.ui_user_text import MainWindow
from cipa_crop_coord.ui_image_to_video import TEXT
from cipa_crop_coord.locales import tr


class VideoUiRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        gc.disable()  # Qt widget cycles must be collected on the GUI thread.
        self.temporary = tempfile.TemporaryDirectory(prefix="cipa_video_regression_")
        self.root = Path(self.temporary.name)
        self.images = self.root / "連写サンプル"
        self.images.mkdir()
        self.output = self.root / "動画出力_日本語"
        self.output.mkdir()
        for index in range(108, 0, -1):
            color = [(0, 0, 230), (0, 230, 0), (230, 0, 0)][(index - 1) % 3]
            image = np.full((80, 120, 3), color, np.uint8)
            ok, encoded = cv2.imencode(".png", image)
            self.assertTrue(ok)
            encoded.tofile(str(self.images / f"画像{index}.png"))
        self.window = MainWindow()
        self.window.tabs.setCurrentIndex(5)
        self.window.show()
        self.app.processEvents()
        self.info, self.warnings = [], []
        self.patchers = [
            patch.object(QMessageBox, "information", side_effect=lambda *a, **kw: self.info.append(a[2])),
            patch.object(QMessageBox, "warning", side_effect=lambda *a, **kw: self.warnings.append(a[2])),
            patch.object(QMessageBox, "exec", return_value=QMessageBox.StandardButton.Yes),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self):
        tab = self.window.f
        if tab.thread is not None:
            tab.stop()
            self.wait_for_completion()
        self.window.close()
        self.window.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temporary.cleanup()
        gc.collect()
        gc.enable()

    def start_from_ui(self, target, output=None, fps=10):
        tab = self.window.f
        tab.input.edit.setText(str(self.images))
        tab.output.edit.setText(str(output or self.output))
        tab.fps.setValue(fps)
        tab.count.setValue(target)
        tab.refresh_count()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.assertIn("108", tab.found.text())
        QTest.mouseClick(tab.run, Qt.MouseButton.LeftButton)
        self._active_thread = tab.thread
        self._active_worker = tab.worker
        return tab

    def wait_for_completion(self):
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(10)
        timer.timeout.connect(lambda: loop.quit() if self.window.f.thread is None else None)
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        timer.start()
        timeout.start(12000)
        loop.exec()
        timer.stop()
        timeout.stop()
        self.assertIsNone(self.window.f.thread, "Original QThread did not complete")
        self.assertTrue(self.window.f.run.isEnabled())
        self.assertFalse(self.window.f.cancel.isEnabled())

    def decode(self, output):
        capture = cv2.VideoCapture(str(output))
        self.assertTrue(capture.isOpened(), str(output))
        fps = capture.get(cv2.CAP_PROP_FPS)
        frames = []
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                frames.append(frame)
        finally:
            capture.release()
        return frames, fps

    def test_108_images_100_frames_10fps_and_folder_output(self):
        self.start_from_ui(100)
        self.wait_for_completion()
        self.assertEqual(self.warnings, [])
        self.assertEqual(len(self.info), 1)
        output = self.output / (self.images.name + ".mp4")
        self.assertEqual(self.window.f.output.text(), str(output))
        frames, fps = self.decode(output)
        self.assertEqual(len(frames), 100)
        self.assertAlmostEqual(fps, 10)
        self.assertAlmostEqual(len(frames) / fps, 10)
        for index, frame in enumerate(frames):
            self.assertEqual(np.argmax(frame.mean(axis=(0, 1))), [2, 1, 0][index % 3])

    def test_padding_112_frames_from_108_images(self):
        self.start_from_ui(112)
        self.wait_for_completion()
        self.assertEqual(self.warnings, [])
        frames, fps = self.decode(Path(self.window.f.output.text()))
        self.assertEqual(len(frames), 112)
        self.assertAlmostEqual(fps, 10)
        self.assertGreater(frames[107].mean(), 50)
        for frame in frames[108:]:
            self.assertLess(frame.max(), 5)

    def test_all_images_fractional_fps_and_japanese_ui(self):
        self.window.combo.setCurrentIndex(1)
        self.assertEqual(self.window.tabs.count(), 6)
        self.assertEqual(len(self.window.task_tabs()), 6)
        self.start_from_ui(0, fps=12.5)
        self.wait_for_completion()
        self.assertEqual(self.warnings, [])
        frames, fps = self.decode(Path(self.window.f.output.text()))
        self.assertEqual(len(frames), 108)
        self.assertAlmostEqual(fps, 12.5)

    def test_switch_languages_validation_overwrite_and_completion(self):
        for lang in ("zh", "ja", "en"):
            with self.subTest(lang=lang):
                self.window.combo.setCurrentIndex(self.window.combo.findData(lang))
                self.window.tabs.setCurrentIndex(5)
                tab = self.window.f
                self.assertEqual(tab.lang, lang)
                self.assertEqual(self.window.tabs.tabText(5), TEXT[lang]["tab"])
                self.assertEqual(tab.count.specialValueText(), TEXT[lang]["all"])
                self.assertEqual(tab.output.edit.placeholderText(), TEXT[lang]["output_hint"])
                self.assertEqual(tab.run.text(), tr(lang, "start"))
                tab.go()
                self.assertEqual(self.warnings.pop(), TEXT[lang]["choose_input"])
                tab.input.edit.setText(str(self.images))
                tab.go()
                self.assertEqual(self.warnings.pop(), TEXT[lang]["choose_output"])

                destination = self.output / (lang + ".mp4")
                destination.write_bytes(b"existing video")
                tab.output.edit.setText(str(destination))

                def decline(dialog):
                    self.assertEqual(dialog.windowTitle(), TEXT[lang]["overwrite_title"])
                    self.assertEqual(dialog.text(), TEXT[lang]["overwrite"].format(path=destination))
                    self.assertEqual(dialog.button(QMessageBox.StandardButton.Yes).text(), TEXT[lang]["yes"])
                    self.assertEqual(dialog.button(QMessageBox.StandardButton.No).text(), TEXT[lang]["no"])
                    return QMessageBox.StandardButton.No

                with patch.object(QMessageBox, "exec", decline):
                    tab.go()
                self.assertIsNone(tab.thread)
                self.assertEqual(destination.read_bytes(), b"existing video")

                self.start_from_ui(110, destination)
                self.wait_for_completion()
                self.assertEqual(self.warnings, [])
                self.assertIn(tr(lang, "finished", ok=110, skip=0, fail=0), tab.log.toPlainText())
                self.assertEqual(self.info.pop(), tr(lang, "done_body", total=110, ok=110, skip=0, fail=0, path=destination, debug=""))
                frames, fps = self.decode(destination)
                self.assertEqual(len(frames), 110)
                self.assertAlmostEqual(fps, 10)
                self.assertLess(frames[-1].max(), 5)

    def test_cancel_button_preserves_existing_output_and_cleans_temporary(self):
        destination = self.output / "existing.mp4"
        destination.write_bytes(b"previous output")
        temp = self.root / "encode_temp"
        temp.mkdir()
        with patch.object(tempfile, "tempdir", str(temp)):
            tab = self.start_from_ui(100000, destination)
            clicked = []

            def cancel_after_progress():
                if tab.progress.value() >= 5 and not clicked:
                    clicked.append(True)
                    QTest.mouseClick(tab.cancel, Qt.MouseButton.LeftButton)

            timer = QTimer()
            timer.timeout.connect(cancel_after_progress)
            timer.start(5)
            self.wait_for_completion()
            timer.stop()
        self.assertEqual(clicked, [True])
        self.assertEqual(destination.read_bytes(), b"previous output")
        self.assertEqual(self.info, [])
        self.assertEqual(len(self.warnings), 1)
        self.assertNotIn("is_set", self.warnings[0])
        self.assertEqual(list(temp.iterdir()), [])
        self.assertEqual(list(self.output.glob(".cipa_video_*.part")), [])

    def test_real_cross_filesystem_output(self):
        if not Path("/dev/shm").is_dir() or os.stat("/dev/shm").st_dev == os.stat(tempfile.gettempdir()).st_dev:
            self.skipTest("No second filesystem available")
        with tempfile.TemporaryDirectory(dir="/dev/shm", prefix="cipa_video_") as other:
            destination = Path(other) / "別ドライブ.mp4"
            self.start_from_ui(3, destination)
            self.wait_for_completion()
            self.assertEqual(self.warnings, [])
            frames, fps = self.decode(destination)
            self.assertEqual(len(frames), 3)
            self.assertEqual(list(Path(other).glob("*.part")), [])

    def test_publish_failure_preserves_existing_file_and_cleans_temp(self):
        destination = self.output / "existing.mp4"
        destination.write_bytes(b"previous output")
        temp = self.root / "encode_temp"
        temp.mkdir()
        with patch.object(tempfile, "tempdir", str(temp)), patch(
            "cipa_crop_coord.image_to_video.os.replace", side_effect=PermissionError("in use")
        ):
            with self.assertRaises(PermissionError):
                create_video_from_images(str(self.images), str(destination), 10, 3, cancel=lambda: False)
        self.assertEqual(destination.read_bytes(), b"previous output")
        self.assertEqual(list(temp.iterdir()), [])
        self.assertEqual(list(self.output.glob(".cipa_video_*.part")), [])


if __name__ == "__main__":
    faulthandler.dump_traceback_later(15, exit=True)
    unittest.main(verbosity=2)
