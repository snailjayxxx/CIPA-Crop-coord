from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (
    QApplication,
    QAbstractSpinBox,
    QDoubleSpinBox,
    QFileDialog,
    QSpinBox,
)

from cipa_crop_coord.ui import (
    CenterTab,
    SearchMask,
    manual_number,
    preferred_image_start,
    quality,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_quality_defaults_to_100_percent() -> None:
    _app()
    widget = quality()
    assert widget.value() == 100
    assert widget.maximum() == 100


def test_numeric_inputs_have_no_step_buttons() -> None:
    _app()
    integer = manual_number(QSpinBox())
    decimal = manual_number(QDoubleSpinBox())
    expected = QAbstractSpinBox.ButtonSymbols.NoButtons
    assert integer.buttonSymbols() == expected
    assert decimal.buttonSymbols() == expected


def test_preferred_image_start_uses_selected_traversal_folder(tmp_path) -> None:
    selected = tmp_path / "images"
    selected.mkdir()
    fallback = str(tmp_path / "previous.jpg")
    assert preferred_image_start(str(selected), fallback) == str(selected)


def test_search_mask_picker_starts_in_traversal_folder(tmp_path, monkeypatch) -> None:
    _app()
    selected = tmp_path / "images"
    selected.mkdir()
    captured = {}

    def fake_open(parent, title, directory, file_filter):
        captured["directory"] = directory
        return "", ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", fake_open)
    widget = SearchMask("zh", lambda: str(selected))
    widget.pick()
    assert captured["directory"] == str(selected)


def test_center_crop_preview_picker_starts_in_traversal_folder(tmp_path, monkeypatch) -> None:
    _app()
    selected = tmp_path / "images"
    selected.mkdir()
    captured = {}

    def fake_open(parent, title, directory, file_filter):
        captured["directory"] = directory
        return "", ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", fake_open)
    tab = CenterTab("zh")
    tab.input.edit.setText(str(selected))
    tab.preview_crop()
    assert captured["directory"] == str(selected)


def test_center_crop_preview_uses_current_fixed_settings() -> None:
    _app()
    tab = CenterTab("zh")
    tab.w.setValue(600)
    tab.h.setValue(400)
    rect = tab.current_crop(1200, 900)
    assert (rect.x, rect.y, rect.width, rect.height) == (300, 250, 600, 400)


def test_center_crop_preview_uses_current_ratio_settings() -> None:
    _app()
    tab = CenterTab("zh")
    tab.ratio.setChecked(True)
    tab.r.setText("1/3")
    rect = tab.current_crop(1200, 900)
    assert (rect.x, rect.y, rect.width, rect.height) == (400, 300, 400, 300)
