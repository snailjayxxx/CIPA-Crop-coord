"""Direct instruction-derived translation of FindsBlur V1.2.1 x86 functions.

0x402430: four-phase, three-template sequential thinning.
0x402910: nonzero pixel classification (0x01 / 0x03).

This is a *local* translation, not a complete engine nor native dynamic parity proof.
Input to both operations is the flattened, byte-per-pixel internal mask.
The original expects a safe interior inclusive ROI; wrapper rejects coordinates
which would make a 3x3 neighborhood access fall outside the image.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class Rect:
    x0: int
    y0: int
    x1: int
    y1: int


# The pointer array at 0x402747 follows this order, as derived from stack
# initializers 0x402436..0x402721. 0 NW, 1 N, 2 NE, 3 W, 4 E,
# 5 SW, 6 S, 7 SE.
NEIGHBORS = ((-1, -1), (0, -1), (1, -1), (-1, 0),
             (1, 0), (-1, 1), (0, 1), (1, 1))

# (must_be_zero_triplet, must_be_nonzero_triplet), three templates per pass.
# These integer indices were obtained by interpreting the actual initializer
# byte code: 0x40250F..0x402721. No profile or historical guesses are used.
THIN_TEMPLATES = (
    (((0, 1, 2), (7, 5, 6)),
     ((0, 1, 3), (7, 4, 6)),
     ((0, 3, 5), (7, 2, 4))),
    (((7, 5, 6), (0, 1, 2)),
     ((7, 4, 6), (0, 1, 3)),
     ((7, 2, 4), (0, 3, 5))),
    (((2, 4, 7), (5, 0, 3)),
     ((2, 1, 4), (5, 3, 6)),
     ((2, 0, 1), (5, 6, 7))),
    (((5, 0, 3), (2, 4, 7)),
     ((5, 3, 6), (2, 1, 4)),
     ((5, 6, 7), (2, 0, 1))),
)

# Exact pass order, confirmed by [esp + edi + 0x34], 0x24 and 0x44:
# TL→right/down, BR→left/up, TR→left/down, BL→right/up.
PASS_ORDERS = ((True, True), (False, False), (True, False), (False, True))

# Extracted from 0x4029F9..0x402A38, 0x402A4C..0x402AA7.
# Component term = enabled(cardinal) and not(enabled(diagonal) and enabled(adjacent cardinal)).
FORK_TRIPLES = ((4, 2, 1), (1, 0, 3), (3, 5, 6), (6, 7, 4))
CORNER_TRIPLES = ((0, 1, 3), (1, 2, 4), (3, 5, 6), (6, 7, 4))


def _buffer(mask: Sequence[int], *, stride: int, height: int, roi: Rect) -> bytearray:
    if stride < 3 or height < 3 or len(mask) != stride * height:
        raise ValueError('expected flat byte buffer with valid dimensions')
    if not (1 <= roi.x0 <= roi.x1 < stride - 1 and
            1 <= roi.y0 <= roi.y1 < height - 1):
        raise ValueError('ROI must be inclusive and have one pixel of border')
    if any(not 0 <= v <= 255 for v in mask):
        raise ValueError('byte pixel values must be in 0..255')
    return mask if isinstance(mask, bytearray) else bytearray(mask)


def _offsets(stride: int) -> tuple[int, ...]:
    return tuple(dx + stride * dy for dx, dy in NEIGHBORS)


def thin_402430(mask: bytes | bytearray, *, stride: int, height: int,
                roi: Rect, max_cycles: int | None = None) -> tuple[bytearray, int]:
    """Replicate the 0x402430 sequential four-pass template deletion.

    On each pass a matched pixel is changed to 1 immediately, so it remains
    nonzero while scanning other pixels; the pass's final full-ROI sweep
    deletes all 1 values. This intentional sequence is not equivalent to a
    parallel thinning kernel. Iteration ends on a full four-pass cycle with
    no deletions. ``max_cycles`` is a Python-only test safeguard, not a
    native threshold; the assembly does not set a cycle cap here.
    """
    result = _buffer(mask, stride=stride, height=height, roi=roi)
    if any(v not in (0, 255) for v in result):
        raise ValueError('thinning native caller supplies a 0/255 mask')
    offsets = _offsets(stride)
    cycles = 0
    while True:
        cycles += 1
        changed = False
        for phase, ((y_forward, x_forward), templates) in enumerate(zip(PASS_ORDERS, THIN_TEMPLATES)):
            yrange = range(roi.y0, roi.y1 + 1) if y_forward else range(roi.y1, roi.y0 - 1, -1)
            xrange = range(roi.x0, roi.x1 + 1) if x_forward else range(roi.x1, roi.x0 - 1, -1)
            for y in yrange:
                for x in xrange:
                    idx = y * stride + x
                    if result[idx] == 0:
                        continue
                    for zeros, ones in templates:
                        if (not any(result[idx + offsets[k]] for k in zeros)
                            and all(result[idx + offsets[k]] for k in ones)):
                            result[idx] = 1
                            break
            # x86 0x4028B3..0x4028DA clears ==1 in the inclusive ROI;
            # scan always advances forward regardless of pass direction.
            for y in range(roi.y0, roi.y1 + 1):
                for x in range(roi.x0, roi.x1 + 1):
                    idx = y * stride + x
                    if result[idx] == 1:
                        result[idx] = 0
                        changed = True
        if not changed:
            return result, cycles
        if max_cycles is not None and cycles >= max_cycles:
            raise RuntimeError('Python test-only thinning cycle limit reached')


def mark_junctions_402910(mask: bytes | bytearray, *, stride: int,
                           height: int, roi: Rect) -> bytearray:
    """0x402910 in-place classifies nonzero centers as 0x01 or 0x03.

    It does NOT directly output a coordinate list. It reads neighbors as
    nonzero (including 1/3), computes four cardinal/diagonal topology
    contributions, then checks four fully-occupied corner triples. These
    exact tests follow 0x4029F9..0x402AA7. Background remains untouched.
    """
    result = _buffer(mask, stride=stride, height=height, roi=roi)
    offsets = _offsets(stride)
    for y in range(roi.y0, roi.y1 + 1):
        for x in range(roi.x0, roi.x1 + 1):
            idx = y * stride + x
            if result[idx] == 0:
                continue
            active = tuple(bool(result[idx + off]) for off in offsets)
            score = sum(active[a] and not (active[b] and active[c])
                        for a, b, c in FORK_TRIPLES)
            corners = any(all(active[j] for j in triple) for triple in CORNER_TRIPLES)
            result[idx] = 3 if (score >= 3 or corners) else 1
    return result
