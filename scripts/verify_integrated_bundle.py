"""Verify a Windows PyInstaller one-file EXE really includes the calculator.

A crop-only public CI artifact must never be passed off as integrated.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sys

from PyInstaller.archive.readers import CArchiveReader

MANDATORY = (
    "standalone_gui/core.py",
    "standalone_gui/calcdebug.py",
    "standalone/__main__.py",
    "phase12/recovered_measurement_region_402b90.py",
    "_work/IJG8c/bin/ijg8c_rgb_probe.exe",
)


def main() -> None:
    exe = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist/CIPA-Crop-Coord.exe")
    if not exe.is_file():
        raise SystemExit("Integrated EXE does not exist: " + str(exe))
    archive = CArchiveReader(str(exe))
    members = {str(name).replace("\\", "/").lower() for name in archive.toc}
    missing = [required for required in MANDATORY
               if not any(item.endswith(required.lower()) for item in members)]
    if missing:
        raise SystemExit(
            "EXE is missing private calculator assets; NOT an integrated build:\n"
            + "\n".join(missing)
        )
    if any("targetexe.exe" in item or "findsblur_standalone.exe" in item
           for item in members):
        raise SystemExit("Original/standalone EXE must not be embedded in the integration.")
    size = exe.stat().st_size
    print("Integrated EXE archive contents: PASS")
    print("Path:", exe.resolve())
    print("Bytes:", size)
    print("SHA256:", sha256(exe.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
