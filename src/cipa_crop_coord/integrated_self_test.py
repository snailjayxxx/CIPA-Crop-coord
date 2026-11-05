"""Run a real bundled decoder + calculation API smoke test without showing the GUI."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile


def self_test_integrated() -> int:
    try:
        from PIL import Image, ImageDraw
        from .blur_pipeline import load_calculator
        calculate, decoder = load_calculator()
        with tempfile.TemporaryDirectory(prefix="cipa_integrated_smoke_") as tmp:
            folder = Path(tmp)
            image = Image.new("RGB", (256, 192), "white")
            pen = ImageDraw.Draw(image)
            for x in range(12, 256, 21):
                pen.line([(x, 10), (x // 2, 180)], fill="black", width=2)
            jpeg = folder / "synthetic_input.jpg"
            image.save(jpeg, quality=95)
            target = folder / "smoke.txt"
            debug = folder / "CalcDebug"
            result = calculate(
                [jpeg], target, decoder,
                workers=1, language="en", calcdebug_root=debug,
            )
            if result.total != 1 or result.completed != 1:
                raise RuntimeError("FindsBlur did not attempt exactly one input.")
            if not target.is_file():
                raise RuntimeError("FindsBlur did not write a result TXT.")
            lines = target.read_text(encoding="utf-8-sig").splitlines()
            if len(lines) != 1 or not lines[0].startswith(jpeg.name + " "):
                raise RuntimeError("Incorrect official-format TXT output.")
            debug_dir = getattr(result, "calcdebug_path", None)
            if not debug_dir or not (Path(debug_dir) / "session_manifest.json").is_file():
                raise RuntimeError("CalcDebug v1.3.1 manifest was not created.")
        return 0
    except Exception as exc:
        # Frozen GUI applications can have no console: the failure exit code
        # is what the local build script asserts. Never upload the test input.
        print(f"Integrated FindsBlur smoke test failed: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 1
