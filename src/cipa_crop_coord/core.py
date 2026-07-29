from __future__ import annotations

import csv
import math
import os
import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable, Iterable

import cv2
import numpy as np
from PIL import Image


SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}

ProgressCallback = Callable[[int, int, str], None]
CancelCallback = Callable[[], bool]


class ProcessingCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class Rect:
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    def resolved(self, image_width: int, image_height: int) -> "Rect":
        x = max(0, min(int(self.x), image_width))
        y = max(0, min(int(self.y), image_height))
        width = int(self.width) if self.width > 0 else image_width - x
        height = int(self.height) if self.height > 0 else image_height - y
        width = max(0, min(width, image_width - x))
        height = max(0, min(height, image_height - y))
        if width <= 0 or height <= 0:
            raise ValueError("指定范围不在图片内")
        return Rect(x, y, width, height)


@dataclass(frozen=True)
class MatchSettings:
    template_rect: Rect = Rect()
    search_rect: Rect = Rect()
    edge_mask_percent: float = 10.0
    threshold: float = 0.70
    coarse_max_dimension: int = 1800


@dataclass(frozen=True)
class MatchResult:
    x: int
    y: int
    score: float
    crop_rect: Rect


@dataclass
class BatchSummary:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    output_path: str = ""


@dataclass(frozen=True)
class PreparedTemplate:
    inner_gray: np.ndarray
    full_width: int
    full_height: int
    margin_x: int
    margin_y: int


def iter_images(
    folder: str | os.PathLike[str],
    exclude_folders: Iterable[str | os.PathLike[str]] = (),
) -> list[Path]:
    root = Path(folder)
    if not root.is_dir():
        raise ValueError(f"图片文件夹不存在：{root}")
    excluded = []
    for folder_path in exclude_folders:
        try:
            excluded.append(Path(folder_path).resolve())
        except OSError:
            continue

    def is_excluded(item: Path) -> bool:
        try:
            resolved = item.resolve()
            return any(resolved == folder or resolved.is_relative_to(folder) for folder in excluded)
        except OSError:
            return False

    return sorted(
        (
            item
            for item in root.rglob("*")
            if item.is_file()
            and item.suffix.lower() in SUPPORTED_EXTENSIONS
            and not is_excluded(item)
        ),
        key=lambda item: str(item).casefold(),
    )


def read_image(path: str | os.PathLike[str], grayscale: bool = False) -> np.ndarray:
    """Read Unicode paths on Windows and honor EXIF orientation where OpenCV supports it."""
    file_path = Path(path)
    data = np.fromfile(file_path, dtype=np.uint8)
    flag = cv2.IMREAD_GRAYSCALE if grayscale else cv2.IMREAD_COLOR
    image = cv2.imdecode(data, flag)
    if image is None:
        raise ValueError(f"无法读取图片：{file_path}")
    return image


def write_image(path: str | os.PathLike[str], image: np.ndarray, jpeg_quality: int = 95) -> Path:
    output = Path(path)
    suffix = output.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        output = output.with_suffix(".jpg")
        suffix = ".jpg"
    params: list[int] = []
    if suffix in {".jpg", ".jpeg"}:
        params = [cv2.IMWRITE_JPEG_QUALITY, max(1, min(int(jpeg_quality), 100))]
    success, encoded = cv2.imencode(suffix, image, params)
    if not success:
        raise ValueError(f"无法编码输出图片：{output.name}")
    output.parent.mkdir(parents=True, exist_ok=True)
    encoded.tofile(output)
    return output


def _safe_filename_part(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value)
    return cleaned.strip(" ._") or "unknown"


def shutter_prefix(path: str | os.PathLike[str]) -> str:
    """Return an EXIF exposure-time prefix such as 1_100."""
    try:
        with Image.open(path) as image:
            exposure = image.getexif().get(33434)
        if exposure is None:
            return "unknown"
        if isinstance(exposure, tuple) and len(exposure) == 2:
            fraction = Fraction(int(exposure[0]), int(exposure[1]))
        else:
            fraction = Fraction(float(exposure)).limit_denominator(1_000_000)
        if fraction <= 0:
            return "unknown"
        if fraction.denominator == 1:
            return _safe_filename_part(str(fraction.numerator))
        return _safe_filename_part(f"{fraction.numerator}_{fraction.denominator}")
    except (OSError, ValueError, TypeError, ZeroDivisionError):
        return "unknown"


def output_filename(source: str | os.PathLike[str]) -> str:
    source_path = Path(source)
    return f"{shutter_prefix(source_path)}_{_safe_filename_part(source_path.stem)}{source_path.suffix.lower()}"


def unique_output_path(output_folder: str | os.PathLike[str], filename: str) -> Path:
    folder = Path(output_folder)
    candidate = folder / filename
    index = 2
    while candidate.exists():
        candidate = folder / f"{Path(filename).stem}__{index}{Path(filename).suffix}"
        index += 1
    return candidate


def prepare_template(
    sample_path: str | os.PathLike[str],
    template_rect: Rect,
    edge_mask_percent: float,
) -> PreparedTemplate:
    sample = read_image(sample_path, grayscale=True)
    height, width = sample.shape[:2]
    rect = template_rect.resolved(width, height)
    mask_percent = max(0.0, min(float(edge_mask_percent), 45.0))
    margin_x = int(round(rect.width * mask_percent / 100.0))
    margin_y = int(round(rect.height * mask_percent / 100.0))
    inner_width = rect.width - margin_x * 2
    inner_height = rect.height - margin_y * 2
    if inner_width < 8 or inner_height < 8:
        raise ValueError("屏蔽边缘后模板过小，请减小屏蔽比例或扩大模板范围")
    inner = sample[
        rect.y + margin_y : rect.y + rect.height - margin_y,
        rect.x + margin_x : rect.x + rect.width - margin_x,
    ].copy()
    return PreparedTemplate(inner, rect.width, rect.height, margin_x, margin_y)


def _best_match(search: np.ndarray, template: np.ndarray) -> tuple[int, int, float]:
    if search.shape[0] < template.shape[0] or search.shape[1] < template.shape[1]:
        raise ValueError("搜索范围小于模板")
    scores = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
    np.nan_to_num(scores, copy=False, nan=-1.0, posinf=-1.0, neginf=-1.0)
    _, score, _, location = cv2.minMaxLoc(scores)
    return int(location[0]), int(location[1]), float(score)


def locate_template(
    image_gray: np.ndarray,
    prepared: PreparedTemplate,
    search_rect: Rect,
    coarse_max_dimension: int = 1800,
) -> MatchResult:
    image_height, image_width = image_gray.shape[:2]
    search = search_rect.resolved(image_width, image_height)
    search_image = image_gray[
        search.y : search.y + search.height,
        search.x : search.x + search.width,
    ]
    template = prepared.inner_gray
    template_height, template_width = template.shape[:2]
    if search.width < template_width or search.height < template_height:
        raise ValueError("搜索范围小于有效模板范围")

    max_dimension = max(search.width, search.height)
    scale = min(1.0, max(64, int(coarse_max_dimension)) / max_dimension)
    if scale < 0.999 and min(template_width * scale, template_height * scale) >= 12:
        coarse_search = cv2.resize(
            search_image,
            (max(1, round(search.width * scale)), max(1, round(search.height * scale))),
            interpolation=cv2.INTER_AREA,
        )
        coarse_template = cv2.resize(
            template,
            (max(1, round(template_width * scale)), max(1, round(template_height * scale))),
            interpolation=cv2.INTER_AREA,
        )
        coarse_x, coarse_y, _ = _best_match(coarse_search, coarse_template)
        approximate_x = round(coarse_x / scale)
        approximate_y = round(coarse_y / scale)
        radius = max(12, int(math.ceil(5.0 / scale)))
        refine_x0 = max(0, approximate_x - radius)
        refine_y0 = max(0, approximate_y - radius)
        refine_x1 = min(search.width, approximate_x + template_width + radius)
        refine_y1 = min(search.height, approximate_y + template_height + radius)
        refine = search_image[refine_y0:refine_y1, refine_x0:refine_x1]
        local_x, local_y, score = _best_match(refine, template)
        inner_x = search.x + refine_x0 + local_x
        inner_y = search.y + refine_y0 + local_y
    else:
        local_x, local_y, score = _best_match(search_image, template)
        inner_x = search.x + local_x
        inner_y = search.y + local_y

    crop_x = inner_x - prepared.margin_x
    crop_y = inner_y - prepared.margin_y
    crop_rect = Rect(crop_x, crop_y, prepared.full_width, prepared.full_height)
    if (
        crop_x < 0
        or crop_y < 0
        or crop_x + crop_rect.width > image_width
        or crop_y + crop_rect.height > image_height
    ):
        raise ValueError("匹配位置靠近边缘，无法裁出完整 sample 范围")
    center_x = crop_x + prepared.full_width // 2
    center_y = crop_y + prepared.full_height // 2
    return MatchResult(center_x, center_y, score, crop_rect)


def _notify(
    callback: ProgressCallback | None,
    current: int,
    total: int,
    message: str,
) -> None:
    if callback:
        callback(current, total, message)


def _check_cancelled(callback: CancelCallback | None) -> None:
    if callback and callback():
        raise ProcessingCancelled("用户已取消处理")


def batch_match_crop(
    sample_path: str,
    input_folder: str,
    output_folder: str,
    settings: MatchSettings,
    jpeg_quality: int = 95,
    progress: ProgressCallback | None = None,
    cancelled: CancelCallback | None = None,
) -> BatchSummary:
    files = iter_images(input_folder, exclude_folders=[output_folder])
    prepared = prepare_template(
        sample_path, settings.template_rect, settings.edge_mask_percent
    )
    Path(output_folder).mkdir(parents=True, exist_ok=True)
    summary = BatchSummary(total=len(files), output_path=str(output_folder))
    for index, path in enumerate(files, start=1):
        _check_cancelled(cancelled)
        try:
            image = read_image(path)
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            result = locate_template(
                gray, prepared, settings.search_rect, settings.coarse_max_dimension
            )
            if result.score < settings.threshold:
                summary.skipped += 1
                _notify(
                    progress,
                    index,
                    len(files),
                    f"跳过（相似度 {result.score:.3f}）：{path.name}",
                )
                continue
            rect = result.crop_rect
            crop = image[rect.y : rect.y + rect.height, rect.x : rect.x + rect.width]
            destination = unique_output_path(output_folder, output_filename(path))
            write_image(destination, crop, jpeg_quality)
            summary.succeeded += 1
            _notify(
                progress,
                index,
                len(files),
                f"完成（相似度 {result.score:.3f}）：{path.name}",
            )
        except Exception as exc:
            summary.failed += 1
            _notify(progress, index, len(files), f"失败：{path.name} — {exc}")
    return summary


def _parse_fraction(value: str | float) -> float:
    if isinstance(value, float):
        ratio = value
    else:
        text = str(value).strip()
        try:
            ratio = float(Fraction(text))
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError("比例请输入 1/3、1/4 或 0.5 这样的数值") from exc
    if not 0 < ratio <= 1:
        raise ValueError("裁切比例必须大于 0 且不超过 1")
    return ratio


def central_crop_rect(
    image_width: int,
    image_height: int,
    width: int = 0,
    height: int = 0,
    ratio: str | float | None = None,
) -> Rect:
    if ratio is not None:
        parsed = _parse_fraction(ratio)
        crop_width = max(1, round(image_width * parsed))
        crop_height = max(1, round(image_height * parsed))
    else:
        crop_width = int(width)
        crop_height = int(height)
        if crop_width <= 0 or crop_height <= 0:
            raise ValueError("固定像素模式下，宽度和高度必须大于 0")
        if crop_width > image_width or crop_height > image_height:
            raise ValueError("指定裁切像素大于原图")
    return Rect(
        (image_width - crop_width) // 2,
        (image_height - crop_height) // 2,
        crop_width,
        crop_height,
    )


def batch_center_crop(
    input_folder: str,
    output_folder: str,
    width: int = 0,
    height: int = 0,
    ratio: str | float | None = None,
    jpeg_quality: int = 95,
    progress: ProgressCallback | None = None,
    cancelled: CancelCallback | None = None,
) -> BatchSummary:
    files = iter_images(input_folder, exclude_folders=[output_folder])
    Path(output_folder).mkdir(parents=True, exist_ok=True)
    summary = BatchSummary(total=len(files), output_path=str(output_folder))
    for index, path in enumerate(files, start=1):
        _check_cancelled(cancelled)
        try:
            image = read_image(path)
            image_height, image_width = image.shape[:2]
            rect = central_crop_rect(
                image_width, image_height, width=width, height=height, ratio=ratio
            )
            crop = image[rect.y : rect.y + rect.height, rect.x : rect.x + rect.width]
            destination = unique_output_path(output_folder, output_filename(path))
            write_image(destination, crop, jpeg_quality)
            summary.succeeded += 1
            _notify(progress, index, len(files), f"完成：{path.name}")
        except Exception as exc:
            summary.failed += 1
            _notify(progress, index, len(files), f"失败：{path.name} — {exc}")
    return summary


def batch_export_coordinates(
    sample_path: str,
    input_folder: str,
    csv_path: str,
    settings: MatchSettings,
    progress: ProgressCallback | None = None,
    cancelled: CancelCallback | None = None,
) -> BatchSummary:
    files = iter_images(input_folder)
    prepared = prepare_template(
        sample_path, settings.template_rect, settings.edge_mask_percent
    )
    rows: list[tuple[str, str | int, str | int]] = []
    summary = BatchSummary(total=len(files), output_path=str(csv_path))
    root = Path(input_folder)
    for index, path in enumerate(files, start=1):
        _check_cancelled(cancelled)
        relative_name = path.relative_to(root).as_posix()
        try:
            image = read_image(path, grayscale=True)
            result = locate_template(
                image, prepared, settings.search_rect, settings.coarse_max_dimension
            )
            if result.score >= settings.threshold:
                rows.append((relative_name, result.x, result.y))
                summary.succeeded += 1
                message = f"已记录（相似度 {result.score:.3f}）：{relative_name}"
            else:
                rows.append((relative_name, "", ""))
                summary.skipped += 1
                message = f"未达阈值（{result.score:.3f}）：{relative_name}"
            _notify(progress, index, len(files), message)
        except Exception as exc:
            rows.append((relative_name, "", ""))
            summary.failed += 1
            _notify(progress, index, len(files), f"失败：{relative_name} — {exc}")

    output = Path(csv_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["文件名", "x坐标", "y坐标"])
        writer.writerows(rows)
    return summary
