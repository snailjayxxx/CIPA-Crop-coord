from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QAbstractSpinBox, QDoubleSpinBox, QSpinBox

from cipa_crop_coord.ui import manual_number, quality


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
