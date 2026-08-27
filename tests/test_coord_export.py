from __future__ import annotations

import csv
from pathlib import Path

import cv2
import numpy as np

from cipa_crop_coord.coord_export import (
    MODE_ABSOLUTE,
    MODE_RELATIVE_PREVIOUS,
    export_coords_python,
    python_match_center,
)


def _write(path: Path, image: np.ndarray) -> None:
    ok, data = cv2.imencode(path.suffix, image)
    assert ok
    data.tofile(path)


def _template() -> np.ndarray:
    rng = np.random.default_rng(20260827)
    template = rng.integers(0, 256, (24, 30, 3), dtype=np.uint8)
    cv2.circle(template, (8, 9), 5, (255, 30, 180), 2)
    cv2.line(template, (2, 20), (27, 3), (10, 240, 70), 2)
    return template


def _target(template: np.ndarray, x: int, y: int) -> np.ndarray:
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    h, w = template.shape[:2]
    image[y : y + h, x : x + w] = template
    return image


def test_python_match_center_matches_reference_formula():
    template = _template()
    image = _target(template, 41, 37)
    match = python_match_center(image, template)
    assert (match.top_left_x, match.top_left_y) == (41, 37)
    assert (match.x, match.y) == (41 + 30 // 2, 37 + 24 // 2)
    assert match.score > 0.999


def test_export_absolute_coordinates(tmp_path):
    template = _template()
    sample = tmp_path / "template.png"
    _write(sample, template)
    input_folder = tmp_path / "input"
    input_folder.mkdir()
    _write(input_folder / "001.png", _target(template, 20, 30))
    _write(input_folder / "002.png", _target(template, 28, 26))

    csv_path = tmp_path / "absolute.csv"
    summary = export_coords_python(
        str(sample),
        str(input_folder),
        str(csv_path),
        mode=MODE_ABSOLUTE,
        workers=2,
    )

    assert summary.succeeded == 2
    rows = list(csv.reader(csv_path.open(encoding="utf-8-sig")))
    assert rows == [
        ["文件名", "x坐标", "y坐标"],
        ["001.png", "35", "42"],
        ["002.png", "43", "38"],
    ]


def test_export_relative_to_previous_and_reset_each_folder(tmp_path):
    template = _template()
    sample = tmp_path / "template.png"
    _write(sample, template)
    input_folder = tmp_path / "input"
    group_a = input_folder / "A"
    group_b = input_folder / "B"
    group_a.mkdir(parents=True)
    group_b.mkdir(parents=True)

    _write(group_a / "001.png", _target(template, 20, 30))
    _write(group_a / "002.png", _target(template, 24, 25))
    _write(group_a / "003.png", _target(template, 19, 32))
    _write(group_b / "001.png", _target(template, 70, 50))

    csv_path = tmp_path / "relative.csv"
    summary = export_coords_python(
        str(sample),
        str(input_folder),
        str(csv_path),
        mode=MODE_RELATIVE_PREVIOUS,
        workers=2,
    )

    assert summary.succeeded == 4
    rows = list(csv.reader(csv_path.open(encoding="utf-8-sig")))
    assert rows == [
        ["文件名", "Δx（相对上一张）", "Δy（相对上一张）"],
        ["A/001.png", "0", "0"],
        ["A/002.png", "4", "-5"],
        ["A/003.png", "-5", "7"],
        ["B/001.png", "0", "0"],
    ]
