#!/usr/bin/env python3
"""Persist per-cut CapCut TTS generation attempts. Never reset a failed count to 0."""

from __future__ import annotations

import argparse
import json
from typing import Any

from constants import MAX_GENERATIONS_PER_CUT
from paths import case_root
from workflow_state import atomic_write, hold, now_iso

SCHEMA = "product_video_tts_generation_attempts.v1"
HOLD_ALLOWANCE = "HOLD_TTS_ALLOWANCE_EXHAUSTED"
HOLD_UNKNOWN = "HOLD_TTS_INPUT_FIELD_UNVERIFIED"


def attempts_path(project_root, case_id: str):
    return case_root(project_root, case_id) / "tts" / "generation-attempts.json"


def empty_attempts(case_id: str) -> dict[str, Any]:
    return {"schema": SCHEMA, "case_id": case_id, "cuts": {}}


def load_attempts(project_root, case_id: str) -> dict[str, Any]:
    path = attempts_path(project_root, case_id)
    if not path.is_file():
        return empty_attempts(case_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValueError("tts generation attempts schema mismatch")
    if data.get("case_id") != case_id:
        raise ValueError("tts generation attempts case_id mismatch")
    cuts = data.get("cuts")
    if not isinstance(cuts, dict):
        raise ValueError("tts generation attempts cuts must be an object")
    return data


def save_attempts(project_root, data: dict[str, Any]):
    case_id = data["case_id"]
    path = attempts_path(project_root, case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return path


def cut_record(data: dict[str, Any], cut_id: str) -> dict[str, Any]:
    cuts = data.get("cuts")
    if not isinstance(cuts, dict):
        return {}
    item = cuts.get(cut_id)
    return item if isinstance(item, dict) else {}


def generation_count_for_cut(data: dict[str, Any], cut_id: str) -> int:
    count = cut_record(data, cut_id).get("generation_count", 0)
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        return 0
    return count


def last_outcome(data: dict[str, Any], cut_id: str) -> str | None:
    value = cut_record(data, cut_id).get("last_outcome")
    return value if isinstance(value, str) else None


def max_generations_for_cut(data: dict[str, Any], cut_id: str) -> int:
    override = cut_record(data, cut_id).get("max_generations")
    if isinstance(override, int) and not isinstance(override, bool) and override > MAX_GENERATIONS_PER_CUT:
        return override
    return MAX_GENERATIONS_PER_CUT


def may_generate_cut(data: dict[str, Any], cut_id: str) -> dict[str, Any]:
    count = generation_count_for_cut(data, cut_id)
    outcome = last_outcome(data, cut_id)
    max_for_cut = max_generations_for_cut(data, cut_id)
    if outcome == "unknown":
        return hold(
            HOLD_UNKNOWN,
            "do not submit a new generation while the previous outcome is unknown",
            generate=False,
            generation_count_for_cut=count,
            last_outcome=outcome,
        )
    if count >= max_for_cut:
        return {
            "status": "HOLD",
            "hold": HOLD_ALLOWANCE,
            "generate": False,
            "generation_count_for_cut": count,
            "reason": "third or later TTS generation per cut is forbidden",
        }
    return {
        "status": "OK",
        "generate": True,
        "generation_count_for_cut": count,
        "next_attempt_number": count + 1,
        "last_outcome": outcome,
    }


def record_generation_attempt(
    project_root,
    case_id: str,
    cut_id: str,
    *,
    outcome: str,
    adopted_audio: bool = False,
    hold_code: str | None = None,
) -> dict[str, Any]:
    if not isinstance(cut_id, str) or not cut_id.strip():
        return hold("HOLD_TTS_INPUT_FIELD_UNVERIFIED", "cut_id is required")
    if outcome not in {"success", "failure", "unknown"}:
        return hold("HOLD_TTS_INPUT_FIELD_UNVERIFIED", "outcome must be success, failure, or unknown")
    data = load_attempts(project_root, case_id)
    current = generation_count_for_cut(data, cut_id)
    previous = last_outcome(data, cut_id)
    max_for_cut = max_generations_for_cut(data, cut_id)
    existing = cut_record(data, cut_id)
    if previous == "unknown":
        return hold(
            HOLD_UNKNOWN,
            "do not submit a new generation while the previous outcome is unknown",
            generate=False,
            generation_count_for_cut=current,
            last_outcome=previous,
        )
    if current >= max_for_cut:
        return {
            "status": "HOLD",
            "hold": HOLD_ALLOWANCE,
            "generate": False,
            "generation_count_for_cut": current,
            "reason": "third or later TTS generation per cut is forbidden",
        }
    adopted = bool(adopted_audio) and outcome == "success"
    if outcome != "success":
        adopted = False
    next_count = current + 1
    updated = {
        "generation_count": next_count,
        "last_outcome": outcome,
        "adopted_audio": adopted,
        "updated_at": now_iso(),
        "last_hold": hold_code,
    }
    if "max_generations" in existing:
        updated["max_generations"] = existing["max_generations"]
    if "exception_reason" in existing:
        updated["exception_reason"] = existing["exception_reason"]
    data.setdefault("cuts", {})[cut_id] = updated
    path = save_attempts(project_root, data)
    return {
        "status": "OK",
        "path": path.as_posix(),
        "cut_id": cut_id,
        "generation_count_for_cut": next_count,
        "last_outcome": outcome,
        "adopted_audio": adopted,
        "audio_adopted": adopted,
    }


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=str)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--cut-id", required=True)
    parser.add_argument("--print", action="store_true")
    parser.add_argument("--may-generate", action="store_true")
    parser.add_argument("--record-outcome", choices=["success", "failure", "unknown"])
    parser.add_argument("--adopted-audio", action="store_true")
    parser.add_argument("--hold-code")
    args = parser.parse_args()
    from pathlib import Path

    root = Path(args.project_root)
    data = load_attempts(root, args.case_id)
    if args.record_outcome:
        payload = record_generation_attempt(
            root,
            args.case_id,
            args.cut_id,
            outcome=args.record_outcome,
            adopted_audio=args.adopted_audio,
            hold_code=args.hold_code,
        )
    elif args.may_generate:
        payload = may_generate_cut(data, args.cut_id)
    else:
        payload = {
            "status": "OK",
            "cut_id": args.cut_id,
            "generation_count_for_cut": generation_count_for_cut(data, args.cut_id),
            "last_outcome": last_outcome(data, args.cut_id),
            "cut": cut_record(data, args.cut_id),
        }
    emit(payload)
    return 0 if payload.get("status") == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
