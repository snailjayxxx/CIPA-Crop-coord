"""Regression tests for bundled FindsBlur module resolution and fail-fast use.

The integrated PyInstaller EXE may ship compiled modules in PYZ, with no
standalone_gui/core.py on disk. That must not prevent calculation.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from cipa_crop_coord import blur_pipeline
from cipa_crop_coord.engine import MatchSettings, match_crop


def test_frozen_loader_imports_compiled_module_without_loose_python_files(
    tmp_path, monkeypatch,
):
    extraction = tmp_path / "_MEItest"
    root = extraction / "vendor" / "findsblur_v131"
    decoder = root / "_work" / "IJG8c" / "bin" / "ijg8c_rgb_probe.exe"
    decoder.parent.mkdir(parents=True)
    decoder.write_bytes(b"MZ")

    def fake_calculate(*args, **kwargs):
        return None

    pkg = types.ModuleType("standalone_gui")
    pkg.__path__ = []
    core = types.ModuleType("standalone_gui.core")
    core.calculate = fake_calculate
    monkeypatch.setitem(sys.modules, "standalone_gui", pkg)
    monkeypatch.setitem(sys.modules, "standalone_gui.core", core)
    monkeypatch.setattr(sys, "_MEIPASS", str(extraction), raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    # A fake checkout path proves the test does not accidentally rely on the
    # real vendor files in this test runner's source tree.
    monkeypatch.setattr(
        blur_pipeline, "__file__",
        str(tmp_path / "empty_repo" / "src" / "cipa_crop_coord" / "blur_pipeline.py"),
    )
    monkeypatch.delenv("CIPA_CALC_ROOT", raising=False)
    monkeypatch.delenv("FINDSBLUR_IJG8C_EXE", raising=False)

    assert not (root / "standalone_gui" / "core.py").exists()
    calculator, found_decoder = blur_pipeline.load_calculator()
    assert calculator is fake_calculate
    assert found_decoder == decoder


def test_calculation_backend_failure_before_cropping_17_images(
    tmp_path, monkeypatch,
):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    pat = np.random.default_rng(13).integers(20, 230, (24, 36, 3), dtype=np.uint8)
    sample = tmp_path / "sample.jpg"
    assert cv2.imwrite(str(sample), pat)
    input_dir = tmp_path / "source"
    input_dir.mkdir()
    for i in range(17):
        image = np.zeros((90, 120, 3), dtype=np.uint8)
        image[32:56, 40:76] = pat
        assert cv2.imwrite(str(input_dir / f"frame_{i:03d}.jpg"), image)
    out = tmp_path / "cropped"

    def unavailable():
        raise RuntimeError("bundled FindsBlur runtime unavailable")

    monkeypatch.setattr(blur_pipeline, "load_calculator", unavailable)
    with pytest.raises(RuntimeError, match="bundled FindsBlur runtime unavailable"):
        match_crop(
            sample, input_dir, out,
            MatchSettings(edge_mask=0, search_mask=0, threshold=-1, coarse=180),
            blur_output=tmp_path / "result.txt",
            blur_workers=4,
        )
    assert not list(out.glob("*.jpg")), "Preflight must prevent wasted cropping"


def test_short_batch_preflight_requires_findsblur_backend(
    tmp_path, monkeypatch,
):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    sample_pixels = np.random.default_rng(15).integers(
        40, 220, (20, 30, 3), dtype=np.uint8
    )
    sample = tmp_path / "sample.jpg"
    assert cv2.imwrite(str(sample), sample_pixels)
    input_dir = tmp_path / "source"
    input_dir.mkdir()
    for index in range(3):
        frame = np.zeros((100, 130, 3), dtype=np.uint8)
        frame[38:58, 50:80] = sample_pixels
        assert cv2.imwrite(str(input_dir / f"photo_{index:03d}.jpg"), frame)

    def unavailable():
        raise RuntimeError("calculator missing for short batch")

    monkeypatch.setattr(blur_pipeline, "load_calculator", unavailable)
    destination = tmp_path / "result.txt"
    with pytest.raises(RuntimeError, match="calculator missing for short batch"):
        match_crop(
            sample, input_dir, tmp_path / "out",
            MatchSettings(edge_mask=0, search_mask=0, threshold=-1, coarse=180),
            workers=2, blur_output=destination,
        )
    assert not list((tmp_path / "out").glob("*.jpg"))
    assert not destination.exists()
