#!/usr/bin/env python3
"""Create an isolated case and verified product inputs. No invented claims."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from constants import NARRATION_SPEED
from paths import case_root, emit, helper_path, project_root_from
from workflow_state import complete_stage, empty_state, hold, save_receipt, save_state, sha256_file

MODEL_RE = re.compile(r"^AN-[A-Z0-9]{4,6}$")
INVENTED_CLAIM_RE = re.compile(
    r"(?i)(\d+\s*%|倍|最強|必ず|絶対|効果実証|医学的|保証)"
)


def load_resolve_helper(project_root: Path):
    import importlib.util

    path = helper_path(project_root, "resolve_product_inputs")
    spec = importlib.util.spec_from_file_location("resolve_product_inputs", path)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def new_case_id(product_model: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"pv-{product_model}-{stamp}"


def resolve_case_id(
    project_root: Path,
    *,
    case_id: str | None,
    product_model: str | None,
) -> str | None:
    from workflow_state import find_active_case

    if case_id:
        return case_id
    return find_active_case(project_root, product_model)


def verified_strings(values: list[Any]) -> list[str]:
    out: list[str] = []
    for item in values:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def build_product_inputs(
    settings: dict[str, Any],
    *,
    verified_facts: list[str] | None = None,
    appeal_points: list[str] | None = None,
    user_campaign_focus: str = "",
    user_instructions: list[str] | None = None,
) -> dict[str, Any]:
    facts = verified_strings(verified_facts or [])
    appeals = verified_strings(appeal_points or [])
    instructions = verified_strings(user_instructions or [])
    cta = settings.get("cta") if isinstance(settings.get("cta"), dict) else {}
    if isinstance(cta.get("text"), str) and cta["text"].strip():
        facts.append(f"CTAは「{cta['text'].strip()}」")
    model = settings.get("product_model")
    if isinstance(model, str) and model.strip():
        facts.append(f"製品型番は{model.strip()}")
    configured_appeals = settings.get("product_appeal_points")
    if isinstance(configured_appeals, list):
        appeals.extend(verified_strings(configured_appeals))
    configured_info = settings.get("product_information")
    if isinstance(configured_info, list):
        facts.extend(verified_strings(configured_info))
    elif isinstance(configured_info, str) and configured_info.strip():
        facts.append(configured_info.strip())
    facts.extend(instructions)
    if user_campaign_focus.strip():
        # Campaign focus is a priority, not a new claim.
        pass
    for text in facts + appeals:
        if INVENTED_CLAIM_RE.search(text) and text not in (verified_facts or []) and text not in (appeal_points or []) and text not in (configured_appeals or []):
            # Allow only if the operator/settings already supplied it.
            continue
    product_information = "\n".join(f"- {line}" for line in facts) if facts else ""
    appeal_text = "\n".join(f"- {line}" for line in appeals) if appeals else ""
    if not facts:
        return hold("HOLD_PRODUCT_INFORMATION_INCOMPLETE", "no verified product information")
    return {
        "status": "OK",
        "product_information": product_information,
        "product_appeal_points": appeal_text,
        "user_campaign_focus": user_campaign_focus.strip(),
        "invented_claims": False,
    }


def create_new_case(
    project_root: Path,
    product_model: str,
    user_campaign_focus: str = "",
    *,
    verified_facts: list[str] | None = None,
    appeal_points: list[str] | None = None,
) -> dict[str, Any]:
    root = project_root_from(project_root)
    if not MODEL_RE.fullmatch(product_model):
        return hold("HOLD_MODEL_UNVERIFIED", "product_model is invalid", product_model=product_model)
    helper = load_resolve_helper(root)
    resolved = helper.resolve_product_inputs(
        root,
        product_model,
        material_root_env=__import__("os").environ.get("PRODUCT_VIDEO_MATERIAL_ROOT"),
        require_materials=True,
    )
    if resolved.get("status") != "READY":
        return resolved
    settings_path = Path(resolved["settings_path"])
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    inputs = build_product_inputs(
        settings,
        verified_facts=verified_facts,
        appeal_points=appeal_points,
        user_campaign_focus=user_campaign_focus,
    )
    if inputs.get("status") != "OK":
        return inputs
    case_id = new_case_id(product_model)
    dest = case_root(root, case_id)
    if dest.exists():
        return hold("HOLD_CASE_EXISTS", "refusing to overwrite an existing case", case_id=case_id)
    dest.mkdir(parents=True)
    state = empty_state(case_id, product_model)
    state["user_campaign_focus"] = user_campaign_focus.strip()
    state["narration_speed"] = NARRATION_SPEED
    state["material_root"] = resolved["material_root"]
    state["settings_path"] = resolved["settings_path"]
    state["settings_sha256"] = resolved["settings_sha256"]
    save_state(root, state)
    receipt = {
        "product_model": product_model,
        "settings_sha256": resolved["settings_sha256"],
        "material_root_exists": True,
        "drive_folder_title": resolved["drive_folder_title"],
        "product_information": inputs["product_information"],
        "product_appeal_points": inputs["product_appeal_points"],
        "user_campaign_focus": inputs["user_campaign_focus"],
        "settings_file_sha256": sha256_file(settings_path),
    }
    save_receipt(root, case_id, "PREPARE_DRAFT", receipt)
    (dest / "product-inputs.json").write_text(
        json.dumps(inputs, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"status": "OK", "case_id": case_id, "product_model": product_model}


def finish_prepare(project_root: Path, case_id: str) -> dict[str, Any]:
    from workflow_state import load_state

    state = load_state(project_root, case_id)
    inputs_path = case_root(project_root, case_id) / "product-inputs.json"
    if not inputs_path.is_file():
        return hold("HOLD_PRODUCT_INFORMATION_INCOMPLETE", "product-inputs.json is missing")
    inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    if inputs.get("status") != "OK":
        return inputs
    return complete_stage(
        project_root,
        state,
        "PREPARE",
        {
            "product_information": inputs.get("product_information"),
            "product_appeal_points": inputs.get("product_appeal_points"),
            "user_campaign_focus": inputs.get("user_campaign_focus"),
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--product-model", required=True)
    parser.add_argument("--campaign-focus", default="")
    parser.add_argument("--facts-json", type=Path)
    parser.add_argument("--appeal-json", type=Path)
    args = parser.parse_args()
    facts = json.loads(args.facts_json.read_text(encoding="utf-8")) if args.facts_json else []
    appeals = json.loads(args.appeal_json.read_text(encoding="utf-8")) if args.appeal_json else []
    payload = create_new_case(
        args.project_root,
        args.product_model,
        args.campaign_focus,
        verified_facts=facts,
        appeal_points=appeals,
    )
    emit(payload)
    return 0 if payload.get("status") == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
