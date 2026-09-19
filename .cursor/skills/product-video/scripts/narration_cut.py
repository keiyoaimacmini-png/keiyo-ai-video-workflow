#!/usr/bin/env python3
"""One-cut NARRATION worker. Live CapCut field value vs frozen line, then Generate.

Happy path is one compare, not a chain of input helpers. The agent must pass the
value it just read from the CapCut field. Copying frozen_line into the actual
slot is rejected.
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

from classify_capcut_credit import NEW_CONTRACT_FLAGS
from constants import HOLD_TTS_INPUT_FIELD_UNVERIFIED
from narration_queue import record_queue_clip
from paths import emit
from tts_attempts import load_attempts, may_generate_cut, record_generation_attempt
from workflow_state import hold

HOLD_FIELD = HOLD_TTS_INPUT_FIELD_UNVERIFIED
HOLD_RESULT = "HOLD_TTS_RESULT_NOT_FRESH"
HOLD_DURATION = "HOLD_TTS_DURATION_ANOMALY"
MAX_INPUT_ATTEMPTS = 2
CUT_TIMING_STEPS = (
    "clear_write_readback",
    "generate_submit",
    "generate_wait",
    "result_capture",
    "record_cut",
    "cut_total",
)

# Remade Holiday Twist successes clustered around 0.16–0.22 s/char (3–7s).
# First-pass leftover accidents were 11–18s on the same one-line cuts.
# HOLD only obvious multi-line concatenation, not a slightly slow read.
ANOMALY_MIN_SECONDS = 11.0
ANOMALY_SECONDS_PER_CHAR = 0.40

LIVE_READBACK_SOURCES = frozenset(
    {
        "browser_field",
        "actual_textarea_value",
        "editor_model",
        "submission_state",
        "user_authored_dom_nodes",
    }
)
FABRICATED_SOURCES = frozenset(
    {
        "constructed",
        "expected",
        "frozen_line",
        "copied_expected",
        "inner_text_from_frozen",
    }
)
EXISTING_CREDIT_TITLES = frozenset({"Credits will be consumed", "クレジットが消費されます"})
PURCHASE_BODY_HINTS = (
    "subscribe",
    "subscription",
    "free trial",
    "buy credit",
    "purchase credit",
    "auto reload",
    "auto-reload",
    "monthly",
    "annual",
    "支払",
    "購入",
    "契約",
    "無料体験",
)


def _is_str(value: object) -> bool:
    return isinstance(value, str)


def observation_is_fabricated(frozen_line: str, observation: dict[str, Any] | None) -> bool:
    """True when expected frozen_line was reused as the alleged actual value."""
    if not isinstance(observation, dict):
        return False
    if observation.get("copied_from_frozen") is True or observation.get("expected_as_actual") is True:
        return True
    source = observation.get("readback_source")
    if source in FABRICATED_SOURCES:
        return True
    has_live_value = "browser_actual" in observation or (
        observation.get("browser_field_read") is True and "actual_readback" in observation
    )
    if has_live_value:
        return False
    if source in LIVE_READBACK_SOURCES and "actual_readback" in observation:
        return False
    inner = observation.get("inner_text")
    readback = observation.get("textarea_readback")
    if _is_str(frozen_line) and frozen_line != "":
        if inner == frozen_line or readback == frozen_line:
            return True
    return False


def live_actual_from_observation(observation: dict[str, Any] | None) -> str | None:
    if not isinstance(observation, dict):
        return None
    if observation_is_fabricated(str(observation.get("frozen_line") or ""), observation):
        return None
    for key in ("browser_actual", "actual_readback"):
        value = observation.get(key)
        if _is_str(value):
            return value
    return None


def compare_actual_readback(frozen_line: str, actual: str | None) -> dict[str, Any]:
    if not _is_str(frozen_line) or frozen_line == "":
        return hold(HOLD_FIELD, "frozen_line must be the approved non-empty line", generate=False)
    if actual is None:
        return hold(HOLD_FIELD, "actual CapCut field value unavailable", generate=False, exact_match=False)
    if not _is_str(actual):
        return hold(HOLD_FIELD, "actual CapCut field value must be a string", generate=False, exact_match=False)
    if actual != frozen_line:
        return {
            "status": "OK",
            "hold": None,
            "generate": False,
            "exact_match": False,
            "frozen_line": frozen_line,
            "actual": actual,
        }
    return {
        "status": "OK",
        "hold": None,
        "generate": False,
        "exact_match": True,
        "frozen_line": frozen_line,
        "actual": actual,
    }


def prove_input(
    frozen_line: str,
    actual: str | None,
    *,
    attempt: int = 1,
    observation: dict[str, Any] | None = None,
    generation_count_for_cut: int = 0,
    may_generate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(observation, dict) and observation_is_fabricated(frozen_line, observation):
        return hold(
            HOLD_FIELD,
            "frozen_line cannot be reused as the CapCut actual value",
            generate=False,
            fabricated_readback=True,
        )
    if actual is None and observation is not None:
        actual = live_actual_from_observation(observation)
        if actual is None and not observation_is_fabricated(frozen_line, observation):
            return hold(HOLD_FIELD, "actual CapCut field value unavailable", generate=False)
    compared = compare_actual_readback(frozen_line, actual)
    if compared.get("status") != "OK":
        return compared
    if compared.get("exact_match") is not True:
        retry = isinstance(attempt, int) and not isinstance(attempt, bool) and 1 <= attempt < MAX_INPUT_ATTEMPTS
        if retry:
            return {
                "status": "RETRY",
                "hold": None,
                "generate": False,
                "exact_match": False,
                "retry": True,
                "attempt": attempt,
                "generation_count_for_cut": generation_count_for_cut,
            }
        return hold(
            HOLD_FIELD,
            "actual CapCut field value is not exactly the frozen line after one retry",
            generate=False,
            exact_match=False,
            retry=False,
            attempt=attempt,
            generation_count_for_cut=generation_count_for_cut,
        )
    allowed = may_generate if isinstance(may_generate, dict) else {
        "status": "OK",
        "generate": True,
        "generation_count_for_cut": generation_count_for_cut,
    }
    if allowed.get("generate") is not True:
        payload = dict(allowed)
        payload["generate"] = False
        payload["exact_match"] = True
        return payload
    return {
        "status": "OK",
        "hold": None,
        "generate": True,
        "exact_match": True,
        "retry": False,
        "attempt": attempt,
        "generation_count_for_cut": allowed.get("generation_count_for_cut", generation_count_for_cut),
        "frozen_line": frozen_line,
        "actual": actual,
    }


def prove_result_fresh(before: object, after: object) -> dict[str, Any]:
    if after is None or after == "":
        return hold(HOLD_RESULT, "new CapCut result identity is missing", capture=False)
    if before is not None and before != "" and before == after:
        return hold(HOLD_RESULT, "result is the same as before Generate", capture=False, stale=True)
    return {"status": "OK", "hold": None, "capture": True, "before": before, "after": after}


def duration_is_anomaly(line: str, duration_seconds: float) -> bool:
    if not _is_str(line) or line == "":
        return True
    if not isinstance(duration_seconds, (int, float)) or isinstance(duration_seconds, bool):
        return True
    if duration_seconds <= 0:
        return True
    chars = len(line)
    return duration_seconds >= ANOMALY_MIN_SECONDS and duration_seconds >= chars * ANOMALY_SECONDS_PER_CHAR


def prove_duration(line: str, duration_seconds: float) -> dict[str, Any]:
    if duration_is_anomaly(line, duration_seconds):
        return hold(
            HOLD_DURATION,
            "source duration looks like leftover or stacked speech",
            adopt=False,
            line_chars=len(line) if _is_str(line) else 0,
            duration_seconds=duration_seconds,
        )
    return {
        "status": "OK",
        "hold": None,
        "adopt": True,
        "duration_seconds": float(duration_seconds),
        "remeasure": False,
    }


def credit_dialog_action(record: dict[str, Any] | None) -> dict[str, Any]:
    """Existing-balance Got it does not need classify_capcut_credit.py."""
    if record is None or record.get("present") is False or record == {}:
        return {"status": "OK", "action": "none", "require_classifier": False, "approve_got_it": False}
    if not isinstance(record, dict):
        return hold("HOLD_CAPCUT_CREDIT_UNVERIFIED", "credit dialog record must be an object", approve_got_it=False)
    for key, label in NEW_CONTRACT_FLAGS:
        if record.get(key) is True:
            return hold(
                "HOLD_CAPCUT_NEW_PURCHASE_REQUIRED",
                f"do not auto-approve {label}",
                approve_got_it=False,
                require_classifier=False,
                blocked_signal=key,
            )
    title = record.get("title")
    body = record.get("body") if isinstance(record.get("body"), str) else ""
    lowered = body.lower()
    if any(hint in lowered for hint in PURCHASE_BODY_HINTS) and title not in EXISTING_CREDIT_TITLES:
        return hold(
            "HOLD_CAPCUT_NEW_PURCHASE_REQUIRED",
            "do not auto-approve a new contract or purchase",
            approve_got_it=False,
            require_classifier=False,
        )
    if isinstance(title, str) and title in EXISTING_CREDIT_TITLES:
        return {
            "status": "OK",
            "action": "click_got_it",
            "require_classifier": False,
            "approve_got_it": True,
            "existing_balance_consumption": True,
        }
    return hold(
        "HOLD_CAPCUT_CREDIT_UNVERIFIED",
        "cannot distinguish existing-balance consumption from a new contract or purchase",
        approve_got_it=False,
        require_classifier=False,
    )


def empty_cut_timing() -> dict[str, Any]:
    return {step: {"started_at": None, "ended_at": None, "elapsed_seconds": None} for step in CUT_TIMING_STEPS}


def mark_timing(timing: dict[str, Any], step: str, *, start: bool, now: float | None = None) -> dict[str, Any]:
    if step not in CUT_TIMING_STEPS:
        raise KeyError(step)
    stamp = time.monotonic() if now is None else now
    item = dict(timing.get(step) or {})
    if start:
        item["started_at"] = stamp
    else:
        item["ended_at"] = stamp
        started = item.get("started_at")
        if isinstance(started, (int, float)) and not isinstance(started, bool):
            item["elapsed_seconds"] = float(stamp) - float(started)
    updated = dict(timing)
    updated[step] = item
    if step != "cut_total" and not start:
        first = (updated.get("clear_write_readback") or {}).get("started_at")
        last = item.get("ended_at")
        if isinstance(first, (int, float)) and isinstance(last, (int, float)):
            updated["cut_total"] = {
                "started_at": first,
                "ended_at": last,
                "elapsed_seconds": float(last) - float(first),
            }
    return updated


def finish_cut(
    project_root,
    case_id: str,
    *,
    cut_id: str,
    line: str,
    audio_path: str,
    capture: dict[str, Any],
    before_result: object,
    after_result: object,
    timing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fresh = prove_result_fresh(before_result, after_result)
    if fresh.get("capture") is not True:
        return fresh
    duration = capture.get("duration_seconds") if isinstance(capture, dict) else None
    if not isinstance(duration, (int, float)) or isinstance(duration, bool):
        return hold(HOLD_DURATION, "capture duration_seconds is missing", adopt=False)
    proved = prove_duration(line, float(duration))
    if proved.get("adopt") is not True:
        return proved
    recorded_attempt = record_generation_attempt(
        project_root,
        case_id,
        cut_id,
        outcome="success",
        adopted_audio=True,
    )
    if recorded_attempt.get("status") != "OK":
        return recorded_attempt
    queued = record_queue_clip(
        project_root,
        case_id,
        cut_id=cut_id,
        line=line,
        audio_path=audio_path,
        source_duration_seconds=float(duration),
        timing=timing,
    )
    if queued.get("status") != "OK":
        return queued
    queued["duration_seconds"] = float(duration)
    queued["remeasure"] = False
    queued["capture"] = True
    queued["generation_count_for_cut"] = recorded_attempt.get("generation_count_for_cut")
    return queued


def _load_json(raw: str | None) -> Any:
    if raw is None or raw == "":
        return None
    return json.loads(raw)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root")
    parser.add_argument("--case-id")
    parser.add_argument("--cut-id")
    parser.add_argument("--frozen-json")
    parser.add_argument("--actual-json")
    parser.add_argument("--observation-json")
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--prove-input", action="store_true")
    parser.add_argument("--prove-result", action="store_true")
    parser.add_argument("--before-id")
    parser.add_argument("--after-id")
    parser.add_argument("--prove-duration", action="store_true")
    parser.add_argument("--line")
    parser.add_argument("--duration-seconds", type=float)
    parser.add_argument("--credit-dialog", action="store_true")
    parser.add_argument("--record-json")
    parser.add_argument("--finish-cut", action="store_true")
    parser.add_argument("--audio-path")
    parser.add_argument("--capture-json")
    parser.add_argument("--timing-json")
    args = parser.parse_args()
    if args.prove_input:
        frozen = json.loads(args.frozen_json) if args.frozen_json else ""
        actual = json.loads(args.actual_json) if args.actual_json is not None else None
        observation = _load_json(args.observation_json)
        may = None
        count = 0
        if args.project_root and args.case_id and args.cut_id:
            from pathlib import Path

            may = may_generate_cut(load_attempts(Path(args.project_root), args.case_id), args.cut_id)
            count = int(may.get("generation_count_for_cut") or 0)
            if may.get("generate") is not True and actual == frozen:
                emit(may)
                return 2
        payload = prove_input(
            frozen,
            actual,
            attempt=args.attempt,
            observation=observation if isinstance(observation, dict) else None,
            generation_count_for_cut=count,
            may_generate=may,
        )
        emit(payload)
        return 0 if payload.get("generate") is True or payload.get("retry") is True else 2
    if args.prove_result:
        payload = prove_result_fresh(args.before_id, args.after_id)
        emit(payload)
        return 0 if payload.get("capture") is True else 2
    if args.prove_duration:
        payload = prove_duration(str(args.line or ""), float(args.duration_seconds or 0))
        emit(payload)
        return 0 if payload.get("adopt") is True else 2
    if args.credit_dialog:
        payload = credit_dialog_action(json.loads(args.record_json) if args.record_json else {})
        emit(payload)
        return 0 if payload.get("status") == "OK" else 2
    if args.finish_cut:
        from pathlib import Path

        if not args.project_root or not args.case_id or not args.cut_id:
            parser.error("--finish-cut requires --project-root --case-id --cut-id")
        payload = finish_cut(
            Path(args.project_root),
            args.case_id,
            cut_id=args.cut_id,
            line=str(args.line or ""),
            audio_path=str(args.audio_path or ""),
            capture=json.loads(args.capture_json) if args.capture_json else {},
            before_result=args.before_id,
            after_result=args.after_id,
            timing=_load_json(args.timing_json) if args.timing_json else None,
        )
        emit(payload)
        return 0 if payload.get("status") == "OK" else 2
    parser.error("choose --prove-input, --prove-result, --prove-duration, --credit-dialog, or --finish-cut")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
