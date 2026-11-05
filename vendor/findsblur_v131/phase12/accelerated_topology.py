"""Speed-only transformations of already instruction-recovered native logic.

No algorithmic heuristic or reference TXT reads. Original scalar functions remain
available, and every accelerated entrypoint is compared against them on small
binary arrays. Optimized region path applies only to source 0/255 masks, with
outer and inner rectangular parameters satisfying original safety conditions.
"""
from __future__ import annotations
import numpy as np
from scipy import ndimage
from numba import njit
from phase9.recovered_401000 import Rect, RegionTrace, ComponentTrace, process_region_401000, MAX_NATIVE_ROUNDS
from phase7.recovered_topology import Rect as Rect7, thin_402430, mark_junctions_402910, THIN_TEMPLATES, PASS_ORDERS, NEIGHBORS, FORK_TRIPLES, CORNER_TRIPLES
from phase8.recovered_overlay import Rect as Rect8, overlay_bit_04_402b00

_N8 = np.ones((3,3),dtype=np.uint8)


def region_component_fast(source: bytes|bytearray,output_a:bytearray,work_b:bytearray,*,stride:int,height:int,outer:Rect,inner:Rect)->RegionTrace:
    """Region component labeling equivalent to exhaustive eight-neighbor propagation.

    The EXE processing order selects components from the TOP edge first and
    then the LEFT edge; accepted components require both opposite INNER
    edges in either axis. The component spans are connectivity facts, not
    fitted parameters. Metadata propagation_rounds=-1 flags unknown sweep
    count (output image bytes are parity-tested, not instruction count).
    """
    if (len(source)!=stride*height or len(output_a)!=stride*height or len(work_b)!=stride*height
        or not (1<=outer.left<outer.right<=stride-2 and 1<=outer.top<outer.bottom<=height-2)
        or not (outer.left<=inner.left<=inner.right<=outer.right and outer.top<=inner.top<=inner.bottom<=outer.bottom)
        or source is output_a or source is work_b or output_a is work_b):
        raise ValueError('invalid native region arguments')
    s=np.frombuffer(source,dtype=np.uint8).reshape(height,stride)
    if not np.all((s==0)|(s==255)):
        return process_region_401000(source,output_a,work_b,stride=stride,height=height,outer=outer,inner=inner)
    sub=s[outer.top:outer.bottom+1,outer.left:outer.right+1]
    lab,n=ndimage.label(sub!=0,structure=_N8)
    out=np.zeros((height,stride),dtype=np.uint8)
    sx0,sx1=inner.left-outer.left,inner.right-outer.left
    sy0,sy1=inner.top-outer.top,inner.bottom-outer.top
    active=set()
    traces=[]
    for axis,starts in [('x',lab[0,:]),('y',lab[:,0])]:
        # must emulate first unread seed within scanning edge; 10k components cap
        for coord,label in enumerate(starts):
            k=int(label)
            if k<=0 or k in active:continue
            if sum(t.seed_axis==axis for t in traces)>=MAX_NATIVE_ROUNDS:break
            component=lab==k
            if axis=='x':
                yy=outer.top;xx=outer.left+coord
                run=0
                while xx+run<=outer.right and lab[0,xx+run-outer.left]==k:
                    run+=1
            else:
                xx=outer.left;yy=outer.top+coord
                run=0
                while yy+run<=outer.bottom and lab[yy+run-outer.top,0]==k:
                    run+=1
            hit_top=bool(component[sy0,sx0:sx1+1].any())
            hit_bot=bool(component[sy1,sx0:sx1+1].any())
            hit_left=bool(component[sy0:sy1+1,sx0].any())
            hit_right=bool(component[sy0:sy1+1,sx1].any())
            keep=(hit_top and hit_bot) or (hit_left and hit_right)
            out[outer.top:outer.bottom+1,outer.left:outer.right+1][component]=255 if keep else 0
            # Original used 0x80 to prevent reseeding rejected components, so mark as active.
            active.add(k)
            traces.append(ComponentTrace(axis,xx,yy,run,-1,int(component.sum())-run,int(component.sum()),keep))
    output_a[:]=out.tobytes()
    work_b[:]=b'\x00'*(stride*height)
    return RegionTrace(tuple(traces),sum(t.kept for t in traces),sum(not t.kept for t in traces),int(np.count_nonzero(out)),sum(t.marked_pixels for t in traces if not t.kept),sum(t.seed_axis=='x' for t in traces),sum(t.seed_axis=='y' for t in traces))

_TEMPLATES=np.empty((4,3,6),np.int64)
for i,p in enumerate(THIN_TEMPLATES):
    for j,(z,o) in enumerate(p):_TEMPLATES[i,j,:3]=z;_TEMPLATES[i,j,3:]=o
_DELTAS=np.array(NEIGHBORS,dtype=np.int64)
_FORK=np.array(FORK_TRIPLES,dtype=np.int64)
_CORNERS=np.array(CORNER_TRIPLES,dtype=np.int64)

@njit(cache=True)
def _thin_mask_njit(mask,w,h,x0,y0,x1,y1,templates,deltas):
    off=np.empty(8,np.int64)
    for k in range(8):off[k]=deltas[k,0]+w*deltas[k,1]
    cycles=0
    while True:
        cycles+=1
        changed=0
        for phase in range(4):
            yf=phase in (0,2)
            xf=phase in (0,3)
            for yi in range(y1-y0+1):
                y=y0+yi if yf else y1-yi
                for xi in range(x1-x0+1):
                    x=x0+xi if xf else x1-xi
                    i=y*w+x
                    if mask[i]==0:continue
                    for t in range(3):
                        zero=True;one=True
                        for k in range(3):
                            if mask[i+off[templates[phase,t,k]]]!=0:zero=False
                            if mask[i+off[templates[phase,t,k+3]]]==0:one=False
                        if zero and one:
                            mask[i]=1
                            break
            for y in range(y0,y1+1):
                for x in range(x0,x1+1):
                    i=y*w+x
                    if mask[i]==1:
                        mask[i]=0
                        changed+=1
        if changed==0:return mask,cycles

@njit(cache=True)
def _junction_njit(mask,w,h,x0,y0,x1,y1,deltas,fork,corners):
    off=np.empty(8,np.int64)
    for k in range(8):off[k]=deltas[k,0]+w*deltas[k,1]
    for y in range(y0,y1+1):
        for x in range(x0,x1+1):
            i=y*w+x
            if mask[i]==0:continue
            a=np.zeros(8,np.uint8)
            for k in range(8):a[k]=mask[i+off[k]]!=0
            score=0
            for j in range(4):
                p,q,r=fork[j]
                if a[p] and not (a[q] and a[r]):score+=1
            corner=False
            for j in range(4):
                p,q,r=corners[j]
                if a[p] and a[q] and a[r]:corner=True
            mask[i]=3 if score>=3 or corner else 1
    return mask


def thin_fast(source:bytes|bytearray,*,stride:int,height:int,roi:Rect7):
    if not (1<=roi.x0<=roi.x1<stride-1 and 1<=roi.y0<=roi.y1<height-1):
        raise ValueError('invalid inset ROI')
    result=np.frombuffer(bytes(source),dtype=np.uint8).copy()
    if not np.all((result==0)|(result==255)):
        raise ValueError('native thinning requires binary input')
    out,cycles=_thin_mask_njit(result,stride,height,roi.x0,roi.y0,roi.x1,roi.y1,_TEMPLATES,_DELTAS)
    return bytearray(out.tobytes()),int(cycles)

def junction_fast(source:bytes|bytearray,*,stride:int,height:int,roi:Rect7):
    arr=np.frombuffer(bytes(source),dtype=np.uint8).copy()
    out=_junction_njit(arr,stride,height,roi.x0,roi.y0,roi.x1,roi.y1,_DELTAS,_FORK,_CORNERS)
    return bytearray(out.tobytes())
