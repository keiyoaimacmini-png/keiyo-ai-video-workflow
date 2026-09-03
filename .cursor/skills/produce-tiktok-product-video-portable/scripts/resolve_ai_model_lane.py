#!/usr/bin/env python3
"""Classify the current assistant model into script vs post-script lanes.

This does not change a Cloud Agent parent model. It only names the required
lane, HOLD codes, and the copy-paste Grok 4.6 continuation prompt.
Product model strings such as AN-S182 are out of scope.
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Any


HOLD_IDENTITY = "HOLD_AI_MODEL_IDENTITY_UNVERIFIED"
HOLD_SCRIPT = "HOLD_AI_MODEL_SCRIPT_LANE_REQUIRED"
HOLD_HANDOFF = "HOLD_AI_MODEL_HANDOFF_REQUIRED"

LANE_SCRIPT = "script"
LANE_POST_SCRIPT = "post_script"
LANE_UNKNOWN = "unknown"

SCRIPT_DISPLAY = "Gemini 3.8 Flash"
POST_SCRIPT_DISPLAY = "Grok 4.6"
SCRIPT_MODEL_ID = "gemini-3.8-flash"
POST_SCRIPT_MODEL_ID = "grok-4.6"

SCRIPT_STAGES = {"PREFLIGHT", "SCRIPT_PREPARED"}
POST_SCRIPT_STAGES = {
    "ROUGH_EDIT",
    "ROUGH_REVIEW",
    "FINISHING",
    "FINAL_QA",
    "FINAL_REVIEW",
    "EXPORT_AND_DELIVERY",
    "COMPLETE",
}
EITHER_STAGES = {"SCRIPT_REVIEW"}
ALL_STAGES = SCRIPT_STAGES | EITHER_STAGES | POST_SCRIPT_STAGES

TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(value: str) -> list[str]:
    return TOKEN_RE.findall(value.strip().lower())


def classify_model(model_name: str | None) -> dict[str, Any]:
    if not isinstance(model_name, str) or not model_name.strip():
        return {
            "status": "HOLD",
            "hold": HOLD_IDENTITY,
            "lane": LANE_UNKNOWN,
            "family": None,
            "display_name": None,
            "observed_model": model_name,
        }

    tokens = tokenize(model_name)
    joined = "-".join(tokens)
    has_gemini = "gemini" in tokens
    has_grok = "grok" in tokens
    has_flash = "flash" in tokens
    has_38 = (
        ("3" in tokens and "8" in tokens)
        or "38" in tokens
        or "3-8" in joined
        or joined.endswith("3-8")
        or "3-8-" in joined
        or "-3-8" in joined
    )
    has_46 = (
        ("4" in tokens and "6" in tokens)
        or "46" in tokens
        or "4-6" in joined
        or "-4-6" in joined
        or "4-6-" in joined
    )
    has_45 = (
        ("4" in tokens and "5" in tokens and not has_46)
        or "45" in tokens
        or "4-5" in joined
    )
    has_37 = ("3" in tokens and "7" in tokens) or "37" in tokens or "3-7" in joined

    if has_gemini and has_flash and has_38 and not has_37:
        return {
            "status": "READY",
            "hold": None,
            "lane": LANE_SCRIPT,
            "family": SCRIPT_MODEL_ID,
            "display_name": SCRIPT_DISPLAY,
            "observed_model": model_name.strip(),
        }
    if has_grok and has_46 and not has_45:
        return {
            "status": "READY",
            "hold": None,
            "lane": LANE_POST_SCRIPT,
            "family": POST_SCRIPT_MODEL_ID,
            "display_name": POST_SCRIPT_DISPLAY,
            "observed_model": model_name.strip(),
        }
    return {
        "status": "HOLD",
        "hold": HOLD_IDENTITY,
        "lane": LANE_UNKNOWN,
        "family": None,
        "display_name": None,
        "observed_model": model_name.strip(),
        "reason": "model is neither Gemini 3.8 Flash nor Grok 4.6",
    }


def required_lane_for_stage(stage: str) -> str | None:
    if stage in SCRIPT_STAGES:
        return LANE_SCRIPT
    if stage in POST_SCRIPT_STAGES:
        return LANE_POST_SCRIPT
    if stage in EITHER_STAGES:
        return None
    raise ValueError(f"unknown stage: {stage}")


def evaluate_lane(model_name: str | None, stage: str | None, *, entering_rough_edit: bool = False) -> dict[str, Any]:
    classified = classify_model(model_name)
    if entering_rough_edit:
        required = LANE_POST_SCRIPT
    elif stage is None:
        required = None
    else:
        required = required_lane_for_stage(stage)

    payload = dict(classified)
    payload["stage"] = stage
    payload["required_lane"] = required
    payload["script_display"] = SCRIPT_DISPLAY
    payload["post_script_display"] = POST_SCRIPT_DISPLAY

    if classified["lane"] == LANE_UNKNOWN:
        return payload
    if required is None:
        payload["status"] = "READY"
        payload["hold"] = None
        return payload
    if classified["lane"] == required:
        payload["status"] = "READY"
        payload["hold"] = None
        return payload
    if required == LANE_SCRIPT:
        payload["status"] = "HOLD"
        payload["hold"] = HOLD_SCRIPT
        payload["reason"] = "script stages must run on Gemini 3.8 Flash"
        return payload
    payload["status"] = "HOLD"
    payload["hold"] = HOLD_HANDOFF
    payload["reason"] = "stages after 台本OK must run on Grok 4.6"
    return payload


def relative_posix(path: str) -> str:
    value = path.strip().replace("\\", "/")
    if value.startswith("/") or re.match(r"^[A-Za-z]:/", value):
        raise ValueError("path must be a safe POSIX relative path")
    parts = [part for part in value.split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        raise ValueError("path must be a safe POSIX relative path")
    return "/".join(parts)


def handoff_card(*, case_id: str, product_model: str, task_root: str, script_approved: bool) -> str:
    root = relative_posix(task_root)
    state_path = f"{root}/product-video-workflow-state.v1.json"
    if script_approved:
        next_step = (
            "台本OKは記録済みです。新規案件は作らず、ROUGH_EDIT から続けてください。"
            "台本OKを再度求めないでください。"
        )
    else:
        next_step = (
            "Checkpoint 1 の台本を確認し、問題なければ exact `台本OK` だけ送ってから粗編集に進んでください。"
        )
    continuation = f"""/produce-tiktok-product-video-portable

この案件の続きです。新規案件は作らないでください。
製品型番は{product_model}です。
case IDは{case_id}です。
task rootは{root}です。
workflow stateは{state_path}です。
このセッションのモデルはGrok 4.6のまま、粗編集以降を実行してください。
{next_step}"""
    return f"""## モデル切替（第四の承認ではありません）

通常確認はこれまでどおり exact `台本OK` だけです。

- 台本生成（PREFLIGHT〜Checkpoint 1）: **{SCRIPT_DISPLAY}**（`{SCRIPT_MODEL_ID}`）
- 粗編集以降: **{POST_SCRIPT_DISPLAY}**（`{POST_SCRIPT_MODEL_ID}`）

Cursor Cloud Agentの親モデルは実行中に変わりません。Desktopなら次のメッセージの前にモデルピッカーを {POST_SCRIPT_DISPLAY} へ切り替えてください。Cloud Agentなら {POST_SCRIPT_DISPLAY} の新しいAgentを起こし、下の続きプロンプトを渡してください。Gemini 3.8 Flashのまま粗編集・CapCut操作へ進んではいけません。

```text
{continuation.strip()}
```
"""


def self_test() -> int:
    checks: list[tuple[str, bool]] = []

    def check(name: str, ok: bool) -> None:
        checks.append((name, ok))
        if not ok:
            raise AssertionError(name)

    gemini = classify_model("Gemini 3.8 Flash")
    check("gemini-display", gemini["lane"] == LANE_SCRIPT)
    check("gemini-id", classify_model("gemini-3.8-flash")["lane"] == LANE_SCRIPT)
    check("gemini-effort", classify_model("gemini-3.8-flash-high")["lane"] == LANE_SCRIPT)
    grok = classify_model("cursor-grok-4.6-xhigh")
    check("grok-slug", grok["lane"] == LANE_POST_SCRIPT)
    check("grok-display", classify_model("Grok 4.6")["lane"] == LANE_POST_SCRIPT)
    check("grok-fast", classify_model("cursor-grok-4.6-high-fast")["lane"] == LANE_POST_SCRIPT)
    check("reject-3-7", classify_model("gemini-3.7-flash")["lane"] == LANE_UNKNOWN)
    check("reject-3-1", classify_model("Gemini 3.1 Pro")["lane"] == LANE_UNKNOWN)
    check("reject-4-5", classify_model("Grok 4.5")["lane"] == LANE_UNKNOWN)
    check("reject-empty", classify_model("  ")["hold"] == HOLD_IDENTITY)
    check("preflight-gemini", evaluate_lane("gemini-3.8-flash", "PREFLIGHT")["status"] == "READY")
    preflight_grok = evaluate_lane("grok-4.6", "PREFLIGHT")
    check("preflight-grok-hold", preflight_grok["hold"] == HOLD_SCRIPT)
    check("review-either-gemini", evaluate_lane("gemini-3.8-flash", "SCRIPT_REVIEW")["status"] == "READY")
    check("review-either-grok", evaluate_lane("cursor-grok-4.6-xhigh", "SCRIPT_REVIEW")["status"] == "READY")
    gemini_edit = evaluate_lane("gemini-3.8-flash", "ROUGH_EDIT")
    check("rough-gemini-hold", gemini_edit["hold"] == HOLD_HANDOFF)
    check("rough-grok-ready", evaluate_lane("Grok 4.6", "ROUGH_EDIT")["status"] == "READY")
    entering = evaluate_lane("gemini-3.8-flash", "SCRIPT_REVIEW", entering_rough_edit=True)
    check("entering-rough-from-gemini", entering["hold"] == HOLD_HANDOFF)
    check("entering-rough-from-grok", evaluate_lane("grok-4.6", "SCRIPT_REVIEW", entering_rough_edit=True)["status"] == "READY")
    card = handoff_card(
        case_id="AN-S182-example-001",
        product_model="AN-S182",
        task_root="outputs/AN-S182-example-001",
        script_approved=True,
    )
    check("card-has-skill", "/produce-tiktok-product-video-portable" in card)
    check("card-relative", "outputs/AN-S182-example-001/product-video-workflow-state.v1.json" in card)
    check("card-no-abs", "/Users/" not in card and "/home/" not in card)
    try:
        relative_posix("/tmp/case")
        check("reject-absolute", False)
    except ValueError:
        check("reject-absolute", True)
    if not all(ok for _, ok in checks):
        print("SELF-TEST FAILED: resolve_ai_model_lane", flush=True)
        return 1
    print("SELF-TEST PASSED: resolve_ai_model_lane")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="Current assistant model name or id")
    parser.add_argument("--stage", choices=sorted(ALL_STAGES))
    parser.add_argument("--entering-rough-edit", action="store_true")
    parser.add_argument("--print-handoff-card", action="store_true")
    parser.add_argument("--case-id")
    parser.add_argument("--product-model")
    parser.add_argument("--task-root")
    parser.add_argument("--script-approved", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.print_handoff_card:
        if not args.case_id or not args.product_model or not args.task_root:
            parser.error("--print-handoff-card requires --case-id, --product-model, and --task-root")
        print(
            handoff_card(
                case_id=args.case_id,
                product_model=args.product_model,
                task_root=args.task_root,
                script_approved=args.script_approved,
            )
        )
        return 0
    payload = evaluate_lane(args.model, args.stage, entering_rough_edit=args.entering_rough_edit)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("status") == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
