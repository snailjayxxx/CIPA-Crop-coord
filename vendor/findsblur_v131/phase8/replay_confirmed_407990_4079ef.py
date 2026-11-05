"""Replay the verified 0x407990/0x4079BC/0x4079EF stage call sequence.

This function deliberately begins AFTER the output of unresolved 0x401000
has been copied back into the source mask. It does not read JPEG and is not a
complete FindsBlur calculator. Arguments are independent native-style byte
buffers, not objects from the prior speculative CIPA-Calc implementation.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from phase7.recovered_topology import Rect as TopologyRect
from phase7.recovered_topology import thin_402430, mark_junctions_402910
from phase8.recovered_overlay import Rect, overlay_bit_04_402b00


@dataclass
class Replayed:
    source_01_03: bytearray
    target_with_04: bytearray
    thinning_cycles: int


def replay_verified_tail(
    working_binary: bytes | bytearray,
    primary_flags: bytes | bytearray,
    *, stride: int,
    height: int,
    roi: Rect,
) -> Replayed:
    """Thin, label nonzero pixels 01/03, then OR 04 into primary mask."""
    roi7 = TopologyRect(roi.left, roi.top, roi.right, roi.bottom)
    thinned, cycles = thin_402430(
        working_binary, stride=stride, height=height, roi=roi7)
    marked = mark_junctions_402910(
        thinned, stride=stride, height=height, roi=roi7)
    projected = overlay_bit_04_402b00(
        primary_flags, marked, stride=stride, height=height, roi=roi)
    return Replayed(marked, projected, cycles)
