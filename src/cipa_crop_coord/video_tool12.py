from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2

from .engine import Cancelled, Summary


@dataclass
class VideoRange:
    path: str
    fps: float
    frame_count: int
    duration: float
    start: float = 0.0
    end: float | None = None

    def normalized_end(self) -> float:
        value = self.duration if self.end is None else float(self.end)
        return max(0.0, min(value, self.duration))


VIDEO_TEXT = {
    "zh": {
        "open_failed": "无法打开视频：{path}",
        "invalid_video": "无法取得有效的视频帧率/帧数：{path}",
        "output_missing": "输出文件夹不存在或无法创建：{path}",
        "write_failed": "无法保存图片：{path}",
        "exporting": "{name}：导出第 {frame} 帧",
        "video_done": "{name}：完成，导出 {count} 张",
    },
    "ja": {
        "open_failed": "動画を開けません：{path}",
        "invalid_video": "有効なフレームレート/フレーム数を取得できません：{path}",
        "output_missing": "出力フォルダーを作成または使用できません：{path}",
        "write_failed": "画像を保存できません：{path}",
        "exporting": "{name}：フレーム {frame} を出力中",
        "video_done": "{name}：完了、{count} 枚出力",
    },
    "en": {
        "open_failed": "Cannot open video: {path}",
        "invalid_video": "Cannot read a valid frame rate/frame count: {path}",
        "output_missing": "Cannot create or use output folder: {path}",
        "write_failed": "Cannot save image: {path}",
        "exporting": "{name}: exporting frame {frame}",
        "video_done": "{name}: done, {count} images exported",
    },
}


def vtr(lang: str, key: str, **kwargs) -> str:
    text = VIDEO_TEXT.get(lang, VIDEO_TEXT["zh"])[key]
    return text.format(**kwargs)


def probe_video(path: str, lang: str = "zh") -> VideoRange:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        cap.release()
        raise ValueError(vtr(lang, "open_failed", path=path))
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        frame_count = int(round(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
    finally:
        cap.release()

    if not math.isfinite(fps) or fps <= 0 or frame_count <= 0:
        raise ValueError(vtr(lang, "invalid_video", path=path))
    duration = frame_count / fps
    return VideoRange(
        path=str(Path(path)),
        fps=fps,
        frame_count=frame_count,
        duration=duration,
        start=0.0,
        end=duration,
    )


def frame_bounds(video: VideoRange) -> tuple[int, int]:
    """Return zero-based [start, end) frame indices for the selected time range.

    Frame timestamps follow Tool 12's original 1-based counter semantics:
    saved frame number N corresponds to timestamp (N-1)/fps.
    """
    start = max(0.0, min(float(video.start), video.duration))
    end = max(start, video.normalized_end())
    eps = 1e-9
    start_index = int(math.ceil(start * video.fps - eps))
    end_index = int(math.ceil(end * video.fps - eps))
    start_index = max(0, min(start_index, video.frame_count))
    end_index = max(start_index, min(end_index, video.frame_count))
    return start_index, end_index


def _coerce_video_range(item) -> VideoRange:
    if isinstance(item, VideoRange):
        return item
    if isinstance(item, dict):
        return VideoRange(
            path=str(item["path"]),
            fps=float(item["fps"]),
            frame_count=int(item["frame_count"]),
            duration=float(item["duration"]),
            start=float(item.get("start", 0.0)),
            end=float(item.get("end", item["duration"])),
        )
    raise TypeError(f"Unsupported video range: {type(item)!r}")


def _write_jpeg_unicode(destination: Path, frame) -> bool:
    """Save JPEG with OpenCV's default JPEG encoder but Unicode-safe filesystem I/O.

    cv2.imwrite() on Windows can fail when the destination path contains Japanese/
    Chinese characters. cv2.imencode('.jpg', frame) uses the same OpenCV JPEG encoder
    and the same default parameters as cv2.imwrite without params; Python then writes
    the encoded bytes to the Unicode path.
    """
    ok, encoded = cv2.imencode(".jpg", frame)
    if not ok:
        return False
    try:
        destination.write_bytes(encoded.tobytes())
        return True
    except OSError:
        return False


def export_video_frames_tool12(
    videos: Iterable[VideoRange | dict],
    output_folder: str,
    progress=None,
    cancel=None,
    lang: str = "zh",
    workers: int = 1,
    debug: bool = False,
) -> Summary:
    """Export selected video ranges using Tool 12-compatible frame I/O.

    Compatibility-critical behavior is intentionally preserved:
      * cv2.VideoCapture reads the source frames.
      * every selected source frame is saved without resizing/conversion.
      * OpenCV's JPEG encoder is used without JPEG parameters (default settings).
      * file name is `<original video filename>_<original 1-based frame>.jpg`.

    The only save-path adaptation is Unicode-safe filesystem output on Windows so
    Japanese/Chinese names remain unchanged instead of causing cv2.imwrite to fail.

    For pixel/result fidelity, decoding still proceeds sequentially from frame 1, just as
    the source Tool 12 does. Frames before the selected start are decoded but not saved.
    """
    del workers, debug

    video_list = [_coerce_video_range(item) for item in videos]
    output = Path(output_folder)
    try:
        output.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValueError(vtr(lang, "output_missing", path=output)) from exc

    bounds = [frame_bounds(video) for video in video_list]
    total = sum(end - start for start, end in bounds)
    summary = Summary(total=total, output_path=str(output))
    done = 0

    for video, (start_index, end_index) in zip(video_list, bounds):
        if cancel and cancel():
            raise Cancelled()

        cap = cv2.VideoCapture(video.path)
        if not cap.isOpened():
            cap.release()
            summary.failed += end_index - start_index
            if progress:
                progress(done, total, vtr(lang, "open_failed", path=video.path))
            continue

        exported_this_video = 0
        frame_index = 0
        try:
            while frame_index < end_index:
                if cancel and cancel():
                    raise Cancelled()

                ret, frame = cap.read()
                if not ret:
                    remaining = max(0, end_index - max(frame_index, start_index))
                    summary.failed += remaining
                    break

                if frame_index >= start_index:
                    frame_number = frame_index + 1
                    filename = f"{Path(video.path).name}_{str(frame_number).zfill(5)}.jpg"
                    destination = output / filename

                    # Keep Tool 12 image/encoding semantics, but make Japanese paths safe.
                    if _write_jpeg_unicode(destination, frame):
                        summary.succeeded += 1
                        exported_this_video += 1
                    else:
                        summary.failed += 1

                    done += 1
                    if progress:
                        progress(
                            done,
                            total,
                            vtr(
                                lang,
                                "exporting",
                                name=Path(video.path).name,
                                frame=frame_number,
                            ),
                        )

                frame_index += 1
        finally:
            cap.release()

        if progress:
            progress(
                done,
                total,
                vtr(
                    lang,
                    "video_done",
                    name=Path(video.path).name,
                    count=exported_this_video,
                ),
            )

    return summary
