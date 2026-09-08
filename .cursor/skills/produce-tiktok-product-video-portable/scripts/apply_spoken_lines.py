#!/usr/bin/env python3
"""Rebind spoken lines onto an existing package and payload without a rewrite.

Use this after a script-review correction. Do not paste a fresh 200-line hash
script. Source SHA and in/out stay as they are. Dialogue-only changes keep the
same cut ranges.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


CHARS_PER_SECOND = 5.5
JST = timezone(timedelta(hours=9), name="Asia/Tokyo")
HOLD_SCRIPT = "HOLD_SCRIPT_INCOMPLETE"

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
from validate_product_video_payload import (  # noqa: E402
    digest,
    errors_for,
    expected_hashes,
    load_trusted_product_settings,
)


def hold(code: str, reason: str) -> dict[str, str]:
    return {"status": "HOLD", "hold": code, "reason": reason}


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    hasher.update(path.read_bytes())
    return hasher.hexdigest()


def now_jst() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def estimated_read_seconds(text: str) -> float:
    return round(len(text) / CHARS_PER_SECOND, 3)


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a JSON object")
    return data


def load_lines(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        lines = {str(key): str(value) for key, value in data.items()}
    elif isinstance(data, list):
        lines = {}
        for row in data:
            if not isinstance(row, dict):
                raise ValueError("lines list items must be objects")
            cut_id = row.get("cut_id")
            text = row.get("text") if "text" in row else row.get("dialogue")
            if not isinstance(cut_id, str) or not isinstance(text, str):
                raise ValueError("lines need cut_id and text")
            lines[cut_id] = text
    else:
        raise ValueError("lines must be an object or a list")
    if not lines:
        raise ValueError("lines are empty")
    return lines


def refresh_payload_hashes(payload: dict[str, Any]) -> None:
    payload["component_hashes"] = {
        "manifest_sha256": digest(payload["manifest"]),
        "favorite_context_sha256": digest(
            {"goal_axis": payload["goal_axis"], "patterns": payload["patterns"]}
        ),
        "script_sha256": digest(payload["script"]),
        "cuts_sha256": digest(payload["cuts"]),
        "captions_sha256": digest(payload["captions"]),
        "tts_sha256": digest(payload["tts"]),
    }
    production_hash, visible_hash = expected_hashes(payload)
    payload["integrity"] = {
        "production_payload_sha256": production_hash,
        "visible_content_sha256": visible_hash,
    }
    for gate in payload.get("approval_gates", {}).values():
        if isinstance(gate, dict):
            gate["bound_production_payload_sha256"] = production_hash
            gate["bound_visible_content_sha256"] = visible_hash


def apply_lines(
    package: dict[str, Any],
    payload: dict[str, Any],
    lines: dict[str, str],
    *,
    created_at: str,
    selected_concept: str | None,
    sync_post_set: bool,
    refresh_hashes: bool = True,
) -> dict[str, Any]:
    expected_ids = [row["cut_id"] for row in payload.get("script", []) if isinstance(row, dict)]
    if list(lines) != expected_ids and set(lines) != set(expected_ids):
        missing = [cut_id for cut_id in expected_ids if cut_id not in lines]
        extra = [cut_id for cut_id in lines if cut_id not in expected_ids]
        return hold(
            HOLD_SCRIPT,
            f"line cut_ids must match payload script; missing={missing} extra={extra}",
        )
    overflows: list[str] = []
    for row in package.get("dialogue", []):
        if not isinstance(row, dict):
            continue
        cut_id = row.get("cut_id")
        if cut_id not in lines:
            continue
        text = lines[cut_id]
        estimate = estimated_read_seconds(text)
        duration = row.get("cut_duration")
        if not isinstance(duration, (int, float)) or estimate > float(duration):
            overflows.append(f"{cut_id}:{estimate}>{duration}")
        row["dialogue"] = text
        row["unicode_codepoint_count"] = len(text)
        row["estimated_read_seconds"] = estimate
    if overflows:
        return hold(HOLD_SCRIPT, "spoken estimate exceeds cut_duration: " + ", ".join(overflows))

    package["created_at"] = created_at
    if selected_concept:
        package["selected_concept"] = selected_concept

    payload["created_at"] = created_at
    for rec in payload.get("script", []):
        if isinstance(rec, dict) and rec.get("cut_id") in lines:
            rec["dialogue"] = lines[rec["cut_id"]]
    for rec in payload.get("captions", []):
        if isinstance(rec, dict) and rec.get("cut_id") in lines:
            rec["text"] = lines[rec["cut_id"]]
    for rec in payload.get("tts", []):
        if isinstance(rec, dict) and rec.get("cut_id") in lines:
            rec["text"] = lines[rec["cut_id"]]
    receipt = payload.get("script_review_receipt")
    if isinstance(receipt, dict):
        if selected_concept:
            receipt["selected_concept"] = selected_concept
        for rec in receipt.get("cuts", []):
            if not isinstance(rec, dict) or rec.get("cut_id") not in lines:
                continue
            text = lines[rec["cut_id"]]
            rec["dialogue"] = text
            rec["unicode_codepoint_count"] = len(text)
            rec["estimated_read_seconds"] = estimated_read_seconds(text)
    if sync_post_set and isinstance(payload.get("post_set"), dict):
        ordered = [lines[cut_id] for cut_id in expected_ids]
        payload["post_set"]["title"] = ordered[0]
        payload["post_set"]["post_text"] = "".join(ordered)
        payload["post_set"]["pinned_comment"] = ordered[-1]
    if selected_concept:
        payload["script_review_receipt"]["selected_concept"] = selected_concept
    if refresh_hashes:
        refresh_payload_hashes(payload)
    return {"status": "OK"}


def craft_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    dialogue = []
    for rec in payload.get("script", []):
        if not isinstance(rec, dict):
            continue
        dialogue.append(
            {
                "cut_id": rec.get("cut_id"),
                "narrative_role": rec.get("narrative_role"),
                "text": rec.get("dialogue"),
            }
        )
    return {"schema": "product_video_craft_script.v1", "dialogue": dialogue}


def write_json(path: Path, data: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def bind_state(state_path: Path, package_path: Path, payload_path: Path) -> None:
    state = load_json(state_path)
    package_sha = sha256_file(package_path)
    payload_sha = sha256_file(payload_path)
    artifacts = state.setdefault("artifacts", {})
    artifacts["script_package"] = {
        "path": package_path.name,
        "sha256": package_sha,
    }
    artifacts["production_payload"] = {
        "path": payload_path.name,
        "sha256": payload_sha,
    }
    receipts = state.get("stage_receipts")
    if isinstance(receipts, list) and receipts:
        receipts[0]["artifact_sha256"] = package_sha
        receipts[0]["observed_at"] = now_jst()
    if isinstance(receipts, list) and len(receipts) > 1:
        receipts[1]["artifact_sha256"] = payload_sha
        receipts[1]["observed_at"] = now_jst()
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def self_test() -> int:
    package = {
        "dialogue": [
            {
                "cut_id": "hot-cabin",
                "dialogue": "old",
                "cut_duration": 4.2,
                "unicode_codepoint_count": 3,
                "estimated_read_seconds": 0.545,
            }
        ]
    }
    payload = {
        "manifest": [],
        "goal_axis": "watch_continuation",
        "patterns": [],
        "script": [{"cut_id": "hot-cabin", "dialogue": "old", "narrative_role": "problem_or_hook"}],
        "captions": [{"cut_id": "hot-cabin", "text": "old"}],
        "tts": [{"cut_id": "hot-cabin", "text": "old"}],
        "cuts": [],
        "script_review_receipt": {
            "cuts": [
                {
                    "cut_id": "hot-cabin",
                    "dialogue": "old",
                    "unicode_codepoint_count": 3,
                    "estimated_read_seconds": 0.545,
                    "cut_duration": 4.2,
                }
            ]
        },
        "approval_gates": {"edit": {}},
        "post_set": {"title": "old", "post_text": "old", "pinned_comment": "x"},
    }
    result = apply_lines(
        package,
        payload,
        {"hot-cabin": "昼の車内って熱いよね？"},
        created_at="2026-09-07T20:00:00+09:00",
        selected_concept=None,
        sync_post_set=True,
        refresh_hashes=False,
    )
    ok = result.get("status") == "OK"
    ok = ok and package["dialogue"][0]["dialogue"] == "昼の車内って熱いよね？"
    ok = ok and payload["captions"][0]["text"] == "昼の車内って熱いよね？"
    overflow = apply_lines(
        deepcopy(package),
        deepcopy(payload),
        {"hot-cabin": "あ" * 80},
        created_at="2026-09-07T20:00:00+09:00",
        selected_concept=None,
        sync_post_set=False,
        refresh_hashes=False,
    )
    if not ok or overflow.get("hold") != HOLD_SCRIPT:
        print("SELF-TEST FAILED: apply_spoken_lines", flush=True)
        return 1
    print("SELF-TEST PASSED: apply_spoken_lines")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", type=Path)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--lines", type=Path)
    parser.add_argument("--output-payload", type=Path)
    parser.add_argument("--output-package", type=Path)
    parser.add_argument("--output-craft", type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--settings-root", type=Path, default=Path("."))
    parser.add_argument("--selected-concept")
    parser.add_argument("--sync-post-set", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    required = [args.payload, args.package, args.lines, args.output_payload, args.output_package]
    if any(item is None for item in required):
        parser.error("--payload --package --lines --output-payload --output-package are required")
    try:
        package = load_json(args.package)
        payload = load_json(args.payload)
        lines = load_lines(args.lines)
        result = apply_lines(
            package,
            payload,
            lines,
            created_at=now_jst(),
            selected_concept=args.selected_concept,
            sync_post_set=args.sync_post_set,
        )
        if result.get("status") != "OK":
            emit(result)
            return 2
        model = payload.get("product_info", {}).get("product_model") if isinstance(payload.get("product_info"), dict) else None
        errors = errors_for(payload, load_trusted_product_settings(str(args.settings_root), model))
        if errors:
            emit({"status": "HOLD", "hold": HOLD_SCRIPT, "errors": errors})
            return 2
        write_json(args.output_package, package)
        write_json(args.output_payload, payload)
        if args.output_craft is not None:
            write_json(args.output_craft, craft_from_payload(payload))
        if args.state is not None:
            bind_state(args.state, args.output_package, args.output_payload)
        emit(
            {
                "status": "OK",
                "package": str(args.output_package),
                "payload": str(args.output_payload),
                "package_sha256": sha256_file(args.output_package),
                "payload_sha256": sha256_file(args.output_payload),
                "visible_content_sha256": payload["integrity"]["visible_content_sha256"],
            }
        )
        return 0
    except FileExistsError as exc:
        emit(hold(HOLD_SCRIPT, str(exc)))
        return 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit(hold(HOLD_SCRIPT, str(exc)))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
