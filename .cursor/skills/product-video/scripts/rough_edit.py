#!/usr/bin/env python3
"""Usable rough edit only. Telop equals approved line. No AI visual scoring."""

from __future__ import annotations

from typing import Any

from assembly import visual_match_passes
from constants import NARRATION_SPEED, operator_rough_message
from caption_wrap import unwrap_visual
from prove_tts_speed import clip_target_duration, prove_editorial_timing, prove_tts_speed
from script_fidelity import assert_immutable
from workflow_state import hold


AUDIO_LOCK_OPS = ("validate_tts", "import_audio_batch", "place_audio", "set_playback_rate")
VIDEO_LOCK_OPS = ("import_video_batch", "place_video", "caption_preset", "place_captions")


def audio_then_video_locked(steps: list[dict[str, Any]]) -> dict[str, Any]:
    ops = [step.get("op") for step in steps if isinstance(step, dict) and step.get("op")]
    if "place_video" in ops and "place_audio" in ops:
        if ops.index("place_video") < ops.index("place_audio"):
            return hold("HOLD_AUDIO_VIDEO_ORDER", "place_video must not run before place_audio")
    if "import_video_batch" in ops and "import_audio_batch" in ops:
        if ops.index("import_video_batch") < ops.index("import_audio_batch"):
            return hold("HOLD_AUDIO_VIDEO_ORDER", "video import must wait until audio import is planned")
    if "place_audio" in ops and "validate_tts" not in ops:
        return hold("HOLD_TTS_DECODE_INVALID", "validate_tts must run before place_audio")
    last_audio = max((ops.index(op) for op in AUDIO_LOCK_OPS if op in ops), default=-1)
    first_video = min((ops.index(op) for op in VIDEO_LOCK_OPS if op in ops), default=len(ops))
    if last_audio >= 0 and first_video < last_audio:
        return hold("HOLD_AUDIO_VIDEO_ORDER", "video/caption placement must wait until audio is locked")
    return {"status": "OK", "audio_then_video_lock": True}


def telop_matches(approved_line: str, telop: str) -> dict[str, Any]:
    if unwrap_visual(telop or "") == approved_line:
        return assert_immutable(approved_line, approved_line, role="telop")
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
    delivery_ready: bool = True,
    allow_rate: float | None = None,
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
        target = clip_target_duration(clip, allow_rate=allow_rate)
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
                "editor_playback_rate": target.get("editor_playback_rate", NARRATION_SPEED),
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
        "operator_message_ja": operator_rough_message(delivery_ready=delivery_ready),
    }


def execute_from_edit_plan(
    edit_plan: dict[str, Any],
    *,
    editor_project_identity: str,
    placed_telops: list[dict[str, str]] | None = None,
    delivery_ready: bool = True,
) -> dict[str, Any]:
    if not editor_project_identity:
        return hold("HOLD_EDITOR_PROJECT_UNVERIFIED", "editor project identity is required")
    if not isinstance(edit_plan, dict) or edit_plan.get("schema") != "product_video_edit_plan.v1":
        return hold("HOLD_ASSEMBLY_PLAN", "edit-plan.json is required before ChatCut placement")
    order = audio_then_video_locked(list(edit_plan.get("chatcut_steps") or []))
    if order.get("status") != "OK":
        return order
    telop_by_cut = {item["cut_id"]: item.get("text") for item in placed_telops or [] if isinstance(item, dict)}
    placed: list[dict[str, Any]] = []
    for cut in edit_plan.get("cuts") or []:
        line = cut["line"]
        telop = telop_by_cut.get(cut["cut_id"], cut.get("caption_text") or line)
        wrapped = cut.get("caption_visual_wrap") or telop
        if unwrap_visual(str(wrapped)) != line:
            return hold("HOLD_SCRIPT_LINE_IMMUTABLE", f"{cut['cut_id']} visual wrap changed frozen characters")
        if cut.get("visual_match") is False or cut.get("visual_match_score") == 0:
            if not visual_match_passes(cut):
                return hold(
                    "HOLD_WEAK_VISUAL_MATCH",
                    f"{cut['cut_id']} visual_match is below threshold; resolve before ChatCut placement",
                    cut_id=cut["cut_id"],
                    visual_match=cut.get("visual_match"),
                    visual_match_score=cut.get("visual_match_score"),
                    current_asset=cut.get("video_source") or cut.get("material"),
                )
        matched = telop_matches(line, str(telop))
        if matched.get("status") != "OK":
            return matched
        placed.append(
            {
                "cut_id": cut["cut_id"],
                "line": line,
                "telop": line,
                "caption_visual_wrap": wrapped,
                "audio_path": cut.get("narration_audio_path"),
                "source_duration_seconds": cut.get("source_duration_seconds"),
                "editor_playback_rate": cut.get("editor_playback_rate", NARRATION_SPEED),
                "planned_duration_seconds": cut.get("target_duration_seconds"),
                "material": cut.get("video_source"),
                "source_in": cut.get("source_in"),
                "source_out": cut.get("source_out"),
                "video_segments": cut.get("video_segments") or [],
                "timeline_start_frame": cut.get("timeline_start_frame"),
                "timeline_end_frame": cut.get("timeline_end_frame"),
            }
        )
    return {
        "status": "OK",
        "usable_rough_edit": True,
        "editor_project_identity": editor_project_identity,
        "cuts": placed,
        "chatcut_steps": list(edit_plan.get("chatcut_steps") or []),
        "reselect_in_editor": False,
        "ai_visual_quality_review": False,
        "operator_message_ja": operator_rough_message(delivery_ready=delivery_ready),
    }
