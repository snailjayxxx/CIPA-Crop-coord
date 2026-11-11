"""Conservative memory-aware concurrency planning for large CIPA image batches.

All estimates govern *scheduling only*. Pixel processing, JPEG encoding and
FindsBlur's recovered calculation formulas are deliberately untouched.
"""
from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image

MIB = 1024 ** 2
GIB = 1024 ** 3
# OpenCV retains BGR, grayscale, binary/search arrays and codec buffers.
CROP_BYTES_PER_PIXEL = 16
# IJG RGB temporary buffers, Pillow conversion and phase-specific arrays.
CALC_BYTES_PER_PIXEL = 32


class MemoryBudgetError(RuntimeError):
    """A single task exceeds the safe per-run memory allowance."""

    def __init__(self, available: int, required: int):
        self.available = int(available)
        self.required = int(required)
        super().__init__(
            f"Estimated single-task memory {required / GIB:.2f} GiB "
            f"exceeds safe allowance {available / GIB:.2f} GiB."
        )


@dataclass(frozen=True)
class ConcurrencyPlan:
    requested_crop: int
    requested_calc: int
    crop_workers: int
    calc_workers: int
    defer_calculation: bool
    available_bytes: int | None
    budget_bytes: int | None
    source_pixels: int
    crop_pixels: int

    @property
    def adjusted(self) -> bool:
        return (
            self.crop_workers < self.requested_crop
            or self.calc_workers < self.requested_calc
            or self.defer_calculation
        )


def available_memory_bytes() -> int | None:
    """Available physical RAM, without adding mandatory dependencies."""
    if sys.platform == "win32":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        try:
            stat = MemoryStatus()
            stat.dwLength = ctypes.sizeof(stat)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return int(stat.ullAvailPhys)
        except (AttributeError, OSError, ValueError):
            pass
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/meminfo", encoding="ascii") as handle:
                for line in handle:
                    if line.startswith("MemAvailable:"):
                        return int(line.split()[1]) * 1024
        except (OSError, IndexError, ValueError):
            pass
    try:
        return int(os.sysconf("SC_AVPHYS_PAGES")) * int(os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, ValueError, OSError):
        return None


def largest_image_pixels(files: Iterable[Path], *, fallback: int = 24_000_000) -> int:
    """Inspect dimensions in headers without allocating decoded image buffers.

    Ignore corrupt files here: the ordinary crop worker still reports its own
    read failure. Unknown dimensions use a conservative fallback.
    """
    largest = 0
    for path in files:
        try:
            with Image.open(path) as image:
                pixels = image.width * image.height
            largest = max(largest, pixels)
        except (OSError, ValueError, SyntaxError, OverflowError):
            continue
    return largest or fallback


def choose_workers(
    requested_crop: int,
    requested_calc: int,
    *,
    source_pixels: int,
    crop_pixels: int,
    calc_enabled: bool,
    calc_debug: bool = False,
    crop_debug: bool = False,
    available_bytes: int | None = None,
    cpu_count: int | None = None,
) -> ConcurrencyPlan:
    """Limit concurrent image-heavy tasks to a conservative RAM/CPU budget.

    If a crop and calculation cannot safely coexist but each can run alone,
    defer the *first* calculation batch until cropping finishes.
    """
    crop_requested = max(1, int(requested_crop))
    calc_requested = max(1, int(requested_calc)) if calc_enabled else 0
    src = max(1, int(source_pixels))
    dst = max(1, int(crop_pixels))
    if available_bytes is None:
        available_bytes = available_memory_bytes()
    cpu = max(2, min(8, int(cpu_count or os.cpu_count() or 4)))

    if available_bytes is not None and available_bytes <= 0:
        raise MemoryBudgetError(0, 1)
    if available_bytes is None:
        # Avoid promising arbitrary high parallelism without RAM information.
        crop = min(crop_requested, 2)
        calc = min(calc_requested, 1)
        return ConcurrencyPlan(
            crop_requested, calc_requested, crop, calc, False,
            None, None, src, dst,
        )

    available = int(available_bytes)
    # Leave at least half the observed physical RAM free for Windows, the GUI,
    # storage caches, JIT compilation and other processes. Reserve a further
    # 256 MiB for persistent sample/matching state and allocations.
    budget = max(0, available // 2 - 256 * MIB)
    crop_cost = max(256 * MIB, src * CROP_BYTES_PER_PIXEL + 128 * MIB)
    if crop_debug:
        crop_cost += max(64 * MIB, src * 2)
    calc_cost = max(320 * MIB, dst * CALC_BYTES_PER_PIXEL + 128 * MIB)
    if calc_debug:
        calc_cost += max(128 * MIB, dst * 8)

    required = max(crop_cost, calc_cost if calc_enabled else 0)
    if budget < required:
        raise MemoryBudgetError(budget, required)

    if not calc_enabled:
        crop = min(crop_requested, cpu, max(1, budget // crop_cost))
        return ConcurrencyPlan(
            crop_requested, 0, int(crop), 0, False,
            available, budget, src, dst,
        )

    if crop_cost + calc_cost > budget or cpu < 2:
        # Serial stages are safer than waiting with multiple decoded buffers
        # alive while the native calculation subsystem is working.
        crop = min(crop_requested, cpu, max(1, budget // crop_cost))
        calc = min(calc_requested, cpu, max(1, budget // calc_cost))
        return ConcurrencyPlan(
            crop_requested, calc_requested, int(crop), int(calc), True,
            available, budget, src, dst,
        )

    # Reserve one calculation worker first. Prioritize crop throughput for
    # 60-80MP photographs, then allocate the remaining memory to calculations.
    crop_capacity = max(1, (budget - calc_cost) // crop_cost)
    crop = min(crop_requested, cpu - 1, crop_capacity)
    calc_capacity = max(1, (budget - crop * crop_cost) // calc_cost)
    calc = min(calc_requested, cpu - crop, calc_capacity)
    return ConcurrencyPlan(
        crop_requested, calc_requested, int(crop), int(calc), False,
        available, budget, src, dst,
    )
