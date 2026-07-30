from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Callable

from PIL import Image
from PySide6.QtCore import QObject, QPoint, QRect, QSize, Qt, QThread, Signal, Slot
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QImageReader,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
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
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .engine import (
    DEFAULT_SEARCH_MASK,
    DEFAULT_THRESHOLD,
    DEFAULT_WORKERS,
    Cancelled,
    MatchSettings,
    Rect,
    center_crop,
    center_rect,
    export_coords,
    match_crop,
)
from .locales import tr


STYLE = """
QWidget { font-size: 13px; }
QMainWindow { background: #f5f6f8; }
QGroupBox {
    font-weight: 600;
    border: 1px solid #d4d8df;
    border-radius: 7px;
    margin-top: 10px;
    padding: 12px 8px 8px;
    background: white;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QLineEdit, QPlainTextEdit {
    border: 1px solid #c9ced7;
    border-radius: 5px;
    padding: 5px;
    background: white;
}
QSpinBox, QDoubleSpinBox {
    border: 1px solid #c9ced7;
    border-radius: 5px;
    padding: 4px 6px;
    min-height: 26px;
    background: white;
}
QPushButton {
    border: 1px solid #b8bec8;
    border-radius: 5px;
    padding: 6px 12px;
    background: white;
}
QPushButton:hover { background: #eef3fb; }
QPushButton#primary {
    color: white;
    background: #1769e0;
    border-color: #1769e0;
    font-weight: 600;
}
QPushButton#primary:disabled {
    background: #9db9df;
    border-color: #9db9df;
}
QProgressBar {
    border: 1px solid #c9ced7;
    border-radius: 5px;
    text-align: center;
}
QProgressBar::chunk { background: #2d7be8; border-radius: 4px; }
QTabBar::tab { padding: 9px 18px; background: #e8ebf0; }
QTabBar::tab:selected { background: white; font-weight: 600; }
"""


def manual_number(spin):
    spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    return spin


def preferred_image_start(input_folder: str = "", fallback: str = "") -> str:
    """Prefer a selected traversal folder; otherwise keep previous/default behavior."""
    text = (input_folder or "").strip()
    if text:
        folder = Path(text)
        if folder.is_dir():
            return str(folder)
    return fallback or str(Path.home())


class PathChooser(QWidget):
    def __init__(self, lang, mode, save_key=""):
        super().__init__()
        self.lang = lang
        self.mode = mode
        self.save_key = save_key
        self.edit = QLineEdit()
        button = QPushButton(tr(lang, "browse"))
        button.clicked.connect(self.browse)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.edit, 1)
        layout.addWidget(button)

    def text(self):
        return self.edit.text().strip()

    def browse(self):
        current = self.text() or str(Path.home())
        if self.mode == "folder":
            value = QFileDialog.getExistingDirectory(self, tr(self.lang, "folder"), current)
        elif self.mode == "save":
            value, _ = QFileDialog.getSaveFileName(
                self, tr(self.lang, "save"), current, tr(self.lang, self.save_key)
            )
        else:
            value, _ = QFileDialog.getOpenFileName(
                self, tr(self.lang, "image"), current, tr(self.lang, "image_filter")
            )
        if value:
            self.edit.setText(value)


class SelectLabel(QLabel):
    changed = Signal()
    zoom = Signal(float)

    def __init__(self, pixmap):
        super().__init__()
        self.base = pixmap
        self.scale = 1.0
        self.origin = QPoint()
        self.sel = QRect()
        self.drag = False
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.set_scale(1)

    def set_scale(self, scale):
        self.scale = max(0.05, min(float(scale), 8))
        size = QSize(
            max(1, round(self.base.width() * self.scale)),
            max(1, round(self.base.height() * self.scale)),
        )
        self.setPixmap(
            self.base.scaled(
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.setFixedSize(size)
        self.update()

    def base_point(self, point):
        return QPoint(
            max(0, min(round(point.x() / self.scale), self.base.width() - 1)),
            max(0, min(round(point.y() / self.scale), self.base.height() - 1)),
        )

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = self.base_point(event.position().toPoint())
            self.sel = QRect(self.origin, QSize())
            self.drag = True
            self.update()

    def mouseMoveEvent(self, event):
        if self.drag:
            self.sel = QRect(
                self.origin, self.base_point(event.position().toPoint())
            ).normalized()
            self.changed.emit()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drag:
            self.drag = False
            self.changed.emit()
            self.update()

    def wheelEvent(self, event: QWheelEvent):
        self.zoom.emit(1.2 if event.angleDelta().y() > 0 else 1 / 1.2)
        event.accept()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.sel.width() > 0 and self.sel.height() > 0:
            painter = QPainter(self)
            rect = QRect(
                round(self.sel.x() * self.scale),
                round(self.sel.y() * self.scale),
                round(self.sel.width() * self.scale),
                round(self.sel.height() * self.scale),
            )
            painter.fillRect(rect, QColor(23, 105, 224, 45))
            painter.setPen(QPen(QColor("#1769e0"), 2))
            painter.drawRect(rect)


class RegionDialog(QDialog):
    def __init__(self, lang, path, initial: Rect | None = None, parent=None, help_text=None):
        super().__init__(parent)
        self.lang = lang
        self.setWindowTitle(tr(lang, "preview"))
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)
        self.resize(1200, 800)
        self.fit_mode = True
        self.full = self.oriented(path)

        reader = QImageReader(path)
        reader.setAutoTransform(True)
        size = reader.size().scaled(QSize(2600, 1800), Qt.AspectRatioMode.KeepAspectRatio)
        reader.setScaledSize(size)
        image = reader.read()
        if image.isNull():
            raise ValueError(tr(lang, "preview_fail"))

        self.label = SelectLabel(QPixmap.fromImage(image))
        self.label.changed.connect(self.status)
        self.label.zoom.connect(self.zoom_by)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.label)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)

        minus = QPushButton("−")
        plus = QPushButton("+")
        fit = QPushButton(tr(lang, "fit"))
        minus.clicked.connect(lambda: self.zoom_by(1 / 1.25))
        plus.clicked.connect(lambda: self.zoom_by(1.25))
        fit.clicked.connect(self.fit)
        tools = QHBoxLayout()
        tools.addWidget(minus)
        tools.addWidget(plus)
        tools.addWidget(fit)
        tools.addStretch()

        self.help = QLabel(help_text or tr(lang, "preview_help"))
        self.help.setWordWrap(True)
        self.info = QLabel()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(tools)
        layout.addWidget(self.scroll, 1)
        layout.addWidget(self.help)
        layout.addWidget(self.info)
        layout.addWidget(buttons)

        if initial and initial.width > 0 and initial.height > 0:
            self.set_initial(initial)
        self.status()

    @staticmethod
    def oriented(path):
        with Image.open(path) as image:
            width, height = image.size
            orientation = image.getexif().get(274, 1)
        return (height, width) if orientation in {5, 6, 7, 8} else (width, height)

    def set_initial(self, rect):
        full_width, full_height = self.full
        base_width, base_height = self.label.base.width(), self.label.base.height()
        self.label.sel = QRect(
            round(rect.x * base_width / full_width),
            round(rect.y * base_height / full_height),
            max(1, round(rect.width * base_width / full_width)),
            max(1, round(rect.height * base_height / full_height)),
        )

    def rect(self):
        rect = self.label.sel.normalized()
        full_width, full_height = self.full
        base_width, base_height = self.label.base.width(), self.label.base.height()
        if rect.width() < 2 or rect.height() < 2:
            return Rect()
        x = round(rect.x() * full_width / base_width)
        y = round(rect.y() * full_height / base_height)
        width = max(1, round(rect.width() * full_width / base_width))
        height = max(1, round(rect.height() * full_height / base_height))
        return Rect(x, y, min(width, full_width - x), min(height, full_height - y))

    def fit(self):
        viewport = self.scroll.viewport().size()
        self.fit_mode = True
        self.label.set_scale(
            min(
                max(1, viewport.width() - 12) / self.label.base.width(),
                max(1, viewport.height() - 12) / self.label.base.height(),
            )
        )

    def zoom_by(self, factor):
        self.fit_mode = False
        self.label.set_scale(self.label.scale * factor)

    def showEvent(self, event):
        super().showEvent(event)
        self.fit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.fit_mode:
            self.fit()

    def status(self):
        rect = self.rect()
        self.info.setText(
            tr(self.lang, "whole")
            if rect.width <= 0
            else tr(self.lang, "range", x=rect.x, y=rect.y, w=rect.width, h=rect.height)
        )


class CropPreviewLabel(QLabel):
    zoom = Signal(float)

    def __init__(self, pixmap: QPixmap, crop_rect: QRect):
        super().__init__()
        self.base = pixmap
        self.crop_base = crop_rect
        self.scale = 1.0
        self.set_scale(1.0)

    def set_scale(self, scale):
        self.scale = max(0.05, min(float(scale), 8))
        size = QSize(
            max(1, round(self.base.width() * self.scale)),
            max(1, round(self.base.height() * self.scale)),
        )
        self.setPixmap(
            self.base.scaled(
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.setFixedSize(size)
        self.update()

    def wheelEvent(self, event: QWheelEvent):
        self.zoom.emit(1.2 if event.angleDelta().y() > 0 else 1 / 1.2)
        event.accept()

    def paintEvent(self, event):
        super().paintEvent(event)
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull():
            return
        crop = QRect(
            round(self.crop_base.x() * self.scale),
            round(self.crop_base.y() * self.scale),
            max(1, round(self.crop_base.width() * self.scale)),
            max(1, round(self.crop_base.height() * self.scale)),
        ).intersected(self.rect())
        if crop.isEmpty():
            return

        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 125))
        painter.drawPixmap(crop, pixmap, crop)
        painter.setPen(QPen(QColor("#00a86b"), 3))
        painter.drawRect(crop.adjusted(1, 1, -2, -2))


class CropPreviewDialog(QDialog):
    def __init__(self, lang: str, path: str, crop: Rect, parent=None):
        super().__init__(parent)
        self.lang = lang
        self.setWindowTitle(tr(lang, "crop_preview_title"))
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)
        self.resize(1200, 800)
        self.fit_mode = True
        self.full = RegionDialog.oriented(path)

        reader = QImageReader(path)
        reader.setAutoTransform(True)
        size = reader.size().scaled(QSize(2600, 1800), Qt.AspectRatioMode.KeepAspectRatio)
        reader.setScaledSize(size)
        image = reader.read()
        if image.isNull():
            raise ValueError(tr(lang, "preview_fail"))

        base = QPixmap.fromImage(image)
        full_width, full_height = self.full
        crop_base = QRect(
            round(crop.x * base.width() / full_width),
            round(crop.y * base.height() / full_height),
            max(1, round(crop.width * base.width() / full_width)),
            max(1, round(crop.height * base.height() / full_height)),
        )
        self.label = CropPreviewLabel(base, crop_base)
        self.label.zoom.connect(self.zoom_by)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.label)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)

        minus = QPushButton("−")
        plus = QPushButton("+")
        fit = QPushButton(tr(lang, "fit"))
        minus.clicked.connect(lambda: self.zoom_by(1 / 1.25))
        plus.clicked.connect(lambda: self.zoom_by(1.25))
        fit.clicked.connect(self.fit)
        tools = QHBoxLayout()
        tools.addWidget(minus)
        tools.addWidget(plus)
        tools.addWidget(fit)
        tools.addStretch()

        help_label = QLabel(tr(lang, "crop_preview_help"))
        help_label.setWordWrap(True)
        info = QLabel(
            tr(
                lang,
                "crop_preview_info",
                iw=full_width,
                ih=full_height,
                x=crop.x,
                y=crop.y,
                w=crop.width,
                h=crop.height,
            )
        )
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(tools)
        layout.addWidget(self.scroll, 1)
        layout.addWidget(help_label)
        layout.addWidget(info)
        layout.addWidget(buttons)

    def fit(self):
        viewport = self.scroll.viewport().size()
        self.fit_mode = True
        self.label.set_scale(
            min(
                max(1, viewport.width() - 12) / self.label.base.width(),
                max(1, viewport.height() - 12) / self.label.base.height(),
            )
        )

    def zoom_by(self, factor):
        self.fit_mode = False
        self.label.set_scale(self.label.scale * factor)

    def showEvent(self, event):
        super().showEvent(event)
        self.fit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.fit_mode:
            self.fit()


class RegionEditor(QWidget):
    def __init__(self, lang, image_getter: Callable[[], str]):
        super().__init__()
        self.lang = lang
        self.get_image = image_getter
        self.spins = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for key in ("x", "y", "w", "h"):
            layout.addWidget(QLabel(tr(lang, key)))
            spin = manual_number(QSpinBox())
            spin.setRange(0, 200000)
            spin.setMinimumWidth(108)
            self.spins.append(spin)
            layout.addWidget(spin)
        button = QPushButton(tr(lang, "pick"))
        button.clicked.connect(self.pick)
        layout.addWidget(button)
        layout.addWidget(QLabel(tr(lang, "template_hint")), 1)

    def rect(self):
        return Rect(*(spin.value() for spin in self.spins))

    def pick(self):
        path = self.get_image()
        if not path:
            return
        try:
            current = self.rect()
            dialog = RegionDialog(
                self.lang,
                path,
                current if current.width > 0 and current.height > 0 else None,
                self,
            )
            if dialog.exec() == QDialog.DialogCode.Accepted:
                rect = dialog.rect()
                for spin, value in zip(self.spins, (rect.x, rect.y, rect.width, rect.height)):
                    spin.setValue(value)
        except Exception as exc:
            QMessageBox.warning(self, tr(self.lang, "preview_fail"), str(exc))


class SearchMask(QWidget):
    def __init__(self, lang, input_folder_getter: Callable[[], str] | None = None):
        super().__init__()
        self.lang = lang
        self.input_folder_getter = input_folder_getter
        self.last = ""
        self.spin = manual_number(QDoubleSpinBox())
        self.spin.setRange(0, 45)
        self.spin.setDecimals(2)
        self.spin.setValue(DEFAULT_SEARCH_MASK)
        self.spin.setSuffix(" %")
        self.spin.setMinimumWidth(120)

        button = QPushButton(tr(lang, "pick"))
        button.clicked.connect(self.pick)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.spin)
        layout.addWidget(button)
        layout.addWidget(QLabel(tr(lang, "search_note")), 1)

    def initial(self, path):
        full_width, full_height = RegionDialog.oriented(path)
        percent = self.spin.value() / 100
        margin_x = round(full_width * percent)
        margin_y = round(full_height * percent)
        return Rect(margin_x, margin_y, full_width - 2 * margin_x, full_height - 2 * margin_y)

    def pick_start(self):
        folder = self.input_folder_getter() if self.input_folder_getter else ""
        return preferred_image_start(folder, self.last)

    def pick(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr(self.lang, "choose_target"),
            self.pick_start(),
            tr(self.lang, "image_filter_short"),
        )
        if not path:
            return
        self.last = path
        try:
            dialog = RegionDialog(
                self.lang,
                path,
                self.initial(path),
                self,
                tr(self.lang, "search_help"),
            )
            if dialog.exec() == QDialog.DialogCode.Accepted:
                rect = dialog.rect()
                full_width, full_height = dialog.full
                if rect.width > 0:
                    self.spin.setValue(
                        max(
                            0,
                            min(
                                45,
                                (
                                    rect.x / full_width
                                    + (full_width - rect.x - rect.width) / full_width
                                    + rect.y / full_height
                                    + (full_height - rect.y - rect.height) / full_height
                                )
                                * 25,
                            ),
                        )
                    )
        except Exception as exc:
            QMessageBox.warning(self, tr(self.lang, "preview_fail"), str(exc))


class Worker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, kwargs, lang):
        super().__init__()
        self.fn = fn
        self.kwargs = kwargs
        self.lang = lang
        self.stop = threading.Event()

    @Slot()
    def run(self):
        try:
            self.finished.emit(
                self.fn(
                    **self.kwargs,
                    progress=lambda current, total, message: self.progress.emit(current, total, message),
                    cancel=self.stop.is_set,
                )
            )
        except Cancelled:
            self.failed.emit(tr(self.lang, "cancelled"))
        except Exception as exc:
            self.failed.emit(str(exc))


class BatchTab(QWidget):
    def __init__(self, lang):
        super().__init__()
        self.lang = lang
        self.thread = None
        self.worker = None
        self.content = QVBoxLayout(self)
        self.content.setContentsMargins(14, 14, 14, 14)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(130)
        self.debug = QCheckBox(tr(lang, "debug"))
        self.debug.setToolTip(tr(lang, "debug_tip"))
        self.workers = manual_number(QSpinBox())
        self.workers.setRange(1, max(2, min(8, os.cpu_count() or 2)))
        self.workers.setValue(min(DEFAULT_WORKERS, self.workers.maximum()))
        self.workers.setToolTip(tr(lang, "threads_tip"))
        self.run = QPushButton(tr(lang, "start"))
        self.run.setObjectName("primary")
        self.cancel = QPushButton(tr(lang, "cancel"))
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.stop)

    def footer(self):
        options = QHBoxLayout()
        options.addWidget(self.debug)
        options.addStretch()
        options.addWidget(QLabel(tr(self.lang, "threads")))
        options.addWidget(self.workers)
        self.content.addLayout(options)
        self.content.addWidget(self.progress)
        self.content.addWidget(self.log, 1)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.cancel)
        buttons.addWidget(self.run)
        self.content.addLayout(buttons)

    def common(self):
        return {"lang": self.lang, "workers": self.workers.value(), "debug": self.debug.isChecked()}

    def start(self, fn, kwargs):
        if self.thread:
            return
        self.log.clear()
        self.progress.setRange(0, 0)
        self.run.setEnabled(False)
        self.cancel.setEnabled(True)
        thread = QThread(self)
        worker = Worker(fn, kwargs, self.lang)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.on_progress)
        worker.finished.connect(self.on_done)
        worker.failed.connect(self.on_fail)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self.clear)
        self.thread = thread
        self.worker = worker
        thread.start()

    def stop(self):
        if self.worker:
            self.cancel.setEnabled(False)
            self.log.appendPlainText(tr(self.lang, "wait_cancel"))
            self.worker.stop.set()

    def on_progress(self, current, total, message):
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(current)
        self.log.appendPlainText(f"[{current}/{total}] {message}")

    def on_done(self, summary):
        self.log.appendPlainText(
            tr(self.lang, "finished", ok=summary.succeeded, skip=summary.skipped, fail=summary.failed)
        )
        debug = tr(self.lang, "debug_line", path=summary.debug_path) if summary.debug_path else ""
        QMessageBox.information(
            self,
            tr(self.lang, "done"),
            tr(
                self.lang,
                "done_body",
                total=summary.total,
                ok=summary.succeeded,
                skip=summary.skipped,
                fail=summary.failed,
                path=summary.output_path,
                debug=debug,
            ),
        )

    def on_fail(self, message):
        self.log.appendPlainText(message)
        QMessageBox.warning(self, tr(self.lang, "failed_title"), message)

    def clear(self):
        self.thread = None
        self.worker = None
        self.run.setEnabled(True)
        self.cancel.setEnabled(False)
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 1)

    def running(self):
        return self.thread is not None


class MatchOpts(QGroupBox):
    def __init__(self, lang, sample, input_folder):
        super().__init__(tr(lang, "match_group"))
        self.lang = lang
        self.region = RegionEditor(lang, sample.text)
        self.search = SearchMask(lang, input_folder.text)
        self.edge = manual_number(QDoubleSpinBox())
        self.edge.setRange(0, 45)
        self.edge.setValue(10)
        self.edge.setSuffix(" %")
        self.sim = manual_number(QDoubleSpinBox())
        self.sim.setRange(-1, 1)
        self.sim.setDecimals(3)
        self.sim.setSingleStep(0.01)
        self.sim.setValue(DEFAULT_THRESHOLD)
        form = QFormLayout(self)
        form.addRow(tr(lang, "template"), self.region)
        form.addRow(tr(lang, "search_mask"), self.search)
        form.addRow(tr(lang, "edge"), self.edge)
        form.addRow(tr(lang, "similarity"), self.sim)

    def value(self):
        return MatchSettings(self.region.rect(), self.edge.value(), self.search.spin.value(), self.sim.value())


def path_check(parent, lang, pairs):
    missing = [label for label, value in pairs if not value]
    if missing:
        QMessageBox.warning(parent, tr(lang, "missing"), tr(lang, "select_missing", items="、".join(missing)))
        return False
    return True


def quality():
    widget = manual_number(QSpinBox())
    widget.setRange(1, 100)
    widget.setValue(100)
    widget.setSuffix(" %")
    return widget


class MatchTab(BatchTab):
    def __init__(self, lang):
        super().__init__(lang)
        paths = QGroupBox(tr(lang, "paths"))
        form = QFormLayout(paths)
        self.sample = PathChooser(lang, "file")
        self.input = PathChooser(lang, "folder")
        self.output = PathChooser(lang, "folder")
        form.addRow(tr(lang, "sample"), self.sample)
        form.addRow(tr(lang, "input"), self.input)
        form.addRow(tr(lang, "output"), self.output)

        self.opts = MatchOpts(lang, self.sample, self.input)

        output = QGroupBox(tr(lang, "output_group"))
        output_form = QFormLayout(output)
        self.q = quality()
        output_form.addRow(tr(lang, "quality"), self.q)
        output_form.addRow("", QLabel(tr(lang, "name_note")))

        self.content.addWidget(paths)
        self.content.addWidget(self.opts)
        self.content.addWidget(output)
        self.footer()
        self.run.clicked.connect(self.go)

    def go(self):
        if path_check(
            self,
            self.lang,
            [
                (tr(self.lang, "sample"), self.sample.text()),
                (tr(self.lang, "input"), self.input.text()),
                (tr(self.lang, "output"), self.output.text()),
            ],
        ):
            self.start(
                match_crop,
                {
                    "sample": self.sample.text(),
                    "input_folder": self.input.text(),
                    "output_folder": self.output.text(),
                    "settings": self.opts.value(),
                    "quality": self.q.value(),
                    **self.common(),
                },
            )


class CenterTab(BatchTab):
    def __init__(self, lang):
        super().__init__(lang)
        self.preview_last = ""

        paths = QGroupBox(tr(lang, "paths"))
        form = QFormLayout(paths)
        self.input = PathChooser(lang, "folder")
        self.output = PathChooser(lang, "folder")
        form.addRow(tr(lang, "input"), self.input)
        form.addRow(tr(lang, "output"), self.output)

        settings = QGroupBox(tr(lang, "center_group"))
        grid = QGridLayout(settings)
        self.fixed = QRadioButton(tr(lang, "fixed"))
        self.ratio = QRadioButton(tr(lang, "ratio"))
        self.fixed.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.fixed)
        group.addButton(self.ratio)

        self.w = manual_number(QSpinBox())
        self.h = manual_number(QSpinBox())
        for spin in (self.w, self.h):
            spin.setRange(1, 200000)
            spin.setValue(1000)
            spin.setSuffix(" px")

        self.r = QLineEdit("1/3")
        self.r.setPlaceholderText(tr(lang, "ratio_ph"))
        self.r.setEnabled(False)
        self.fixed.toggled.connect(self.toggle_mode)

        grid.addWidget(self.fixed, 0, 0)
        grid.addWidget(QLabel(tr(lang, "w") + "："), 0, 1)
        grid.addWidget(self.w, 0, 2)
        grid.addWidget(QLabel(tr(lang, "h") + "："), 0, 3)
        grid.addWidget(self.h, 0, 4)
        grid.addWidget(self.ratio, 1, 0)
        grid.addWidget(QLabel(tr(lang, "ratio_label")), 1, 1, 1, 2)
        grid.addWidget(self.r, 1, 3, 1, 2)

        self.preview_button = QPushButton(tr(lang, "crop_preview"))
        self.preview_button.clicked.connect(self.preview_crop)
        grid.addWidget(self.preview_button, 2, 0, 1, 5)

        output = QGroupBox(tr(lang, "output_group"))
        output_form = QFormLayout(output)
        self.q = quality()
        output_form.addRow(tr(lang, "quality"), self.q)
        output_form.addRow("", QLabel(tr(lang, "center_note")))

        self.content.addWidget(paths)
        self.content.addWidget(settings)
        self.content.addWidget(output)
        self.footer()
        self.run.clicked.connect(self.go)

    def toggle_mode(self, fixed):
        self.w.setEnabled(fixed)
        self.h.setEnabled(fixed)
        self.r.setEnabled(not fixed)

    def preview_start(self):
        return preferred_image_start(self.input.text(), self.preview_last)

    def current_crop(self, width: int, height: int) -> Rect:
        if self.fixed.isChecked():
            return center_rect(
                width,
                height,
                width=self.w.value(),
                height=self.h.value(),
                lang=self.lang,
            )
        return center_rect(width, height, ratio=self.r.text().strip(), lang=self.lang)

    def preview_crop(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr(self.lang, "choose_crop_preview"),
            self.preview_start(),
            tr(self.lang, "image_filter_short"),
        )
        if not path:
            return
        self.preview_last = path
        try:
            width, height = RegionDialog.oriented(path)
            crop = self.current_crop(width, height)
            CropPreviewDialog(self.lang, path, crop, self).exec()
        except Exception as exc:
            QMessageBox.warning(self, tr(self.lang, "preview_fail"), str(exc))

    def go(self):
        if not path_check(
            self,
            self.lang,
            [
                (tr(self.lang, "input"), self.input.text()),
                (tr(self.lang, "output"), self.output.text()),
            ],
        ):
            return
        kwargs = {
            "input_folder": self.input.text(),
            "output_folder": self.output.text(),
            "quality": self.q.value(),
            **self.common(),
        }
        if self.fixed.isChecked():
            kwargs.update(width=self.w.value(), height=self.h.value())
        else:
            kwargs.update(ratio=self.r.text().strip())
        self.start(center_crop, kwargs)


class CoordTab(BatchTab):
    def __init__(self, lang):
        super().__init__(lang)
        paths = QGroupBox(tr(lang, "paths"))
        form = QFormLayout(paths)
        self.sample = PathChooser(lang, "file")
        self.input = PathChooser(lang, "folder")
        self.csv = PathChooser(lang, "save", "csv_filter")
        form.addRow(tr(lang, "sample"), self.sample)
        form.addRow(tr(lang, "input"), self.input)
        form.addRow(tr(lang, "csv"), self.csv)

        self.opts = MatchOpts(lang, self.sample, self.input)
        note = QLabel(tr(lang, "coord_note"))
        note.setWordWrap(True)

        self.content.addWidget(paths)
        self.content.addWidget(self.opts)
        self.content.addWidget(note)
        self.footer()
        self.run.clicked.connect(self.go)

    def go(self):
        if not path_check(
            self,
            self.lang,
            [
                (tr(self.lang, "sample"), self.sample.text()),
                (tr(self.lang, "input"), self.input.text()),
                (tr(self.lang, "csv"), self.csv.text()),
            ],
        ):
            return
        path = self.csv.text()
        path = path if Path(path).suffix.lower() == ".csv" else path + ".csv"
        self.csv.edit.setText(path)
        self.start(
            export_coords,
            {
                "sample": self.sample.text(),
                "input_folder": self.input.text(),
                "csv_path": path,
                "settings": self.opts.value(),
                **self.common(),
            },
        )


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
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
        toolbar.addWidget(self.combo)
        self.combo.currentIndexChanged.connect(self.switch)
        self.build()

    def build(self):
        old = self.centralWidget()
        self.tabs = QTabWidget()
        self.a = MatchTab(self.lang)
        self.b = CenterTab(self.lang)
        self.c = CoordTab(self.lang)
        self.tabs.addTab(self.a, tr(self.lang, "tab1"))
        self.tabs.addTab(self.b, tr(self.lang, "tab2"))
        self.tabs.addTab(self.c, tr(self.lang, "tab3"))
        self.setCentralWidget(self.tabs)
        if old:
            old.deleteLater()
        self.lang_label.setText(tr(self.lang, "language"))
        self.statusBar().showMessage(tr(self.lang, "status"))

    def switch(self, index):
        new = self.combo.itemData(index)
        if new == self.lang:
            return
        if any(tab.running() for tab in (self.a, self.b, self.c)):
            QMessageBox.information(self, tr(self.lang, "running"), tr(self.lang, "running_msg"))
            self.combo.blockSignals(True)
            self.combo.setCurrentIndex(0 if self.lang == "zh" else 1)
            self.combo.blockSignals(False)
            return
        self.lang = new
        self.build()

    def closeEvent(self, event: QCloseEvent):
        if any(tab.running() for tab in (self.a, self.b, self.c)):
            QMessageBox.information(self, tr(self.lang, "running"), tr(self.lang, "running_msg"))
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CIPA Crop & Coord")
    app.setOrganizationName("CIPA")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    return app.exec()
