"""Reconstruction of x86 0x403E30 *numeric stage* from official EXE bytes.

THE OFFICIAL REFERENCE TXT IS NEVER READ. This module assumes a byte-per-pixel
mask already annotated by upstream measurement function 0x402B90 / 0x4037F0.

0x403FA4-0x404088: bit 0x28 -> scan 0x04 vertically per x-column.
0x4041F5-0x4042D9: bit 0x18 -> scan 0x04 horizontally per y-row.
0x4040EA-0x40414B, 0x404304-0x40433B: each populated line rounds
    (sample_width_sum/sample_count + 0.5) with the CRT's _ftol routine.
0x40434F-0x404460: directional means, weighted combined mean, -2, *scale,
    then sqrt(x*x+y*y).

This translation is statically evidenced; it is NOT a substitute for native
runtime comparison of 32-bit x87 and IJG's original JPEG decode.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import sqrt
from collections.abc import Sequence
import numpy as np
from numba import njit


@dataclass(frozen=True)
class MeasuredWidths:
    values: tuple[float,float,float,float]
    x_row_valid_count: int
    y_col_valid_count: int
    x_raw_samples: int
    y_raw_samples: int
    x_raw_width_sum: int
    y_raw_width_sum: int
    x_line_rounded_sum: int
    y_line_rounded_sum: int
    x_rejected_boundary: int
    y_rejected_boundary: int
    x_over_limit: int
    y_over_limit: int
    debug_width_image: bytes|None = None


@njit(cache=False)
def _samples_native(flags: np.ndarray, w:int,h:int,x0:int,y0:int,x1:int,y1:int,limit:int):
    """Two native scan passes, using strict endpoint checks on the run ends."""
    counts_col=np.zeros(w,np.int64)
    sums_col=np.zeros(w,np.int64)
    counts_row=np.zeros(h,np.int64)
    sums_row=np.zeros(h,np.int64)
    debug=np.zeros((h,w),np.uint8)
    reject_up=0;reject_down=0;over_up=0;over_down=0
    for y in range(y0,y1+1):
        for x in range(x0,x1+1):
            pix=flags[y,x]
            if (pix & 0x28) != 0x28:continue
            up=0; yy=y;last_y=y
            while yy>=y0 and (flags[yy,x] & 4)!=0:
                up+=1;last_y=yy;yy-=1
            if last_y==y0:
                reject_up+=1;continue
            down=0; yy=y+1;last_y=yy
            while yy<=y1 and (flags[yy,x]&4)!=0:
                down+=1;last_y=yy;yy+=1
            if last_y==y1:
                reject_up+=1;continue
            size=up+down
            if size>limit:
                size=0;over_up+=1
            counts_col[x]+=1;sums_col[x]+=size
            debug[y,x]=255 if size>=256 else size
    for y in range(y0,y1+1):
        for x in range(x0,x1+1):
            pix=flags[y,x]
            if (pix & 0x18) != 0x18:continue
            left=0;xx=x;last_x=x
            while xx>=x0 and (flags[y,xx]&4)!=0:
                left+=1;last_x=xx;xx-=1
            if last_x==x0:
                reject_down+=1;continue
            right=0;xx=x+1;last_x=xx
            while xx<=x1 and (flags[y,xx]&4)!=0:
                right+=1;last_x=xx;xx+=1
            if last_x==x1:
                reject_down+=1;continue
            size=left+right
            if size>limit:
                size=0;over_down+=1
            counts_row[y]+=1;sums_row[y]+=size
            debug[y,x]=255 if size>=256 else size
    return counts_row,sums_row,counts_col,sums_col,debug,reject_down,reject_up,over_down,over_up


def measure_403e30(flags:Sequence[int],*,width:int,height:int,roi:tuple[int,int,int,int],
                   max_width:int,scale:float=1.25, save_debug:bool=False)->MeasuredWidths:
    """Compute four actual numeric columns from an already-classified flag mask.

    Does not accept reference values nor access filenames/TXT. `max_width` is
    caller [esi+0x848]; native 0x403E87 adds 2. `roi` inclusive (x0,y0,x1,y1).
    """
    x0,y0,x1,y1=roi
    if not (width>2 and height>2 and 0<=x0<=x1<width and 0<=y0<=y1<height):
        raise ValueError('Native scan ROI is out of bounds')
    if len(flags)!=width*height:raise ValueError('Flat byte image length mismatch')
    if max_width<0 or not np.isfinite(scale):raise ValueError('Invalid EXE parameters')
    buf=np.frombuffer(bytes(flags),np.uint8).reshape(height,width)
    nc,sc,np_,sp,dbg,rejx,rejy,overx,overy=_samples_native(buf,width,height,x0,y0,x1,y1,max_width+2)
    def native_reduce(counts:np.ndarray,sums:np.ndarray)->tuple[int,int]:
        reps=[int(s) if c==1 else int(float(s)/int(c)+.5) for c,s in zip(counts,sums) if c]
        return sum(reps),len(reps)
    sx,nx=native_reduce(nc,sc)
    sy,ny=native_reduce(np_,sp)
    rawx=float(sx)/nx if nx else 0.0
    rawy=float(sy)/ny if ny else 0.0
    rawc=float(sx+sy)/(nx+ny) if nx+ny else 0.0
    xx=max(0.0,rawx-2.0)*scale
    yy=max(0.0,rawy-2.0)*scale
    zz=max(0.0,rawc-2.0)*scale
    return MeasuredWidths((xx,yy,zz,sqrt(xx*xx+yy*yy)),nx,ny,
        int(nc.sum()),int(np_.sum()),int(sc.sum()),int(sp.sum()),sx,sy,
        rejx,rejy,overx,overy,dbg.tobytes() if save_debug else None)
