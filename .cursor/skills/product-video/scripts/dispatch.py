#!/usr/bin/env python3
"""Thin orchestrator: choose one stage Skill, never rerun completed work."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from constants import (
    DELIVERY_APPROVAL,
    OPERATOR_ROUGH_MESSAGE,
    SKILL_FOR_STAGE,
    STOP_STAGES,
)
from bind_script_selection import bind_script_selection
from paths import emit, project_root_from, skill_root, state_path
from workflow_state import hold, load_state, stage_already_complete


def stop(reason: str, **extra: Any) -> dict[str, Any]:
    payload = {"status": "OK", "action": "stop", "reason": reason}
    payload.update(extra)
    return payload


def run_skill(skill: str, stage: str, **extra: Any) -> dict[str, Any]:
    payload = {
        "status": "OK",
        "action": "run_skill",
        "skill": skill,
        "stage": stage,
        "ask_continue": False,
    }
    payload.update(extra)
    return payload


def dispatch(
    project_root: Path,
    *,
    case_id: str | None = None,
    utterance: str | None = None,
    product_model: str | None = None,
) -> dict[str, Any]:
    from prepare import create_new_case, resolve_case_id

    root = project_root_from(project_root)
    resolved_case = resolve_case_id(root, case_id=case_id, product_model=product_model)
    if resolved_case is None:
        if not product_model:
            return hold("HOLD_PRODUCT_MODEL_REQUIRED", "new case needs --product-model")
        created = create_new_case(root, product_model, utterance or "")
        if created.get("status") != "OK":
            return created
        return run_skill(
            "product-video-prepare",
            "PREPARE",
            case_id=created["case_id"],
            skill_root=str(skill_root(root) / ".." / "product-video-prepare"),
        )

    case_id = resolved_case
    path = state_path(root, case_id)
    if not path.is_file():
        return hold("HOLD_CASE_STATE_MISSING", "workflow state is missing", case_id=case_id)

    state = load_state(root, case_id)
    stage = state["current_stage"]
    text = (utterance or "").strip()

    if stage == "COMPLETE":
        return stop("complete", case_id=case_id, current_stage=stage)

    if state.get("hold"):
        return stop("hold", case_id=case_id, current_stage=stage, hold=state["hold"])

    if stage == "SCRIPT_SELECTION":
        bound = bind_script_selection(text, state)
        if bound.get("status") != "OK":
            return stop(
                "waiting_script_selection",
                case_id=case_id,
                current_stage=stage,
                message_ja="案番号を指定して「案Nで台本OK」と送ってください。",
                bind=bound,
            )
        from script_fidelity import freeze_approved_script

        frozen = freeze_approved_script(root, state, bound["variant_id"])
        if frozen.get("status") != "OK":
            return frozen
        state = load_state(root, case_id)
        return run_skill("product-video-narration", "NARRATION", case_id=case_id)

    if stage == "WAITING_FOR_OPERATOR":
        if text != DELIVERY_APPROVAL:
            return stop(
                "waiting_for_operator",
                case_id=case_id,
                current_stage=stage,
                message_ja=OPERATOR_ROUGH_MESSAGE,
            )
        from delivery import authorize_delivery

        authorized = authorize_delivery(root, state, text)
        if authorized.get("status") != "OK":
            return authorized
        state = load_state(root, case_id)
        return run_skill("product-video-delivery", "DELIVERY", case_id=case_id)

    if stage in STOP_STAGES:
        return stop("wait", case_id=case_id, current_stage=stage)

    if stage_already_complete(state, stage):
        return hold(
            "HOLD_STAGE_ALREADY_COMPLETE",
            f"{stage} already completed; resume from {state.get('current_stage')}",
            case_id=case_id,
        )

    skill = SKILL_FOR_STAGE.get(stage)
    if not skill:
        return hold("HOLD_STAGE_UNKNOWN", f"no skill for {stage}", case_id=case_id)
    extra = {"case_id": case_id}
    if stage == "ROUGH_EDIT":
        extra["on_success_message_ja"] = OPERATOR_ROUGH_MESSAGE
    return run_skill(skill, stage, **extra)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--case-id")
    parser.add_argument("--product-model")
    parser.add_argument("--utterance")
    parser.add_argument("--utterance-file", type=Path)
    args = parser.parse_args()
    utterance = args.utterance
    if args.utterance_file:
        utterance = args.utterance_file.read_text(encoding="utf-8")
    payload = dispatch(
        args.project_root,
        case_id=args.case_id,
        utterance=utterance,
        product_model=args.product_model,
    )
    emit(payload)
    return 0 if payload.get("status") == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
