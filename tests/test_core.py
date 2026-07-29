from __future__ import annotations

import csv
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from cipa_crop_coord.core import (
    MatchSettings,
    Rect,
    batch_export_coordinates,
    central_crop_rect,
    iter_images,
    locate_template,
    output_filename,
    prepare_template,
)


def _write(path: Path, image: np.ndarray) -> None:
    ok, data = cv2.imencode(path.suffix, image)
    assert ok
    data.tofile(path)


def _pattern() -> np.ndarray:
    rng = np.random.default_rng(42)
    image = rng.integers(0, 256, (80, 100), dtype=np.uint8)
    cv2.circle(image, (50, 40), 18, 245, 3)
    cv2.line(image, (20, 10), (85, 70), 15, 4)
    return image


def test_rect_and_center_crop() -> None:
    assert Rect(10, 20, 0, 0).resolved(100, 80) == Rect(10, 20, 90, 60)
    assert central_crop_rect(1200, 900, ratio="1/3") == Rect(400, 300, 400, 300)
    assert central_crop_rect(1200, 900, width=600, height=500) == Rect(
        300, 200, 600, 500
    )


def test_recursive_images_and_excluded_output(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    output = tmp_path / "output"
    nested.mkdir()
    output.mkdir()
    (nested / "a.JPG").write_bytes(b"x")
    (nested / "readme.txt").write_text("x")
    (output / "old.jpg").write_bytes(b"x")
    assert [path.name for path in iter_images(tmp_path, [output])] == ["a.JPG"]


def test_exif_shutter_filename(tmp_path: Path) -> None:
    path = tmp_path / "abc.jpg"
    image = Image.new("RGB", (10, 10), "red")
    exif = Image.Exif()
    exif[33434] = (1, 100)
    image.save(path, exif=exif)
    assert output_filename(path) == "1_100_abc.jpg"


def test_locate_and_coordinate_csv(tmp_path: Path) -> None:
    sample_gray = _pattern()
    sample_color = cv2.cvtColor(sample_gray, cv2.COLOR_GRAY2BGR)
    sample_path = tmp_path / "sample.png"
    _write(sample_path, sample_color)

    input_folder = tmp_path / "input"
    input_folder.mkdir()
    target = np.zeros((500, 700), dtype=np.uint8)
    top_left = (310, 190)
    target[
        top_left[1] : top_left[1] + sample_gray.shape[0],
        top_left[0] : top_left[0] + sample_gray.shape[1],
    ] = sample_gray
    target_path = input_folder / "target.png"
    _write(target_path, cv2.cvtColor(target, cv2.COLOR_GRAY2BGR))

    prepared = prepare_template(sample_path, Rect(), 10)
    result = locate_template(target, prepared, Rect(), coarse_max_dimension=180)
    assert abs(result.x - (top_left[0] + 50)) <= 1
    assert abs(result.y - (top_left[1] + 40)) <= 1
    assert result.score > 0.99

    csv_path = tmp_path / "coordinates.csv"
    summary = batch_export_coordinates(
        str(sample_path),
        str(input_folder),
        str(csv_path),
        MatchSettings(edge_mask_percent=10, threshold=0.8, coarse_max_dimension=180),
    )
    assert summary.succeeded == 1
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows == [["文件名", "x坐标", "y坐标"], ["target.png", "360", "230"]]
