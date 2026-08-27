from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
from PySide6.QtWidgets import QApplication, QLabel

from cipa_crop_coord.locales import TEXT, tr
from cipa_crop_coord.resize_tool7 import DEFAULT_RESIZE_RATIO, resize_images_tool7
from cipa_crop_coord.ui_coord_modes import CoordTab, MainWindow, ResizeTab


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_all_three_languages_have_identical_keys() -> None:
    assert set(TEXT["zh"]) == set(TEXT["ja"]) == set(TEXT["en"])
    assert tr("en", "tab4") == "④ Image compression"


def test_main_window_has_four_tabs_and_three_languages() -> None:
    _app()
    window = MainWindow()
    assert window.tabs.count() == 4
    assert [window.combo.itemData(i) for i in range(window.combo.count())] == ["zh", "ja", "en"]
    window.close()


def test_coordinate_page_has_no_algorithm_explanation() -> None:
    _app()
    tab = CoordTab("zh")
    text = "\n".join(label.text() for label in tab.findChildren(QLabel))
    assert "calc_center_point" not in text
    assert "cv2.matchTemplate" not in text


def test_resize_page_defaults_match_tool7() -> None:
    _app()
    tab = ResizeTab("en")
    assert tab.ratio.value() == DEFAULT_RESIZE_RATIO == 0.25


def test_resize_output_bytes_match_direct_tool7_pipeline(tmp_path: Path) -> None:
    source_root = tmp_path / "input"
    nested = source_root / "nested"
    nested.mkdir(parents=True)

    rng = np.random.default_rng(20260827)
    image = rng.integers(0, 256, (181, 263, 3), dtype=np.uint8)
    cv2.circle(image, (100, 80), 35, (20, 230, 110), 4)
    source = nested / "sample.jpg"
    assert cv2.imwrite(str(source), image)

    summary = resize_images_tool7(str(source_root), ratio=0.25, workers=2)
    output = nested / "resize_images" / "sample.jpg"
    assert summary.succeeded == 1
    assert output.exists()

    # Reference implementation: exactly the same three calls used by tool_7_resize_image(1).py.
    reference_image = cv2.imread(str(source))
    reference_resize = cv2.resize(reference_image, (0, 0), fx=0.25, fy=0.25)
    reference = tmp_path / "reference.jpg"
    assert cv2.imwrite(str(reference), reference_resize)

    assert output.read_bytes() == reference.read_bytes()


def test_resize_recurses_jpg_only_and_preserves_name(tmp_path: Path) -> None:
    root = tmp_path / "input"
    sub = root / "A"
    sub.mkdir(parents=True)
    image = np.full((80, 120, 3), 127, dtype=np.uint8)
    assert cv2.imwrite(str(sub / "a.jpg"), image)
    assert cv2.imwrite(str(sub / "b.png"), image)

    summary = resize_images_tool7(str(root), ratio=0.5, workers=1)
    assert summary.total == 1
    assert (sub / "resize_images" / "a.jpg").exists()
    assert not (sub / "resize_images" / "b.png").exists()
