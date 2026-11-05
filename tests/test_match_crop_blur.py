from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
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
    assert calls == [(16, 4), (1, 4)]
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
    assert [pair[0] for pair in calls] == [16, 1]
    assert len(txt_path.read_text(encoding="utf-8").splitlines()) == 17
    run_folder = Path(summary.blur_calcdebug_path)
    assert run_folder.is_dir() and run_folder.parent == debug_root
    manifest = json.loads(
        (run_folder / "crop_pipeline_manifest.json").read_text(encoding="utf-8")
    )
    assert len(manifest["calcdebug_sessions"]) == 2


def test_matching_skips_existing_calcdebug_pngs_inside_input_root(tmp_path):
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
    assert summary.blur_skipped_minimum
    assert not (tmp_path / "result.txt").exists()
