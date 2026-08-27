from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QLabel, QTabWidget

from . import ui
from . import ui_coord_modes as coord_ui
from . import ui_video_tool12 as video_ui
from .locales import tr


TEXT = {
    "zh": {
        "resize_note": "递归压缩所选文件夹及其子文件夹中的 .jpg 图片；保持文件名和子文件夹结构。",
        "video_note": "按所选时间范围逐帧导出 JPG 图片；不改变原视频画面尺寸，文件名使用原视频文件名和原始帧号。",
    },
    "ja": {
        "resize_note": "選択フォルダーとサブフォルダー内の .jpg 画像を再帰的に縮小し、ファイル名とサブフォルダー構成を維持します。",
        "video_note": "選択した時間範囲をフレームごとに JPG 出力します。元動画の画面サイズは変更せず、元動画名と元フレーム番号をファイル名に使用します。",
    },
    "en": {
        "resize_note": "Recursively resize .jpg images in the selected folder and its subfolders while preserving filenames and subfolder structure.",
        "video_note": "Export the selected time range frame by frame as JPG images without changing frame dimensions; filenames use the original video name and source frame number.",
    },
}


def text(lang: str, key: str) -> str:
    return TEXT.get(lang, TEXT["zh"])[key]


def _replace_tool_note(widget, token: str, replacement: str) -> None:
    for label in widget.findChildren(QLabel):
        if token in label.text():
            label.setText(replacement)


class ResizeTab(coord_ui.ResizeTab):
    def __init__(self, lang: str):
        super().__init__(lang)
        _replace_tool_note(self, "Tool 7", text(lang, "resize_note"))


class VideoTab(video_ui.VideoTab):
    def __init__(self, lang: str):
        super().__init__(lang)
        _replace_tool_note(self, "Tool 12", text(lang, "video_note"))


class MainWindow(video_ui.MainWindow):
    def build(self):
        old = self.centralWidget()
        self.tabs = QTabWidget()
        self.a = ui.MatchTab(self.lang)
        self.b = ui.CenterTab(self.lang)
        self.c = coord_ui.CoordTab(self.lang)
        self.d = ResizeTab(self.lang)
        self.e = VideoTab(self.lang)
        self.tabs.addTab(self.a, tr(self.lang, "tab1"))
        self.tabs.addTab(self.b, tr(self.lang, "tab2"))
        self.tabs.addTab(self.c, tr(self.lang, "tab3"))
        self.tabs.addTab(self.d, tr(self.lang, "tab4"))
        self.tabs.addTab(self.e, video_ui.txt(self.lang, "tab"))
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
