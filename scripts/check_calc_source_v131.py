"""Verify repository-local FindsBlur v1.3.1 source and native decoder."""
from __future__ import annotations
import ast
import os
from pathlib import Path


def validate(root: Path, decoder: Path) -> None:
    root = root.expanduser().resolve()
    core_file = root / "standalone_gui/core.py"
    debug_file = root / "standalone_gui/calcdebug.py"
    stage_file = root / "phase12/recovered_measurement_region_402b90.py"
    source_file = root / "tools/ijg8c_rgb_probe.c"
    required = [core_file, debug_file, stage_file, source_file, decoder]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        raise SystemExit("Incomplete vendored FindsBlur v1.3.1:\n" + "\n".join(missing))
    tree = ast.parse(core_file.read_text(encoding="utf-8"))
    methods = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    calculate = methods.get("calculate")
    if calculate is None or "calcdebug_root" not in {
        item.arg for item in calculate.args.kwonlyargs
    } or "_decoder_creationflags" not in methods:
        raise SystemExit("Vendored core is older than FindsBlur v1.3.1.")
    diag = ast.parse(debug_file.read_text(encoding="utf-8"))
    names = {n.targets[0].id for n in diag.body if isinstance(n, ast.Assign)
             and len(n.targets)==1 and isinstance(n.targets[0], ast.Name)}
    if not {"STAGES", "REFERENCE_IMAGE"}.issubset(names):
        raise SystemExit("CalcDebug metadata is incomplete.")
    print("Bundled FindsBlur v1.3.1 source, CalcDebug and native decoder: PASS")


if __name__ == "__main__":
    project = Path(__file__).resolve().parents[1]
    root = project / "vendor/findsblur_v131"
    env_decoder = os.environ.get("FINDSBLUR_IJG8C_EXE", "").strip()
    decoder = (Path(env_decoder) if env_decoder else
               root / "_work/IJG8c/bin/ijg8c_rgb_probe.exe")
    validate(root, decoder)
