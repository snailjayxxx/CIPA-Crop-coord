"""Crash log must be local-only and omit photo names/paths."""
from __future__ import annotations

from cipa_crop_coord import crash_diagnostics


def test_log_path_uses_windows_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert crash_diagnostics.log_path() == (
        tmp_path / "CIPA-Crop-Coord" / "logs" / "runtime.log"
    )


def test_worker_record_contains_only_statistics(tmp_path, monkeypatch):
    logfile = tmp_path / "log.txt"
    with logfile.open("w", encoding="utf-8") as target:
        monkeypatch.setattr(crash_diagnostics, "_FILE", target)
        crash_diagnostics.record_worker_plan(
            selected_images=110, source_pixels=66_000_000,
            crop_pixels=4_000_000, requested_crop=8, actual_crop=2,
            requested_calc=4, actual_calc=1,
            available_gib=6.0, deferred=False,
        )
    content = logfile.read_text(encoding="utf-8")
    assert "selected_images" not in content
    assert "image_count=110" in content
    assert "actual_crop=2" in content
    assert "available_gib=6.0" in content
    assert "C:\\Users" not in content
