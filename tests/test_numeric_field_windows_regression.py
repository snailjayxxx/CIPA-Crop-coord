"""Regression guard for the Windows EXE's formerly blank numeric fields.

Exercise every tab with the application's real stylesheet. The controls must
both display their values and accept editing, not just store an internal value.
Only synthetic values are used, never personal image paths.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFontInfo, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QAbstractSpinBox,
    QDoubleSpinBox,
    QLineEdit,
    QSpinBox,
)

from cipa_crop_coord.ui import STYLE, MatchTab
from cipa_crop_coord.ui_user_text import MainWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _entry(spin):
    editor = spin.findChild(QLineEdit)
    assert editor is not None, f"{spin.objectName() or type(spin).__name__}: no editor"
    assert not spin.isReadOnly(), "Numeric controls must never be read-only"
    assert not editor.isReadOnly(), "Embedded text editor must accept typing"
    assert spin.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.UpDownArrows
    assert editor.text().strip(), "Numeric editor must not start empty"
    text_color = editor.palette().color(QPalette.ColorRole.Text)
    background = editor.palette().color(QPalette.ColorRole.Base)
    assert text_color != background, "Numeric text must contrast with the editor"
    return editor


def _type(spin, value):
    editor = _entry(spin)
    spin.setFocus()
    QTest.mouseClick(
        editor, Qt.MouseButton.LeftButton, pos=editor.rect().center()
    )
    editor.selectAll()
    QTest.keyClicks(editor, str(value))
    QTest.keyClick(editor, Qt.Key.Key_Return)
    QApplication.processEvents()
    actual = spin.value()
    if isinstance(spin, QSpinBox):
        assert actual == int(value), (spin.objectName(), value, actual)
    else:
        assert abs(actual - float(value)) < 0.001, (spin.objectName(), value, actual)


def _visible_digits_change_when_number_changes(spin) -> None:
    """Pixel-diff is a stronger check than spin.value()/spin.text() alone."""
    assert spin.width() >= 90, "An overly narrow spin box can hide its editor"
    low, high = spin.minimum(), spin.maximum()
    assert high > low
    # The similarity input is limited to [-1, 1], whereas image dimensions
    # can exceed 1000. Pick two distinct valid values for every field.
    if isinstance(spin, QSpinBox):
        value1 = min(high, max(low, 0))
        value2 = min(high, value1 + 3)
    else:
        value1 = min(high, max(low, 0.0))
        value2 = min(high, value1 + max(0.25, spin.singleStep()))
    if value1 == value2:
        value1, value2 = low, high
    editor = spin.findChild(QLineEdit)
    spin.setValue(value1)
    QApplication.processEvents()
    first_text = spin.text()
    first = spin.grab().toImage()
    first_editor = editor.grab().toImage()
    spin.setValue(value2)
    QApplication.processEvents()
    second_text = spin.text()
    second = spin.grab().toImage()
    second_editor = editor.grab().toImage()
    assert first_text != second_text, "Spinbox did not update its text after value change"
    assert first.size() == second.size()
    if not QFontInfo(editor.font()).family():
        # On Windows GitHub Actions with QT_QPA_PLATFORM=offscreen, Qt's
        # QFontInfo resolves to an empty family and even a *plain native
        # QLineEdit* paints every ASCII digit as the same tofu rectangle.
        # Pixel comparisons are meaningless in that environment. Continue
        # to check visible geometry, editor.text, actual mouse clicks and
        # keyboard input. Interactive desktop visual acceptance remains.
        return

    # Inspect the editing part only, excluding the step arrows and border.
    width = max(10, min(90, spin.width() - 23))
    height = spin.height()
    changed = 0
    for y in range(5, max(6, height - 5)):
        for x in range(5, width):
            if first.pixel(x, y) != second.pixel(x, y):
                changed += 1
    changed_editor = sum(
        first_editor.pixel(x, y) != second_editor.pixel(x, y)
        for y in range(first_editor.height())
        for x in range(first_editor.width())
    )
    if changed <= 2 and changed_editor <= 2:
        # This records both native spinbox and its child editor. Qt's
        # offscreen plugin can sometimes omit child painting from grab().
        from pathlib import Path
        capture = Path("ui-capture")
        capture.mkdir(exist_ok=True)
        first.save(str(capture / "spin_before.png"))
        second.save(str(capture / "spin_after.png"))
        first_editor.save(str(capture / "editor_before.png"))
        second_editor.save(str(capture / "editor_after.png"))
        native = QSpinBox()
        native.setRange(1, 8)
        native.resize(130, 34)
        native.show()
        QApplication.processEvents()
        native.setValue(1)
        ref1 = native.findChild(QLineEdit).grab().toImage()
        native.setValue(4)
        ref2 = native.findChild(QLineEdit).grab().toImage()
        ref1.save(str(capture / "native_before.png"))
        ref2.save(str(capture / "native_after.png"))
        reference_diff = sum(
            ref1.pixel(x,y) != ref2.pixel(x,y)
            for y in range(ref1.height()) for x in range(ref1.width())
        )
        native.close()
    else:
        reference_diff = -1
    assert changed > 2 or changed_editor > 2, (
        "Changing value did not paint visible digits: "
        f"type={type(spin).__name__} name={spin.objectName()!r} "
        f"parent={type(spin.parentWidget()).__name__} "
        f"values={value1!r}->{value2!r}, "
        f"current={spin.value()!r}, display={spin.text()!r}, "
        f"editor={spin.findChild(QLineEdit).geometry()}, "
        f"spin_size={spin.size()}, inspected_width={width}, "
        f"pixel_changes=spin:{changed}/editor:{changed_editor}, "
        f"native_editor_reference={reference_diff}"
    )


def test_every_page_numeric_field_has_visible_text_and_editable_controls():
    app = _app()
    previous = app.styleSheet()
    app.setStyleSheet(STYLE)
    window = MainWindow()
    try:
        window.a.blur_enabled.setChecked(True)
        window.a.match_section.toggle_button.setChecked(True)
        window.a.output_section.toggle_button.setChecked(True)
        window.show()
        app.processEvents()
        found = []
        for index in range(window.tabs.count()):
            window.tabs.setCurrentIndex(index)
            app.processEvents()
            page = window.tabs.widget(index)
            for spin in page.findChildren(QAbstractSpinBox):
                if not isinstance(spin, (QSpinBox, QDoubleSpinBox)):
                    continue
                editor = _entry(spin)
                if not spin.isEnabled():
                    # The images-to-video page deliberately disables its
                    # unused legacy crop-thread setting.
                    continue
                assert spin.isVisible()
                assert editor.isVisible()
                assert editor.width() >= 15, "Embedded edit area collapsed"
                assert editor.height() >= 12, "Embedded edit area collapsed"
                found.append((index, spin))
        assert len(found) >= 15, "Expected fields across all six tabs"
        for index, spin in found:
            window.tabs.setCurrentIndex(index)
            app.processEvents()
            _visible_digits_change_when_number_changes(spin)
    finally:
        window.close()
        app.setStyleSheet(previous)


def test_typing_changes_all_representative_number_formats():
    app = _app()
    previous = app.styleSheet()
    app.setStyleSheet(STYLE)
    window = MainWindow()
    try:
        window.a.blur_enabled.setChecked(True)
        window.a.match_section.toggle_button.setChecked(True)
        window.a.output_section.toggle_button.setChecked(True)
        window.show()
        app.processEvents()
        cases = [
            (window.a, window.a.workers, "3"),
            (window.a, window.a.blur_workers, "4"),
            (window.a, window.a.opts.region.spins[0], "27"),
            (window.a, window.a.opts.search.spin, "18.25"),
            (window.a, window.a.opts.edge, "12.5"),
            (window.a, window.a.opts.sim, "0.75"),
            (window.a, window.a.q, "97"),
            (window.b, window.b.w, "640"),
            (window.b, window.b.h, "480"),
            (window.b, window.b.q, "98"),
            (window.d, window.d.ratio, "0.5"),
            (window.f, window.f.fps, "12.5"),
            (window.f, window.f.count, "30"),
        ]
        for tab, spin, number in cases:
            window.tabs.setCurrentWidget(tab)
            app.processEvents()
            _type(spin, number)
        assert window.a.workers.value() == 3
        assert window.a.blur_workers.value() == 4
        assert window.a.q.value() == 97
        assert window.f.fps.value() == 12.5
        assert window.f.count.value() == 30
    finally:
        window.close()
        app.setStyleSheet(previous)


def test_numeric_style_and_defaults_work_in_all_languages():
    app = _app()
    previous = app.styleSheet()
    app.setStyleSheet(STYLE)
    try:
        for lang in ("zh", "ja", "en"):
            tab = MatchTab(lang)
            tab.blur_enabled.setChecked(True)
            tab.match_section.toggle_button.setChecked(True)
            tab.output_section.toggle_button.setChecked(True)
            tab.show()
            app.processEvents()
            try:
                assert tab.blur_workers.value() == 2
                assert tab.q.value() == 100
                assert tab.opts.sim.value() == -1.0
                for spin in tab.findChildren(QAbstractSpinBox):
                    if isinstance(spin, (QSpinBox, QDoubleSpinBox)):
                        _entry(spin)
                        assert spin.findChild(QLineEdit).isVisible()
            finally:
                tab.close()
    finally:
        app.setStyleSheet(previous)


def test_mouse_step_buttons_can_choose_worker_counts():
    app = _app()
    previous = app.styleSheet()
    app.setStyleSheet(STYLE)
    tab = MatchTab("zh")
    tab.blur_enabled.setChecked(True)
    try:
        tab.show()
        app.processEvents()
        for spin in (tab.workers, tab.blur_workers):
            spin.setValue(2)
            app.processEvents()
            QTest.mouseClick(
                spin, Qt.MouseButton.LeftButton,
                pos=QPoint(spin.width() - 9, max(6, spin.height() // 4)),
            )
            app.processEvents()
            assert spin.value() == 3, "Clicking the up arrow must increment"
    finally:
        tab.close()
        app.setStyleSheet(previous)
