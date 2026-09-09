#!/usr/bin/env python3
"""SCRIPT LINE == NARRATION == TELOP. Exact equality only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paths import case_root
from workflow_state import complete_stage, hold, save_state, sha256_text


def exact_equal(left: str, right: str) -> bool:
    return left == right


def assert_immutable(approved_line: str, candidate: str, *, role: str) -> dict[str, Any]:
    if not exact_equal(approved_line, candidate):
        return hold(
            "HOLD_SCRIPT_LINE_IMMUTABLE",
            f"{role} must equal the approved script line exactly",
        )
    return {"status": "OK"}


def load_variants(project_root: Path, case_id: str) -> dict[str, Any]:
    path = case_root(project_root, case_id) / "script-variants.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("status") != "OK":
        raise ValueError("script variants are missing")
    return data


def freeze_approved_script(project_root: Path, state: dict[str, Any], variant_id: int) -> dict[str, Any]:
    from constants import NEXT_STAGE

    variants = load_variants(project_root, state["case_id"])
    chosen = next((item for item in variants["variants"] if item["variant_id"] == variant_id), None)
    if chosen is None:
        return hold("HOLD_SCRIPT_VARIANT_MISSING", f"案{variant_id} is not available")
    frozen = {
        "schema": "product_video_approved_script.v1",
        "variant_id": variant_id,
        "title": chosen["title"],
        "cuts": [
            {
                "cut_id": cut["cut_id"],
                "index": cut["index"],
                "line": cut["line"],
                "situation": cut["situation"],
            }
            for cut in chosen["cuts"]
        ],
    }
    text = json.dumps(frozen, ensure_ascii=False, indent=2) + "\n"
    dest = case_root(project_root, state["case_id"]) / "approved-script.json"
    dest.write_text(text, encoding="utf-8")
    digest = sha256_text(text)
    state["selected_script_variant"] = variant_id
    state["approved_script_path"] = dest.as_posix()
    state["approved_script_hash"] = digest
    save_state(project_root, state)
    return complete_stage(
        project_root,
        state,
        "SCRIPT_SELECTION",
        {
            "variant_id": variant_id,
            "approved_script_hash": digest,
            "cut_count": len(frozen["cuts"]),
        },
        next_stage=NEXT_STAGE["SCRIPT_SELECTION"],
    )


def load_approved_script(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "product_video_approved_script.v1":
        raise ValueError("approved script schema mismatch")
    return data
