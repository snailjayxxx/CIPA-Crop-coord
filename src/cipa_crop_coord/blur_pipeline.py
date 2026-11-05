"""Optional streaming FindsBlur bridge for Similar Area Crop.

The independent CIPA-Calc repository is read-only. Its source and IJG 8c
decoder are provided at local build time, not copied into this public repo.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from typing import Callable

from .locales import tr

MIN_CALC_IMAGES = 16
MAX_CALC_WORKERS = 4
DEFAULT_CALC_WORKERS = 2
FAILURE_TEXT = "ブレ度合測定に失敗しました。"
_SENTINEL = object()


@dataclass(frozen=True)
class BlurResult:
    requested: bool
    output: str
    queued: int
    attempted: int
    successful: int
    failed: int
    below_minimum: bool
    cancelled: bool
    error: str = ""
    errors_path: str = ""
    calcdebug_path: str = ""


def load_calculator():
    """Load the recovered implementation without starting its separate GUI.

    Packaged builds include the private modules as local PyInstaller data.
    Development runs may point CIPA_CALC_ROOT to a sibling checkout.
    """
    env_root = os.environ.get("CIPA_CALC_ROOT", "").strip()
    roots = []
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        # The executable's bundled sources take precedence over any developer
        # environment variable retained on the machine at runtime.
        roots.append(Path(frozen_root))
    if env_root:
        roots.append(Path(env_root).expanduser().resolve())
    else:
        project = Path(__file__).resolve().parents[2]
        roots.extend((project.parent / "CIPA-Calc", project / "CIPA-Calc"))
    root = next(
        (
            candidate for candidate in roots
            if (candidate / "standalone_gui" / "core.py").is_file()
            and (candidate / "standalone" / "__main__.py").is_file()
            and (candidate / "phase11" / "replay_407170_4077eb.py").is_file()
        ),
        None,
    )
    if root is None:
        raise RuntimeError(
            "FindsBlur 计算核心不可用：请使用包含 CIPA-Calc 的集成构建，"
            "或在本地开发时设置 CIPA_CALC_ROOT。"
        )
    decoder_env = os.environ.get("FINDSBLUR_IJG8C_EXE", "").strip()
    bundled_decoder = root / "_work" / "IJG8c" / "bin" / "ijg8c_rgb_probe.exe"
    if frozen_root and root == Path(frozen_root) and bundled_decoder.is_file():
        # A self-contained integrated EXE must use the decoder it shipped
        # with, even on the developer's PC where an override is still set.
        decoder = bundled_decoder
    else:
        decoder = (
            Path(decoder_env).expanduser().resolve()
            if decoder_env else bundled_decoder
        )
    if not decoder.is_file():
        raise RuntimeError("未找到 IJG 8c 解码器：" + str(decoder))
    for folder in (root, root / "phase5"):
        if str(folder) not in sys.path:
            sys.path.insert(0, str(folder))
    from standalone_gui.core import calculate
    return calculate, decoder


def _atomic_write(path: Path, contents: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\r\n",
            dir=path.parent, prefix=".findsblur_", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class BlurPipeline:
    """Start after 16 saved crops, then consume new crops on another thread.

    The calculation core retains its own independently capped worker pool.
    Results are keyed by original input index, never completion order.
    """

    def __init__(
        self,
        output: str | Path,
        *,
        workers: int = DEFAULT_CALC_WORKERS,
        expected: int = 0,
        progress: Callable[[int, int, str], None] | None = None,
        cancel: Callable[[], bool] | None = None,
        lang: str = "zh",
        backend=None,
        calcdebug_root: str | Path | None = None,
    ):
        if not 1 <= int(workers) <= MAX_CALC_WORKERS:
            raise ValueError("抖动量计算并行数必须在 1～4 之间。")
        self.output = Path(output).expanduser().resolve()
        if self.output.suffix.lower() != ".txt":
            raise ValueError("抖动量计算结果必须是 .txt 文件。")
        self.calcdebug_root = (
            Path(calcdebug_root).expanduser().resolve()
            if calcdebug_root is not None else None
        )
        if self.calcdebug_root is not None:
            if self.calcdebug_root == self.output or self.calcdebug_root.is_file():
                raise ValueError("CalcDebug 保存位置必须是文件夹，不能使用 TXT 文件路径。")
        self.workers = int(workers)
        self.expected = max(0, int(expected))
        self.progress = progress
        self.cancel = cancel
        self.lang = lang
        # Resolve the optional private backend only once the 16-image gate opens.
        # Missing computation dependencies must not prevent cropping.
        self.calculate, self.decoder = backend if backend is not None else (None, None)
        self._queue = Queue()
        self._thread = threading.Thread(
            target=self._consume, name="findsblur-consumer", daemon=False
        )
        self._lock = threading.Lock()
        self._closed = False
        self._queued = 0
        self._attempted = 0
        self._successful = 0
        self._failed = 0
        self._started = False
        self._below_minimum = False
        self._cancelled = False
        self._error = ""
        self._lines: dict[int, str] = {}
        self._failures: list[tuple[str, str]] = []
        self._calc_sidecar_warnings: list[str] = []
        self._errors_path = ""
        self._debug_run_path = ""
        self._debug_sessions: list[str] = []

    def start(self):
        self._thread.start()

    def submit(self, index: int, saved_path: str | Path):
        with self._lock:
            if self._closed:
                raise RuntimeError("抖动量计算队列已关闭。")
            self._queued += 1
            self._queue.put((int(index), Path(saved_path)))

    def finish(self) -> BlurResult:
        with self._lock:
            if not self._closed:
                self._closed = True
                self._queue.put(_SENTINEL)
        self._thread.join()
        return BlurResult(
            requested=True,
            output=str(self.output),
            queued=self._queued,
            attempted=self._attempted,
            successful=self._successful,
            failed=self._failed,
            below_minimum=self._below_minimum,
            cancelled=self._cancelled,
            error=self._error,
            errors_path=self._errors_path,
            calcdebug_path=self._debug_run_path,
        )

    def _emit(self, completed: int, detail: str):
        if self.progress:
            self.progress(completed, max(self.expected, completed, 1), detail)

    def _consume(self):
        pending: list[tuple[int, Path]] = []
        try:
            with tempfile.TemporaryDirectory(prefix="findsblur_batches_") as folder:
                while True:
                    item = self._queue.get()
                    if item is _SENTINEL:
                        if not self._started:
                            self._below_minimum = True
                            self._emit(0, tr(self.lang, "blur_under_min", count=MIN_CALC_IMAGES))
                        elif self.cancel and self.cancel():
                            self._cancelled = True
                        elif pending:
                            self._process(pending, Path(folder))
                        break
                    if self._cancelled or self._error:
                        continue
                    pending.append(item)
                    # First 16 saved crops open the pipeline; afterwards, smaller
                    # batches allow calculation to overlap ongoing crop tasks.
                    required = MIN_CALC_IMAGES if not self._started else max(1, self.workers)
                    if len(pending) >= required:
                        self._started = True
                        self._process(pending, Path(folder))
                        pending = []
                        if self._cancelled:
                            break
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"
            self._emit(self._attempted, tr(self.lang, "blur_error_line", error=self._error))
        finally:
            if self._debug_run_path:
                # Make the many upstream CalcDebug batch sessions discoverable
                # under one local folder without changing the private engine.
                manifest = {
                    "tool": "CIPA Crop & Coord / FindsBlur CalcDebug",
                    "output_txt": str(self.output),
                    "saved_crops": self._queued,
                    "images_attempted": self._attempted,
                    "images_successful": self._successful,
                    "images_failed": self._failed,
                    "cancelled": self._cancelled,
                    "error": self._error,
                    "calcdebug_sessions": self._debug_sessions,
                    "calculator_sidecar_count": len(self._calc_sidecar_warnings),
                    "result_filenames": [
                        self._lines[i].split(" ", 1)[0]
                        for i in sorted(self._lines)
                    ],
                    "raw_images_uploaded": False,
                }
                try:
                    _atomic_write(
                        Path(self._debug_run_path) / "crop_pipeline_manifest.json",
                        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                    )
                except OSError:
                    pass
            if self._started and not self._error:
                # Final progress uses the number of actually saved crops, not
                # the number of source images that might have failed cropping.
                self.expected = self._queued
                self._emit(self._attempted, tr(self.lang, "blur_queue_complete"))
            if self._started or self._error:
                if self._failures or self._error or self._calc_sidecar_warnings:
                    errors = [f"{filename}: {reason}" for filename, reason in self._failures]
                    if self._calc_sidecar_warnings:
                        errors += [
                            "=== FindsBlur batch diagnostics (v1.3.1) ===",
                            *self._calc_sidecar_warnings,
                        ]
                    if self._error:
                        errors.insert(0, self._error)
                    errors_path = self.output.with_name(self.output.stem + "_errors.txt")
                    try:
                        _atomic_write(errors_path, "\n".join(errors) + "\n")
                        self._errors_path = str(errors_path)
                    except OSError:
                        pass
                elif self._lines:
                    self.output.with_name(
                        self.output.stem + "_errors.txt"
                    ).unlink(missing_ok=True)

    def _process(self, batch: list[tuple[int, Path]], workdir: Path):
        batch = sorted(batch, key=lambda pair: pair[0])
        if self.calculate is None:
            self.calculate, self.decoder = load_calculator()
        temp_txt = workdir / f"batch_{self._attempted:06d}.txt"
        initial_done = self._attempted

        def on_progress(done, total, filename, ok, details):
            self._emit(
                initial_done + done,
                tr(self.lang, "blur_progress_ok" if ok else "blur_progress_fail", name=filename.name),
            )

        calculation_options = {
            "workers": self.workers,
            "progress": on_progress,
            "cancel": self.cancel,
            "language": self.lang,
        }
        if self.calcdebug_root is not None:
            if not self._debug_run_path:
                self.calcdebug_root.mkdir(parents=True, exist_ok=True)
                self._debug_run_path = tempfile.mkdtemp(
                    prefix="crop_calcdebug_", dir=self.calcdebug_root
                )
            calculation_options["calcdebug_root"] = Path(self._debug_run_path)
        result = self.calculate(
            [path for _, path in batch],
            temp_txt,
            self.decoder,
            **calculation_options,
        )
        session_path = getattr(result, "calcdebug_path", None)
        if session_path is not None:
            self._debug_sessions.append(str(session_path))
        # Upstream may write non-numeric CalcDebug warnings even when all
        # four-column measurements succeed. Preserve these sidecars before
        # the temporary batch folder is deleted.
        upstream_errors = getattr(result, "errors_path", None)
        if upstream_errors is not None and Path(upstream_errors).is_file():
            self._calc_sidecar_warnings.append(
                Path(upstream_errors).read_text(encoding="utf-8-sig")
            )
        if not temp_txt.is_file():
            raise RuntimeError("计算核心未生成批次 TXT：" + str(temp_txt))
        lines = temp_txt.read_text(encoding="utf-8-sig").splitlines()
        recovered: dict[int, str] = {}
        for line in lines:
            matches = [
                idx for idx, path in batch if line.startswith(path.name + " ")
            ]
            if len(matches) != 1 or matches[0] in recovered:
                raise RuntimeError("计算 TXT 存在未知或重复的图片名：" + line[:120])
            recovered[matches[0]] = line
        if not result.cancelled and len(recovered) != len(batch):
            raise RuntimeError("计算结果行数与本批裁切图片数量不一致。")
        self._lines.update(recovered)
        self._attempted += len(recovered)
        self._successful += result.successful
        self._failed += len(result.failures)
        self._failures.extend(result.failures)
        self._cancelled = bool(result.cancelled)
        if self._lines:
            output_lines = [self._lines[index] for index in sorted(self._lines)]
            _atomic_write(self.output, "\n".join(output_lines) + "\n")
        self._emit(self._attempted, tr(self.lang, "blur_batch_complete"))
