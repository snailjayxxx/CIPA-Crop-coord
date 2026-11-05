"""Direct-EXE-referenced main-route (0x402B90) junction selection and ring.

This does NOT consult the official output text, and must not be used to
claim parity until the complete caller route and decoded pixels are verified.

Original i386 addresses:
0x402C97..402D38: projection of flags&0x07 into integer x/y histograms.
0x402DDA..402E17: local height/width half thresholds and _ftol.
0x402E8B..402F3A: select at most 100 branch candidates (flags&0x02)
                     with two projection-window comparisons.
0x402F6D..40316B: locate first/last rows/columns containing bit0x04,
                     conditionally trim with native x/y margin args.
0x4031A6..40323D: intersect two candidate tables by exact (x,y) pair,
                     excluding candidates outside the computed rectangle.
0x403253..40337C: closest center branch, strict-near neighbors.
0x403384..4037C9: rect/annulus/0x30 propagation/axis flags; shared with
                     the independently reconstructed 4037F0 tail.

`mark_measurement_4037f0` tail assumes a matching center+candidate array;
reusing it here avoids introducing another, divergent, ring implementation.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Sequence
import numpy as np
from .recovered_measurement_region_4037f0 import mark_measurement_4037f0, Region4037F0

@dataclass(frozen=True)
class MainRoute402B90:
    success: bool
    reason: str
    flags: bytes
    x_histogram: np.ndarray
    y_histogram: np.ndarray
    x_candidates: tuple[tuple[int,int],...]
    y_candidates: tuple[tuple[int,int],...]
    intersections: tuple[tuple[int,int],...]
    first_last_region: tuple[int,int,int,int]|None
    region: Region4037F0|None
    x_threshold: int
    y_threshold: int


def _sum_inclusive(cumsum: np.ndarray, a: int, b: int) -> int:
    a=max(0,a)
    b=min(len(cumsum)-2,b)
    return int(cumsum[b+1]-cumsum[a]) if a<=b else 0


def _half_positive(value: int, factor: float) -> int:
    return int(value*factor + .5)  # x87 fadd 0.5 before _ftol


def mark_measurement_402b90(flags:Sequence[int],*,width:int,height:int,
                              processing_roi:tuple[int,int,int,int],
                              scan_roi:tuple[int,int,int,int],
                              ring_start:int,ring_width:int,
                              histogram_radius:int,x_margin:int,y_margin:int,
                              nearby_distance:int,screen_half_ratio:float=0.5,
                              asymmetry_weight:float=.75)->MainRoute402B90:
    """Native 0x402B90 normal-route complete preselection+ring tail.

    Rect tuples inclusive (x0,y0,x1,y1); all physical parameters come
    from caller 0x407A7A–407B07 not from any reference TXT.

    `scan_roi` is the actual native bitmap rectangle for ring bound checking;
    `processing_roi` is caller [arg4...arg7] for histogram/branch search.
    """
    if len(flags)!=width*height:raise ValueError('Flag buffer dimension mismatch')
    x0,y0,x1,y1=processing_roi
    if not(0<=x0<=x1<width and 0<=y0<=y1<height):
        raise ValueError('bad main path ROI')
    radius=int(histogram_radius)
    if radius<0 or nearby_distance<0:raise ValueError('negative native radii')
    frame=np.frombuffer(bytes(flags),np.uint8).reshape(height,width)
    # 0x402CB7/402D15: projections of any (0x01|0x02|0x04)
    active=(frame[y0:y1+1,x0:x1+1]&7)!=0
    x_hist=np.zeros(width,dtype=np.int64)
    y_hist=np.zeros(height,dtype=np.int64)
    x_hist[x0:x1+1]=np.count_nonzero(active,axis=0)
    y_hist[y0:y1+1]=np.count_nonzero(active,axis=1)
    csx=np.empty(width+1,dtype=np.int64);csx[0]=0;np.cumsum(x_hist,out=csx[1:])
    csy=np.empty(height+1,dtype=np.int64);csy[0]=0;np.cumsum(y_hist,out=csy[1:])
    x_threshold=_half_positive(y1-y0-2*radius+1,screen_half_ratio)
    y_threshold=_half_positive(x1-x0-2*radius+1,screen_half_ratio)
    two_lists=[[],[]]
    # 0x402E4D starts at x0+radius, y0+radius; the projection is
    # cumulative absolute whole-image coordinates (not ROI-local).
    if x0+radius <= x1-radius and y0+radius <= y1-radius:
        for yy in range(y0+radius,y1-radius+1):
            for xx in range(x0+radius,x1-radius+1):
                if not (int(frame[yy,xx]) & 2):continue
                a=_sum_inclusive(csx,xx-radius,xx+radius)
                b=_sum_inclusive(csy,yy-radius,yy+radius)
                if a>x_threshold and len(two_lists[0])<100:
                    two_lists[0].append((xx,yy))
                if b>y_threshold and len(two_lists[1])<100:
                    two_lists[1].append((xx,yy))
    x_candidates=tuple(two_lists[0]);y_candidates=tuple(two_lists[1])
    # 0x402F6D–403112: edges of union of pixels bearing 0x04.
    source=(frame[y0:y1+1,x0:x1+1]&4)!=0
    indices=np.argwhere(source)
    def fail(reason,limited=None):
        return MainRoute402B90(False,reason,bytes(flags),x_hist,y_hist,x_candidates,
                                y_candidates,(),limited,None,x_threshold,y_threshold)
    if len(indices)==0:
        return fail('native:no 0x04 pixels in processing rectangle')
    lo_y,lo_x=indices.min(axis=0);hi_y,hi_x=indices.max(axis=0)
    lo_x+=x0;hi_x+=x0;lo_y+=y0;hi_y+=y0
    # At 403119 and 403141 the margins are added only if the found
    # bit04 border did not reach the original region boundary.
    ax0=int(lo_x+(x_margin if lo_x!=x0 else 0))
    ay0=int(lo_y+(y_margin if lo_y!=y0 else 0))
    ax1=int(hi_x-(x_margin if hi_x!=x1 else 0))
    ay1=int(hi_y-(y_margin if hi_y!=y1 else 0))
    allowable=(ax0,ay0,ax1,ay1)
    if ax0>ax1 or ay0>ay1:return fail('native:bit04 extents trimmed away',allowable)
    # Native independently builds the two ordered candidate lists of ≤100
    # and then takes pairwise intersections; the order of table[0] is stable.
    permitted=set(q for q in y_candidates if ax0<=q[0]<=ax1 and ay0<=q[1]<=ay1)
    matched=tuple(q for q in x_candidates if q in permitted)
    if not matched:
        return MainRoute402B90(False,'native:no matching projection junctions',
                bytes(flags),x_hist,y_hist,x_candidates,y_candidates,matched,allowable,None,
                x_threshold,y_threshold)
    tail=mark_measurement_4037f0(flags,width=width,height=height,
             branch_roi=processing_roi,image_roi=scan_roi,
             ring_start=ring_start,ring_width=ring_width,
             nearby_distance=nearby_distance,asymmetry_weight=asymmetry_weight,
             candidate_junctions=matched)
    return MainRoute402B90(tail.success,tail.reason,tail.flags,x_hist,y_hist,
             x_candidates,y_candidates,matched,allowable,tail,x_threshold,y_threshold)
