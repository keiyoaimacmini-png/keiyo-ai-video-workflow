#!/usr/bin/env python3
"""Narration at fixed 1.2x. TTS generate only after exact textarea read-back."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from constants import NARRATION_SPEED
from paths import case_root, helper_path
from prepare_tts_field import prepare_tts_field
from script_fidelity import assert_immutable, load_approved_script
from workflow_state import hold


def load_tts_helper(project_root: Path):
    import importlib.util

    path = helper_path(project_root, "prove_tts_textarea")
    spec = importlib.util.spec_from_file_location("prove_tts_textarea", path)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def narration_speed() -> float:
    return NARRATION_SPEED


def prepare_tts_input(
    field: Any,
    approved_line: str,
    *,
    generation_count_for_cut: int = 0,
    previous_line: str | None = None,
) -> dict[str, Any]:
    prepared = prepare_tts_field(
        field,
        approved_line,
        generation_count_for_cut=generation_count_for_cut,
        previous_line=previous_line,
    )
    prepared_count = prepared.get("generation_count_for_cut", generation_count_for_cut)
    if prepared_count != generation_count_for_cut:
        return hold("HOLD_TTS_INPUT_FIELD_UNVERIFIED", "input retry must not increment generation_count_for_cut")
    return prepared


def gate_tts_generate(project_root: Path, record: dict[str, Any], approved_line: str) -> dict[str, Any]:
    fidelity = assert_immutable(approved_line, record.get("frozen_line") or "", role="tts_input")
    if fidelity.get("status") != "OK":
        return fidelity
    helper = load_tts_helper(project_root)
    decision = helper.decide_tts_generate(record)
    if decision.get("generate") is not True:
        return {
            "status": "HOLD",
            "hold": decision.get("hold") or "HOLD_TTS_INPUT_FIELD_UNVERIFIED",
            "generate": False,
            "errors": decision.get("errors") or ["textarea read-back mismatch"],
        }
    return {
        "status": "OK",
        "generate": True,
        "speed": NARRATION_SPEED,
        "bound_frozen_line": approved_line,
    }


def record_clip(
    *,
    cut_id: str,
    line: str,
    audio_path: str,
    duration_seconds: float,
    speed: float = NARRATION_SPEED,
) -> dict[str, Any]:
    if speed != NARRATION_SPEED:
        return hold("HOLD_NARRATION_SPEED", "narration speed must be 1.2x")
    if not isinstance(duration_seconds, (int, float)) or isinstance(duration_seconds, bool) or duration_seconds <= 0:
        return hold("HOLD_NARRATION_DURATION", "actual playback duration is required")
    if not audio_path:
        return hold("HOLD_NARRATION_AUDIO", "audio path is missing")
    return {
        "status": "OK",
        "cut_id": cut_id,
        "line": line,
        "audio_path": audio_path,
        "duration_seconds": float(duration_seconds),
        "speed": NARRATION_SPEED,
    }


def write_manifest(project_root: Path, case_id: str, clips: list[dict[str, Any]]) -> dict[str, Any]:
    dest = case_root(project_root, case_id) / "narration-manifest.json"
    payload = {
        "schema": "product_video_narration_manifest.v1",
        "speed": NARRATION_SPEED,
        "clips": clips,
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"status": "OK", "path": dest.as_posix(), "clip_count": len(clips)}


def approved_lines(project_root: Path, approved_script_path: str) -> list[dict[str, Any]]:
    script = load_approved_script(Path(approved_script_path))
    return script["cuts"]
