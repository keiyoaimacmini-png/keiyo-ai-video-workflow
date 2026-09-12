#!/usr/bin/env python3
"""Shared constants for the /product-video workflow."""

from __future__ import annotations

SCHEMA = "product_video_state.v1"
NARRATION_SPEED = 1.2
MAX_GENERATIONS_PER_CUT = 2
HOLD_TTS_SPEED_UNVERIFIED = "HOLD_TTS_SPEED_UNVERIFIED"
HOLD_TTS_INPUT_FIELD_UNVERIFIED = "HOLD_TTS_INPUT_FIELD_UNVERIFIED"
HOLD_CAPCUT_TTS_GENERATE_FAILED = "HOLD_CAPCUT_TTS_GENERATE_FAILED"
HOLD_MATERIAL_VIDEO_REQUIRED = "HOLD_MATERIAL_VIDEO_REQUIRED"
HOLD_INPUT_MATERIALS_REQUIRED = "HOLD_INPUT_MATERIALS_REQUIRED"
HOLD_CAPCUT_CREDIT_UNVERIFIED = "HOLD_CAPCUT_CREDIT_UNVERIFIED"
HOLD_CAPCUT_NEW_PURCHASE_REQUIRED = "HOLD_CAPCUT_NEW_PURCHASE_REQUIRED"
HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE = "HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE"
HOLD_PREFLIGHT_REQUIRED = "HOLD_PREFLIGHT_REQUIRED"
HOLD_CHATCUT_UNAVAILABLE = "HOLD_CHATCUT_UNAVAILABLE"
MAX_TRANSIENT_RETRIES = 3
HUMAN_HOLD_CODES = frozenset(
    {
        "HOLD_GEMINI_LOGIN_USER_ACTION_REQUIRED",
        "HOLD_CAPCUT_LOGIN_USER_ACTION_REQUIRED",
        "HOLD_DRIVE_LOGIN_USER_ACTION_REQUIRED",
        "HOLD_CAPCUT_NEW_PURCHASE_REQUIRED",
        "HOLD_MATERIAL_VIDEO_REQUIRED",
        "HOLD_INPUT_MATERIALS_REQUIRED",
        "HOLD_DRIVE_LOCAL_BYTES_UNAVAILABLE",
        "HOLD_DRIVE_SCOPE_AMBIGUOUS",
    }
)
TRANSIENT_HOLD_CODES = frozenset(
    {
        HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE,
        "HOLD_GEMINI_CLI_NOT_VERIFIED",
        "HOLD_CHATCUT_UNAVAILABLE",
        "HOLD_DRIVE_LOOKUP_TRANSIENT",
    }
)
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".m4v", ".avi", ".mkv"})
PERSISTENT_SHARED_INPUT_RELATIVE = ".runtime/product-video-inputs"
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

OWNED_HELPERS = {
    "prove_tts_textarea": "prove_tts_textarea.py",
    "prepare_tts_field": "prepare_tts_field.py",
    "resolve_tts_text": "resolve_tts_text.py",
    "prove_tts_speed": "prove_tts_speed.py",
    "tts_attempts": "tts_attempts.py",
    "prove_material_videos": "prove_material_videos.py",
    "classify_capcut_credit": "classify_capcut_credit.py",
    "preserve_shared_inputs": "preserve_shared_inputs.py",
    "run_preflight": "run_preflight.py",
}

LEGACY_TRACKED_HELPERS = {
    "resolve_product_inputs": "resolve_product_inputs.py",
    "send_gemini_cli_prompt": "send_gemini_cli_prompt.py",
    "capture_capcut_result_audio": "capture_capcut_result_audio.py",
    "prove_source_range": "prove_source_range.py",
    "upload_drive_local_file": "upload_drive_local_file.py",
    "purge_local_working_media": "purge_local_working_media.py",
}

HELPER_SCRIPTS = {**OWNED_HELPERS, **LEGACY_TRACKED_HELPERS}

RUNTIME_HELPER_RELS = (
    (".cursor/skills/product-video/scripts/prove_tts_textarea.py", "NARRATION"),
    (".cursor/skills/product-video/scripts/prepare_tts_field.py", "NARRATION"),
    (".cursor/skills/product-video/scripts/resolve_tts_text.py", "NARRATION"),
    (".cursor/skills/product-video/scripts/prove_tts_speed.py", "NARRATION"),
    (".cursor/skills/product-video/scripts/tts_attempts.py", "NARRATION"),
    (".cursor/skills/product-video/scripts/prove_material_videos.py", "PREPARE"),
    (".cursor/skills/product-video/scripts/run_preflight.py", "PREPARE"),
    (".cursor/skills/product-video/scripts/classify_capcut_credit.py", "NARRATION"),
    (".cursor/skills/product-video/scripts/preserve_shared_inputs.py", "DELIVERY"),
    (".cursor/skills/produce-tiktok-product-video-portable/scripts/resolve_product_inputs.py", "PREPARE"),
    (".cursor/skills/produce-tiktok-product-video-portable/scripts/send_gemini_cli_prompt.py", "SCRIPT"),
    (".cursor/skills/produce-tiktok-product-video-portable/scripts/capture_capcut_result_audio.py", "NARRATION"),
    (".cursor/skills/produce-tiktok-product-video-portable/scripts/prove_source_range.py", "ASSEMBLY"),
    (".cursor/skills/produce-tiktok-product-video-portable/scripts/upload_drive_local_file.py", "DELIVERY"),
    (".cursor/skills/produce-tiktok-product-video-portable/scripts/purge_local_working_media.py", "DELIVERY"),
)
