"""GUI regression checks for collapsed settings, localization and progress counts."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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
