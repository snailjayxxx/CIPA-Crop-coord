# -*- mode: python ; coding: utf-8 -*-
# Standard public build remains crop-only. For an integrated local build,
# set CIPA_CALC_ROOT to the private CIPA-Calc checkout, with a locally compiled
# IJG8c decoder. No private source is committed to this repository.
import os
from pathlib import Path

pathex = ["src"]
datas = []
binaries = []
hiddenimports = []

source_env = os.environ.get("CIPA_CALC_ROOT", "").strip()
if source_env:
    calc_root = Path(source_env).expanduser().resolve()
    required = [
        calc_root / "standalone_gui" / "core.py",
        calc_root / "standalone" / "__main__.py",
        calc_root / "phase11" / "replay_407170_4077eb.py",
    ]
    for required_path in required:
        if not required_path.is_file():
            raise FileNotFoundError("CIPA-Calc source is missing: " + str(required_path))

    decoder_env = os.environ.get("FINDSBLUR_IJG8C_EXE", "").strip()
    decoder = (
        Path(decoder_env).expanduser().resolve()
        if decoder_env else calc_root / "_work" / "IJG8c" / "bin" / "ijg8c_rgb_probe.exe"
    )
    if not decoder.is_file():
        raise FileNotFoundError("Missing locally compiled IJG8c decoder: " + str(decoder))

    # Include private computation sources only in this local executable.
    # Do not copy them into the public GitHub repository or source distribution.
    for group in ("standalone", "standalone_gui") + tuple(
        f"phase{i}" for i in range(1, 14)
    ):
        folder = calc_root / group
        if not folder.is_dir():
            continue
        for file in folder.rglob("*.py"):
            if "tests" in file.parts or file.name.startswith("test_"):
                continue
            datas.append((str(file), str(file.relative_to(calc_root).parent)))
    binaries.append((str(decoder), "_work/IJG8c/bin"))
    pathex.extend((str(calc_root), str(calc_root / "phase5")))
    hiddenimports.extend((
        "standalone_gui.core", "standalone_gui.accelerate",
        "standalone_gui.i18n", "standalone.__main__",
        "phase12.accelerated_topology",
    ))
    from PyInstaller.utils.hooks import collect_all

    for package in ("numba", "scipy"):
        extra_datas, extra_bins, extra_imports = collect_all(package)
        datas.extend(extra_datas)
        binaries.extend(extra_bins)
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
