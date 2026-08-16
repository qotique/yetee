from __future__ import annotations

import pytest

from services.profile_preload_service import (
    PROFILE_PRELOAD_DIALOG_MIN_FILES,
    PreloadEstimate,
    estimate_preload,
    should_confirm,
)


def test_estimate_empty_files():
    est = estimate_preload([])
    assert est.count == 0
    assert est.total_bytes == 0
    assert est.seconds >= 0


def test_estimate_counts_and_bytes(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text('{"a": 1}', encoding="utf-8")
    b.write_text('{"b": 2}', encoding="utf-8")

    est = estimate_preload([str(a), str(b)])
    assert est.count == 2
    assert est.total_bytes > 0


def test_estimate_ignores_missing_files():
    est = estimate_preload(["/definitely/not/here.json"])
    assert est.count == 1
    assert est.total_bytes == 0


def test_estimate_seconds_positive_floor():
    est = estimate_preload([str(__file__)] * 200)
    assert est.seconds >= 0


def test_should_confirm_threshold(tmp_path):
    files = []
    for i in range(PROFILE_PRELOAD_DIALOG_MIN_FILES):
        p = tmp_path / f"f{i}.json"
        p.write_text("{}", encoding="utf-8")
        files.append(str(p))
    est = estimate_preload(files)
    assert should_confirm(est) is True

    small = estimate_preload(files[: PROFILE_PRELOAD_DIALOG_MIN_FILES - 1])
    assert should_confirm(small) is False


def test_estimate_returns_dataclass():
    est = estimate_preload([])
    assert isinstance(est, PreloadEstimate)
