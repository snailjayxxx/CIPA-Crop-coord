"""Instruction-oriented reconstruction of FindsBlur V1.2.1 at VA 0x401000.

Provenance: literal control flow and stack-offset tables in the user's original
TargetEXE.exe (SHA-256 81c1f1aa...73eb62). No PDF-derived morphological
shortcuts and no regression-value fitting.

Native call: 401000(source, output_A, work_B, stride, height,
                    outer_x0, outer_y0, outer_x1, outer_y1,
                    inner_x0, inner_y0, inner_x1, inner_y1)

Safety guard: require a one-pixel *image* border around outer, so the original
unconditional neighbor-pointer dereferences cannot leave the Python buffer.
This is a documented wrapper constraint, not a claim that the native function
contains an equivalent validation. The caller is expected to supply a padded
rect; call-site argument provenance still needs end-to-end confirmation.

This is a static instruction reconstruction, NOT native x86 differential proof.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

# The previously independently instruction-recovered gate at 401A29 is reused
# verbatim; this module must also run under unittest with cwd=phase9.
_PARENT = str(Path(__file__).resolve().parent.parent)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)
from phase8.recovered_component_gate import (  # noqa: E402
    Rect,
    commit_component_401a29,
    clear_rejected_80_401b8b,
)

MAX_NATIVE_ROUNDS = 0x2710  # addresses 40158A, 4016FE, 401A1B, 401B7D

# 401094..4010B0: 8 DWORD neighbor-pointer displacements, in exact order.
_NEIGHBORS_8 = ((-1, -1), (0, -1), (1, -1), (-1, 0),
                (1, 0), (-1, 1), (0, 1), (1, 1))

# 4010E4..401130: four groups of FIVE neighbors for the four edges:
# top, bottom, left, right.  Their order is preserved for in-place propagation.
_EDGE_FIVE = (
    ((-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)),
    ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0)),
    ((0, -1), (1, -1), (1, 0), (0, 1), (1, 1)),
    ((-1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)),
)

# 4010B4..4010E0: four groups of THREE neighbors at four corners:
# top-left, top-right, bottom-left, bottom-right.
_CORNER_THREE = (
    ((1, 0), (0, 1), (1, 1)),
    ((-1, 0), (0, 1), (-1, 1)),
    ((0, -1), (1, -1), (1, 0)),
    ((0, -1), (-1, -1), (-1, 0)),
)


@dataclass(frozen=True, slots=True)
class ComponentTrace:
    seed_axis: str
    seed_x: int
    seed_y: int
    seed_run_pixels: int
    propagation_rounds: int
    propagation_pixels: int
    marked_pixels: int
    kept: bool


@dataclass(frozen=True, slots=True)
class RegionTrace:
    components: tuple[ComponentTrace, ...]
    accepted_components: int
    rejected_components: int
    accepted_pixels: int
    rejected_pixels_cleared: int
    x_seed_components: int
    y_seed_components: int


def _validate(source: bytes | bytearray, output_a: bytearray, work_b: bytearray,
              stride: int, height: int, outer: Rect, inner: Rect) -> None:
    size = stride * height
    if stride < 3 or height < 3 or any(len(v) != size for v in (source, output_a, work_b)):
        raise ValueError('buffers must be equal flat stride*height images')
    if source is output_a or source is work_b or output_a is work_b:
        raise ValueError('native caller supplies three separate buffers')
    if not (1 <= outer.left < outer.right <= stride - 2 and
            1 <= outer.top < outer.bottom <= height - 2):
        raise ValueError('outer ROI must be within the image with a 1-pixel safety halo')
    if not (outer.left <= inner.left <= inner.right <= outer.right and
            outer.top <= inner.top <= inner.bottom <= outer.bottom):
        raise ValueError('inner ROI must be contained within outer ROI')


def _try_mark(i: int, source: bytes | bytearray, output_a: bytearray,
              work_b: bytearray, stride: int,
              offsets: tuple[tuple[int, int], ...]) -> int:
    """Equivalent to 401403..401437 and 4014C5..4014F5 predicate order."""
    if source[i] == 0 or output_a[i] != 0 or work_b[i] != 0:
        return 0
    for dx, dy in offsets:
        if work_b[i + dy * stride + dx] == 0xff:
            work_b[i] = 0xff
            return 1
    return 0


def _propagate(work_b: bytearray, source: bytes | bytearray,
               output_a: bytearray, stride: int, outer: Rect, *,
               seed_axis: str) -> tuple[int, int]:
    """Reproduce 40135E..401598 (x-seeds) or 40181D..401A29 (y-seeds).

    First phase scans row-major, second phase scans column-major. Each round
    walks interiors *before* four border-edge + corner groups. Pixel writes
    are immediate, so later positions of the same round see prior changes.
    """
    rounds = 0
    pixels = 0
    if seed_axis == 'x':
        def positions():
            for y in range(outer.top + 1, outer.bottom):
                for x in range(outer.left + 1, outer.right):
                    yield y * stride + x
    elif seed_axis == 'y':
        def positions():
            for x in range(outer.left + 1, outer.right):
                for y in range(outer.top + 1, outer.bottom):
                    yield y * stride + x
    else:
        raise ValueError('seed_axis must be x or y')

    # Specific order from the four-mode stack tables at 40144D..401581 and
    # 4018F4..401A12; the corner follows its corresponding edge.
    corners = ((outer.left, outer.top), (outer.right, outer.top),
               (outer.left, outer.bottom), (outer.right, outer.bottom))

    # Edge iterators are freshly created every round, preserving scan order.
    for _ in range(MAX_NATIVE_ROUNDS):
        rounds += 1
        changed = 0
        for index in positions():
            changed += _try_mark(index, source, output_a, work_b, stride, _NEIGHBORS_8)
        for mode, corner in enumerate(corners):
            if mode == 0:
                edge = ((x, outer.top) for x in range(outer.left + 1, outer.right))
            elif mode == 1:
                edge = ((x, outer.bottom) for x in range(outer.left + 1, outer.right))
            elif mode == 2:
                edge = ((outer.left, y) for y in range(outer.top + 1, outer.bottom))
            else:
                edge = ((outer.right, y) for y in range(outer.top + 1, outer.bottom))
            for x, y in edge:
                changed += _try_mark(y * stride + x, source, output_a, work_b,
                                     stride, _EDGE_FIVE[mode])
            x, y = corner
            changed += _try_mark(y * stride + x, source, output_a, work_b,
                                 stride, _CORNER_THREE[mode])
        pixels += changed
        if not changed:
            break
    return rounds, pixels


def process_region_401000(
    source: bytes | bytearray,
    output_a: bytearray,
    work_b: bytearray,
    *, stride: int, height: int, outer: Rect, inner: Rect,
) -> RegionTrace:
    """Process region with exact two seed-axis passes and 10,000-round caps.

    The two phases select candidates along outer TOP, then outer LEFT. Each
    candidate is propagated in work B, classified by opposite INNER boundaries,
    and copied to A as FF or 80. Only after both phases all 80 are cleared.
    """
    _validate(source, output_a, work_b, stride, height, outer, inner)
    # 40101B..401038: clear ALL output bytes before processing outer ROI.
    output_a[:] = b'\x00' * len(output_a)
    component_traces: list[ComponentTrace] = []

    for axis in ('x', 'y'):
        # 401269/401714: component counter is reset when changing axis; check
        # 4016FE/401B7D limits after completing the current component.
        for _ in range(MAX_NATIVE_ROUNDS):
            # 40127A / 401725: memset entire work B even on the final empty search
            work_b[:] = b'\x00' * len(work_b)
            if axis == 'x':
                # 4012CB: scan outer TOP row left-to-right, exact two byte tests.
                y = outer.top
                found = next((x for x in range(outer.left, outer.right + 1)
                              if source[y * stride + x] != 0 and
                              output_a[y * stride + x] == 0), None)
                if found is None:
                    break
                x = found
                seed_x, seed_y = found, y
                run = 0
                # 401321..401334: contiguous run along top border to the right
                while x <= outer.right and source[y * stride + x] != 0 and output_a[y * stride + x] == 0:
                    work_b[y * stride + x] = 0xff
                    run += 1
                    x += 1
            else:
                # 40176E: scan outer LEFT column top-to-bottom.
                x = outer.left
                found = next((y for y in range(outer.top, outer.bottom + 1)
                              if source[y * stride + x] != 0 and
                              output_a[y * stride + x] == 0), None)
                if found is None:
                    break
                y = found
                seed_x, seed_y = x, found
                run = 0
                # 4017E3..4017F8: contiguous run down the left border
                while y <= outer.bottom and source[y * stride + x] != 0 and output_a[y * stride + x] == 0:
                    work_b[y * stride + x] = 0xff
                    run += 1
                    y += 1
            prop_rounds, prop_pixels = _propagate(work_b, source, output_a, stride, outer, seed_axis=axis)
            gate = commit_component_401a29(output_a, work_b, stride=stride, height=height,
                                            outer=outer, inner=inner)
            component_traces.append(ComponentTrace(axis, seed_x, seed_y, run,
                                                    prop_rounds, prop_pixels,
                                                    gate.written_pixels, gate.spans_two_sides))

    # 401B8B..401BE2: cleanup ONLY once, after both seed-axis phases.
    rejected_cleared = clear_rejected_80_401b8b(output_a, stride=stride, height=height, outer=outer)
    return RegionTrace(
        components=tuple(component_traces),
        accepted_components=sum(t.kept for t in component_traces),
        rejected_components=sum(not t.kept for t in component_traces),
        accepted_pixels=sum(v == 0xff for v in output_a),
        rejected_pixels_cleared=rejected_cleared,
        x_seed_components=sum(t.seed_axis == 'x' for t in component_traces),
        y_seed_components=sum(t.seed_axis == 'y' for t in component_traces),
    )
