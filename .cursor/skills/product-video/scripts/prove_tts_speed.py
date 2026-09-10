#!/usr/bin/env python3
"""Gate CapCut TTS generate on a read-back of the live speed value.

Calling onSpeedChange(1.2) is not proof. Generate only when the actual
CapCut speed value equals 1.2.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from constants import NARRATION_SPEED

HOLD_SPEED = "HOLD_TTS_SPEED_UNVERIFIED"
ALLOWED_READBACK_SOURCES = frozenset({"ui", "selected_state", "internal_model"})


def prove_tts_speed(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {
            "status": "HOLD",
            "hold": HOLD_SPEED,
            "generate": False,
            "reason": "speed record must be an object",
        }
    actual = record.get("actual_speed")
    setter_called = record.get("on_speed_change_called") is True or record.get("setter_succeeded") is True
    if not isinstance(actual, (int, float)) or isinstance(actual, bool):
        return {
            "status": "HOLD",
            "hold": HOLD_SPEED,
            "generate": False,
            "reason": "actual CapCut speed value is unavailable",
            "on_speed_change_called": setter_called,
            "actual_speed": None,
        }
    if actual != NARRATION_SPEED:
        return {
            "status": "HOLD",
            "hold": HOLD_SPEED,
            "generate": False,
            "reason": "actual CapCut speed is not 1.2",
            "actual_speed": actual,
            "on_speed_change_called": setter_called,
        }
    source = record.get("speed_readback_source")
    if source is not None and source not in ALLOWED_READBACK_SOURCES:
        return {
            "status": "HOLD",
            "hold": HOLD_SPEED,
            "generate": False,
            "reason": "speed read-back source must be ui, selected_state, or internal_model",
            "speed_readback_source": source,
            "actual_speed": actual,
        }
    return {
        "status": "OK",
        "hold": None,
        "generate": False,
        "speed_ok": True,
        "actual_speed": NARRATION_SPEED,
        "speed_readback_source": source,
    }


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record-json", required=True)
    args = parser.parse_args()
    payload = prove_tts_speed(json.loads(args.record_json))
    emit(payload)
    return 0 if payload.get("speed_ok") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
