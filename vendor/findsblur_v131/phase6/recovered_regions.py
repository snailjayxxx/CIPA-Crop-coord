"""Local instruction-led reconstruction of FindsBlur V1.2.1 PE functions.

0x401BF0:  boundary-seeded, 8-connected nonzero region propagation.
0x401EF0:  boundary-connected background rejection, enclosed component scan,
           size-gated source fill, plus an auxiliary destination mask.

The original is an x86 PE with flat byte image buffers, inclusive ROI and
10,000-cycle safety caps. Caller arguments are mapped in `README.md`.
These are NOT verified against an executing native EXE, and NOT a full CIPA
measurement engine. Safety checks here reject invalid geometries rather
than attempting the native program's undefined memory accesses.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence

MAX_NATIVE_CYCLES = 10000  # cmp xx,0x2710 at 401ED0, 40212C, 40225B, 4023E8


@dataclass(frozen=True, slots=True)
class Rect:
    x0: int
    y0: int
    x1: int
    y1: int


@dataclass(frozen=True, slots=True)
class Component:
    bounds: Rect
    span_x: int  # max X - min X, NOT inclusive pixel count
    span_y: int  # max Y - min Y
    source_filled: bool
    pixels: int
    propagation_sweeps: int


@dataclass(frozen=True, slots=True)
class HoleProcessResult:
    source: bytearray
    auxiliary: bytearray
    components: tuple[Component, ...]
    outer_sweeps: int


def _check(source: Sequence[int], stride: int, height: int, roi: Rect,
           auxiliary: bytearray | None = None) -> int:
    if stride <= 0 or height <= 0:
        raise ValueError('invalid buffer dimensions')
    if not (0 <= roi.x0 <= roi.x1 < stride and 0 <= roi.y0 <= roi.y1 < height):
        raise ValueError('inclusive ROI outside image')
    size = stride * height
    if len(source) != size or (auxiliary is not None and len(auxiliary) != size):
        raise ValueError('byte buffer size must match stride * height')
    if source is auxiliary:
        raise ValueError('source and destination must not alias (native callers separate them)')
    return size


def _border_indices(roi: Rect, stride: int):
    # 401C79..401D2B / 401F84..40203C; corners can be visited twice.
    for x in range(roi.x0, roi.x1 + 1):
        yield roi.y0 * stride + x
    for x in range(roi.x0, roi.x1 + 1):
        yield roi.y1 * stride + x
    for y in range(roi.y0, roi.y1 + 1):
        yield y * stride + roi.x0
    for y in range(roi.y0, roi.y1 + 1):
        yield y * stride + roi.x1


def _flood_two_sweeps(destination: bytearray, stride: int, roi: Rect,
                      *, target: int, permitted_source: Sequence[int],
                      forbidden_source_value: int) -> int:
    """Instruction order: forward NW/N/NE/W, then reverse E/SW/S/SE.

    Used by 401BF0 (target=0xff, source != 0). The 401EF0 function
    instead uses a SINGLE forward scan testing all 8 neighbors.
    """
    forward = (-stride-1, -stride, -stride+1, -1)
    backward = (1, stride-1, stride, stride+1)
    sweeps = 0
    for _ in range(MAX_NATIVE_CYCLES):
        writes = 0
        for y in range(roi.y0+1, roi.y1):
            for x in range(roi.x0+1, roi.x1):
                i = y*stride+x
                if destination[i] != 0:
                    continue
                if permitted_source[i] == forbidden_source_value:
                    continue
                if any(destination[i+d] == target for d in forward):
                    destination[i] = target
                    writes += 1
        for y in range(roi.y1-1, roi.y0, -1):
            for x in range(roi.x1-1, roi.x0, -1):
                i = y*stride+x
                if destination[i] != 0:
                    continue
                if permitted_source[i] == forbidden_source_value:
                    continue
                if any(destination[i+d] == target for d in backward):
                    destination[i] = target
                    writes += 1
        sweeps += 1
        if writes == 0:
            break
    return sweeps


def retain_border_connected_401bf0(source: bytes | bytearray, *, stride: int,
                                    height: int, roi: Rect,
                                    destination: bytearray | None = None) -> bytearray:
    """0x401BF0: zero the ENTIRE destination, seed ROI nonzero boundary to ff,
    and propagate into source-nonzero 8-neighbors within ROI.

    Native calling convention passes an unused third pointer argument between
    destination and stride. This Python wrapper intentionally omits it.
    The input source is not modified.
    """
    size = _check(source, stride, height, roi, destination)
    dest = destination if destination is not None else bytearray(size)
    dest[:] = b'\x00' * size
    for i in _border_indices(roi, stride):
        if source[i] != 0:
            dest[i] = 255
    _flood_two_sweeps(dest, stride, roi, target=255, permitted_source=source,
                      forbidden_source_value=0)
    return dest


def _flood_one_sweep_8(mask: bytearray, stride: int, roi: Rect,
                       *, forbidden: Sequence[int] | None = None,
                       interior_only: bool = False) -> int:
    """One forward row-major scan per cycle, testing all eight neighbors.

    4020B5..40213A: used after initial outside-zero border seeding,
    requiring source pixel != 0xff. The 4021E5..402263 component phase uses
    the same 8-neighbor condition but only checks auxiliary == 0.
    """
    offsets = (-stride-1, -stride, -stride+1, -1,
               1, stride-1, stride, stride+1)
    sweeps = 0
    ys = range(roi.y0+1, roi.y1) if interior_only else range(roi.y0,roi.y1+1)
    xs = range(roi.x0+1, roi.x1) if interior_only else range(roi.x0,roi.x1+1)
    for _ in range(MAX_NATIVE_CYCLES):
        writes = 0
        for y in ys:
            for x in xs:
                i = y*stride+x
                if mask[i] != 0:
                    continue
                if forbidden is not None and forbidden[i] == 255:
                    continue
                if any(0 <= i+d < len(mask) and mask[i+d] == 1 for d in offsets):
                    mask[i] = 1
                    writes += 1
        sweeps += 1
        if writes == 0:
            break
    return sweeps


def _mark_one_zero_component(mask: bytearray, stride: int, roi: Rect,
                             seed: int) -> int:
    """4021E0..402263: label a new enclosed zero component as 1."""
    mask[seed] = 1
    return _flood_one_sweep_8(mask, stride, roi)


def _one_component_bounds(mask: Sequence[int], stride: int,
                          roi: Rect) -> tuple[Rect, int]:
    """402263..40236C: scan label == 1 from TOP/BOTTOM/LEFT/RIGHT.

    The original search short-circuits at the first hit in each direction;
    dimensions are checked as coordinate span (max-min), not count.
    """
    coords = [(x,y) for y in range(roi.y0, roi.y1+1)
              for x in range(roi.x0, roi.x1+1) if mask[y*stride+x] == 1]
    if not coords:
        raise AssertionError('component cannot be empty immediately after seeding')
    left=min(x for x,_ in coords); right=max(x for x,_ in coords)
    top=min(y for _,y in coords); bottom=max(y for _,y in coords)
    return Rect(left,top,right,bottom), len(coords)


def process_enclosed_zeros_401ef0(source: bytes | bytearray, *, stride: int,
                                   height: int, roi: Rect, size_threshold: int,
                                   destination: bytearray | None = None) -> HoleProcessResult:
    """0x401EF0: source + auxiliary outputs, both mutated in the native API.

    Seed *zero source* boundary pixels, propagate 8-connected zeros; turn
    all nonzero source and boundary-connected zero pixels to ff in the
    auxiliary image. For each remaining enclosed zero component, flood to
    1, scan bbox, select 0x80 if (max_x-min_x < threshold) OR
    (max_y-min_y < threshold), else ff. After at most 10000 components,
    0x80 pixels change to ff in source and 0 in auxiliary; source is otherwise
    unaffected. The auxiliary is NOT simply a binary copy of source.

    The native function modifies the first arg. If passed a `bytearray`, this
    function mutates that same object. `bytes` are copied for safety.
    """
    size = _check(source, stride, height, roi, destination)
    src = source if isinstance(source, bytearray) else bytearray(source)
    dest = destination if destination is not None else bytearray(size)
    dest[:] = b'\x00' * size
    for i in _border_indices(roi, stride):
        if src[i] == 0:
            dest[i] = 1
    border_sweeps = _flood_one_sweep_8(dest, stride, roi, forbidden=src,
                                       interior_only=True)
    # 40213E..402160: if src[i] != 0 OR dst[i] != 0: dst[i] = ff.
    # This loop scans the FULL buffer; enclosed zeros are the only remaining 0.
    for i in range(size):
        if src[i] != 0 or dest[i] != 0:
            dest[i] = 255

    found = []
    for _ in range(MAX_NATIVE_CYCLES):
        seed = next((y*stride+x
                     for y in range(roi.y0,roi.y1+1)
                     for x in range(roi.x0,roi.x1+1)
                     if dest[y*stride+x] == 0), None)
        if seed is None:
            break
        count = _mark_one_zero_component(dest, stride, roi, seed)
        bounds, pixels = _one_component_bounds(dest, stride, roi)
        span_x = bounds.x1 - bounds.x0
        span_y = bounds.y1 - bounds.y0
        fill_source = span_x < size_threshold or span_y < size_threshold
        # 4023B1..4023E4: rewrite ONLY the 1-labeled component.
        marker = 128 if fill_source else 255
        for y in range(roi.y0,roi.y1+1):
            for x in range(roi.x0,roi.x1+1):
                i = y*stride+x
                if dest[i] == 1:
                    dest[i] = marker
        found.append(Component(bounds,span_x,span_y,fill_source,pixels,count))

    # 4023F4..402421: output merge, both buffers touched.
    for i in range(size):
        if dest[i] == 128:
            if src[i] == 0:
                src[i] = 255
            dest[i] = 0
    return HoleProcessResult(src,dest,tuple(found),border_sweeps)
