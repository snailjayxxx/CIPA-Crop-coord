from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QMainWindow,
    QMessageBox,
    QRadioButton,
    QSizePolicy,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .coord_export import (
    MODE_ABSOLUTE,
    MODE_RELATIVE_FIRST,
    MODE_RELATIVE_PREVIOUS,
    export_coords_python,
)
from .locales import tr
from .resize_tool7 import DEFAULT_RESIZE_RATIO, resize_images_tool7
from . import ui


TEXT = {
    "zh": {
        "template": "特征模板图片：",
        "mode_group": "坐标记录模式",
        "absolute": "绝对特征点坐标",
        "relative_previous": "相对上一张坐标",
        "relative_first": "相对第一张坐标",
        "resize_output": "压缩图片保存文件夹：",
    },
    "ja": {
        "template": "特徴テンプレート画像：",
        "mode_group": "座標記録モード",
        "absolute": "特徴点の絶対座標",
        "relative_previous": "1つ前の画像に対する相対座標",
        "relative_first": "1枚目の画像に対する相対座標",
        "resize_output": "圧縮画像の保存先：",
    },
    "en": {
        "template": "Feature template image:",
        "mode_group": "Coordinate mode",
        "absolute": "Absolute feature-point coordinates",
        "relative_previous": "Relative to previous image",
        "relative_first": "Relative to first image",
        "resize_output": "Compressed image output folder:",
    },
}


def txt(lang: str, key: str) -> str:
    return TEXT[lang if lang in TEXT else "zh"][key]


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

        mode_layout.addWidget(self.absolute)
        mode_layout.addWidget(self.relative_previous)
        mode_layout.addWidget(self.relative_first)

        self.content.addWidget(paths)
        self.content.addWidget(modes)
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


class ResizeTab(ui.BatchTab):
    def __init__(self, lang):
        super().__init__(lang)

        paths = QGroupBox(tr(lang, "paths"))
        path_form = QFormLayout(paths)
        self.input = ui.PathChooser(lang, "folder")
        self.output = ui.PathChooser(lang, "folder")
        path_form.addRow(tr(lang, "input"), self.input)
        path_form.addRow(txt(lang, "resize_output"), self.output)

        settings = QGroupBox(tr(lang, "resize_group"))
        form = QFormLayout(settings)
        self.ratio = ui.manual_number(QDoubleSpinBox())
        self.ratio.setRange(0.001, 10.0)
        self.ratio.setDecimals(4)
        self.ratio.setSingleStep(0.05)
        self.ratio.setValue(DEFAULT_RESIZE_RATIO)
        self.ratio.setMinimumWidth(140)
        form.addRow(tr(lang, "resize_ratio"), self.ratio)

        ratio_note = QLabel(tr(lang, "resize_ratio_note"))
        ratio_note.setWordWrap(True)
        source_note = QLabel(tr(lang, "resize_source_note"))
        source_note.setWordWrap(True)
        form.addRow("", ratio_note)
        form.addRow("", source_note)

        self.debug.setVisible(False)
        self.content.addWidget(paths)
        self.content.addWidget(settings)
        self.footer()
        self.run.clicked.connect(self.go)

    def go(self):
        if not ui.path_check(
            self,
            self.lang,
            [
                (tr(self.lang, "input"), self.input.text()),
                (txt(self.lang, "resize_output"), self.output.text()),
            ],
        ):
            return
        self.start(
            resize_images_tool7,
            {
                "input_folder": self.input.text(),
                "output_folder": self.output.text(),
                "ratio": self.ratio.value(),
                **self.common(),
            },
        )


class MainWindow(ui.MainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self.lang = "zh"
        self.setWindowTitle("CIPA Crop & Coord")
        self.resize(1180, 860)
        self.setMinimumSize(940, 700)

        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        self.lang_label = QLabel()
        toolbar.addWidget(self.lang_label)
        self.combo = QComboBox()
        self.combo.addItem("中文", "zh")
        self.combo.addItem("日本語", "ja")
        self.combo.addItem("English", "en")
        toolbar.addWidget(self.combo)
        self.combo.currentIndexChanged.connect(self.switch)
        self.build()

    def task_tabs(self):
        return tuple(
            tab for tab in (
                getattr(self, "a", None),
                getattr(self, "b", None),
                getattr(self, "c", None),
                getattr(self, "d", None),
            ) if tab is not None
        )

    def build(self):
        old = self.centralWidget()
        self.tabs = QTabWidget()
        self.a = ui.MatchTab(self.lang)
        self.b = ui.CenterTab(self.lang)
        self.c = CoordTab(self.lang)
        self.d = ResizeTab(self.lang)
        self.tabs.addTab(self.a, tr(self.lang, "tab1"))
        self.tabs.addTab(self.b, tr(self.lang, "tab2"))
        self.tabs.addTab(self.c, tr(self.lang, "tab3"))
        self.tabs.addTab(self.d, tr(self.lang, "tab4"))
        self.setCentralWidget(self.tabs)
        if old:
            old.deleteLater()
        self.lang_label.setText(tr(self.lang, "language"))
        self.statusBar().showMessage(tr(self.lang, "status"))

    def switch(self, index):
        new = self.combo.itemData(index)
        if new == self.lang:
            return
        if any(tab.running() for tab in self.task_tabs()):
            QMessageBox.information(self, tr(self.lang, "running"), tr(self.lang, "running_msg"))
            self.combo.blockSignals(True)
            restore = self.combo.findData(self.lang)
            self.combo.setCurrentIndex(max(0, restore))
            self.combo.blockSignals(False)
            return
        self.lang = new
        self.build()

    def closeEvent(self, event):
        if any(tab.running() for tab in self.task_tabs()):
            QMessageBox.information(self, tr(self.lang, "running"), tr(self.lang, "running_msg"))
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CIPA Crop & Coord")
    app.setOrganizationName("CIPA")
    app.setStyleSheet(ui.STYLE)
    window = MainWindow()
    window.show()
    return app.exec()
