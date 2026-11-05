"""Fail closed unless the single-file EXE embeds FindsBlur v1.3.1."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import sys
from PyInstaller.archive.readers import CArchiveReader

MANDATORY = (
    "vendor/findsblur_v131/standalone_gui/core.py",
    "vendor/findsblur_v131/standalone_gui/calcdebug.py",
    "vendor/findsblur_v131/standalone/__main__.py",
    "vendor/findsblur_v131/phase12/recovered_measurement_region_402b90.py",
    "vendor/findsblur_v131/_work/IJG8c/bin/ijg8c_rgb_probe.exe",
)

def main():
    exe = Path(sys.argv[1] if len(sys.argv)>1 else "dist/CIPA-Crop-Coord.exe")
    if not exe.is_file():
        raise SystemExit("EXE not found: " + str(exe))
    names = {str(x).replace("\\", "/").lower() for x in CArchiveReader(str(exe)).toc}
    missing = [x for x in MANDATORY
               if not any(z.endswith(x.lower()) for z in names)]
    if missing:
        raise SystemExit("Not an integrated EXE (missing assets): " + ", ".join(missing))
    if any("targetexe.exe" in x or "findsblur_standalone.exe" in x for x in names):
        raise SystemExit("Original/external FindsBlur EXE must not be embedded.")
    digest=sha256()
    with exe.open("rb") as f:
        for data in iter(lambda:f.read(4*1024*1024),b""):
            digest.update(data)
    print("Integrated archive check: PASS", exe.resolve())
    print("SHA256:",digest.hexdigest())

if __name__ == "__main__":
    main()
