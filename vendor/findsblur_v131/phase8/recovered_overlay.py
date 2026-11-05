"""Literal x86 control-flow translation of FindsBlur V1.2.1 0x402B00.

The function copies neither pixels nor junction labels. It visits an inclusive
rectangle, and sets bit 0x04 in the FIRST byte buffer iff the corresponding
pixel of the SECOND byte buffer is nonzero. The assembly does not check the
fourth positional argument (full image height): validation is a Python-only
safety guard. It modifies its first argument in place if it is a bytearray.

Evidence: 0x402B00..0x402B83, with caller at 0x4079DB..0x4079F4.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Sequence


@dataclass(frozen=True, slots=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int


def overlay_bit_04_402b00(
    target: Sequence[int],
    source: Sequence[int],
    *,
    stride: int,
    height: int,
    roi: Rect,
) -> bytearray:
    """Apply `target[y*stride+x] |= 0x04` where source is nonzero.

    The two buffers and stride correspond to native arguments 1, 2, 3.
    Original argument 4 is unused in 0x402B00. Its ROI is args 5-8, in
    `left, top, right, bottom` inclusive order.
    """
    if stride <= 0 or height <= 0:
        raise ValueError('stride and height must be positive')
    if len(target) != stride * height or len(source) != stride * height:
        raise ValueError('both buffers must match stride * height')
    if not (0 <= roi.left <= roi.right < stride and
            0 <= roi.top <= roi.bottom < height):
        raise ValueError('inclusive ROI is outside the image')
    result = target if isinstance(target, bytearray) else bytearray(target)
    if any(not 0 <= x <= 255 for x in source):
        raise ValueError('source values must be byte values')
    if any(not 0 <= x <= 255 for x in result):
        raise ValueError('target values must be byte values')
    for y in range(roi.top, roi.bottom + 1):
        base = y * stride
        for x in range(roi.left, roi.right + 1):
            index = base + x
            if source[index] != 0:
                result[index] |= 0x04
    return result
