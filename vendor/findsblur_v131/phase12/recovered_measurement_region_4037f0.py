"""Direct reconstruction of the *mode==1* native measurement marker (0x4037F0).

All geometrical conditions are taken from 0x4038AC..0x403E02. This function
receives its *actual caller* ROI and parameters rather than deriving them by
looking at oracle TXT output. It does not decide when the native caller takes
this path; that is a separate 0x408290/0x407A02 control-flow task.

For computation speed the monotonically expanding 0x30 marker closure is
implemented with 8-connected binary propagation; explicit sequential copies
are tested to have the same final fixed-point on bounded graphs. The native
iteration has at most area-sized sweeps; this replacement reports the limit
and does not claim machine-cycle equivalence.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence
import numpy as np
from scipy import ndimage


@dataclass(frozen=True)
class Region4037F0:
    success: bool
    reason: str
    flags: bytes
    branch_count: int
    center_branch: tuple[int,int]|None
    branch_bbox: tuple[int,int,int,int]|None
    inner: tuple[int,int,int,int]|None
    outer: tuple[int,int,int,int]|None
    ring_pixels: int
    candidate_marked_pixels: int
    axis_0x10: int
    axis_0x20: int


def mark_measurement_4037f0(flags:Sequence[int],*,width:int,height:int,
                             branch_roi:tuple[int,int,int,int],
                             image_roi:tuple[int,int,int,int],
                             ring_start:int,ring_width:int,nearby_distance:int,
                             asymmetry_weight:float=0.75,
                             candidate_junctions:Sequence[tuple[int,int]]|None=None)->Region4037F0:
    """x86 arguments 1,2,3,4,6,7,8,9..16. Inclusive (x0,y0,x1,y1).

    0x4038AC scans byte & 0x02 in `branch_roi` into a stack table of 100
    pairs, 0x403971 selects minimum max-norm scaled distance, 0x403A16
    identifies strict-nearby junctions, 0x403A6B..0x403B8F checks ring
    rectangle bounds, 0x403BC3 marks annular 0x08, 0x403C22 seeds 0x30,
    0x403CDD propagates, and 0x403D84 chooses orientation 0x10/0x20.
    """
    if len(flags)!=width*height:raise ValueError('bad flag image size')
    bx0,by0,bx1,by1=branch_roi
    ix0,iy0,ix1,iy1=image_roi
    if not (0<=bx0<=bx1<width and 0<=by0<=by1<height and
            0<=ix0<=ix1<width and 0<=iy0<=iy1<height):
        raise ValueError('bad native rectangles')
    if min(ring_start,ring_width,nearby_distance)<0:raise ValueError('negative native extent')
    frame=np.frombuffer(bytes(flags),np.uint8).reshape(height,width).copy()
    if candidate_junctions is None:
        points=np.argwhere((frame[by0:by1+1,bx0:bx1+1]&2)!=0)
        pts=[(int(x)+bx0,int(y)+by0) for y,x in points]
    else:
        pts=[(int(x),int(y)) for x,y in candidate_junctions]
        if any(not (bx0<=x<=bx1 and by0<=y<=by1 and (frame[y,x]&2)) for x,y in pts):
            raise ValueError('invalid native junction candidate coordinates')
    count=len(pts)
    def fail(reason):
        return Region4037F0(False,reason,frame.tobytes(),count,None,None,None,None,0,0,0,0)
    if count==0:return fail('native:NO_BRANCH_POINT')
    if count>100:return fail('native:100-entry stack junction table overrun; refuse unsafe translation')
    cx0=(bx0+bx1)*0.5;cy0=(by0+by1)*0.5
    # 0x403910..0x403937 swaps the 1.0 / caller 0.75 multipliers
    # based on stride>height; 0x403982 and 0x403990 select Chebyshev max.
    if width>height:weight_x,weight_y=asymmetry_weight,1.0
    else:weight_x,weight_y=1.0,asymmetry_weight
    center=min(pts,key=lambda q:max(abs(q[0]-cx0)*weight_x,abs(q[1]-cy0)*weight_y))
    near=[p for p in pts if abs(p[0]-center[0])<nearby_distance
                      and abs(p[1]-center[1])<nearby_distance]
    if not near:return fail('native:no_nearby_junctions')
    xmin=min(p[0] for p in near);xmax=max(p[0] for p in near)
    ymin=min(p[1] for p in near);ymax=max(p[1] for p in near)
    inner=(xmin-ring_start,ymin-ring_start,xmax+ring_start,ymax+ring_start)
    outer=tuple((v + (-ring_width if i<2 else ring_width)) for i,v in enumerate(inner))
    ox0,oy0,ox1,oy1=outer
    px0,py0,px1,py1=inner
    bb=(xmin,ymin,xmax,ymax)
    if ox0<ix0 or oy0<iy0 or ox1>ix1 or oy1>iy1:
        return Region4037F0(False,'native:ring crosses provided processing ROI',frame.tobytes(),count,center,bb,inner,outer,0,0,0,0)
    # 403BBD..403BF4 - ring: set 0x08 outside inner rectangle.
    yy,xx=np.ogrid[oy0:oy1+1,ox0:ox1+1]
    ring=~((xx>=px0)&(xx<=px1)&(yy>=py0)&(yy<=py1))
    section=frame[oy0:oy1+1,ox0:ox1+1]
    section[ring] |= 8
    # 403C22..403C8E - seed 0x30 at 0x01 skeleton pixels along
    # the four sides of the nearby-branch enclosing rectangle.
    for y in range(ymin,ymax+1):
        for x in (xmin,xmax):
            if frame[y,x]&1:frame[y,x] |= 0x30
    for x in range(xmin,xmax+1):
        for y in (ymin,ymax):
            if frame[y,x]&1:frame[y,x] |= 0x30
    # 403CCD..403D33: 8-neighbor propagation from seeding, through
    # 0x01 skeleton only (but any pre-existing 0x30 pixel can seed).
    # Native 0x40365D–0x403696 computes (outer_max-outer_min+1)
    # for BOTH dimensions. Prior translation wrongly skipped the outer
    # perimeter, losing two valid rows/columns from each measurement ring.
    sy0,sy1=oy0,oy1+1
    sx0,sx1=ox0,ox1+1
    if sy0<sy1 and sx0<sx1:
        f=frame[sy0:sy1,sx0:sx1]
        seeds=(f&0x30)!=0
        reachable=ndimage.binary_propagation(seeds,structure=np.ones((3,3),np.uint8),mask=(f&1)!=0)
        f[reachable] |= 0x30
    # 403D33..403DD4: two diagonal cuts from branch bounding-box center.
    midx=int((xmin+xmax)/2);midy=int((ymin+ymax)/2)
    candidates=((section&0x30)!=0)&((section&8)!=0)
    oy,ox=np.nonzero(candidates)
    xx=ox+ox0;yy=oy+oy0
    # The boundary ties are from jL/jG at 0x403DAC..0x403DBD.
    dx=xx-midx;dy=yy-midy
    vertical=(dy>=dx)&(dy>=-dx) | (dy<=dx)&(dy<=-dx)
    keepx=~vertical
    section[oy[vertical],ox[vertical]] &= np.uint8(0xdf) # bit 0x20 removed
    section[oy[keepx],ox[keepx]] &= np.uint8(0xef) # bit 0x10 removed
    return Region4037F0(True,'ok',frame.tobytes(),count,center,bb,inner,outer,int(ring.sum()),int(candidates.sum()),int(vertical.sum()),int(keepx.sum()))
