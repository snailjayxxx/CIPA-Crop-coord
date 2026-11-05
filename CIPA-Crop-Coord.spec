# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for crop-only or full integrated FindsBlur builds.

Full integration uses repository-local vendor/findsblur_v131 source and the
IJG 8c executable built from the vendored C probe in Windows CI. No second
GitHub repository is required at build or runtime.
"""
import os
from pathlib import Path

root = Path.cwd()
pathex = [str(root / "src")]
datas = []
binaries = []
hiddenimports = []
integrated = os.environ.get("CIPA_BUILD_INTEGRATED") == "1"

if integrated:
    calc_root = root / "vendor" / "findsblur_v131"
    required = [
        calc_root / "standalone_gui" / "core.py",
        calc_root / "standalone_gui" / "calcdebug.py",
        calc_root / "standalone" / "__main__.py",
        calc_root / "phase12" / "recovered_measurement_region_402b90.py",
    ]
    for source in required:
        if not source.is_file():
            raise FileNotFoundError(f"Required vendored FindsBlur v1.3.1 module is missing: {source}")
    decoder_env = os.environ.get("FINDSBLUR_IJG8C_EXE", "").strip()
    decoder = (
        Path(decoder_env).expanduser().resolve()
        if decoder_env else calc_root / "_work" / "IJG8c" / "bin" / "ijg8c_rgb_probe.exe"
    )
    if not decoder.is_file():
        raise FileNotFoundError(
            f"Native IJG 8c decoder is missing: {decoder}. "
            "Build with the integrated GitHub Actions workflow or compile the "
            "included tools/ijg8c_rgb_probe.c against the IJG 8c library."
        )
    for source in calc_root.rglob("*.py"):
        if "__pycache__" in source.parts or source.name.startswith("test_"):
            continue
        output_dir = Path("vendor/findsblur_v131") / source.relative_to(calc_root).parent
        datas.append((str(source), output_dir.as_posix()))
    binaries.append((str(decoder), "vendor/findsblur_v131/_work/IJG8c/bin"))
    pathex.extend([str(calc_root), str(calc_root / "phase5")])
    hiddenimports.extend([
        "standalone_gui.core", "standalone_gui.accelerate",
        "standalone_gui.calcdebug", "standalone_gui.i18n",
        "standalone.__main__", "phase12.accelerated_topology",
    ])
    from PyInstaller.utils.hooks import collect_all
    for package in ("scipy", "numba"):
        extra_data, extra_binaries, extra_imports = collect_all(package)
        datas.extend(extra_data)
        binaries.extend(extra_binaries)
        hiddenimports.extend(extra_imports)

a = Analysis(
    ["launcher.py"],
    pathex=pathex,
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="CIPA-Crop-Coord",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
