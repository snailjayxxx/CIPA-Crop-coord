from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from . import ui
from .image_to_video import create_video_from_images, list_images, resolve_output_file


TEXT = {
    "zh": {
        "tab": "⑥ 图片生成视频",
        "group": "图片序列与视频设置",
        "input": "图片文件夹：",
        "output": "MP4 保存位置：",
        "browse": "浏览…",
        "fps": "每秒图片数（FPS）：",
        "count": "视频总帧数：",
        "all": "使用全部图片",
        "found": "检测到图片：{count} 张",
        "duration": "预计视频时长：{duration:.3f} 秒",
        "note": "按文件名进行自然排序。数量少于实际图片时截断；数量多于实际图片时，末尾自动补黑屏。不同尺寸的图片会等比例缩放并用黑边补齐，视频尺寸以第一张可读取图片为准。",
        "choose_input": "请选择图片文件夹。",
        "choose_output": "请选择 MP4 保存位置。",
        "output_hint": "可填写完整 MP4 文件名，或粘贴保存文件夹路径",
        "overwrite_title": "替换已有视频？",
        "overwrite": "以下文件已存在，是否替换？\n{path}",
        "yes": "是",
        "no": "否",
        "no_images": "所选文件夹内没有可用图片。若要制作纯黑视频，请将总帧数设为大于 0。",
        "folder_title": "选择图片文件夹",
        "save_title": "保存 MP4 视频",
        "filter": "MP4 视频 (*.mp4)",
    },
    "ja": {
        "tab": "⑥ 画像から動画作成",
        "group": "画像シーケンスと動画設定",
        "input": "画像フォルダー：",
        "output": "MP4 保存先：",
        "browse": "参照…",
        "fps": "1秒あたりの画像数（FPS）：",
        "count": "動画の総フレーム数：",
        "all": "すべての画像を使用",
        "found": "検出画像：{count} 枚",
        "duration": "予定動画時間：{duration:.3f} 秒",
        "note": "ファイル名を自然順で並べます。指定数が画像数より少ない場合は打ち切り、多い場合は末尾を黒画面で補完します。サイズが異なる画像は縦横比を維持して黒帯で調整し、動画サイズは最初に読み込めた画像に合わせます。",
        "choose_input": "画像フォルダーを選択してください。",
        "choose_output": "MP4 の保存先を選択してください。",
        "output_hint": "MP4 ファイル名または保存先フォルダーのパスを入力",
        "overwrite_title": "既存の動画を上書きしますか？",
        "overwrite": "次のファイルは既に存在します。上書きしますか？\n{path}",
        "yes": "はい",
        "no": "いいえ",
        "no_images": "選択フォルダーに使用可能な画像がありません。黒画面のみの動画を作る場合は、総フレーム数を 1 以上に設定してください。",
        "folder_title": "画像フォルダーを選択",
        "save_title": "MP4 動画を保存",
        "filter": "MP4 動画 (*.mp4)",
    },
    "en": {
        "tab": "⑥ Images to Video",
        "group": "Image sequence and video settings",
        "input": "Image folder:",
        "output": "MP4 output file:",
        "browse": "Browse…",
        "fps": "Images per second (FPS):",
        "count": "Total video frames:",
        "all": "Use all images",
        "found": "Images found: {count}",
        "duration": "Estimated duration: {duration:.3f} seconds",
        "note": "Images are read in natural filename order. A smaller target truncates the sequence; a larger target appends black frames. Different image sizes are fitted without distortion and padded with black; the first readable image defines the video size.",
        "choose_input": "Select an image folder.",
        "choose_output": "Select an MP4 output file.",
        "output_hint": "Enter an MP4 filename or paste an output folder path",
        "overwrite_title": "Replace existing video?",
        "overwrite": "This file already exists. Replace it?\n{path}",
        "yes": "Yes",
        "no": "No",
        "no_images": "No usable images were found. Set the total frame count above zero to create an all-black video.",
        "folder_title": "Select image folder",
        "save_title": "Save MP4 video",
        "filter": "MP4 video (*.mp4)",
    },
}


def txt(lang: str, key: str) -> str:
    return TEXT.get(lang, TEXT["zh"])[key]


class BrowseRow(QWidget):
    def __init__(self, lang: str, mode: str):
        super().__init__()
        self.lang = lang
        self.mode = mode
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        button = QPushButton(txt(lang, "browse"))
        button.clicked.connect(self.browse)
        row.addWidget(self.edit, 1)
        row.addWidget(button)

    def text(self) -> str:
        return self.edit.text().strip()

    def browse(self) -> None:
        if self.mode == "folder":
            selected = QFileDialog.getExistingDirectory(
                self, txt(self.lang, "folder_title"), self.text()
            )
        else:
            start = self.text() or str(Path.home() / "image_sequence.mp4")
            selected, _ = QFileDialog.getSaveFileName(
                self, txt(self.lang, "save_title"), start, txt(self.lang, "filter")
            )
            if selected and Path(selected).suffix.casefold() != ".mp4":
                selected += ".mp4"
        if selected:
            self.edit.setText(selected)


class ImageToVideoTab(ui.BatchTab):
    def __init__(self, lang: str):
        super().__init__(lang)
        box = QGroupBox(txt(lang, "group"))
        form = QFormLayout(box)
        self.input = BrowseRow(lang, "folder")
        self.output = BrowseRow(lang, "save")
        self.output.edit.setPlaceholderText(txt(lang, "output_hint"))
        self.fps = QDoubleSpinBox()
        self.fps.setRange(0.1, 240.0)
        self.fps.setDecimals(3)
        self.fps.setValue(10.0)
        self.fps.setSuffix(" fps")
        self.count = QSpinBox()
        self.count.setRange(0, 10_000_000)
        self.count.setSpecialValueText(txt(lang, "all"))
        self.found = QLabel(txt(lang, "found").format(count=0))
        self.duration = QLabel(txt(lang, "duration").format(duration=0.0))
        form.addRow(txt(lang, "input"), self.input)
        form.addRow("", self.found)
        form.addRow(txt(lang, "output"), self.output)
        form.addRow(txt(lang, "fps"), self.fps)
        form.addRow(txt(lang, "count"), self.count)
        form.addRow("", self.duration)
        note = QLabel(txt(lang, "note"))
        note.setWordWrap(True)
        note_box = QGroupBox()
        note_layout = QVBoxLayout(note_box)
        note_layout.addWidget(note)
        self.content.addWidget(box)
        self.content.addWidget(note_box)
        self.content.addStretch(1)
        self.footer()
        self.workers.setValue(1)
        self.workers.setEnabled(False)
        self.debug.setVisible(False)
        self.run.clicked.connect(self.go)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(250)
        self._refresh_timer.timeout.connect(self.refresh_count)
        self.input.edit.textChanged.connect(lambda: self._refresh_timer.start())
        self.count.valueChanged.connect(self.refresh_duration)
        self.fps.valueChanged.connect(self.refresh_duration)

    def refresh_count(self) -> None:
        actual = len(list_images(self.input.text()))
        self.found.setText(txt(self.lang, "found").format(count=actual))
        self.refresh_duration()

    def refresh_duration(self) -> None:
        actual = len(list_images(self.input.text()))
        frames = self.count.value() or actual
        seconds = frames / self.fps.value() if self.fps.value() else 0.0
        self.duration.setText(txt(self.lang, "duration").format(duration=seconds))

    def go(self) -> None:
        input_folder = self.input.text()
        output_file = self.output.text()
        if not input_folder or not Path(input_folder).is_dir():
            QMessageBox.warning(self, "CIPA Crop & Coord", txt(self.lang, "choose_input"))
            return
        if not output_file:
            QMessageBox.warning(self, "CIPA Crop & Coord", txt(self.lang, "choose_output"))
            return
        actual = len(list_images(input_folder))
        if actual == 0 and self.count.value() == 0:
            QMessageBox.warning(self, "CIPA Crop & Coord", txt(self.lang, "no_images"))
            return
        destination = resolve_output_file(output_file, input_folder, self.lang)
        self.output.edit.setText(str(destination))
        if destination.exists():
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Icon.Question)
            dialog.setWindowTitle(txt(self.lang, "overwrite_title"))
            dialog.setText(txt(self.lang, "overwrite").format(path=destination))
            dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            dialog.button(QMessageBox.StandardButton.Yes).setText(txt(self.lang, "yes"))
            dialog.button(QMessageBox.StandardButton.No).setText(txt(self.lang, "no"))
            dialog.setDefaultButton(QMessageBox.StandardButton.No)
            choice = dialog.exec()
            dialog.deleteLater()
            if choice != QMessageBox.StandardButton.Yes:
                return
        self.start(
            create_video_from_images,
            {
                "input_folder": input_folder,
                "output_file": str(destination),
                "fps": self.fps.value(),
                "frame_count": self.count.value(),
                "lang": self.lang,
            },
        )
