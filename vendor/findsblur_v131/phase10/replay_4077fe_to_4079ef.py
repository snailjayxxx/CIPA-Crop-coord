"""EXE call-site-driven 404F10 -> 401000 -> 402430 -> 402910 -> 402B00.

Only starts with the ALREADY-SEGMENTED one-byte-per-pixel native primary
mask. Do not supply decoded JPEG pixels here: upstream preprocessing is not
connected, and a full FindsBlur result is NOT produced by this module.

Call arguments / conditional control flow are sourced from 4077FE..4079EF
of the original executable and checked by trace_native_caller.py.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
for directory in (BASE, BASE / 'phase5'):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from recovered_404f10 import NonzeroExtents, find_nonzero_extents_404f10  # noqa: E402
from recovered_4050d0 import Rect as ExtentRect  # noqa: E402
from phase9.replay_4078cb_to_4079ef import (  # noqa: E402
    StageChainResult, replay_4078cb_to_4079ef,
)
from phase9.recovered_401000 import Rect  # noqa: E402


@dataclass(frozen=True, slots=True)
class CallerChainResult:
    native_status: int
    extents: NonzeroExtents
    tail_roi: Rect | None
    downstream: StageChainResult | None
    original_mask_unchanged: bool


def replay_4077fe_to_4079ef(primary_mask: bytes | bytearray, *,
                              stride: int, height: int, initial_roi: Rect,
                              x_margin: int, y_margin: int) -> CallerChainResult:
    """Reconstruct the caller's extents, ROI passing and buffer handoff.

    407869: 404F10(source C4, stride, height,
       &det.left,&det.top,&det.right,&det.bottom,
       &adjusted.left,&adjusted.top,&adjusted.right,&adjusted.bottom,
       y_margin_field_86c,x_margin_field_870)

    4078CB: 401000(C4,C0,BC,stride,height, detected rect, adjusted rect)
    4078F6: C4[:] = C0[:] for EXACTLY stride*height bytes
    40790B-40797B: the caller increments INITIAL roi left/top and decrements
                    INITIAL roi right/bottom (NOT detected/adjusted bounds)
    407990-4079EF: thin -> junction -> OR 04.

    The phase9 wrapper copies the input and explicitly allocates C0/BC
    scratch buffers, so external input remains unchanged.
    """
    before=bytes(primary_mask)
    if len(before) != stride*height:
        raise ValueError('primary mask must be exactly stride*height bytes')
    ext=find_nonzero_extents_404f10(
        before,stride=stride,height=height,
        roi=ExtentRect(initial_roi.left,initial_roi.top,initial_roi.right,initial_roi.bottom),
        x_margin=x_margin,y_margin=y_margin,
    )
    if ext.status != 0:
        # 407871..407873 jumps to failure branch on any nonzero return value.
        return CallerChainResult(ext.status,ext,None,None,before==bytes(primary_mask))
    assert ext.adjusted is not None
    tail_roi=Rect(initial_roi.left+1,initial_roi.top+1,
                  initial_roi.right-1,initial_roi.bottom-1)
    if tail_roi.left>tail_roi.right or tail_roi.top>tail_roi.bottom:
        raise ValueError('original ROI too small for post-region native bounds')
    det=ext.detected
    adj=ext.adjusted
    downstream = replay_4078cb_to_4079ef(
        before,stride=stride,height=height,
        outer=Rect(det.x0,det.y0,det.x1,det.y1),
        inner=Rect(adj.x0,adj.y0,adj.x1,adj.y1),thin_roi=tail_roi,
    )
    return CallerChainResult(0,ext,tail_roi,downstream,
                             bytes(primary_mask)==before)
