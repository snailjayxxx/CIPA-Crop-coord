"""Accelerated exact-equivalent connectivity *when known preconditions hold*.

The observed EXE 401BF0/401EF0 operates on binary 0/255 masks on a
proper inset ROI. We use connected-component labeling ONLY for that domain.
For nonbinary input, a ROI touching the image boundary, or more than 10000
holes, the original order-sensitive scalar reconstruction remains authoritative.

Invariants are checked with randomized comparisons to the independently
instruction-translated phase6 functions; no fitted thresholds are present.
"""
from __future__ import annotations
from scipy import ndimage
import numpy as np
from phase6.recovered_regions import Rect, Component, HoleProcessResult, retain_border_connected_401bf0, process_enclosed_zeros_401ef0, MAX_NATIVE_CYCLES

_EIGHT = np.ones((3,3),dtype=np.uint8)


def _eligible(src, stride, height, roi):
    if not (1 <= roi.x0 <= roi.x1 < stride-1 and 1 <= roi.y0 <= roi.y1 < height-1):
        return False
    arr=np.frombuffer(src,dtype=np.uint8)
    return len(arr)==stride*height and bool(np.all((arr==0)|(arr==255)))


def _boundary(mask):
    edges=np.zeros(mask.shape,dtype=bool)
    edges[0,:]=True;edges[-1,:]=True;edges[:,0]=True;edges[:,-1]=True
    return mask & edges


def retain_border_connected_fast(source,*,stride,height,roi:Rect,destination=None):
    if not _eligible(source,stride,height,roi):
        return retain_border_connected_401bf0(source,stride=stride,height=height,roi=roi,destination=destination)
    output=np.zeros((height,stride),dtype=np.uint8)
    sub=np.frombuffer(source,dtype=np.uint8).reshape(height,stride)[roi.y0:roi.y1+1,roi.x0:roi.x1+1]
    labels,count=ndimage.label(sub!=0,structure=_EIGHT)
    if count:
        boundary_labels=np.unique(labels[_boundary(sub!=0)])
        boundary_labels=boundary_labels[boundary_labels!=0]
        output[roi.y0:roi.y1+1,roi.x0:roi.x1+1]=np.isin(labels,boundary_labels).astype(np.uint8)*255
    raw=output.tobytes()
    if destination is not None:
        if source is destination:raise ValueError('source and destination must not alias')
        destination[:]=raw
        return destination
    return bytearray(raw)


def process_enclosed_fast(source,*,stride,height,roi:Rect,size_threshold:int,destination=None):
    if not _eligible(source,stride,height,roi):
        return process_enclosed_zeros_401ef0(source,stride=stride,height=height,roi=roi,size_threshold=size_threshold,destination=destination)
    original=np.frombuffer(source,dtype=np.uint8).reshape(height,stride)
    output=original.copy()
    aux=np.where(original!=0,255,0).astype(np.uint8)
    sub=original[roi.y0:roi.y1+1,roi.x0:roi.x1+1]
    zero_labels,count=ndimage.label(sub==0,structure=_EIGHT)
    if count==0:
        raw=aux.tobytes();dest=destination if destination is not None else bytearray(raw)
        if destination is not None:destination[:]=raw
        return HoleProcessResult(source if isinstance(source,bytearray) else bytearray(source),dest,tuple(),1)
    # Outer zero-components touching the ROI boundary are marked 255 in the native auxiliary.
    boundary_components=np.unique(zero_labels[_boundary(sub==0)])
    boundary_components=boundary_components[boundary_components!=0]
    outside=np.isin(zero_labels,boundary_components)
    sub_aux=aux[roi.y0:roi.y1+1,roi.x0:roi.x1+1]
    sub_aux[outside]=255
    eligible=[k for k in range(1,count+1) if k not in set(boundary_components.tolist())]
    # Original walks row-major by first zero pixel; connected-components labels do too.
    if len(eligible)>MAX_NATIVE_CYCLES:
        return process_enclosed_zeros_401ef0(source,stride=stride,height=height,roi=roi,size_threshold=size_threshold,destination=destination)
    objects=ndimage.find_objects(zero_labels)
    found=[]
    for k in eligible:
        slices=objects[k-1]
        ys,xs=slices
        bounds=Rect(roi.x0+xs.start,roi.y0+ys.start,roi.x0+xs.stop-1,roi.y0+ys.stop-1)
        spanx=bounds.x1-bounds.x0;spany=bounds.y1-bounds.y0
        filled=spanx<size_threshold or spany<size_threshold
        mask=(zero_labels[slices]==k)
        if filled:
            output[roi.y0+ys.start:roi.y0+ys.stop,roi.x0+xs.start:roi.x0+xs.stop][mask]=255
            # Native sets 128 then rewrites as zero in auxiliary
            sub_aux[ys,xs][mask]=0
        else:
            sub_aux[ys,xs][mask]=255
        found.append(Component(bounds,spanx,spany,filled,int(mask.sum()),-1))
    src_raw=output.tobytes()
    if isinstance(source,bytearray):source[:]=src_raw; src=source
    else:src=bytearray(src_raw)
    raw=aux.tobytes()
    if destination is not None:
        if source is destination:raise ValueError('buffers alias')
        destination[:]=raw;dest=destination
    else:dest=bytearray(raw)
    return HoleProcessResult(src,dest,tuple(found),-1)
