#!/usr/bin/env python3
"""Render a key-free Gemini Web paste prompt from a local brief.

No network. No API keys. The host pastes the printed text into official
Gemini Web on this machine's Chrome after frame inventory.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any


BRIEF_SCHEMA = "product_video_gemini_web_brief.v1"
CTA_TEXT = "下からチェック！"
NARRATIVE_ROLES = (
    "problem_or_hook",
    "product",
    "use_or_change",
    "result",
    "problem_resolution",
    "cta",
)
SECRET_RE = re.compile(r"(?i)(?:x-goog-api-key\s*[:=]\s*)[^\s\"']+|AIza[0-9A-Za-z_\-]{10,}")
FORBIDDEN_KEY_RE = re.compile(
    r"(?i)(sha256|in_sec|out_sec|source_in|source_out|cookie|token|api[_-]?key|password)"
)


def hold(code: str, reason: str) -> dict[str, str]:
    return {"status": "HOLD", "hold": code, "reason": reason}


def load_brief(text: str) -> dict[str, Any]:
    if SECRET_RE.search(text):
        raise ValueError("brief must not contain secrets")
    data = json.loads(text)
    if not isinstance(data, dict) or data.get("schema") != BRIEF_SCHEMA:
        raise ValueError("brief schema mismatch")
    facts = data.get("verified_facts")
    shots = data.get("usable_shots")
    if not isinstance(facts, list) or not facts:
        raise ValueError("verified_facts required")
    if not isinstance(shots, list) or not shots:
        raise ValueError("usable_shots required")
    if data.get("cta_text") != CTA_TEXT:
        raise ValueError("cta_text must be the frozen CTA")
    blob = json.dumps(data, ensure_ascii=False)
    if FORBIDDEN_KEY_RE.search(blob):
        raise ValueError("brief must not include hashes, in/out, cookies, tokens, or keys")
    for fact in facts:
        if not isinstance(fact, str) or not fact.strip():
            raise ValueError("verified_facts must be non-empty strings")
        if re.search(r"AN-[A-Z0-9]{4,6}", fact):
            raise ValueError("verified_facts must not include product-model codes")
    for shot in shots:
        if not isinstance(shot, dict):
            raise ValueError("usable_shots must be objects")
        action = shot.get("observed_action")
        asset_id = shot.get("asset_id")
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise ValueError("usable_shots need asset_id")
        if not isinstance(action, str) or not action.strip():
            raise ValueError("usable_shots need observed_action")
        if re.search(r"AN-[A-Z0-9]{4,6}", action):
            raise ValueError("observed_action must not include product-model codes")
        extra = set(shot) - {"asset_id", "observed_action"}
        if extra:
            raise ValueError("usable_shots may only include asset_id and observed_action")
    return data


def render_prompt(brief: dict[str, Any]) -> str:
    product_model = brief.get("product_model")
    if not isinstance(product_model, str) or not product_model.strip():
        raise ValueError("product_model required")
    return (
        "TikTok商品動画の台本ドラフトを1本だけ返す。説明文は付けない。\n"
        "要件:\n"
        "- 20案を内部比較し、実行可能な1案だけを選ぶ。ユーザーに案を選ばせない。\n"
        f"- 台詞の流れは {', '.join(NARRATIVE_ROLES)} の6段。省略・逆順禁止。\n"
        f"- CTAの台詞は完全一致で {CTA_TEXT}\n"
        "- 画面・音声に製品型番を出さない。\n"
        "- 各行は検証済み事実と usable_shots の観察内容だけで書く。推測しない。\n"
        "- 素材の SHA や in/out 秒は作らない。役割と台詞だけ返す。\n"
        f"- 内部の製品型番は {product_model}。台詞には書かない。\n"
        "返す形式: selected_concept、twenty_candidate_summary（20件）、"
        "dialogue（6件以上。各要素は cut_id, narrative_role, text）。\n"
        f"verified_facts={json.dumps(brief.get('verified_facts'), ensure_ascii=False)}\n"
        f"usable_shots={json.dumps(brief.get('usable_shots'), ensure_ascii=False)}\n"
    )


def self_test() -> int:
    checks: list[tuple[str, bool]] = []

    def check(name: str, ok: bool) -> None:
        checks.append((name, ok))
        if not ok:
            print(f"FAIL {name}", flush=True)

    good = {
        "schema": BRIEF_SCHEMA,
        "product_model": "AN-S182",
        "cta_text": CTA_TEXT,
        "verified_facts": ["仮眠が続かない"],
        "usable_shots": [{"asset_id": "asset-a", "observed_action": "shade opens"}],
    }
    prompt = render_prompt(good)
    check("cta-in-prompt", CTA_TEXT in prompt)
    check("six-roles", all(role in prompt for role in NARRATIVE_ROLES))
    check("no-secret", "AIza" not in prompt)
    try:
        load_brief(json.dumps({**good, "usable_shots": [{"asset_id": "a", "observed_action": "x", "sha256": "abc"}]}))
        check("reject-sha", False)
    except ValueError:
        check("reject-sha", True)
    try:
        load_brief('{"schema":"nope"}')
        check("reject-schema", False)
    except ValueError:
        check("reject-schema", True)
    if not all(ok for _, ok in checks):
        print("SELF-TEST FAILED: render_gemini_web_prompt", flush=True)
        return 1
    print("SELF-TEST PASSED: render_gemini_web_prompt")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brief", type=argparse.FileType("r", encoding="utf-8"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.brief is None:
        parser.error("--brief is required unless --self-test is used")
    try:
        brief = load_brief(args.brief.read())
        prompt = render_prompt(brief)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        payload = hold("HOLD_SCRIPT_INCOMPLETE", str(exc))
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    print(prompt, end="" if prompt.endswith("\n") else "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
