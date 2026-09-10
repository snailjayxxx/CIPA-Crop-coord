from pathlib import Path
from string import Formatter

import cv2
import pytest

from cipa_crop_coord.image_to_video import TEXT, create_video_from_images, resolve_output_file
from cipa_crop_coord.ui_image_to_video import TEXT as UI_TEXT


@pytest.mark.parametrize("table", [TEXT, UI_TEXT])
def test_translations_have_matching_keys_and_format_fields(table):
    def fields(value):
        return {(field, spec) for _, field, spec, _ in Formatter().parse(value) if field}

    for lang in ("ja", "en"):
        assert table[lang].keys() == table["zh"].keys()
        for key, value in table[lang].items():
            assert value.strip()
            assert fields(value) == fields(table["zh"][key])


@pytest.mark.parametrize("lang", ["zh", "ja", "en"])
def test_parameter_and_encoder_errors_use_selected_language(tmp_path, monkeypatch, lang):
    output = str(tmp_path / "result.mp4")
    for fps, count, key in [(0, 1, "fps"), (float("nan"), 1, "fps"), (10, -1, "count"), (10, 1.5, "count"), (10, 0, "empty")]:
        with pytest.raises(ValueError) as error:
            create_video_from_images(str(tmp_path), output, fps, count, lang=lang)
        assert str(error.value) == TEXT[lang][key]

    with pytest.raises(ValueError) as error:
        resolve_output_file("", str(tmp_path), lang)
    assert str(error.value) == TEXT[lang]["output"]

    class UnavailableEncoder:
        def isOpened(self):
            return False

        def release(self):
            pass

    monkeypatch.setattr(cv2, "VideoWriter", lambda *args: UnavailableEncoder())
    with pytest.raises(RuntimeError) as error:
        create_video_from_images(str(tmp_path), output, 10, 1, lang=lang)
    assert str(error.value) == TEXT[lang]["encoder"]
    assert not Path(output).exists()


@pytest.mark.parametrize("lang", ["zh", "ja", "en"])
def test_empty_folder_produces_requested_black_frames_with_translated_progress(tmp_path, lang):
    output = tmp_path / "black.mp4"
    messages = []
    summary = create_video_from_images(
        str(tmp_path), str(output), 10, 2, lang=lang,
        cancel=lambda: False, progress=lambda current, total, message: messages.append(message),
    )
    assert summary.succeeded == summary.total == 2
    assert len(messages) == 2
    assert all(TEXT[lang]["black"] in message for message in messages)
    capture = cv2.VideoCapture(str(output))
    try:
        assert capture.isOpened()
        assert capture.get(cv2.CAP_PROP_FPS) == 10
        for _ in range(2):
            ok, frame = capture.read()
            assert ok
            assert frame.shape == (1080, 1920, 3)
            assert frame.max() < 5
        assert not capture.read()[0]
    finally:
        capture.release()
