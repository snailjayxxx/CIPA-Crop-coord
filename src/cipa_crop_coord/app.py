from __future__ import annotations

import sys
import threading
import traceback
from pathlib import Path
from typing import Callable

from PIL import Image
from PySide6.QtCore import QObject, QPoint, QRect, QSize, Qt, QThread, Signal, Slot
from PySide6.QtGui import QCloseEvent, QImageReader, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .core import (
    BatchSummary,
    MatchSettings,
    ProcessingCancelled,
    Rect,
    batch_center_crop,
    batch_export_coordinates,
    batch_match_crop,
)


APP_STYLE = """
QWidget { font-size: 13px; }
QMainWindow { background: #f5f6f8; }
QGroupBox {
    font-weight: 600;
    border: 1px solid #d4d8df;
    border-radius: 7px;
    margin-top: 10px;
    padding: 12px 8px 8px 8px;
    background: white;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit {
    border: 1px solid #c9ced7; border-radius: 5px; padding: 5px; background: white;
}
QPushButton {
    border: 1px solid #b8bec8; border-radius: 5px; padding: 6px 12px; background: #fff;
}
QPushButton:hover { background: #eef3fb; }
QPushButton#primary {
    color: white; background: #1769e0; border-color: #1769e0; font-weight: 600;
}
QPushButton#primary:disabled { background: #9db9df; border-color: #9db9df; }
QProgressBar { border: 1px solid #c9ced7; border-radius: 5px; text-align: center; }
QProgressBar::chunk { background: #2d7be8; border-radius: 4px; }
QTabWidget::pane { border: 1px solid #d4d8df; background: #f5f6f8; }
QTabBar::tab { padding: 9px 18px; background: #e8ebf0; }
QTabBar::tab:selected { background: white; font-weight: 600; }
"""


class PathChooser(QWidget):
    def __init__(self, mode: str, save_filter: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.mode = mode
        self.save_filter = save_filter
        self.edit = QLineEdit()
        button = QPushButton("浏览…")
        button.clicked.connect(self._browse)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.edit, 1)
        layout.addWidget(button)

    def text(self) -> str:
        return self.edit.text().strip()

    @Slot()
    def _browse(self) -> None:
        current = self.text() or str(Path.home())
        if self.mode == "folder":
            value = QFileDialog.getExistingDirectory(self, "选择文件夹", current)
        elif self.mode == "save":
            value, _ = QFileDialog.getSaveFileName(
                self, "选择保存文件", current, self.save_filter
            )
        else:
            value, _ = QFileDialog.getOpenFileName(
                self,
                "选择图片",
                current,
                "图片 (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp);;所有文件 (*)",
            )
        if value:
            self.edit.setText(value)


class SelectionLabel(QLabel):
    selection_changed = Signal(QRect)

    def __init__(self, pixmap: QPixmap):
        super().__init__()
        self.setPixmap(pixmap)
        self.setFixedSize(pixmap.size())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._origin = QPoint()
        self._selection = QRect()
        self._dragging = False

    @property
    def selection(self) -> QRect:
        return self._selection.normalized()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._selection = QRect(self._origin, QSize())
            self._dragging = True
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            point = event.position().toPoint()
            point.setX(max(0, min(point.x(), self.width() - 1)))
            point.setY(max(0, min(point.y(), self.height() - 1)))
            self._selection = QRect(self._origin, point).normalized()
            self.selection_changed.emit(self.selection)
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self.selection_changed.emit(self.selection)
            self.update()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().paintEvent(event)
        if not self.selection.isNull():
            from PySide6.QtGui import QColor, QPainter, QPen

            painter = QPainter(self)
            painter.fillRect(self.selection, QColor(23, 105, 224, 45))
            painter.setPen(QPen(QColor("#1769e0"), 2))
            painter.drawRect(self.selection)


class ImageRegionDialog(QDialog):
    def __init__(self, image_path: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("在图片上拖动选择范围")
        self.resize(1000, 700)
        self._oriented_size = self._read_oriented_size(image_path)
        preview = self._read_preview(image_path)
        self._label = SelectionLabel(QPixmap.fromImage(preview))
        self._label.selection_changed.connect(self._update_text)
        self._status = QLabel("按住鼠标左键拖动选择；不选择代表整张图片。")

        scroll = QScrollArea()
        scroll.setWidget(self._label)
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll.setWidgetResizable(False)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(scroll, 1)
        layout.addWidget(self._status)
        layout.addWidget(buttons)

    @staticmethod
    def _read_oriented_size(path: str) -> tuple[int, int]:
        with Image.open(path) as image:
            width, height = image.size
            orientation = image.getexif().get(274, 1)
        return (height, width) if orientation in {5, 6, 7, 8} else (width, height)

    def _read_preview(self, path: str):
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        raw_size = reader.size()
        if not raw_size.isValid():
            raise ValueError("无法读取图片尺寸")
        target = raw_size.scaled(QSize(1400, 850), Qt.AspectRatioMode.KeepAspectRatio)
        reader.setScaledSize(target)
        image = reader.read()
        if image.isNull():
            raise ValueError(f"无法生成预览：{reader.errorString()}")
        return image

    def selected_rect(self) -> Rect:
        selection = self._label.selection
        if selection.width() < 2 or selection.height() < 2:
            return Rect()
        full_width, full_height = self._oriented_size
        scale_x = full_width / self._label.width()
        scale_y = full_height / self._label.height()
        x = round(selection.x() * scale_x)
        y = round(selection.y() * scale_y)
        width = max(1, round(selection.width() * scale_x))
        height = max(1, round(selection.height() * scale_y))
        return Rect(x, y, min(width, full_width - x), min(height, full_height - y))

    @Slot(QRect)
    def _update_text(self, _: QRect) -> None:
        rect = self.selected_rect()
        self._status.setText(
            f"当前范围：x={rect.x}, y={rect.y}, 宽={rect.width}, 高={rect.height}"
        )


class RegionEditor(QWidget):
    def __init__(
        self,
        select_image: Callable[[], str],
        zero_means: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._select_image = select_image
        self.spins: list[QSpinBox] = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for label_text in ("x", "y", "宽", "高"):
            layout.addWidget(QLabel(label_text))
            spin = QSpinBox()
            spin.setRange(0, 200_000)
            spin.setFixedWidth(94)
            self.spins.append(spin)
            layout.addWidget(spin)
        select_button = QPushButton("在图片上选择…")
        select_button.clicked.connect(self._select)
        layout.addWidget(select_button)
        layout.addWidget(QLabel(zero_means), 1)

    def rect(self) -> Rect:
        return Rect(*(spin.value() for spin in self.spins))

    @Slot()
    def _select(self) -> None:
        path = self._select_image()
        if not path:
            return
        try:
            dialog = ImageRegionDialog(path, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                rect = dialog.selected_rect()
                for spin, value in zip(
                    self.spins, (rect.x, rect.y, rect.width, rect.height)
                ):
                    spin.setValue(value)
        except Exception as exc:
            QMessageBox.warning(self, "无法打开预览", str(exc))


class Worker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, task: Callable[..., BatchSummary], kwargs: dict):
        super().__init__()
        self.task = task
        self.kwargs = kwargs
        self.cancel_event = threading.Event()

    @Slot()
    def run(self) -> None:
        try:
            summary = self.task(
                **self.kwargs,
                progress=lambda current, total, message: self.progress.emit(
                    current, total, message
                ),
                cancelled=self.cancel_event.is_set,
            )
            self.finished.emit(summary)
        except ProcessingCancelled:
            self.failed.emit("处理已取消。已经保存的文件不会被删除。")
        except Exception:
            self.failed.emit(traceback.format_exc())

    def cancel(self) -> None:
        self.cancel_event.set()


class BatchTab(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: Worker | None = None
        self.content = QVBoxLayout(self)
        self.content.setContentsMargins(14, 14, 14, 14)
        self.content.setSpacing(10)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1000)
        self.log.setMinimumHeight(130)
        self.run_button = QPushButton("开始处理")
        self.run_button.setObjectName("primary")
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)

    def add_footer(self) -> None:
        self.content.addWidget(self.progress_bar)
        self.content.addWidget(self.log, 1)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.run_button)
        self.content.addLayout(buttons)

    def start_worker(self, task: Callable[..., BatchSummary], kwargs: dict) -> None:
        if self._thread is not None:
            return
        self.log.clear()
        self.progress_bar.setRange(0, 0)
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        thread = QThread(self)
        worker = Worker(task, kwargs)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_worker)
        self._thread = thread
        self._worker = worker
        thread.start()

    @Slot()
    def cancel(self) -> None:
        if self._worker:
            self.cancel_button.setEnabled(False)
            self.log.appendPlainText("正在等待当前图片处理完毕后取消…")
            self._worker.cancel()

    @Slot(int, int, str)
    def _on_progress(self, current: int, total: int, message: str) -> None:
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(current)
        self.log.appendPlainText(f"[{current}/{total}] {message}")

    @Slot(object)
    def _on_finished(self, summary: BatchSummary) -> None:
        self.log.appendPlainText(
            "\n处理结束："
            f"成功 {summary.succeeded}，未达阈值 {summary.skipped}，失败 {summary.failed}。"
        )
        QMessageBox.information(
            self,
            "处理完成",
            f"共 {summary.total} 张\n成功：{summary.succeeded}\n"
            f"未达阈值：{summary.skipped}\n失败：{summary.failed}\n\n"
            f"保存位置：{summary.output_path}",
        )

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self.log.appendPlainText(message)
        QMessageBox.warning(self, "处理未完成", message.splitlines()[-1])

    @Slot()
    def _clear_worker(self) -> None:
        self._thread = None
        self._worker = None
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        if self.progress_bar.maximum() == 0:
            self.progress_bar.setRange(0, 1)

    def is_running(self) -> bool:
        return self._thread is not None


class MatchOptions(QGroupBox):
    def __init__(
        self,
        sample: PathChooser,
        parent: QWidget | None = None,
    ):
        super().__init__("匹配范围与精度", parent)
        self.template_region = RegionEditor(
            sample.text, "宽/高为 0：使用整张 sample"
        )
        self._search_preview_path = ""
        self.search_region = RegionEditor(
            self._choose_search_preview,
            "宽/高为 0：搜索整张被遍历图片",
        )
        self.mask = QDoubleSpinBox()
        self.mask.setRange(0, 45)
        self.mask.setValue(10)
        self.mask.setSuffix(" %")
        self.mask.setToolTip("忽略 sample 模板四周的比例，只用中心区域进行匹配")
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(-1, 1)
        self.threshold.setDecimals(3)
        self.threshold.setSingleStep(0.01)
        self.threshold.setValue(0.70)
        self.threshold.setToolTip("越接近 1 越严格；通常可从 0.70 开始测试")

        form = QFormLayout(self)
        form.addRow("sample 有效范围：", self.template_region)
        form.addRow("被遍历图片搜索范围：", self.search_region)
        form.addRow("sample 边缘屏蔽：", self.mask)
        form.addRow("最低相似度：", self.threshold)

    def _choose_search_preview(self) -> str:
        value, _ = QFileDialog.getOpenFileName(
            self,
            "选择一张有代表性的被遍历图片",
            self._search_preview_path or str(Path.home()),
            "图片 (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp)",
        )
        if value:
            self._search_preview_path = value
        return value

    def settings(self) -> MatchSettings:
        return MatchSettings(
            template_rect=self.template_region.rect(),
            search_rect=self.search_region.rect(),
            edge_mask_percent=self.mask.value(),
            threshold=self.threshold.value(),
        )


def _quality_spin() -> QSpinBox:
    quality = QSpinBox()
    quality.setRange(1, 100)
    quality.setValue(95)
    quality.setSuffix(" %")
    return quality


def _require_paths(parent: QWidget, values: list[tuple[str, str]]) -> bool:
    missing = [label for label, value in values if not value]
    if missing:
        QMessageBox.warning(parent, "信息不完整", "请选择：" + "、".join(missing))
        return False
    return True


class MatchCropTab(BatchTab):
    def __init__(self):
        super().__init__()
        paths = QGroupBox("文件位置")
        form = QFormLayout(paths)
        self.sample = PathChooser("file")
        self.input_folder = PathChooser("folder")
        self.output_folder = PathChooser("folder")
        form.addRow("sample 图片：", self.sample)
        form.addRow("遍历文件夹（含子文件夹）：", self.input_folder)
        form.addRow("裁切图片保存文件夹：", self.output_folder)
        self.options = MatchOptions(self.sample)
        output = QGroupBox("输出设置")
        output_form = QFormLayout(output)
        self.quality = _quality_spin()
        output_form.addRow("JPEG 保存质量：", self.quality)
        output_form.addRow(
            "",
            QLabel("命名示例：1/100s + abc.jpg → 1_100_abc.jpg；无 EXIF 时以 unknown_ 开头。"),
        )
        self.content.addWidget(paths)
        self.content.addWidget(self.options)
        self.content.addWidget(output)
        self.add_footer()
        self.run_button.clicked.connect(self._start)

    @Slot()
    def _start(self) -> None:
        if not _require_paths(
            self,
            [
                ("sample 图片", self.sample.text()),
                ("遍历文件夹", self.input_folder.text()),
                ("保存文件夹", self.output_folder.text()),
            ],
        ):
            return
        self.start_worker(
            batch_match_crop,
            {
                "sample_path": self.sample.text(),
                "input_folder": self.input_folder.text(),
                "output_folder": self.output_folder.text(),
                "settings": self.options.settings(),
                "jpeg_quality": self.quality.value(),
            },
        )


class CenterCropTab(BatchTab):
    def __init__(self):
        super().__init__()
        paths = QGroupBox("文件位置")
        form = QFormLayout(paths)
        self.input_folder = PathChooser("folder")
        self.output_folder = PathChooser("folder")
        form.addRow("遍历文件夹（含子文件夹）：", self.input_folder)
        form.addRow("裁切图片保存文件夹：", self.output_folder)

        settings = QGroupBox("从图片中心裁切")
        grid = QGridLayout(settings)
        self.fixed_radio = QRadioButton("固定像素")
        self.ratio_radio = QRadioButton("原图比例")
        self.fixed_radio.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.fixed_radio)
        group.addButton(self.ratio_radio)
        self.width = QSpinBox()
        self.height = QSpinBox()
        for spin in (self.width, self.height):
            spin.setRange(1, 200_000)
            spin.setValue(1000)
            spin.setSuffix(" px")
        self.ratio = QLineEdit("1/3")
        self.ratio.setPlaceholderText("例如 1/3、1/4 或 0.5")
        self.ratio.setEnabled(False)
        self.fixed_radio.toggled.connect(self._toggle_mode)
        grid.addWidget(self.fixed_radio, 0, 0)
        grid.addWidget(QLabel("宽："), 0, 1)
        grid.addWidget(self.width, 0, 2)
        grid.addWidget(QLabel("高："), 0, 3)
        grid.addWidget(self.height, 0, 4)
        grid.addWidget(self.ratio_radio, 1, 0)
        grid.addWidget(QLabel("宽、高均取原图的："), 1, 1, 1, 2)
        grid.addWidget(self.ratio, 1, 3, 1, 2)

        output = QGroupBox("输出设置")
        output_form = QFormLayout(output)
        self.quality = _quality_spin()
        output_form.addRow("JPEG 保存质量：", self.quality)
        output_form.addRow(
            "",
            QLabel("裁切区域始终居中；文件名使用“快门速度_原文件名”。"),
        )
        self.content.addWidget(paths)
        self.content.addWidget(settings)
        self.content.addWidget(output)
        self.add_footer()
        self.run_button.clicked.connect(self._start)

    @Slot(bool)
    def _toggle_mode(self, fixed: bool) -> None:
        self.width.setEnabled(fixed)
        self.height.setEnabled(fixed)
        self.ratio.setEnabled(not fixed)

    @Slot()
    def _start(self) -> None:
        if not _require_paths(
            self,
            [
                ("遍历文件夹", self.input_folder.text()),
                ("保存文件夹", self.output_folder.text()),
            ],
        ):
            return
        kwargs = {
            "input_folder": self.input_folder.text(),
            "output_folder": self.output_folder.text(),
            "jpeg_quality": self.quality.value(),
        }
        if self.fixed_radio.isChecked():
            kwargs.update(width=self.width.value(), height=self.height.value())
        else:
            kwargs.update(ratio=self.ratio.text().strip())
        self.start_worker(batch_center_crop, kwargs)


class CoordinateTab(BatchTab):
    def __init__(self):
        super().__init__()
        paths = QGroupBox("文件位置")
        form = QFormLayout(paths)
        self.sample = PathChooser("file")
        self.input_folder = PathChooser("folder")
        self.csv_path = PathChooser("save", "CSV 文件 (*.csv)")
        form.addRow("sample 图片：", self.sample)
        form.addRow("遍历文件夹（含子文件夹）：", self.input_folder)
        form.addRow("CSV 保存位置：", self.csv_path)
        self.options = MatchOptions(self.sample)
        note = QLabel(
            "CSV 固定为三列：文件名、x坐标、y坐标。坐标是 sample 中心点在被遍历图片中的像素位置；"
            "未匹配到的图片也会保留一行，坐标为空。"
        )
        note.setWordWrap(True)
        self.content.addWidget(paths)
        self.content.addWidget(self.options)
        self.content.addWidget(note)
        self.add_footer()
        self.run_button.clicked.connect(self._start)

    @Slot()
    def _start(self) -> None:
        if not _require_paths(
            self,
            [
                ("sample 图片", self.sample.text()),
                ("遍历文件夹", self.input_folder.text()),
                ("CSV 保存位置", self.csv_path.text()),
            ],
        ):
            return
        csv_path = self.csv_path.text()
        if Path(csv_path).suffix.lower() != ".csv":
            csv_path += ".csv"
            self.csv_path.edit.setText(csv_path)
        self.start_worker(
            batch_export_coordinates,
            {
                "sample_path": self.sample.text(),
                "input_folder": self.input_folder.text(),
                "csv_path": csv_path,
                "settings": self.options.settings(),
            },
        )


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CIPA Crop & Coord")
        self.resize(1120, 830)
        self.setMinimumSize(900, 680)
        self.tabs = QTabWidget()
        self.match_crop_tab = MatchCropTab()
        self.center_crop_tab = CenterCropTab()
        self.coordinate_tab = CoordinateTab()
        self.tabs.addTab(self.match_crop_tab, "① 相似区域裁切")
        self.tabs.addTab(self.center_crop_tab, "② 中心裁切")
        self.tabs.addTab(self.coordinate_tab, "③ 坐标导出")
        self.setCentralWidget(self.tabs)
        self.statusBar().showMessage(
            "支持 JPG / PNG / BMP / TIFF / WebP；所有文件夹均递归遍历子文件夹。"
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        running = any(
            tab.is_running()
            for tab in (
                self.match_crop_tab,
                self.center_crop_tab,
                self.coordinate_tab,
            )
        )
        if not running:
            event.accept()
            return
        answer = QMessageBox.question(
            self,
            "仍在处理",
            "任务仍在运行。请先取消并等待当前图片处理结束，再关闭程序。",
        )
        if answer:
            event.ignore()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("CIPA Crop & Coord")
    app.setOrganizationName("CIPA")
    app.setStyleSheet(APP_STYLE)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
