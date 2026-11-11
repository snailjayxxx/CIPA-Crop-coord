"""Local-only crash diagnostics for the packaged Windows GUI.

This never uploads photos, processed image buffers, or private files. Fatal
Python/C crashes may be recorded; an operating-system hard kill might not be.
"""
from __future__ import annotations

import faulthandler
import os
from pathlib import Path
import sys
import threading
import traceback
from datetime import datetime, timezone

_FILE = None


def log_path() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "CIPA-Crop-Coord" / "logs" / "runtime.log"
    return Path.home() / ".cipa-crop-coord" / "logs" / "runtime.log"


def start_logging() -> Path | None:
    """Called before importing Qt; cannot interfere with GUI startup."""
    global _FILE
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 5_000_000:
            path.replace(path.with_name("runtime.previous.log"))
        _FILE = path.open("a", encoding="utf-8", buffering=1)
        _FILE.write(
            "\n=== GUI start "
            + datetime.now(timezone.utc).isoformat()
            + f" (pid={os.getpid()}, Python={sys.version_info.major}.{sys.version_info.minor}) ===\n"
        )
        faulthandler.enable(file=_FILE, all_threads=True)
        old_hook = sys.excepthook

        def exception_hook(exc_type, exc, tb):
            try:
                traceback.print_exception(exc_type, exc, tb, file=_FILE)
            except (OSError, ValueError):
                pass
            old_hook(exc_type, exc, tb)

        sys.excepthook = exception_hook
        return path
    except (OSError, ValueError):
        return None


def record_worker_plan(
    *, selected_images: int, source_pixels: int, crop_pixels: int,
    requested_crop: int, actual_crop: int, requested_calc: int, actual_calc: int,
    available_gib: float | None, deferred: bool,
) -> None:
    """Records counts/memory/thread limits but never input paths or filenames."""
    if _FILE is None:
        return
    try:
        _FILE.write(
            "Batch start: "
            f"image_count={selected_images}, "
            f"largest_source_pixels={source_pixels}, crop_pixels={crop_pixels}, "
            f"requested_crop={requested_crop}, actual_crop={actual_crop}, "
            f"requested_calc={requested_calc}, actual_calc={actual_calc}, "
            f"available_gib={available_gib}, deferred={deferred}\n"
        )
    except (OSError, ValueError):
        pass
