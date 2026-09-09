#!/usr/bin/env python3
"""Resolve PROJECT_ROOT, skill roots, helper roots, and case paths."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from constants import HELPER_SCRIPTS, STATE_FILENAME


def project_root_from(path: Path) -> Path:
    resolved = path.resolve()
    if (resolved / ".cursor" / "skills" / "product-video" / "SKILL.md").is_file():
        return resolved
    for parent in resolved.parents:
        if (parent / ".cursor" / "skills" / "product-video" / "SKILL.md").is_file():
            return parent
    raise ValueError("PROJECT_ROOT must contain .cursor/skills/product-video/SKILL.md")


def skill_root(project_root: Path) -> Path:
    return project_root / ".cursor" / "skills" / "product-video"


def old_helper_root(project_root: Path) -> Path:
    return project_root / ".cursor" / "skills" / "produce-tiktok-product-video-portable" / "scripts"


def helper_path(project_root: Path, name: str) -> Path:
    filename = HELPER_SCRIPTS[name]
    path = old_helper_root(project_root) / filename
    if not path.is_file():
        raise FileNotFoundError(f"missing reused helper: {filename}")
    return path


def outputs_root(project_root: Path) -> Path:
    return project_root / "outputs"


def case_root(project_root: Path, case_id: str) -> Path:
    return outputs_root(project_root) / case_id


def state_path(project_root: Path, case_id: str) -> Path:
    return case_root(project_root, case_id) / STATE_FILENAME


def receipts_dir(project_root: Path, case_id: str) -> Path:
    return case_root(project_root, case_id) / "receipts"


def emit(payload: dict[str, Any]) -> None:
    import json

    print(json.dumps(payload, ensure_ascii=False, indent=2))
