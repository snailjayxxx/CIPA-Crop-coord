from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from cipa_crop_coord.ui_user_text import MainWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_user_facing_pages_do_not_show_tool_numbers() -> None:
    _app()
    window = MainWindow()
    for tab in (window.d, window.e):
        visible_text = "\n".join(label.text() for label in tab.findChildren(QLabel))
        assert "Tool 7" not in visible_text
        assert "Tool 12" not in visible_text
        assert "imwrite" not in visible_text
        assert "OpenCV" not in visible_text
    window.close()


def test_main_window_has_five_tabs() -> None:
    _app()
    window = MainWindow()
    assert window.tabs.count() == 5
    window.close()
