"""Standalone FindsBlur 1.1 calculation and official-format result writer.

The existing Phase 11--13 reconstruction is the computation engine. Its
source remains unmodified. This wrapper fixes the native parameters and uses
an IJG 8c RGB decoder. The official FindsBlur TXT is NEVER used as input.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from time import perf_counter
from typing import Callable
from .accelerate import patched_normalization
from .i18n import localize_error, tr
from .calcdebug import create_session, write_image_report, write_session_report

EXTENSIONS = {'.jpg', '.jpeg', '.bmp'}
FAILURE_MESSAGE = 'ブレ度合測定に失敗しました。'


class CalculationError(RuntimeError):
    pass


@dataclass(frozen=True)
class BatchResult:
    output: Path
    total: int
    completed: int
    successful: int
    failures: tuple[tuple[str, str], ...]
    cancelled: bool
    seconds: float
    errors_path: Path | None
    calcdebug_path: Path | None = None


def collect_images(mode: str, user_path: str) -> list[Path]:
    """Resolve the ACTUAL editable GUI field each time Start is pressed."""
    raw = user_path.strip().strip('"').strip("'").strip()
    if not raw:
        raise CalculationError('请选择或填写图片文件夹/图片路径。')
    path = Path(raw).expanduser().resolve()
    if mode == 'folder':
        if not path.is_dir():
            raise CalculationError('找不到图片文件夹：' + str(path))
        candidates = (p for p in path.rglob('*') if p.is_file() and p.suffix.lower() in EXTENSIONS)
    elif mode == 'single':
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
            raise CalculationError('请输入存在的 JPG/JPEG/BMP 文件路径：' + str(path))
        candidates = (path,)
    else:
        raise CalculationError('无效的图片模式：' + mode)
    images = sorted(set(candidates), key=lambda p: (p.name.casefold(), str(p).casefold()))
    if not images:
        raise CalculationError('没有找到 JPG、JPEG 或 BMP 图片。')
    seen: dict[str, Path] = {}
    for p in images:
        name = p.name.casefold()
        if name in seen and seen[name] != p:
            raise CalculationError('两个子文件夹存在同名图片，官方 TXT 无法区分：\n'+str(seen[name])+'\n'+str(p))
        seen[name] = p
    return images


def proposed_output(mode: str, source: str) -> Path | None:
    try:
        path = Path(source.strip().strip('"')).expanduser()
        if mode == 'folder' and path.is_dir():
            return path/'FindsBlur_Result.txt'
        if mode == 'single' and path.is_file():
            return path.parent/(path.stem+'_FindsBlur.txt')
    except (OSError, ValueError):
        pass
    return None


def fixed_parameters(original):
    """Captured native arguments; short-side proportional mapping (experimental beyond captured sizes)."""
    def corrected(width: int, height: int):
        p = original(width, height)
        s = min(width, height)
        half_up = lambda x: int(x + 0.5)
        return replace(
            p,
            field_0x898=half_up(s * 0.05),  # nearby junction cutoff
            field_0x848=half_up(s * 0.10),  # maximum scan width
            x_margin=half_up(s * 0.20),
            y_margin=half_up(s * (7.0/30.0 + 0.05)),
            hole_threshold=half_up(s * 0.05),
        )
    return corrected


def verify_captured_parameters(original):
    p = fixed_parameters(original)(1170, 779)
    measured = (p.field_0x898, p.field_0x848, p.x_margin,
                p.y_margin, p.hole_threshold, p.field_0x844,
                p.ring_start, p.ring_width)
    expected = (39, 78, 156, 221, 39, 12, 97, 70)
    if measured != expected:
        raise CalculationError(f'原生参数自检不通过：{measured}，预期 {expected}')


def _decoder_creationflags(platform: str | None = None) -> int:
    """Hide the console for each IJG 8c JPEG decoder child on Windows.

    This affects *only* Windows process creation. The same executable,
    arguments, stdout capture, JPEG pixel bytes, and numerical pipeline
    remain unchanged. On Linux/macOS creationflags=0 is harmless.
    """
    platform = sys.platform if platform is None else platform
    return getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000) if platform == 'win32' else 0


class IJG8cReader:
    """Use the byte-parity IJG 8c settings established by previous native capture."""
    def __init__(self, executable: Path, workdir: Path):
        self.executable = executable
        self.workdir = workdir
        self.workdir.mkdir(parents=True, exist_ok=True)

    def open(self, filename, *args, **kwargs):
        from PIL import Image
        path = Path(filename)
        if path.suffix.lower() not in ('.jpg', '.jpeg'):
            return Image.open(filename, *args, **kwargs)
        if args or kwargs:
            raise CalculationError('IJG 8c 不接受额外 Image.open 参数。')
        with tempfile.TemporaryDirectory(prefix='jpg_', dir=self.workdir) as tmp:
            scratch = Path(tmp)
            # IJG 8c Windows narrow fopen works reliably with ASCII-only paths.
            source = path
            if not str(path).isascii():
                source = scratch/'input.jpg'
                shutil.copyfile(path, source)  # no recompression
            prefix = scratch/'decoded'
            cmd = [str(self.executable), str(source), str(prefix), 'islow', '1', '1']
            try:
                run = subprocess.run(cmd, capture_output=True, text=True,
                                     errors='replace', check=False, timeout=300,
                                     creationflags=_decoder_creationflags())
            except subprocess.TimeoutExpired as exc:
                raise CalculationError('IJG 8c 解码超时：' + path.name) from exc
            if run.returncode or not re.search(r'\bJPEG_LIB_VERSION=80\b', run.stdout):
                raise CalculationError('IJG 8c 解码失败：'+path.name+' '+(run.stderr+run.stdout)[-400:])
            match = re.search(r'WIDTH=(\d+)\s+HEIGHT=(\d+)', run.stdout)
            if not match:
                raise CalculationError('IJG 8c 没有返回尺寸：' + path.name)
            w,h = map(int, match.groups())
            if w <= 0 or h <= 0 or w*h > 80_000_000:
                raise CalculationError('图片尺寸不受支持：' + path.name)
            rgb_file = Path(f'{prefix}_RGB.raw')
            if not rgb_file.is_file() or rgb_file.stat().st_size != w*h*3:
                raise CalculationError('IJG 8c RGB 缓冲区损坏：' + path.name)
            image = Image.frombytes('RGB', (w,h), rgb_file.read_bytes())
            image.format = 'JPEG'
            return image


@contextmanager
def substitute_runtime(reader: IJG8cReader):
    # Patch imported references only for this batch; restore on exit.
    import phase11.replay_407170_4077eb as replay
    from phase11.native_parameters import from_dimensions as original_dimensions
    verify_captured_parameters(original_dimensions)
    original_image = replay.Image
    original_dimensions_ref = replay.from_dimensions
    class ReaderShim:
        open = staticmethod(reader.open)
    replay.Image = ReaderShim
    replay.from_dimensions = fixed_parameters(original_dimensions_ref)
    try:
        with patched_normalization():
            yield
    finally:
        replay.Image = original_image
        replay.from_dimensions = original_dimensions_ref


def numeric_line(image: Path, values) -> str:
    numbers = list(values)
    if len(numbers) != 4 or not all(math.isfinite(float(n)) for n in numbers):
        raise CalculationError('未返回四个有效数值。')
    return image.name + ' ' + ' '.join(f'{float(n):.6f}' for n in numbers)


def failure_line(image: Path) -> str:
    return image.name + ' ' + FAILURE_MESSAGE


def _atomic_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',newline='\r\n',
                                         dir=path.parent,prefix='.fb_',suffix='.tmp',delete=False) as f:
            name=f.name
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if name:
            Path(name).unlink(missing_ok=True)


def calculate(images: list[Path], target: Path, decoder: Path, *, workers=2,
              progress: Callable | None=None, cancel: Callable | None=None,
              workdir: Path | None=None, language: str='zh',
              calcdebug_root: Path | None=None) -> BatchResult:
    """Produce one output line per *attempted* image in filename order.

    If the user cancels, unattempted images are never falsely reported as
    measurement failures. A detailed error sidecar is written when needed.
    """
    images = list(images)
    if not images:
        raise CalculationError('请选择图片。')
    if workers not in (1,2,3,4):
        raise CalculationError('并行数量必须为 1～4。')
    if not decoder.is_file():
        raise CalculationError('缺少本机已编译的 IJG8c 解码器：'+str(decoder))
    target = Path(target).expanduser().resolve()
    if calcdebug_root is not None and Path(calcdebug_root).expanduser().resolve() == target:
        raise CalculationError('CalcDebug 文件夹路径不能与 TXT 文件路径相同。')
    if target.suffix.lower() != '.txt':
        raise CalculationError('输出名称必须以 .txt 结尾。')
    if target in images:
        raise CalculationError('输出文件不能覆盖输入图片。')
    start = perf_counter()
    if workdir is None:
        workdir = Path(os.environ.get('LOCALAPPDATA') or tempfile.gettempdir())/'FindsBlur-Standalone'/'Work'
    workdir.mkdir(parents=True,exist_ok=True)
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root/'phase5') not in sys.path:
        sys.path.insert(0,str(project_root/'phase5'))
    from standalone.__main__ import _analyze_without_oracle
    debug_session = create_session(calcdebug_root, target, images) if calcdebug_root is not None else None
    debug_warnings: dict[Path,str] = {}
    passed: dict[Path,str] = {}
    failed: dict[Path,str] = {}
    attempted: set[Path] = set()
    cancelled = False
    completed = 0

    def one(p: Path):
        debug_dir = debug_session.for_image(p) if debug_session is not None else None
        data = None
        error = None
        try:
            data = _analyze_without_oracle(p, 'calculate', debug_dir)
            values = data.get('candidate_values')
            if values is None:
                # Reveal the specific rejected selection only in error logs;
                # reference TXT values are never used in this branch.
                selection=(data.get('details') or {}).get('native_normal_branch_402b90') or {}
                reason=selection.get('reason')
                raise CalculationError(str(data.get('status'))+'/'+str(data.get('stage')) +
                                       (('/' + str(reason)) if reason else ''))
            line = numeric_line(p,values)
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
            line = failure_line(p)
        if debug_dir is not None:
            try:
                write_image_report(debug_dir, p, data, error)
            except Exception as exc:
                # Optional report errors must not corrupt official TXT results.
                debug_warnings[p] = f'{type(exc).__name__}: {exc}'
        return p, line, error

    def record(result):
        nonlocal completed
        p,text,error=result
        attempted.add(p)
        if error: failed[p]=error
        else: passed[p]=text
        completed+=1
        if progress:
            progress(completed,len(images),p,error is None,error or text)

    with tempfile.TemporaryDirectory(prefix='fb_session_',dir=workdir) as wd:
        reader=IJG8cReader(decoder,Path(wd))
        with substitute_runtime(reader):
            # Initial JIT warm-up is kept sequential, then remaining images
            # are processed by a small, fixed worker pool.
            if not cancel or not cancel():
                record(one(images[0]))
            else:
                cancelled=True
            if not cancelled and len(images)>1:
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    pending={}
                    for p in images[1:]:
                        if cancel and cancel():
                            cancelled=True
                            break
                        pending[executor.submit(one,p)]=p
                    for future in as_completed(pending):
                        if cancel and cancel():
                            cancelled=True
                        if future.cancelled():
                            continue
                        record(future.result())
    # Never change sequence as a side effect of thread completion order.
    lines = [passed[p] if p in passed else failure_line(p) for p in images if p in attempted]
    if not cancelled and len(lines)!=len(images):
        raise CalculationError('内部错误：输出记录数与输入图片数不同。')
    _atomic_text(target, '\n'.join(lines)+'\n' if lines else '')
    errors = tuple((p.name,failed[p]) for p in images if p in failed)
    error_file=target.with_name(target.stem+'_errors.txt')
    if errors or cancelled or debug_warnings:
        msg=[tr(language, 'sidecar_title'),
             tr(language, 'sidecar_total', count=len(images)),
             tr(language, 'sidecar_success', count=len(passed)),
             tr(language, 'sidecar_failed', count=len(failed)),
             tr(language, 'sidecar_cancelled', cancelled=tr(language, 'yes' if cancelled else 'no')),'']
        msg += [f'{n}\n  {localize_error(e, language)}' for n,e in errors]
        if debug_warnings:
            msg += ['', 'CalcDebug:', *[f'{p.name}\n  {reason}' for p,reason in debug_warnings.items()]]
        _atomic_text(error_file,'\n'.join(msg)+'\n')
    else:
        error_file.unlink(missing_ok=True)
        error_file=None
    debug_path = None
    if debug_session is not None:
        try:
            debug_path = write_session_report(debug_session,images,attempted,failed,target,cancelled)
        except Exception as exc:
            # The optional session index may fail (e.g. full disk); preserve the
            # numeric output, and surface the problem in the normal error log.
            debug_path = debug_session.root
            try:
                previous = error_file.read_text(encoding='utf-8') if error_file else ''
                error_file = target.with_name(target.stem+'_errors.txt')
                _atomic_text(error_file, previous +
                    f'\nCalcDebug session report failed: {type(exc).__name__}: {exc}\n')
            except OSError:
                pass
    return BatchResult(target,len(images),len(attempted),len(passed),errors,
                       cancelled,round(perf_counter()-start,3),error_file,debug_path)
