from __future__ import annotations

import os
import math
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path

import cv2
import numpy as np

from .engine import Cancelled, Summary


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}

TEXT = {
    "zh": {
        "output": "请选择 MP4 保存位置。",
        "fps": "每秒图片数必须大于 0，且为有限数值。",
        "count": "视频总帧数必须是大于或等于 0 的整数。",
        "empty": "所选文件夹内没有图片。",
        "encoder": "无法启动 MP4 视频编码器。",
        "invalid": "MP4 编码器未生成有效的视频文件。",
        "black": "黑屏",
        "file_error": "读写视频文件失败：{error}",
        "image_error": "处理图片或视频失败：{error}",
    },
    "ja": {
        "output": "MP4 の保存先を選択してください。",
        "fps": "1秒あたりの画像数は、0 より大きい有限の数値にしてください。",
        "count": "動画の総フレーム数は、0 以上の整数にしてください。",
        "empty": "選択フォルダーに画像がありません。",
        "encoder": "MP4 動画エンコーダーを起動できません。",
        "invalid": "MP4 エンコーダーが有効な動画ファイルを生成しませんでした。",
        "black": "黒画面",
        "file_error": "動画ファイルの読み書きに失敗しました：{error}",
        "image_error": "画像または動画の処理に失敗しました：{error}",
    },
    "en": {
        "output": "Select an MP4 output file.",
        "fps": "FPS must be a finite number greater than zero.",
        "count": "Frame count must be an integer greater than or equal to zero.",
        "empty": "No images were found in the selected folder.",
        "encoder": "Could not open the MP4 video encoder.",
        "invalid": "The MP4 encoder did not create a valid output file.",
        "black": "Black frame",
        "file_error": "Could not read or write the video file: {error}",
        "image_error": "Could not process the image or video: {error}",
    },
}


def vtr(lang: str, key: str, **kwargs) -> str:
    return TEXT.get(lang, TEXT["zh"])[key].format(**kwargs)


@contextmanager
def _localized_errors(lang: str):
    try:
        yield
    except OSError as exc:
        raise type(exc)(vtr(lang, "file_error", error=exc)) from exc
    except cv2.error as exc:
        raise RuntimeError(vtr(lang, "image_error", error=exc)) from exc


def resolve_output_file(output_file: str, input_folder: str, lang: str = "zh") -> Path:
    """Accept either an MP4 filename or a folder pasted into the output field."""
    if not output_file.strip():
        raise ValueError(vtr(lang, "output"))
    destination = Path(output_file.strip())
    if destination.is_dir() or output_file.strip().endswith(("/", "\\")):
        stem = Path(input_folder).resolve().name or "image_sequence"
        destination = destination / (stem + ".mp4")
    if destination.suffix.casefold() != ".mp4":
        destination = destination.with_suffix(".mp4")
    return destination


def _check_cancelled(cancel) -> None:
    # ui.Worker passes Event.is_set itself, so cancel is a callable.
    if cancel is not None and cancel():
        raise Cancelled()


def _publish_video(source: Path, destination: Path, cancel) -> None:
    """Stage beside the destination for atomic publication across drives."""
    staging = None
    try:
        _check_cancelled(cancel)
        with tempfile.NamedTemporaryFile(
            prefix=".cipa_video_", suffix=".part", dir=destination.parent,
            delete=False,
        ) as output:
            staging = Path(output.name)
            with source.open("rb") as encoded:
                while True:
                    _check_cancelled(cancel)
                    block = encoded.read(1024 * 1024)
                    if not block:
                        break
                    output.write(block)
        _check_cancelled(cancel)
        os.replace(staging, destination)
    finally:
        if staging is not None:
            staging.unlink(missing_ok=True)


def _natural_key(path: Path) -> tuple:
    """Case-insensitive, numeric-aware filename order (1, 2, 10)."""
    return tuple(int(part) if part.isdigit() else part.casefold()
                 for part in re.split(r"(\d+)", path.name))


def list_images(folder: str) -> list[Path]:
    if not folder.strip():
        return []
    root = Path(folder)
    if not root.is_dir():
        return []
    return sorted(
        (item for item in root.iterdir()
         if item.is_file() and item.suffix.casefold() in IMAGE_EXTENSIONS),
        key=_natural_key,
    )


def _read_unicode(path: Path) -> np.ndarray | None:
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    except (OSError, ValueError, cv2.error):
        return None


def _to_bgr(image: np.ndarray | None) -> np.ndarray | None:
    if image is None:
        return None
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.ndim != 3:
        return None
    channels = image.shape[2]
    if channels == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    if channels == 3:
        return image
    if channels == 1:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    return None


def _even(value: int) -> int:
    return max(2, value - value % 2)


def _fit_on_black(image: np.ndarray, width: int, height: int) -> np.ndarray:
    source_h, source_w = image.shape[:2]
    if source_w <= 0 or source_h <= 0:
        return np.zeros((height, width, 3), dtype=np.uint8)
    scale = min(width / source_w, height / source_h)
    new_w = max(1, min(width, int(round(source_w * scale))))
    new_h = max(1, min(height, int(round(source_h * scale))))
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    resized = cv2.resize(image, (new_w, new_h), interpolation=interpolation)
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    x = (width - new_w) // 2
    y = (height - new_h) // 2
    canvas[y:y + new_h, x:x + new_w] = resized
    return canvas


def create_video_from_images(
    input_folder: str,
    output_file: str,
    fps: float,
    frame_count: int,
    progress=None,
    cancel=None,
    lang: str = "zh",
    workers: int = 1,
    debug: bool = False,
) -> Summary:
    with _localized_errors(lang):
        del workers, debug  # VideoWriter is intentionally sequential.
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError(vtr(lang, "fps"))
        if not isinstance(frame_count, int) or frame_count < 0:
            raise ValueError(vtr(lang, "count"))
        _check_cancelled(cancel)

        images = list_images(input_folder)
        target = len(images) if frame_count <= 0 else frame_count
        if target <= 0:
            raise ValueError(vtr(lang, "empty"))

        first = None
        for path in images[:target]:
            _check_cancelled(cancel)
            first = _to_bgr(_read_unicode(path))
            if first is not None:
                break
        if first is None:
            width, height = 1920, 1080
        else:
            height, width = first.shape[:2]
            width, height = _even(width), _even(height)

        destination = resolve_output_file(output_file, input_folder, lang)
        destination.parent.mkdir(parents=True, exist_ok=True)

        handle = tempfile.NamedTemporaryFile(prefix="cipa_image_video_", suffix=".mp4", delete=False)
        temporary = Path(handle.name)
        handle.close()
        writer = None
        failed = 0
        try:
            _check_cancelled(cancel)
            writer = cv2.VideoWriter(
                str(temporary), cv2.VideoWriter_fourcc(*"mp4v"), float(fps), (width, height)
            )
            if not writer.isOpened():
                raise RuntimeError(vtr(lang, "encoder"))
            black = np.zeros((height, width, 3), dtype=np.uint8)
            for index in range(target):
                _check_cancelled(cancel)
                if index < len(images):
                    image = _to_bgr(_read_unicode(images[index]))
                    if image is None:
                        frame = black
                        failed += 1
                        name = images[index].name
                    else:
                        frame = _fit_on_black(image, width, height)
                        name = images[index].name
                else:
                    frame = black
                    name = vtr(lang, "black")
                writer.write(frame)
                if progress is not None:
                    progress(index + 1, target, f"{index + 1}/{target}  {name}")
            writer.release()
            writer = None
            if not temporary.exists() or temporary.stat().st_size == 0:
                raise RuntimeError(vtr(lang, "invalid"))
            _publish_video(temporary, destination, cancel)
        finally:
            if writer is not None:
                writer.release()
            temporary.unlink(missing_ok=True)

        return Summary(
            total=target,
            succeeded=target - failed,
            failed=failed,
            skipped=max(0, len(images) - target),
            output_path=str(destination),
            debug_path="",
        )
