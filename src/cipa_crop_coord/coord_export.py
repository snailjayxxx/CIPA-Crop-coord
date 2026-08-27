from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .engine import Cancelled, Summary, debug_write, images, parallel, read, stem


MODE_RELATIVE_PREVIOUS = "relative_previous"
MODE_ABSOLUTE = "absolute"


@dataclass(frozen=True)
class PythonMatchResult:
    x: int
    y: int
    score: float
    top_left_x: int
    top_left_y: int
    width: int
    height: int


def python_match_center(image: np.ndarray, template: np.ndarray) -> PythonMatchResult:
    """Reproduce tool_9_calc_chart_center.py's feature-point detection path.

    The reference script performs full-color TM_CCOEFF_NORMED template matching,
    takes cv2.minMaxLoc(...).max_loc, then records the center of the matched
    template rectangle.  No grayscale conversion, thresholding, edge masking,
    search masking, coarse matching, refinement, or similarity cutoff is used.
    """
    if image is None or template is None:
        raise ValueError("图片或模板为空")
    if image.ndim != template.ndim:
        raise ValueError("图片与模板通道数不一致")
    if image.ndim == 3 and image.shape[2] != template.shape[2]:
        raise ValueError("图片与模板通道数不一致")

    template_h, template_w = template.shape[:2]
    image_h, image_w = image.shape[:2]
    if image_h < template_h or image_w < template_w:
        raise ValueError("被遍历图片尺寸小于模板图片")

    # The source Python explicitly resizes each target image with resize_ratio=1.
    # Keep that step so the coordinate-export path mirrors it as closely as possible.
    resize_image = cv2.resize(image, (0, 0), fx=1.0, fy=1.0)
    result = cv2.matchTemplate(resize_image, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    top_left_x, top_left_y = int(max_loc[0]), int(max_loc[1])
    bottom_right_x = top_left_x + template_w
    bottom_right_y = top_left_y + template_h
    center_x = (top_left_x + bottom_right_x) // 2
    center_y = (top_left_y + bottom_right_y) // 2

    return PythonMatchResult(
        center_x,
        center_y,
        float(max_val),
        top_left_x,
        top_left_y,
        template_w,
        template_h,
    )


def _text(lang: str, key: str, **kwargs) -> str:
    texts = {
        "zh": {
            "record": "已记录（最大相似度 {score:.3f}）：{name}",
            "fail": "失败：{name} — {error}",
        },
        "ja": {
            "record": "記録済み（最大類似度 {score:.3f}）：{name}",
            "fail": "失敗：{name} — {error}",
        },
    }
    language = "ja" if lang == "ja" else "zh"
    return texts[language][key].format(**kwargs)


def _header(lang: str, mode: str) -> tuple[str, str, str]:
    if lang == "ja":
        if mode == MODE_RELATIVE_PREVIOUS:
            return ("ファイル名", "Δx（前画像比）", "Δy（前画像比）")
        return ("ファイル名", "x座標", "y座標")
    if mode == MODE_RELATIVE_PREVIOUS:
        return ("文件名", "Δx（相对上一张）", "Δy（相对上一张）")
    return ("文件名", "x坐标", "y坐标")


def _debug_match(debug_folder: Path, index: int, path: Path, image: np.ndarray, match: PythonMatchResult) -> None:
    output = image.copy()
    top_left = (match.top_left_x, match.top_left_y)
    bottom_right = (match.top_left_x + match.width, match.top_left_y + match.height)
    center = (match.x, match.y)
    thickness = max(2, round(max(output.shape[:2]) / 1000))
    radius = max(8, round(max(output.shape[:2]) / 250))
    cv2.rectangle(output, top_left, bottom_right, (0, 255, 0), thickness)
    cv2.circle(output, center, radius, (0, 0, 255), thickness)
    debug_write(debug_folder / f"{stem(index, path)}_python_match.jpg", output)


def export_coords_python(
    sample: str,
    input_folder: str,
    csv_path: str,
    mode: str = MODE_RELATIVE_PREVIOUS,
    progress=None,
    cancel=None,
    lang: str = "zh",
    workers: int = 2,
    debug: bool = False,
) -> Summary:
    if mode not in {MODE_RELATIVE_PREVIOUS, MODE_ABSOLUTE}:
        raise ValueError(f"Unsupported coordinate mode: {mode}")

    output = Path(csv_path)
    debug_folder = output.parent / f"{output.stem}_debug"
    files = images(input_folder, [debug_folder], lang)
    root = Path(input_folder)
    template = read(sample, False, lang)
    summary = Summary(
        total=len(files),
        output_path=str(output),
        debug_path=str(debug_folder) if debug else "",
    )

    if cancel and cancel():
        raise Cancelled()

    def one(i: int, path: Path):
        name = path.relative_to(root).as_posix()
        try:
            image = read(path, False, lang)
            match = python_match_center(image, template)
            if debug:
                _debug_match(debug_folder, i + 1, path, image, match)
            return (
                i,
                _text(lang, "record", score=match.score, name=name),
                ("ok", name, path.parent, match.x, match.y),
            )
        except Exception as exc:
            return (
                i,
                _text(lang, "fail", name=name, error=exc),
                ("fail", name, path.parent, "", ""),
            )

    results = parallel(files, one, workers, progress, cancel)

    rows: list[tuple[str, str | int, str | int]] = []
    previous_by_folder: dict[Path, tuple[int, int] | None] = {}
    for result in results:
        if result is None:
            continue
        status, name, parent, x, y = result
        if status != "ok":
            summary.failed += 1
            rows.append((name, "", ""))
            previous_by_folder[parent] = None
            continue

        summary.succeeded += 1
        x = int(x)
        y = int(y)
        if mode == MODE_ABSOLUTE:
            rows.append((name, x, y))
            continue

        previous = previous_by_folder.get(parent)
        if previous is None:
            rows.append((name, 0, 0))
        else:
            rows.append((name, x - previous[0], y - previous[1]))
        previous_by_folder[parent] = (x, y)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(_header(lang, mode))
        writer.writerows(rows)

    return summary
