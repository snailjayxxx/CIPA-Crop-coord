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

from .coord_export import MODE_ABSOLUTE, MODE_RELATIVE_PREVIOUS, export_coords_python
from .locales import tr
from . import ui


TEXT = {
    "zh": {
        "template": "特征模板图片：",
        "mode_group": "坐标记录模式",
        "relative": "相对移动坐标（相对上一张）",
        "relative_note": "同一文件夹内第一张记录为 (0, 0)；之后每张 = 当前特征点中心坐标 − 上一张特征点中心坐标。进入新的子文件夹后重新从 (0, 0) 开始。",
        "absolute": "绝对特征点坐标",
        "absolute_note": "每张图片直接记录识别到的特征点中心 x / y 像素坐标，不减去上一张或第一张的坐标。",
        "algorithm": "坐标识别完全采用来源 Python 的方法：彩色图片直接执行 cv2.matchTemplate(..., TM_CCOEFF_NORMED) → cv2.minMaxLoc 取得最大相似位置 → 记录模板框中心。坐标导出不使用灰度化、二值化、边缘屏蔽、搜索遮蔽、粗匹配/二次精修或最低相似度阈值。",
    },
    "ja": {
        "template": "特徴テンプレート画像：",
        "mode_group": "座標記録モード",
        "relative": "相対移動座標（1つ前の画像との差分）",
        "relative_note": "同一フォルダー内の1枚目は (0, 0) として記録し、2枚目以降は「現在の特徴点中心 − 1つ前の画像の特徴点中心」を記録します。別のサブフォルダーに移ると (0, 0) から再開します。",
        "absolute": "特徴点の絶対座標",
        "absolute_note": "各画像で検出した特徴点中心の x / y ピクセル座標をそのまま記録し、前画像や1枚目の座標は差し引きません。",
        "algorithm": "座標検出は元 Python と同じ方法を使用します。カラー画像のまま cv2.matchTemplate(..., TM_CCOEFF_NORMED) → cv2.minMaxLoc の最大一致位置 → テンプレート枠中心を記録します。グレースケール化、二値化、周辺除外、検索範囲除外、粗探索/再探索、最低類似度しきい値は座標出力では使用しません。",
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
        self.relative = QRadioButton(txt(lang, "relative"))
        self.absolute = QRadioButton(txt(lang, "absolute"))
        self.relative.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.relative)
        group.addButton(self.absolute)

        relative_note = QLabel(txt(lang, "relative_note"))
        relative_note.setWordWrap(True)
        absolute_note = QLabel(txt(lang, "absolute_note"))
        absolute_note.setWordWrap(True)
        mode_layout.addWidget(self.relative)
        mode_layout.addWidget(relative_note)
        mode_layout.addSpacing(6)
        mode_layout.addWidget(self.absolute)
        mode_layout.addWidget(absolute_note)

        algorithm = QLabel(txt(lang, "algorithm"))
        algorithm.setWordWrap(True)

        self.content.addWidget(paths)
        self.content.addWidget(modes)
        self.content.addWidget(algorithm)
        self.footer()
        self.run.clicked.connect(self.go)

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
        mode = MODE_RELATIVE_PREVIOUS if self.relative.isChecked() else MODE_ABSOLUTE
        self.start(
            export_coords_python,
            {
                "sample": self.sample.text(),
                "input_folder": self.input.text(),
                "csv_path": path,
                "mode": mode,
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
