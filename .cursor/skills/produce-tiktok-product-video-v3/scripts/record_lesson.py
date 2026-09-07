#!/usr/bin/env python3
"""Record a product-video v3 lesson. Quality activates; safety stays pending."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lessons import (
    ID_RE,
    LESSON_SCHEMA,
    SURFACES,
    active_dir,
    dump,
    load_json,
    pending_dir,
    validate_lesson,
)


def slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if ID_RE.fullmatch(text) is None:
        raise ValueError("defect/id must slug to a lowercase hyphen id")
    return text


def read_pair(path: Path | None, raw: str | None) -> dict[str, Any] | None:
    if path is None and raw is None:
        return None
    if path is not None and raw is not None:
        raise ValueError("use file or inline JSON, not both")
    data = load_json(path) if path is not None else json.loads(raw or "")
    if not isinstance(data, dict) or not data:
        raise ValueError("bad/good must be a non-empty object")
    return data


def write_lesson(path: Path, lesson: dict[str, Any], replace: bool) -> None:
    errors = validate_lesson(lesson)
    if errors:
        raise ValueError("; ".join(errors))
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not replace:
        raise ValueError(f"refusing to overwrite {path}")
    path.write_text(dump(lesson), encoding="utf-8")


def record_quality(args: argparse.Namespace) -> dict[str, Any]:
    lesson_id = args.id or slug(args.defect.replace("_", "-"))
    bad = read_pair(args.bad_file, args.bad_json)
    good = read_pair(args.good_file, args.good_json)
    if bad is None or good is None:
        raise ValueError("quality lessons require --bad-file/--bad-json and --good-file/--good-json")
    gate = json.loads(args.gate_json) if args.gate_json else default_gate(args.surface, bad, good)
    if not isinstance(gate, dict):
        raise ValueError("gate must be a JSON object")
    models = list(args.product_model or [])
    lesson = {
        "schema": LESSON_SCHEMA,
        "id": lesson_id,
        "surface": args.surface,
        "defect": args.defect,
        "auto": True,
        "status": "active",
        "product_models": models,
        "bad": bad,
        "good": good,
        "gate": gate,
    }
    if args.note:
        lesson["note"] = args.note
    dest = active_dir(args.project_root, args.surface) / f"{lesson_id}.json"
    write_lesson(dest, lesson, args.replace)
    return {"status": "active", "path": dest.as_posix(), "lesson": lesson}


def default_gate(surface: str, bad: dict[str, Any], good: dict[str, Any]) -> dict[str, Any]:
    if surface != "script":
        return {"kind": "artifact_flag", "fail_if_true": [bad.get("defect") or "unspecified"]}
    hook = str(bad.get("hook") or "")
    resolution = str(bad.get("resolution") or "")
    good_resolution = str(good.get("resolution") or "")
    fail_tokens = [token for token in (resolution,) if token]
    pass_tokens = [token for token in (good_resolution,) if token]
    return {
        "kind": "text_pair",
        "when_hook_contains": [hook] if hook else [],
        "fail_if_resolution_contains": fail_tokens,
        "pass_if_resolution_contains_any": pass_tokens,
    }


def record_safety(args: argparse.Namespace) -> dict[str, Any]:
    if not args.note:
        raise ValueError("safety lessons require --note describing the safety-engine change")
    lesson_id = args.id or slug(args.defect.replace("_", "-"))
    lesson = {
        "schema": LESSON_SCHEMA,
        "id": lesson_id,
        "surface": args.surface,
        "defect": args.defect,
        "auto": False,
        "status": "pending",
        "product_models": list(args.product_model or []),
        "note": args.note,
    }
    dest = pending_dir(args.project_root) / f"{lesson_id}.json"
    write_lesson(dest, lesson, args.replace)
    return {
        "status": "pending",
        "path": dest.as_posix(),
        "lesson": lesson,
        "message": "Safety lesson is pending. Not applied to the portable skill. Promote only with --i-confirm-safety-promote.",
    }


def promote_safety(project_root: Path, lesson_id: str) -> dict[str, Any]:
    path = pending_dir(project_root) / f"{lesson_id}.json"
    if not path.is_file():
        raise ValueError(f"pending safety lesson not found: {lesson_id}")
    lesson = load_json(path)
    if lesson.get("auto") is not False:
        raise ValueError("refusing to promote a quality lesson through the safety path")
    lesson["status"] = "acknowledged"
    errors = validate_lesson(lesson)
    if errors:
        raise ValueError("; ".join(errors))
    path.write_text(dump(lesson), encoding="utf-8")
    return {
        "status": "acknowledged",
        "path": path.as_posix(),
        "lesson": lesson,
        "message": "Safety lesson acknowledged only. Portable skill files were not edited.",
    }


def self_test() -> int:
    checks: list[tuple[str, bool]] = []

    def check(name: str, ok: bool) -> None:
        checks.append((name, ok))
        if not ok:
            print(f"FAIL {name}", flush=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        quality = record_quality(
            argparse.Namespace(
                project_root=root,
                surface="script",
                defect="hook_closed_by_result_looks",
                id=None,
                bad_file=None,
                good_file=None,
                bad_json=json.dumps({"hook": "車の中、暑すぎない？", "resolution": "正面からの日差しが入ってこない。"}, ensure_ascii=False),
                good_json=json.dumps({"hook": "車の中、暑すぎない？", "resolution": "これで車内の暑さをしのげる。"}, ensure_ascii=False),
                gate_json=None,
                product_model=None,
                note="seed",
                replace=False,
            )
        )
        check("quality-active", quality["status"] == "active")
        check("quality-path", Path(quality["path"]).is_file())
        from lessons import load_active_lessons

        loaded = load_active_lessons(root, "script", "AN-S182")
        check("load-quality", len(loaded) == 1 and loaded[0]["defect"] == "hook_closed_by_result_looks")
        safety = record_safety(
            argparse.Namespace(
                project_root=root,
                surface="script",
                defect="add_fourth_checkpoint",
                id=None,
                note="would add a fourth checkpoint",
                product_model=None,
                replace=False,
            )
        )
        check("safety-pending", safety["status"] == "pending")
        check("safety-not-active", load_active_lessons(root, "script")[0]["id"] == quality["lesson"]["id"])
        promoted = promote_safety(root, safety["lesson"]["id"])
        check("safety-ack", promoted["status"] == "acknowledged")
        check("safety-still-excluded", all(item["auto"] is True for item in load_active_lessons(root)))
    if not all(ok for _, ok in checks):
        print("SELF-TEST FAILED: record_lesson", flush=True)
        return 1
    print("SELF-TEST PASSED: record_lesson")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=False)
    parser.add_argument("--surface", choices=SURFACES)
    parser.add_argument("--defect")
    parser.add_argument("--id")
    parser.add_argument("--bad-file", type=Path)
    parser.add_argument("--good-file", type=Path)
    parser.add_argument("--bad-json")
    parser.add_argument("--good-json")
    parser.add_argument("--gate-json")
    parser.add_argument("--product-model", action="append")
    parser.add_argument("--note")
    parser.add_argument("--safety", action="store_true")
    parser.add_argument("--promote-id")
    parser.add_argument("--i-confirm-safety-promote", action="store_true")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.project_root is None:
        parser.error("--project-root is required unless --self-test is used")
    args.project_root = args.project_root.resolve()
    try:
        if args.promote_id:
            if not args.i_confirm_safety_promote:
                raise ValueError("promoting a safety lesson requires --i-confirm-safety-promote")
            result = promote_safety(args.project_root, args.promote_id)
        else:
            if not args.surface or not args.defect:
                parser.error("--surface and --defect are required to record a lesson")
            result = record_safety(args) if args.safety else record_quality(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(dump({"status": "HOLD", "hold": "HOLD_CRAFT_QUALITY", "reason": str(exc)}), end="")
        return 2
    print(dump(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
