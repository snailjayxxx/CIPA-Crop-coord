"""Partial instruction-led reconstruction of FindsBlur V1.2.1 native image helpers.

ALGORITHM SOURCE: TargetEXE.exe SHA-256
  81c1f1aa25116cdd0ab4f2babae5884649c1479a699d85cb885e32695973eb62

Covered PE virtual addresses: 0x4047A0, 0x4049F0, 0x404A20, 0x404C40,
0x404CB0, 0x405550 and the mode-100 branch of 0x405750.

Scope is *local* byte transformations with explicit, caller-supplied inclusive
ROI, stride, radius and mode. This is NOT a complete JPEG/BMP blur analyzer.
No historical CIPA-Calc code or PDF algorithm is used.

The Win32 routines assume the caller keeps the enlarged filter window inside
allocated memory and, for 4047A0/404A20, uses disjoint source/destination.
This Python port rejects unsafe geometries rather than reproducing an invalid
native memory access.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Sequence


@dataclass(frozen=True)
class Rect:
    """Coordinates inclusive at both ends, matching EXE's jle loop bounds."""
    x0: int
    y0: int
    x1: int
    y1: int

    def empty(self) -> bool:
        return self.x0 > self.x1 or self.y0 > self.y1


def _validate(buffer: Sequence[int], stride: int, height: int, rect: Rect, radius: int = 0) -> None:
    if stride <= 0 or height <= 0 or len(buffer) < stride * height:
        raise ValueError('bad buffer dimensions')
    if radius < 0:
        raise ValueError('negative radius')
    if rect.empty():
        return
    if rect.x0 - radius < 0 or rect.y0 - radius < 0 or rect.x1 + radius >= stride or rect.y1 + radius >= height:
        raise ValueError('ROI or expanded filter window outside buffer')


def _starting_histogram(src: Sequence[int], stride: int, center_x: int, center_y: int, radius: int) -> list[int]:
    """Equivalent to EXE helper 0x404C40, using inclusive rectangle."""
    h = [0] * 256
    for y in range(center_y - radius, center_y + radius + 1):
        k = y * stride
        for x in range(center_x - radius, center_x + radius + 1):
            h[src[k+x]] += 1
    return h


def first_cumulative_gt_4049f0(hist: Sequence[int], cutoff: int) -> int:
    """0x4049F0: lowest bin with cumulative frequency > cutoff; else 0."""
    if len(hist) != 256:
        raise ValueError('256 histogram bins required')
    subtotal = 0
    for i, n in enumerate(hist):
        subtotal += int(n)
        if subtotal > cutoff:
            return i
    return 0


def first_or_last_occupied_404cb0(hist: Sequence[int], mode: int) -> int:
    """0x404CB0: mode=1 => minimum; all other modes => maximum.

    In the all-zero histogram case, EXE initializes the result byte to 0 or
    255 respectively; it retains that fallback if no positive bin is found.
    """
    if len(hist) != 256:
        raise ValueError('256 histogram bins required')
    if mode == 1:
        for i in range(256):
            if hist[i] != 0:
                return i
        return 0
    for i in range(255, -1, -1):
        if hist[i] != 0:
            return i
    return 255


def _slide_right(h: list[int], src: Sequence[int], stride: int, old_x: int, y: int, radius: int) -> None:
    """0x40493A/0x404B88: remove old left column, add new right."""
    drop_x = old_x - radius
    add_x = old_x + radius + 1
    for row in range(y - radius, y + radius + 1):
        offset = row * stride
        h[src[offset+drop_x]] -= 1
        h[src[offset+add_x]] += 1


def sliding_median_4047a0(
    source: bytes | bytearray, *, stride: int, height: int, roi: Rect,
    radius: int, destination: bytearray | None = None,
) -> bytearray:
    """Recover 0x4047A0, only for valid (non-overflowing) native call geometry.

    Output is first filled with 0xFF over stride*height. Each ROI pixel uses
    an inclusive square of side 2*radius+1; selection uses helper 0x4049F0
    with cutoff _ftol(window_area * 0.5), i.e. the upper middle index if the
    population were even. The native neighborhood is always odd in valid runs.

    EXE updates a 256-bin window histogram as x moves right, rather than
    calling a standard medianBlur library; this port preserves that behavior.
    """
    _validate(source, stride, height, roi, radius)
    if destination is None:
        destination = bytearray(stride*height)
    _validate(destination, stride, height, roi)
    if source is destination:
        raise ValueError('EXE 4047A0 expects disjoint source and destination')
    destination[:stride*height] = b'\xff' * (stride*height)
    if roi.empty():
        return destination
    cutoff = floor(((2*radius+1)**2) * .5)  # 0x404811, 0x404817, 0x428500
    for y in range(roi.y0, roi.y1 + 1):
        hist = _starting_histogram(source, stride, roi.x0, y, radius)
        for x in range(roi.x0, roi.x1+1):
            destination[y*stride+x] = first_cumulative_gt_4049f0(hist, cutoff)
            if x < roi.x1:
                _slide_right(hist, source, stride, x, y, radius)
    return destination


def sliding_extremum_404a20(
    source: bytes | bytearray, *, stride: int, height: int, roi: Rect,
    radius: int, mode: int, destination: bytearray | None = None,
) -> bytearray:
    """Recover 0x404A20 (mode 1=min, any other mode=max).

    This is the histogram-driven implementation, not a guessed SciPy border
    mode. Outside the supplied valid ROI, every output byte is 0xFF.
    """
    _validate(source, stride, height, roi, radius)
    if destination is None:
        destination = bytearray(stride*height)
    _validate(destination, stride, height, roi)
    if source is destination:
        raise ValueError('EXE 404A20 expects disjoint source and destination')
    destination[:stride*height] = b'\xff' * (stride*height)
    if roi.empty():
        return destination
    for y in range(roi.y0, roi.y1+1):
        hist = _starting_histogram(source, stride, roi.x0, y, radius)
        for x in range(roi.x0, roi.x1+1):
            destination[y*stride+x] = first_or_last_occupied_404cb0(hist, mode)
            if x < roi.x1:
                _slide_right(hist, source, stride, x, y, radius)
    return destination


def combine_pair_405550(
    first: bytes | bytearray, second: bytes | bytearray, *,
    stride: int, height: int, roi: Rect, mode: int,
    destination: bytearray | None = None,
) -> bytearray:
    """Recover active mode branches of 0x405550.

    0: abs(first - second), mode 1: clip(round(first*second/255)).
    For a disjoint destination, the native routine initializes outside ROI to
    0 for mode 0 and 0xFF for mode 1. For aliasing destination, the original
    skips the fill. The computed output is local per pixel so aliasing is safe.
    Values are uint8, hence product/255 cannot have an exact half tie; the
    integer expression (a*b+127)//255 agrees with the x87 half-up instruction.
    """
    _validate(first, stride, height, roi)
    _validate(second, stride, height, roi)
    if destination is None:
        destination = bytearray(stride*height)
    _validate(destination, stride, height, roi)
    # For mode != 0/1, EXE still executes the disjoint-buffer fill (0x00),
    # and then returns without touching the ROI in the two mode branches.
    if destination is not first and destination is not second:
        destination[:stride*height] = (b'\xff' if mode==1 else b'\x00')*(stride*height)
    if mode not in (0,1):
        return destination
    if roi.empty():
        return destination
    for y in range(roi.y0, roi.y1+1):
        row=y*stride
        for x in range(roi.x0, roi.x1+1):
            i=row+x
            a,b=int(first[i]), int(second[i])
            destination[i] = abs(a-b) if mode==0 else min(255, (a*b + 127)//255)
    return destination


def threshold_mode_100_405750(
    source: bytes | bytearray, *, stride: int, height: int,
    roi: Rect, raw_threshold: int, destination: bytearray | None = None,
) -> bytearray:
    """Recover the mode=100 ('0x64') branch of 0x405750.

    0x40592B-0x405952 select a caller-supplied integer threshold clamped to
    [0,255]. 0x4059BC `cmp threshold, source_byte`; `sbb dl,dl` yields 0xFF
    exactly if source_byte > threshold, otherwise 0x00. The EXE computes a
    256-bin histogram and some moments regardless of mode, but mode 100 never
    uses those moments to choose its output threshold. This port skips that
    dead calculation *only for mode 100*, not for other modes.
    """
    _validate(source, stride, height, roi)
    if destination is None:
        destination = bytearray(stride*height)
    _validate(destination, stride, height, roi)
    if destination is not source:
        destination[:stride*height] = b'\xff' * (stride*height)
    t=max(0,min(255,int(raw_threshold)))
    if roi.empty():
        return destination
    for y in range(roi.y0,roi.y1+1):
        row=y*stride
        for x in range(roi.x0,roi.x1+1):
            i=row+x
            destination[i]=0xff if source[i]>t else 0
    return destination
