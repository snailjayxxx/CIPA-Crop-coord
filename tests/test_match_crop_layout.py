"""GUI regression checks for collapsed settings, localization and progress counts."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QPushButton

from cipa_crop_coord.ui_user_text import MainWindow
from cipa_crop_coord.locales import tr


def _app():
    return QApplication.instance() or QApplication([])


def test_initial_language_and_settings_sections():
    _app()
    window = MainWindow()
    try:
        assert window.lang == "ja"
        assert window.combo.currentData() == "ja"
        assert window.tabs.tabText(0) == tr("ja", "tab1")
        assert not window.a.match_section.toggle_button.isChecked()
        assert not window.a.output_section.toggle_button.isChecked()
        assert window.a.workers.value() == 2
        assert window.a.blur_workers.value() == 2
        assert window.a.q.value() == 100
        assert window.a.opts.sim.value() == -1
    finally:
        window.close()


def test_browse_labels_have_enough_room_in_all_languages():
    _app()
    from cipa_crop_coord.ui import PathChooser
    for lang in ("ja", "zh", "en"):
        chooser = PathChooser(lang, "folder")
        try:
            assert chooser.button.text() == tr(lang, "browse")
            assert chooser.button.minimumWidth() >= 98
            assert chooser.button.minimumWidth() >= (
                chooser.button.fontMetrics().horizontalAdvance(chooser.button.text()) + 40
            )
        finally:
            chooser.close()


def test_count_bars_and_disclosures_expand_without_hiding_actions():
    app = _app()
    window = MainWindow()
    window.show()
    app.processEvents()
    try:
        tab = window.a
        tab.blur_enabled.setChecked(True)
        tab.on_progress(3, 14, "")
        tab.on_blur_progress(2, 14, "")
        assert tab.progress.format().endswith("%v/14")
        assert tab.blur_progress_bar.format().endswith("%v/14")
        assert tab.content.indexOf(tab.progress) < tab.content.indexOf(tab.blur_progress_bar)
        assert tab.content.indexOf(tab.blur_progress_bar) < tab.content.indexOf(tab.log)
        h0 = window.height()
        tab.match_section.toggle_button.setChecked(True)
        tab.output_section.toggle_button.setChecked(True)
        app.processEvents()
        window.fit_active_tab()
        app.processEvents()
        assert tab.match_section.body.isVisible()
        assert tab.output_section.body.isVisible()
        assert window.height() >= h0 or tab.settings_scroll.verticalScrollBar().maximum() > 0
        assert tab.run.isVisible()
        assert tab.cancel.isVisible()
        assert all(
            child.minimumWidth() >= 98
            for child in tab.findChildren(QPushButton)
            if child.objectName() == "cipaBrowseButton"
        )
    finally:
        window.close()



def test_crop_worker_alignment_and_debug_after_worker():
    app = _app()
    from cipa_crop_coord.ui import MatchTab
    for lang in ("ja", "zh", "en"):
        tab = MatchTab(lang)
        tab.resize(1180, 760)
        tab.show()
        app.processEvents()
        try:
            def left(w):
                return w.mapTo(tab, QPoint(0, 0)).x()

            assert abs(left(tab.crop_workers_label) - left(tab.calc_workers_label)) <= 2
            assert abs(left(tab.workers) - left(tab.blur_workers)) <= 2
            assert left(tab.debug) >= left(tab.workers) + tab.workers.width()
            assert abs(left(tab.calcdebug_enabled) - left(tab.debug)) <= 2
            assert left(tab.calcdebug_enabled) >= left(tab.blur_workers) + tab.blur_workers.width()
            assert abs(
                tab.debug.mapTo(tab, QPoint(0, 0)).y()
                - tab.workers.mapTo(tab, QPoint(0, 0)).y()
            ) < 12
            assert abs(
                tab.calcdebug_enabled.mapTo(tab, QPoint(0, 0)).y()
                - tab.blur_workers.mapTo(tab, QPoint(0, 0)).y()
            ) < 12
            assert abs(left(tab.calcdebug_folder) - left(tab.blur_file)) <= 2
            assert tab.calcdebug_folder_label.text() == tr(lang, "calcdebug_folder")
            # Folder location is unchanged, and its activation still follows
            # both the blur-calculation and CalcDebug switches.
            assert not tab.calcdebug_enabled.isEnabled()
            assert not tab.calcdebug_folder.isEnabled()
            tab.blur_enabled.setChecked(True)
            assert tab.calcdebug_enabled.isEnabled()
            tab.calcdebug_enabled.setChecked(True)
            assert tab.calcdebug_folder.isEnabled()
            tab.calcdebug_enabled.setChecked(False)
            assert not tab.calcdebug_folder.isEnabled()
        finally:
            tab.close()


def test_crop_folder_suggestion_and_original_blur_txt_rule(tmp_path):
    _app()
    from cipa_crop_coord.ui import MatchTab
    for lang in ("ja", "zh", "en"):
        tab = MatchTab(lang)
        try:
            first = tmp_path / "日本語" / "第一组"
            second = tmp_path / "日本語" / "第二组"
            tab.input.edit.setText(str(first))
            assert tab.output.text() == str(first / "resize")
            assert tab.blur_file.text() == str(first / "resize" / "FindsBlur_Result.txt")
            # Automatic paths follow a changed input folder, even after clearing.
            tab.input.edit.setText("")
            tab.input.edit.setText(str(second))
            assert tab.output.text() == str(second / "resize")
            assert tab.blur_file.text() == str(second / "resize" / "FindsBlur_Result.txt")
            # Explicit output choice wins over further input-folder selection.
            manual = tmp_path / "custom-output"
            tab.output.edit.setText(str(manual))
            tab.input.edit.setText(str(first))
            assert tab.output.text() == str(manual)
            assert tab.blur_file.text() == str(manual / "FindsBlur_Result.txt")
            # Keep the previous behavior for manually edited calculation TXT.
            custom_txt = tmp_path / "manually-chosen.txt"
            tab.blur_file.edit.setText(str(custom_txt))
            tab.output.edit.setText(str(tmp_path / "another-output"))
            assert tab.blur_file.text() == str(custom_txt)
        finally:
            tab.close()


def test_processing_log_shows_nine_lines_and_keeps_scrollable_history():
    app = _app()
    from cipa_crop_coord.ui import MatchTab, CenterTab
    for tab_cls in (MatchTab, CenterTab):
        tab = tab_cls("ja")
        tab.show()
        app.processEvents()
        try:
            nine_lines = 9 * tab.log.fontMetrics().lineSpacing()
            assert nine_lines + 8 <= tab.log.height() <= nine_lines + 32
            assert tab.log.minimumHeight() == tab.log.maximumHeight()
            for i in range(40):
                tab.log.appendPlainText(f"record {i:02}")
            assert tab.log.document().blockCount() == 40
            assert tab.log.verticalScrollBar().maximum() > 0
        finally:
            tab.close()
