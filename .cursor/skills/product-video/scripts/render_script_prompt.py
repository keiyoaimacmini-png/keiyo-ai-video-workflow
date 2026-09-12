#!/usr/bin/env python3
"""Render the Gemini script prompt from verified inputs. Do not invent claims."""

from __future__ import annotations

import argparse
from pathlib import Path

from paths import emit, skill_root
from script_grounding import label_product_blocks
from workflow_state import hold

PLACEHOLDERS = (
    "{{PRODUCT_INFORMATION}}",
    "{{PRODUCT_APPEAL_POINTS}}",
    "{{USER_CAMPAIGN_FOCUS}}",
)


def load_template(project_root: Path) -> str:
    path = skill_root(project_root) / "references" / "gemini-script-instructions.md"
    return path.read_text(encoding="utf-8")


def render_script_prompt(
    template: str,
    *,
    product_information: str,
    product_appeal_points: str,
    user_campaign_focus: str = "",
) -> str:
    if not product_information.strip():
        raise ValueError("PRODUCT_INFORMATION is required")
    labeled = label_product_blocks(product_information, product_appeal_points)
    prompt = template
    prompt = prompt.replace("{{PRODUCT_INFORMATION}}", labeled["product_information"])
    prompt = prompt.replace("{{PRODUCT_APPEAL_POINTS}}", labeled["product_appeal_points"])
    prompt = prompt.replace("{{USER_CAMPAIGN_FOCUS}}", user_campaign_focus.strip())
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
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        prompt = render_script_prompt(
            load_template(args.project_root),
            product_information=args.product_information,
            product_appeal_points=args.appeal_points,
            user_campaign_focus=args.campaign_focus,
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
