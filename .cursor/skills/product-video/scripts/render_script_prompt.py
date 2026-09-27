#!/usr/bin/env python3
"""Render the Gemini script prompt from verified inputs. Do not invent claims."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from paths import emit, skill_root
from script_grounding import label_product_blocks
from workflow_state import hold

PLACEHOLDERS = (
    "{{PRODUCT_INFORMATION}}",
    "{{PRODUCT_APPEAL_POINTS}}",
    "{{USER_CAMPAIGN_FOCUS}}",
    "{{LEDGER_SCENES}}",
)

EMPTY_LEDGER_SCENES = "撮れている画面の一覧は空です。シチュエーションは、商品情報の範囲で撮影できる場面にする。"


def script_rules_path(project_root: Path, product_model: str) -> Path:
    return project_root / "config" / f"product_video_script_rules_{product_model}.v1.json"


def load_product_script_rules_text(project_root: Path, product_model: str) -> str:
    if not product_model:
        return ""
    path = script_rules_path(project_root, product_model)
    if not path.is_file():
        return ""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("product_model") != product_model:
        raise ValueError(f"script rules product_model mismatch: {path.name}")
    rules = data.get("rules") or []
    if isinstance(rules, str):
        return rules.strip()
    if not isinstance(rules, list):
        return ""
    lines = [str(item).strip() for item in rules if str(item).strip()]
    return "\n".join(f"- {line}" for line in lines)


def merge_campaign_focus(campaign_focus: str, rules_text: str) -> str:
    focus = campaign_focus.strip()
    extra = rules_text.strip()
    if not extra or extra in focus:
        return focus
    if not focus:
        return extra
    return f"{focus}\n{extra}"


def load_template(project_root: Path) -> str:
    path = skill_root(project_root) / "references" / "gemini-script-instructions.md"
    return path.read_text(encoding="utf-8")


def render_script_prompt(
    template: str,
    *,
    product_information: str,
    product_appeal_points: str,
    user_campaign_focus: str = "",
    ledger_scenes: str = "",
) -> str:
    if not product_information.strip():
        raise ValueError("PRODUCT_INFORMATION is required")
    labeled = label_product_blocks(product_information, product_appeal_points)
    prompt = template
    prompt = prompt.replace("{{PRODUCT_INFORMATION}}", labeled["product_information"])
    prompt = prompt.replace("{{PRODUCT_APPEAL_POINTS}}", labeled["product_appeal_points"])
    prompt = prompt.replace("{{USER_CAMPAIGN_FOCUS}}", user_campaign_focus.strip())
    prompt = prompt.replace("{{LEDGER_SCENES}}", ledger_scenes.strip() or EMPTY_LEDGER_SCENES)
    for token in PLACEHOLDERS:
        if token in prompt:
            raise ValueError(f"unresolved placeholder {token}")
    return prompt if prompt.endswith("\n") else prompt + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--product-information", required=True)
    parser.add_argument("--appeal-points", default="")
    parser.add_argument("--campaign-focus", default="")
    parser.add_argument("--product-model", default="")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    ledger_scenes = ""
    campaign_focus = args.campaign_focus
    if args.product_model:
        from compile_material_ledger import scene_lines_from_catalog
        from visual_catalog import load_catalog

        ledger_scenes = scene_lines_from_catalog(load_catalog(args.project_root, args.product_model))
        campaign_focus = merge_campaign_focus(
            campaign_focus,
            load_product_script_rules_text(args.project_root, args.product_model),
        )
    try:
        prompt = render_script_prompt(
            load_template(args.project_root),
            product_information=args.product_information,
            product_appeal_points=args.appeal_points,
            user_campaign_focus=campaign_focus,
            ledger_scenes=ledger_scenes,
        )
    except (OSError, ValueError) as exc:
        emit(hold("HOLD_SCRIPT_PROMPT", str(exc)))
        return 2
    if args.output:
        args.output.write_text(prompt, encoding="utf-8")
        emit({"status": "OK", "path": args.output.as_posix(), "chars": len(prompt)})
    else:
        print(prompt, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
