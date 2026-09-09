#!/usr/bin/env python3
"""Shared constants for the /product-video workflow."""

from __future__ import annotations

SCHEMA = "product_video_state.v1"
NARRATION_SPEED = 1.2
STATE_FILENAME = "workflow-state.json"
STATE_MAX_BYTES = 16384
RECEIPT_MAX_BYTES = 65536

STAGES = (
    "PREPARE",
    "SCRIPT",
    "SCRIPT_SELECTION",
    "NARRATION",
    "ASSEMBLY",
    "ROUGH_EDIT",
    "WAITING_FOR_OPERATOR",
    "DELIVERY",
    "COMPLETE",
)

NEXT_STAGE = {
    "PREPARE": "SCRIPT",
    "SCRIPT": "SCRIPT_SELECTION",
    "SCRIPT_SELECTION": "NARRATION",
    "NARRATION": "ASSEMBLY",
    "ASSEMBLY": "ROUGH_EDIT",
    "ROUGH_EDIT": "WAITING_FOR_OPERATOR",
    "WAITING_FOR_OPERATOR": "DELIVERY",
    "DELIVERY": "COMPLETE",
}

SKILL_FOR_STAGE = {
    "PREPARE": "product-video-prepare",
    "SCRIPT": "product-video-script",
    "NARRATION": "product-video-narration",
    "ASSEMBLY": "product-video-assembly",
    "ROUGH_EDIT": "product-video-rough-edit",
    "DELIVERY": "product-video-delivery",
}

STOP_STAGES = frozenset({"SCRIPT_SELECTION", "WAITING_FOR_OPERATOR", "COMPLETE"})
SCRIPT_APPROVAL_RE = r"^案([1-5])で台本OK$"
DELIVERY_APPROVAL = "完成・格納してください"
OPERATOR_ROUGH_MESSAGE = (
    "粗編集まで完了しました。\n"
    "手動で確認・修正してください。\n"
    "修正完了後「完成・格納してください」と送ってください。"
)

UNKNOWN_JOB_STATUSES = frozenset(
    {"unknown", "pending", "in_progress", "submitted", "running"}
)
MAJOR_VISUAL_KEYS = (
    "subject",
    "framing",
    "camera_distance",
    "camera_angle",
    "location",
    "action",
    "interaction",
    "movement",
)

OLD_SKILL_MARKERS = (
    "produce-tiktok-product-video-portable/SKILL.md",
    "produce-tiktok-product-video-v3/SKILL.md",
    "validate_craft_quality.py",
    "select_common_tts_speed.py",
    "HOLD_CRAFT_QUALITY",
)

FORBIDDEN_STATE_KEYS = frozenset(
    {
        "image",
        "images",
        "video",
        "audio",
        "dom",
        "snapshot",
        "base64",
        "html",
        "log",
        "logs",
        "screenshot",
    }
)

HELPER_SCRIPTS = {
    "resolve_product_inputs": "resolve_product_inputs.py",
    "send_gemini_cli_prompt": "send_gemini_cli_prompt.py",
    "prove_tts_textarea": "prove_tts_textarea.py",
    "capture_capcut_result_audio": "capture_capcut_result_audio.py",
    "prove_source_range": "prove_source_range.py",
    "upload_drive_local_file": "upload_drive_local_file.py",
    "purge_local_working_media": "purge_local_working_media.py",
}
