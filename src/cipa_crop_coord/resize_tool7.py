from __future__ import annotations

import glob
import os
from pathlib import Path

import cv2

from .engine import Cancelled, Summary, parallel
from .locales import tr


DEFAULT_RESIZE_RATIO = 0.25
EXTENSION = ".jpg"


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
    """Batch resize JPG files with Tool 7-compatible OpenCV image processing.

    The destination root is user-selected, but the compatibility-critical per-image
    operations remain exactly:
      cv2.imread -> cv2.resize(fx=ratio, fy=ratio) -> cv2.imwrite(no params)

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

    # If the user places the output folder inside the input tree, never feed existing
    # output JPGs back into the same batch.
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

            # Keep the same OpenCV load/resize/save calls as tool_7_resize_image(1).py.
            image = cv2.imread(str(file))
            resize_image = cv2.resize(image, (0, 0), fx=ratio, fy=ratio)
            if not cv2.imwrite(str(destination), resize_image):
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
