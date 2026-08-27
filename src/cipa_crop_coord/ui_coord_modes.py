from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFormLayout,
    QGroupBox,
    QLabel,
    QRadioButton,
    QTabWidget,
    QVBoxLayout,
)

from .coord_export import (
    MODE_ABSOLUTE,
    MODE_RELATIVE_FIRST,
    MODE_RELATIVE_PREVIOUS,
    export_coords_python,
)
from .locales import tr
from . import ui


TEXT = {
    "zh": {
        "template": "特征模板图片：",
        "mode_group": "坐标记录模式",
        "absolute": "绝对特征点坐标",
        "absolute_note": "每张图片直接记录识别到的特征点中心 x / y 像素坐标，不减去任何基准坐标。",
        "relative_previous": "相对上一张坐标",
        "relative_previous_note": "同一文件夹内第一张记录为 (0, 0)；之后每张 = 当前特征点中心坐标 − 上一张特征点中心坐标。进入新的子文件夹后重新从 (0, 0) 开始。",
        "relative_first": "相对第一张坐标",
        "relative_first_note": "同一文件夹内第一张记录为 (0, 0)；之后每张 = 当前特征点中心坐标 − 第一张特征点中心坐标。这个模式对应来源 Python 的 calc_center_point() 处理方式。",
        "algorithm": "三种模式共用完全相同的特征点识别：彩色图片直接执行 cv2.matchTemplate(..., TM_CCOEFF_NORMED) → cv2.minMaxLoc 取得最大相似位置 → 记录模板框中心。三种模式只改变坐标导出时的后处理方式。",
    },
    "ja": {
        "template": "特徴テンプレート画像：",
        "mode_group": "座標記録モード",
        "absolute": "特徴点の絶対座標",
        "absolute_note": "各画像で検出した特徴点中心の x / y ピクセル座標をそのまま記録し、基準座標を差し引きません。",
        "relative_previous": "1つ前の画像に対する相対座標",
        "relative_previous_note": "同一フォルダー内の1枚目は (0, 0)。2枚目以降は「現在の特徴点中心 − 1つ前の画像の特徴点中心」を記録します。別のサブフォルダーに移ると (0, 0) から再開します。",
        "relative_first": "1枚目の画像に対する相対座標",
        "relative_first_note": "同一フォルダー内の1枚目は (0, 0)。2枚目以降は「現在の特徴点中心 − 1枚目の特徴点中心」を記録します。このモードは元 Python の calc_center_point() と同じ後処理です。",
        "algorithm": "3つのモードはすべて同じ特徴点検出方法を使用します。カラー画像のまま cv2.matchTemplate(..., TM_CCOEFF_NORMED) → cv2.minMaxLoc の最大一致位置 → テンプレート枠中心を記録します。違いは座標出力時の後処理だけです。",
    },
}


def txt(lang: str, key: str) -> str:
    return TEXT["ja" if lang == "ja" else "zh"][key]


class CoordTab(ui.BatchTab):
    def __init__(self, lang):
        super().__init__(lang)

        paths = QGroupBox(tr(lang, "paths"))
        form = QFormLayout(paths)
        self.sample = ui.PathChooser(lang, "file")
        self.input = ui.PathChooser(lang, "folder")
        self.csv = ui.PathChooser(lang, "save", "csv_filter")
        form.addRow(txt(lang, "template"), self.sample)
        form.addRow(tr(lang, "input"), self.input)
        form.addRow(tr(lang, "csv"), self.csv)

        modes = QGroupBox(txt(lang, "mode_group"))
        mode_layout = QVBoxLayout(modes)
        self.absolute = QRadioButton(txt(lang, "absolute"))
        self.relative_previous = QRadioButton(txt(lang, "relative_previous"))
        self.relative_first = QRadioButton(txt(lang, "relative_first"))
        self.relative_previous.setChecked(True)

        group = QButtonGroup(self)
        group.addButton(self.absolute)
        group.addButton(self.relative_previous)
        group.addButton(self.relative_first)

        absolute_note = QLabel(txt(lang, "absolute_note"))
        absolute_note.setWordWrap(True)
        previous_note = QLabel(txt(lang, "relative_previous_note"))
        previous_note.setWordWrap(True)
        first_note = QLabel(txt(lang, "relative_first_note"))
        first_note.setWordWrap(True)

        mode_layout.addWidget(self.absolute)
        mode_layout.addWidget(absolute_note)
        mode_layout.addSpacing(6)
        mode_layout.addWidget(self.relative_previous)
        mode_layout.addWidget(previous_note)
        mode_layout.addSpacing(6)
        mode_layout.addWidget(self.relative_first)
        mode_layout.addWidget(first_note)

        algorithm = QLabel(txt(lang, "algorithm"))
        algorithm.setWordWrap(True)

        self.content.addWidget(paths)
        self.content.addWidget(modes)
        self.content.addWidget(algorithm)
        self.footer()
        self.run.clicked.connect(self.go)

    def selected_mode(self) -> str:
        if self.absolute.isChecked():
            return MODE_ABSOLUTE
        if self.relative_first.isChecked():
            return MODE_RELATIVE_FIRST
        return MODE_RELATIVE_PREVIOUS

    def go(self):
        if not ui.path_check(
            self,
            self.lang,
            [
                (txt(self.lang, "template"), self.sample.text()),
                (tr(self.lang, "input"), self.input.text()),
                (tr(self.lang, "csv"), self.csv.text()),
            ],
        ):
            return

        path = self.csv.text()
        path = path if Path(path).suffix.lower() == ".csv" else path + ".csv"
        self.csv.edit.setText(path)
        self.start(
            export_coords_python,
            {
                "sample": self.sample.text(),
                "input_folder": self.input.text(),
                "csv_path": path,
                "mode": self.selected_mode(),
                **self.common(),
            },
        )


class MainWindow(ui.MainWindow):
    def build(self):
        old = self.centralWidget()
        self.tabs = QTabWidget()
        self.a = ui.MatchTab(self.lang)
        self.b = ui.CenterTab(self.lang)
        self.c = CoordTab(self.lang)
        self.tabs.addTab(self.a, tr(self.lang, "tab1"))
        self.tabs.addTab(self.b, tr(self.lang, "tab2"))
        self.tabs.addTab(self.c, tr(self.lang, "tab3"))
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
