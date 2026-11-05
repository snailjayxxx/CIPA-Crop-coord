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

            # IMPORTANT: the former self-test calculated one image directly,
            # bypassing the 16-crop background pipeline used by actual users.
            # Test the SAME deferred module import path with 17 completed JPGs:
            # one 16-image starting batch plus the final one-image flush.
            from shutil import copyfile
            from .blur_pipeline import BlurPipeline
            sample_dir = folder / "cropped"
            sample_dir.mkdir()
            images = []
            for index in range(17):
                dst = sample_dir / f"synthetic_crop_{index:03d}.jpg"
                copyfile(jpeg, dst)
                images.append(dst)
            pipeline_target = folder / "FindsBlur_Result.txt"
            pipeline = BlurPipeline(
                pipeline_target, workers=4, expected=17, lang="en",
            )
            pipeline.start()
            for index, path in enumerate(images):
                pipeline.submit(index, path)
            pipeline_result = pipeline.finish()
            if pipeline_result.error:
                raise RuntimeError("16-image background calculator failed: " + pipeline_result.error)
            if pipeline_result.queued != 17 or pipeline_result.attempted != 17:
                raise RuntimeError(
                    "16-image streaming pipeline did not process all 17 photos: "
                    + str(pipeline_result)
                )
            if not pipeline_target.is_file():
                raise RuntimeError("The background calculation did not create TXT output.")
            rows = pipeline_target.read_text(encoding="utf-8-sig").splitlines()
            if len(rows) != 17 or not all(
                row.startswith(f"synthetic_crop_{index:03d}.jpg ")
                for index, row in enumerate(rows)
            ):
                raise RuntimeError("The 16-image streaming TXT sequence is incorrect.")
        return 0
    except Exception as exc:
        # Frozen GUI applications can have no console: the failure exit code
        # is what the local build script asserts. Never upload the test input.
        print(f"Integrated FindsBlur smoke test failed: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 1
