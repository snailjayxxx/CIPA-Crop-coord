"""Entry point for the Windows PyInstaller portable distribution."""
from __future__ import annotations
from pathlib import Path
import os
import sys
import traceback


def main():
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    for p in (base, base / 'phase5'):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    decoder = base / '_work' / 'IJG8c' / 'bin' / 'ijg8c_rgb_probe.exe'
    if '--self-test' in sys.argv:
        import tempfile
        from PIL import Image
        from standalone_gui.core import IJG8cReader, verify_captured_parameters
        from phase11.native_parameters import from_dimensions
        from standalone.__main__ import _analyze_without_oracle
        from standalone_gui.gui import Window
        verify_captured_parameters(from_dimensions)
        with tempfile.TemporaryDirectory(prefix='findsblur_bundle_smoke_') as tmp:
            path = Path(tmp)
            source = path / 'smoke.jpg'
            # Synthetic calibration input only; no private photographs.
            Image.new('RGB', (80, 60), (100, 140, 190)).save(source, quality=92)
            im = IJG8cReader(decoder, path / 'decoder').open(source)
            assert im.size == (80, 60) and im.mode == 'RGB', 'IJG8c decoder self-test failed'
        return 0
    from standalone_gui.gui import launch
    launch(decoder)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
