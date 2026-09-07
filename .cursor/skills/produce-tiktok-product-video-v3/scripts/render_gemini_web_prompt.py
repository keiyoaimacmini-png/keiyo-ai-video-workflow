#!/usr/bin/env python3
"""Render a Gemini.app paste prompt that includes active script lessons."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lessons import dump, hold_payload, load_active_lessons


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


def lesson_examples(lessons: list[dict[str, Any]]) -> str:
    if not lessons:
        return ""
    lines = [
        "次の落ちた実例は使うな。通った実例の結び方だけを守れ。",
    ]
    for lesson in lessons:
        bad = lesson.get("bad") if isinstance(lesson.get("bad"), dict) else {}
        good = lesson.get("good") if isinstance(lesson.get("good"), dict) else {}
        lines.append(f"欠格 {lesson.get('defect')}:")
        if bad.get("hook") or bad.get("resolution"):
            lines.append(f"落ちたフック: {bad.get('hook', '')}")
            lines.append(f"落ちた解決: {bad.get('resolution', '')}")
        if good.get("hook") or good.get("resolution"):
            lines.append(f"通ったフック: {good.get('hook', '')}")
            lines.append(f"通った解決: {good.get('resolution', '')}")
    return "\n".join(lines) + "\n"


def render(project_root: Path, brief_text: str, product_model: str | None) -> str:
    portable = load_portable_renderer(project_root)
    brief = portable.load_brief(brief_text)
    model = product_model or brief.get("product_model")
    prompt = portable.render_prompt(brief)
    lessons = load_active_lessons(project_root, "script", model if isinstance(model, str) else None)
    extra = lesson_examples(lessons)
    if extra:
        prompt = prompt.rstrip() + "\n" + extra
        if not prompt.endswith("\n"):
            prompt += "\n"
    return prompt


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
    check("includes-bad-resolution", "正面からの日差しが入ってこない。" in prompt)
    check("includes-good-resolution", "これで車内の暑さをしのげる。" in prompt)
    check("includes-defect-name", "hook_closed_by_result_looks" in prompt)
    check("keeps-portable-cta", "下からチェック！" in prompt)
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
