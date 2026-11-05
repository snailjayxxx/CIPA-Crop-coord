"""Replay confirmed native call order 4078CB to 4079EF on a supplied mask.

No JPEG/BMP decode or image segmentation: the primary *byte mask* and three
ROI rectangles must already be supplied by the still-unconnected caller.

4078CB  -> 401000(source C4, output C0, workspace BC)
4078F6  -> copy result C0 back over original source C4, byte by byte
407990  -> thin C0 via 402430
4079BC  -> mark junctions in C0 via 402910
4079EF  -> OR bit04 into C4 where C0 is nonzero via 402B00
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import sys

ROOT=str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:sys.path.insert(0,ROOT)
from phase9.recovered_401000 import Rect, RegionTrace, process_region_401000
from phase8.replay_confirmed_407990_4079ef import replay_verified_tail


@dataclass(frozen=True, slots=True)
class StageChainResult:
    region: RegionTrace
    mask_after_region: bytes
    junction_mask: bytes
    final_primary_mask: bytes
    thinning_cycles: int


def replay_4078cb_to_4079ef(primary_mask: bytes | bytearray, *,
                              stride: int, height: int,
                              outer: Rect, inner: Rect, thin_roi: Rect) -> StageChainResult:
    # Buffer relationships at native member offsets +8C4, +8C0 and +8BC.
    c4 = bytearray(primary_mask)
    c0 = bytearray(stride * height)
    bc = bytearray(stride * height)
    region = process_region_401000(c4, c0, bc, stride=stride, height=height,
                                   outer=outer,inner=inner)
    c4[:] = c0[:]  # 4078E2..407905: explicit byte-by-byte copy
    snapshot = bytes(c0)
    tail = replay_verified_tail(c0, c4, stride=stride,height=height,roi=thin_roi)
    return StageChainResult(region,snapshot,bytes(tail.source_01_03),
                            bytes(tail.target_with_04),tail.thinning_cycles)
