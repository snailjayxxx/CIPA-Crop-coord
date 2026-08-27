from pathlib import Path

import numpy as np

from cipa_crop_coord.video_tool12 import VideoRange, export_video_frames_tool12, frame_bounds


def test_frame_bounds_keep_original_frame_numbers():
    video = VideoRange(
        path="sample.MP4",
        fps=30.0,
        frame_count=300,
        duration=10.0,
        start=1.0,
        end=2.0,
    )
    assert frame_bounds(video) == (30, 60)


def test_full_range_contains_all_frames():
    video = VideoRange(
        path="sample.MP4",
        fps=29.97,
        frame_count=300,
        duration=300 / 29.97,
        start=0.0,
        end=300 / 29.97,
    )
    assert frame_bounds(video) == (0, 300)


def test_export_preserves_unicode_video_name_and_original_frame_index(monkeypatch, tmp_path):
    frames = [np.full((2, 3, 3), value, dtype=np.uint8) for value in range(8)]
    encoded_values = []

    class FakeCapture:
        def __init__(self, _path):
            self.index = 0

        def isOpened(self):
            return True

        def read(self):
            if self.index >= len(frames):
                return False, None
            frame = frames[self.index]
            self.index += 1
            return True, frame

        def release(self):
            pass

    def fake_imencode(ext, frame, *args):
        assert ext == ".jpg"
        assert args == ()
        value = int(frame[0, 0, 0])
        encoded_values.append(value)
        return True, np.array([0xFF, 0xD8, value, 0xFF, 0xD9], dtype=np.uint8)

    monkeypatch.setattr("cipa_crop_coord.video_tool12.cv2.VideoCapture", FakeCapture)
    monkeypatch.setattr("cipa_crop_coord.video_tool12.cv2.imencode", fake_imencode)

    output = tmp_path / "日本語フォルダ" / "frame_output"
    video = VideoRange(
        path="テスト動画_漢字かなカナ.MP4",
        fps=2.0,
        frame_count=8,
        duration=4.0,
        start=1.0,
        end=3.0,
    )
    summary = export_video_frames_tool12([video], str(output))

    expected_names = [
        "テスト動画_漢字かなカナ.MP4_00003.jpg",
        "テスト動画_漢字かなカナ.MP4_00004.jpg",
        "テスト動画_漢字かなカナ.MP4_00005.jpg",
        "テスト動画_漢字かなカナ.MP4_00006.jpg",
    ]
    assert sorted(path.name for path in output.glob("*.jpg")) == sorted(expected_names)
    assert encoded_values == [2, 3, 4, 5]
    assert summary.succeeded == 4
    assert summary.failed == 0
