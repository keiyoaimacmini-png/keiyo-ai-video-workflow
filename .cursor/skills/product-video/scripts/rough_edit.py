#!/usr/bin/env python3
"""Usable rough edit only. Telop equals approved line. No AI visual scoring."""

from __future__ import annotations

from typing import Any

from constants import OPERATOR_ROUGH_MESSAGE
from script_fidelity import assert_immutable
from workflow_state import hold


def telop_matches(approved_line: str, telop: str) -> dict[str, Any]:
    return assert_immutable(approved_line, telop, role="telop")


def build_rough_edit(
    approved_script: dict[str, Any],
    assembly_plan: dict[str, Any],
    narration_manifest: dict[str, Any],
    *,
    editor_project_identity: str,
    placed_telops: list[dict[str, str]],
) -> dict[str, Any]:
    if not editor_project_identity:
        return hold("HOLD_EDITOR_PROJECT_UNVERIFIED", "editor project identity is required")
    clips = {clip["cut_id"]: clip for clip in narration_manifest.get("clips") or []}
    plan_cuts = {cut["cut_id"]: cut for cut in assembly_plan.get("cuts") or []}
    telop_by_cut = {item["cut_id"]: item.get("text") for item in placed_telops}
    placed: list[dict[str, Any]] = []
    for cut in approved_script.get("cuts") or []:
        line = cut["line"]
        telop = telop_by_cut.get(cut["cut_id"])
        matched = telop_matches(line, telop or "")
        if matched.get("status") != "OK":
            return matched
        if cut["cut_id"] not in clips:
            return hold("HOLD_NARRATION_AUDIO", f"missing narration for {cut['cut_id']}")
        if cut["cut_id"] not in plan_cuts:
            return hold("HOLD_ASSEMBLY_PLAN", f"missing assembly cut {cut['cut_id']}")
        placed.append(
            {
                "cut_id": cut["cut_id"],
                "line": line,
                "telop": telop,
                "audio_path": clips[cut["cut_id"]]["audio_path"],
                "duration_seconds": clips[cut["cut_id"]]["duration_seconds"],
                "material": plan_cuts[cut["cut_id"]].get("material_id") or plan_cuts[cut["cut_id"]].get("path"),
            }
        )
    return {
        "status": "OK",
        "usable_rough_edit": True,
        "editor_project_identity": editor_project_identity,
        "cuts": placed,
        "ai_visual_quality_review": False,
        "operator_message_ja": OPERATOR_ROUGH_MESSAGE,
    }
