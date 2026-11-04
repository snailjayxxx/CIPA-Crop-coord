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
    def run(images, target, decoder, *, workers, progress, cancel, language):
        calls.append((len(images), workers))
        target.write_text(
            "".join(f"{p.name} 1.000000 2.000000 3.000000 4.000000\n" for p in images),
            encoding="utf-8",
        )
        for count, path in enumerate(images, start=1):
            progress(count, len(images), path, True, "ok")
        return SimpleNamespace(
            completed=len(images), successful=len(images),
            failures=(), cancelled=False,
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
        crop_workers = tab.workers.value()
        tab.blur_enabled.setChecked(True)
        assert tab.blur_file.isEnabled()
        assert tab.blur_workers.isEnabled()
        tab.blur_workers.setValue(4)
        assert tab.workers.value() == crop_workers
        tab.output.edit.setText(str(tmp_path / "crops"))
        assert tab.blur_file.text() == str(tmp_path / "crops" / "FindsBlur_Result.txt")
        tab.blur_file.edit.setText(str(tmp_path / "custom.txt"))
        tab.output.edit.setText(str(tmp_path / "second"))
        assert tab.blur_file.text() == str(tmp_path / "custom.txt")
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
