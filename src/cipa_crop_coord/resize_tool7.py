from __future__ import annotations

import glob
import os
from pathlib import Path

import cv2
import numpy as np

from .engine import Cancelled, Summary, parallel
from .locales import tr


DEFAULT_RESIZE_RATIO = 0.25
EXTENSION = ".jpg"


def _imread_unicode(path: Path):
    """Read an image with OpenCV decoding while supporting Unicode Windows paths."""
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def _imwrite_jpeg_unicode(path: Path, image) -> bool:
    """Encode JPEG with OpenCV defaults and write through Unicode-safe Python I/O."""
    ok, encoded = cv2.imencode(".jpg", image)
    if not ok:
        return False
    try:
        with path.open("wb") as stream:
            encoded.tofile(stream)
        return True
    except OSError:
        return False


def resize_images_tool7(
    input_folder: str,
    output_folder: str,
    ratio: float = DEFAULT_RESIZE_RATIO,
    progress=None,
    cancel=None,
    lang: str = "zh",
    workers: int = 2,
    debug: bool = False,
) -> Summary:
    """Recursively resize JPG files into a user-selected output folder.

    Image decoding/resizing/JPEG encoding uses OpenCV. Filesystem access is handled
    through Unicode-safe paths so Japanese and Chinese folder/file names work on Windows.
    Relative subfolder structure below the selected input folder is preserved below
    the selected output folder so files with identical names do not overwrite each other.
    """
    del debug

    selected = Path(input_folder)
    output_root = Path(output_folder)
    if not selected.is_dir():
        raise ValueError(tr(lang, "folder_missing", path=selected))

    ratio = float(ratio)
    if ratio <= 0:
        raise ValueError(tr(lang, "resize_ratio_positive"))

    try:
        output_resolved = output_root.resolve()
    except OSError:
        output_resolved = output_root.absolute()

    candidates = [
        Path(p)
        for p in glob.glob(os.path.join(input_folder, "**", "*.jpg"), recursive=True)
    ]

    # If the output folder is inside the input tree, existing outputs are excluded.
    files: list[Path] = []
    for file in candidates:
        try:
            file_resolved = file.resolve()
            if file_resolved == output_resolved or file_resolved.is_relative_to(output_resolved):
                continue
        except OSError:
            pass
        files.append(file)

    output_root.mkdir(parents=True, exist_ok=True)
    summary = Summary(total=len(files), output_path=str(output_root))

    if cancel and cancel():
        raise Cancelled()

    def one(index: int, file: Path):
        try:
            relative = file.relative_to(selected)
            destination = output_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)

            image = _imread_unicode(file)
            if image is None or image.size == 0:
                raise ValueError(tr(lang, "read_fail", path=file))

            resize_image = cv2.resize(image, (0, 0), fx=ratio, fy=ratio)
            if not _imwrite_jpeg_unicode(destination, resize_image):
                raise ValueError(tr(lang, "resize_write_failed", path=destination))

            return index, tr(lang, "resize_done", name=file.name), ("ok", str(destination))
        except Exception as exc:
            return index, tr(lang, "fail", name=file.name, error=exc), ("fail", None)

    results = parallel(files, one, workers, progress, cancel)
    for result in results:
        if not result:
            continue
        status, _destination = result
        if status == "ok":
            summary.succeeded += 1
        else:
            summary.failed += 1

    return summary
