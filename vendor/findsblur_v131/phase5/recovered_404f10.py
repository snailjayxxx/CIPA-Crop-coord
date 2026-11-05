"""Input-region nonzero-extent scan from FindsBlur V1.2.1 at 0x404F10.

This is a literal scalar recovery of four directional scans and their
secondary margin adjustment. Unlike a guessed region-selection algorithm,
all compare directions come from addresses 0x404F50..0x4050B8 of the EXE.

The original function receives four pointers to mutable bounds, four pointers
to secondary bounds and two margins (13 stack arguments total). It writes the
raw detected bbox through the first four pointers unconditionally, then
returns -1 if the margin-adjusted bbox is invalid. In that error case the
secondary four pointers are not written. This port returns an immutable result
with ``adjusted=None`` for that failure; that is an intentional API adaptation.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Sequence
from recovered_4050d0 import Rect

@dataclass(frozen=True, slots=True)
class NonzeroExtents:
    original: Rect
    detected: Rect
    adjusted: Rect | None
    status: int


def find_nonzero_extents_404f10(
    source: bytes | bytearray, *, stride: int, height: int, roi: Rect,
    x_margin: int, y_margin: int,
) -> NonzeroExtents:
    """Read (nonzero) pixels within inclusive ROI; scan each of 4 directions.

    The input image is a flat byte buffer. For a direction where no nonzero
    pixel is found, the original bound is kept. Margin is applied only when a
    detected bound moved inward relative to the original bound, matching the
    explicit register comparisons at 0x405050..0x40508D.

    Negative margins are legal at machine level; callers pass positive values.
    """
    if stride <= 0 or height <= 0 or len(source) < stride * height:
        raise ValueError('invalid image buffer geometry')
    if not (0 <= roi.x0 <= roi.x1 < stride and 0 <= roi.y0 <= roi.y1 < height):
        raise ValueError('ROI not inside the buffer')

    x0,y0,x1,y1=roi.as_tuple()
    top=y0
    for y in range(y0,y1+1):
        if any(source[y*stride+x] != 0 for x in range(x0,x1+1)):
            top=y
            break

    bottom=y1
    for y in range(y1,y0-1,-1):
        if any(source[y*stride+x] != 0 for x in range(x0,x1+1)):
            bottom=y
            break

    left=x0
    for x in range(x0,x1+1):
        if any(source[y*stride+x] != 0 for y in range(y0,y1+1)):
            left=x
            break

    right=x1
    for x in range(x1,x0-1,-1):
        if any(source[y*stride+x] != 0 for y in range(y0,y1+1)):
            right=x
            break

    detected=Rect(left,top,right,bottom)
    trimmed=Rect(
        left + (x_margin if left != x0 else 0),
        top + (y_margin if top != y0 else 0),
        right - (x_margin if right != x1 else 0),
        bottom - (y_margin if bottom != y1 else 0),
    )
    if trimmed.x0 > trimmed.x1 or trimmed.y0 > trimmed.y1:
        return NonzeroExtents(roi,detected,None,-1)
    return NonzeroExtents(roi,detected,trimmed,0)
