from __future__ import annotations
import csv
from pathlib import Path
import cv2, numpy as np
from PIL import Image
from cipa_crop_coord.engine import DEFAULT_SEARCH_MASK,MatchSettings,Rect,center_crop,center_rect,export_coords,locate,match_crop,output_name,prepare,search_rect
from cipa_crop_coord.locales import TEXT

def _write(path,image):
    ok,data=cv2.imencode(path.suffix,image);assert ok;data.tofile(path)
def _pattern():
    rng=np.random.default_rng(42);im=rng.integers(0,256,(80,100),dtype=np.uint8);cv2.circle(im,(50,40),18,245,3);cv2.line(im,(20,10),(85,70),15,4);return im

def test_translation_keys_match():assert set(TEXT['zh'])==set(TEXT['ja'])
def test_search_mask_one_sixth():assert search_rect(1200,900,DEFAULT_SEARCH_MASK)==Rect(200,150,800,600)
def test_center_rect():assert center_rect(1200,900,ratio='1/3')==Rect(400,300,400,300)
def test_exif(tmp_path):
    p=tmp_path/'a.jpg';im=Image.new('RGB',(10,10),'red');ex=Image.Exif();ex[33434]=(1,100);im.save(p,exif=ex);assert output_name(p)=='1_100_a.jpg'
def test_match_csv_japanese_debug_threads(tmp_path):
    pat=_pattern();sample=tmp_path/'sample.png';_write(sample,cv2.cvtColor(pat,cv2.COLOR_GRAY2BGR));inp=tmp_path/'in';inp.mkdir();target=np.zeros((500,700),np.uint8);target[190:270,310:410]=pat;_write(inp/'target.png',cv2.cvtColor(target,cv2.COLOR_GRAY2BGR));prep=prepare(sample,Rect(),10);m=locate(target,prep,DEFAULT_SEARCH_MASK,180);assert (m.x,m.y)==(360,230);assert m.score>.80
    settings=MatchSettings(edge_mask=10,search_mask=DEFAULT_SEARCH_MASK,threshold=.8,coarse=180);csvp=tmp_path/'coords.csv';s=export_coords(str(sample),str(inp),str(csvp),settings,lang='ja',workers=2,debug=True);assert s.succeeded==1;rows=list(csv.reader(csvp.open(encoding='utf-8-sig')));assert rows==[['ファイル名','x座標','y座標'],['target.png','360','230']];assert (Path(s.debug_path)/'sample_center.jpg').exists();assert list(Path(s.debug_path).glob('*_point.jpg'))
def test_parallel_match_and_center_debug(tmp_path):
    pat=_pattern();sample=tmp_path/'sample.png';_write(sample,cv2.cvtColor(pat,cv2.COLOR_GRAY2BGR));inp=tmp_path/'inm';out=tmp_path/'outm';inp.mkdir()
    for i,(x,y) in enumerate(((250,160),(300,200))):
        a=np.zeros((500,700),np.uint8);a[y:y+80,x:x+100]=pat;_write(inp/f't{i}.png',cv2.cvtColor(a,cv2.COLOR_GRAY2BGR))
    s=match_crop(str(sample),str(inp),str(out),MatchSettings(threshold=.7,coarse=180),workers=2,debug=True);assert s.succeeded==2;assert len(list(Path(s.debug_path).glob('[0-9]*_binary.jpg')))==2;assert len(list(Path(s.debug_path).glob('*_masked.jpg')))==2
    ci=tmp_path/'inc';co=tmp_path/'outc';ci.mkdir()
    for i in range(3):_write(ci/f'{i}.png',np.full((120,160,3),50+i*20,np.uint8))
    c=center_crop(str(ci),str(co),width=80,height=60,workers=2,debug=True);assert c.succeeded==3;assert len(list(Path(c.debug_path).glob('*_crop_rect.jpg')))==3
