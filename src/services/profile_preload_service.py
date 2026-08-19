from __future__ import annotations

import os
from dataclasses import dataclass

BYTES_PER_SECOND = 5 * 1024 * 1024
BYTES_PER_FILE_OVERHEAD = 16 * 1024
PROFILE_PRELOAD_DIALOG_MIN_FILES = 8


@dataclass(frozen=True)
class PreloadEstimate:
    count: int
    total_bytes: int
    seconds: float


def estimate_preload(files: list[str]) -> PreloadEstimate:
    total_bytes = sum(os.path.getsize(p) for p in files if os.path.isfile(p))
    raw_seconds = sum(
        (os.path.getsize(p) + BYTES_PER_FILE_OVERHEAD) / BYTES_PER_SECOND
        for p in files
        if os.path.isfile(p)
    )
    seconds = max(len(files) * 0.01, raw_seconds)
    return PreloadEstimate(count=len(files), total_bytes=total_bytes, seconds=seconds)


def should_confirm(estimate: PreloadEstimate) -> bool:
    return estimate.count >= PROFILE_PRELOAD_DIALOG_MIN_FILES
