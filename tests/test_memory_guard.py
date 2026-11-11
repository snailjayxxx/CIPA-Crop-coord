"""Synthetic memory-budget checks; no personal photos or native decoder required."""
from __future__ import annotations

import pytest
from PIL import Image

from cipa_crop_coord.memory_guard import (
    GIB, MemoryBudgetError, choose_workers, largest_image_pixels,
)


def test_maximum_8_plus_4_does_not_overcommit_eight_gig_available_memory():
    plan = choose_workers(
        8, 4,
        source_pixels=66_000_000,
        crop_pixels=4_000_000,
        calc_enabled=True,
        available_bytes=8 * GIB,
        cpu_count=16,
    )
    assert 1 <= plan.crop_workers < 8
    assert 1 <= plan.calc_workers <= 4
    assert plan.adjusted
    assert not plan.defer_calculation


def test_calc_can_be_deferred_without_disabling_any_result():
    plan = choose_workers(
        8, 4, source_pixels=66_000_000, crop_pixels=66_000_000,
        calc_enabled=True, available_bytes=6 * GIB, cpu_count=16,
    )
    assert plan.defer_calculation
    assert plan.crop_workers >= 1
    assert plan.calc_workers >= 1


def test_low_ram_fails_safely_before_image_processing():
    with pytest.raises(MemoryBudgetError):
        choose_workers(
            8, 4, source_pixels=66_000_000, crop_pixels=4_000_000,
            calc_enabled=True, available_bytes=1 * GIB, cpu_count=8,
        )


def test_no_memory_information_falls_back_conservatively():
    from cipa_crop_coord import memory_guard
    old = memory_guard.available_memory_bytes
    memory_guard.available_memory_bytes = lambda: None
    try:
        p = choose_workers(
            8, 4, source_pixels=66_000_000, crop_pixels=2_000_000,
            calc_enabled=True, cpu_count=16,
        )
        assert p.crop_workers == 2 and p.calc_workers == 1
        assert p.available_bytes is None
    finally:
        memory_guard.available_memory_bytes = old


def test_small_images_can_run_multiple_workers():
    p = choose_workers(
        8, 4, source_pixels=1_000_000, crop_pixels=100_000,
        calc_enabled=True, available_bytes=32 * GIB, cpu_count=16,
    )
    assert p.crop_workers > 1 and p.calc_workers >= 1
    assert p.crop_workers + p.calc_workers <= 8


def test_header_scan_detects_largest_dimensions_without_decode(tmp_path):
    for name, size in (("a.png", (10, 10)), ("b.png", (12, 20))):
        Image.new("RGB", size).save(tmp_path / name)
    (tmp_path / "broken.png").write_bytes(b"corrupt")
    assert largest_image_pixels(sorted(tmp_path.iterdir())) == 240
