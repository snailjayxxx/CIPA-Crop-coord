"""Instruction-sourced 407170..4077EB caller replay, experiment only.

Sources: original EXE function calls at VA 4071D7,407212,4072C6,40730E,
4073CC,4073FA,407430,407458,40750C,407538,40756E,407596,4075CD,
407636,407695,4076D1,4076FF,407739,407773,4077AF,4077EB.

The decoder (Pillow) is NOT IJG8c byte-parity-validated. This is a live
candidate based on native helper functions, NOT a validated implementation.
It never reads official TXT reference values.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from time import perf_counter
import sys
import numpy as np
import cv2
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from phase11.native_parameters import from_dimensions, NativeParameters
from phase3.mask_stage import normalize_histogram_404d00, gamma_lut_404670
from phase11.accelerated_4050d0 import transform_4050d0, Rect
from phase11.optimized_native_regions import retain_border_connected_fast as retain_border_connected_401bf0, process_enclosed_fast as process_enclosed_zeros_401ef0

@dataclass
class PrepResult:
    primary: bytes
    width: int
    height: int
    initial: Rect
    processed: Rect
    parameters: NativeParameters
    timings: dict
    stats: dict


def _roi_inset(roi:Rect,r:int)->Rect:
    return Rect(roi.x0+r,roi.y0+r,roi.x1-r,roi.y1-r)


def _assert_valid(roi:Rect,w:int,h:int,r:int=0)->None:
    if not (r<=roi.x0<=roi.x1<w-r and r<=roi.y0<=roi.y1<h-r):
        raise ValueError(f'unsafe native ROI {roi} with radius={r} for {w}x{h}')


def _filter_native_cv2(src:bytes | bytearray, w:int,h:int,roi:Rect,r:int,kind:str)->bytearray:
    """Array implementation of exact EXE histogram-window operation.

    Verified against phase4/native_filters.py (scalar) over safe random ROI.
    Fast path is permitted only because the source neighborhood is contained
    in the image and the selected statistic is identical for 8-bit pixels.
    Outside native destination ROI always initialized FF.
    """
    _assert_valid(roi,w,h,r)
    arr=np.frombuffer(src,dtype=np.uint8,count=w*h).reshape(h,w)
    k=2*r+1
    if kind=='median':
        if k==1: intermediate=arr
        else: intermediate=cv2.medianBlur(arr,k)
    elif kind=='max':
        intermediate=cv2.dilate(arr,np.ones((k,k),np.uint8))
    elif kind=='min':
        intermediate=cv2.erode(arr,np.ones((k,k),np.uint8))
    else:raise ValueError(kind)
    dest=np.full((h,w),255,dtype=np.uint8)
    dest[roi.y0:roi.y1+1,roi.x0:roi.x1+1]=intermediate[roi.y0:roi.y1+1,roi.x0:roi.x1+1]
    return bytearray(dest.tobytes())


def _absdiff_native(first:bytes | bytearray,second:bytes|bytearray,w:int,h:int,roi:Rect)->bytearray:
    _assert_valid(roi,w,h)
    a=np.frombuffer(first,dtype=np.uint8,count=w*h).reshape(h,w)
    b=np.frombuffer(second,dtype=np.uint8,count=w*h).reshape(h,w)
    out=np.zeros((h,w),dtype=np.uint8)
    out[roi.y0:roi.y1+1,roi.x0:roi.x1+1] = cv2.absdiff(a,b)[roi.y0:roi.y1+1,roi.x0:roi.x1+1]
    return bytearray(out.tobytes())


def _threshold_native(src: bytes|bytearray,w:int,h:int,roi:Rect,t:int)->bytearray:
    _assert_valid(roi,w,h)
    a=np.frombuffer(src,dtype=np.uint8,count=w*h).reshape(h,w)
    output=a.copy()
    output[roi.y0:roi.y1+1,roi.x0:roi.x1+1] = (a[roi.y0:roi.y1+1,roi.x0:roi.x1+1]>t)*np.uint8(255)
    return bytearray(output.tobytes())


def _combine_native_inplace(a:bytes|bytearray,b:bytes|bytearray,w:int,h:int,roi:Rect)->bytearray:
    _assert_valid(roi,w,h)
    first=np.frombuffer(a,dtype=np.uint8,count=w*h).reshape(h,w)
    second=np.frombuffer(b,dtype=np.uint8,count=w*h).reshape(h,w)
    out=second.copy()
    aa=first[roi.y0:roi.y1+1,roi.x0:roi.x1+1].astype(np.uint32)
    bb=second[roi.y0:roi.y1+1,roi.x0:roi.x1+1].astype(np.uint32)
    out[roi.y0:roi.y1+1,roi.x0:roi.x1+1]=((aa*bb+127)//255).astype(np.uint8)
    return bytearray(out.tobytes())


def replay_from_image(image_path:str|Path, *, halt_after:str='full', diagnostics_directory:Path|None=None,
                      on_stage=None)->PrepResult:
    """Native caller sequence, preserving per-buffer writes with diagnostics.

    The returned `primary` is C4 at 4077EB, before bbox / region selection.
    Choices unsupported by original direct evidence (IJG decoding byte
    equivalence) are identified in run metadata, not concealed as 'exact'.
    """
    path=Path(image_path)
    timings:dict[str,float]={}; stats={}
    def emit(name:str,data:bytes|bytearray,w:int,h:int,roi:Rect):
        if diagnostics_directory is not None:
            diagnostics_directory.mkdir(parents=True,exist_ok=True)
            # Save raw uint8 pixels losslessly. Pillow supports CJK paths on Windows,
            # while cv2.imwrite can fail on non-ASCII Windows paths.
            from PIL import Image as PILImage
            PILImage.frombytes('L',(w,h),bytes(data)).save(
                diagnostics_directory/f'{name}.png',format='PNG')
        stats[name]={'nonzero_in_roi':int(np.count_nonzero(np.frombuffer(data,dtype=np.uint8).reshape(h,w)[roi.y0:roi.y1+1,roi.x0:roi.x1+1])),
                     'roi':[roi.x0,roi.y0,roi.x1,roi.y1]}
        if on_stage:on_stage(name,stats[name])
    def timed(stage,op):
        tick=perf_counter()
        try:return op()
        finally:timings[stage]=round(perf_counter()-tick,5)
    # Decoder is an explicitly unverified compatibility boundary.
    with Image.open(path) as im:
        if im.format not in ('JPEG','BMP'):
            raise ValueError('official executable accepts JPG/BMP only')
        rgb=np.asarray(im.convert('RGB'),dtype=np.uint8).copy()
    h,w=rgb.shape[:2]
    if diagnostics_directory is not None:
        # Stage 00 is a reference, not a processing step: identical RGB pixels
        # used by the calculation (IJG 8c on JPEG). Never recompress the input.
        from PIL import Image as PILImage
        diagnostics_directory.mkdir(parents=True,exist_ok=True)
        PILImage.fromarray(rgb,'RGB').save(
            diagnostics_directory/'00-input-RGB.png',format='PNG')
    initial=Rect(0,0,w-1,h-1)
    p=from_dimensions(w,h)
    a,b,c=(rgb[...,2].astype(np.uint32),rgb[...,1].astype(np.uint32),rgb[...,0].astype(np.uint32))
    lum=((117*a+601*b+306*c)>>10).astype(np.uint8)
    # 4071D7: BGR channel buffers, disjoint grayscale C4 during decode hand-off.
    buffer_bc=bytearray(lum.tobytes())
    emit('01-luminance-404550',buffer_bc,w,h,initial)
    gamma=gamma_lut_404670(p.gamma)
    buffer_bc=bytearray(np.frombuffer(gamma,dtype=np.uint8)[np.frombuffer(buffer_bc,dtype=np.uint8)].tobytes())
    emit('02-gamma-404670',buffer_bc,w,h,initial)
    roi=_roi_inset(initial,p.median_luminance)
    buffer_c0=timed('median_luminance',lambda:_filter_native_cv2(buffer_bc,w,h,roi,p.median_luminance,'median'))
    emit('03-median-4047a0',buffer_c0,w,h,roi)
    norm=timed('normalize',lambda:normalize_histogram_404d00(buffer_c0,stride=w,height=h,rect=type('R',(),dict(x0=roi.x0,y0=roi.y0,x1=roi.x1,y1=roi.y1,empty=lambda self:False))(),low_fraction=p.low_fraction,high_fraction=p.high_fraction))
    if not norm.success:raise RuntimeError(f'0x404D00 rejected image black={norm.black_level}, white={norm.white_level}')
    stats['normalization']={'black':norm.black_level,'white':norm.white_level}
    emit('04-normalized-404d00',buffer_c0,w,h,roi)
    roi=_roi_inset(roi,p.max_min_radius)
    buffer_c4=timed('max_filter',lambda:_filter_native_cv2(buffer_c0,w,h,roi,p.max_min_radius,'max'))
    buffer_bc=timed('min_filter',lambda:_filter_native_cv2(buffer_c0,w,h,roi,p.max_min_radius,'min'))
    emit('05-max-404a20',buffer_c4,w,h,roi)
    emit('06-min-404a20',buffer_bc,w,h,roi)
    buffer_bc=_absdiff_native(buffer_c0,buffer_bc,w,h,roi)
    buffer_c4=_absdiff_native(buffer_c0,buffer_c4,w,h,roi)
    emit('07-difference-black-405550',buffer_bc,w,h,roi)
    emit('08-difference-white-405550',buffer_c4,w,h,roi)
    roi=_roi_inset(roi,p.median_difference)
    buffer_c0=timed('median_diff_a',lambda:_filter_native_cv2(buffer_bc,w,h,roi,p.median_difference,'median'))
    buffer_bc=timed('median_diff_b',lambda:_filter_native_cv2(buffer_c4,w,h,roi,p.median_difference,'median'))
    buffer_bc=_threshold_native(buffer_bc,w,h,roi,p.threshold_first)
    buffer_c0=_threshold_native(buffer_c0,w,h,roi,p.threshold_second)
    emit('09-threshold-BC-405750',buffer_bc,w,h,roi)
    emit('10-threshold-C0-405750',buffer_c0,w,h,roi)
    if halt_after=='threshold':return PrepResult(bytes(buffer_c0),w,h,initial,roi,p,timings,stats)
    # 4075CD..407670: buffer C4 is scratch; each result copied back.
    buffer_c4=timed('propagate_first',lambda:transform_4050d0(buffer_bc,stride=w,height=h,roi=roi,propagation_limit=1,mode=0))
    buffer_bc=bytearray(buffer_c4)
    buffer_c4=timed('propagate_second',lambda:transform_4050d0(buffer_c0,stride=w,height=h,roi=roi,propagation_limit=1,mode=0))
    buffer_c0=bytearray(buffer_c4)
    buffer_c0=_combine_native_inplace(buffer_bc,buffer_c0,w,h,roi)
    emit('11-combine-405550',buffer_c0,w,h,roi)
    buffer_c4=timed('repair_first',lambda:transform_4050d0(buffer_c0,stride=w,height=h,roi=roi,propagation_limit=p.repair_radius_second,mode=0))
    buffer_bc=timed('repair_second',lambda:transform_4050d0(buffer_c4,stride=w,height=h,roi=roi,propagation_limit=p.repair_radius_second,mode=1))
    emit('12-repair-4050d0',buffer_bc,w,h,roi)
    if halt_after=='repair':return PrepResult(bytes(buffer_bc),w,h,initial,roi,p,timings,stats)
    buffer_c4=timed('border_regions_401bf0',lambda:retain_border_connected_401bf0(buffer_bc,stride=w,height=h,roi=Rect(roi.x0,roi.y0,roi.x1,roi.y1)))
    emit('13-border-401bf0',buffer_c4,w,h,roi)
    holes=timed('holes_401ef0',lambda:process_enclosed_zeros_401ef0(buffer_c4,stride=w,height=h,roi=Rect(roi.x0,roi.y0,roi.x1,roi.y1),size_threshold=p.hole_threshold))
    buffer_c4=holes.source
    stats['holes']={'component_count':len(holes.components),'source_filled_count':sum(int(v.source_filled) for v in holes.components)}
    emit('14-holes-401ef0',buffer_c4,w,h,roi)
    buffer_c0=timed('surface_mode0',lambda:transform_4050d0(buffer_c4,stride=w,height=h,roi=roi,propagation_limit=p.repair_radius_first,mode=0))
    buffer_c4=timed('surface_mode1',lambda:transform_4050d0(buffer_c0,stride=w,height=h,roi=roi,propagation_limit=p.repair_radius_first,mode=1))
    emit('15-final-segmentation-C4-4050d0',buffer_c4,w,h,roi)
    return PrepResult(bytes(buffer_c4),w,h,initial,roi,p,timings,stats)
