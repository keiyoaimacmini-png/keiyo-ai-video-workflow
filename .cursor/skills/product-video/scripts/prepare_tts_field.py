#!/usr/bin/env python3
"""Prepare CapCut TTS input by full clear + frozen-line write, then raw exact read-back.

Never trim, strip, ignore newlines, ignore zero-width characters, normalize
Unicode, or treat visible/OCR text as a match. Generate is allowed only when
the actual field value equals the frozen line. One input retry is allowed and
does not count as a TTS generation.
"""

from __future__ import annotations

import argparse
import json
import unicodedata
from typing import Any, Protocol

HOLD_FIELD = "HOLD_TTS_INPUT_FIELD_UNVERIFIED"
MAX_INPUT_ATTEMPTS = 2
CONTROL_NAMES = {
    "\n": "LINE FEED (LF)",
    "\r": "CARRIAGE RETURN (CR)",
    "\t": "CHARACTER TABULATION",
}


class TtsField(Protocol):
    def identify(self) -> str | None: ...
    def clear(self) -> bool: ...
    def write(self, text: str) -> bool: ...
    def read_actual(self) -> str | None: ...


def codepoint_label(char: str) -> str:
    label = f"U+{ord(char):04X}"
    name = CONTROL_NAMES.get(char)
    if name is None:
        try:
            name = unicodedata.name(char)
        except ValueError:
            return label
    return f"{label} {name}"


def diagnose_mismatch(expected: str, actual: str | None) -> dict[str, Any]:
    if actual is None:
        return {
            "match": False,
            "reason": "actual textarea value unavailable",
            "expected_length": len(expected),
            "actual_length": None,
            "expected_repr": repr(expected),
            "actual_repr": None,
            "diff_index": None,
            "extra_codepoint": None,
            "missing_codepoint": None,
        }
    if expected == actual:
        return {"match": True}
    limit = min(len(expected), len(actual))
    index = next((i for i in range(limit) if expected[i] != actual[i]), limit)
    extra = actual[index] if index < len(actual) else None
    missing = expected[index] if index < len(expected) else None
    return {
        "match": False,
        "reason": "actual textarea value is not exactly the frozen line",
        "expected_length": len(expected),
        "actual_length": len(actual),
        "expected_repr": repr(expected),
        "actual_repr": repr(actual),
        "diff_index": index,
        "extra_codepoint": codepoint_label(extra) if extra is not None else None,
        "missing_codepoint": codepoint_label(missing) if missing is not None else None,
    }


def compare_tts_readback(
    frozen_line: str,
    actual: str | None,
    *,
    attempt: int,
    generation_count_for_cut: int,
) -> dict[str, Any]:
    if not isinstance(frozen_line, str) or frozen_line == "":
        return {
            "status": "HOLD",
            "hold": HOLD_FIELD,
            "generate": False,
            "retry": False,
            "generation_count_for_cut": generation_count_for_cut,
            "reason": "frozen_line must be the approved non-empty line",
        }
    if actual is None:
        return {
            "status": "HOLD",
            "hold": HOLD_FIELD,
            "generate": False,
            "retry": False,
            "generation_count_for_cut": generation_count_for_cut,
            "reason": "actual textarea value unavailable",
            "diagnostic": diagnose_mismatch(frozen_line, None),
        }
    if actual == frozen_line:
        return {
            "status": "OK",
            "generate": False,
            "exact_match": True,
            "retry": False,
            "attempt": attempt,
            "generation_count_for_cut": generation_count_for_cut,
            "readback_source": "actual_textarea_value",
            "textarea_readback": actual,
            "frozen_line": frozen_line,
        }
    diagnostic = diagnose_mismatch(frozen_line, actual)
    retry = attempt < MAX_INPUT_ATTEMPTS
    return {
        "status": "HOLD" if not retry else "RETRY",
        "hold": HOLD_FIELD if not retry else None,
        "generate": False,
        "exact_match": False,
        "retry": retry,
        "attempt": attempt,
        "generation_count_for_cut": generation_count_for_cut,
        "diagnostic": diagnostic,
    }


def _write_frozen_only(field: TtsField, frozen_line: str) -> dict[str, Any]:
    field_id = field.identify()
    if not isinstance(field_id, str) or not field_id.strip():
        return {"status": "HOLD", "hold": HOLD_FIELD, "reason": "target textarea field must be identified"}
    if not field.clear():
        return {"status": "HOLD", "hold": HOLD_FIELD, "reason": "textarea clear failed"}
    emptied = field.read_actual()
    if emptied is None:
        return {
            "status": "HOLD",
            "hold": HOLD_FIELD,
            "reason": "actual textarea value unavailable",
            "diagnostic": diagnose_mismatch("", None),
        }
    if emptied != "":
        return {
            "status": "HOLD",
            "hold": HOLD_FIELD,
            "reason": "textarea was not completely empty after clear; refusing to append",
            "diagnostic": diagnose_mismatch("", emptied),
        }
    if not field.write(frozen_line):
        return {"status": "HOLD", "hold": HOLD_FIELD, "reason": "textarea write failed"}
    actual = field.read_actual()
    if actual is None:
        return {
            "status": "HOLD",
            "hold": HOLD_FIELD,
            "reason": "actual textarea value unavailable",
            "diagnostic": diagnose_mismatch(frozen_line, None),
        }
    return {"status": "OK", "field_id": field_id, "actual": actual}


def prepare_tts_field(
    field: TtsField,
    frozen_line: str,
    *,
    generation_count_for_cut: int = 0,
    previous_line: str | None = None,
) -> dict[str, Any]:
    start_count = generation_count_for_cut
    diagnostics: list[dict[str, Any]] = []
    field_id: str | None = None
    for attempt in range(1, MAX_INPUT_ATTEMPTS + 1):
        applied = _write_frozen_only(field, frozen_line)
        if applied.get("status") != "OK":
            payload = dict(applied)
            payload["generate"] = False
            payload["retry"] = False
            payload["generation_count_for_cut"] = start_count
            payload["input_attempts"] = attempt
            return payload
        field_id = applied["field_id"]
        actual = applied["actual"]
        compared = compare_tts_readback(
            frozen_line,
            actual,
            attempt=attempt,
            generation_count_for_cut=start_count,
        )
        if compared.get("exact_match") is True:
            record = {
                "field_id": field_id,
                "field_identified": True,
                "full_replace_applied": True,
                "textarea_readback": actual,
                "readback_source": "actual_textarea_value",
                "frozen_line": frozen_line,
                "previous_line": previous_line,
                "input_tool_success": True,
                "generation_count_for_cut": start_count,
                "input_attempts": attempt,
            }
            return {
                "status": "OK",
                "generate": False,
                "exact_match": True,
                "retry": False,
                "record": record,
                "input_attempts": attempt,
                "generation_count_for_cut": start_count,
            }
        diagnostics.append(compared.get("diagnostic") or diagnose_mismatch(frozen_line, actual))
        if not compared.get("retry"):
            break
    return {
        "status": "HOLD",
        "hold": HOLD_FIELD,
        "generate": False,
        "retry": False,
        "exact_match": False,
        "generation_count_for_cut": start_count,
        "input_attempts": MAX_INPUT_ATTEMPTS,
        "diagnostics": diagnostics,
        "reason": "actual textarea value is not exactly the frozen line after one retry",
    }


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen-json", help="JSON string of the frozen line")
    parser.add_argument("--actual-json", help="JSON string of the actual textarea value")
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--generation-count", type=int, default=0)
    args = parser.parse_args()
    if args.frozen_json is None:
        parser.error("--frozen-json is required")
    frozen = json.loads(args.frozen_json)
    actual = json.loads(args.actual_json) if args.actual_json is not None else None
    payload = compare_tts_readback(
        frozen,
        actual,
        attempt=args.attempt,
        generation_count_for_cut=args.generation_count,
    )
    emit(payload)
    return 0 if payload.get("exact_match") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
