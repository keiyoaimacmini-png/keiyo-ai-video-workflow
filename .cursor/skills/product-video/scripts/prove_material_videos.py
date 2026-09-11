#!/usr/bin/env python3
"""Require at least one real video file under the resolved material root.

Does not replace resolve_product_inputs.py. Does not ffprobe or inspect frames.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from constants import HOLD_INPUT_MATERIALS_REQUIRED, HOLD_MATERIAL_VIDEO_REQUIRED, VIDEO_EXTENSIONS
from workflow_state import hold


def _is_regular_file(path: Path) -> bool:
    try:
        return path.is_file() and not path.is_symlink()
    except OSError:
        return False


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def count_material_videos(material_root: Path) -> int:
    if not material_root.is_dir() or material_root.is_symlink():
        return 0
    count = 0
    for dirpath, _dirnames, filenames in os.walk(material_root, followlinks=False):
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            if not _is_regular_file(path):
                continue
            if _file_size(path) <= 0:
                continue
            count += 1
    return count


def prove_material_videos(material_root: object) -> dict[str, Any]:
    if not isinstance(material_root, (str, Path)) or not str(material_root).strip():
        return hold(
            HOLD_INPUT_MATERIALS_REQUIRED,
            "material_root is required",
            material_root=None,
            video_count=0,
        )
    root = Path(material_root)
    if not root.exists() or not root.is_dir() or root.is_symlink():
        return hold(
            HOLD_INPUT_MATERIALS_REQUIRED,
            "material_root is missing or not a real directory",
            material_root=root.as_posix(),
            video_count=0,
        )
    count = count_material_videos(root)
    if count < 1:
        return hold(
            HOLD_MATERIAL_VIDEO_REQUIRED,
            "material_root has no video files; do not start SCRIPT or TTS",
            material_root=root.as_posix(),
            video_count=0,
        )
    return {
        "status": "OK",
        "hold": None,
        "material_root": root.as_posix(),
        "material_video_count": count,
        "video_count": count,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--material-root", required=True)
    args = parser.parse_args()
    payload = prove_material_videos(args.material_root)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("status") == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
