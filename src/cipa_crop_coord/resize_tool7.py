from __future__ import annotations

import glob
import os
from pathlib import Path

import cv2

from .engine import Cancelled, Summary, parallel
from .locales import tr


OUTPUT_DIR_NAME = "resize_images"
DEFAULT_RESIZE_RATIO = 0.25
EXTENSION = ".jpg"


def resize_images_tool7(
    input_folder: str,
    ratio: float = DEFAULT_RESIZE_RATIO,
    progress=None,
    cancel=None,
    lang: str = "zh",
    workers: int = 2,
    debug: bool = False,
) -> Summary:
    """Batch resize JPG files using the same per-image pipeline as tool_7_resize_image(1).py.

    Compatibility-critical operations are intentionally kept as:
      cv2.imread -> cv2.resize(fx=ratio, fy=ratio) -> cv2.imwrite(no params)
    Output directory name and recursive *.jpg discovery also match the source script.
    """
    del debug
    selected = Path(input_folder)
    if not selected.is_dir():
        raise ValueError(tr(lang, "folder_missing", path=selected))

    ratio = float(ratio)
    if ratio <= 0:
        raise ValueError(tr(lang, "resize_ratio_positive"))

    files = [Path(p) for p in glob.glob(os.path.join(input_folder, "**", "*.jpg"), recursive=True)]
    summary = Summary(total=len(files), output_path=str(selected))

    if cancel and cancel():
        raise Cancelled()

    def one(index: int, file: Path):
        try:
            dir_of_file = os.path.dirname(str(file))
            dir_of_output = dir_of_file + "/" + OUTPUT_DIR_NAME
            os.makedirs(dir_of_output, exist_ok=True)

            # Keep the same OpenCV load/resize/save calls as the source Python.
            image = cv2.imread(str(file))
            resize_image = cv2.resize(image, (0, 0), fx=ratio, fy=ratio)
            root, ext = os.path.splitext(str(file))
            name_of_file = os.path.basename(root)
            destination = dir_of_output + "/" + name_of_file + ext
            if not cv2.imwrite(destination, resize_image):
                raise ValueError(tr(lang, "resize_write_failed", path=destination))

            return index, tr(lang, "resize_done", name=file.name), ("ok", destination)
        except Exception as exc:
            return index, tr(lang, "fail", name=file.name, error=exc), ("fail", None)

    results = parallel(files, one, workers, progress, cancel)
    output_dirs: set[str] = set()
    for result in results:
        if not result:
            continue
        status, destination = result
        if status == "ok":
            summary.succeeded += 1
            if destination:
                output_dirs.add(str(Path(destination).parent))
        else:
            summary.failed += 1

    if len(output_dirs) == 1:
        summary.output_path = next(iter(output_dirs))
    else:
        summary.output_path = tr(lang, "resize_output_multiple", root=selected)
    return summary
