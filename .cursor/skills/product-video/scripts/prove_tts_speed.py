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
from paths import case_root

HOLD_SPEED = "HOLD_TTS_SPEED_UNVERIFIED"
PLAYBACK_OVERRIDE_FILENAME = "playback-override.json"


def _locked_segments(raw: object) -> list[dict[str, Any]] | None:
    if not isinstance(raw, list) or not raw:
        return None
    cleaned: list[dict[str, Any]] = []
    for seg in raw:
        if not isinstance(seg, dict):
            return None
        src = seg.get("source")
        start = seg.get("source_in")
        end = seg.get("source_out")
        if not isinstance(src, str) or not src.strip():
            return None
        if isinstance(start, bool) or not isinstance(start, (int, float)) or start < 0:
            return None
        if isinstance(end, bool) or not isinstance(end, (int, float)) or float(end) <= float(start):
            return None
        cleaned.append(
            {
                "source": src.strip(),
                "source_in": float(start),
                "source_out": float(end),
                "duration": float(end) - float(start),
            }
        )
    return cleaned
ALLOWED_READBACK_SOURCES = frozenset({"chatcut_item"})
MEASURED_DURATION_SOURCES = frozenset({"chatcut_item"})


def planned_editorial_duration(
    source_duration_seconds: object,
    playback_rate: object = NARRATION_SPEED,
    *,
    allow_rate: float | None = None,
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
    if playback_rate != NARRATION_SPEED and playback_rate != allow_rate:
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
        "editor_playback_rate": float(playback_rate),
        "planned_duration_seconds": planned,
        "pre_accelerated": False,
    }


def clip_target_duration(clip: dict[str, Any], *, allow_rate: float | None = None) -> dict[str, Any]:
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
    computed = planned_editorial_duration(
        source,
        rate if rate is not None else NARRATION_SPEED,
        allow_rate=allow_rate,
    )
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
            "reason": "planned_duration_seconds must equal source_duration_seconds / editor_playback_rate",
            "source_duration_seconds": computed["source_duration_seconds"],
            "planned_duration_seconds": float(planned),
            "expected_planned_duration_seconds": expected,
        }
    return {
        "status": "OK",
        "target_duration_seconds": expected,
        "source_duration_seconds": computed["source_duration_seconds"],
        "editor_playback_rate": computed["editor_playback_rate"],
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
        "editor_playback_rate": target["editor_playback_rate"],
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
    expected = record.get("expected_playback_rate", NARRATION_SPEED)
    if actual != expected:
        return {
            "status": "HOLD",
            "hold": HOLD_SPEED,
            "generate": False,
            "reason": "ChatCut playbackRate is not 1.2" if expected == NARRATION_SPEED else "ChatCut playbackRate does not match the case plan",
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
        "playback_rate": actual,
        "speed_readback_source": source,
    }


def case_allow_narration_rate(project_root: Any, case_id: str) -> float | None:
    """Non-default editorial rate for this case. 1.2 needs no allow_rate."""
    override = load_playback_override(project_root, case_id)
    rate = override.get("narration_playback_rate")
    if not isinstance(rate, float):
        from pathlib import Path

        from workflow_state import load_state

        try:
            state = load_state(Path(project_root), case_id)
        except (OSError, ValueError, KeyError):
            return None
        raw = state.get("narration_speed")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or raw <= 0:
            return None
        rate = float(raw)
    if float(rate) == NARRATION_SPEED:
        return None
    return float(rate)


def load_playback_override(project_root: Any, case_id: str) -> dict[str, Any]:
    path = case_root(project_root, case_id) / PLAYBACK_OVERRIDE_FILENAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    rate = data.get("narration_playback_rate")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or rate <= 0:
        return {}
    video = data.get("video_playback_rate_by_cut")
    rates: dict[str, float] = {}
    if isinstance(video, dict):
        for cut_id, value in video.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                continue
            rates[str(cut_id)] = float(value)
    locked = data.get("locked_sources")
    sources: dict[str, dict[str, Any]] = {}
    if isinstance(locked, dict):
        for cut_id, source in locked.items():
            if isinstance(source, str) and source.strip():
                sources[str(cut_id)] = {"source": source.strip(), "source_in": 0.0}
            elif isinstance(source, dict) and isinstance(source.get("source"), str) and source.get("source").strip():
                start = source.get("source_in", 0.0)
                if isinstance(start, bool) or not isinstance(start, (int, float)) or start < 0:
                    start = 0.0
                entry = {"source": source["source"].strip(), "source_in": float(start)}
                segments = _locked_segments(source.get("segments"))
                if segments:
                    entry["segments"] = segments
                    entry["source"] = segments[0]["source"]
                    entry["source_in"] = segments[0]["source_in"]
                sources[str(cut_id)] = entry
    return {
        "narration_playback_rate": float(rate),
        "video_playback_rate_by_cut": rates,
        "locked_sources": sources,
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
