"""FindsBlur V1.2.1: exact *local* bit operations independently decoded from EXE.

NO jpeg decoding, segmentation, ROI selection, or full blur calculation is claimed.
The functions below reproduce instruction-level behavior for caller-supplied
rectangles and already-constructed binary masks.  They do not infer geometry.

Original PE SHA-256:
81c1f1aa25116cdd0ab4f2babae5884649c1479a699d85cb885e32695973eb62
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    """Inclusive image coordinate bounds, matching the assembly jle loops."""
    x0: int
    y0: int
    x1: int
    y1: int

    def empty(self) -> bool:
        return self.x0 > self.x1 or self.y0 > self.y1


def _validate_geometry(
    destination: bytearray,
    stride: int,
    height: int,
    rectangles: tuple[Rect, ...],
    source: bytes | bytearray | None = None,
) -> None:
    """Memory-safety checks *not* present in original unchecked native loops."""
    if stride <= 0 or height <= 0:
        raise ValueError("stride and height must be > 0")
    if len(destination) < stride * height:
        raise ValueError("destination too short")
    if source is not None and len(source) < stride * height:
        raise ValueError("source too short")
    for rect in rectangles:
        if rect.empty():
            continue
        if (rect.x0 < 0 or rect.y0 < 0 or rect.x1 >= stride or rect.y1 >= height):
            raise ValueError(f"rectangle outside buffer: {rect}")


def transfer_04_from_nonzero(
    work_flags: bytearray,
    reference: bytes | bytearray,
    *,
    stride: int,
    height: int,
    rect: Rect,
) -> None:
    """Exact byte result of 0x402B00 on valid, equal-stride buffers.

    Precondition: parameters for a legitimate in-bounds caller.
    The function tests one byte from arg1's reference buffer.  When nonzero,
    it performs OR 0x04 into arg2's working-byte buffer, preserving other bits.
    X and Y endpoints are inclusive; other pixels are left untouched.

    Witnesses: 402B57 cmp [...],0 ; 402B5D or byte ptr [...],04 ;
               402B64 / 402B68 jle; 402B76 / 402B7D loop.
    Caller: 4079CF-4079F4, with [esi+8C4] as arg1, [esi+8C0] as arg2.
    """
    _validate_geometry(work_flags, stride, height, (rect,), reference)
    if rect.empty():
        return
    for y in range(rect.y0, rect.y1 + 1):
        offset = y * stride
        for x in range(rect.x0, rect.x1 + 1):
            i = offset + x
            if reference[i] != 0:
                work_flags[i] |= 0x04


def tag_08_outside_inner(
    flags: bytearray,
    *,
    stride: int,
    height: int,
    outer: Rect,
    inner: Rect,
) -> None:
    """Exact local condition used by the loops 0x403587..0x40359F.

    Within caller-provided *outer* rect, OR 0x08 whenever the pixel lies
    strictly outside the *inner* inclusive rect; existing bits are preserved.
    A second code path at 0x403BC3..0x403BDB performs the same comparison.
    This does not reproduce the upstream rectangle selection algorithm.
    """
    _validate_geometry(flags, stride, height, (outer,))
    if outer.empty():
        return
    for y in range(outer.y0, outer.y1 + 1):
        offset = y * stride
        for x in range(outer.x0, outer.x1 + 1):
            if (y < inner.y0 or y > inner.y1 or x < inner.x0 or x > inner.x1):
                flags[offset + x] |= 0x08


def tag_30_where_bit01_on_indices(
    flags: bytearray,
    positions: list[int] | tuple[int, ...],
) -> None:
    """Exact local branch at 0x4035F0..0x4035F8 (also 0x403C2D..35).

    The caller generates the pair of scanline coordinates, which is NOT
    reconstructed here. For each such pixel: if bit 0x01 is set, OR 0x30.
    """
    for pos in positions:
        if pos < 0 or pos >= len(flags):
            raise IndexError(pos)
        if flags[pos] & 0x01:
            flags[pos] |= 0x30


def discard_20_or_10(flag: int, discard_20: bool) -> int:
    """Two explicit machine-code outcomes at 0x403779 vs 0x40378B.

    *Calling this function* requires geometric branch choice from EXE; that
    choice is NOT reproduced. See 0x40376D..0x40378E for path conditions.
    """
    if not 0 <= flag <= 0xFF:
        raise ValueError(flag)
    return flag & (0xDF if discard_20 else 0xEF)


@dataclass(frozen=True)
class WidthProbe:
    """One candidate observed in 0x403FA4..0x404060 or 0x4041F5..0x404298.

    None is a discarded candidate. 0 is an accepted candidate whose raw
    measured width exceeded the caller's maximum plus two.
    """
    status: str
    raw_width: int | None
    counted_width: int | None
    saved_u8: int | None


def probe_width_by_04_run(
    flags: bytes | bytearray,
    *,
    stride: int,
    height: int,
    x: int,
    y: int,
    axis: str,
    lower: int,
    upper: int,
    max_width_argument: int,
) -> WidthProbe:
    """Recover local symmetric width scan in the EXE, not caller ROI selection.

    axis='vertical': 0x403FA4..0x404060; center must contain 0x08 & 0x20.
    axis='horizontal': 0x4041F5..0x404298; center must contain 0x08 & 0x10.

    Width is length of the *continuous* run of 0x04: begin at the candidate
    pixel, scan negative until 0x04 clears, then scan positive from +1.
    Both search directions reject a run which reaches an inclusive boundary.
    When width > (max_width_argument+2), count an actual zero, don't discard.
    Save a one-byte debug width capped at 255, but accumulate the raw integer.
    """
    if axis not in {"vertical", "horizontal"}:
        raise ValueError("axis must be vertical or horizontal")
    if stride <= 0 or height <= 0 or len(flags) < stride * height:
        raise ValueError("invalid buffer geometry")
    if not 0 <= x < stride or not 0 <= y < height:
        raise ValueError("candidate out of bounds")
    length = height if axis == "vertical" else stride
    pos = y if axis == "vertical" else x
    if not 0 <= lower <= pos <= upper < length:
        raise ValueError("invalid scan bounds")
    center = y*stride+x
    required = 0x28 if axis == "vertical" else 0x18
    if flags[center] & required != required:
        return WidthProbe("not_candidate", None, None, None)

    def idx(coord: int) -> int:
        return coord*stride+x if axis == "vertical" else y*stride+coord

    down_or_left = 0
    pointer = pos
    last_negative = pos
    while pointer >= lower and (flags[idx(pointer)] & 0x04):
        down_or_left += 1
        last_negative = pointer
        pointer -= 1
    if last_negative == lower:
        return WidthProbe("touches_negative_border", None, None, None)

    up_or_right = 0
    pointer = pos+1
    last_positive = pointer
    while pointer <= upper and (flags[idx(pointer)] & 0x04):
        up_or_right += 1
        last_positive = pointer
        pointer += 1
    if last_positive == upper:
        return WidthProbe("touches_positive_border", None, None, None)

    raw = down_or_left+up_or_right
    accepted = raw if raw <= max_width_argument+2 else 0
    return WidthProbe("accepted" if accepted==raw else "clipped_to_zero",
                      raw_width=raw,counted_width=accepted,saved_u8=min(accepted,255))


def reduce_scanline_totals(
    counts: list[int] | tuple[int, ...],
    sums: list[int] | tuple[int, ...],
) -> tuple[int, int]:
    """Postprocess one direction: 0x4040EA..0x40414B, 0x404304..0x40433B.

    Each populated row/column contributes EXACTLY ONE integer result; with
    count>=2, width=floor(sum/count + .5), via x87 FILD/FIDIV/FADD(0.5)/_ftol.
    For count==1, the sum is used directly. Count==0 is skipped.
    Returns (sum_of_scanline_representatives, number_of_populated_scanlines).
    """
    if len(counts) != len(sums):
        raise ValueError("count/sum lengths mismatch")
    total=0
    nonempty=0
    for count,value in zip(counts,sums):
        if count<0 or value<0:
            raise ValueError("counts and sums must be nonnegative")
        if count==0:
            continue
        # Exact, for nonnegative 32-bit integer counts and sums;
        # avoids Python's banker-rounding and intermediate float errors.
        representative = value if count==1 else (2*value+count)//(2*count)
        total+=representative
        nonempty+=1
    return total, nonempty


def reduce_final_values(
    *,
    horizontal_rows: tuple[int, int],
    vertical_columns: tuple[int, int],
    offset_pixels: float,
    scale: float,
) -> tuple[float,float,float,float]:
    """Reconstruct 0x40433B..0x404460 from *already computed* scanline totals.

    First output: horizontal-width scanlines (= rows); second: vertical
    width scanlines (= columns). Third: combined weighted mean of those
    *scanline representatives*; fourth: Euclidean norm of first two outputs.

    The scale is a caller argument (0x404406 load), not hardcoded here.
    """
    from math import hypot
    sx,nx=horizontal_rows
    sy,ny=vertical_columns
    if min(nx,ny,sx,sy) < 0:
        raise ValueError("negative count or sum")
    first = sx/nx if nx else 0.0
    second = sy/ny if ny else 0.0
    both = (sx+sy)/(nx+ny) if nx+ny else 0.0
    a,b,c=(max(0.0,v-offset_pixels)*scale for v in (first,second,both))
    return a,b,c,hypot(a,b)


@dataclass(frozen=True)
class NormalizationResult:
    """Status and two integer thresholds from EXE routine 0x404D00."""
    success: bool
    black_level: int
    white_level: int


def normalize_histogram_404d00(
    pixels: bytearray,
    *,
    stride: int,
    height: int,
    rect: Rect,
    low_fraction: float,
    high_fraction: float,
) -> NormalizationResult:
    """Independent scalar decompilation of 0x404D00..0x404F00.

    1. Build 256-bin histogram from ROI (inclusive), not full buffer.
    2. From the low and high ends, choose the first bin whose cumulative
       pixel count is STRICTLY GREATER than pixel_count * respective fraction.
    3. Fail if black >= white, before modifying the image.
    4. Map each ROI pixel using the uint8 LUT:
       clip_0_255( trunc((pixel-black)*255/(white-black) + 0.5) ).
       In original, x87 floats are used; integer math for the positive-range
       LUT is equivalent to the observed expression for normal dimensions.

    Evidence: histogram 404D5D..404D79; fraction/quantiles 404DD2..404E47;
    denominator 404E5B; LUT 404E6D..404EA5; apply 404ED5..404EE6.
    The function is caller-driven, including both fractions. No 5% constant
    is inserted here. The original expects valid in-bounds native arguments.
    """
    _validate_geometry(pixels,stride,height,(rect,))
    if rect.empty():
        raise ValueError("empty ROI is not a valid histogram")
    if not (0.0 <= low_fraction < 1.0 and 0.0 <= high_fraction < 1.0):
        raise ValueError("fractions should be in [0,1)")

    hist=[0]*256
    for y in range(rect.y0,rect.y1+1):
        offset=y*stride
        for x in range(rect.x0,rect.x1+1):
            hist[pixels[offset+x]]+=1
    n=(rect.x1-rect.x0+1)*(rect.y1-rect.y0+1)

    low_count=0
    black=0
    for i in range(256):
        low_count+=hist[i]
        if low_count>n*low_fraction:
            black=i
            break

    high_count=0
    white=255
    for i in range(255,-1,-1):
        high_count+=hist[i]
        if high_count>n*high_fraction:
            white=i
            break

    if black>=white:
        return NormalizationResult(False,black,white)

    den=white-black
    # Original uses FILD / FADD(0.5) / _ftol, then clamps into uint8.
    lut=[max(0,min(255,((2*(i-black)*255+den)//(2*den)))) for i in range(256)]
    for y in range(rect.y0,rect.y1+1):
        base=y*stride
        for x in range(rect.x0,rect.x1+1):
            loc=base+x
            pixels[loc]=lut[pixels[loc]]
    return NormalizationResult(True,black,white)


def luminance_from_3_buffers_404550(
    channel_117: bytes | bytearray,
    channel_601: bytes | bytearray,
    channel_306: bytes | bytearray,
    *,
    stride: int,
    height: int,
    rect: Rect,
) -> bytearray:
    """EXE 0x404550 exact fixed-point three-channel intensity conversion.

    It first initializes the *entire* output to 0xFF, and writes the ROI only:
        dst = (117 * c117 + 601 * c601 + 306 * c306) >> 10.

    No rounding correction or floating-point operations are involved.
    Source byte-array mapping to named R/G/B is deliberately deferred until
    the caller's channel-buffer layout is independently reconstructed.
    Witnesses: 0x404568 fill FF; 0x4045F5..0x40462D multiply/shift.
    """
    _validate_geometry(bytearray(stride*height),stride,height,(rect,),channel_117)
    if len(channel_601) < stride*height or len(channel_306) < stride*height:
        raise ValueError("source channel too short")
    dst=bytearray([0xFF])*(stride*height)
    if rect.empty():
        return dst
    for y in range(rect.y0,rect.y1+1):
        base=y*stride
        for x in range(rect.x0,rect.x1+1):
            i=base+x
            dst[i]=(117*channel_117[i]+601*channel_601[i]+306*channel_306[i]) >> 10
    return dst


def gamma_lut_404670(exponent: float) -> bytes:
    """Algorithm of EXE gamma LUT builder 0x4046B8..0x404704.

    Each input byte b maps to clamp_to_u8(_ftol(255.0*_CIpow(b/255.0,
    exponent)+0.5)). The original calls MSVCRT _CIpow on x87 registers;
    Python's math.pow may differ in the last bit at rounding boundaries.
    Therefore this is an INSTRUCTION-BACKED mathematical translation, not
    an assertion of exact Microsoft x87 floating-point parity.
    """
    from math import pow, trunc
    if not 0.0 < exponent < 1000.0:
        raise ValueError("gamma exponent must be positive and finite")
    return bytes(max(0,min(255,trunc(255.0*pow(i/255.0,exponent)+0.5)))
                 for i in range(256))


def apply_gamma_lut_404670(
    pixels: bytes | bytearray,
    *,
    stride: int,
    height: int,
    rect: Rect,
    exponent: float,
    destination: bytearray | None = None,
) -> bytearray:
    """Image buffer logic from 0x404670..0x404790.

    When source != destination, clear destination to 0xFF first. Only ROI is
    re-mapped with the LUT. Supports in-place updates as the original does.
    """
    if destination is None:
        destination=bytearray(stride*height)
    _validate_geometry(destination,stride,height,(rect,),pixels)
    if destination is not pixels:
        destination[:stride*height]=b"\xFF"*(stride*height)
    lut=gamma_lut_404670(exponent)
    if rect.empty():
        return destination
    for y in range(rect.y0,rect.y1+1):
        for x in range(rect.x0,rect.x1+1):
            i=y*stride+x
            destination[i]=lut[pixels[i]]
    return destination
