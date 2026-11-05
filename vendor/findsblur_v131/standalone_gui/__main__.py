"""Run with: .venv\\Scripts\\python -m standalone_gui"""
from __future__ import annotations
import os
from pathlib import Path
import sys


def main():
    root=Path(__file__).resolve().parents[1]
    if str(root) not in sys.path: sys.path.insert(0,str(root))
    if str(root/'phase5') not in sys.path: sys.path.insert(0,str(root/'phase5'))
    from .gui import launch
    decoder=Path(os.environ.get('FINDSBLUR_IJG8C_EXE',
        root/'_work'/'IJG8c'/'bin'/'ijg8c_rgb_probe.exe'))
    launch(decoder)


if __name__=='__main__':main()
