#!/usr/bin/env python3
"""Own the persistent shared product-video input library.

`.runtime/product-video-inputs` is reusable source material, not case working media.
Routine DELIVERY purge must never delete that tree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from constants import PERSISTENT_SHARED_INPUT_RELATIVE

PERSISTENT_SKIP_REASON = "persistent_shared_input"


def persistent_shared_input_root(project_root: Path) -> Path:
    return Path(project_root) / Path(*Path(PERSISTENT_SHARED_INPUT_RELATIVE).parts)


def is_persistent_shared_input_path(relative_or_absolute: str) -> bool:
    posix = relative_or_absolute.replace("\\", "/")
    if posix.startswith("./"):
        posix = posix[2:]
    root = PERSISTENT_SHARED_INPUT_RELATIVE
    return posix == root or posix.startswith(root + "/")


def planned_hits_persistent_shared_inputs(planned: list[dict[str, Any]]) -> list[str]:
    hits: list[str] = []
    for entry in planned:
        path = entry.get("path") if isinstance(entry, dict) else None
        if isinstance(path, str) and is_persistent_shared_input_path(path):
            hits.append(path)
    return hits
