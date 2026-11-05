"""Optional vectorized ROI histogram normalization with byte-for-byte self-check.

No numerical changes are accepted without reproducing the scalar original on
its first invocation in each batch. Subsequent exceptions restore the input
before falling back to the original implementation.
"""
from __future__ import annotations
from contextlib import contextmanager
import numpy as np


def normalize_histogram_fast(pixels, *, stride, height, rect, low_fraction, high_fraction):
    from phase3.mask_stage import NormalizationResult, _validate_geometry
    _validate_geometry(pixels,stride,height,(rect,))
    if rect.empty(): raise ValueError('empty histogram ROI')
    if not (0 <= low_fraction < 1 and 0 <= high_fraction < 1):
        raise ValueError('invalid histogram fractions')
    buf=np.frombuffer(pixels,dtype=np.uint8,count=stride*height).reshape(height,stride)
    view=buf[rect.y0:rect.y1+1,rect.x0:rect.x1+1]
    hist=np.bincount(view.ravel(),minlength=256)
    n=(rect.x1-rect.x0+1)*(rect.y1-rect.y0+1)
    black=0;count=0
    for i in range(256):
        count+=int(hist[i])
        if count > n*low_fraction: black=i;break
    white=255;count=0
    for i in range(255,-1,-1):
        count+=int(hist[i])
        if count > n*high_fraction: white=i;break
    if black>=white:return NormalizationResult(False,black,white)
    den=white-black
    lut=np.fromiter((max(0,min(255,(2*(i-black)*255+den)//(2*den)))
                     for i in range(256)),dtype=np.uint8,count=256)
    view[:,:]=lut[view]
    return NormalizationResult(True,black,white)


@contextmanager
def patched_normalization():
    import phase11.replay_407170_4077eb as replay
    original=replay.normalize_histogram_404d00
    verified=False
    fallback=False

    def replacement(buf,**kwargs):
        nonlocal verified,fallback
        if fallback:return original(buf,**kwargs)
        original_buf=bytearray(buf)
        if not verified:
            expected_buf=bytearray(buf)
            expected=original(expected_buf,**kwargs)
            try:
                candidate=normalize_histogram_fast(buf,**kwargs)
                if candidate==expected and buf==expected_buf:
                    verified=True
                    return candidate
            except Exception:
                pass
            buf[:]=expected_buf
            fallback=True
            return expected
        try:
            return normalize_histogram_fast(buf,**kwargs)
        except Exception:
            buf[:]=original_buf
            fallback=True
            return original(buf,**kwargs)

    replay.normalize_histogram_404d00=replacement
    try:yield
    finally:replay.normalize_histogram_404d00=original
