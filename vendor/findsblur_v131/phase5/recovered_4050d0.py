"""Instruction-led translation of FindsBlur.exe 1.2.1 function 0x004050D0.

Only algorithm source: the original Windows PE binary whose SHA-256 is
81c1f1aa25116cdd0ab4f2babae5884649c1479a699d85cb885e32695973eb62.

This code is a LOCAL transform of an existing 8-bit image mask. It is NOT an
image classifier, a complete FindsBlur engine, or a drop-in morphology API.

x86 parameters reconstructed from the stack at 0x4050D0:
    (source, destination, stride_bytes, height_rows,
     x0, y0, x1, y1, propagation_limit, mode)

The ROI is inclusive. Only the interior ROI pixels take part as *centers* of
8-neighbor propagation; the ROI boundary can be written by those centers.
There is an unconditional full-buffer copy, followed by in-place label updates
and a mode-specific canonicalization of the inclusive ROI.

For precision/debuggability this implementation uses direct bytearray indexing
and preserves row-major iteration and neighbor ordering. We explicitly reject
invalid geometries rather than reproduce unsafe native memory accesses.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True, slots=True)
class Rect:
    x0: int
    y0: int
    x1: int
    y1: int

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.x0, self.y0, self.x1, self.y1)


@dataclass(slots=True)
class Trace:
    """Per-call measurements; not an additional algorithmic criterion."""
    mode: int
    requested_iterations: int
    propagation_writes: list[int] = field(default_factory=list)
    thinning_writes: list[tuple[int, int]] = field(default_factory=list)
    completed_propagation_layers: int = 0


# 0x40519C..0x4051D3: 8 pointers in the original array order.
# The order matters: updates are immediate and may affect later reads.
NEIGHBORS = ((-1, -1), (-1, 0), (-1, 1), (0, -1),
             (0, 1), (1, -1), (1, 0), (1, 1))


def _validate(src: Sequence[int], stride: int, height: int, roi: Rect,
              dest: bytearray | None) -> None:
    if stride <= 0 or height <= 0:
        raise ValueError('nonpositive stride/height')
    if not (0 <= roi.x0 <= roi.x1 < stride and 0 <= roi.y0 <= roi.y1 < height):
        raise ValueError('inclusive ROI outside the buffer')
    n = stride * height
    if len(src) < n or (dest is not None and len(dest) < n):
        raise ValueError('source/destination shorter than stride*height')


def transform_4050d0(
    source: bytes | bytearray, *, stride: int, height: int, roi: Rect,
    propagation_limit: int, mode: int, destination: bytearray | None = None,
    trace: Trace | None = None,
) -> bytearray:
    """Translate function 0x4050D0 for safe, complete uint8 image buffers.

    mode == 0 uses an 0xff-seeded expanding propagation; mode != 0 uses a
    0x00-seeded propagation, then an ordered topology-sensitive deletion pass.
    Those names describe observed machine behavior, not inferred CIPA intent.

    A zero propagation_limit STILL executes one propagation sweep in the EXE.
    Valid real callers supply positive limits. Negative limits are not rejected
    since the binary performs its first sweep before testing against the limit.
    """
    _validate(source, stride, height, roi, destination)
    size = stride * height
    result = bytearray(source[:size]) if destination is None else destination
    if destination is not None:
        # 4050EE..405103: forwards byte copy; src==dest is permitted.
        result[:size] = source[:size]

    interior_x = range(roi.x0 + 1, roi.x1)
    interior_y = range(roi.y0 + 1, roi.y1)
    neighbor_offsets = tuple(dy * stride + dx for dy, dx in NEIGHBORS)
    is_mode_one = mode != 0
    match_center = 0 if is_mode_one else 255
    match_neighbor = 255 if is_mode_one else 0
    new_label = 1 if is_mode_one else 254
    step = 1 if is_mode_one else -1

    if trace is not None:
        trace.mode = mode
        trace.requested_iterations = propagation_limit
        trace.propagation_writes.clear()
        trace.thinning_writes.clear()
        trace.completed_propagation_layers = 0

    # 405183..405303: the instruction runs a synchronous *layer* number,
    # but its writes inside the current sweep are immediate, not buffered.
    # Centers match exactly one current byte label, and only neighbors with
    # the opposite extreme value are relabeled. This distinction matters.
    completed = 0
    while True:
        wrote = 0
        for y in interior_y:
            row = y * stride
            for x in interior_x:
                center = row + x
                if result[center] != match_center:
                    continue
                for offset in neighbor_offsets:
                    neighbor = center + offset
                    if result[neighbor] == match_neighbor:
                        result[neighbor] = new_label
                        wrote += 1
        completed += 1
        if trace is not None:
            trace.propagation_writes.append(wrote)
        # 4052A6..405303: after increment, stop at requested limit; on
        # an earlier empty sweep, subtract the empty sweep from completed.
        if completed >= propagation_limit:
            if wrote == 0:
                completed -= 1
            break
        if wrote == 0:
            completed -= 1
            break
        match_center = new_label
        candidate = new_label + step
        if is_mode_one:
            new_label = candidate if candidate <= 254 else 1
            if candidate > 254:
                match_center = 254
        else:
            new_label = candidate if candidate >= 1 else 254
            if candidate < 1:
                match_center = 1

    if trace is not None:
        trace.completed_propagation_layers = completed

    # 405308..4054AB: unlike mode 0, mode 1 performs topological deletion
    # of CURRENT-layer pixels. The four terms below are a literal translation
    # of imul/sub/add registers at 0x4053E2..0x40542C. Note that neighbor
    # occupancy is '!=0', not '==255'. Each deletion is immediate.
    if is_mode_one:
        for layer in range(1, completed + 1):
            for sweep in range(1, 11):  # 405370..40548B: max 10 sweeps
                erased = 0
                for y in interior_y:
                    row = y * stride
                    for x in interior_x:
                        i = row + x
                        if result[i] != layer:
                            continue
                        nw = int(result[i - stride - 1] != 0)
                        n  = int(result[i - stride    ] != 0)
                        ne = int(result[i - stride + 1] != 0)
                        w  = int(result[i          - 1] != 0)
                        e  = int(result[i          + 1] != 0)
                        sw = int(result[i + stride - 1] != 0)
                        s  = int(result[i + stride    ] != 0)
                        se = int(result[i + stride + 1] != 0)
                        # 4053E2..40542A. Do not replace with a generic
                        # thinning library: it need not follow this order.
                        count = (s * (1 - se * e)
                                 + w * (1 - sw * s)
                                 + n * (1 - nw * w)
                                 + e * (1 - ne * n))
                        if count == 1:
                            result[i] = 0
                            erased += 1
                if trace is not None:
                    trace.thinning_writes.append((layer, erased))
                if erased == 0:
                    break
        # 4054AB..4054DD: canonicalize nonzero labels in the INNER ROI.
        for y in interior_y:
            row = y * stride
            for x in interior_x:
                i = row + x
                if result[i] != 0:
                    result[i] = 255

    # 4054E2..40553F and mode-0 branch 405547..40554C:
    # Canonicalize the INCLUSIVE ROI, without altering buffer outside it.
    # mode 0: any nonzero -> ff, zero stays zero.
    # mode 1: exact ff stays ff, anything else -> zero.
    for y in range(roi.y0, roi.y1 + 1):
        row = y * stride
        for x in range(roi.x0, roi.x1 + 1):
            i = row + x
            if is_mode_one:
                if result[i] != 255:
                    result[i] = 0
            elif result[i] != 0:
                result[i] = 255
    return result
