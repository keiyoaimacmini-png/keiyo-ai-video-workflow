#!/usr/bin/env python3
"""Validate bounded TTS self-repair against an actual product-video payload."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA = "product_video_execution_plan.v1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_ACTIONS = [
    "finish_edit",
    "apply_official_template",
    "first_attempt_tts",
    "first_attempt_ai_credits",
    "same_text_same_preset_tts_regeneration",
    "replace_current_project_task_owned_defective_tts",
    "resync_tts_to_approved_timing",
    "settings_bounded_common_tts_speed_adjustment",
    "derived_video_timing_adjustment",
]
LEGACY_ALLOWED_ACTIONS = ALLOWED_ACTIONS[:-2]
FORBIDDEN_ACTIONS = [
    "credit_purchase",
    "third_or_later_tts_generation_per_cut",
    "wording_or_line_break_change",
    "per_cut_or_out_of_settings_voice_speed_change_after_rough_approval",
    "source_or_range_change_after_rough_approval",
    "export_retry",
    "drive_upload_retry",
    "overwrite",
    "publish",
    "external_send",
    "cleanup",
    "delete_outside_current_project_task_owned_defective_tts",
]
LEGACY_FORBIDDEN_ACTIONS = [
    *FORBIDDEN_ACTIONS[:3],
    "speed_change_after_rough_approval",
    *FORBIDDEN_ACTIONS[4:],
]
BASE_CREDIT_ACTIONS = [
    "finish_edit",
    "apply_official_template",
    "first_attempt_tts",
    "first_attempt_ai_credits",
]
TOP_FIELDS = {
    "schema", "production_payload_sha256", "checkpoint", "approval_text",
    "narration_target_cut_ids", "narration_target_count",
    "initial_tts_generation_cap", "repair_tts_generation_cap",
    "max_tts_generations_per_cut", "max_total_tts_generation_actions",
    "allowed_actions", "forbidden_actions", "tts_input_sha256_by_cut",
    "approval", "events",
    "plan_sha256",
    "carried_event_ledger",
}
REQUIRED_TOP_FIELDS = TOP_FIELDS - {"carried_event_ledger"}
PLAN_FIELDS = (
    "schema", "production_payload_sha256", "checkpoint", "approval_text",
    "narration_target_cut_ids", "narration_target_count",
    "initial_tts_generation_cap", "repair_tts_generation_cap",
    "max_tts_generations_per_cut", "max_total_tts_generation_actions",
    "allowed_actions", "forbidden_actions", "tts_input_sha256_by_cut",
)
CARRIED_LEDGER_FIELDS = {
    "source_path", "source_file_sha256", "source_plan_sha256",
    "source_terminal_event_sha256", "source_event_count",
    "generation_request_count_by_cut", "remaining_generation_actions_by_cut",
    "ledger_binding_sha256",
}
APPROVAL_FIELDS = {
    "status", "receipt", "explicit_approval", "bound_plan_sha256",
    "bound_production_payload_sha256",
}
EVENT_FIELDS = {
    "sequence", "cut_id", "event_type", "observed_at",
    "plan_sha256", "production_payload_sha256", "tts_input_sha256",
    "clip_identity_sha256", "related_clip_identity_sha256",
    "verification_receipt_sha256", "previous_event_sha256", "event_sha256",
}
EVENT_TYPES = {
    "initial_generation_requested",
    "initial_generation_verified",
    "initial_generation_failed",
    "defect_confirmed",
    "repair_generation_requested",
    "repair_generation_verified",
    "repair_generation_failed",
    "defective_clip_replaced",
    "replacement_clip_adopted",
    "timing_resynced",
    "hold",
}


def canonical_sha(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(HEX64.fullmatch(value))


def parse_offset_time(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def derive_tts_inputs(payload: dict[str, Any], errors: list[str]) -> tuple[list[str], dict[str, str]]:
    script = payload.get("script")
    captions = payload.get("captions")
    tts = payload.get("tts")
    if not isinstance(script, list) or not isinstance(captions, list) or not isinstance(tts, list):
        errors.append("payload script, captions, and tts must be lists")
        return [], {}

    targets: list[str] = []
    script_by_cut: dict[str, dict[str, Any]] = {}
    caption_by_cut: dict[str, dict[str, Any]] = {}
    tts_by_cut: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(script):
        if not isinstance(item, dict):
            errors.append(f"payload.script[{index}] must be an object")
            continue
        cut_id = item.get("cut_id")
        if not isinstance(cut_id, str) or not cut_id:
            errors.append(f"payload.script[{index}].cut_id must be non-empty")
            continue
        if cut_id in script_by_cut:
            errors.append(f"payload script cut ID {cut_id} is duplicated")
        script_by_cut[cut_id] = item
        if item.get("narration_target") is True:
            targets.append(cut_id)
    for collection, destination, label in (
        (captions, caption_by_cut, "captions"),
        (tts, tts_by_cut, "tts"),
    ):
        for index, item in enumerate(collection):
            if not isinstance(item, dict):
                errors.append(f"payload.{label}[{index}] must be an object")
                continue
            cut_id = item.get("cut_id")
            if not isinstance(cut_id, str) or not cut_id:
                errors.append(f"payload.{label}[{index}].cut_id must be non-empty")
                continue
            if cut_id in destination:
                errors.append(f"payload {label} cut ID {cut_id} is duplicated")
            destination[cut_id] = item

    fingerprints: dict[str, str] = {}
    for cut_id in targets:
        script_item = script_by_cut.get(cut_id)
        caption_item = caption_by_cut.get(cut_id)
        tts_item = tts_by_cut.get(cut_id)
        if not all(isinstance(item, dict) for item in (script_item, caption_item, tts_item)):
            errors.append(f"payload narration target {cut_id} needs script, caption, and tts records")
            continue
        projection = {
            "cut_id": cut_id,
            "script_dialogue": script_item.get("dialogue"),
            "caption_text": caption_item.get("text"),
            "caption_line_breaks": caption_item.get("line_breaks"),
            "tts_text": tts_item.get("text"),
            "voice": tts_item.get("voice"),
            "speed": tts_item.get("speed"),
            "pitch": tts_item.get("pitch"),
            "voice_processing": tts_item.get("voice_processing"),
            "timeline_in": tts_item.get("timeline_in"),
            "timeline_out": tts_item.get("timeline_out"),
        }
        try:
            fingerprints[cut_id] = canonical_sha(projection)
        except (TypeError, ValueError):
            errors.append(f"payload TTS input for {cut_id} is non-canonical")
    return targets, fingerprints


def validate_payload_binding(plan: dict[str, Any], payload: Any, errors: list[str]) -> None:
    if not isinstance(payload, dict):
        errors.append("payload top level must be an object")
        return
    integrity = payload.get("integrity")
    if not isinstance(integrity, dict):
        errors.append("payload.integrity must be an object")
        return
    production_sha = integrity.get("production_payload_sha256")
    visible_sha = integrity.get("visible_content_sha256")
    if not is_sha(production_sha) or not is_sha(visible_sha):
        errors.append("payload integrity hashes must be lowercase SHA-256")
    if plan["production_payload_sha256"] != production_sha:
        errors.append("plan must bind the actual payload production SHA-256")

    targets, fingerprints = derive_tts_inputs(payload, errors)
    if plan["narration_target_cut_ids"] != targets:
        errors.append("plan narration targets must exactly match actual payload order")
    if plan["tts_input_sha256_by_cut"] != fingerprints:
        errors.append("plan TTS input hashes must exactly match the actual payload")

    gates = payload.get("approval_gates")
    credit = gates.get("credit") if isinstance(gates, dict) else None
    if not isinstance(credit, dict):
        errors.append("payload.approval_gates.credit must be an object")
        return
    if credit.get("checkpoint") != "rough_edit":
        errors.append("base credit gate checkpoint must be rough_edit")
    if credit.get("authorized_actions") != BASE_CREDIT_ACTIONS:
        errors.append("base credit gate actions must remain the base first-attempt list")
    if credit.get("max_first_attempt_tts_count") != len(targets):
        errors.append("base credit first-attempt count must match narration targets")

    approval = plan["approval"]
    if approval["status"] == "pending":
        if credit.get("status") != "pending":
            errors.append("pending execution plan requires pending base credit gate")
    elif approval["status"] == "approved":
        if (
            credit.get("status") != "approved"
            or credit.get("receipt") != "粗編集OK"
            or credit.get("explicit_approval") is not True
        ):
            errors.append("approved execution plan requires exact approved base credit gate")
        if credit.get("bound_production_payload_sha256") != production_sha:
            errors.append("base credit gate must bind current production payload hash")
        if credit.get("bound_visible_content_sha256") != visible_sha:
            errors.append("base credit gate must bind current visible-content hash")


def validate_event_ledger(plan: dict[str, Any], errors: list[str]) -> None:
    events = plan["events"]
    approval = plan["approval"]
    if not isinstance(events, list):
        errors.append("events must be a list")
        return
    if approval["status"] == "pending" and events:
        errors.append("pending plans cannot contain execution events")

    targets = set(plan["narration_target_cut_ids"])
    states = {cut_id: "start" for cut_id in targets}
    current_clip: dict[str, str | None] = {cut_id: None for cut_id in targets}
    defective_clip: dict[str, str | None] = {cut_id: None for cut_id in targets}
    replacement_clip: dict[str, str | None] = {cut_id: None for cut_id in targets}
    previous_sha: str | None = plan["plan_sha256"]
    for index, event in enumerate(events):
        prefix = f"events[{index}]"
        if not isinstance(event, dict) or set(event) != EVENT_FIELDS:
            errors.append(f"{prefix} must contain exactly {sorted(EVENT_FIELDS)}")
            continue
        if event["sequence"] != index + 1:
            errors.append(f"{prefix}.sequence must equal {index + 1}")
        cut_id = event["cut_id"]
        kind = event["event_type"]
        if not isinstance(cut_id, str) or cut_id not in targets:
            errors.append(f"{prefix}.cut_id must name a narration target")
            continue
        if not isinstance(kind, str) or kind not in EVENT_TYPES:
            errors.append(f"{prefix}.event_type is invalid")
            continue
        if not parse_offset_time(event["observed_at"]):
            errors.append(f"{prefix}.observed_at must be offset-aware ISO-8601")
        if event["plan_sha256"] != plan["plan_sha256"]:
            errors.append(f"{prefix}.plan_sha256 must bind the approved plan")
        if event["production_payload_sha256"] != plan["production_payload_sha256"]:
            errors.append(f"{prefix}.production_payload_sha256 must bind the approved payload")
        input_hashes = plan["tts_input_sha256_by_cut"]
        expected_input = input_hashes.get(cut_id) if isinstance(input_hashes, dict) else None
        if event["tts_input_sha256"] != expected_input:
            errors.append(f"{prefix}.tts_input_sha256 must match the frozen cut input")
        for identity_field in (
            "clip_identity_sha256",
            "related_clip_identity_sha256",
            "verification_receipt_sha256",
        ):
            value = event[identity_field]
            if value is not None and not is_sha(value):
                errors.append(f"{prefix}.{identity_field} must be null or lowercase SHA-256")
        if event["previous_event_sha256"] != previous_sha:
            errors.append(f"{prefix}.previous_event_sha256 breaks the event chain")
        projection = {field: event[field] for field in EVENT_FIELDS - {"event_sha256"}}
        try:
            expected_sha = canonical_sha(projection)
        except (TypeError, ValueError):
            errors.append(f"{prefix} contains non-canonical values")
            expected_sha = None
        if event["event_sha256"] != expected_sha:
            errors.append(f"{prefix}.event_sha256 mismatch")
        if is_sha(event["event_sha256"]):
            previous_sha = event["event_sha256"]

        state = states[cut_id]
        clip_sha = event["clip_identity_sha256"]
        related_sha = event["related_clip_identity_sha256"]
        verification_sha = event["verification_receipt_sha256"]
        if kind == "initial_generation_requested":
            if clip_sha is not None or related_sha is not None or verification_sha is not None:
                errors.append(f"{prefix} initial request cannot claim clip or verification evidence")
        elif kind == "initial_generation_verified":
            if not is_sha(clip_sha) or related_sha is not None or not is_sha(verification_sha):
                errors.append(f"{prefix} initial verification needs one clip and verification receipt")
            else:
                current_clip[cut_id] = clip_sha
        elif kind == "initial_generation_failed":
            if clip_sha is not None or related_sha is not None or not is_sha(verification_sha):
                errors.append(f"{prefix} initial failure needs only a verification receipt")
        elif kind == "defect_confirmed":
            expected_defective = current_clip[cut_id] if state == "verified" else None
            if clip_sha != expected_defective or related_sha is not None or not is_sha(verification_sha):
                errors.append(f"{prefix} defect evidence must bind the current defective clip")
            defective_clip[cut_id] = clip_sha
        elif kind == "repair_generation_requested":
            if clip_sha is not None or related_sha != defective_clip[cut_id] or verification_sha is not None:
                errors.append(f"{prefix} repair request must bind only the defective clip")
        elif kind == "repair_generation_verified":
            if (
                not is_sha(clip_sha)
                or related_sha != defective_clip[cut_id]
                or not is_sha(verification_sha)
                or (defective_clip[cut_id] is not None and clip_sha == defective_clip[cut_id])
            ):
                errors.append(f"{prefix} repair verification needs a distinct replacement and evidence")
            else:
                replacement_clip[cut_id] = clip_sha
        elif kind == "repair_generation_failed":
            if clip_sha is not None or related_sha != defective_clip[cut_id] or not is_sha(verification_sha):
                errors.append(f"{prefix} repair failure must bind the defective clip and evidence")
        elif kind == "defective_clip_replaced":
            if (
                not is_sha(clip_sha)
                or not is_sha(related_sha)
                or clip_sha != replacement_clip[cut_id]
                or related_sha != defective_clip[cut_id]
                or clip_sha == related_sha
                or not is_sha(verification_sha)
            ):
                errors.append(f"{prefix} replacement must bind verified old/new clip identities")
            else:
                current_clip[cut_id] = clip_sha
        elif kind == "replacement_clip_adopted":
            if (
                defective_clip[cut_id] is not None
                or clip_sha != replacement_clip[cut_id]
                or related_sha is not None
                or not is_sha(verification_sha)
            ):
                errors.append(f"{prefix} adoption is only for a verified replacement when no old clip exists")
            else:
                current_clip[cut_id] = clip_sha
        elif kind == "timing_resynced":
            if clip_sha != current_clip[cut_id] or related_sha is not None or not is_sha(verification_sha):
                errors.append(f"{prefix} timing evidence must bind the current verified clip")
        elif kind == "hold":
            if related_sha is not None or not is_sha(verification_sha):
                errors.append(f"{prefix} hold needs a verification receipt and no related clip")
        transitions = {
            ("start", "initial_generation_requested"): "initial_requested",
            ("initial_requested", "initial_generation_verified"): "verified",
            ("initial_requested", "initial_generation_failed"): "initial_failed",
            ("verified", "defect_confirmed"): "defect",
            ("initial_failed", "defect_confirmed"): "defect",
            ("defect", "repair_generation_requested"): "repair_requested",
            ("repair_requested", "repair_generation_verified"): "repair_verified",
            ("repair_requested", "repair_generation_failed"): "repair_failed",
            ("repair_verified", "defective_clip_replaced"): "repaired",
            ("repair_verified", "replacement_clip_adopted"): "repaired",
            ("verified", "timing_resynced"): "verified",
            ("repaired", "timing_resynced"): "repaired",
        }
        if kind == "hold" and state != "start":
            states[cut_id] = "hold"
        elif (state, kind) in transitions:
            states[cut_id] = transitions[(state, kind)]
        else:
            errors.append(f"{prefix} invalid transition {state} -> {kind}")


def plan_projection(plan: dict[str, Any]) -> dict[str, Any]:
    projection = {field: plan[field] for field in PLAN_FIELDS}
    if "carried_event_ledger" in plan:
        projection["carried_event_ledger"] = plan["carried_event_ledger"]
    return projection


def validate_carried_event_ledger(
    plan: dict[str, Any], plan_path: Path | None, errors: list[str]
) -> None:
    carried = plan.get("carried_event_ledger")
    events = plan.get("events")
    approval = plan.get("approval")
    if carried is None:
        if isinstance(approval, dict) and approval.get("status") == "approved" and events == []:
            errors.append("approved empty event ledger requires carried_event_ledger")
        return
    if not isinstance(carried, dict) or set(carried) != CARRIED_LEDGER_FIELDS:
        errors.append(f"carried_event_ledger must contain exactly {sorted(CARRIED_LEDGER_FIELDS)}")
        return
    source_path = carried.get("source_path")
    if not isinstance(source_path, str) or not source_path or Path(source_path).name != source_path:
        errors.append("carried_event_ledger.source_path must be one safe sibling filename")
        return
    projection = {key: carried[key] for key in CARRIED_LEDGER_FIELDS - {"ledger_binding_sha256"}}
    if carried.get("ledger_binding_sha256") != canonical_sha(projection):
        errors.append("carried_event_ledger.ledger_binding_sha256 mismatch")
    if plan_path is None:
        errors.append("carried_event_ledger requires validator plan path context")
        return
    source_file = plan_path.parent / source_path
    try:
        source_bytes = source_file.read_bytes()
        source = json.loads(source_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"carried event source is unreadable: {exc}")
        return
    if hashlib.sha256(source_bytes).hexdigest() != carried.get("source_file_sha256"):
        errors.append("carried event source file SHA-256 mismatch")
    if not isinstance(source, dict):
        errors.append("carried event source must be a JSON object")
        return
    source_errors: list[str] = []
    validate_event_ledger(source, source_errors)
    if source_errors:
        errors.extend(f"carried event source: {item}" for item in source_errors)
    source_events = source.get("events")
    if not isinstance(source_events, list) or not source_events:
        errors.append("carried event source must contain a non-empty event ledger")
        return
    if source.get("plan_sha256") != carried.get("source_plan_sha256"):
        errors.append("carried event source plan SHA-256 mismatch")
    if len(source_events) != carried.get("source_event_count"):
        errors.append("carried event source event count mismatch")
    if source_events[-1].get("event_sha256") != carried.get("source_terminal_event_sha256"):
        errors.append("carried event source terminal event SHA-256 mismatch")
    counts = {cut_id: 0 for cut_id in plan.get("narration_target_cut_ids", [])}
    for event in source_events:
        if event.get("event_type") in {"initial_generation_requested", "repair_generation_requested"}:
            cut_id = event.get("cut_id")
            if cut_id in counts:
                counts[cut_id] += 1
    remaining = {cut_id: 2 - count for cut_id, count in counts.items()}
    if any(value < 0 for value in remaining.values()):
        errors.append("carried event source exceeds per-cut generation cap")
    if carried.get("generation_request_count_by_cut") != counts:
        errors.append("carried generation_request_count_by_cut mismatch")
    if carried.get("remaining_generation_actions_by_cut") != remaining:
        errors.append("carried remaining_generation_actions_by_cut mismatch")

    current_counts = {cut_id: 0 for cut_id in counts}
    current_events = plan.get("events")
    if isinstance(current_events, list):
        for index, event in enumerate(current_events):
            if not isinstance(event, dict):
                continue
            cut_id = event.get("cut_id")
            kind = event.get("event_type")
            if kind in {"initial_generation_requested", "repair_generation_requested"} and cut_id in current_counts:
                current_counts[cut_id] += 1
            if kind == "initial_generation_requested" and cut_id in counts and counts[cut_id] > 0:
                errors.append(
                    f"events[{index}] cannot restart initial generation for {cut_id} after carried spend"
                )
    combined = {cut_id: counts[cut_id] + current_counts[cut_id] for cut_id in counts}
    for cut_id, total in combined.items():
        if total > plan.get("max_tts_generations_per_cut"):
            errors.append(f"combined carried/current generation requests exceed cap for {cut_id}")
    if sum(combined.values()) > plan.get("max_total_tts_generation_actions"):
        errors.append("combined carried/current generation requests exceed total cap")


def validate(plan: Any, payload: Any, plan_path: Path | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["plan top level must be an object"]
    extra = set(plan) - TOP_FIELDS
    missing = REQUIRED_TOP_FIELDS - set(plan)
    if extra:
        errors.append(f"unexpected fields: {sorted(extra)}")
    if missing:
        errors.append(f"missing fields: {sorted(missing)}")
        return errors

    if plan["schema"] != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    if not is_sha(plan["production_payload_sha256"]):
        errors.append("production_payload_sha256 must be lowercase SHA-256")
    if plan["checkpoint"] != "rough_edit" or plan["approval_text"] != "粗編集OK":
        errors.append("checkpoint and approval_text must be rough_edit / 粗編集OK")

    cut_ids = plan["narration_target_cut_ids"]
    if not isinstance(cut_ids, list) or any(
        not isinstance(item, str) or not item for item in cut_ids
    ):
        errors.append("narration_target_cut_ids must be a string list")
        cut_ids = []
    elif len(set(cut_ids)) != len(cut_ids):
        errors.append("narration_target_cut_ids must be unique")
    count = len(cut_ids)
    expectations = {
        "narration_target_count": count,
        "initial_tts_generation_cap": count,
        "repair_tts_generation_cap": count,
        "max_tts_generations_per_cut": 2,
        "max_total_tts_generation_actions": count * 2,
    }
    for field, expected in expectations.items():
        value = plan[field]
        if isinstance(value, bool) or not isinstance(value, int) or value != expected:
            errors.append(f"{field} must equal {expected}")
    valid_action_contract = (
        (plan["allowed_actions"] == ALLOWED_ACTIONS and plan["forbidden_actions"] == FORBIDDEN_ACTIONS)
        or (
            "carried_event_ledger" not in plan
            and plan["allowed_actions"] == LEGACY_ALLOWED_ACTIONS
            and plan["forbidden_actions"] == LEGACY_FORBIDDEN_ACTIONS
        )
    )
    if not valid_action_contract:
        errors.append("allowed_actions and forbidden_actions must equal one complete supported contract")
    input_hashes = plan["tts_input_sha256_by_cut"]
    if not isinstance(input_hashes, dict):
        errors.append("tts_input_sha256_by_cut must be an object")
    elif set(input_hashes) != set(cut_ids) or any(not is_sha(value) for value in input_hashes.values()):
        errors.append("TTS input hash keys must match the target set and all values must be SHA-256")

    approval = plan["approval"]
    if not isinstance(approval, dict) or set(approval) != APPROVAL_FIELDS:
        errors.append(f"approval must contain exactly {sorted(APPROVAL_FIELDS)}")
        return errors
    projection = plan_projection(plan)
    try:
        expected_plan_sha = canonical_sha(projection)
    except (TypeError, ValueError):
        errors.append("plan contains non-canonical values")
        expected_plan_sha = None
    if plan["plan_sha256"] != expected_plan_sha:
        errors.append("plan_sha256 mismatch")

    if approval["status"] == "pending":
        if (
            approval["receipt"] is not None
            or approval["explicit_approval"] is not False
            or approval["bound_plan_sha256"] is not None
            or approval["bound_production_payload_sha256"] is not None
        ):
            errors.append("pending approval must have null bindings and no receipt")
    elif approval["status"] == "approved":
        if approval["receipt"] != "粗編集OK" or approval["explicit_approval"] is not True:
            errors.append("approved plan requires exact receipt 粗編集OK")
        if approval["bound_plan_sha256"] != plan["plan_sha256"]:
            errors.append("approved receipt must bind the unchanged plan hash")
        if approval["bound_production_payload_sha256"] != plan["production_payload_sha256"]:
            errors.append("approved receipt must bind the actual production payload hash")
    else:
        errors.append("approval.status must be pending or approved")

    validate_payload_binding(plan, payload, errors)
    validate_event_ledger(plan, errors)
    validate_carried_event_ledger(plan, plan_path, errors)
    return errors


def payload_fixture(targets: list[str], approved: bool = False) -> dict[str, Any]:
    production_sha = "a" * 64
    visible_sha = "b" * 64
    credit = {
        "status": "approved" if approved else "pending",
        "receipt": "粗編集OK" if approved else None,
        "explicit_approval": approved,
        "checkpoint": "rough_edit",
        "authorized_actions": BASE_CREDIT_ACTIONS.copy(),
        "max_first_attempt_tts_count": len(targets),
        "bound_production_payload_sha256": production_sha if approved else None,
        "bound_visible_content_sha256": visible_sha if approved else None,
    }
    return {
        "integrity": {
            "production_payload_sha256": production_sha,
            "visible_content_sha256": visible_sha,
        },
        "script": [
            {"cut_id": cut_id, "narration_target": True, "dialogue": f"line-{cut_id}"}
            for cut_id in targets
        ],
        "captions": [
            {"cut_id": cut_id, "text": f"line-{cut_id}", "line_breaks": []}
            for cut_id in targets
        ],
        "tts": [
            {
                "cut_id": cut_id,
                "text": f"line-{cut_id}",
                "voice": "CapCut official ホリデーツイスト",
                "speed": 1.0,
                "pitch": 1.0,
                "voice_processing": "none",
                "timeline_in": index * 2.0,
                "timeline_out": (index + 1) * 2.0,
            }
            for index, cut_id in enumerate(targets)
        ],
        "approval_gates": {"credit": credit},
    }


def plan_fixture(targets: list[str], approved: bool = False) -> dict[str, Any]:
    fixture_errors: list[str] = []
    _, input_hashes = derive_tts_inputs(payload_fixture(targets, approved), fixture_errors)
    if fixture_errors:
        raise AssertionError(fixture_errors)
    plan: dict[str, Any] = {
        "schema": SCHEMA,
        "production_payload_sha256": "a" * 64,
        "checkpoint": "rough_edit",
        "approval_text": "粗編集OK",
        "narration_target_cut_ids": targets.copy(),
        "narration_target_count": len(targets),
        "initial_tts_generation_cap": len(targets),
        "repair_tts_generation_cap": len(targets),
        "max_tts_generations_per_cut": 2,
        "max_total_tts_generation_actions": len(targets) * 2,
        "allowed_actions": ALLOWED_ACTIONS.copy(),
        "forbidden_actions": FORBIDDEN_ACTIONS.copy(),
        "tts_input_sha256_by_cut": input_hashes,
        "approval": {
            "status": "approved" if approved else "pending",
            "receipt": "粗編集OK" if approved else None,
            "explicit_approval": approved,
            "bound_plan_sha256": None,
            "bound_production_payload_sha256": "a" * 64 if approved else None,
        },
        "events": [],
        "plan_sha256": "",
    }
    plan["plan_sha256"] = canonical_sha({field: plan[field] for field in PLAN_FIELDS})
    if approved:
        plan["approval"]["bound_plan_sha256"] = plan["plan_sha256"]
    return plan


def append_event(
    plan: dict[str, Any],
    cut_id: str,
    kind: str,
    observed_at: str,
    *,
    clip: str | None = None,
    related: str | None = None,
    verification: str | None = None,
) -> None:
    previous = plan["events"][-1]["event_sha256"] if plan["events"] else plan["plan_sha256"]
    event = {
        "sequence": len(plan["events"]) + 1,
        "cut_id": cut_id,
        "event_type": kind,
        "observed_at": observed_at,
        "plan_sha256": plan["plan_sha256"],
        "production_payload_sha256": plan["production_payload_sha256"],
        "tts_input_sha256": plan["tts_input_sha256_by_cut"][cut_id],
        "clip_identity_sha256": clip,
        "related_clip_identity_sha256": related,
        "verification_receipt_sha256": verification,
        "previous_event_sha256": previous,
        "event_sha256": "",
    }
    projection = {field: event[field] for field in EVENT_FIELDS - {"event_sha256"}}
    event["event_sha256"] = canonical_sha(projection)
    plan["events"].append(event)


def self_test() -> int:
    cases: list[tuple[str, dict[str, Any], dict[str, Any], bool]] = []
    six_targets = [f"cut-{index:02d}" for index in range(1, 7)]
    six_cut = plan_fixture(six_targets, approved=True)
    for index, cut_id in enumerate(six_targets):
        append_event(
            six_cut,
            cut_id,
            "initial_generation_requested",
            f"2026-08-28T10:{index:02d}:00+09:00",
        )
        append_event(
            six_cut,
            cut_id,
            "initial_generation_verified",
            f"2026-08-28T10:{index:02d}:03+09:00",
            clip=f"{index + 1:x}" * 64,
            verification=f"{index + 7:x}" * 64,
        )
    cases.append(("valid six-cut normal completion", six_cut, payload_fixture(six_targets, approved=True), False))

    pending = plan_fixture(["cut-01", "cut-02"])
    cases.append(("valid pending", pending, payload_fixture(["cut-01", "cut-02"]), False))

    approved = plan_fixture(["cut-01"], approved=True)
    append_event(approved, "cut-01", "initial_generation_requested", "2026-08-28T10:00:00+09:00")
    append_event(
        approved,
        "cut-01",
        "initial_generation_verified",
        "2026-08-28T10:00:03+09:00",
        clip="c" * 64,
        verification="d" * 64,
    )
    cases.append(("valid approved ledger", approved, payload_fixture(["cut-01"], approved=True), False))

    repaired = plan_fixture(["cut-01"], approved=True)
    append_event(repaired, "cut-01", "initial_generation_requested", "2026-08-28T11:00:00+09:00")
    append_event(repaired, "cut-01", "initial_generation_verified", "2026-08-28T11:00:02+09:00", clip="c" * 64, verification="d" * 64)
    append_event(repaired, "cut-01", "defect_confirmed", "2026-08-28T11:00:04+09:00", clip="c" * 64, verification="e" * 64)
    append_event(repaired, "cut-01", "repair_generation_requested", "2026-08-28T11:00:06+09:00", related="c" * 64)
    append_event(repaired, "cut-01", "repair_generation_verified", "2026-08-28T11:00:08+09:00", clip="f" * 64, related="c" * 64, verification="1" * 64)
    append_event(repaired, "cut-01", "defective_clip_replaced", "2026-08-28T11:00:10+09:00", clip="f" * 64, related="c" * 64, verification="2" * 64)
    append_event(repaired, "cut-01", "timing_resynced", "2026-08-28T11:00:12+09:00", clip="f" * 64, verification="3" * 64)
    cases.append(("valid full repair transaction", repaired, payload_fixture(["cut-01"], approved=True), False))

    missing_clip = plan_fixture(["cut-01"], approved=True)
    append_event(missing_clip, "cut-01", "initial_generation_requested", "2026-08-28T11:10:00+09:00")
    append_event(missing_clip, "cut-01", "initial_generation_failed", "2026-08-28T11:10:02+09:00", verification="d" * 64)
    append_event(missing_clip, "cut-01", "defect_confirmed", "2026-08-28T11:10:04+09:00", verification="e" * 64)
    append_event(missing_clip, "cut-01", "repair_generation_requested", "2026-08-28T11:10:06+09:00")
    append_event(missing_clip, "cut-01", "repair_generation_verified", "2026-08-28T11:10:08+09:00", clip="f" * 64, verification="1" * 64)
    append_event(missing_clip, "cut-01", "replacement_clip_adopted", "2026-08-28T11:10:10+09:00", clip="f" * 64, verification="2" * 64)
    append_event(missing_clip, "cut-01", "timing_resynced", "2026-08-28T11:10:12+09:00", clip="f" * 64, verification="3" * 64)
    cases.append(("valid missing-clip adoption transaction", missing_clip, payload_fixture(["cut-01"], approved=True), False))

    overflow_hold = plan_fixture(["cut-01"], approved=True)
    append_event(overflow_hold, "cut-01", "initial_generation_requested", "2026-08-28T12:00:00+09:00")
    append_event(overflow_hold, "cut-01", "initial_generation_verified", "2026-08-28T12:00:02+09:00", clip="c" * 64, verification="d" * 64)
    append_event(overflow_hold, "cut-01", "hold", "2026-08-28T12:00:04+09:00", clip="c" * 64, verification="e" * 64)
    cases.append(("valid true-overflow hold", overflow_hold, payload_fixture(["cut-01"], approved=True), False))

    zero = plan_fixture([])
    cases.append(("valid narration none", zero, payload_fixture([]), False))

    stale_payload = plan_fixture(["cut-01"])
    stale_payload["production_payload_sha256"] = "c" * 64
    stale_payload["plan_sha256"] = canonical_sha({field: stale_payload[field] for field in PLAN_FIELDS})
    cases.append(("reject stale payload binding", stale_payload, payload_fixture(["cut-01"]), True))

    broadened = plan_fixture(["cut-01"])
    broadened["allowed_actions"].append("credit_purchase")
    broadened["plan_sha256"] = canonical_sha({field: broadened[field] for field in PLAN_FIELDS})
    cases.append(("reject broadened actions", broadened, payload_fixture(["cut-01"]), True))

    forged_approval = plan_fixture(["cut-01"], approved=True)
    forged_payload = payload_fixture(["cut-01"], approved=False)
    cases.append(("reject missing base approval", forged_approval, forged_payload, True))

    bad_chain = plan_fixture(["cut-01"], approved=True)
    append_event(bad_chain, "cut-01", "repair_generation_requested", "2026-08-28T10:00:00+09:00")
    cases.append(("reject repair without defect", bad_chain, payload_fixture(["cut-01"], approved=True), True))

    bypass = plan_fixture(["cut-01"], approved=True)
    append_event(bypass, "cut-01", "initial_generation_requested", "2026-08-28T12:10:00+09:00")
    append_event(bypass, "cut-01", "initial_generation_verified", "2026-08-28T12:10:02+09:00", clip="c" * 64, verification="d" * 64)
    append_event(bypass, "cut-01", "defect_confirmed", "2026-08-28T12:10:04+09:00", clip="c" * 64, verification="e" * 64)
    append_event(bypass, "cut-01", "repair_generation_requested", "2026-08-28T12:10:06+09:00", related="c" * 64)
    append_event(bypass, "cut-01", "repair_generation_verified", "2026-08-28T12:10:08+09:00", clip="f" * 64, related="c" * 64, verification="1" * 64)
    append_event(bypass, "cut-01", "timing_resynced", "2026-08-28T12:10:10+09:00", clip="c" * 64, verification="2" * 64)
    cases.append(("reject resync before defective replacement", bypass, payload_fixture(["cut-01"], approved=True), True))

    null_old_replacement = plan_fixture(["cut-01"], approved=True)
    append_event(null_old_replacement, "cut-01", "initial_generation_requested", "2026-08-28T12:20:00+09:00")
    append_event(null_old_replacement, "cut-01", "initial_generation_failed", "2026-08-28T12:20:02+09:00", verification="d" * 64)
    append_event(null_old_replacement, "cut-01", "defect_confirmed", "2026-08-28T12:20:04+09:00", verification="e" * 64)
    append_event(null_old_replacement, "cut-01", "repair_generation_requested", "2026-08-28T12:20:06+09:00")
    append_event(null_old_replacement, "cut-01", "repair_generation_verified", "2026-08-28T12:20:08+09:00", clip="f" * 64, verification="1" * 64)
    append_event(null_old_replacement, "cut-01", "defective_clip_replaced", "2026-08-28T12:20:10+09:00", clip="f" * 64, verification="2" * 64)
    cases.append(("reject replacement with null old clip", null_old_replacement, payload_fixture(["cut-01"], approved=True), True))

    ledger_a = plan_fixture(["cut-01"], approved=True)
    append_event(ledger_a, "cut-01", "initial_generation_requested", "2026-08-28T13:00:00+09:00")
    append_event(ledger_a, "cut-01", "initial_generation_verified", "2026-08-28T13:00:02+09:00", clip="c" * 64, verification="d" * 64)
    payload_b = payload_fixture(["cut-01"], approved=True)
    payload_b["script"][0]["dialogue"] = "changed-line"
    payload_b["captions"][0]["text"] = "changed-line"
    payload_b["tts"][0]["text"] = "changed-line"
    payload_b["integrity"]["production_payload_sha256"] = "e" * 64
    payload_b["approval_gates"]["credit"]["bound_production_payload_sha256"] = "e" * 64
    payload_b_errors: list[str] = []
    _, payload_b_inputs = derive_tts_inputs(payload_b, payload_b_errors)
    if payload_b_errors:
        raise AssertionError(payload_b_errors)
    transplanted = json.loads(json.dumps(ledger_a))
    transplanted["production_payload_sha256"] = "e" * 64
    transplanted["tts_input_sha256_by_cut"] = payload_b_inputs
    transplanted["plan_sha256"] = canonical_sha({field: transplanted[field] for field in PLAN_FIELDS})
    transplanted["approval"]["bound_plan_sha256"] = transplanted["plan_sha256"]
    transplanted["approval"]["bound_production_payload_sha256"] = "e" * 64
    cases.append(("reject cross-payload ledger transplant", transplanted, payload_b, True))

    failures = []
    for name, plan, payload, should_fail in cases:
        actual_fail = bool(validate(plan, payload))
        if actual_fail != should_fail:
            failures.append(name)
    with tempfile.TemporaryDirectory() as temp_dir:
        source = plan_fixture(["cut-01"], approved=True)
        append_event(source, "cut-01", "initial_generation_requested", "2026-08-28T14:00:00+09:00")
        append_event(
            source, "cut-01", "initial_generation_verified", "2026-08-28T14:00:02+09:00",
            clip="c" * 64, verification="d" * 64,
        )
        source_path = Path(temp_dir) / "source.json"
        source_bytes = (json.dumps(source, ensure_ascii=False, indent=2) + "\n").encode()
        source_path.write_bytes(source_bytes)
        carried = {
            "source_path": source_path.name,
            "source_file_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "source_plan_sha256": source["plan_sha256"],
            "source_terminal_event_sha256": source["events"][-1]["event_sha256"],
            "source_event_count": 2,
            "generation_request_count_by_cut": {"cut-01": 1},
            "remaining_generation_actions_by_cut": {"cut-01": 1},
            "ledger_binding_sha256": "",
        }
        carried["ledger_binding_sha256"] = canonical_sha(
            {key: value for key, value in carried.items() if key != "ledger_binding_sha256"}
        )
        rebound = plan_fixture(["cut-01"], approved=True)
        rebound["carried_event_ledger"] = carried
        rebound["plan_sha256"] = canonical_sha(plan_projection(rebound))
        rebound["approval"]["bound_plan_sha256"] = rebound["plan_sha256"]
        append_event(rebound, "cut-01", "initial_generation_requested", "2026-08-28T14:01:00+09:00")
        restart_errors = validate(
            rebound, payload_fixture(["cut-01"], approved=True), Path(temp_dir) / "rebound.json"
        )
        if not any("cannot restart initial generation" in item for item in restart_errors):
            failures.append("reject initial-generation restart after carried spend")
    if failures:
        print("SELF-TEST FAILED: " + ", ".join(failures), file=sys.stderr)
        return 1
    print(f"SELF-TEST PASSED: {len(cases)} cases")
    return 0


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", nargs="?")
    parser.add_argument("--payload")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.plan or not args.payload:
        parser.error("plan and --payload are required unless --self-test is used")
    try:
        plan = load_json(args.plan)
        payload = load_json(args.payload)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    errors = validate(plan, payload, Path(args.plan))
    if errors:
        for error in errors:
            print(f"INVALID: {error}", file=sys.stderr)
        return 1
    print("VALID: product_video_execution_plan.v1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
