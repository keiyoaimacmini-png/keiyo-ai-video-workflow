#!/usr/bin/env python3
"""Shared lesson store for product-video v3 craft learning."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable


LESSON_SCHEMA = "product_video_lesson.v1"
SURFACES = ("script", "picture", "captions", "tts-timing")
STATUSES = ("active", "pending", "acknowledged")
HOLD_CRAFT = "HOLD_CRAFT_QUALITY"
NARRATIVE_ROLES = (
    "problem_or_hook",
    "product",
    "use_or_change",
    "result",
    "problem_resolution",
    "cta",
)
CTA_TEXT = "下からチェック！"
DEFECT_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
MODEL_RE = re.compile(r"^AN-[A-Z0-9]{4,6}$")


def lessons_root(project_root: Path) -> Path:
    return project_root / "config" / "product-video-lessons"


def active_dir(project_root: Path, surface: str) -> Path:
    return lessons_root(project_root) / "active" / surface


def pending_dir(project_root: Path) -> Path:
    return lessons_root(project_root) / "pending-safety"


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def spoken_text(record: dict[str, Any]) -> str:
    for key in ("text", "dialogue", "resolution", "hook"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def validate_lesson(lesson: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(lesson, dict):
        return ["lesson must be an object"]
    if lesson.get("schema") != LESSON_SCHEMA:
        errors.append(f"schema must be {LESSON_SCHEMA}")
    lesson_id = lesson.get("id")
    if not isinstance(lesson_id, str) or ID_RE.fullmatch(lesson_id) is None:
        errors.append("id must be a lowercase hyphen slug")
    if lesson.get("surface") not in SURFACES:
        errors.append("surface must be script, picture, captions, or tts-timing")
    defect = lesson.get("defect")
    if not isinstance(defect, str) or DEFECT_RE.fullmatch(defect) is None:
        errors.append("defect must be a lowercase underscore slug")
    if lesson.get("auto") not in (True, False):
        errors.append("auto must be a boolean")
    if lesson.get("status") not in STATUSES:
        errors.append("status must be active, pending, or acknowledged")
    if lesson.get("auto") is True and lesson.get("status") != "active":
        errors.append("auto quality lessons must be status active")
    if lesson.get("auto") is False and lesson.get("status") == "active":
        errors.append("safety lessons must not be auto-active")
    models = lesson.get("product_models", [])
    if models is None:
        models = []
    if not isinstance(models, list) or any(
        not isinstance(item, str) or MODEL_RE.fullmatch(item) is None for item in models
    ):
        errors.append("product_models must be an array of AN- model codes")
    for key in ("bad", "good"):
        value = lesson.get(key)
        if value is None:
            if lesson.get("auto") is True:
                errors.append(f"{key} is required for quality lessons")
            continue
        if not isinstance(value, dict) or not value:
            errors.append(f"{key} must be a non-empty object")
    gate = lesson.get("gate")
    if lesson.get("auto") is True and not isinstance(gate, dict):
        errors.append("gate is required for quality lessons")
    note = lesson.get("note")
    if note is not None and (not isinstance(note, str) or not note.strip()):
        errors.append("note must be a non-empty string when present")
    extra = set(lesson) - {
        "schema",
        "id",
        "surface",
        "defect",
        "auto",
        "status",
        "product_models",
        "bad",
        "good",
        "gate",
        "note",
    }
    if extra:
        errors.append(f"unknown fields: {', '.join(sorted(extra))}")
    return errors


def lesson_applies(lesson: dict[str, Any], product_model: str | None) -> bool:
    models = lesson.get("product_models") or []
    if not models:
        return True
    return product_model in models


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_lesson_files(directory: Path) -> Iterable[Path]:
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob("*.json") if path.is_file() and not path.is_symlink())


def load_active_lessons(
    project_root: Path,
    surface: str | None = None,
    product_model: str | None = None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    surfaces = (surface,) if surface else SURFACES
    for item in surfaces:
        for path in iter_lesson_files(active_dir(project_root, item)):
            lesson = load_json(path)
            errors = validate_lesson(lesson)
            if errors:
                raise ValueError(f"{path}: {'; '.join(errors)}")
            if lesson.get("status") != "active" or lesson.get("auto") is not True:
                continue
            if surface and lesson.get("surface") != surface:
                raise ValueError(f"{path}: surface folder mismatch")
            if lesson_applies(lesson, product_model):
                selected.append(lesson)
    return selected


def hold_payload(reason: str, *, surface: str | None = None, defect: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": "HOLD", "hold": HOLD_CRAFT, "reason": reason}
    if surface:
        payload["surface"] = surface
    if defect:
        payload["defect"] = defect
    return payload


def dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
