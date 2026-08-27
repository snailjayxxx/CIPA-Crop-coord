from __future__ import annotations

import math
import sys
from pathlib import Path

import cv2
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import ui
from . import ui_coord_modes as coord_ui
from .locales import tr
from .video_tool12 import VideoRange, export_video_frames_tool12, probe_video


TEXT = {
    "zh": {
        "tab": "⑤ 视频逐帧导出",
        "videos": "视频文件",
        "add": "添加视频…",
        "remove": "移除选中",
        "clear": "清空",
        "video_filter": "视频 (*.mp4 *.MP4);;所有文件 (*)",
        "video_list_hint": "可一次导入多个视频。每个视频单独保存开始/结束时间；默认范围为整个视频。",
        "output": "输出图片文件夹：",
        "preview_group": "视频预览与导出范围",
        "preview_empty": "选择左侧某个视频后显示预览",
        "duration": "视频时长：",
        "fps": "帧率：",
        "start": "开始时间：",
        "end": "结束时间：",
        "time_hint": "可拖动蓝色范围条左右两端，也可手动输入 HH:MM:SS.mmm（也支持 MM:SS 或秒数）。",
        "naming_note": "导出保持 Tool 12：原视频帧不缩放、不转换，JPEG 使用 OpenCV 默认 imwrite；文件名保持“原视频文件名_原始帧号5位.jpg”。",
        "select_videos": "请选择至少一个视频",
        "select_output": "请选择输出图片文件夹",
        "invalid_time": "时间格式无效：{value}",
        "probe_failed": "无法读取视频",
        "duplicate_name": "注意：多个输入视频同名时，输出文件名可能互相覆盖。",
    },
    "ja": {
        "tab": "⑤ 動画フレーム出力",
        "videos": "動画ファイル",
        "add": "動画を追加…",
        "remove": "選択を削除",
        "clear": "すべて削除",
        "video_filter": "動画 (*.mp4 *.MP4);;すべてのファイル (*)",
        "video_list_hint": "複数動画を一括追加できます。開始/終了時間は動画ごとに保持し、初期値は動画全体です。",
        "output": "出力画像フォルダー：",
        "preview_group": "動画プレビューと出力範囲",
        "preview_empty": "左側の動画を選択するとプレビューを表示します",
        "duration": "動画時間：",
        "fps": "フレームレート：",
        "start": "開始時間：",
        "end": "終了時間：",
        "time_hint": "青い範囲バーの左右端をドラッグするか、HH:MM:SS.mmm（MM:SS / 秒数も可）を直接入力できます。",
        "naming_note": "Tool 12 の処理を維持：元フレームはリサイズ/変換せず、JPEG は OpenCV 既定 imwrite。ファイル名は「元動画ファイル名_元フレーム番号5桁.jpg」のままです。",
        "select_videos": "動画を1つ以上選択してください",
        "select_output": "出力画像フォルダーを選択してください",
        "invalid_time": "時間形式が正しくありません：{value}",
        "probe_failed": "動画を読み込めません",
        "duplicate_name": "注意：同名の入力動画が複数ある場合、出力ファイル名が上書きされる可能性があります。",
    },
    "en": {
        "tab": "⑤ Video to Frames",
        "videos": "Video files",
        "add": "Add videos…",
        "remove": "Remove selected",
        "clear": "Clear",
        "video_filter": "Videos (*.mp4 *.MP4);;All files (*)",
        "video_list_hint": "Add multiple videos at once. Each video keeps its own start/end range; the default is the full video.",
        "output": "Output image folder:",
        "preview_group": "Video preview and export range",
        "preview_empty": "Select a video on the left to show its preview",
        "duration": "Duration:",
        "fps": "Frame rate:",
        "start": "Start time:",
        "end": "End time:",
        "time_hint": "Drag either end of the blue range bar, or type HH:MM:SS.mmm (MM:SS and raw seconds are also accepted).",
        "naming_note": "Tool 12 behavior is preserved: source frames are not resized/converted, JPEG uses OpenCV default imwrite, and names remain “original-video-filename_original-5-digit-frame.jpg”.",
        "select_videos": "Select at least one video",
        "select_output": "Select an output image folder",
        "invalid_time": "Invalid time format: {value}",
        "probe_failed": "Cannot read video",
        "duplicate_name": "Note: videos with identical filenames can overwrite each other's output images.",
    },
}


def txt(lang: str, key: str, **kwargs) -> str:
    text = TEXT.get(lang, TEXT["zh"])[key]
    return text.format(**kwargs)


def format_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    total_ms = int(round(seconds * 1000.0))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def parse_time(text: str) -> float:
    value = text.strip()
    if not value:
        raise ValueError(value)
    parts = value.split(":")
    if len(parts) == 1:
        result = float(parts[0])
    elif len(parts) == 2:
        result = float(parts[0]) * 60.0 + float(parts[1])
    elif len(parts) == 3:
        result = float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2])
    else:
        raise ValueError(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(value)
    return result


class RangeSlider(QWidget):
    valuesChanged = Signal(int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.minimum = 0
        self.maximum = 1
        self.lower = 0
        self.upper = 1
        self.active = -1
        self.setMinimumHeight(42)
        self.setMouseTracking(True)

    def set_range(self, minimum: int, maximum: int):
        self.minimum = int(minimum)
        self.maximum = max(self.minimum + 1, int(maximum))
        self.set_values(self.minimum, self.maximum, emit=False)

    def set_values(self, lower: int, upper: int, emit: bool = False, active: int = -1):
        lower = max(self.minimum, min(int(lower), self.maximum))
        upper = max(self.minimum, min(int(upper), self.maximum))
        if lower > upper:
            lower, upper = upper, lower
        changed = lower != self.lower or upper != self.upper
        self.lower, self.upper = lower, upper
        self.update()
        if emit and changed:
            self.valuesChanged.emit(self.lower, self.upper, active)

    def _track(self) -> tuple[float, float, float]:
        margin = 14.0
        left = margin
        right = max(left + 1.0, self.width() - margin)
        return left, right, self.height() / 2.0

    def _x(self, value: int) -> float:
        left, right, _ = self._track()
        ratio = (value - self.minimum) / max(1, self.maximum - self.minimum)
        return left + ratio * (right - left)

    def _value(self, x: float) -> int:
        left, right, _ = self._track()
        ratio = (x - left) / max(1.0, right - left)
        ratio = max(0.0, min(1.0, ratio))
        return int(round(self.minimum + ratio * (self.maximum - self.minimum)))

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        left, right, y = self._track()

        painter.setPen(QPen(QColor("#c7ccd5"), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(int(left), int(y), int(right), int(y))

        x1, x2 = self._x(self.lower), self._x(self.upper)
        painter.setPen(QPen(QColor("#1769e0"), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(int(x1), int(y), int(x2), int(y))

        painter.setPen(QPen(QColor("#1769e0"), 2))
        painter.setBrush(QColor("white"))
        painter.drawEllipse(QRectF(x1 - 8, y - 8, 16, 16))
        painter.drawEllipse(QRectF(x2 - 8, y - 8, 16, 16))

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        x = event.position().x()
        self.active = 0 if abs(x - self._x(self.lower)) <= abs(x - self._x(self.upper)) else 1
        self._move_active(x)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.active >= 0 and event.buttons() & Qt.MouseButton.LeftButton:
            self._move_active(event.position().x())
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.active = -1
            event.accept()

    def _move_active(self, x: float):
        value = self._value(x)
        if self.active == 0:
            self.set_values(min(value, self.upper), self.upper, emit=True, active=0)
        elif self.active == 1:
            self.set_values(self.lower, max(value, self.lower), emit=True, active=1)


class VideoTab(ui.BatchTab):
    def __init__(self, lang: str):
        super().__init__(lang)
        self.videos: list[VideoRange] = []
        self.preview_image = QPixmap()

        paths = QGroupBox(txt(lang, "videos"))
        paths_layout = QVBoxLayout(paths)
        self.video_list = QListWidget()
        self.video_list.setMinimumWidth(360)
        self.video_list.currentRowChanged.connect(self.select_row)
        paths_layout.addWidget(self.video_list, 1)

        buttons = QHBoxLayout()
        add = QPushButton(txt(lang, "add"))
        remove = QPushButton(txt(lang, "remove"))
        clear = QPushButton(txt(lang, "clear"))
        add.clicked.connect(self.add_videos)
        remove.clicked.connect(self.remove_selected)
        clear.clicked.connect(self.clear_videos)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addWidget(clear)
        buttons.addStretch()
        paths_layout.addLayout(buttons)

        list_hint = QLabel(txt(lang, "video_list_hint"))
        list_hint.setWordWrap(True)
        paths_layout.addWidget(list_hint)

        output_box = QGroupBox(tr(lang, "paths"))
        output_form = QFormLayout(output_box)
        self.output = ui.PathChooser(lang, "folder")
        output_form.addRow(txt(lang, "output"), self.output)

        preview_box = QGroupBox(txt(lang, "preview_group"))
        preview_layout = QVBoxLayout(preview_box)
        self.preview = QLabel(txt(lang, "preview_empty"))
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(520, 292)
        self.preview.setStyleSheet("background:#111; color:#ddd; border-radius:6px;")
        preview_layout.addWidget(self.preview, 1)

        info_form = QFormLayout()
        self.duration_label = QLabel("-")
        self.fps_label = QLabel("-")
        self.start_edit = QLineEdit()
        self.end_edit = QLineEdit()
        self.start_edit.editingFinished.connect(lambda: self.commit_time("start"))
        self.end_edit.editingFinished.connect(lambda: self.commit_time("end"))
        info_form.addRow(txt(lang, "duration"), self.duration_label)
        info_form.addRow(txt(lang, "fps"), self.fps_label)
        info_form.addRow(txt(lang, "start"), self.start_edit)
        info_form.addRow(txt(lang, "end"), self.end_edit)
        preview_layout.addLayout(info_form)

        self.range_slider = RangeSlider()
        self.range_slider.valuesChanged.connect(self.range_changed)
        preview_layout.addWidget(self.range_slider)

        time_hint = QLabel(txt(lang, "time_hint"))
        time_hint.setWordWrap(True)
        naming_note = QLabel(txt(lang, "naming_note"))
        naming_note.setWordWrap(True)
        duplicate_note = QLabel(txt(lang, "duplicate_name"))
        duplicate_note.setWordWrap(True)
        preview_layout.addWidget(time_hint)
        preview_layout.addWidget(naming_note)
        preview_layout.addWidget(duplicate_note)

        middle = QHBoxLayout()
        middle.addWidget(paths, 2)
        middle.addWidget(preview_box, 3)

        self.debug.setVisible(False)
        self.workers.setValue(1)
        self.workers.setEnabled(False)

        self.content.addLayout(middle, 1)
        self.content.addWidget(output_box)
        self.footer()
        self.run.clicked.connect(self.go)
        self.set_editor_enabled(False)

    def add_videos(self):
        start = str(Path.home())
        if self.videos:
            parent = Path(self.videos[-1].path).parent
            if parent.is_dir():
                start = str(parent)
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            txt(self.lang, "add"),
            start,
            txt(self.lang, "video_filter"),
        )
        if not paths:
            return

        existing = {str(Path(video.path).resolve()) for video in self.videos}
        first_new = None
        failures = []
        for path in paths:
            try:
                key = str(Path(path).resolve())
                if key in existing:
                    continue
                video = probe_video(path, self.lang)
                existing.add(key)
                self.videos.append(video)
                self.video_list.addItem("")
                row = len(self.videos) - 1
                self.refresh_item(row)
                if first_new is None:
                    first_new = row
            except Exception as exc:
                failures.append(f"{Path(path).name}: {exc}")

        if first_new is not None:
            self.video_list.setCurrentRow(first_new)
        if failures:
            QMessageBox.warning(
                self,
                txt(self.lang, "probe_failed"),
                "\n".join(failures),
            )

    def remove_selected(self):
        row = self.video_list.currentRow()
        if row < 0:
            return
        self.videos.pop(row)
        self.video_list.takeItem(row)
        if self.videos:
            self.video_list.setCurrentRow(min(row, len(self.videos) - 1))
        else:
            self.select_row(-1)

    def clear_videos(self):
        self.videos.clear()
        self.video_list.clear()
        self.select_row(-1)

    def refresh_item(self, row: int):
        if not (0 <= row < len(self.videos)):
            return
        video = self.videos[row]
        self.video_list.item(row).setText(
            f"{Path(video.path).name}    {format_time(video.start)} → {format_time(video.normalized_end())}"
        )
        self.video_list.item(row).setToolTip(video.path)

    def select_row(self, row: int):
        if not (0 <= row < len(self.videos)):
            self.preview_image = QPixmap()
            self.preview.clear()
            self.preview.setText(txt(self.lang, "preview_empty"))
            self.duration_label.setText("-")
            self.fps_label.setText("-")
            self.start_edit.clear()
            self.end_edit.clear()
            self.set_editor_enabled(False)
            return

        self.set_editor_enabled(True)
        video = self.videos[row]
        self.duration_label.setText(format_time(video.duration))
        self.fps_label.setText(f"{video.fps:.6f} fps")
        self.start_edit.setText(format_time(video.start))
        self.end_edit.setText(format_time(video.normalized_end()))
        maximum = max(1, int(round(video.duration * 1000.0)))
        self.range_slider.set_range(0, maximum)
        self.range_slider.set_values(
            int(round(video.start * 1000.0)),
            int(round(video.normalized_end() * 1000.0)),
            emit=False,
        )
        preview_at = video.start if video.start < video.duration else max(0.0, video.duration - 1.0 / video.fps)
        self.load_preview(preview_at)

    def set_editor_enabled(self, enabled: bool):
        self.start_edit.setEnabled(enabled)
        self.end_edit.setEnabled(enabled)
        self.range_slider.setEnabled(enabled)

    def range_changed(self, lower_ms: int, upper_ms: int, active: int):
        row = self.video_list.currentRow()
        if not (0 <= row < len(self.videos)):
            return
        video = self.videos[row]
        video.start = max(0.0, min(lower_ms / 1000.0, video.duration))
        video.end = max(video.start, min(upper_ms / 1000.0, video.duration))
        self.start_edit.setText(format_time(video.start))
        self.end_edit.setText(format_time(video.normalized_end()))
        self.refresh_item(row)
        self.load_preview(video.start if active == 0 else video.normalized_end())

    def commit_time(self, which: str):
        row = self.video_list.currentRow()
        if not (0 <= row < len(self.videos)):
            return
        video = self.videos[row]
        edit = self.start_edit if which == "start" else self.end_edit
        try:
            value = min(parse_time(edit.text()), video.duration)
        except Exception:
            QMessageBox.warning(
                self,
                tr(self.lang, "missing"),
                txt(self.lang, "invalid_time", value=edit.text()),
            )
            self.start_edit.setText(format_time(video.start))
            self.end_edit.setText(format_time(video.normalized_end()))
            return

        if which == "start":
            video.start = min(value, video.normalized_end())
        else:
            video.end = max(video.start, value)

        self.start_edit.setText(format_time(video.start))
        self.end_edit.setText(format_time(video.normalized_end()))
        self.range_slider.set_values(
            int(round(video.start * 1000.0)),
            int(round(video.normalized_end() * 1000.0)),
            emit=False,
        )
        self.refresh_item(row)
        self.load_preview(video.start if which == "start" else video.normalized_end())

    def load_preview(self, seconds: float):
        row = self.video_list.currentRow()
        if not (0 <= row < len(self.videos)):
            return
        video = self.videos[row]
        if video.frame_count <= 0:
            return

        frame_index = int(math.ceil(max(0.0, seconds) * video.fps - 1e-9))
        frame_index = max(0, min(frame_index, video.frame_count - 1))
        cap = cv2.VideoCapture(video.path)
        if not cap.isOpened():
            cap.release()
            return
        try:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ret, frame = cap.read()
        finally:
            cap.release()
        if not ret:
            return

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape
        image = QImage(
            rgb.data,
            width,
            height,
            channels * width,
            QImage.Format.Format_RGB888,
        ).copy()
        self.preview_image = QPixmap.fromImage(image)
        self.update_preview_pixmap()

    def update_preview_pixmap(self):
        if self.preview_image.isNull():
            return
        target = self.preview.size()
        if target.width() < 10 or target.height() < 10:
            return
        self.preview.setPixmap(
            self.preview_image.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_preview_pixmap()

    def go(self):
        if not self.videos:
            QMessageBox.warning(self, tr(self.lang, "missing"), txt(self.lang, "select_videos"))
            return
        if not self.output.text():
            QMessageBox.warning(self, tr(self.lang, "missing"), txt(self.lang, "select_output"))
            return

        videos = [
            {
                "path": video.path,
                "fps": video.fps,
                "frame_count": video.frame_count,
                "duration": video.duration,
                "start": video.start,
                "end": video.normalized_end(),
            }
            for video in self.videos
        ]
        self.start(
            export_video_frames_tool12,
            {
                "videos": videos,
                "output_folder": self.output.text(),
                "lang": self.lang,
                "workers": 1,
                "debug": False,
            },
        )


class MainWindow(coord_ui.MainWindow):
    def task_tabs(self):
        return tuple(
            tab
            for tab in (
                getattr(self, "a", None),
                getattr(self, "b", None),
                getattr(self, "c", None),
                getattr(self, "d", None),
                getattr(self, "e", None),
            )
            if tab is not None
        )

    def build(self):
        old = self.centralWidget()
        self.tabs = QTabWidget()
        self.a = ui.MatchTab(self.lang)
        self.b = ui.CenterTab(self.lang)
        self.c = coord_ui.CoordTab(self.lang)
        self.d = coord_ui.ResizeTab(self.lang)
        self.e = VideoTab(self.lang)
        self.tabs.addTab(self.a, tr(self.lang, "tab1"))
        self.tabs.addTab(self.b, tr(self.lang, "tab2"))
        self.tabs.addTab(self.c, tr(self.lang, "tab3"))
        self.tabs.addTab(self.d, tr(self.lang, "tab4"))
        self.tabs.addTab(self.e, txt(self.lang, "tab"))
        self.setCentralWidget(self.tabs)
        if old:
            old.deleteLater()
        self.lang_label.setText(tr(self.lang, "language"))
        self.statusBar().showMessage(tr(self.lang, "status"))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CIPA Crop & Coord")
    app.setOrganizationName("CIPA")
    app.setStyleSheet(ui.STYLE)
    window = MainWindow()
    window.show()
    return app.exec()
