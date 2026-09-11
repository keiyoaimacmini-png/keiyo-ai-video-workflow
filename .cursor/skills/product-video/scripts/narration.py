#!/usr/bin/env python3
"""Narration source audio from CapCut; 1.2x is ChatCut clip playbackRate, not CapCut generate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from constants import NARRATION_SPEED
from paths import case_root, helper_path
from prepare_tts_field import prepare_tts_field
from prove_tts_speed import planned_editorial_duration
from prove_tts_textarea import FORBIDDEN_READBACK_SOURCES
from resolve_tts_text import compare_effective_to_frozen
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
    if not isinstance(record, dict):
        return hold("HOLD_TTS_INPUT_FIELD_UNVERIFIED", "tts generate record must be an object", generate=False)
    gated = dict(record)
    observation = gated.get("observation")
    if observation is not None:
        resolved = compare_effective_to_frozen(approved_line, observation)
        if resolved.get("status") != "OK" or resolved.get("effective_tts_text") != approved_line:
            payload = dict(resolved)
            payload["generate"] = False
            payload["hold"] = payload.get("hold") or "HOLD_TTS_INPUT_FIELD_UNVERIFIED"
            return payload
        gated["textarea_readback"] = resolved["effective_tts_text"]
        gated["readback_source"] = resolved["readback_source"]
        gated["effective_tts_text"] = resolved["effective_tts_text"]
        gated["frozen_line"] = approved_line
    if gated.get("readback_source") in FORBIDDEN_READBACK_SOURCES:
        return hold(
            "HOLD_TTS_INPUT_FIELD_UNVERIFIED",
            "document HTML, preview, OCR, or visible text is not TTS input proof",
            generate=False,
            rejected_proof_source=gated.get("readback_source"),
        )
    fidelity = assert_immutable(approved_line, gated.get("frozen_line") or "", role="tts_input")
    if fidelity.get("status") != "OK":
        payload = dict(fidelity)
        payload["generate"] = False
        return payload
    helper = load_tts_helper(project_root)
    decision = helper.decide_tts_generate(gated)
    if decision.get("generate") is not True:
        return {
            "status": "HOLD",
            "hold": decision.get("hold") or "HOLD_TTS_INPUT_FIELD_UNVERIFIED",
            "generate": False,
            "errors": decision.get("errors") or ["textarea read-back mismatch"],
        }
    readback = gated.get("effective_tts_text")
    if readback is None:
        readback = gated.get("textarea_readback")
    return {
        "status": "OK",
        "generate": True,
        "editor_playback_rate": NARRATION_SPEED,
        "bound_frozen_line": approved_line,
        "effective_tts_text": readback,
        "readback_source": gated.get("readback_source"),
    }


def record_clip(
    *,
    cut_id: str,
    line: str,
    audio_path: str,
    source_duration_seconds: float | None = None,
    editor_playback_rate: float = NARRATION_SPEED,
    source_already_accelerated: bool = False,
    duration_seconds: float | None = None,
    speed: float | None = None,
) -> dict[str, Any]:
    rate = editor_playback_rate if speed is None else speed
    if source_already_accelerated:
        return hold("HOLD_NARRATION_SPEED", "do not record the source file as already 1.2x processed")
    if source_duration_seconds is None:
        return hold("HOLD_NARRATION_DURATION", "source_duration_seconds is the original file length")
    planned = planned_editorial_duration(source_duration_seconds, rate)
    if planned.get("status") != "OK":
        hold_code = planned.get("hold") or "HOLD_NARRATION_SPEED"
        if hold_code == "HOLD_TTS_SPEED_UNVERIFIED":
            hold_code = "HOLD_NARRATION_SPEED"
        return hold(hold_code, planned.get("reason") or "editorial 1.2x plan is unavailable")
    if not audio_path:
        return hold("HOLD_NARRATION_AUDIO", "audio path is missing")
    return {
        "status": "OK",
        "cut_id": cut_id,
        "line": line,
        "audio_path": audio_path,
        "source_duration_seconds": planned["source_duration_seconds"],
        "editor_playback_rate": NARRATION_SPEED,
        "planned_duration_seconds": planned["planned_duration_seconds"],
        "source_already_accelerated": False,
    }


def write_manifest(project_root: Path, case_id: str, clips: list[dict[str, Any]]) -> dict[str, Any]:
    dest = case_root(project_root, case_id) / "narration-manifest.json"
    payload = {
        "schema": "product_video_narration_manifest.v1",
        "editor_playback_rate": NARRATION_SPEED,
        "clips": clips,
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"status": "OK", "path": dest.as_posix(), "clip_count": len(clips)}


def approved_lines(project_root: Path, approved_script_path: str) -> list[dict[str, Any]]:
    script = load_approved_script(Path(approved_script_path))
    return script["cuts"]
