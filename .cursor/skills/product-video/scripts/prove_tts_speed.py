#!/usr/bin/env python3
"""Prove ChatCut clip playbackRate. CapCut generate speed is not this proof.

edit_item updates audio items with playbackRate. inspect_item read-back is
the source. Calling a setter is not proof. Do not treat CapCut speechRate
or actual_speed as the editorial 1.2x.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from constants import NARRATION_SPEED

HOLD_SPEED = "HOLD_TTS_SPEED_UNVERIFIED"
ALLOWED_READBACK_SOURCES = frozenset({"chatcut_item"})
MEASURED_DURATION_SOURCES = frozenset({"chatcut_item"})


def planned_editorial_duration(
    source_duration_seconds: object,
    playback_rate: object = NARRATION_SPEED,
) -> dict[str, Any]:
    if not isinstance(source_duration_seconds, (int, float)) or isinstance(source_duration_seconds, bool):
        return {
            "status": "HOLD",
            "hold": HOLD_SPEED,
            "reason": "source_duration_seconds is required",
        }
    if source_duration_seconds <= 0:
        return {
            "status": "HOLD",
            "hold": HOLD_SPEED,
            "reason": "source_duration_seconds must be positive",
        }
    if not isinstance(playback_rate, (int, float)) or isinstance(playback_rate, bool):
        return {
            "status": "HOLD",
            "hold": HOLD_SPEED,
            "reason": "editor playback_rate is required",
        }
    if playback_rate != NARRATION_SPEED:
        return {
            "status": "HOLD",
            "hold": HOLD_SPEED,
            "reason": "editor playback_rate must be 1.2",
            "playback_rate": playback_rate,
        }
    planned = float(source_duration_seconds) / float(playback_rate)
    return {
        "status": "OK",
        "hold": None,
        "source_duration_seconds": float(source_duration_seconds),
        "editor_playback_rate": NARRATION_SPEED,
        "planned_duration_seconds": planned,
        "pre_accelerated": False,
    }


def clip_target_duration(clip: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(clip, dict):
        return {
            "status": "HOLD",
            "hold": "HOLD_NARRATION_DURATION",
            "reason": "narration clip must be an object",
        }
    if clip.get("source_already_accelerated") is True:
        return {
            "status": "HOLD",
            "hold": HOLD_SPEED,
            "reason": "do not treat the source file as already 1.2x processed",
        }
    source = clip.get("source_duration_seconds")
    planned = clip.get("planned_duration_seconds")
    rate = clip.get("editor_playback_rate")
    computed = planned_editorial_duration(source, rate if rate is not None else NARRATION_SPEED)
    if computed.get("status") != "OK":
        return {
            "status": "HOLD",
            "hold": computed.get("hold") or "HOLD_NARRATION_DURATION",
            "reason": computed.get("reason") or "planned editorial duration is unavailable",
        }
    expected = computed["planned_duration_seconds"]
    if not isinstance(planned, (int, float)) or isinstance(planned, bool):
        return {
            "status": "HOLD",
            "hold": "HOLD_NARRATION_DURATION",
            "reason": "planned_duration_seconds is required and is not the source duration",
        }
    if float(planned) != expected:
        return {
            "status": "HOLD",
            "hold": "HOLD_NARRATION_DURATION",
            "reason": "planned_duration_seconds must equal source_duration_seconds / 1.2",
            "source_duration_seconds": computed["source_duration_seconds"],
            "planned_duration_seconds": float(planned),
            "expected_planned_duration_seconds": expected,
        }
    return {
        "status": "OK",
        "target_duration_seconds": expected,
        "source_duration_seconds": computed["source_duration_seconds"],
        "editor_playback_rate": NARRATION_SPEED,
        "planned_duration_seconds": expected,
    }


def prove_editorial_timing(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {
            "status": "HOLD",
            "hold": HOLD_SPEED,
            "reason": "editorial timing record must be an object",
        }
    target = clip_target_duration(record)
    if target.get("status") != "OK":
        return target
    measured = record.get("measured_duration_seconds")
    measured_source = record.get("measured_duration_source")
    if measured_source in {"calculated", "planned", "source_divided"}:
        return {
            "status": "HOLD",
            "hold": HOLD_SPEED,
            "reason": "measured ChatCut duration must not be copied from the calculated plan",
            "planned_duration_seconds": target["planned_duration_seconds"],
            "measured_duration_source": measured_source,
        }
    if measured_source not in MEASURED_DURATION_SOURCES:
        return {
            "status": "HOLD",
            "hold": HOLD_SPEED,
            "reason": "measured duration source must be chatcut_item",
            "measured_duration_source": measured_source,
        }
    if not isinstance(measured, (int, float)) or isinstance(measured, bool) or measured <= 0:
        return {
            "status": "HOLD",
            "hold": HOLD_SPEED,
            "reason": "ChatCut measured duration is unavailable",
        }
    return {
        "status": "OK",
        "hold": None,
        "source_duration_seconds": target["source_duration_seconds"],
        "editor_playback_rate": NARRATION_SPEED,
        "planned_duration_seconds": target["planned_duration_seconds"],
        "measured_duration_seconds": float(measured),
        "measured_duration_source": measured_source,
        "durations_distinguished": True,
    }


def prove_tts_speed(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {
            "status": "HOLD",
            "hold": HOLD_SPEED,
            "generate": False,
            "reason": "speed record must be an object",
        }
    setter_called = record.get("on_speed_change_called") is True or record.get("setter_succeeded") is True
    if record.get("actual_speed") is not None and record.get("playback_rate") is None:
        return {
            "status": "HOLD",
            "hold": HOLD_SPEED,
            "generate": False,
            "reason": "CapCut actual_speed is not ChatCut clip playbackRate proof",
            "on_speed_change_called": setter_called,
            "actual_speed": record.get("actual_speed"),
        }
    actual = record.get("playback_rate")
    if not isinstance(actual, (int, float)) or isinstance(actual, bool):
        return {
            "status": "HOLD",
            "hold": HOLD_SPEED,
            "generate": False,
            "reason": "ChatCut inspect_item playbackRate is unavailable",
            "on_speed_change_called": setter_called,
            "playback_rate": None,
        }
    if actual != NARRATION_SPEED:
        return {
            "status": "HOLD",
            "hold": HOLD_SPEED,
            "generate": False,
            "reason": "ChatCut playbackRate is not 1.2",
            "playback_rate": actual,
            "on_speed_change_called": setter_called,
        }
    source = record.get("speed_readback_source")
    if source not in ALLOWED_READBACK_SOURCES:
        return {
            "status": "HOLD",
            "hold": HOLD_SPEED,
            "generate": False,
            "reason": "speed read-back source must be chatcut_item",
            "speed_readback_source": source,
            "playback_rate": actual,
        }
    return {
        "status": "OK",
        "hold": None,
        "generate": False,
        "speed_ok": True,
        "playback_rate": NARRATION_SPEED,
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
