#!/usr/bin/env python3
"""Owned by /product-video. Gate CapCut TTS generation on an actual textarea read-back.

Identify the target field, require a full replace, then compare the live
field value to the frozen line. A tool-success response is not a match.
Do not generate when the read-back is mixed, stale, or unverified.
"""

from __future__ import annotations

import argparse
import json
from typing import Any


HOLD_FIELD = "HOLD_TTS_INPUT_FIELD_UNVERIFIED"
HOLD_ALLOWANCE = "HOLD_TTS_ALLOWANCE_EXHAUSTED"
MAX_GENERATIONS_PER_CUT = 2


def normalize_line(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value


def leftover_mixed(readback: str, frozen_line: str, previous_line: str | None) -> bool:
    if readback == frozen_line:
        return False
    if previous_line and previous_line in readback and frozen_line in readback and readback != frozen_line:
        return True
    if frozen_line in readback and readback != frozen_line:
        return True
    return False


def decide_tts_generate(record: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(record, dict):
        return {"status": "HOLD", "hold": HOLD_FIELD, "generate": False, "errors": ["record must be an object"]}

    frozen = normalize_line(record.get("frozen_line"))
    readback = normalize_line(record.get("textarea_readback"))
    field_id = record.get("field_id")
    identified = record.get("field_identified") is True
    replaced = record.get("full_replace_applied") is True
    readback_source = record.get("readback_source")
    tool_ok = record.get("input_tool_success") is True
    generations = record.get("generation_count_for_cut")
    request_id = record.get("generation_request_id")
    clip_id = record.get("adopted_clip_id")
    expected_clip = record.get("expected_clip_id")
    previous_clip = record.get("previous_clip_id")
    outcome = record.get("previous_outcome")

    if not identified or not isinstance(field_id, str) or not field_id.strip():
        errors.append("target textarea field must be identified")
    if frozen is None or not frozen:
        errors.append("frozen_line must be the approved non-empty line")
    if not replaced:
        errors.append("textarea must be fully replaced, not appended")
    if readback_source != "actual_textarea_value":
        errors.append("readback_source must be actual_textarea_value")
    if readback is None:
        errors.append("textarea_readback is unavailable")
        return {"status": "HOLD", "hold": HOLD_FIELD, "generate": False, "errors": errors}
    if leftover_mixed(readback, frozen or "", record.get("previous_line") if isinstance(record.get("previous_line"), str) else None):
        errors.append("textarea read-back mixes leftover text with the frozen line")
    elif readback != frozen:
        errors.append("textarea read-back must equal the frozen line exactly")
    if tool_ok and readback != frozen:
        errors.append("input_tool_success is not proof of textarea match")
    if not isinstance(generations, int) or isinstance(generations, bool) or generations < 0:
        errors.append("generation_count_for_cut must be a non-negative integer")
    elif generations >= MAX_GENERATIONS_PER_CUT:
        return {
            "status": "HOLD",
            "hold": HOLD_ALLOWANCE,
            "generate": False,
            "errors": ["third or later TTS generation per cut is forbidden"],
        }
    if outcome == "unknown":
        errors.append("do not submit a new generation while the previous outcome is unknown")
    if clip_id is not None and previous_clip is not None and clip_id == previous_clip:
        errors.append("do not adopt a previous or other-cut clip as this generation")
    if expected_clip is not None and clip_id is not None and clip_id != expected_clip:
        errors.append("adopted clip is not bound to this case/cut/request")
    if request_id is not None and not isinstance(request_id, str):
        errors.append("generation_request_id must be a string when present")

    if errors:
        return {"status": "HOLD", "hold": HOLD_FIELD, "generate": False, "errors": errors}
    return {
        "status": "READY",
        "hold": None,
        "generate": True,
        "errors": [],
        "bound_field_id": field_id,
        "bound_frozen_line": frozen,
    }


def self_test() -> int:
    frozen = "そんな時はこのサンシェード。"
    previous = "夏の車、サウナレベルで暑いの地獄すぎん？"
    ready = decide_tts_generate({
        "field_id": "capcut-tts-textarea",
        "field_identified": True,
        "full_replace_applied": True,
        "textarea_readback": frozen,
        "readback_source": "actual_textarea_value",
        "frozen_line": frozen,
        "previous_line": previous,
        "input_tool_success": True,
        "generation_count_for_cut": 0,
        "generation_request_id": "req-1",
    })
    if ready.get("generate") is not True or ready.get("status") != "READY":
        print("SELF-TEST FAILED: exact read-back should allow generate")
        return 1
    mixed = decide_tts_generate({
        "field_id": "capcut-tts-textarea",
        "field_identified": True,
        "full_replace_applied": True,
        "textarea_readback": previous + frozen,
        "readback_source": "actual_textarea_value",
        "frozen_line": frozen,
        "previous_line": previous,
        "input_tool_success": True,
        "generation_count_for_cut": 0,
    })
    if mixed.get("generate") is not False or mixed.get("hold") != HOLD_FIELD:
        print("SELF-TEST FAILED: leftover mixed textarea must not generate")
        return 1
    tool_only = decide_tts_generate({
        "field_id": "capcut-tts-textarea",
        "field_identified": True,
        "full_replace_applied": True,
        "textarea_readback": previous,
        "readback_source": "actual_textarea_value",
        "frozen_line": frozen,
        "input_tool_success": True,
        "generation_count_for_cut": 0,
    })
    if tool_only.get("generate") is not False:
        print("SELF-TEST FAILED: tool success must not replace textarea match")
        return 1
    third = decide_tts_generate({
        "field_id": "capcut-tts-textarea",
        "field_identified": True,
        "full_replace_applied": True,
        "textarea_readback": frozen,
        "readback_source": "actual_textarea_value",
        "frozen_line": frozen,
        "generation_count_for_cut": 2,
    })
    if third.get("hold") != HOLD_ALLOWANCE:
        print("SELF-TEST FAILED: third generation must HOLD")
        return 1
    stale = decide_tts_generate({
        "field_id": "capcut-tts-textarea",
        "field_identified": True,
        "full_replace_applied": True,
        "textarea_readback": frozen,
        "readback_source": "actual_textarea_value",
        "frozen_line": frozen,
        "generation_count_for_cut": 1,
        "adopted_clip_id": "old-clip",
        "previous_clip_id": "old-clip",
    })
    if stale.get("generate") is not False:
        print("SELF-TEST FAILED: previous clip adoption must be rejected")
        return 1
    unknown = decide_tts_generate({
        "field_id": "capcut-tts-textarea",
        "field_identified": True,
        "full_replace_applied": True,
        "textarea_readback": frozen,
        "readback_source": "actual_textarea_value",
        "frozen_line": frozen,
        "generation_count_for_cut": 0,
        "previous_outcome": "unknown",
    })
    if unknown.get("generate") is not False:
        print("SELF-TEST FAILED: unknown previous outcome must not resubmit")
        return 1
    second = decide_tts_generate({
        "field_id": "capcut-tts-textarea",
        "field_identified": True,
        "full_replace_applied": True,
        "textarea_readback": frozen,
        "readback_source": "actual_textarea_value",
        "frozen_line": frozen,
        "generation_count_for_cut": 1,
        "generation_request_id": "req-2",
        "expected_clip_id": "clip-2",
        "adopted_clip_id": "clip-2",
        "previous_clip_id": "clip-1",
    })
    if second.get("generate") is not True:
        print("SELF-TEST FAILED: second generate after exact read-back should remain allowed")
        return 1
    print("SELF-TEST PASSED: 7 cases")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--record-json", type=str)
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.record_json:
        parser.error("provide --record-json or --self-test")
    result = decide_tts_generate(json.loads(args.record_json))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("generate") else 1


if __name__ == "__main__":
    raise SystemExit(main())
