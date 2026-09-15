#!/usr/bin/env python3
"""Select material from frozen lines, Gemini scenarios, and measured durations.

Duration is a pre-ranking gate. ChatCut placement is not a duration probe.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from approved_shots import candidate_from_history, history_close_enough, matching_history_shots
from constants import MAJOR_VISUAL_KEYS
from paths import case_root
from prove_tts_speed import clip_target_duration
from script_fidelity import assert_immutable
from semantic_material_match import (
    apply_semantic_matches,
    catalog_history_payloads,
    collect_scene_payloads,
    load_matches,
    merge_scene_payloads,
    persist_matches,
    run_semantic_fallback,
)
from visual_catalog import scene_match_score, scene_text
from workflow_state import hold

DURATION_EPS = 1e-9
MAX_RANGE_PAD_SECONDS = 0.5
MAX_SEGMENTS_PER_CUT = 2
COVERAGE_PATTERNS = (
    ("UV", re.compile(r"(?<![A-Za-z])UV(?![A-Za-z])")),
    ("UPF", re.compile(r"(?<![A-Za-z])UPF(?![A-Za-z0-9])")),
    ("紫外線", re.compile(r"紫外線")),
    ("遮断", re.compile(r"遮断")),
    ("遮る", re.compile(r"遮る")),
    ("ブロック", re.compile(r"ブロック")),
    ("陰", re.compile(r"陰")),
    ("影", re.compile(r"(?<![撮投])影")),
)
FILE_DURATION_KEYS = (
    "source_duration_seconds",
    "duration_sec",
    "file_duration_seconds",
)
ADJACENT_COMPARE_AXES = (
    "framing",
    "location",
    "subject",
    "action",
    "product_state",
)
CONTINUITY_AXES = ("framing", "subject", "action", "location")


def _join_norm(value: object) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, (list, tuple, set)):
        parts = [_join_norm(item) for item in value]
        return " ".join(part for part in parts if part)
    if isinstance(value, dict):
        return ""
    text = str(value).strip().lower()
    return " ".join(text.split())


def visual_profile(item: dict[str, Any] | None) -> dict[str, str]:
    item = item if isinstance(item, dict) else {}
    visual = item.get("visual") if isinstance(item.get("visual"), dict) else {}
    scene = item.get("catalog_scene") if isinstance(item.get("catalog_scene"), dict) else {}
    framing = _join_norm(
        visual.get("framing") or visual.get("camera_distance") or scene.get("framing")
    )
    camera = _join_norm(
        visual.get("camera_distance") or visual.get("framing") or scene.get("framing")
    )
    location = _join_norm(
        visual.get("location") or scene.get("location") or item.get("classification_folder")
    )
    objects = _join_norm(scene.get("objects") or visual.get("objects"))
    subject = _join_norm(visual.get("subject") or objects)
    action = _join_norm(visual.get("action") or scene.get("actions"))
    product_state = _join_norm(visual.get("product_state") or scene.get("product_state"))
    return {
        "framing": framing or camera,
        "camera_distance": camera or framing,
        "location": location,
        "subject": subject,
        "objects": objects or subject,
        "action": action,
        "product_state": product_state,
    }


def _compare_axes(item: dict[str, Any] | None) -> dict[str, str]:
    profile = visual_profile(item)
    return {
        "framing": profile.get("framing") or profile.get("camera_distance") or "",
        "location": profile.get("location") or "",
        "subject": profile.get("subject") or profile.get("objects") or "",
        "action": profile.get("action") or "",
        "product_state": profile.get("product_state") or "",
    }


def _has_shot_geometry(profile: dict[str, str]) -> bool:
    return bool(profile.get("framing") or profile.get("camera_distance"))


def _folder_location(item: dict[str, Any] | None, profile: dict[str, str]) -> str:
    return profile.get("location") or _join_norm((item or {}).get("classification_folder"))


def visual_diff_score(left: dict[str, Any], right: dict[str, Any]) -> int:
    return sum(1 for key in MAJOR_VISUAL_KEYS if left.get(key) != right.get(key))


def adjacent_visual_diff(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> int:
    lp = visual_profile(left)
    rp = visual_profile(right)
    if not _has_shot_geometry(lp) and not _has_shot_geometry(rp):
        left_loc = _folder_location(left, lp)
        right_loc = _folder_location(right, rp)
        if left_loc and left_loc == right_loc:
            return 0
        return 1 if left_loc or right_loc else 0
    axes_l = _compare_axes(left)
    axes_r = _compare_axes(right)
    return sum(1 for key in ADJACENT_COMPARE_AXES if axes_l.get(key) != axes_r.get(key))


def looks_similar(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> bool:
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    lp = visual_profile(left)
    rp = visual_profile(right)
    if not _has_shot_geometry(lp) and not _has_shot_geometry(rp):
        left_loc = _folder_location(left, lp)
        return bool(left_loc) and left_loc == _folder_location(right, rp)
    axes_l = _compare_axes(left)
    axes_r = _compare_axes(right)
    filled_both = [key for key in ADJACENT_COMPARE_AXES if axes_l.get(key) and axes_r.get(key)]
    if not filled_both:
        folder = _join_norm(left.get("classification_folder"))
        return bool(folder) and folder == _join_norm(right.get("classification_folder"))
    matched = sum(1 for key in filled_both if axes_l.get(key) == axes_r.get(key))
    diffs = sum(1 for key in ADJACENT_COMPARE_AXES if (axes_l.get(key) or "") != (axes_r.get(key) or ""))
    if matched == len(filled_both) and diffs <= 1:
        return True
    return diffs == 0


def repeats_shot_axes(
    candidate: dict[str, Any] | None,
    previous: dict[str, Any] | None,
) -> bool:
    if not isinstance(candidate, dict) or not isinstance(previous, dict):
        return False
    lp = visual_profile(candidate)
    rp = visual_profile(previous)
    if not _has_shot_geometry(lp) and not _has_shot_geometry(rp):
        return looks_similar(candidate, previous)
    axes_l = _compare_axes(candidate)
    axes_r = _compare_axes(previous)
    compared = [key for key in CONTINUITY_AXES if axes_l.get(key) and axes_r.get(key)]
    if not compared:
        return looks_similar(candidate, previous)
    return all(axes_l.get(key) == axes_r.get(key) for key in compared)


def continuity_overlap(
    candidate: dict[str, Any] | None,
    previous: dict[str, Any] | None,
) -> int:
    if not isinstance(candidate, dict) or not isinstance(previous, dict):
        return 0
    lp = visual_profile(candidate)
    rp = visual_profile(previous)
    if not _has_shot_geometry(lp) and not _has_shot_geometry(rp):
        return 1 if looks_similar(candidate, previous) else 0
    axes_l = _compare_axes(candidate)
    axes_r = _compare_axes(previous)
    return sum(
        1
        for key in CONTINUITY_AXES
        if axes_l.get(key) and axes_r.get(key) and axes_l.get(key) == axes_r.get(key)
    )


def scenario_score(candidate: dict[str, Any], intended_scenario: str) -> int:
    intended = (intended_scenario or "").strip()
    material_situation = str(candidate.get("situation") or "").strip()
    tags = candidate.get("scenario_tags") or []
    if candidate.get("visual_match") is True or int(candidate.get("visual_match_score") or 0) > 0:
        return 3
    if material_situation and intended and (material_situation == intended or intended in tags):
        return 2
    if candidate.get("semantic_valid") is True:
        return 1
    return 0


def supports_line(candidate: dict[str, Any], line: str) -> bool:
    supported = candidate.get("supported_line")
    if supported is None:
        return True
    return supported == line


def annotate_visual_match(candidate: dict[str, Any], line: str, intended_scenario: str) -> dict[str, Any]:
    clone = dict(candidate)
    if clone.get("from_semantic_fallback") is True:
        clone["visual_match"] = True
        clone["semantic_valid"] = True
        clone["visual_match_score"] = max(int(clone.get("visual_match_score") or 0), 1)
        return clone
    scene = clone.get("catalog_scene") if isinstance(clone.get("catalog_scene"), dict) else clone
    score = int(clone.get("visual_match_score") or 0)
    if clone.get("from_visual_catalog") is True or clone.get("catalog_scene"):
        score = max(score, scene_match_score(scene, line, intended_scenario))
    elif clone.get("from_approved_history") is True:
        score = max(score, scene_match_score(clone, line, intended_scenario))
    clone["visual_match_score"] = score
    clone["visual_match"] = score > 0
    if score > 0:
        clone["semantic_valid"] = True
    return clone


def source_id(item: dict[str, Any] | None) -> str:
    if not isinstance(item, dict):
        return ""
    value = item.get("source") or item.get("material_id") or item.get("path")
    return str(value) if value else ""


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


def is_meaning_matched_scene(candidate: dict[str, Any]) -> bool:
    return (
        candidate.get("from_approved_history") is True
        or candidate.get("from_visual_catalog") is True
        or candidate.get("from_semantic_fallback") is True
        or candidate.get("visual_match") is True
        or int(candidate.get("visual_match_score") or 0) > 0
    )


def contains_source_range(window: tuple[float, float], original: tuple[float, float]) -> bool:
    return window[0] <= original[0] + DURATION_EPS and window[1] + DURATION_EPS >= original[1]


def apply_minimal_range_padding(
    candidate: dict[str, Any],
    target_seconds: float,
    file_durations: dict[str, float] | None = None,
) -> dict[str, Any]:
    clone = dict(candidate)
    rng = source_range(clone)
    if rng is None:
        return clone
    span = rng[1] - rng[0]
    target = float(target_seconds)
    if span + DURATION_EPS >= target:
        return clone
    if not is_meaning_matched_scene(clone):
        return clone
    if target - span > MAX_RANGE_PAD_SECONDS + DURATION_EPS:
        return clone
    file_duration = lookup_file_duration(clone, file_durations)
    if file_duration is None or file_duration + DURATION_EPS < target:
        return clone
    window = fit_window(file_duration, target, rng[0], rng[1])
    if window is None or not contains_source_range(window, rng):
        return clone
    if window[1] - window[0] + DURATION_EPS < target:
        return clone
    clone["original_source_in"] = rng[0]
    clone["original_source_out"] = rng[1]
    clone["source_in"] = window[0]
    clone["source_out"] = window[1]
    clone["in_sec"] = window[0]
    clone["out_sec"] = window[1]
    clone["available_duration"] = window[1] - window[0]
    clone["range_padded"] = True
    return clone


def has_duration_for_target(
    candidate: dict[str, Any],
    target_seconds: float,
    file_durations: dict[str, float] | None = None,
) -> bool:
    padded = apply_minimal_range_padding(candidate, target_seconds, file_durations)
    return duration_passes(padded, target_seconds, file_durations)


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
    found: list[dict[str, Any]] = []
    for item in candidates:
        padded = apply_minimal_range_padding(item, target_seconds, file_durations)
        if duration_passes(padded, target_seconds, file_durations):
            found.append(padded)
    return found


def range_key(item: dict[str, Any] | None) -> tuple[str, float, float] | None:
    sid = source_id(item)
    rng = source_range(item) if isinstance(item, dict) else None
    if not sid or rng is None:
        return None
    return (sid, round(rng[0], 3), round(rng[1], 3))


class SelectionUsage:
    def __init__(self) -> None:
        self.source_counts: dict[str, int] = {}
        self.used_ranges: set[tuple[str, float, float]] = set()
        self.windows: dict[str, list[tuple[float, float]]] = {}
        self.pair_orders: list[tuple[tuple[str, float, float], ...]] = []

    def note(self, item: dict[str, Any]) -> None:
        segments = item.get("video_segments") if isinstance(item.get("video_segments"), list) else []
        usable = [seg for seg in segments if isinstance(seg, dict)]
        if len(usable) >= MAX_SEGMENTS_PER_CUT:
            keys: list[tuple[str, float, float]] = []
            for seg in usable:
                self.note(
                    {
                        "source": seg.get("source") or source_id(item),
                        "source_in": seg.get("scene_in", seg.get("source_in")),
                        "source_out": seg.get("scene_out", seg.get("source_out")),
                    }
                )
                key = range_key(
                    {
                        "source": seg.get("source") or source_id(item),
                        "source_in": seg.get("scene_in", seg.get("source_in")),
                        "source_out": seg.get("scene_out", seg.get("source_out")),
                    }
                )
                if key is not None:
                    keys.append(key)
            if keys:
                self.pair_orders.append(tuple(keys))
            return
        sid = source_id(item)
        rng = source_range(item)
        if sid:
            self.source_counts[sid] = self.source_counts.get(sid, 0) + 1
        if sid and rng is not None:
            self.used_ranges.add((sid, round(rng[0], 3), round(rng[1], 3)))
            self.windows.setdefault(sid, []).append(rng)

    def source_used(self, source: str) -> int:
        return self.source_counts.get(source, 0)

    def range_used(self, item: dict[str, Any]) -> bool:
        key = range_key(item)
        return key in self.used_ranges if key is not None else False

    def pair_order_used(self, keys: tuple[tuple[str, float, float], ...]) -> bool:
        return keys in self.pair_orders


def is_selectable(candidate: dict[str, Any], line: str) -> bool:
    if not supports_line(candidate, line):
        return False
    return (
        candidate.get("from_approved_history") is True
        or candidate.get("visual_match") is True
        or int(candidate.get("visual_match_score") or 0) > 0
        or candidate.get("semantic_valid") is True
        or candidate.get("search_aid") is True
    )


def history_rank(candidate: dict[str, Any], line: str, intended_scenario: str) -> int:
    if candidate.get("from_approved_history") is not True:
        return 0
    return 1 if history_close_enough(candidate, line, intended_scenario) else 0


def semantic_tier(candidate: dict[str, Any], line: str, intended_scenario: str) -> int:
    if history_rank(candidate, line, intended_scenario) > 0:
        return 4
    if candidate.get("from_semantic_fallback") is True:
        return 2
    meaning = (
        candidate.get("visual_match") is True
        or int(candidate.get("visual_match_score") or 0) > 0
        or candidate.get("semantic_valid") is True
    )
    if not meaning:
        if candidate.get("search_aid") is True:
            return 0
        return -1
    if candidate.get("from_visual_catalog") is True:
        return 3
    return 1


def appropriate_match(candidate: dict[str, Any], line: str, intended_scenario: str) -> bool:
    return (
        history_rank(candidate, line, intended_scenario) > 0
        or candidate.get("visual_match") is True
        or int(candidate.get("visual_match_score") or 0) > 0
        or candidate.get("semantic_valid") is True
    )


def _coverage_hits(text: str) -> list[str]:
    hay = str(text or "")
    return [name for name, pattern in COVERAGE_PATTERNS if pattern.search(hay)]


def folder_only_catalog_scene(item: dict[str, Any] | None) -> bool:
    if not isinstance(item, dict):
        return False
    folder = _join_norm(item.get("classification_folder"))
    if not folder:
        return False
    scene = item.get("catalog_scene") if isinstance(item.get("catalog_scene"), dict) else {}
    visual = item.get("visual") if isinstance(item.get("visual"), dict) else {}
    framing = _join_norm(visual.get("framing") or scene.get("framing") or visual.get("camera_distance"))
    if framing:
        return False
    location = _join_norm(visual.get("location") or scene.get("location"))
    return bool(location) and location == folder


def stitch_meaning_match(candidate: dict[str, Any], line: str, intended_scenario: str) -> bool:
    if history_rank(candidate, line, intended_scenario) > 0:
        return True
    if candidate.get("from_semantic_fallback") is True:
        return True
    if candidate.get("visual_match") is True or int(candidate.get("visual_match_score") or 0) > 0:
        return True
    if folder_only_catalog_scene(candidate):
        return False
    scene = candidate.get("catalog_scene") if isinstance(candidate.get("catalog_scene"), dict) else candidate
    request_hits = _coverage_hits(f"{line or ''}\n{intended_scenario or ''}")
    scene_hits = _coverage_hits(scene_text(scene) if isinstance(scene, dict) else "")
    return bool(request_hits) and bool(scene_hits)


def original_span(candidate: dict[str, Any] | None) -> float | None:
    rng = source_range(candidate) if isinstance(candidate, dict) else None
    if rng is None:
        return None
    span = rng[1] - rng[0]
    return span if span > DURATION_EPS else None


def ranges_overlap(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    if source_id(left) != source_id(right) or not source_id(left):
        return False
    first = source_range(left) if isinstance(left, dict) else None
    second = source_range(right) if isinstance(right, dict) else None
    if first is None or second is None:
        return False
    return first[0] < second[1] - DURATION_EPS and second[0] < first[1] - DURATION_EPS


def can_pair_scenes(
    left: dict[str, Any],
    right: dict[str, Any],
    target_seconds: float,
) -> bool:
    if range_key(left) is None or range_key(left) == range_key(right):
        return False
    if ranges_overlap(left, right):
        return False
    first = original_span(left)
    second = original_span(right)
    if first is None or second is None:
        return False
    return first + second + DURATION_EPS >= float(target_seconds)


def dedupe_scene_ranges(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[tuple[str, float, float], dict[str, Any]] = {}
    for item in items:
        key = range_key(item)
        if key is None:
            continue
        current = best.get(key)
        if current is None or int(item.get("visual_match_score") or 0) > int(current.get("visual_match_score") or 0):
            best[key] = item
    return list(best.values())


def stitch_two_scenes(
    first: dict[str, Any],
    second: dict[str, Any],
    target_seconds: float,
) -> dict[str, Any] | None:
    start_end = source_range(first)
    other = source_range(second)
    if start_end is None or other is None:
        return None
    first_span = start_end[1] - start_end[0]
    remain = float(target_seconds) - first_span
    if remain <= DURATION_EPS or other[1] - other[0] + DURATION_EPS < remain:
        return None
    second_out = other[0] + remain
    chosen = dict(second)
    chosen.update(
        {
            "source": source_id(first) or first.get("source"),
            "material_id": first.get("material_id") or source_id(first),
            "source_in": start_end[0],
            "source_out": start_end[1],
            "in_sec": start_end[0],
            "out_sec": start_end[1],
            "available_duration": float(target_seconds),
            "target_duration_seconds": float(target_seconds),
            "multi_segment": True,
            "video_segments": [
                {
                    "source": source_id(first),
                    "source_in": start_end[0],
                    "source_out": start_end[1],
                    "duration": first_span,
                    "scene_in": start_end[0],
                    "scene_out": start_end[1],
                },
                {
                    "source": source_id(second),
                    "source_in": other[0],
                    "source_out": second_out,
                    "duration": remain,
                    "scene_in": other[0],
                    "scene_out": other[1],
                },
            ],
        }
    )
    return chosen


def select_meaning_pair(
    candidates: list[dict[str, Any]],
    *,
    line: str,
    intended_scenario: str,
    duration_seconds: float,
    previous: dict[str, Any] | None = None,
    previous_2: dict[str, Any] | None = None,
    usage: SelectionUsage | None = None,
) -> dict[str, Any] | None:
    scenes = dedupe_scene_ranges(
        [
            item
            for item in candidates
            if stitch_meaning_match(item, line, intended_scenario) and original_span(item) is not None
        ]
    )
    if usage is not None:
        unused = [item for item in scenes if not usage.range_used(item)]
        if len(unused) >= MAX_SEGMENTS_PER_CUT:
            scenes = unused
    if len(scenes) < 2:
        return None
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for left in scenes:
        for right in scenes:
            if not can_pair_scenes(left, right, duration_seconds):
                continue
            keys = (range_key(left), range_key(right))
            if None in keys:
                continue
            if usage is not None and usage.pair_order_used(keys):
                continue
            pairs.append((left, right))
    if not pairs:
        return None
    first_options = []
    seen: set[tuple[str, float, float]] = set()
    for left, _right in pairs:
        key = range_key(left)
        if key is None or key in seen:
            continue
        seen.add(key)
        first_options.append(left)
    first = pick_from_pool(
        first_options,
        previous,
        line=line,
        intended_scenario=intended_scenario,
        usage=usage,
        previous_2=previous_2,
    )
    seconds = [right for left, right in pairs if range_key(left) == range_key(first)]
    if not seconds:
        return None
    prev_sources: set[str] = set()
    if isinstance(previous, dict):
        for seg in previous.get("video_segments") or []:
            if isinstance(seg, dict) and source_id(seg):
                prev_sources.add(source_id(seg))
        if not prev_sources and source_id(previous):
            prev_sources.add(source_id(previous))
    unused_prev = [item for item in seconds if source_id(item) not in prev_sources]
    if unused_prev:
        seconds = unused_prev
    second = pick_from_pool(
        seconds,
        first,
        line=line,
        intended_scenario=intended_scenario,
        usage=usage,
        previous_2=previous,
    )
    return stitch_two_scenes(first, second, duration_seconds)


def unused_alternate_range(
    candidate: dict[str, Any],
    usage: SelectionUsage | None,
) -> tuple[float, float] | None:
    sid = source_id(candidate)
    if not sid or usage is None:
        return None
    current = source_range(candidate)
    alternates = list(candidate.get("alternate_ranges") or [])
    if current is not None:
        alternates = [current, *alternates]
    seen: set[tuple[float, float]] = set()
    for item in alternates:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            continue
        start = float(item[0])
        end = float(item[1])
        key = (sid, round(start, 3), round(end, 3))
        if key in seen or key in usage.used_ranges:
            continue
        seen.add(key)
        if end > start:
            return (start, end)
    return None


def next_full_clip_window(
    file_duration: float,
    target_seconds: float,
    used_windows: list[tuple[float, float]],
) -> tuple[float, float] | None:
    target = float(target_seconds)
    if file_duration + DURATION_EPS < target:
        return None
    occupied = sorted(used_windows)
    start = 0.0
    for window in occupied:
        if start + target <= window[0] + DURATION_EPS:
            return (start, start + target)
        start = max(start, window[1])
    if start + target <= file_duration + DURATION_EPS:
        return (start, start + target)
    return None


def rank_key(
    candidate: dict[str, Any],
    *,
    line: str,
    intended_scenario: str,
    previous: dict[str, Any] | None,
    usage: SelectionUsage | None,
    previous_2: dict[str, Any] | None = None,
) -> tuple[int, ...]:
    tier = semantic_tier(candidate, line, intended_scenario)
    history = history_rank(candidate, line, intended_scenario)
    visual = int(candidate.get("visual_match_score") or 0)
    facts = 1 if candidate.get("semantic_valid") is True else 0
    aid = 1 if candidate.get("search_aid") is True else 0
    used_range = 1 if usage is not None and usage.range_used(candidate) else 0
    used_source = usage.source_used(source_id(candidate)) if usage is not None else 0
    overlap1 = continuity_overlap(candidate, previous) if previous is not None else 0
    similar1 = 1 if previous is not None and looks_similar(candidate, previous) else 0
    diff1 = adjacent_visual_diff(candidate, previous) if previous is not None else 0
    overlap2 = continuity_overlap(candidate, previous_2) if previous_2 is not None else 0
    similar2 = 1 if previous_2 is not None and looks_similar(candidate, previous_2) else 0
    diff2 = adjacent_visual_diff(candidate, previous_2) if previous_2 is not None else 0
    return (
        tier,
        -overlap1,
        -similar1,
        -overlap2,
        -similar2,
        diff1,
        diff2,
        history,
        visual,
        -used_range,
        -used_source,
        facts,
        aid,
    )


def pick_from_pool(
    pool: list[dict[str, Any]],
    previous: dict[str, Any] | None,
    *,
    line: str = "",
    intended_scenario: str = "",
    usage: SelectionUsage | None = None,
    previous_2: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ranked = sorted(
        pool,
        key=lambda item: rank_key(
            item,
            line=line,
            intended_scenario=intended_scenario,
            previous=previous,
            previous_2=previous_2,
            usage=usage,
        ),
        reverse=True,
    )
    return ranked[0]


def stamp_selection(
    chosen: dict[str, Any],
    target_seconds: float,
    file_durations: dict[str, float] | None = None,
    usage: SelectionUsage | None = None,
) -> dict[str, Any]:
    stamped = dict(chosen)
    rng = source_range(stamped)
    file_duration = lookup_file_duration(stamped, file_durations)
    sid = source_id(stamped)
    if usage is not None and rng is not None and usage.range_used(stamped):
        unused = unused_alternate_range(stamped, usage)
        if unused is not None:
            rng = unused
            stamped["full_clip"] = False
    if rng is None and usage is not None:
        unused = unused_alternate_range(stamped, usage)
        if unused is not None:
            rng = unused
    if rng is None and file_duration is not None:
        used_windows = usage.windows.get(sid, []) if usage is not None else []
        if used_windows:
            window = next_full_clip_window(file_duration, target_seconds, used_windows)
        else:
            window = fit_window(file_duration, target_seconds)
        if window is not None:
            rng = window
            stamped["full_clip"] = True
    if rng is not None:
        if file_duration is not None:
            fitted = fit_window(file_duration, target_seconds, rng[0], rng[1])
            if fitted is not None:
                rng = fitted
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


def _filter_reuse(
    pool: list[dict[str, Any]],
    *,
    line: str,
    intended_scenario: str,
    usage: SelectionUsage | None,
) -> list[dict[str, Any]]:
    if usage is None or not pool:
        return pool
    unused_range = [item for item in pool if not usage.range_used(item)]
    if unused_range:
        pool = unused_range
    return pool


def select_cut(
    candidates: list[dict[str, Any]],
    *,
    line: str,
    intended_scenario: str,
    duration_seconds: float,
    previous: dict[str, Any] | None = None,
    previous_2: dict[str, Any] | None = None,
    history: dict[str, Any] | None = None,
    file_durations: dict[str, float] | None = None,
    usage: SelectionUsage | None = None,
) -> dict[str, Any]:
    combined = prefer_history_candidates(
        candidates,
        line=line,
        intended_scenario=intended_scenario,
        duration_seconds=duration_seconds,
        history=history,
    )
    annotated = [annotate_visual_match(item, line, intended_scenario) for item in combined]
    valid = [item for item in annotated if is_selectable(item, line)]
    if not valid:
        return hold("HOLD_MEDIA_NOT_MATCHED", "no semantically valid material for this line")
    meaning = [item for item in annotated if stitch_meaning_match(item, line, intended_scenario)]
    eligible_meaning = duration_eligible(meaning, duration_seconds, file_durations)
    if eligible_meaning:
        pool = _filter_reuse(eligible_meaning, line=line, intended_scenario=intended_scenario, usage=usage)
        chosen = stamp_selection(
            dict(
                pick_from_pool(
                    pool,
                    previous,
                    line=line,
                    intended_scenario=intended_scenario,
                    usage=usage,
                    previous_2=previous_2,
                )
            ),
            duration_seconds,
            file_durations,
            usage,
        )
    else:
        paired = select_meaning_pair(
            meaning,
            line=line,
            intended_scenario=intended_scenario,
            duration_seconds=duration_seconds,
            previous=previous,
            previous_2=previous_2,
            usage=usage,
        )
        if paired is not None:
            chosen = paired
        else:
            eligible = duration_eligible(valid, duration_seconds, file_durations)
            if not eligible:
                return hold(
                    "HOLD_MEDIA_NOT_MATCHED",
                    "no material with available_duration >= target_duration_seconds",
                )
            pool = _filter_reuse(eligible, line=line, intended_scenario=intended_scenario, usage=usage)
            chosen = stamp_selection(
                dict(
                    pick_from_pool(
                        pool,
                        previous,
                        line=line,
                        intended_scenario=intended_scenario,
                        usage=usage,
                        previous_2=previous_2,
                    )
                ),
                duration_seconds,
                file_durations,
                usage,
            )
    chosen["line"] = line
    chosen["intended_scenario"] = intended_scenario
    return {"status": "OK", "selection": chosen}


def assemble_plan(
    approved_script: dict[str, Any],
    narration_manifest: dict[str, Any],
    candidates_by_cut: dict[str, list[dict[str, Any]]],
    history: dict[str, Any] | None = None,
    file_durations: dict[str, float] | None = None,
    *,
    semantic_match_fn: Any = None,
    project_root: Path | None = None,
    case_id: str | None = None,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    clips = {clip["cut_id"]: clip for clip in narration_manifest.get("clips") or []}
    prepared: dict[str, list[dict[str, Any]]] = {}
    durations: dict[str, float] = {}
    unresolved: list[dict[str, Any]] = []
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
        duration = float(target["target_duration_seconds"])
        durations[cut["cut_id"]] = duration
        combined = prefer_history_candidates(
            list(candidates_by_cut.get(cut["cut_id"]) or []),
            line=cut["line"],
            intended_scenario=cut["situation"],
            duration_seconds=duration,
            history=history,
        )
        annotated = [annotate_visual_match(item, cut["line"], cut["situation"]) for item in combined]
        prepared[cut["cut_id"]] = annotated
        if not any(
            is_selectable(item, cut["line"]) and has_duration_for_target(item, duration, file_durations)
            for item in annotated
        ):
            unresolved.append(
                {
                    "cut_id": cut["cut_id"],
                    "line": cut["line"],
                    "situation": cut["situation"],
                    "target_duration_seconds": duration,
                }
            )

    stored_matches: dict[str, dict[str, Any]] = {}
    if project_root is not None and case_id:
        stored_matches = load_matches(project_root, case_id)
    if unresolved and stored_matches:
        apply_semantic_matches(
            prepared,
            stored_matches,
            scenes=merge_scene_payloads(
                collect_scene_payloads(prepared, [item["cut_id"] for item in unresolved]),
                catalog_history_payloads(catalog, history),
            ),
            targets=durations,
        )
        unresolved = [
            item
            for item in unresolved
            if not any(
                is_selectable(candidate, item["line"])
                and has_duration_for_target(candidate, durations[item["cut_id"]], file_durations)
                for candidate in prepared.get(item["cut_id"]) or []
            )
        ]

    if unresolved and (semantic_match_fn is not None or project_root is not None):
        scenes = merge_scene_payloads(
            collect_scene_payloads(prepared, [item["cut_id"] for item in unresolved]),
            catalog_history_payloads(catalog, history),
        )
        fallback = run_semantic_fallback(
            unresolved,
            scenes,
            send_fn=semantic_match_fn,
            project_root=project_root,
        )
        if fallback.get("status") == "HOLD":
            return fallback
        matches = fallback.get("matches") if isinstance(fallback.get("matches"), dict) else {}
        apply_semantic_matches(prepared, matches, scenes=scenes, targets=durations)
        if project_root is not None and case_id and int(fallback.get("gemini_calls") or 0) > 0:
            saved = dict(stored_matches)
            saved.update(matches)
            persist_matches(project_root, case_id, saved, gemini_calls=int(fallback.get("gemini_calls") or 0))

    cuts: list[dict[str, Any]] = []
    previous = None
    previous_2 = None
    usage = SelectionUsage()
    for cut in approved_script.get("cuts") or []:
        duration = durations[cut["cut_id"]]
        selected = select_cut(
            prepared.get(cut["cut_id"]) or [],
            line=cut["line"],
            intended_scenario=cut["situation"],
            duration_seconds=duration,
            previous=previous,
            previous_2=previous_2,
            history=history,
            file_durations=file_durations,
            usage=usage,
        )
        if selected.get("status") != "OK":
            return selected
        item = selected["selection"]
        item["cut_id"] = cut["cut_id"]
        item["material_situation"] = item.get("situation")
        item["situation"] = cut["situation"]
        cuts.append(item)
        usage.note(item)
        previous_2 = previous
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
