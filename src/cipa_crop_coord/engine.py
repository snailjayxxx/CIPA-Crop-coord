from __future__ import annotations

import csv, math, os, re, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from PIL import Image
from .locales import tr

EXT={".jpg",".jpeg",".png",".bmp",".tif",".tiff",".webp"}
DEFAULT_SEARCH_MASK=100/6
DEFAULT_THRESHOLD=-1.0
DEFAULT_WORKERS=2

class Cancelled(RuntimeError): pass

@dataclass(frozen=True)
class Rect:
    x:int=0; y:int=0; width:int=0; height:int=0
    def resolved(self,w:int,h:int,lang="zh"):
        x=max(0,min(self.x,w)); y=max(0,min(self.y,h))
        rw=self.width if self.width>0 else w-x; rh=self.height if self.height>0 else h-y
        rw=max(0,min(rw,w-x)); rh=max(0,min(rh,h-y))
        if rw<=0 or rh<=0: raise ValueError(tr(lang,"range_out"))
        return Rect(x,y,rw,rh)

@dataclass(frozen=True)
class MatchSettings:
    template_rect:Rect=Rect(); edge_mask:float=10.0; search_mask:float=DEFAULT_SEARCH_MASK; threshold:float=DEFAULT_THRESHOLD; coarse:int=1800
@dataclass(frozen=True)
class Prepared:
    inner:np.ndarray; full_w:int; full_h:int; mx:int; my:int; binary:np.ndarray
@dataclass(frozen=True)
class Match:
    x:int; y:int; score:float; crop:Rect; search:Rect
@dataclass
class Summary:
    total:int=0; succeeded:int=0; failed:int=0; skipped:int=0; output_path:str=""; debug_path:str=""


def images(folder,exclude:Iterable=(),lang="zh"):
    root=Path(folder)
    if not root.is_dir(): raise ValueError(tr(lang,"folder_missing",path=root))
    ex=[]
    for p in exclude:
        try: ex.append(Path(p).resolve())
        except OSError: pass
    def excluded(p):
        try:
            r=p.resolve(); return any(r==e or r.is_relative_to(e) for e in ex)
        except OSError: return False
    return sorted((p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in EXT and not excluded(p)),key=lambda p:str(p).casefold())


def read(path,gray=False,lang="zh"):
    data=np.fromfile(Path(path),dtype=np.uint8); flag=cv2.IMREAD_GRAYSCALE if gray else cv2.IMREAD_COLOR
    image=cv2.imdecode(data,flag)
    if image is None: raise ValueError(tr(lang,"read_fail",path=path))
    return image


def write(path,image,quality=95,lang="zh"):
    p=Path(path); suffix=p.suffix.lower() if p.suffix.lower() in EXT else ".jpg"; p=p if p.suffix.lower() in EXT else p.with_suffix(suffix)
    params=[cv2.IMWRITE_JPEG_QUALITY,max(1,min(int(quality),100))] if suffix in {".jpg",".jpeg"} else []
    ok,data=cv2.imencode(suffix,image,params)
    if not ok: raise ValueError(tr(lang,"encode_fail",path=p.name))
    p.parent.mkdir(parents=True,exist_ok=True); data.tofile(p); return p


def safe(s): return re.sub(r'[<>:"/\\|?*\x00-\x1f]+',"_",str(s)).strip(" ._") or "unknown"

def shutter(path):
    try:
        import exifread
        with open(path,"rb") as f: tag=exifread.process_file(f,details=False,stop_tag="EXIF ExposureTime").get("EXIF ExposureTime")
        if tag:
            vals=getattr(tag,"values",None)
            if vals:
                v=vals[0]; num=getattr(v,"num",None); den=getattr(v,"den",None)
                if num is not None and den:
                    q=Fraction(int(num),int(den)); return safe(str(q.numerator) if q.denominator==1 else f"{q.numerator}_{q.denominator}")
            return safe(str(tag).replace("/","_").replace(" ",""))
    except Exception: pass
    try:
        with Image.open(path) as im: e=im.getexif().get(33434)
        if e is None:return "unknown"
        q=Fraction(int(e[0]),int(e[1])) if isinstance(e,tuple) else Fraction(float(e)).limit_denominator(1_000_000)
        return safe(str(q.numerator) if q.denominator==1 else f"{q.numerator}_{q.denominator}")
    except Exception:return "unknown"

def output_name(path):
    p=Path(path); return f"{shutter(p)}_{safe(p.stem)}{p.suffix.lower()}"

class Allocator:
    def __init__(self,folder): self.folder=Path(folder); self.lock=threading.Lock(); self.used=set()
    def get(self,name):
        with self.lock:
            p=self.folder/name; i=2
            while p.exists() or p in self.used: p=self.folder/f"{Path(name).stem}__{i}{Path(name).suffix}"; i+=1
            self.used.add(p); return p


def threshold(gray,template=False):
    _,b=cv2.threshold(gray,190 if template else 160,255 if template else 200,cv2.THRESH_BINARY); return b

def prepare(sample,rect:Rect,edge,lang="zh"):
    g=read(sample,True,lang); h,w=g.shape; r=rect.resolved(w,h,lang); b=threshold(g[r.y:r.y+r.height,r.x:r.x+r.width],True)
    mx=round(r.width*max(0,min(edge,45))/100); my=round(r.height*max(0,min(edge,45))/100)
    if r.width-2*mx<8 or r.height-2*my<8: raise ValueError(tr(lang,"template_small"))
    return Prepared(b[my:r.height-my,mx:r.width-mx].copy(),r.width,r.height,mx,my,b)
def search_rect(w,h,pct,lang="zh"):
    p=max(0,min(float(pct),45))/100; mx=round(w*p); my=round(h*p); return Rect(mx,my,w-2*mx,h-2*my).resolved(w,h,lang)
def best(search,tpl,lang):
    if search.shape[0]<tpl.shape[0] or search.shape[1]<tpl.shape[1]: raise ValueError(tr(lang,"search_small"))
    s=cv2.matchTemplate(search,tpl,cv2.TM_CCOEFF_NORMED); np.nan_to_num(s,copy=False,nan=-1,posinf=-1,neginf=-1); _,v,_,loc=cv2.minMaxLoc(s); return loc[0],loc[1],float(v)
def locate(gray,prep:Prepared,mask=DEFAULT_SEARCH_MASK,coarse=1800,lang="zh"):
    h,w=gray.shape; sr=search_rect(w,h,mask,lang); b=threshold(gray,False); area=b[sr.y:sr.y+sr.height,sr.x:sr.x+sr.width]; tpl=prep.inner; th,tw=tpl.shape
    if sr.width<tw or sr.height<th: raise ValueError(tr(lang,"search_small"))
    scale=min(1,max(64,int(coarse))/max(sr.width,sr.height))
    if scale<.999 and min(tw*scale,th*scale)>=12:
        a=cv2.resize(area,(round(sr.width*scale),round(sr.height*scale)),interpolation=cv2.INTER_AREA); t=cv2.resize(tpl,(round(tw*scale),round(th*scale)),interpolation=cv2.INTER_AREA)
        cx,cy,_=best(a,t,lang); ax=round(cx/scale); ay=round(cy/scale); rad=max(12,math.ceil(5/scale)); x0=max(0,ax-rad); y0=max(0,ay-rad); x1=min(sr.width,ax+tw+rad); y1=min(sr.height,ay+th+rad)
        lx,ly,score=best(area[y0:y1,x0:x1],tpl,lang); ix=sr.x+x0+lx; iy=sr.y+y0+ly
    else:
        lx,ly,score=best(area,tpl,lang); ix=sr.x+lx; iy=sr.y+ly
    x=ix-prep.mx; y=iy-prep.my; crop=Rect(x,y,prep.full_w,prep.full_h)
    if x<0 or y<0 or x+crop.width>w or y+crop.height>h: raise ValueError(tr(lang,"edge_crop"))
    return Match(x+prep.full_w//2,y+prep.full_h//2,score,crop,sr)


def debug_write(path,image):
    h,w=image.shape[:2]; s=min(1,1600/max(h,w)); out=image if s>=.999 else cv2.resize(image,(round(w*s),round(h*s)),interpolation=cv2.INTER_AREA)
    if out.ndim==2: out=cv2.cvtColor(out,cv2.COLOR_GRAY2BGR)
    ok,data=cv2.imencode(".jpg",out,[cv2.IMWRITE_JPEG_QUALITY,70])
    if ok: Path(path).parent.mkdir(parents=True,exist_ok=True); data.tofile(Path(path).with_suffix(".jpg"))
def stem(i,p): return f"{i:05d}_{safe(Path(p).stem)}"

def parallel(files,fn,workers,progress,cancel):
    results=[None]*len(files); done=0
    with ThreadPoolExecutor(max_workers=max(1,int(workers))) as ex:
        fut={ex.submit(fn,i,p):(i,p) for i,p in enumerate(files)}
        for f in as_completed(fut):
            if cancel and cancel():
                for x in fut:x.cancel()
                raise Cancelled()
            i,msg,payload=f.result(); results[i]=payload; done+=1
            if progress:progress(done,len(files),msg)
    return results

def _count(summary,results):
    for r in results:
        if not r:continue
        if r[0]=="ok":summary.succeeded+=1
        elif r[0]=="skip":summary.skipped+=1
        else:summary.failed+=1


def match_crop(sample,input_folder,output_folder,settings:MatchSettings,quality=95,progress=None,cancel=None,lang="zh",workers=DEFAULT_WORKERS,debug=False):
    dbg=Path(output_folder)/"_debug_match_crop"; fs=images(input_folder,[output_folder,dbg],lang); prep=prepare(sample,settings.template_rect,settings.edge_mask,lang); Path(output_folder).mkdir(parents=True,exist_ok=True); alloc=Allocator(output_folder); s=Summary(len(fs),output_path=str(output_folder),debug_path=str(dbg) if debug else "")
    if debug:debug_write(dbg/"sample_binary.jpg",prep.binary)
    def one(i,p):
        try:
            im=read(p,False,lang); g=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY); m=locate(g,prep,settings.search_mask,settings.coarse,lang)
            if debug:
                b=threshold(g); n=stem(i+1,p); debug_write(dbg/f"{n}_binary.jpg",b); masked=b.copy(); r=m.search; masked[:r.y,:]=0; masked[r.y+r.height:,:]=0; masked[r.y:r.y+r.height,:r.x]=0; masked[r.y:r.y+r.height,r.x+r.width:]=0; debug_write(dbg/f"{n}_masked.jpg",masked)
            if m.score<settings.threshold:return i,tr(lang,"skip",score=m.score,name=p.name),("skip",None)
            r=m.crop; write(alloc.get(output_name(p)),im[r.y:r.y+r.height,r.x:r.x+r.width],quality,lang); return i,tr(lang,"ok_score",score=m.score,name=p.name),("ok",None)
        except Exception as e:return i,tr(lang,"fail",name=p.name,error=e),("fail",None)
    rs=parallel(fs,one,workers,progress,cancel); _count(s,rs); return s


def parse_ratio(v,lang):
    try:q=float(Fraction(str(v).strip()))
    except Exception as e:raise ValueError(tr(lang,"ratio_format")) from e
    if not 0<q<=1:raise ValueError(tr(lang,"ratio_range"))
    return q
def center_rect(w,h,width=0,height=0,ratio=None,lang="zh"):
    if ratio is not None:q=parse_ratio(ratio,lang); cw=max(1,round(w*q)); ch=max(1,round(h*q))
    else:
        cw=int(width);ch=int(height)
        if cw<=0 or ch<=0:raise ValueError(tr(lang,"fixed_positive"))
        if cw>w or ch>h:raise ValueError(tr(lang,"fixed_large"))
    return Rect((w-cw)//2,(h-ch)//2,cw,ch)
def center_crop(input_folder,output_folder,width=0,height=0,ratio=None,quality=95,progress=None,cancel=None,lang="zh",workers=DEFAULT_WORKERS,debug=False):
    dbg=Path(output_folder)/"_debug_center_crop";fs=images(input_folder,[output_folder,dbg],lang);Path(output_folder).mkdir(parents=True,exist_ok=True);alloc=Allocator(output_folder);s=Summary(len(fs),output_path=str(output_folder),debug_path=str(dbg) if debug else "")
    def one(i,p):
        try:
            im=read(p,False,lang);h,w=im.shape[:2];r=center_rect(w,h,width,height,ratio,lang);write(alloc.get(output_name(p)),im[r.y:r.y+r.height,r.x:r.x+r.width],quality,lang)
            if debug:o=im.copy();cv2.rectangle(o,(r.x,r.y),(r.x+r.width,r.y+r.height),(0,0,255),max(2,round(max(w,h)/1000)));debug_write(dbg/f"{stem(i+1,p)}_crop_rect.jpg",o)
            return i,tr(lang,"ok",name=p.name),("ok",None)
        except Exception as e:return i,tr(lang,"fail",name=p.name,error=e),("fail",None)
    rs=parallel(fs,one,workers,progress,cancel);_count(s,rs);return s


def export_coords(sample,input_folder,csv_path,settings:MatchSettings,progress=None,cancel=None,lang="zh",workers=DEFAULT_WORKERS,debug=False):
    out=Path(csv_path);dbg=out.parent/f"{out.stem}_debug";fs=images(input_folder,[dbg],lang);prep=prepare(sample,settings.template_rect,settings.edge_mask,lang);root=Path(input_folder);s=Summary(len(fs),output_path=str(out),debug_path=str(dbg) if debug else "")
    if debug:
        im=read(sample,False,lang);h,w=im.shape[:2];r=settings.template_rect.resolved(w,h,lang);c=(r.x+r.width//2,r.y+r.height//2);cv2.circle(im,c,max(8,round(max(w,h)/250)),(0,0,255),max(2,round(max(w,h)/1000)));debug_write(dbg/"sample_center.jpg",im)
    def one(i,p):
        name=p.relative_to(root).as_posix()
        try:
            im=read(p,False,lang);g=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY);m=locate(g,prep,settings.search_mask,settings.coarse,lang);ok=m.score>=settings.threshold;row=(name,m.x,m.y) if ok else (name,"","")
            if debug:rad=max(8,round(max(im.shape[:2])/250));cv2.circle(im,(m.x,m.y),rad,(0,0,255),max(2,round(max(im.shape[:2])/1000)));cv2.putText(im,f"score={m.score:.3f}",(max(5,m.x+rad),max(25,m.y)),cv2.FONT_HERSHEY_SIMPLEX,.7,(0,0,255),2,cv2.LINE_AA);debug_write(dbg/f"{stem(i+1,p)}_point.jpg",im)
            return i,tr(lang,"record" if ok else "below",score=m.score,name=name),("ok" if ok else "skip",row)
        except Exception as e:return i,tr(lang,"fail",name=name,error=e),("fail",(name,"",""))
    rs=parallel(fs,one,workers,progress,cancel);rows=[]
    for r in rs:
        if r: rows.append(r[1]); s.succeeded+=r[0]=="ok";s.skipped+=r[0]=="skip";s.failed+=r[0]=="fail"
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("w",newline="",encoding="utf-8-sig") as f:w=csv.writer(f);w.writerow(tr(lang,"csv_header"));w.writerows(rows)
    return s
