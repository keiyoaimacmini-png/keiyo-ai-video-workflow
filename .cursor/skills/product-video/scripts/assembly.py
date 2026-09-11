#!/usr/bin/env python3
"""Select material from frozen lines, Gemini scenarios, and measured durations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from constants import MAJOR_VISUAL_KEYS
from paths import case_root
from prove_tts_speed import clip_target_duration
from script_fidelity import assert_immutable
from workflow_state import hold


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


def select_cut(
    candidates: list[dict[str, Any]],
    *,
    line: str,
    intended_scenario: str,
    duration_seconds: float,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    valid = [item for item in candidates if supports_line(item, line)]
    if not valid:
        return hold("HOLD_MEDIA_NOT_MATCHED", "no semantically valid material for this line")
    best = max(scenario_score(item, intended_scenario) for item in valid)
    pool = [item for item in valid if scenario_score(item, intended_scenario) == best]
    if previous is not None:
        pool = sorted(
            pool,
            key=lambda item: visual_diff_score(item.get("visual") or {}, previous.get("visual") or {}),
            reverse=True,
        )
    chosen = dict(pool[0])
    chosen["target_duration_seconds"] = float(duration_seconds)
    chosen["line"] = line
    chosen["intended_scenario"] = intended_scenario
    return {"status": "OK", "selection": chosen}


def assemble_plan(
    approved_script: dict[str, Any],
    narration_manifest: dict[str, Any],
    candidates_by_cut: dict[str, list[dict[str, Any]]],
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
