"""Independent 0x403E30 scanline evidence, without any official reference input.

This opt-in trace uses the separate scalar translation in phase3.mask_stage,
NOT the optimized Numba scanner in recovered_final_width_403e30.py. Results
are cross-checked against the production scanner for the same staged flags.
It cannot demonstrate that the upstream native EXE generated identical flags.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Sequence
import numpy as np

from phase3.mask_stage import probe_width_by_04_run, reduce_scanline_totals
from phase12.recovered_final_width_403e30 import measure_403e30


@dataclass(frozen=True)
class ScanlineTrace:
    axis: str
    coordinate: int
    sample_count: int
    raw_width_sum: int
    rounded_width: int
    samples: tuple[dict, ...]


def trace_scanlines_403e30(
    flags: Sequence[int], *, width: int, height: int,
    roi: tuple[int, int, int, int], max_width: int,
    scale: float = 1.25,
) -> dict:
    """Collect per-candidate and per-row/column results, with exact scalar cross-check.

    Does not access image paths, filenames, reference TXT or official numeric
    results. ROI is inclusive (x0,y0,x1,y1). The return value is JSON-serializable.
    """
    x0, y0, x1, y1 = roi
    fast = measure_403e30(
        flags, width=width, height=height, roi=roi,
        max_width=max_width, scale=scale,
    )
    mask = np.frombuffer(bytes(flags), dtype=np.uint8).reshape(height, width)
    inside = mask[y0:y1+1, x0:x1+1]
    axes = []
    for axis, required, size in (
        ('horizontal', 0x18, height), ('vertical', 0x28, width),
    ):
        accepted = defaultdict(list)
        rejected = defaultdict(list)
        cropped_y, cropped_x = np.nonzero((inside & required) == required)
        status_counts: dict[str, int] = defaultdict(int)
        for ry, rx in zip(cropped_y.tolist(), cropped_x.tolist()):
            x, y = rx+x0, ry+y0
            line = y if axis == 'horizontal' else x
            probe = probe_width_by_04_run(
                flags, stride=width, height=height, x=x, y=y,
                axis=axis, lower=y0 if axis == 'vertical' else x0,
                upper=y1 if axis == 'vertical' else x1,
                max_width_argument=max_width,
            )
            status_counts[probe.status] += 1
            sample = {
                'x':x, 'y':y, 'status':probe.status,
                'raw_width':probe.raw_width,
                'counted_width':probe.counted_width,
            }
            if probe.counted_width is not None:
                accepted[line].append(sample)
            else:
                rejected[line].append(sample)
        lines=[]
        counts=[0]*size
        sums=[0]*size
        for coord in sorted(set(accepted) | set(rejected)):
            acc = accepted.get(coord, [])
            cnt = len(acc)
            total = sum(s['counted_width'] for s in acc)
            counts[coord]=cnt
            sums[coord]=total
            if cnt:
                representative=total if cnt==1 else (2*total+cnt)//(2*cnt)
            else:
                representative=None
            lines.append(asdict(ScanlineTrace(
                axis=axis, coordinate=coord, sample_count=cnt,
                raw_width_sum=total, rounded_width=representative,
                samples=tuple(acc+rejected.get(coord, [])),
            )))
        s,n=reduce_scanline_totals(counts, sums)
        axes.append({
            'axis':axis,
            'required_bits':f'0x{required:02X}',
            'total_rounded_width':s,
            'populated_lines':n,
            'accepted_samples':sum(counts),
            'status_counts':dict(status_counts),
            'lines':lines,
        })
    horizontal,vertical=axes
    fast_x=(fast.x_line_rounded_sum,fast.x_row_valid_count,fast.x_raw_samples)
    fast_y=(fast.y_line_rounded_sum,fast.y_col_valid_count,fast.y_raw_samples)
    slow_x=(horizontal['total_rounded_width'],horizontal['populated_lines'],horizontal['accepted_samples'])
    slow_y=(vertical['total_rounded_width'],vertical['populated_lines'],vertical['accepted_samples'])
    if (slow_x,slow_y)!=(fast_x,fast_y):
        raise AssertionError(f'0x403E30 optimized/scalar mismatch: X {slow_x}!={fast_x}, Y {slow_y}!={fast_y}')
    return {
        'method':'0x403E30 independent scalar-vs-Numba measurement',
        'official_results_consulted':False,
        'native_upstream_flag_parity_verified':False,
        'roi_xyxy':list(roi),
        'width_limit_argument':max_width,
        'candidate_values':list(fast.values),
        'scalar_and_optimized_identical':True,
        'axes':axes,
    }
