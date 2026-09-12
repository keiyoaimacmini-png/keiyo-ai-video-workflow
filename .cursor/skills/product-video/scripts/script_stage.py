#!/usr/bin/env python3
"""Save Gemini variants then advance SCRIPT -> SCRIPT_SELECTION."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from constants import HOLD_SCRIPT_PRODUCT_GROUNDING, MAX_SCRIPT_GROUNDING_ATTEMPTS
from parse_gemini_scripts import parse_gemini_scripts
from paths import case_root, emit, helper_path
from script_grounding import present_for_operator, prove_scripts_grounding
from workflow_state import complete_stage, hold, load_state, save_state


def store_variants(project_root: Path, case_id: str, parsed: dict) -> Path:
    dest = case_root(project_root, case_id) / "script-variants.json"
    dest.write_text(json.dumps(parsed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dest


def load_product_inputs(project_root: Path, case_id: str) -> dict:
    path = case_root(project_root, case_id) / "product-inputs.json"
    if not path.is_file():
        return hold("HOLD_PRODUCT_INFORMATION_INCOMPLETE", "product-inputs.json is missing")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return hold("HOLD_PRODUCT_INFORMATION_INCOMPLETE", "product-inputs.json is invalid")
    return data


def accept_gemini_output(project_root: Path, case_id: str, raw_text: str) -> dict:
    parsed = parse_gemini_scripts(raw_text)
    if parsed.get("status") != "OK":
        return parsed
    inputs = load_product_inputs(project_root, case_id)
    if inputs.get("status") == "HOLD":
        return inputs
    proof = prove_scripts_grounding(
        parsed,
        str(inputs.get("product_information") or ""),
        str(inputs.get("product_appeal_points") or ""),
    )
    state = load_state(project_root, case_id)
    if proof.get("status") != "OK":
        attempts = int(state.get("script_grounding_attempts") or 0) + 1
        state["script_grounding_attempts"] = attempts
        save_state(project_root, state)
        regenerate = bool(proof.get("regenerate")) and attempts < MAX_SCRIPT_GROUNDING_ATTEMPTS
        payload = hold(
            HOLD_SCRIPT_PRODUCT_GROUNDING,
            proof.get("reason") or "script product grounding failed",
            regenerate=regenerate,
            attempt=attempts,
        )
        if proof.get("failures"):
            payload["failures"] = proof["failures"]
        payload["fact_count"] = proof.get("fact_count")
        return payload
    path = store_variants(project_root, case_id, parsed)
    state["script_variant_ids"] = [item["variant_id"] for item in parsed["variants"]]
    state["script_grounding_attempts"] = int(state.get("script_grounding_attempts") or 0)
    save_state(project_root, state)
    operator = present_for_operator(parsed)
    receipt = complete_stage(
        project_root,
        state,
        "SCRIPT",
        {"variant_count": parsed["variant_count"], "variants_path": path.as_posix()},
    )
    receipt["message_ja"] = "台本案を提示します。採用する案を「案Nで台本OK」で指定してください。"
    receipt["variants"] = [
        {"variant_id": item["variant_id"], "title": item["title"], "cut_count": len(item["cuts"])}
        for item in operator["variants"]
    ]
    receipt["operator_variants"] = operator["variants"]
    return receipt


def gemini_transport_path(project_root: Path) -> str:
    return str(helper_path(project_root, "send_gemini_cli_prompt"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--gemini-output", type=Path, required=True)
    args = parser.parse_args()
    payload = accept_gemini_output(
        args.project_root,
        args.case_id,
        args.gemini_output.read_text(encoding="utf-8"),
    )
    emit(payload)
    return 0 if payload.get("status") == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
