from __future__ import annotations

import os, sys, threading
from pathlib import Path
from typing import Callable
from PIL import Image
from PySide6.QtCore import QObject,QPoint,QRect,QSize,Qt,QThread,Signal,Slot
from PySide6.QtGui import QCloseEvent,QImageReader,QMouseEvent,QPixmap,QWheelEvent
from PySide6.QtWidgets import (QApplication,QButtonGroup,QCheckBox,QComboBox,QDialog,QDialogButtonBox,QDoubleSpinBox,QFileDialog,QFormLayout,QGridLayout,QGroupBox,QHBoxLayout,QLabel,QLineEdit,QMainWindow,QMessageBox,QPlainTextEdit,QProgressBar,QPushButton,QRadioButton,QScrollArea,QSizePolicy,QSpinBox,QTabWidget,QToolBar,QVBoxLayout,QWidget)
from .engine import DEFAULT_SEARCH_MASK,DEFAULT_THRESHOLD,DEFAULT_WORKERS,Cancelled,MatchSettings,Rect,center_crop,export_coords,match_crop
from .locales import tr

STYLE="""
QWidget{font-size:13px}QMainWindow{background:#f5f6f8}QGroupBox{font-weight:600;border:1px solid #d4d8df;border-radius:7px;margin-top:10px;padding:12px 8px 8px;background:white}QGroupBox::title{subcontrol-origin:margin;left:10px;padding:0 4px}
QLineEdit,QPlainTextEdit{border:1px solid #c9ced7;border-radius:5px;padding:5px;background:white}
QSpinBox,QDoubleSpinBox{border:1px solid #c9ced7;border-radius:5px;padding:4px 30px 4px 6px;min-height:26px;background:white}QSpinBox::up-button,QDoubleSpinBox::up-button{subcontrol-origin:border;subcontrol-position:top right;width:26px;border-left:1px solid #c9ced7}QSpinBox::down-button,QDoubleSpinBox::down-button{subcontrol-origin:border;subcontrol-position:bottom right;width:26px;border-left:1px solid #c9ced7}
QPushButton{border:1px solid #b8bec8;border-radius:5px;padding:6px 12px;background:white}QPushButton:hover{background:#eef3fb}QPushButton#primary{color:white;background:#1769e0;border-color:#1769e0;font-weight:600}QPushButton#primary:disabled{background:#9db9df;border-color:#9db9df}QProgressBar{border:1px solid #c9ced7;border-radius:5px;text-align:center}QProgressBar::chunk{background:#2d7be8;border-radius:4px}QTabBar::tab{padding:9px 18px;background:#e8ebf0}QTabBar::tab:selected{background:white;font-weight:600}
"""

class PathChooser(QWidget):
    def __init__(self,lang,mode,save_key=""):
        super().__init__();self.lang=lang;self.mode=mode;self.save_key=save_key;self.edit=QLineEdit();b=QPushButton(tr(lang,"browse"));b.clicked.connect(self.browse);l=QHBoxLayout(self);l.setContentsMargins(0,0,0,0);l.addWidget(self.edit,1);l.addWidget(b)
    def text(self):return self.edit.text().strip()
    def browse(self):
        cur=self.text() or str(Path.home())
        if self.mode=="folder":v=QFileDialog.getExistingDirectory(self,tr(self.lang,"folder"),cur)
        elif self.mode=="save":v,_=QFileDialog.getSaveFileName(self,tr(self.lang,"save"),cur,tr(self.lang,self.save_key))
        else:v,_=QFileDialog.getOpenFileName(self,tr(self.lang,"image"),cur,tr(self.lang,"image_filter"))
        if v:self.edit.setText(v)

class SelectLabel(QLabel):
    changed=Signal();zoom=Signal(float)
    def __init__(self,pix):
        super().__init__();self.base=pix;self.scale=1.;self.origin=QPoint();self.sel=QRect();self.drag=False;self.setCursor(Qt.CursorShape.CrossCursor);self.set_scale(1)
    def set_scale(self,s):
        self.scale=max(.05,min(float(s),8));size=QSize(max(1,round(self.base.width()*self.scale)),max(1,round(self.base.height()*self.scale)));self.setPixmap(self.base.scaled(size,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));self.setFixedSize(size);self.update()
    def base_point(self,p):return QPoint(max(0,min(round(p.x()/self.scale),self.base.width()-1)),max(0,min(round(p.y()/self.scale),self.base.height()-1)))
    def mousePressEvent(self,e:QMouseEvent):
        if e.button()==Qt.MouseButton.LeftButton:self.origin=self.base_point(e.position().toPoint());self.sel=QRect(self.origin,QSize());self.drag=True;self.update()
    def mouseMoveEvent(self,e):
        if self.drag:self.sel=QRect(self.origin,self.base_point(e.position().toPoint())).normalized();self.changed.emit();self.update()
    def mouseReleaseEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton and self.drag:self.drag=False;self.changed.emit();self.update()
    def wheelEvent(self,e:QWheelEvent):self.zoom.emit(1.2 if e.angleDelta().y()>0 else 1/1.2);e.accept()
    def paintEvent(self,e):
        super().paintEvent(e)
        if self.sel.width()>0 and self.sel.height()>0:
            from PySide6.QtGui import QColor,QPainter,QPen
            p=QPainter(self);r=QRect(round(self.sel.x()*self.scale),round(self.sel.y()*self.scale),round(self.sel.width()*self.scale),round(self.sel.height()*self.scale));p.fillRect(r,QColor(23,105,224,45));p.setPen(QPen(QColor("#1769e0"),2));p.drawRect(r)

class RegionDialog(QDialog):
    def __init__(self,lang,path,initial:Rect|None=None,parent=None,help_text=None):
        super().__init__(parent);self.lang=lang;self.setWindowTitle(tr(lang,"preview"));self.setWindowFlags(self.windowFlags()|Qt.WindowType.WindowMaximizeButtonHint);self.resize(1200,800);self.fit_mode=True;self.full=self.oriented(path)
        reader=QImageReader(path);reader.setAutoTransform(True);size=reader.size().scaled(QSize(2600,1800),Qt.AspectRatioMode.KeepAspectRatio);reader.setScaledSize(size);img=reader.read()
        if img.isNull():raise ValueError(tr(lang,"preview_fail"))
        self.label=SelectLabel(QPixmap.fromImage(img));self.label.changed.connect(self.status);self.label.zoom.connect(self.zoom_by);self.scroll=QScrollArea();self.scroll.setWidget(self.label);self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        minus=QPushButton("−");plus=QPushButton("+");fit=QPushButton(tr(lang,"fit"));minus.clicked.connect(lambda:self.zoom_by(1/1.25));plus.clicked.connect(lambda:self.zoom_by(1.25));fit.clicked.connect(self.fit);tools=QHBoxLayout();tools.addWidget(minus);tools.addWidget(plus);tools.addWidget(fit);tools.addStretch()
        self.help=QLabel(help_text or tr(lang,"preview_help"));self.help.setWordWrap(True);self.info=QLabel();buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);lay=QVBoxLayout(self);lay.addLayout(tools);lay.addWidget(self.scroll,1);lay.addWidget(self.help);lay.addWidget(self.info);lay.addWidget(buttons)
        if initial and initial.width>0 and initial.height>0:self.set_initial(initial)
        self.status()
    @staticmethod
    def oriented(path):
        with Image.open(path) as im:w,h=im.size;o=im.getexif().get(274,1)
        return (h,w) if o in {5,6,7,8} else (w,h)
    def set_initial(self,r):
        fw,fh=self.full;bw,bh=self.label.base.width(),self.label.base.height();self.label.sel=QRect(round(r.x*bw/fw),round(r.y*bh/fh),max(1,round(r.width*bw/fw)),max(1,round(r.height*bh/fh)))
    def rect(self):
        r=self.label.sel.normalized();fw,fh=self.full;bw,bh=self.label.base.width(),self.label.base.height()
        if r.width()<2 or r.height()<2:return Rect()
        x=round(r.x()*fw/bw);y=round(r.y()*fh/bh);w=max(1,round(r.width()*fw/bw));h=max(1,round(r.height()*fh/bh));return Rect(x,y,min(w,fw-x),min(h,fh-y))
    def fit(self):
        v=self.scroll.viewport().size();self.fit_mode=True;self.label.set_scale(min(max(1,v.width()-12)/self.label.base.width(),max(1,v.height()-12)/self.label.base.height()))
    def zoom_by(self,f):self.fit_mode=False;self.label.set_scale(self.label.scale*f)
    def showEvent(self,e):super().showEvent(e);self.fit()
    def resizeEvent(self,e):super().resizeEvent(e);self.fit() if self.fit_mode else None
    def status(self):
        r=self.rect();self.info.setText(tr(self.lang,"whole") if r.width<=0 else tr(self.lang,"range",x=r.x,y=r.y,w=r.width,h=r.height))

class RegionEditor(QWidget):
    def __init__(self,lang,image_getter:Callable[[],str]):
        super().__init__();self.lang=lang;self.get_image=image_getter;self.spins=[];l=QHBoxLayout(self);l.setContentsMargins(0,0,0,0)
        for key in ("x","y","w","h"):
            l.addWidget(QLabel(tr(lang,key)));s=QSpinBox();s.setRange(0,200000);s.setMinimumWidth(108);self.spins.append(s);l.addWidget(s)
        b=QPushButton(tr(lang,"pick"));b.clicked.connect(self.pick);l.addWidget(b);l.addWidget(QLabel(tr(lang,"template_hint")),1)
    def rect(self):return Rect(*(s.value() for s in self.spins))
    def pick(self):
        p=self.get_image()
        if not p:return
        try:
            cur=self.rect();d=RegionDialog(self.lang,p,cur if cur.width>0 and cur.height>0 else None,self)
            if d.exec()==QDialog.DialogCode.Accepted:
                r=d.rect()
                for s,v in zip(self.spins,(r.x,r.y,r.width,r.height)):s.setValue(v)
        except Exception as e:QMessageBox.warning(self,tr(self.lang,"preview_fail"),str(e))

class SearchMask(QWidget):
    def __init__(self,lang):
        super().__init__();self.lang=lang;self.last="";self.spin=QDoubleSpinBox();self.spin.setRange(0,45);self.spin.setDecimals(2);self.spin.setValue(DEFAULT_SEARCH_MASK);self.spin.setSuffix(" %");self.spin.setMinimumWidth(120);b=QPushButton(tr(lang,"pick"));b.clicked.connect(self.pick);l=QHBoxLayout(self);l.setContentsMargins(0,0,0,0);l.addWidget(self.spin);l.addWidget(b);l.addWidget(QLabel(tr(lang,"search_note")),1)
    def initial(self,path):
        fw,fh=RegionDialog.oriented(path);p=self.spin.value()/100;mx=round(fw*p);my=round(fh*p);return Rect(mx,my,fw-2*mx,fh-2*my)
    def pick(self):
        p,_=QFileDialog.getOpenFileName(self,tr(self.lang,"choose_target"),self.last or str(Path.home()),tr(self.lang,"image_filter_short"))
        if not p:return
        self.last=p
        try:
            d=RegionDialog(self.lang,p,self.initial(p),self,tr(self.lang,"search_help"))
            if d.exec()==QDialog.DialogCode.Accepted:
                r=d.rect();fw,fh=d.full
                if r.width>0:self.spin.setValue(max(0,min(45,(r.x/fw+(fw-r.x-r.width)/fw+r.y/fh+(fh-r.y-r.height)/fh)*25)))
        except Exception as e:QMessageBox.warning(self,tr(self.lang,"preview_fail"),str(e))

class Worker(QObject):
    progress=Signal(int,int,str);finished=Signal(object);failed=Signal(str)
    def __init__(self,fn,kw,lang):super().__init__();self.fn=fn;self.kw=kw;self.lang=lang;self.stop=threading.Event()
    @Slot()
    def run(self):
        try:self.finished.emit(self.fn(**self.kw,progress=lambda c,n,m:self.progress.emit(c,n,m),cancel=self.stop.is_set))
        except Cancelled:self.failed.emit(tr(self.lang,"cancelled"))
        except Exception as e:self.failed.emit(str(e))

class BatchTab(QWidget):
    def __init__(self,lang):
        super().__init__();self.lang=lang;self.thread=None;self.worker=None;self.content=QVBoxLayout(self);self.content.setContentsMargins(14,14,14,14);self.progress=QProgressBar();self.progress.setRange(0,1);self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setMinimumHeight(130);self.debug=QCheckBox(tr(lang,"debug"));self.debug.setToolTip(tr(lang,"debug_tip"));self.workers=QSpinBox();self.workers.setRange(1,max(2,min(8,os.cpu_count() or 2)));self.workers.setValue(min(DEFAULT_WORKERS,self.workers.maximum()));self.workers.setToolTip(tr(lang,"threads_tip"));self.run=QPushButton(tr(lang,"start"));self.run.setObjectName("primary");self.cancel=QPushButton(tr(lang,"cancel"));self.cancel.setEnabled(False);self.cancel.clicked.connect(self.stop)
    def footer(self):
        o=QHBoxLayout();o.addWidget(self.debug);o.addStretch();o.addWidget(QLabel(tr(self.lang,"threads")));o.addWidget(self.workers);self.content.addLayout(o);self.content.addWidget(self.progress);self.content.addWidget(self.log,1);b=QHBoxLayout();b.addStretch();b.addWidget(self.cancel);b.addWidget(self.run);self.content.addLayout(b)
    def common(self):return {"lang":self.lang,"workers":self.workers.value(),"debug":self.debug.isChecked()}
    def start(self,fn,kw):
        if self.thread:return
        self.log.clear();self.progress.setRange(0,0);self.run.setEnabled(False);self.cancel.setEnabled(True);th=QThread(self);w=Worker(fn,kw,self.lang);w.moveToThread(th);th.started.connect(w.run);w.progress.connect(self.on_progress);w.finished.connect(self.on_done);w.failed.connect(self.on_fail);w.finished.connect(th.quit);w.failed.connect(th.quit);th.finished.connect(w.deleteLater);th.finished.connect(th.deleteLater);th.finished.connect(self.clear);self.thread=th;self.worker=w;th.start()
    def stop(self):
        if self.worker:self.cancel.setEnabled(False);self.log.appendPlainText(tr(self.lang,"wait_cancel"));self.worker.stop.set()
    def on_progress(self,c,n,m):self.progress.setRange(0,max(n,1));self.progress.setValue(c);self.log.appendPlainText(f"[{c}/{n}] {m}")
    def on_done(self,s):
        self.log.appendPlainText(tr(self.lang,"finished",ok=s.succeeded,skip=s.skipped,fail=s.failed));dbg=tr(self.lang,"debug_line",path=s.debug_path) if s.debug_path else "";QMessageBox.information(self,tr(self.lang,"done"),tr(self.lang,"done_body",total=s.total,ok=s.succeeded,skip=s.skipped,fail=s.failed,path=s.output_path,debug=dbg))
    def on_fail(self,m):self.log.appendPlainText(m);QMessageBox.warning(self,tr(self.lang,"failed_title"),m)
    def clear(self):self.thread=None;self.worker=None;self.run.setEnabled(True);self.cancel.setEnabled(False);self.progress.setRange(0,1) if self.progress.maximum()==0 else None
    def running(self):return self.thread is not None

class MatchOpts(QGroupBox):
    def __init__(self,lang,sample):
        super().__init__(tr(lang,"match_group"));self.lang=lang;self.region=RegionEditor(lang,sample.text);self.search=SearchMask(lang);self.edge=QDoubleSpinBox();self.edge.setRange(0,45);self.edge.setValue(10);self.edge.setSuffix(" %");self.sim=QDoubleSpinBox();self.sim.setRange(-1,1);self.sim.setDecimals(3);self.sim.setSingleStep(.01);self.sim.setValue(DEFAULT_THRESHOLD);f=QFormLayout(self);f.addRow(tr(lang,"template"),self.region);f.addRow(tr(lang,"search_mask"),self.search);f.addRow(tr(lang,"edge"),self.edge);f.addRow(tr(lang,"similarity"),self.sim)
    def value(self):return MatchSettings(self.region.rect(),self.edge.value(),self.search.spin.value(),self.sim.value())

def path_check(parent,lang,pairs):
    miss=[a for a,b in pairs if not b]
    if miss:QMessageBox.warning(parent,tr(lang,"missing"),tr(lang,"select_missing",items="、".join(miss)));return False
    return True

def quality():q=QSpinBox();q.setRange(1,100);q.setValue(95);q.setSuffix(" %");return q

class MatchTab(BatchTab):
    def __init__(self,lang):
        super().__init__(lang);g=QGroupBox(tr(lang,"paths"));f=QFormLayout(g);self.sample=PathChooser(lang,"file");self.input=PathChooser(lang,"folder");self.output=PathChooser(lang,"folder");f.addRow(tr(lang,"sample"),self.sample);f.addRow(tr(lang,"input"),self.input);f.addRow(tr(lang,"output"),self.output);self.opts=MatchOpts(lang,self.sample);og=QGroupBox(tr(lang,"output_group"));of=QFormLayout(og);self.q=quality();of.addRow(tr(lang,"quality"),self.q);of.addRow("",QLabel(tr(lang,"name_note")));self.content.addWidget(g);self.content.addWidget(self.opts);self.content.addWidget(og);self.footer();self.run.clicked.connect(self.go)
    def go(self):
        if path_check(self,self.lang,[(tr(self.lang,"sample"),self.sample.text()),(tr(self.lang,"input"),self.input.text()),(tr(self.lang,"output"),self.output.text())]):self.start(match_crop,{"sample":self.sample.text(),"input_folder":self.input.text(),"output_folder":self.output.text(),"settings":self.opts.value(),"quality":self.q.value(),**self.common()})

class CenterTab(BatchTab):
    def __init__(self,lang):
        super().__init__(lang);g=QGroupBox(tr(lang,"paths"));f=QFormLayout(g);self.input=PathChooser(lang,"folder");self.output=PathChooser(lang,"folder");f.addRow(tr(lang,"input"),self.input);f.addRow(tr(lang,"output"),self.output);sg=QGroupBox(tr(lang,"center_group"));grid=QGridLayout(sg);self.fixed=QRadioButton(tr(lang,"fixed"));self.ratio=QRadioButton(tr(lang,"ratio"));self.fixed.setChecked(True);bg=QButtonGroup(self);bg.addButton(self.fixed);bg.addButton(self.ratio);self.w=QSpinBox();self.h=QSpinBox()
        for s in (self.w,self.h):s.setRange(1,200000);s.setValue(1000);s.setSuffix(" px")
        self.r=QLineEdit("1/3");self.r.setPlaceholderText(tr(lang,"ratio_ph"));self.r.setEnabled(False);self.fixed.toggled.connect(lambda on:(self.w.setEnabled(on),self.h.setEnabled(on),self.r.setEnabled(not on)));grid.addWidget(self.fixed,0,0);grid.addWidget(QLabel(tr(lang,"w")+"："),0,1);grid.addWidget(self.w,0,2);grid.addWidget(QLabel(tr(lang,"h")+"："),0,3);grid.addWidget(self.h,0,4);grid.addWidget(self.ratio,1,0);grid.addWidget(QLabel(tr(lang,"ratio_label")),1,1,1,2);grid.addWidget(self.r,1,3,1,2);og=QGroupBox(tr(lang,"output_group"));of=QFormLayout(og);self.q=quality();of.addRow(tr(lang,"quality"),self.q);of.addRow("",QLabel(tr(lang,"center_note")));self.content.addWidget(g);self.content.addWidget(sg);self.content.addWidget(og);self.footer();self.run.clicked.connect(self.go)
    def go(self):
        if not path_check(self,self.lang,[(tr(self.lang,"input"),self.input.text()),(tr(self.lang,"output"),self.output.text())]):return
        kw={"input_folder":self.input.text(),"output_folder":self.output.text(),"quality":self.q.value(),**self.common()};kw.update({"width":self.w.value(),"height":self.h.value()} if self.fixed.isChecked() else {"ratio":self.r.text().strip()});self.start(center_crop,kw)

class CoordTab(BatchTab):
    def __init__(self,lang):
        super().__init__(lang);g=QGroupBox(tr(lang,"paths"));f=QFormLayout(g);self.sample=PathChooser(lang,"file");self.input=PathChooser(lang,"folder");self.csv=PathChooser(lang,"save","csv_filter");f.addRow(tr(lang,"sample"),self.sample);f.addRow(tr(lang,"input"),self.input);f.addRow(tr(lang,"csv"),self.csv);self.opts=MatchOpts(lang,self.sample);note=QLabel(tr(lang,"coord_note"));note.setWordWrap(True);self.content.addWidget(g);self.content.addWidget(self.opts);self.content.addWidget(note);self.footer();self.run.clicked.connect(self.go)
    def go(self):
        if not path_check(self,self.lang,[(tr(self.lang,"sample"),self.sample.text()),(tr(self.lang,"input"),self.input.text()),(tr(self.lang,"csv"),self.csv.text())]):return
        p=self.csv.text();p=p if Path(p).suffix.lower()==".csv" else p+".csv";self.csv.edit.setText(p);self.start(export_coords,{"sample":self.sample.text(),"input_folder":self.input.text(),"csv_path":p,"settings":self.opts.value(),**self.common()})

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__();self.lang="zh";self.setWindowTitle("CIPA Crop & Coord");self.resize(1180,860);self.setMinimumSize(940,700);tb=QToolBar();tb.setMovable(False);self.addToolBar(tb);sp=QWidget();sp.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred);tb.addWidget(sp);self.lang_label=QLabel();tb.addWidget(self.lang_label);self.combo=QComboBox();self.combo.addItem("中文","zh");self.combo.addItem("日本語","ja");tb.addWidget(self.combo);self.combo.currentIndexChanged.connect(self.switch);self.build()
    def build(self):
        old=self.centralWidget();self.tabs=QTabWidget();self.a=MatchTab(self.lang);self.b=CenterTab(self.lang);self.c=CoordTab(self.lang);self.tabs.addTab(self.a,tr(self.lang,"tab1"));self.tabs.addTab(self.b,tr(self.lang,"tab2"));self.tabs.addTab(self.c,tr(self.lang,"tab3"));self.setCentralWidget(self.tabs);old.deleteLater() if old else None;self.lang_label.setText(tr(self.lang,"language"));self.statusBar().showMessage(tr(self.lang,"status"))
    def switch(self,i):
        new=self.combo.itemData(i)
        if new==self.lang:return
        if any(x.running() for x in (self.a,self.b,self.c)):
            QMessageBox.information(self,tr(self.lang,"running"),tr(self.lang,"running_msg"));self.combo.blockSignals(True);self.combo.setCurrentIndex(0 if self.lang=="zh" else 1);self.combo.blockSignals(False);return
        self.lang=new;self.build()
    def closeEvent(self,e:QCloseEvent):
        if any(x.running() for x in (self.a,self.b,self.c)):QMessageBox.information(self,tr(self.lang,"running"),tr(self.lang,"running_msg"));e.ignore()
        else:e.accept()

def main():
    app=QApplication(sys.argv);app.setApplicationName("CIPA Crop & Coord");app.setOrganizationName("CIPA");app.setStyleSheet(STYLE);w=MainWindow();w.show();return app.exec()
