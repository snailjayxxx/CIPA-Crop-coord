from __future__ import annotations

from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from cipa_crop_coord.blur_pipeline import (
    BlurPipeline, DEFAULT_CALC_WORKERS, MAX_CALC_WORKERS, MIN_CALC_IMAGES,
    FAILURE_TEXT,
)


def _backend(recorder, *, started=None, resume=None, fail_name=None):
    def calculate(images, target, decoder, *, workers, progress, cancel, language):
        assert 1 <= workers <= 4
        assert decoder == Path("test_decoder.exe")
        recorder.append((len(images), workers, [item.name for item in images]))
        if started:
            started.set()
        if resume:
            assert resume.wait(5), "calculation did not overlap the crop producer"
        lines = []
        failures = []
        for number, path in enumerate(images, 1):
            if fail_name == path.name:
                lines.append(f"{path.name} {FAILURE_TEXT}")
                failures.append((path.name, "fake measurement failure"))
            else:
                lines.append(f"{path.name} 1.000000 2.000000 3.000000 4.000000")
            if progress:
                progress(number, len(images), path, path.name != fail_name, "test")
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return SimpleNamespace(
            cancelled=False, successful=len(images) - len(failures),
            failures=tuple(failures), completed=len(images),
        )
    return calculate, Path("test_decoder.exe")


def test_fewer_than_four_crops_are_calculated_after_finish(tmp_path):
    calls = []
    target = tmp_path / "not_written.txt"
    pipeline = BlurPipeline(target, workers=2, expected=50, backend=_backend(calls))
    pipeline.start()
    for index in range(MIN_CALC_IMAGES - 1):
        pipeline.submit(index, tmp_path / f"{index:03}.jpg")
    result = pipeline.finish()
    assert result.below_minimum is False
    assert result.attempted == MIN_CALC_IMAGES - 1
    assert result.queued == MIN_CALC_IMAGES - 1
    assert calls[0][0] == MIN_CALC_IMAGES - 1
    assert target.exists()


def test_calculation_starts_at_four_and_overlaps_more_crops(tmp_path):
    calls, started, resume = [], Event(), Event()
    target = tmp_path / "result.txt"
    pipeline = BlurPipeline(
        target, workers=4, expected=35,
        backend=_backend(calls, started=started, resume=resume),
    )
    pipeline.start()
    # Mimic out-of-order arrivals from the crop worker pool.
    for index in reversed(range(4)):
        pipeline.submit(index, tmp_path / f"{index:03}.jpg")
    assert started.wait(5), "the 4th saved crop must start calculation"
    for index in reversed(range(4, 35)):
        pipeline.submit(index, tmp_path / f"{index:03}.jpg")
    resume.set()
    result = pipeline.finish()
    assert result.queued == result.attempted == result.successful == 35
    assert result.failed == 0 and result.error == ""
    assert calls[0][0] == 4
    assert sum(count for count, _, _ in calls) == 35
    assert all(1 <= count <= 4 for count, _, _ in calls)
    assert all(workers == 4 for _, workers, _ in calls)
    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 35
    assert [line.split()[0] for line in lines] == [
        f"{index:03}.jpg" for index in range(35)
    ]


def test_calculation_failure_keeps_filename_and_error_sidecar(tmp_path):
    target = tmp_path / "result.txt"
    pipeline = BlurPipeline(
        target, workers=DEFAULT_CALC_WORKERS,
        backend=_backend([], fail_name="007.jpg"),
    )
    pipeline.start()
    for index in range(16):
        pipeline.submit(index, tmp_path / f"{index:03}.jpg")
    result = pipeline.finish()
    assert result.failed == 1 and result.successful == 15
    assert "007.jpg " + FAILURE_TEXT in target.read_text(encoding="utf-8")
    assert Path(result.errors_path).is_file()
    assert "007.jpg" in Path(result.errors_path).read_text(encoding="utf-8")


def test_calculation_worker_cap_is_independent_from_crop_workers(tmp_path):
    assert MAX_CALC_WORKERS == 4
    for value in (0, 5):
        with pytest.raises(ValueError, match="1～4"):
            BlurPipeline(tmp_path / "invalid.txt", workers=value, backend=_backend([]))



def test_calcdebug_v131_uses_one_local_run_folder_with_batch_sessions(tmp_path):
    import json

    calls = []
    root = tmp_path / "CalcDebug"

    def calculate(images, target, decoder, *, workers, progress, cancel, language,
                  calcdebug_root=None):
        assert calcdebug_root is not None, "the v1.3.1 API must receive calcdebug_root"
        session = Path(calcdebug_root) / f"batch_session_{len(calls)}"
        session.mkdir(parents=True)
        (session / "session_manifest.json").write_text("{}", encoding="utf-8")
        calls.append((len(images), str(calcdebug_root), str(session)))
        target.write_text(
            "".join(f"{p.name} 1.000000 2.000000 3.000000 4.000000\n" for p in images),
            encoding="utf-8",
        )
        for done, path in enumerate(images, 1):
            progress(done, len(images), path, True, "ok")
        return SimpleNamespace(
            completed=len(images), successful=len(images),
            failures=(), cancelled=False, calcdebug_path=session,
        )

    pipeline = BlurPipeline(
        tmp_path / "out.txt", workers=3, expected=19,
        backend=(calculate, Path("test_decoder.exe")),
        calcdebug_root=root,
    )
    pipeline.start()
    for index in range(19):
        pipeline.submit(index, tmp_path / f"{index:03d}.jpg")
    result = pipeline.finish()
    assert calls[0][0] == 4
    assert sum(batch[0] for batch in calls) == 19
    assert all(batch[0] <= 3 for batch in calls[1:])
    assert result.attempted == result.successful == 19
    assert Path(result.calcdebug_path).is_dir()
    assert Path(result.calcdebug_path).parent == root
    assert {parent for _, parent, _ in calls} == {result.calcdebug_path}
    manifest = json.loads(
        (Path(result.calcdebug_path) / "crop_pipeline_manifest.json").read_text(
            encoding="utf-8",
        )
    )
    assert len(manifest["calcdebug_sessions"]) == len(calls)
    assert manifest["images_successful"] == 19
    assert manifest["result_filenames"] == [f"{n:03d}.jpg" for n in range(19)]


def test_calcdebug_does_not_create_images_when_zero_crops_saved(tmp_path):
    root = tmp_path / "CalcDebug"
    pipeline = BlurPipeline(
        tmp_path / "out.txt", workers=2, backend=_backend([]),
        calcdebug_root=root,
    )
    pipeline.start()
    result = pipeline.finish()
    assert result.below_minimum
    assert result.calcdebug_path == ""
    assert not root.exists()


def test_calcdebug_path_rejects_existing_file(tmp_path):
    raw_file = tmp_path / "not_a_directory.txt"
    raw_file.write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="CalcDebug"):
        BlurPipeline(
            tmp_path / "out.txt", backend=_backend([]),
            calcdebug_root=raw_file,
        )



def test_calcdebug_warnings_are_kept_even_if_numeric_txt_succeeds(tmp_path):
    def calculate(images, target, decoder, *, workers, progress, cancel,
                  language, calcdebug_root=None):
        assert calcdebug_root is not None
        target.write_text(
            "".join(f"{p.name} 1.000000 2.000000 3.000000 4.000000\n" for p in images),
            encoding="utf-8",
        )
        errors_path = target.with_name(target.stem + "_errors.txt")
        errors_path.write_text("CalcDebug: synthetic PNG warning", encoding="utf-8")
        return SimpleNamespace(
            completed=len(images), successful=len(images), failures=(),
            cancelled=False, errors_path=errors_path,
            calcdebug_path=Path(calcdebug_root),
        )

    pipeline = BlurPipeline(
        tmp_path / "numeric.txt",
        backend=(calculate, Path("test_decoder.exe")),
        calcdebug_root=tmp_path / "CalcDebug",
    )
    pipeline.start()
    for i in range(16):
        pipeline.submit(i, tmp_path / f"{i:03d}.jpg")
    result = pipeline.finish()
    assert result.successful == 16 and result.failed == 0
    assert Path(result.errors_path).is_file()
    assert "synthetic PNG warning" in Path(result.errors_path).read_text(
        encoding="utf-8"
    )
    assert len((tmp_path / "numeric.txt").read_text(encoding="utf-8").splitlines()) == 16



def test_deferred_pipeline_does_not_require_four_images(tmp_path):
    calls = []
    pipeline = BlurPipeline(
        tmp_path / "safe-short.txt", workers=1, expected=2,
        defer_until_finish=True, backend=_backend(calls),
    )
    pipeline.start()
    pipeline.submit(1, tmp_path / "b.jpg")
    pipeline.submit(0, tmp_path / "a.jpg")
    result = pipeline.finish()
    assert not result.below_minimum
    assert result.successful == 2
    assert [batch[0] for batch in calls] == [2]
    assert (tmp_path / "safe-short.txt").read_text(encoding="utf-8").splitlines()[0].startswith("a.jpg ")
