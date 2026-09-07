#!/usr/bin/env python3
"""Craft-quality gates that run before the three routine checkpoints."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lessons import (
    CTA_TEXT,
    HOLD_CRAFT,
    NARRATIVE_ROLES,
    SURFACES,
    dump,
    hold_payload,
    load_active_lessons,
    load_json,
    normalize_text,
    spoken_text,
)


HEAT_HOOK_RE = re.compile(r"暑|熱すぎ|熱い")
RESULT_LOOKS_RE = re.compile(
    r"銀色|黒色|黒い内側|外からは|見た目|日差しが入ってこない|日差しが入らない|光が入らない|光が入ってこない"
)
HEAT_SOLUTION_RE = re.compile(r"暑さ|熱さ|焼かれ|しのげ|防げ|止められ|凌げ")
EXPLAIN_LINE_RE = re.compile(r"(します|してみて|あるよ|できます)[。]?$")
GAP_MIN_MS = 400
GAP_MAX_MS = 1200


def dialogue_records(artifact: Any) -> list[dict[str, Any]]:
    if not isinstance(artifact, dict):
        return []
    for key in ("dialogue", "script"):
        rows = artifact.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def role_text(records: list[dict[str, Any]], role: str) -> str:
    for record in records:
        if record.get("narrative_role") == role:
            return spoken_text(record)
    return ""


def contains_any(text: str, needles: list[Any]) -> bool:
    return any(isinstance(item, str) and item and item in text for item in needles)


def apply_text_pair_gate(
    hook: str, resolution: str, gate: dict[str, Any], defect: str
) -> dict[str, Any] | None:
    when = gate.get("when_hook_contains") or []
    if when and not contains_any(hook, when):
        return None
    fail_tokens = gate.get("fail_if_resolution_contains") or []
    pass_tokens = gate.get("pass_if_resolution_contains_any") or []
    looks_only = contains_any(resolution, fail_tokens)
    has_solution = contains_any(resolution, pass_tokens) if pass_tokens else True
    if looks_only and not has_solution:
        return hold_payload(
            "problem_resolution restates a result look instead of solving the hook problem",
            surface="script",
            defect=defect,
        )
    if pass_tokens and not has_solution:
        return hold_payload(
            "problem_resolution does not present a spoken solution to the hook problem",
            surface="script",
            defect=defect,
        )
    return None


def apply_forbidden_line_tokens(
    records: list[dict[str, Any]], gate: dict[str, Any], defect: str
) -> dict[str, Any] | None:
    tokens = gate.get("fail_if_any_line_contains") or []
    role = gate.get("role")
    for record in records:
        if role and record.get("narrative_role") != role:
            continue
        text = spoken_text(record)
        if contains_any(text, tokens):
            return hold_payload(
                f"{record.get('narrative_role') or 'line'} uses a rejected spoken token",
                surface="script",
                defect=defect,
            )
    return None


def dialogue_unchanged(artifact: dict[str, Any], records: list[dict[str, Any]]) -> bool:
    previous = artifact.get("previous_dialogue")
    if not isinstance(previous, list) or not previous:
        return False
    old = [
        normalize_text(spoken_text(row) if isinstance(row, dict) else str(row))
        for row in previous
    ]
    new = [normalize_text(spoken_text(row)) for row in records]
    return old == new and any(old)


def apply_lesson_script_gates(
    records: list[dict[str, Any]], hook: str, resolution: str, lessons: list[dict[str, Any]]
) -> dict[str, Any] | None:
    for lesson in lessons:
        defect = str(lesson.get("defect") or "hook_closed_by_result_looks")
        bad = lesson.get("bad") if isinstance(lesson.get("bad"), dict) else {}
        if (
            normalize_text(str(bad.get("hook") or ""))
            and normalize_text(hook) == normalize_text(str(bad.get("hook")))
            and normalize_text(resolution) == normalize_text(str(bad.get("resolution") or ""))
        ):
            return hold_payload(
                f"matches rejected lesson {lesson.get('id')}",
                surface="script",
                defect=defect,
            )
        bad_lines = bad.get("dialogue")
        if isinstance(bad_lines, list) and bad_lines:
            rejected = [
                normalize_text(spoken_text(row) if isinstance(row, dict) else str(row))
                for row in bad_lines
            ]
            current = [normalize_text(spoken_text(row)) for row in records]
            if rejected == current:
                return hold_payload(
                    f"matches rejected lesson {lesson.get('id')}",
                    surface="script",
                    defect=defect,
                )
        gate = lesson.get("gate") if isinstance(lesson.get("gate"), dict) else {}
        kind = gate.get("kind")
        if kind == "text_pair":
            held = apply_text_pair_gate(hook, resolution, gate, defect)
            if held:
                return held
        elif kind in {"forbidden_tokens", "forbidden_role_tokens"}:
            held = apply_forbidden_line_tokens(records, gate, defect)
            if held:
                return held
    return None


def gate_script(artifact: Any, lessons: list[dict[str, Any]]) -> dict[str, Any]:
    records = dialogue_records(artifact)
    if not records and isinstance(artifact, dict) and artifact.get("hook") and artifact.get("resolution"):
        records = [
            {"narrative_role": "problem_or_hook", "text": artifact["hook"]},
            {"narrative_role": "product", "text": "商品です。"},
            {"narrative_role": "use_or_change", "text": "使います。"},
            {"narrative_role": "result", "text": artifact.get("result") or "変化が見える。"},
            {"narrative_role": "problem_resolution", "text": artifact["resolution"]},
            {"narrative_role": "cta", "text": CTA_TEXT},
        ]
    roles = [record.get("narrative_role") for record in records]
    compressed = [role for index, role in enumerate(roles) if index == 0 or role != roles[index - 1]]
    if compressed != list(NARRATIVE_ROLES):
        return hold_payload(
            "spoken script must complete problem_or_hook, product, use_or_change, result, problem_resolution, cta in order",
            surface="script",
            defect="six_stage_incomplete",
        )
    hook = role_text(records, "problem_or_hook")
    result = role_text(records, "result")
    resolution = role_text(records, "problem_resolution")
    cta = role_text(records, "cta")
    if cta != CTA_TEXT:
        return hold_payload("CTA must be exactly 下からチェック！", surface="script", defect="cta_mismatch")
    if not hook.strip() or not resolution.strip():
        return hold_payload("hook and problem_resolution are required", surface="script", defect="hook_resolution_missing")
    if normalize_text(result) and normalize_text(result) == normalize_text(resolution):
        return hold_payload(
            "problem_resolution restates result; it must present a solution to the hook problem",
            surface="script",
            defect="hook_closed_by_result_looks",
        )
    if HEAT_HOOK_RE.search(hook):
        looks_or_sun = RESULT_LOOKS_RE.search(resolution)
        solved = HEAT_SOLUTION_RE.search(resolution)
        if looks_or_sun and not solved:
            return hold_payload(
                "a heat hook is not closed by looks or blocked sunlight alone",
                surface="script",
                defect="hook_closed_by_result_looks",
            )
        if not solved:
            return hold_payload(
                "a heat hook needs a spoken heat solution within verified facts",
                surface="script",
                defect="hook_closed_by_result_looks",
            )
    if dialogue_unchanged(artifact if isinstance(artifact, dict) else {}, records):
        return hold_payload(
            "a rejected script revision must change the spoken lines before Checkpoint 1",
            surface="script",
            defect="revision_unchanged",
        )
    for record in records:
        if record.get("narrative_role") == "cta":
            continue
        text = spoken_text(record).strip()
        if EXPLAIN_LINE_RE.search(text):
            return hold_payload(
                "spoken lines must be short TikTok copy, not instruction-sheet narration",
                surface="script",
                defect="explanatory_register",
            )
    held = apply_lesson_script_gates(records, hook, resolution, lessons)
    if held:
        return held
    return {"status": "PASS", "surface": "script"}


def cuts_from(artifact: Any) -> list[dict[str, Any]]:
    if isinstance(artifact, dict) and isinstance(artifact.get("cuts"), list):
        return [cut for cut in artifact["cuts"] if isinstance(cut, dict)]
    return []


def apply_picture_lessons(cuts: list[dict[str, Any]], lessons: list[dict[str, Any]]) -> dict[str, Any] | None:
    for lesson in lessons:
        defect = str(lesson.get("defect") or "picture_lesson")
        gate = lesson.get("gate") if isinstance(lesson.get("gate"), dict) else {}
        kind = gate.get("kind")
        if kind == "artifact_flag":
            flags = gate.get("fail_if_true") or []
            for flag in flags:
                if any(cut.get(flag) is True for cut in cuts):
                    return hold_payload(
                        f"active picture lesson {lesson.get('id')} failed",
                        surface="picture",
                        defect=defect,
                    )
        elif kind == "cut_claimed_action_must_contain":
            role = gate.get("when_narrative_role")
            needles = [item for item in (gate.get("must_contain") or []) if isinstance(item, str) and item]
            matched = False
            for cut in cuts:
                if role and cut.get("narrative_role") != role:
                    continue
                matched = True
                action = str(cut.get("claimed_action") or "")
                if needles and not any(needle in action for needle in needles):
                    return hold_payload(
                        f"{cut.get('cut_id') or 'cut'}: claimed action must show {needles[0]}",
                        surface="picture",
                        defect=defect,
                    )
            if role and not matched:
                return hold_payload(
                    f"picture selection needs a {role} cut whose claimed action shows the required motion",
                    surface="picture",
                    defect=defect,
                )
    return None


def gate_picture(artifact: Any, lessons: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(artifact, dict) or artifact.get("schema") not in {
        "product_video_picture_selection.v1",
        None,
    }:
        if not isinstance(artifact, dict):
            return hold_payload("picture artifact must be an object", surface="picture", defect="picture_artifact_missing")
    cuts = cuts_from(artifact)
    if not cuts:
        return hold_payload("picture selection must list cuts", surface="picture", defect="picture_selection_missing")
    for index, cut in enumerate(cuts):
        cut_id = cut.get("cut_id") or "cut"
        if not str(cut.get("claimed_action") or "").strip():
            return hold_payload(
                f"{cut_id}: claimed visible action is required",
                surface="picture",
                defect="claimed_action_missing",
            )
        if cut.get("defaulted_to_first_n_seconds") is True:
            return hold_payload(
                f"{cut_id}: do not default to the first N seconds of a usable take",
                surface="picture",
                defect="defaulted_first_n_seconds",
            )
        if cut.get("action_centered") is not True:
            return hold_payload(
                f"{cut_id}: chosen in/mid/out must show the claimed action as the point of the range",
                surface="picture",
                defect="claimed_action_not_centered",
            )
        if cut.get("range_covers_claimed_action") is not True:
            return hold_payload(
                f"{cut_id}: chosen range must cover the claimed action, not leftover head/tail",
                surface="picture",
                defect="claimed_action_not_centered",
            )
        if cut.get("adjacent_similar_look") is True or cut.get("adjacent_same_look") is True:
            return hold_payload(
                f"{cut_id}: consecutive cuts must not continue the same place, distance, and camera angle",
                surface="picture",
                defect="adjacent_similar_look",
            )
        if index > 0 and cut.get("look_reads_different_from_previous") is not True and cut.get(
            "look_distinct_from_previous"
        ) is not True:
            return hold_payload(
                f"{cut_id}: neighboring cuts must not continue the same place, distance, and camera angle; related sequential actions are allowed",
                surface="picture",
                defect="adjacent_similar_look",
            )
        chosen = cut.get("chosen") if isinstance(cut.get("chosen"), dict) else {}
        source_in = chosen.get("source_in")
        candidates = cut.get("candidates") if isinstance(cut.get("candidates"), list) else []
        if source_in in (0, 0.0) and len(candidates) < 1:
            return hold_payload(
                f"{cut_id}: starting at 0s requires compared candidates, not an uncompared first-N default",
                surface="picture",
                defect="defaulted_first_n_seconds",
            )
        usable = [item for item in candidates if isinstance(item, dict)]
        if len(usable) >= 2 and not any(item.get("rejected_reason") for item in usable):
            return hold_payload(
                f"{cut_id}: compared candidates must record why the losers were dropped",
                surface="picture",
                defect="no_rejected_candidate_reason",
            )
    held = apply_picture_lessons(cuts, lessons)
    if held:
        return held
    return {"status": "PASS", "surface": "picture"}


def gate_captions(artifact: Any, lessons: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        return hold_payload("caption artifact must be an object", surface="captions", defect="caption_artifact_missing")
    cuts = cuts_from(artifact)
    if not cuts:
        return hold_payload("caption craft must list cuts", surface="captions", defect="caption_craft_missing")
    for cut in cuts:
        cut_id = cut.get("cut_id") or "cut"
        if cut.get("json_geometry_only") is True or cut.get("composed_frame_proof") is not True:
            return hold_payload(
                f"{cut_id}: composed frames are required; JSON geometry is not visual proof",
                surface="captions",
                defect="json_geometry_only",
            )
        if cut.get("centered_on_screen") is not True:
            return hold_payload(f"{cut_id}: captions must be centered on screen", surface="captions", defect="caption_not_centered")
        if cut.get("prominent") is not True:
            return hold_payload(
                f"{cut_id}: captions need heavy weight, thick stroke, and a contrast band",
                surface="captions",
                defect="caption_not_prominent",
            )
        if cut.get("wrap_changed_characters") is True:
            return hold_payload(
                f"{cut_id}: visual wrap must not change frozen characters",
                surface="captions",
                defect="wrap_changed_characters",
            )
        visible = cut.get("visible_layer_count")
        if visible is not None and visible != 1:
            return hold_payload(
                f"{cut_id}: exactly one visible caption layer is required",
                surface="captions",
                defect="duplicate_caption_layers",
            )
        duplicates = cut.get("duplicate_layers")
        if isinstance(duplicates, int) and duplicates > 0:
            return hold_payload(
                f"{cut_id}: exactly one visible caption layer is required",
                surface="captions",
                defect="duplicate_caption_layers",
            )
    for lesson in lessons:
        gate = lesson.get("gate") if isinstance(lesson.get("gate"), dict) else {}
        flags = gate.get("fail_if_true") if gate.get("kind") == "artifact_flag" else []
        for flag in flags or []:
            if any(cut.get(flag) is True for cut in cuts):
                return hold_payload(
                    f"active caption lesson {lesson.get('id')} failed",
                    surface="captions",
                    defect=str(lesson.get("defect") or flag),
                )
    return {"status": "PASS", "surface": "captions"}


def gate_tts(artifact: Any, lessons: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        return hold_payload("tts artifact must be an object", surface="tts-timing", defect="tts_artifact_missing")
    if artifact.get("combined_clip_left_on_timeline") is True or artifact.get("bulk_tts_used") is True:
        return hold_payload(
            "do not leave one combined bulk narration clip on the timeline",
            surface="tts-timing",
            defect="combined_tts_clip",
        )
    if artifact.get("per_cut_generation") is not True:
        return hold_payload(
            "generate one Holiday Twist render per narration-target cut",
            surface="tts-timing",
            defect="combined_tts_clip",
        )
    cuts = cuts_from(artifact)
    if not cuts:
        return hold_payload("tts craft must list cuts", surface="tts-timing", defect="tts_craft_missing")
    for cut in cuts:
        cut_id = cut.get("cut_id") or "cut"
        if cut.get("cut_mid_speech") is True:
            return hold_payload(f"{cut_id}: do not cut inside speech", surface="tts-timing", defect="cut_mid_speech")
        if cut.get("speech_matches_frozen_line") is False:
            return hold_payload(
                f"{cut_id}: narration cut points must follow the frozen line",
                surface="tts-timing",
                defect="cut_mid_speech",
            )
        if cut.get("too_fast_to_hear") is True or cut.get("speech_shorter_than_claimed_action") is True:
            return hold_payload(
                f"{cut_id}: trim picture to speech while keeping the claimed action; do not speed past it",
                surface="tts-timing",
                defect="too_fast_to_hear",
            )
        if cut.get("picture_trimmed_to_speech") is not True and cut.get("is_final") is not True:
            return hold_payload(
                f"{cut_id}: non-final picture must be trimmed to that cut's audible speech",
                surface="tts-timing",
                defect="three_layer_open",
            )
        if cut.get("three_layer_closed") is not True and cut.get("is_final") is not True:
            return hold_payload(
                f"{cut_id}: source, caption, and TTS must close together",
                surface="tts-timing",
                defect="three_layer_open",
            )
        if "gap_ms" in cut:
            gap = cut.get("gap_ms")
            if not isinstance(gap, int) or isinstance(gap, bool) or gap < GAP_MIN_MS or gap > GAP_MAX_MS:
                return hold_payload(
                    f"{cut_id}: scene-split gap must be {GAP_MIN_MS}-{GAP_MAX_MS} ms",
                    surface="tts-timing",
                    defect="scene_gap_out_of_range",
                )
    for lesson in lessons:
        gate = lesson.get("gate") if isinstance(lesson.get("gate"), dict) else {}
        flags = gate.get("fail_if_true") if gate.get("kind") == "artifact_flag" else []
        for flag in flags or []:
            if artifact.get(flag) is True or any(cut.get(flag) is True for cut in cuts):
                return hold_payload(
                    f"active tts lesson {lesson.get('id')} failed",
                    surface="tts-timing",
                    defect=str(lesson.get("defect") or flag),
                )
    return {"status": "PASS", "surface": "tts-timing"}


GATES = {
    "script": gate_script,
    "picture": gate_picture,
    "captions": gate_captions,
    "tts-timing": gate_tts,
}


def validate(surface: str, artifact: Any, lessons: list[dict[str, Any]]) -> dict[str, Any]:
    return GATES[surface](artifact, lessons)


def ans182_bad_script() -> dict[str, Any]:
    return {
        "schema": "product_video_craft_script.v1",
        "dialogue": [
            {"cut_id": "cut-01", "narrative_role": "problem_or_hook", "text": "車の中、暑すぎない？"},
            {"cut_id": "cut-02", "narrative_role": "product", "text": "サンシェードを使う。"},
            {"cut_id": "cut-03", "narrative_role": "use_or_change", "text": "フロントに置くだけ。"},
            {"cut_id": "cut-04", "narrative_role": "result", "text": "正面からの日差しが入ってこない。"},
            {"cut_id": "cut-05", "narrative_role": "problem_resolution", "text": "正面からの日差しが入ってこない。"},
            {"cut_id": "cut-06", "narrative_role": "cta", "text": CTA_TEXT},
        ],
    }


def ans182_good_script() -> dict[str, Any]:
    script = ans182_bad_script()
    script["dialogue"][4]["text"] = "これで車内の暑さをしのげる。"
    return script


def self_test(project_root: Path | None) -> int:
    checks: list[tuple[str, bool]] = []

    def check(name: str, ok: bool) -> None:
        checks.append((name, ok))
        if not ok:
            print(f"FAIL {name}", flush=True)

    lessons: list[dict[str, Any]] = []
    if project_root is not None:
        lessons = load_active_lessons(project_root, "script", "AN-S182")
        check("lessons-loadable", isinstance(lessons, list))
    bad = validate("script", ans182_bad_script(), lessons)
    check("ans182-sun-only-hold", bad.get("status") == "HOLD" and bad.get("hold") == HOLD_CRAFT)
    check("ans182-sun-only-defect", bad.get("defect") == "hook_closed_by_result_looks")
    sun_only = ans182_bad_script()
    sun_only["dialogue"][3]["text"] = "外から銀色に見える。"
    sun_only_hold = validate("script", sun_only, lessons)
    check(
        "ans182-sun-only-not-restatement",
        sun_only_hold.get("status") == "HOLD" and sun_only_hold.get("defect") == "hook_closed_by_result_looks",
    )
    good = validate("script", ans182_good_script(), lessons)
    check("ans182-solution-pass", good.get("status") == "PASS")
    picture_bad = validate(
        "picture",
        {
            "schema": "product_video_picture_selection.v1",
            "cuts": [
                {
                    "cut_id": "cut-01",
                    "claimed_action": "shade opens",
                    "action_centered": True,
                    "range_covers_claimed_action": True,
                    "defaulted_to_first_n_seconds": True,
                    "chosen": {"asset_id": "asset-a", "source_in": 0, "source_out": 3},
                    "candidates": [],
                }
            ],
        },
        [],
    )
    check("picture-first-n-hold", picture_bad.get("defect") == "defaulted_first_n_seconds")
    picture_good = validate(
        "picture",
        {
            "schema": "product_video_picture_selection.v1",
            "cuts": [
                {
                    "cut_id": "cut-01",
                    "narrative_role": "product",
                    "claimed_action": "傘を開く",
                    "action_centered": True,
                    "range_covers_claimed_action": True,
                    "look_reads_different_from_previous": True,
                    "defaulted_to_first_n_seconds": False,
                    "chosen": {"asset_id": "asset-a", "source_in": 4.2, "source_out": 7.1},
                    "candidates": [
                        {"asset_id": "asset-a", "source_in": 0, "source_out": 3, "rejected_reason": "defaulted_first_n_seconds"},
                        {"asset_id": "asset-b", "source_in": 1, "source_out": 4, "rejected_reason": "action_not_centered"},
                    ],
                }
            ],
        },
        [],
    )
    check("picture-selection-pass", picture_good.get("status") == "PASS")
    caption_bad = validate(
        "captions",
        {
            "schema": "product_video_caption_craft.v1",
            "cuts": [
                {
                    "cut_id": "cut-01",
                    "composed_frame_proof": False,
                    "json_geometry_only": True,
                    "centered_on_screen": True,
                    "prominent": True,
                    "wrap_changed_characters": False,
                    "visible_layer_count": 1,
                }
            ],
        },
        [],
    )
    check("caption-json-only-hold", caption_bad.get("defect") == "json_geometry_only")
    caption_good = validate(
        "captions",
        {
            "schema": "product_video_caption_craft.v1",
            "cuts": [
                {
                    "cut_id": "cut-01",
                    "composed_frame_proof": True,
                    "json_geometry_only": False,
                    "centered_on_screen": True,
                    "prominent": True,
                    "wrap_changed_characters": False,
                    "visible_layer_count": 1,
                    "duplicate_layers": 0,
                }
            ],
        },
        [],
    )
    check("caption-composed-pass", caption_good.get("status") == "PASS")
    tts_bad = validate(
        "tts-timing",
        {"schema": "product_video_tts_craft.v1", "combined_clip_left_on_timeline": True, "per_cut_generation": False, "cuts": [{"cut_id": "cut-01", "three_layer_closed": True}]},
        [],
    )
    check("tts-combined-hold", tts_bad.get("defect") == "combined_tts_clip")
    tts_good = validate(
        "tts-timing",
        {
            "schema": "product_video_tts_craft.v1",
            "combined_clip_left_on_timeline": False,
            "per_cut_generation": True,
            "bulk_tts_used": False,
            "cuts": [
                {
                    "cut_id": "cut-01",
                    "cut_mid_speech": False,
                    "speech_matches_frozen_line": True,
                    "too_fast_to_hear": False,
                    "speech_shorter_than_claimed_action": False,
                    "picture_trimmed_to_speech": True,
                    "three_layer_closed": True,
                    "gap_ms": 600,
                    "is_final": False,
                }
            ],
        },
        [],
    )
    check("tts-split-pass", tts_good.get("status") == "PASS")
    explain_hold = validate(
        "script",
        {
            "schema": "product_video_craft_script.v1",
            "dialogue": [
                {"cut_id": "cut-01", "narrative_role": "problem_or_hook", "text": "車内が暑い。"},
                {"cut_id": "cut-02", "narrative_role": "product", "text": "サンシェードあるよ。"},
                {"cut_id": "cut-03", "narrative_role": "use_or_change", "text": "フロントへポン。"},
                {"cut_id": "cut-04", "narrative_role": "result", "text": "一面黒で隠れる。"},
                {"cut_id": "cut-05", "narrative_role": "problem_resolution", "text": "車内の暑さ防げる。"},
                {"cut_id": "cut-06", "narrative_role": "cta", "text": CTA_TEXT},
            ],
        },
        [],
    )
    check("explanatory-register-hold", explain_hold.get("defect") == "explanatory_register")
    unchanged = ans182_good_script()
    unchanged["previous_dialogue"] = [row["text"] for row in unchanged["dialogue"]]
    unchanged_hold = validate("script", unchanged, [])
    check("revision-unchanged-hold", unchanged_hold.get("defect") == "revision_unchanged")
    pita = ans182_good_script()
    pita["dialogue"][2]["text"] = "フロントにピタッ"
    pita_hold = validate(
        "script",
        pita,
        [
            {
                "id": "product-use-impossible-seal",
                "defect": "product_use_impossible",
                "gate": {
                    "kind": "forbidden_role_tokens",
                    "role": "use_or_change",
                    "fail_if_any_line_contains": ["ピタッ"],
                },
            }
        ],
    )
    check("pita-hold", pita_hold.get("defect") == "product_use_impossible")
    adjacent = validate(
        "picture",
        {
            "schema": "product_video_picture_selection.v1",
            "cuts": [
                {
                    "cut_id": "cut-01",
                    "claimed_action": "暑い車内",
                    "action_centered": True,
                    "range_covers_claimed_action": True,
                    "defaulted_to_first_n_seconds": False,
                    "chosen": {"asset_id": "a", "source_in": 3, "source_out": 5},
                    "candidates": [{"asset_id": "a", "rejected_reason": "head"}],
                },
                {
                    "cut_id": "cut-02",
                    "claimed_action": "押し当てる",
                    "action_centered": True,
                    "range_covers_claimed_action": True,
                    "look_reads_different_from_previous": False,
                    "adjacent_similar_look": True,
                    "defaulted_to_first_n_seconds": False,
                    "chosen": {"asset_id": "b", "source_in": 2, "source_out": 4},
                    "candidates": [{"asset_id": "b", "rejected_reason": "similar consecutive look"}],
                },
            ],
        },
        [],
    )
    check("adjacent-similar-look-hold", adjacent.get("defect") == "adjacent_similar_look")
    sequential = validate(
        "picture",
        {
            "schema": "product_video_picture_selection.v1",
            "cuts": [
                {
                    "cut_id": "cut-02",
                    "claimed_action": "傘を開く",
                    "action_centered": True,
                    "range_covers_claimed_action": True,
                    "defaulted_to_first_n_seconds": False,
                    "chosen": {"asset_id": "open", "source_in": 4, "source_out": 7},
                    "candidates": [{"asset_id": "open", "rejected_reason": "head"}],
                },
                {
                    "cut_id": "cut-03",
                    "claimed_action": "押し当てる",
                    "action_centered": True,
                    "range_covers_claimed_action": True,
                    "look_reads_different_from_previous": True,
                    "defaulted_to_first_n_seconds": False,
                    "chosen": {"asset_id": "press", "source_in": 2, "source_out": 5},
                    "candidates": [{"asset_id": "press", "rejected_reason": "same place and angle"}],
                },
            ],
        },
        [],
    )
    check("related-sequential-actions-pass", sequential.get("status") == "PASS")
    if not all(ok for _, ok in checks):
        print("SELF-TEST FAILED: validate_craft_quality", flush=True)
        return 1
    print("SELF-TEST PASSED: validate_craft_quality")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--product-model")
    parser.add_argument("--surface", choices=SURFACES)
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        root = args.project_root.resolve() if args.project_root else None
        return self_test(root)
    if args.project_root is None or args.surface is None or args.artifact is None:
        parser.error("--project-root, --surface, and --artifact are required unless --self-test is used")
    try:
        artifact = load_json(args.artifact)
        lessons = load_active_lessons(args.project_root.resolve(), args.surface, args.product_model)
        result = validate(args.surface, artifact, lessons)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = hold_payload(str(exc), surface=args.surface, defect="craft_artifact_unreadable")
        print(dump(result), end="")
        return 2
    print(dump(result), end="")
    return 0 if result.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
