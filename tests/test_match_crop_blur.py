from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from cipa_crop_coord import blur_pipeline
from cipa_crop_coord.engine import MatchSettings, match_crop
from cipa_crop_coord.locales import tr
from cipa_crop_coord.ui import MatchTab


def _app():
    return QApplication.instance() or QApplication([])


def _make_samples(tmp_path, count):
    rng = np.random.default_rng(20261105)
    pattern = rng.integers(10, 240, (25, 30, 3), dtype=np.uint8)
    sample = tmp_path / "sample.jpg"
    assert cv2.imwrite(str(sample), pattern)
    sources = tmp_path / "images"
    sources.mkdir()
    for index in range(count):
        image = np.zeros((85, 100, 3), dtype=np.uint8)
        image[28:53, 36:66] = pattern
        assert cv2.imwrite(str(sources / f"{index:03d}.jpg"), image)
    return sample, sources


def _fake_backend(calls):
    def run(images, target, decoder, *, workers, progress, cancel, language,
            calcdebug_root=None):
        calls.append((len(images), workers))
        debug_session = None
        if calcdebug_root is not None:
            debug_session = Path(calcdebug_root) / f"batch_{len(calls)}"
            debug_session.mkdir(parents=True)
            (debug_session / "session_manifest.json").write_text("{}", encoding="utf-8")
        target.write_text(
            "".join(f"{p.name} 1.000000 2.000000 3.000000 4.000000\n" for p in images),
            encoding="utf-8",
        )
        for count, path in enumerate(images, start=1):
            progress(count, len(images), path, True, "ok")
        return SimpleNamespace(
            completed=len(images), successful=len(images),
            failures=(), cancelled=False, calcdebug_path=debug_session,
        )
    return run, Path("fake_decoder.exe")


def test_opt_in_interface_has_independent_1_to_4_calc_workers(tmp_path):
    _app()
    for lang in ("zh", "ja", "en"):
        tab = MatchTab(lang)
        assert not tab.blur_enabled.isChecked()
        assert tab.blur_enabled.text() == tr(lang, "blur_output")
        assert not tab.blur_file.isEnabled()
        assert not tab.blur_workers.isEnabled()
        assert tab.blur_workers.minimum() == 1
        assert tab.blur_workers.maximum() == 4
        assert tab.blur_workers.value() == 2
        assert not tab.calcdebug_enabled.isChecked()
        assert not tab.calcdebug_enabled.isEnabled()
        assert not tab.calcdebug_folder.isEnabled()
        assert tab.calcdebug_enabled.text() == tr(lang, "calcdebug_enable")
        crop_workers = tab.workers.value()
        tab.blur_enabled.setChecked(True)
        assert tab.blur_file.isEnabled()
        assert tab.blur_workers.isEnabled()
        assert tab.calcdebug_enabled.isEnabled()
        tab.calcdebug_enabled.setChecked(True)
        assert tab.calcdebug_folder.isEnabled()
        tab.blur_workers.setValue(4)
        assert tab.workers.value() == crop_workers
        tab.output.edit.setText(str(tmp_path / "crops"))
        assert tab.blur_file.text() == str(tmp_path / "crops" / "FindsBlur_Result.txt")
        tab.blur_file.edit.setText(str(tmp_path / "custom.txt"))
        tab.output.edit.setText(str(tmp_path / "second"))
        assert tab.blur_file.text() == str(tmp_path / "custom.txt")
        tab.blur_enabled.setChecked(False)
        assert not tab.calcdebug_folder.isEnabled()
        assert not tab.calcdebug_enabled.isEnabled()
        tab.deleteLater()


def test_match_crop_streams_to_calc_only_when_selected(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(blur_pipeline, "load_calculator", lambda: _fake_backend(calls))
    sample, sources = _make_samples(tmp_path, 17)
    crops = tmp_path / "cropped"
    target = tmp_path / "result.txt"
    summary = match_crop(
        sample, sources, crops,
        MatchSettings(edge_mask=0, search_mask=0, threshold=-1, coarse=180),
        workers=2, blur_output=target, blur_workers=4,
    )
    assert summary.succeeded == 17
    assert summary.blur_requested
    assert summary.blur_queued == summary.blur_attempted == 17
    assert summary.blur_succeeded == 17
    assert summary.blur_failed == 0
    assert calls[0] == (4, 4)
    assert sum(batch_size for batch_size, _ in calls) == 17
    assert all(1 <= batch_size <= 4 and workers == 4 for batch_size, workers in calls)
    assert len(target.read_text(encoding="utf-8").splitlines()) == 17


def test_match_crop_off_does_not_initialize_calc(tmp_path, monkeypatch):
    def unavailable():
        raise AssertionError("calculator must not load if checkbox was off")
    monkeypatch.setattr(blur_pipeline, "load_calculator", unavailable)
    sample, sources = _make_samples(tmp_path, 1)
    summary = match_crop(
        sample, sources, tmp_path / "cropped",
        MatchSettings(edge_mask=0, search_mask=0, threshold=-1, coarse=180),
        workers=2,
    )
    assert summary.succeeded == 1 and not summary.blur_requested



def test_match_crop_routes_calcdebug_to_new_core_without_affecting_txt(tmp_path, monkeypatch):
    import json

    calls = []
    monkeypatch.setattr(blur_pipeline, "load_calculator", lambda: _fake_backend(calls))
    sample, sources = _make_samples(tmp_path, 17)
    debug_root = tmp_path / "CalcDebug"
    txt_path = tmp_path / "blur_result.txt"
    summary = match_crop(
        sample, sources, tmp_path / "cropped",
        MatchSettings(edge_mask=0, search_mask=0, threshold=-1, coarse=180),
        blur_output=txt_path,
        blur_workers=3,
        blur_calcdebug_root=debug_root,
    )
    assert summary.succeeded == 17
    assert summary.blur_succeeded == 17
    assert calls[0] == (4, 3)
    assert sum(batch_size for batch_size, _ in calls) == 17
    assert all(1 <= batch_size <= 4 for batch_size, _ in calls)
    assert len(txt_path.read_text(encoding="utf-8").splitlines()) == 17
    run_folder = Path(summary.blur_calcdebug_path)
    assert run_folder.is_dir() and run_folder.parent == debug_root
    manifest = json.loads(
        (run_folder / "crop_pipeline_manifest.json").read_text(encoding="utf-8")
    )
    assert len(manifest["calcdebug_sessions"]) == len(calls)


def test_matching_skips_existing_calcdebug_pngs_inside_input_root(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(blur_pipeline, "load_calculator", lambda: _fake_backend(calls))
    sample, sources = _make_samples(tmp_path, 1)
    debug_folder = sources / "CalcDebug"
    debug_folder.mkdir()
    assert cv2.imwrite(
        str(debug_folder / "old_checkpoint.png"),
        np.zeros((85, 100, 3), dtype=np.uint8),
    )
    summary = match_crop(
        sample, sources, tmp_path / "cropped",
        MatchSettings(edge_mask=0, search_mask=0, threshold=-1, coarse=180),
        blur_output=tmp_path / "result.txt",
        blur_calcdebug_root=debug_folder,
    )
    assert summary.total == 1
    assert summary.succeeded == 1
    assert summary.blur_succeeded == 1
    assert calls == [(1, 2)]
    assert (tmp_path / "result.txt").is_file()


@pytest.mark.parametrize("count", (1, 2, 3, 4))
def test_short_batch_always_generates_calculation_txt(tmp_path, monkeypatch, count):
    calls = []
    monkeypatch.setattr(blur_pipeline, "load_calculator", lambda: _fake_backend(calls))
    sample, sources = _make_samples(tmp_path, count)
    destination = tmp_path / "result.txt"
    summary = match_crop(
        sample, sources, tmp_path / "out",
        MatchSettings(edge_mask=0, search_mask=0, threshold=-1, coarse=180),
        blur_output=destination, workers=2,
    )
    assert summary.succeeded == count
    assert summary.blur_queued == summary.blur_attempted == count
    assert summary.blur_succeeded == count
    assert not summary.blur_skipped_minimum
    assert calls == [(count, 2)]
    assert len(destination.read_text(encoding="utf-8").splitlines()) == count


def test_zero_input_does_not_initialize_calculator(tmp_path, monkeypatch):
    def unavailable():
        raise AssertionError("zero images must not load calculator")
    monkeypatch.setattr(blur_pipeline, "load_calculator", unavailable)
    sample, sources = _make_samples(tmp_path, 0)
    result = tmp_path / "result.txt"
    summary = match_crop(
        sample, sources, tmp_path / "out",
        MatchSettings(edge_mask=0, search_mask=0, threshold=-1, coarse=180),
        blur_output=result,
    )
    assert summary.blur_queued == summary.blur_attempted == 0
    assert summary.blur_skipped_minimum
    assert not result.exists()


def test_calc_launches_after_four_saved_files_before_finish(tmp_path):
    from threading import Event
    started = Event()
    calls = []

    def fake_calculate(images, target, decoder, *, workers, progress, cancel, language,
                       calcdebug_root=None):
        calls.append(len(images))
        target.write_text(
            "".join(f"{path.name} 1 2 3 4\n" for path in images),
            encoding="utf-8",
        )
        for i, path in enumerate(images, 1):
            progress(i, len(images), path, True, "ok")
        started.set()
        return SimpleNamespace(
            completed=len(images), successful=len(images),
            failures=(), cancelled=False, calcdebug_path=None,
        )

    pipeline = blur_pipeline.BlurPipeline(
        tmp_path / "stream.txt", expected=6,
        backend=(fake_calculate, Path("fake_decoder.exe")),
    )
    pipeline.start()
    try:
        for idx in range(4):
            pipeline.submit(idx, tmp_path / f"crop_{idx}.jpg")
        assert started.wait(timeout=5), "4 completed crops should start calculation"
        for idx in range(4, 6):
            pipeline.submit(idx, tmp_path / f"crop_{idx}.jpg")
    finally:
        result = pipeline.finish()
    assert calls == [4, 2]
    assert result.attempted == 6



def test_full_worker_request_is_throttled_without_changing_txt(tmp_path, monkeypatch):
    from cipa_crop_coord import memory_guard
    calls = []
    monkeypatch.setattr(blur_pipeline, "load_calculator", lambda: _fake_backend(calls))
    # Simulate 66MP input metadata without allocating actual 66MP image arrays.
    monkeypatch.setattr(memory_guard, "largest_image_pixels", lambda files: 66_000_000)
    monkeypatch.setattr(memory_guard, "available_memory_bytes", lambda: 6 * memory_guard.GIB)
    sample, sources = _make_samples(tmp_path, 9)
    lines = []
    destination = tmp_path / "safe.txt"
    summary = match_crop(
        sample, sources, tmp_path / "out",
        MatchSettings(edge_mask=0, search_mask=0, threshold=-1, coarse=180),
        workers=8, blur_output=destination, blur_workers=4,
        progress=lambda current, total, message: lines.append(message),
    )
    assert summary.succeeded == summary.blur_succeeded == 9
    assert 1 <= summary.effective_crop_workers < 8
    assert 1 <= summary.effective_calc_workers <= 4
    assert summary.safety_note and summary.safety_note in lines
    assert len(destination.read_text(encoding="utf-8").splitlines()) == 9
    assert sum(batch_size for batch_size, _ in calls) == 9


def test_deferred_calculation_does_not_start_before_crop_finish(tmp_path):
    from threading import Event
    started = Event()

    def calculate(images, output, decoder, *, workers, progress, cancel, language,
                  calcdebug_root=None):
        started.set()
        output.write_text(
            "".join(f"{path.name} 1 2 3 4\n" for path in images),
            encoding="utf-8",
        )
        for i, path in enumerate(images, 1):
            progress(i, len(images), path, True, "ok")
        return SimpleNamespace(
            completed=len(images), successful=len(images),
            failures=(), cancelled=False, calcdebug_path=None,
        )

    pipeline = blur_pipeline.BlurPipeline(
        tmp_path / "deferred.txt",
        workers=1, expected=6, defer_until_finish=True,
        backend=(calculate, Path("fake_decoder.exe")),
    )
    pipeline.start()
    for index in range(6):
        pipeline.submit(index, tmp_path / f"{index:03d}.jpg")
    assert not started.wait(timeout=0.15), "RAM guard must defer computation"
    result = pipeline.finish()
    assert started.is_set()
    assert result.attempted == 6
    assert len((tmp_path / "deferred.txt").read_text(encoding="utf-8").splitlines()) == 6
