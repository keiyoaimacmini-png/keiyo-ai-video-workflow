#!/usr/bin/env python3
"""Draft a six-stage product-video script with Gemini 3.8 Flash.

Reads GEMINI_API_KEY or GOOGLE_API_KEY from the environment. Never prints,
logs, or writes the key. The returned dialogue is a draft: the host still
proves source ranges against real frames and builds the canonical payload.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any, Callable


BRIEF_SCHEMA = "product_video_gemini_script_brief.v1"
DRAFT_SCHEMA = "product_video_gemini_script_draft.v1"
MODEL_ID = "gemini-3.8-flash"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_ID}:generateContent"
HOLD_API = "HOLD_GEMINI_SCRIPT_API_UNAVAILABLE"
HOLD_SCRIPT = "HOLD_SCRIPT_INCOMPLETE"
NARRATIVE_ROLES = (
    "problem_or_hook",
    "product",
    "use_or_change",
    "result",
    "problem_resolution",
    "cta",
)
CTA_TEXT = "下からチェック！"
SECRET_RE = re.compile(r"(?i)(?:x-goog-api-key\s*[:=]\s*)[^\s\"']+|AIza[0-9A-Za-z_\-]{10,}")
FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)


HttpOpener = Callable[[urllib.request.Request, float], Any]


def redact(value: str) -> str:
    return SECRET_RE.sub("[redacted]", value)


def hold_payload(code: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": "HOLD", "hold": code}
    payload.update(extra)
    return payload


def api_key_from_env(environ: dict[str, str] | None = None) -> str | None:
    env = os.environ if environ is None else environ
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        value = env.get(name, "").strip()
        if value:
            return value
    return None


def load_brief(path_text: str) -> dict[str, Any]:
    data = json.loads(path_text)
    if not isinstance(data, dict) or data.get("schema") != BRIEF_SCHEMA:
        raise ValueError("brief schema mismatch")
    facts = data.get("verified_facts")
    shots = data.get("usable_shots")
    cta = data.get("cta_text")
    if not isinstance(facts, list) or not facts:
        raise ValueError("verified_facts required")
    if not isinstance(shots, list) or not shots:
        raise ValueError("usable_shots required")
    if cta != CTA_TEXT:
        raise ValueError("cta_text must be the frozen CTA")
    return data


def build_prompt(brief: dict[str, Any]) -> str:
    product_model = brief.get("product_model")
    return (
        "TikTok商品動画の台本ドラフトを1本だけJSONで返す。説明文は付けない。\n"
        "要件:\n"
        "- 20案を内部比較し、実行可能な1案だけを選ぶ。ユーザーに案を選ばせない。\n"
        f"- 台詞の流れは {', '.join(NARRATIVE_ROLES)} の6段。省略・逆順禁止。\n"
        f"- CTAの台詞は完全一致で {CTA_TEXT}\n"
        "- 画面・音声に製品型番を出さない。\n"
        "- 各行は検証済み事実と usable_shots の観察内容だけで書く。推測しない。\n"
        "- 素材の SHA や in/out 秒は作らない。役割と台詞だけ返す。\n"
        f"- 内部の製品型番は {product_model}。台詞には書かない。\n"
        "返すJSONのキー: selected_concept (string), twenty_candidate_summary "
        "(20件の短いstring配列), dialogue (6件以上の配列。"
        "各要素は cut_id, narrative_role, text)。\n"
        f"verified_facts={json.dumps(brief.get('verified_facts'), ensure_ascii=False)}\n"
        f"usable_shots={json.dumps(brief.get('usable_shots'), ensure_ascii=False)}\n"
    )


def extract_json_object(text: str) -> dict[str, Any]:
    candidate = text.strip()
    fenced = FENCE_RE.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()
    data = json.loads(candidate)
    if not isinstance(data, dict):
        raise ValueError("model output is not an object")
    return data


def validate_draft(data: dict[str, Any]) -> str | None:
    concept = data.get("selected_concept")
    summary = data.get("twenty_candidate_summary")
    dialogue = data.get("dialogue")
    if not isinstance(concept, str) or not concept.strip():
        return HOLD_SCRIPT
    if not isinstance(summary, list) or len(summary) != 20:
        return HOLD_SCRIPT
    if any(not isinstance(item, str) or not item.strip() for item in summary):
        return HOLD_SCRIPT
    if not isinstance(dialogue, list) or len(dialogue) < 6:
        return HOLD_SCRIPT
    roles: list[str] = []
    for row in dialogue:
        if not isinstance(row, dict):
            return HOLD_SCRIPT
        cut_id = row.get("cut_id")
        role = row.get("narrative_role")
        text = row.get("text")
        if not isinstance(cut_id, str) or not cut_id.strip():
            return HOLD_SCRIPT
        if role not in NARRATIVE_ROLES:
            return HOLD_SCRIPT
        if not isinstance(text, str) or not text.strip():
            return HOLD_SCRIPT
        if role == "cta" and text != CTA_TEXT:
            return HOLD_SCRIPT
        if re.search(r"AN-[A-Z0-9]{4,6}", text):
            return HOLD_SCRIPT
        roles.append(role)
    compressed: list[str] = []
    for role in roles:
        if not compressed or compressed[-1] != role:
            compressed.append(role)
    if compressed != list(NARRATIVE_ROLES):
        return HOLD_SCRIPT
    return None


def default_opener(request: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout)


def call_gemini(
    prompt: str,
    api_key: str,
    *,
    thinking_level: str = "medium",
    timeout: float = 120.0,
    opener: HttpOpener | None = None,
) -> dict[str, Any]:
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingLevel": thinking_level},
        },
    }
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    open_http = opener or default_opener
    try:
        with open_http(request, timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = redact(exc.read().decode("utf-8", errors="replace")[:500])
        return hold_payload(HOLD_API, reason=f"http {exc.code}", detail=detail)
    except urllib.error.URLError as exc:
        return hold_payload(HOLD_API, reason=redact(str(exc.reason)))
    except TimeoutError:
        return hold_payload(HOLD_API, reason="timeout")
    try:
        payload = json.loads(raw)
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        draft = extract_json_object(text)
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return hold_payload(HOLD_API, reason="unparseable model output")
    problem = validate_draft(draft)
    if problem:
        return hold_payload(problem, reason="draft failed six-stage or CTA checks")
    return {
        "status": "READY",
        "schema": DRAFT_SCHEMA,
        "model": MODEL_ID,
        "selected_concept": draft["selected_concept"],
        "twenty_candidate_summary": draft["twenty_candidate_summary"],
        "dialogue": draft["dialogue"],
    }


def draft_from_brief(
    brief: dict[str, Any],
    *,
    environ: dict[str, str] | None = None,
    opener: HttpOpener | None = None,
) -> dict[str, Any]:
    key = api_key_from_env(environ)
    if not key:
        return hold_payload(
            HOLD_API,
            reason="GEMINI_API_KEY or GOOGLE_API_KEY is missing from the environment",
        )
    try:
        prompt = build_prompt(brief)
    except (TypeError, ValueError) as exc:
        return hold_payload(HOLD_SCRIPT, reason=str(exc))
    return call_gemini(prompt, key, opener=opener)


def valid_fixture_draft() -> dict[str, Any]:
    summary = [f"案{index + 1}" for index in range(20)]
    dialogue = [
        {"cut_id": "cut-01", "narrative_role": "problem_or_hook", "text": "仮眠しても、すぐ目が覚める。"},
        {"cut_id": "cut-02", "narrative_role": "product", "text": "車内で、パッと開くサンシェード。"},
        {"cut_id": "cut-03", "narrative_role": "use_or_change", "text": "フロントガラスに押し込むだけ。"},
        {"cut_id": "cut-04", "narrative_role": "result", "text": "今度は、仮眠が続く。"},
        {"cut_id": "cut-05", "narrative_role": "problem_resolution", "text": "畳むと、細くなる。"},
        {"cut_id": "cut-06", "narrative_role": "cta", "text": CTA_TEXT},
    ]
    return {
        "selected_concept": "車内仮眠をサンシェードで続ける",
        "twenty_candidate_summary": summary,
        "dialogue": dialogue,
    }


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._raw = json.dumps(
            {"candidates": [{"content": {"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}}]}
        ).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def self_test() -> int:
    checks: list[tuple[str, bool]] = []

    def check(name: str, ok: bool) -> None:
        checks.append((name, ok))
        if not ok:
            print(f"FAIL {name}", flush=True)

    missing = draft_from_brief(
        {
            "schema": BRIEF_SCHEMA,
            "product_model": "AN-S182",
            "verified_facts": ["fact"],
            "usable_shots": [{"asset_id": "a", "observed_action": "open"}],
            "cta_text": CTA_TEXT,
        },
        environ={},
    )
    check("missing-key-hold", missing.get("hold") == HOLD_API)
    check("missing-key-no-secret", "AIza" not in json.dumps(missing))

    fixture = valid_fixture_draft()
    check("fixture-valid", validate_draft(fixture) is None)
    bad_cta = json.loads(json.dumps(fixture))
    bad_cta["dialogue"][-1]["text"] = "カートからチェック"
    check("bad-cta", validate_draft(bad_cta) == HOLD_SCRIPT)
    with_model = json.loads(json.dumps(fixture))
    with_model["dialogue"][0]["text"] = "AN-S182を見て"
    check("model-in-dialogue", validate_draft(with_model) == HOLD_SCRIPT)
    fenced = extract_json_object("```json\n" + json.dumps(fixture, ensure_ascii=False) + "\n```")
    check("fence-parse", fenced["selected_concept"] == fixture["selected_concept"])

    def opener(request: urllib.request.Request, timeout: float) -> _FakeResponse:
        check("timeout-passed", timeout >= 1)
        check("endpoint-model", MODEL_ID in request.full_url)
        header_blob = " ".join(f"{name} {value}" for name, value in request.header_items()).lower()
        check("key-header-present", "x-goog-api-key" in header_blob)
        body = json.loads(request.data.decode("utf-8"))
        thinking = body.get("generationConfig", {}).get("thinkingConfig", {})
        check("thinking-level", thinking.get("thinkingLevel") == "medium")
        return _FakeResponse(fixture)

    ready = draft_from_brief(
        {
            "schema": BRIEF_SCHEMA,
            "product_model": "AN-S182",
            "verified_facts": ["仮眠が続かない"],
            "usable_shots": [{"asset_id": "asset-a", "observed_action": "shade opens"}],
            "cta_text": CTA_TEXT,
        },
        environ={"GEMINI_API_KEY": "AIzaSyDummyTestKeyValue000"},
        opener=opener,
    )
    check("mock-ready", ready.get("status") == "READY")
    check("mock-model", ready.get("model") == MODEL_ID)
    check("redact-helper", redact("x-goog-api-key: AIzaSyDummyTestKeyValue000") == "[redacted]")

    if not all(ok for _, ok in checks):
        print("SELF-TEST FAILED: draft_script_with_gemini", flush=True)
        return 1
    print("SELF-TEST PASSED: draft_script_with_gemini")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brief", type=argparse.FileType("r", encoding="utf-8"))
    parser.add_argument("--output")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.brief is None:
        parser.error("--brief is required unless --self-test is used")
    try:
        brief = load_brief(args.brief.read())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        payload = hold_payload(HOLD_SCRIPT, reason=str(exc))
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    payload = draft_from_brief(brief)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        path = args.output
        if os.path.exists(path) or os.path.islink(path):
            print("refusing to overwrite output", file=sys.stderr)
            return 2
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    return 0 if payload.get("status") == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
