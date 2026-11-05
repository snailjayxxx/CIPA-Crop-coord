"""Isolated verified blocks of FindsBlur V1.2.1's 0x401000 region function.

This is NOT a translation of 0x401000 in its entirety. It reconstructs only:
 - the component spanning gate 0x401A29..0x401B09;
 - the component projection to the output 0x401B09..0x401B7D;
 - the final clearing of marker 0x80 0x401B8B..0x401BE2.

The caller to 0x401000 provides source/primary mask, output A, workspace B,
stride, height, outer ROI and inner ROI (13 arguments in total). Here we
operate on buffers A and B *after* the rest of 0x401000 has built the current
component in workspace B as 0xFF. We never fabricate how that component was
constructed; see `README.md` for the unresolved upstream propagation.
"""
from __future__ import annotations
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int


@dataclass(frozen=True, slots=True)
class GateResult:
    marker: int
    touches_top: bool
    touches_bottom: bool
    touches_left: bool
    touches_right: bool
    written_pixels: int

    @property
    def spans_two_sides(self) -> bool:
        return self.marker == 0xFF


def _check(buffer: Sequence[int], stride: int, height: int, rect: Rect) -> None:
    if stride <= 0 or height <= 0 or len(buffer) != stride * height:
        raise ValueError('invalid flat byte buffer dimensions')
    if not (0 <= rect.left <= rect.right < stride and
            0 <= rect.top <= rect.bottom < height):
        raise ValueError('inclusive ROI outside image')


def commit_component_401a29(
    output_a: bytearray,
    workspace_b: Sequence[int],
    *,
    stride: int,
    height: int,
    outer: Rect,
    inner: Rect,
) -> GateResult:
    """Classify one FF-marked workspace component and mark it in output A.

    Section 0x401A29..0x401B09 tests workspace B == FF along top/bottom rows
    (within the inner x-span), and left/right columns (inner y-span). The
    component is accepted if it hits BOTH opposite sides on EITHER axis.
    Otherwise it's marked 80 in output A for eventual deletion.
    Section 0x401B49..0x401B59 writes the marker for each FF pixel in the
    OUTER ROI. Existing non-FF workspace pixels leave output A unchanged.
    """
    _check(output_a, stride, height, outer)
    _check(workspace_b, stride, height, inner)
    if output_a is workspace_b:
        raise ValueError('native caller uses separate A and B buffers')
    touches_top = any(workspace_b[inner.top * stride + x] == 0xFF
                      for x in range(inner.left, inner.right + 1))
    touches_bottom = any(workspace_b[inner.bottom * stride + x] == 0xFF
                         for x in range(inner.left, inner.right + 1))
    touches_left = any(workspace_b[y * stride + inner.left] == 0xFF
                       for y in range(inner.top, inner.bottom + 1))
    touches_right = any(workspace_b[y * stride + inner.right] == 0xFF
                        for y in range(inner.top, inner.bottom + 1))
    marker = 0xFF if ((touches_top and touches_bottom) or
                      (touches_left and touches_right)) else 0x80
    written = 0
    for y in range(outer.top, outer.bottom + 1):
        base = y * stride
        for x in range(outer.left, outer.right + 1):
            i = base + x
            if workspace_b[i] == 0xFF:
                output_a[i] = marker
                written += 1
    return GateResult(marker, touches_top, touches_bottom,
                      touches_left, touches_right, written)


def clear_rejected_80_401b8b(
    output_a: bytearray, *, stride: int, height: int, outer: Rect,
) -> int:
    """At 0x401B8B..0x401BE2, change only 0x80 to 0x00 in outer ROI.

    The native caller reaches this after processing component candidates; it
    must NOT be run between component classifications by default.
    """
    _check(output_a, stride, height, outer)
    changed = 0
    for y in range(outer.top, outer.bottom + 1):
        base = y * stride
        for x in range(outer.left, outer.right + 1):
            i = base + x
            if output_a[i] == 0x80:
                output_a[i] = 0
                changed += 1
    return changed
