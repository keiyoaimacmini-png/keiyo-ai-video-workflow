#!/usr/bin/env python3
"""Select material from frozen lines, Gemini scenarios, and measured durations.

Duration is a pre-ranking gate. ChatCut placement is not a duration probe.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from approved_shots import candidate_from_history, matching_history_shots
from constants import MAJOR_VISUAL_KEYS
from paths import case_root
from prove_tts_speed import clip_target_duration
from script_fidelity import assert_immutable
from workflow_state import hold

DURATION_EPS = 1e-9
FILE_DURATION_KEYS = (
    "source_duration_seconds",
    "duration_sec",
    "file_duration_seconds",
)


def visual_diff_score(left: dict[str, Any], right: dict[str, Any]) -> int:
    return sum(1 for key in MAJOR_VISUAL_KEYS if left.get(key) != right.get(key))


def scenario_score(candidate: dict[str, Any], intended_scenario: str) -> int:
    if candidate.get("semantic_valid") is not True:
        return 0
    intended = (intended_scenario or "").strip()
    tags = candidate.get("scenario_tags") or []
    if candidate.get("situation") == intended or intended in tags:
        return 2
    return 1


def supports_line(candidate: dict[str, Any], line: str) -> bool:
    if candidate.get("semantic_valid") is not True:
        return False
    supported = candidate.get("supported_line")
    if supported is None:
        return True
    return supported == line


def source_id(item: dict[str, Any] | None) -> str:
    if not isinstance(item, dict):
        return ""
    value = item.get("source") or item.get("material_id") or item.get("path")
    return str(value) if value else ""


def framing_id(item: dict[str, Any] | None) -> str:
    visual = (item or {}).get("visual") if isinstance(item, dict) else {}
    if not isinstance(visual, dict):
        return ""
    return str(visual.get("framing") or visual.get("camera_distance") or "")


def same_source_and_angle(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    if not source_id(left) or source_id(left) != source_id(right):
        return False
    left_frame = framing_id(left)
    right_frame = framing_id(right)
    if left_frame and right_frame:
        return left_frame == right_frame
    return True


def _number(value: object, *, allow_zero: bool = False) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if allow_zero:
        return number if number >= 0 else None
    return number if number > 0 else None


def source_range(candidate: dict[str, Any]) -> tuple[float, float] | None:
    start = _number(candidate.get("source_in"), allow_zero=True)
    if start is None:
        start = _number(candidate.get("in_sec"), allow_zero=True)
    end = _number(candidate.get("source_out"))
    if end is None:
        end = _number(candidate.get("out_sec"))
    if start is None or end is None or end <= start:
        return None
    return (start, end)


def lookup_file_duration(
    candidate: dict[str, Any],
    file_durations: dict[str, float] | None = None,
) -> float | None:
    for key in FILE_DURATION_KEYS:
        duration = _number(candidate.get(key))
        if duration is not None:
            return duration
    if not file_durations:
        return None
    sid = source_id(candidate)
    if not sid:
        return None
    if sid in file_durations:
        return file_durations[sid]
    posix = sid.replace("\\", "/").lstrip("./")
    name = Path(posix).name
    for key, duration in file_durations.items():
        stored = str(key).replace("\\", "/")
        if posix.endswith("/" + stored) or stored.endswith("/" + posix) or stored == posix:
            return duration
        if Path(stored).name == name and name:
            return duration
    return None


def available_duration(
    candidate: dict[str, Any],
    file_durations: dict[str, float] | None = None,
) -> float | None:
    rng = source_range(candidate)
    if rng is not None:
        return rng[1] - rng[0]
    explicit = _number(candidate.get("available_duration"))
    if explicit is not None:
        return explicit
    return lookup_file_duration(candidate, file_durations)


def duration_passes(
    candidate: dict[str, Any],
    target_seconds: float,
    file_durations: dict[str, float] | None = None,
) -> bool:
    available = available_duration(candidate, file_durations)
    if available is None:
        return False
    return available + DURATION_EPS >= float(target_seconds)


def fit_window(
    file_duration: float,
    target_seconds: float,
    prefer_in: float | None = None,
    prefer_out: float | None = None,
) -> tuple[float, float] | None:
    file_duration = float(file_duration)
    target = float(target_seconds)
    if file_duration + DURATION_EPS < target:
        return None
    if prefer_in is None or prefer_out is None or prefer_out <= prefer_in:
        return (0.0, target)
    span = prefer_out - prefer_in
    if span + DURATION_EPS >= target:
        end = prefer_in + target
        if end <= file_duration + DURATION_EPS:
            return (prefer_in, prefer_in + target)
        start = max(0.0, file_duration - target)
        return (start, start + target)
    extra = target - span
    room_after = max(0.0, file_duration - prefer_out)
    after = min(extra, room_after)
    before = extra - after
    start = prefer_in - before
    end = prefer_out + after
    if start < 0:
        end -= start
        start = 0.0
    if end > file_duration:
        start -= end - file_duration
        end = file_duration
        start = max(0.0, start)
    if end - start + DURATION_EPS < target:
        start = max(0.0, file_duration - target)
        end = start + target
    return (start, end)


def as_full_clip(
    candidate: dict[str, Any],
    file_duration: float,
    target_seconds: float,
) -> dict[str, Any] | None:
    rng = source_range(candidate)
    window = fit_window(
        file_duration,
        target_seconds,
        rng[0] if rng else None,
        rng[1] if rng else None,
    )
    if window is None:
        return None
    clone = dict(candidate)
    clone["in_sec"] = window[0]
    clone["out_sec"] = window[1]
    clone["source_in"] = window[0]
    clone["source_out"] = window[1]
    clone["available_duration"] = window[1] - window[0]
    clone["source_duration_seconds"] = float(file_duration)
    clone["from_approved_history"] = False
    clone["full_clip"] = True
    return clone


def prefer_history_candidates(
    candidates: list[dict[str, Any]],
    *,
    line: str,
    intended_scenario: str,
    duration_seconds: float,
    history: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    matched = matching_history_shots(history, line=line, situation=intended_scenario)
    if not matched:
        return list(candidates)
    return [
        candidate_from_history(
            shot,
            line=line,
            situation=intended_scenario,
            duration_seconds=duration_seconds,
        )
        for shot in matched
    ] + list(candidates)


def duration_eligible(
    candidates: list[dict[str, Any]],
    target_seconds: float,
    file_durations: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    return [item for item in candidates if duration_passes(item, target_seconds, file_durations)]


def pick_from_pool(
    pool: list[dict[str, Any]],
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    ranked = list(pool)
    if previous is not None:
        ranked = sorted(
            ranked,
            key=lambda item: visual_diff_score(item.get("visual") or {}, previous.get("visual") or {}),
            reverse=True,
        )
        varied = [item for item in ranked if not same_source_and_angle(item, previous)]
        if varied:
            ranked = varied
    return ranked[0]


def stamp_selection(chosen: dict[str, Any], target_seconds: float, file_durations: dict[str, float] | None = None) -> dict[str, Any]:
    stamped = dict(chosen)
    rng = source_range(stamped)
    file_duration = lookup_file_duration(stamped, file_durations)
    if rng is None and file_duration is not None:
        window = fit_window(file_duration, target_seconds)
        if window is not None:
            rng = window
            stamped["full_clip"] = True
    if rng is not None:
        stamped["in_sec"] = rng[0]
        stamped["out_sec"] = rng[1]
        stamped["source_in"] = rng[0]
        stamped["source_out"] = rng[1]
        stamped["available_duration"] = rng[1] - rng[0]
    else:
        available = available_duration(stamped, file_durations)
        if available is not None:
            stamped["available_duration"] = available
    stamped["target_duration_seconds"] = float(target_seconds)
    return stamped


def select_cut(
    candidates: list[dict[str, Any]],
    *,
    line: str,
    intended_scenario: str,
    duration_seconds: float,
    previous: dict[str, Any] | None = None,
    history: dict[str, Any] | None = None,
    file_durations: dict[str, float] | None = None,
) -> dict[str, Any]:
    combined = prefer_history_candidates(
        candidates,
        line=line,
        intended_scenario=intended_scenario,
        duration_seconds=duration_seconds,
        history=history,
    )
    valid = [item for item in combined if supports_line(item, line)]
    if not valid:
        return hold("HOLD_MEDIA_NOT_MATCHED", "no semantically valid material for this line")
    eligible = duration_eligible(valid, duration_seconds, file_durations)
    if not eligible:
        return hold(
            "HOLD_MEDIA_NOT_MATCHED",
            "no material with available_duration >= target_duration_seconds",
        )
    best = max(scenario_score(item, intended_scenario) for item in eligible)
    pool = [item for item in eligible if scenario_score(item, intended_scenario) == best]
    history_in_pool = [item for item in pool if item.get("from_approved_history") is True]
    if history_in_pool:
        if previous is not None:
            varied_history = [item for item in history_in_pool if not same_source_and_angle(item, previous)]
            if varied_history:
                pool = varied_history
            else:
                varied = [item for item in pool if not same_source_and_angle(item, previous)]
                pool = varied or history_in_pool
        else:
            pool = history_in_pool
    chosen = stamp_selection(dict(pick_from_pool(pool, previous)), duration_seconds, file_durations)
    chosen["line"] = line
    chosen["intended_scenario"] = intended_scenario
    return {"status": "OK", "selection": chosen}


def assemble_plan(
    approved_script: dict[str, Any],
    narration_manifest: dict[str, Any],
    candidates_by_cut: dict[str, list[dict[str, Any]]],
    history: dict[str, Any] | None = None,
    file_durations: dict[str, float] | None = None,
) -> dict[str, Any]:
    clips = {clip["cut_id"]: clip for clip in narration_manifest.get("clips") or []}
    cuts: list[dict[str, Any]] = []
    previous = None
    for cut in approved_script.get("cuts") or []:
        fidelity = assert_immutable(cut["line"], cut["line"], role="assembly_line")
        if fidelity.get("status") != "OK":
            return fidelity
        clip = clips.get(cut["cut_id"])
        if not clip:
            return hold("HOLD_NARRATION_DURATION", f"missing narration duration for {cut['cut_id']}")
        target = clip_target_duration(clip)
        if target.get("status") != "OK":
            return hold(
                target.get("hold") or "HOLD_NARRATION_DURATION",
                target.get("reason") or f"invalid editorial duration for {cut['cut_id']}",
            )
        duration = target["target_duration_seconds"]
        selected = select_cut(
            candidates_by_cut.get(cut["cut_id"]) or [],
            line=cut["line"],
            intended_scenario=cut["situation"],
            duration_seconds=float(duration),
            previous=previous,
            history=history,
            file_durations=file_durations,
        )
        if selected.get("status") != "OK":
            return selected
        item = selected["selection"]
        item["cut_id"] = cut["cut_id"]
        item["situation"] = cut["situation"]
        cuts.append(item)
        previous = item
    return {
        "status": "OK",
        "schema": "product_video_assembly_plan.v1",
        "cuts": cuts,
    }


def write_plan(project_root: Path, case_id: str, plan: dict[str, Any]) -> Path:
    dest = case_root(project_root, case_id) / "assembly-plan.json"
    dest.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dest
