"""Order-preserving Numba execution of the direct 0x4050D0 byte translation.

This is a speed-only port of phase5.recovered_4050d0.transform_4050d0.
Each propagation and deletion writes immediately in ascending native scan order.
It does NOT substitute general OpenCV morphology or tuned thresholds.
"""
from __future__ import annotations
import numpy as np
from numba import njit
from phase5.recovered_4050d0 import Rect,Trace,transform_4050d0 as scalar_4050d0

@njit(cache=True)
def _run_native_4050d0(src,w,h,x0,y0,x1,y1,limit,mode):
    buf=src.copy()
    nbs=np.empty(8,np.int64)
    nbs[0]=-w-1;nbs[1]=-w;nbs[2]=-w+1;nbs[3]=-1
    nbs[4]=1;nbs[5]=w-1;nbs[6]=w;nbs[7]=w+1
    one=mode!=0
    center_label=0 if one else 255
    neighbor_label=255 if one else 0
    new_label=1 if one else 254
    step=1 if one else -1
    completed=0
    while True:
        wrote=0
        for y in range(y0+1,y1):
            for x in range(x0+1,x1):
                at=y*w+x
                if buf[at]!=center_label:continue
                for k in range(8):
                    neighbor=at+nbs[k]
                    if buf[neighbor]==neighbor_label:
                        buf[neighbor]=new_label
                        wrote+=1
        completed+=1
        if completed>=limit or wrote==0:
            if wrote==0:completed-=1
            break
        center_label=new_label
        candidate=new_label+step
        if one:
            if candidate<=254:
                new_label=candidate
            else:
                new_label=1
                center_label=254
        else:
            if candidate>=1:
                new_label=candidate
            else:
                new_label=254
                center_label=1
    if one:
        for layer in range(1,completed+1):
            for sweep in range(10):
                erased=0
                for y in range(y0+1,y1):
                    for x in range(x0+1,x1):
                        i=y*w+x
                        if buf[i]!=layer:continue
                        nw=1 if buf[i-w-1]!=0 else 0
                        n=1 if buf[i-w]!=0 else 0
                        ne=1 if buf[i-w+1]!=0 else 0
                        w0=1 if buf[i-1]!=0 else 0
                        e=1 if buf[i+1]!=0 else 0
                        sw=1 if buf[i+w-1]!=0 else 0
                        s=1 if buf[i+w]!=0 else 0
                        se=1 if buf[i+w+1]!=0 else 0
                        count=(s*(1-se*e)+w0*(1-sw*s)+n*(1-nw*w0)+e*(1-ne*n))
                        if count==1:
                            buf[i]=0
                            erased+=1
                if erased==0:break
        for y in range(y0+1,y1):
            for x in range(x0+1,x1):
                i=y*w+x
                if buf[i]!=0:buf[i]=255
    for y in range(y0,y1+1):
        for x in range(x0,x1+1):
            i=y*w+x
            if one:
                if buf[i]!=255:buf[i]=0
            elif buf[i]!=0:buf[i]=255
    return buf


def transform_4050d0(source:bytes|bytearray,*,stride:int,height:int,roi:Rect,
                       propagation_limit:int,mode:int,destination:bytearray|None=None,
                       trace:Trace|None=None)->bytearray:
    if trace is not None:
        return scalar_4050d0(source,stride=stride,height=height,roi=roi,
                             propagation_limit=propagation_limit,mode=mode,
                             destination=destination,trace=trace)
    if not (stride>0 and height>0 and 0<=roi.x0<=roi.x1<stride and
            0<=roi.y0<=roi.y1<height and len(source)>=stride*height):
        raise ValueError('Invalid native image geometry')
    a=np.frombuffer(source,dtype=np.uint8,count=stride*height).copy()
    b=_run_native_4050d0(a,stride,height,roi.x0,roi.y0,roi.x1,roi.y1,propagation_limit,mode)
    if destination is not None:
        destination[:stride*height]=b.tobytes()
        return destination
    return bytearray(b.tobytes())
