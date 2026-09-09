#!/usr/bin/env python3
"""Export, Drive upload/read-back, then purge. Observe unknown jobs. No blind retry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from constants import DELIVERY_APPROVAL, UNKNOWN_JOB_STATUSES
from paths import case_root, helper_path
from workflow_state import complete_stage, hold, save_state

ORDINAL_MARKERS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def authorize_delivery(project_root: Path, state: dict[str, Any], utterance: str) -> dict[str, Any]:
    if (utterance or "").strip() != DELIVERY_APPROVAL:
        return hold("HOLD_DELIVERY_APPROVAL_REQUIRED", "need 完成・格納してください")
    if state.get("current_stage") != "WAITING_FOR_OPERATOR":
        return hold("HOLD_DELIVERY_NOT_DUE", "delivery is only after WAITING_FOR_OPERATOR")
    state["delivery_authorized"] = True
    save_state(project_root, state)
    return complete_stage(
        project_root,
        state,
        "WAITING_FOR_OPERATOR",
        {"approval": DELIVERY_APPROVAL, "ai_visual_quality_review": False},
        next_stage="DELIVERY",
    )


def may_start_job(status: str | None) -> dict[str, Any]:
    if status in UNKNOWN_JOB_STATUSES:
        return hold(
            "HOLD_JOB_OUTCOME_UNKNOWN",
            "observe the existing export/upload job before retrying",
            retry=False,
        )
    if status in (None, "not_started", "failed"):
        return {"status": "OK", "start": True}
    if status in ("verified", "complete", "completed", "ok"):
        return hold("HOLD_JOB_ALREADY_DONE", "do not duplicate a finished job", retry=False)
    return hold("HOLD_JOB_OUTCOME_UNKNOWN", f"status {status} is not safe to retry", retry=False)


def may_complete(delivery: dict[str, Any]) -> dict[str, Any]:
    if delivery.get("export_verified") is not True:
        return hold("HOLD_EXPORT_NOT_VERIFIED", "export verification is required")
    if delivery.get("local_file_verified") is not True:
        return hold("HOLD_EXPORT_NOT_VERIFIED", "local exported file is unverified")
    if delivery.get("drive_uploaded") is not True or delivery.get("drive_readback_verified") is not True:
        return hold("HOLD_DRIVE_READBACK_REQUIRED", "Drive verification is required before COMPLETE")
    return {"status": "OK"}


def may_purge(state: dict[str, Any], delivery: dict[str, Any]) -> dict[str, Any]:
    if state.get("current_stage") != "COMPLETE":
        return hold("HOLD_POST_COMPLETE_PURGE_NOT_DUE", "purge is only after COMPLETE")
    if delivery.get("drive_readback_verified") is not True and delivery.get("destination_verified") is not True:
        return hold("HOLD_POST_COMPLETE_PURGE_NOT_DUE", "purge requires verified delivery")
    return {"status": "OK", "purge": True}


def write_purge_compat_state(
    project_root: Path,
    state: dict[str, Any],
    delivery: dict[str, Any],
) -> Path:
    """Adapter so the existing purge helper can run without redesigning it."""
    dest = case_root(project_root, state["case_id"]) / "product-video-workflow-state.v1.json"
    filename = delivery.get("completed_video_filename")
    payload = {
        "schema": "product_video_workflow_state.v1",
        "case_id": state["case_id"],
        "stage": "COMPLETE",
        "delivery_mode": "drive",
        "approvals": {
            "final_export": {
                "status": "approved",
                "receipt": "完成・書き出しOK",
                "mapped_from": DELIVERY_APPROVAL,
            }
        },
        "artifacts": {
            "export": {"path": "receipts/delivery.json", "completed_video_filename": filename},
            "drive": {"path": "receipts/delivery.json"},
        },
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dest


def helper_commands(project_root: Path) -> dict[str, str]:
    return {
        "upload_drive_local_file": str(helper_path(project_root, "upload_drive_local_file")),
        "purge_local_working_media": str(helper_path(project_root, "purge_local_working_media")),
    }


def render_completed_filename(jst_date: str, product_model: str, ordinal: int) -> str:
    if ordinal < 1 or ordinal > 20:
        raise ValueError("ordinal must be 1-20")
    return f"{jst_date}_{product_model}_AI作成{ORDINAL_MARKERS[ordinal - 1]}.mp4"
