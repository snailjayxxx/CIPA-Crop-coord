"""Values reconstructed from FindsBlur V1.2.1 x87 initialization (0x407D42-0x407F2A).

No official TXT values are read by this module.  All constants are taken
from the fixed PE .rdata and x87 opcodes, see native_parameter_evidence.md.
The native _ftol has nonnegative operands at these conversions; we use the
x87 +0.5 before truncation, without Python banker's round.
"""
from dataclasses import dataclass
from math import trunc


def _ftol_add_half(a: float) -> int:
    return trunc(a + 0.5)


@dataclass(frozen=True)
class NativeParameters:
    short: int
    median_luminance: int
    median_difference: int
    max_min_radius: int
    low_fraction: float
    high_fraction: float
    threshold_first: int
    threshold_second: int
    repair_radius_first: int
    repair_radius_second: int
    ring_start: int
    ring_width: int
    hole_threshold: int
    x_margin: int
    y_margin: int
    gamma: float
    final_scale: float
    final_offset: float
    # x87 initialization values used later by measurement stages
    field_0x840: int
    field_0x844: int
    field_0x848: int
    field_0x850: int
    field_0x898: int


def from_dimensions(width: int, height: int) -> NativeParameters:
    if width <= 0 or height <= 0:
        raise ValueError('positive dimensions required')
    s = min(width, height)
    # At 407D46: lea eax,[eax+eax*2]; 407D53..59 ecx = 60*s.
    # 429638 = 1/24000.0; 429280=0.5. These are native values.
    unit = 60.0 * s * (1.0 / 24000.0)
    median_difference = _ftol_add_half(unit * 0.5)
    max_min_radius = _ftol_add_half(unit * 20.0 * 0.3 + 5.0)
    # 407DBF and 407DF0 subtract earlier st(3) from s*.2*.5.
    median_other = s * 0.2 * 0.5 - unit * 20.0
    repair_first = _ftol_add_half(median_other * 0.5)
    repair_second = _ftol_add_half(median_other * 0.5 * 0.5)
    # 407E1C..32 combines 0.2*S and 0.05*S, then halves -> 3000um.
    ring_start = _ftol_add_half((s * 0.2 + unit * 20.0) * 0.5)
    # 407E37..6E obtains 2160um from 0.9 * min(3000um, 3000um-600um).
    ring_width = _ftol_add_half(min((s * 0.2 + unit * 20.0) * 0.5, (s * 0.2 + unit * 20.0) * 0.5 - 0.5*unit*20.0)*0.9)
    # 0x407E7F uses the *remaining short-edge ST(0)* after 0x407E7A
    # _ftol consumes the ring-width candidate, leaving ST(0)=short_edge.
    # It multiplies short_edge by 1/64, NOT unit*20/64.
    # 0x407E9E / 0x407EA0 doubles this value for +0x848.
    x87_aux = s * 0.015625
    f844 = _ftol_add_half(x87_aux)
    f848 = _ftol_add_half(x87_aux*2)
    # 407EDA: short*.2333333333 (4295F8); 407EF4 uses the same
    # x87 auxiliary from initialization. 407F11: short*.15 (4295F0).
    hole_threshold = _ftol_add_half(s * (0.2333333333333333))
    margin_first = _ftol_add_half(s * (0.2333333333333333) + x87_aux)
    margin_second = _ftol_add_half(s * 0.15 + x87_aux)
    return NativeParameters(
        short=s,
        median_luminance=5,
        median_difference=median_difference,
        max_min_radius=max_min_radius,
        low_fraction=0.05,
        high_fraction=0.05,
        threshold_first=26,
        threshold_second=26,
        repair_radius_first=repair_first,
        repair_radius_second=repair_second,
        ring_start=ring_start,
        ring_width=ring_width,
        hole_threshold=hole_threshold,
        x_margin=margin_second,  # [esi+0x870], 40781A
        y_margin=margin_first,  # [esi+0x86c], 40781B
        gamma=2.2,
        final_scale=1.25,
        final_offset=2.0,
        field_0x840=ring_width,
        field_0x844=f844,
        field_0x848=f848,
        field_0x850=26,
        # 0x407ED1 moves the second x87 round to EDI; 0x407F36 copies
        # EDI into +0x898 (nearby junction cutoff), NOT hole_threshold.
        field_0x898=_ftol_add_half(x87_aux),
    )
