#!/usr/bin/env python3
"""Compact per-case workflow state. No media, DOM, base64, or large logs."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from constants import (
    FORBIDDEN_STATE_KEYS,
    NARRATION_SPEED,
    SCHEMA,
    STAGES,
    STATE_FILENAME,
    STATE_MAX_BYTES,
)
from paths import outputs_root, receipts_dir, state_path


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def hold(code: str, reason: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": "HOLD", "hold": code, "reason": reason}
    payload.update(extra)
    return payload


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _walk_forbidden(obj: Any, trail: tuple[str, ...] = ()) -> str | None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            lowered = str(key).lower()
            if lowered in FORBIDDEN_STATE_KEYS:
                return ".".join(trail + (str(key),))
            found = _walk_forbidden(value, trail + (str(key),))
            if found:
                return found
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            found = _walk_forbidden(value, trail + (str(index),))
            if found:
                return found
    elif isinstance(obj, str) and obj.startswith(("data:image", "data:video", "data:audio")):
        return ".".join(trail) or "inline_data_url"
    return None


def validate_compact(data: dict[str, Any], *, max_bytes: int = STATE_MAX_BYTES) -> list[str]:
    errors: list[str] = []
    blob = json.dumps(data, ensure_ascii=False)
    if len(blob.encode("utf-8")) > max_bytes:
        errors.append(f"payload exceeds {max_bytes} bytes")
    found = _walk_forbidden(data)
    if found:
        errors.append(f"forbidden key or inline media: {found}")
    return errors


def empty_state(case_id: str, product_model: str) -> dict[str, Any]:
    stamp = now_iso()
    return {
        "schema": SCHEMA,
        "case_id": case_id,
        "product_model": product_model,
        "current_stage": "PREPARE",
        "selected_script_variant": None,
        "approved_script_path": None,
        "approved_script_hash": None,
        "narration_speed": NARRATION_SPEED,
        "narration_manifest_path": None,
        "editor_project_identity": None,
        "delivery_status": None,
        "created_at": stamp,
        "updated_at": stamp,
        "completed_stages": [],
        "hold": None,
        "user_campaign_focus": "",
    }


def load_state(project_root: Path, case_id: str) -> dict[str, Any]:
    path = state_path(project_root, case_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_state(data, case_id)
    if errors:
        raise ValueError("; ".join(errors))
    return data


def validate_state(data: dict[str, Any], case_id: str | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["state must be an object"]
    if data.get("schema") != SCHEMA:
        errors.append("schema mismatch")
    if case_id is not None and data.get("case_id") != case_id:
        errors.append("case_id mismatch")
    if data.get("current_stage") not in STAGES:
        errors.append("current_stage invalid")
    if data.get("narration_speed") != NARRATION_SPEED:
        errors.append("narration_speed must be 1.2")
    completed = data.get("completed_stages")
    if not isinstance(completed, list) or any(item not in STAGES for item in completed):
        errors.append("completed_stages invalid")
    errors.extend(validate_compact(data))
    return errors


def save_state(project_root: Path, data: dict[str, Any]) -> Path:
    case_id = data["case_id"]
    data["updated_at"] = now_iso()
    errors = validate_state(data, case_id)
    if errors:
        raise ValueError("; ".join(errors))
    path = state_path(project_root, case_id)
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return path


def save_receipt(project_root: Path, case_id: str, stage: str, receipt: dict[str, Any]) -> Path:
    payload = {
        "schema": "product_video_stage_receipt.v1",
        "case_id": case_id,
        "stage": stage,
        "recorded_at": now_iso(),
        "result": receipt,
    }
    errors = validate_compact(payload, max_bytes=65536)
    if errors:
        raise ValueError("; ".join(errors))
    path = receipts_dir(project_root, case_id) / f"{stage.lower()}.json"
    atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return path


def stage_already_complete(state: dict[str, Any], stage: str) -> bool:
    return stage in state.get("completed_stages", [])


def clear_hold(project_root: Path, case_id: str) -> dict[str, Any]:
    state = load_state(project_root, case_id)
    state["hold"] = None
    save_state(project_root, state)
    return {
        "status": "OK",
        "case_id": case_id,
        "current_stage": state["current_stage"],
        "completed_stages": list(state.get("completed_stages") or []),
        "hold": None,
    }


def complete_stage(
    project_root: Path,
    state: dict[str, Any],
    stage: str,
    receipt: dict[str, Any],
    *,
    next_stage: str | None = None,
) -> dict[str, Any]:
    from constants import NEXT_STAGE

    if state.get("current_stage") != stage:
        raise ValueError(f"current_stage is {state.get('current_stage')}, not {stage}")
    if stage_already_complete(state, stage):
        raise ValueError(f"stage {stage} already completed")
    receipt_path = save_receipt(project_root, state["case_id"], stage, receipt)
    state["completed_stages"] = list(state.get("completed_stages") or []) + [stage]
    state["current_stage"] = next_stage or NEXT_STAGE[stage]
    state["hold"] = None
    save_state(project_root, state)
    return {"status": "OK", "receipt_path": receipt_path.as_posix(), "current_stage": state["current_stage"]}


def find_active_case(project_root: Path, product_model: str | None = None) -> str | None:
    root = outputs_root(project_root)
    if not root.is_dir():
        return None
    found: list[tuple[str, str]] = []
    for path in sorted(root.glob("*/" + STATE_FILENAME.split("/")[-1])):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("schema") != SCHEMA:
            continue
        if data.get("current_stage") == "COMPLETE":
            continue
        if product_model and data.get("product_model") != product_model:
            continue
        found.append((data.get("updated_at") or "", data["case_id"]))
    if not found:
        return None
    found.sort()
    return found[-1][1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args()
    data = load_state(args.project_root, args.case_id)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
