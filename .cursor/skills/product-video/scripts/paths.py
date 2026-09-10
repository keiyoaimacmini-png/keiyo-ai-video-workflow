#!/usr/bin/env python3
"""Resolve PROJECT_ROOT, skill roots, helper roots, and case paths."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import subprocess

from constants import HELPER_SCRIPTS, LEGACY_TRACKED_HELPERS, OWNED_HELPERS, RUNTIME_HELPER_RELS, STATE_FILENAME


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


def helper_relpath(name: str) -> str:
    filename = HELPER_SCRIPTS[name]
    if name in OWNED_HELPERS:
        return f".cursor/skills/product-video/scripts/{filename}"
    if name in LEGACY_TRACKED_HELPERS:
        return f".cursor/skills/produce-tiktok-product-video-portable/scripts/{filename}"
    raise KeyError(name)


def helper_path(project_root: Path, name: str) -> Path:
    path = project_root / helper_relpath(name)
    if not path.is_file():
        raise FileNotFoundError(f"missing reused helper: {helper_relpath(name)}")
    return path


def git_tracks(project_root: Path, relative: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(project_root), "ls-files", "--error-unmatch", relative],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def missing_git_tracked_helpers(project_root: Path) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    for relative, stage in RUNTIME_HELPER_RELS:
        path = project_root / relative
        if not path.is_file():
            missing.append({"path": relative, "stage": stage, "reason": "missing_on_disk"})
            continue
        if not git_tracks(project_root, relative):
            missing.append({"path": relative, "stage": stage, "reason": "not_git_tracked"})
    return missing


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
