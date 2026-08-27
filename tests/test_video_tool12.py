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


def test_export_uses_original_video_name_and_original_frame_index(monkeypatch, tmp_path):
    frames = [np.full((2, 3, 3), value, dtype=np.uint8) for value in range(8)]
    writes = []

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

    def fake_imwrite(path, frame, *args):
        assert args == ()
        writes.append((Path(path).name, int(frame[0, 0, 0])))
        return True

    monkeypatch.setattr("cipa_crop_coord.video_tool12.cv2.VideoCapture", FakeCapture)
    monkeypatch.setattr("cipa_crop_coord.video_tool12.cv2.imwrite", fake_imwrite)

    video = VideoRange(
        path="C:/data/C2241-GIRI.MP4",
        fps=2.0,
        frame_count=8,
        duration=4.0,
        start=1.0,
        end=3.0,
    )
    summary = export_video_frames_tool12([video], str(tmp_path))

    assert [name for name, _ in writes] == [
        "C2241-GIRI.MP4_00003.jpg",
        "C2241-GIRI.MP4_00004.jpg",
        "C2241-GIRI.MP4_00005.jpg",
        "C2241-GIRI.MP4_00006.jpg",
    ]
    assert [value for _, value in writes] == [2, 3, 4, 5]
    assert summary.succeeded == 4
    assert summary.failed == 0
