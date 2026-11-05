"""Read-only integration build prerequisite check for a private CIPA-Calc checkout.

Never updates, clones or writes to the calculator repository.
"""
from __future__ import annotations

import ast
from hashlib import sha256
import os
from pathlib import Path
import subprocess
import sys


def validate(root: Path, decoder: Path) -> None:
    root = root.expanduser().resolve()
    decoder = decoder.expanduser().resolve()
    core_file = root / "standalone_gui" / "core.py"
    debug_file = root / "standalone_gui" / "calcdebug.py"
    stage_file = root / "phase12" / "recovered_measurement_region_402b90.py"
    required = [core_file, debug_file, stage_file, decoder]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        raise SystemExit(
            "FindsBlur v1.3.1 local integration is incomplete:\n  "
            + "\n  ".join(missing)
        )
    tree = ast.parse(core_file.read_text(encoding="utf-8"), filename=str(core_file))
    methods = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    calculate = methods.get("calculate")
    if not calculate:
        raise SystemExit("Invalid private calculate() entrypoint.")
    keywords = {arg.arg for arg in calculate.args.kwonlyargs}
    if "calcdebug_root" not in keywords:
        raise SystemExit("CIPA-Calc is older than v1.3: calcdebug_root is missing.")
    if "_decoder_creationflags" not in methods:
        raise SystemExit("CIPA-Calc is older than v1.3.1: hidden JPEG decoder console fix missing.")
    debug_tree = ast.parse(debug_file.read_text(encoding="utf-8"), filename=str(debug_file))
    names = {node.targets[0].id for node in debug_tree.body
             if isinstance(node, ast.Assign)
             and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)}
    if "STAGES" not in names or "REFERENCE_IMAGE" not in names:
        raise SystemExit("CalcDebug stage catalog is incomplete.")
    print("FindsBlur v1.3.1 API and CalcDebug catalog: PASS")
    try:
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        print("Read-only CIPA-Calc revision:", commit)
    except (OSError, subprocess.CalledProcessError):
        print("Source revision unavailable (no git metadata).")
    for p in (core_file, debug_file, stage_file):
        print(p.relative_to(root), sha256(p.read_bytes()).hexdigest())
    print("Native IJG8c decoder:", decoder)
    print("All checks are read-only; CIPA-Calc remains unchanged.")


if __name__ == "__main__":
    root_text = os.environ.get("CIPA_CALC_ROOT", "").strip()
    if not root_text:
        raise SystemExit("Set CIPA_CALC_ROOT to the local private checkout.")
    root = Path(root_text)
    native_text = os.environ.get("FINDSBLUR_IJG8C_EXE", "").strip()
    native = (
        Path(native_text) if native_text else
        root / "_work" / "IJG8c" / "bin" / "ijg8c_rgb_probe.exe"
    )
    validate(root, native)
