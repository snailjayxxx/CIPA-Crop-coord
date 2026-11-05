"""Diagnostic-only probe for Qt numeric glyph rendering on Windows CI.

The Windows offscreen platform has sometimes rendered all QSpinBox digits as
the exact same black rectangle. This compares explicit fonts, a plain
QLineEdit, and the spinbox's embedded QLineEdit using only synthetic digits.
"""
from __future__ import annotations

import os
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont, QFontInfo
from PySide6.QtWidgets import QApplication, QSpinBox, QLineEdit

from cipa_crop_coord.ui import STYLE


def pixels_changed(a, b):
    if a.size() != b.size():
        return -1
    return sum(
        a.pixel(x,y) != b.pixel(x,y)
        for y in range(a.height()) for x in range(a.width())
    )


def snapshot(widget, name, out):
    widget.setValue(1) if isinstance(widget, QSpinBox) else widget.setText("1")
    QApplication.processEvents()
    first = widget.grab().toImage()
    widget.setValue(4) if isinstance(widget, QSpinBox) else widget.setText("4")
    QApplication.processEvents()
    second = widget.grab().toImage()
    first.save(str(out / f"{name}_1.png"))
    second.save(str(out / f"{name}_4.png"))
    return pixels_changed(first,second)


def main():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    out = Path("ui-capture")
    out.mkdir(exist_ok=True)
    for family in ("default", "Segoe UI", "Arial", "Tahoma", "Consolas", "Microsoft YaHei UI"):
        for kind in ("plain", "spin", "embedded"):
            spin = QSpinBox()
            spin.setRange(0,9)
            spin.resize(140,34)
            edit = spin.findChild(QLineEdit)
            if family != "default":
                font = QFont(family)
                font.setPixelSize(16)
                spin.setFont(font)
                edit.setFont(font)
            if kind == "plain":
                widget = QLineEdit()
                widget.resize(140,34)
                if family != "default":
                    widget.setFont(spin.font())
            elif kind == "embedded":
                widget = edit
            else:
                widget = spin
            spin.show()
            if kind=="plain":
                widget.show()
            app.processEvents()
            key = family.replace(" ","_")+"_"+kind
            result = snapshot(widget, key, out)
            print(f"Font probe {key}: resolved={QFontInfo(widget.font()).family()!r} diff_pixels={result}")
            if kind=="plain":
                widget.close()
            spin.close()


if __name__=="__main__":
    main()
