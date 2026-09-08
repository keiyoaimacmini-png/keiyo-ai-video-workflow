#!/usr/bin/env python3
"""Render the portable Gemini.app prompt. Do not inject prior-correction examples."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lessons import dump, hold_payload


def load_portable_renderer(project_root: Path):
    path = (
        project_root
        / ".cursor"
        / "skills"
        / "produce-tiktok-product-video-portable"
        / "scripts"
        / "render_gemini_web_prompt.py"
    )
    spec = importlib.util.spec_from_file_location("portable_gemini_prompt", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"portable renderer missing: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render(project_root: Path, brief_text: str, product_model: str | None) -> str:
    portable = load_portable_renderer(project_root)
    brief = portable.load_brief(brief_text)
    return portable.render_prompt(brief)


def self_test(project_root: Path) -> int:
    checks: list[tuple[str, bool]] = []

    def check(name: str, ok: bool) -> None:
        checks.append((name, ok))
        if not ok:
            print(f"FAIL {name}", flush=True)

    brief = {
        "schema": "product_video_gemini_web_brief.v1",
        "product_model": "AN-S182",
        "cta_text": "下からチェック！",
        "verified_facts": ["車内が暑い"],
        "usable_shots": [{"asset_id": "asset-a", "observed_action": "shade opens"}],
    }
    prompt = render(project_root, json.dumps(brief, ensure_ascii=False), "AN-S182")
    check("keeps-portable-cta", "下からチェック！" in prompt)
    check("keeps-verified-fact", "車内が暑い" in prompt)
    check("does-not-send-shots", "shade opens" not in prompt)
    if not all(ok for _, ok in checks):
        print("SELF-TEST FAILED: render_gemini_web_prompt", flush=True)
        return 1
    print("SELF-TEST PASSED: render_gemini_web_prompt")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brief", type=argparse.FileType("r", encoding="utf-8"))
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--product-model")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    root = args.project_root.resolve()
    if args.self_test:
        return self_test(root)
    if args.brief is None:
        parser.error("--brief is required unless --self-test is used")
    try:
        prompt = render(root, args.brief.read(), args.product_model)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(dump(hold_payload(str(exc), surface="script", defect="gemini_brief_invalid")), end="")
        return 2
    print(prompt, end="" if prompt.endswith("\n") else "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
