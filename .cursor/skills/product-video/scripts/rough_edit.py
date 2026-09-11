#!/usr/bin/env python3
"""Usable rough edit only. Telop equals approved line. No AI visual scoring."""

from __future__ import annotations

from typing import Any

from constants import NARRATION_SPEED, OPERATOR_ROUGH_MESSAGE
from prove_tts_speed import clip_target_duration, prove_editorial_timing, prove_tts_speed
from script_fidelity import assert_immutable
from workflow_state import hold


def telop_matches(approved_line: str, telop: str) -> dict[str, Any]:
    return assert_immutable(approved_line, telop, role="telop")


def prove_placed_narration_clip(record: dict[str, Any]) -> dict[str, Any]:
    speed = prove_tts_speed(record)
    if speed.get("speed_ok") is not True:
        return speed
    return prove_editorial_timing(record)


def build_rough_edit(
    approved_script: dict[str, Any],
    assembly_plan: dict[str, Any],
    narration_manifest: dict[str, Any],
    *,
    editor_project_identity: str,
    placed_telops: list[dict[str, str]],
) -> dict[str, Any]:
    if not editor_project_identity:
        return hold("HOLD_EDITOR_PROJECT_UNVERIFIED", "editor project identity is required")
    clips = {clip["cut_id"]: clip for clip in narration_manifest.get("clips") or []}
    plan_cuts = {cut["cut_id"]: cut for cut in assembly_plan.get("cuts") or []}
    telop_by_cut = {item["cut_id"]: item.get("text") for item in placed_telops}
    placed: list[dict[str, Any]] = []
    for cut in approved_script.get("cuts") or []:
        line = cut["line"]
        telop = telop_by_cut.get(cut["cut_id"])
        matched = telop_matches(line, telop or "")
        if matched.get("status") != "OK":
            return matched
        clip = clips[cut["cut_id"]] if cut["cut_id"] in clips else None
        if clip is None:
            return hold("HOLD_NARRATION_AUDIO", f"missing narration for {cut['cut_id']}")
        if cut["cut_id"] not in plan_cuts:
            return hold("HOLD_ASSEMBLY_PLAN", f"missing assembly cut {cut['cut_id']}")
        target = clip_target_duration(clip)
        if target.get("status") != "OK":
            return hold(
                target.get("hold") or "HOLD_NARRATION_DURATION",
                target.get("reason") or f"invalid editorial duration for {cut['cut_id']}",
            )
        placed.append(
            {
                "cut_id": cut["cut_id"],
                "line": line,
                "telop": telop,
                "audio_path": clip["audio_path"],
                "source_duration_seconds": target["source_duration_seconds"],
                "editor_playback_rate": NARRATION_SPEED,
                "planned_duration_seconds": target["planned_duration_seconds"],
                "material": plan_cuts[cut["cut_id"]].get("material_id") or plan_cuts[cut["cut_id"]].get("path"),
            }
        )
    return {
        "status": "OK",
        "usable_rough_edit": True,
        "editor_project_identity": editor_project_identity,
        "cuts": placed,
        "ai_visual_quality_review": False,
        "operator_message_ja": OPERATOR_ROUGH_MESSAGE,
    }
