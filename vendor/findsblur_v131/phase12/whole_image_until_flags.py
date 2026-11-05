"""Independent image -> 0x01/0x03/0x04 flag buffers using EXE call sequence.

This is a partial native pipeline. The following x86 geometry/measurement
functions have NOT yet been recovered: 402B90, 4037F0, and the assembly
between 407A00 and 407B7B that chooses the measurement ring/axes.
Output flags are NOT FindsBlur measurement values. No TXT reference access.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
for directory in (ROOT, ROOT / 'phase5'):
    if str(directory) not in sys.path:sys.path.insert(0,str(directory))
from phase11.replay_407170_4077eb import replay_from_image, PrepResult
from phase5.recovered_404f10 import find_nonzero_extents_404f10, Rect as ExtentRect
from phase9.recovered_401000 import Rect
from phase12.accelerated_topology import region_component_fast,thin_fast,junction_fast
from phase7.recovered_topology import Rect as ThinRect
from phase8.recovered_overlay import overlay_bit_04_402b00,Rect as OverlayRect

@dataclass
class WholeImagePartial:
    image_path: str
    width: int
    height: int
    preprocessing: PrepResult
    stage: str
    status: str
    flags: bytes|None
    region: object|None
    thinning_cycles: int|None
    metadata: dict

def analyze_to_flags(path:str|Path,*,halt_after='flags',diagnostics_directory:Path|None=None)->WholeImagePartial:
    path=Path(path)
    prep=replay_from_image(path,halt_after='full',diagnostics_directory=diagnostics_directory)
    w,h=prep.width,prep.height
    r=prep.processed
    ext=find_nonzero_extents_404f10(prep.primary,stride=w,height=h,
        roi=ExtentRect(r.x0,r.y0,r.x1,r.y1),
        x_margin=prep.parameters.x_margin,y_margin=prep.parameters.y_margin)
    meta={'processed_roi':[r.x0,r.y0,r.x1,r.y1],
          'detected':[ext.detected.x0,ext.detected.y0,ext.detected.x1,ext.detected.y1],
          'adjusted':([ext.adjusted.x0,ext.adjusted.y0,ext.adjusted.x1,ext.adjusted.y1] if ext.adjusted else None),
          'params':prep.parameters.__dict__}
    if ext.status!=0 or not ext.adjusted:
        return WholeImagePartial(str(path),w,h,prep,'extents','failure',None,None,None,meta)
    outer=Rect(ext.detected.x0,ext.detected.y0,ext.detected.x1,ext.detected.y1)
    inner=Rect(ext.adjusted.x0,ext.adjusted.y0,ext.adjusted.x1,ext.adjusted.y1)
    c4=bytearray(prep.primary)
    c0=bytearray(w*h);bc=bytearray(w*h)
    region=region_component_fast(c4,c0,bc,stride=w,height=h,outer=outer,inner=inner)
    c4[:]=c0[:]
    if diagnostics_directory:
        from PIL import Image
        Image.frombytes('L',(w,h),bytes(c0)).save(diagnostics_directory/'16-region-401000.png')
    if halt_after=='region':
        return WholeImagePartial(str(path),w,h,prep,'region','partial',bytes(c4),region,None,meta)
    tail_roi=ThinRect(r.x0+1,r.y0+1,r.x1-1,r.y1-1)
    # Native caller copies C4 into C0, and C0 is the thin/branch workspace.
    fine,cycles=thin_fast(c0,stride=w,height=h,roi=tail_roi)
    junctions=junction_fast(fine,stride=w,height=h,roi=tail_roi)
    # Important: overlay_bit_04_402b00 writes into its FIRST argument.
    # Classified 0x01/0x03 junction labels must remain in the destination;
    # region mask C4 (0x00/0xff) supplies bit 0x04, not vice versa.
    # Reversing these operands labels EVERY 0xff region pixel as a false
    # 0x02 junction, saturating both 100-entry projection candidate tables.
    work_flags=overlay_bit_04_402b00(bytearray(junctions),c4,stride=w,height=h,
       roi=OverlayRect(tail_roi.x0,tail_roi.y0,tail_roi.x1,tail_roi.y1))
    meta.update({'region_accepted_components':region.accepted_components,
                 'region_rejected_components':region.rejected_components,
                 'region_accepted_pixels':region.accepted_pixels,
                 'thinning_cycles':cycles,
                 'flags_nonzero':int(np.count_nonzero(np.frombuffer(work_flags,np.uint8))),
                 'skeleton_pixels':int(np.count_nonzero(np.frombuffer(junctions,np.uint8))),
                 'flag04_count':int(np.count_nonzero(np.frombuffer(work_flags,np.uint8)&4)),
                 'junction03_count':int(np.count_nonzero(np.frombuffer(junctions,np.uint8)==3))})
    if diagnostics_directory:
        from PIL import Image
        Image.frombytes('L',(w,h),bytes(junctions)).save(diagnostics_directory/'17-junctions-402910.png')
        Image.frombytes('L',(w,h),bytes(work_flags)).save(diagnostics_directory/'18-flags-402b00.png')
    return WholeImagePartial(str(path),w,h,prep,'flags','partial',bytes(work_flags),region,cycles,meta)
