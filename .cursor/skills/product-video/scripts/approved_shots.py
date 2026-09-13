#!/usr/bin/env python3
"""Product-level history of shots adopted on a completed timeline.

Lightweight reuse only. No AI scoring, no library-wide analysis, no new HOLDs.
Source videos are never modified. Completed exports are never stored.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from constants import PERSISTENT_APPROVED_SHOTS_RELATIVE, PERSISTENT_SHARED_INPUT_RELATIVE
from paths import case_root, emit
from workflow_state import atomic_write, now_iso

SCHEMA = "product_video_approved_shot_history.v1"
MAX_SHOTS = 200
TOKEN_SPLIT = re.compile(r"[、。！？!?,.・/\s]+")


def history_dir(project_root: Path) -> Path:
    return project_root / Path(*Path(PERSISTENT_APPROVED_SHOTS_RELATIVE).parts)


def history_path(project_root: Path, product_model: str) -> Path:
    return history_dir(project_root) / f"{product_model}.v1.json"


def empty_history(product_model: str) -> dict[str, Any]:
    return {"schema": SCHEMA, "product_model": product_model, "shots": []}


def load_history(project_root: Path, product_model: str) -> dict[str, Any]:
    path = history_path(project_root, product_model)
    if not path.is_file():
        return empty_history(product_model)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_history(product_model)
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return empty_history(product_model)
    if data.get("product_model") != product_model:
        return empty_history(product_model)
    shots = data.get("shots")
    if not isinstance(shots, list):
        data["shots"] = []
    return data


def save_history(project_root: Path, data: dict[str, Any]) -> Path:
    product_model = str(data["product_model"])
    path = history_path(project_root, product_model)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return path


def simple_tags(situation: str, extra: list[str] | None = None) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        text = (value or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        tags.append(text)

    for item in extra or []:
        add(str(item))
    situation_text = (situation or "").strip()
    if situation_text:
        add(situation_text)
        for part in TOKEN_SPLIT.split(situation_text):
            if len(part) >= 2:
                add(part)
    return tags


def is_source_material(source: str | None) -> bool:
    if not isinstance(source, str) or not source.strip():
        return False
    posix = source.replace("\\", "/").lstrip("./")
    if "AI作成" in posix:
        return False
    if posix.startswith("outputs/") or "/outputs/" in posix:
        return False
    if posix.startswith(PERSISTENT_SHARED_INPUT_RELATIVE):
        return True
    return not posix.endswith((".mp4", ".mov", ".m4v")) or "product-video-inputs" in posix


def shot_key(shot: dict[str, Any]) -> tuple[Any, ...]:
    return (
        shot.get("source"),
        shot.get("in_sec"),
        shot.get("out_sec"),
        shot.get("line"),
    )


def history_match_score(shot: dict[str, Any], line: str, situation: str) -> int:
    line_text = (line or "").strip()
    situation_text = (situation or "").strip()
    score = 0
    if (shot.get("line") or "").strip() == line_text and line_text:
        score += 4
    if (shot.get("situation") or "").strip() == situation_text and situation_text:
        score += 3
    hay = f"{line_text}\n{situation_text}"
    for tag in shot.get("semantic_tags") or []:
        text = str(tag).strip()
        if len(text) >= 4 and text in hay:
            score += 1
            break
    return score


def candidate_from_history(
    shot: dict[str, Any],
    *,
    line: str,
    situation: str,
    duration_seconds: float,
) -> dict[str, Any]:
    return {
        "semantic_valid": True,
        "supported_line": line,
        "situation": shot.get("situation") or situation,
        "scenario_tags": list(shot.get("semantic_tags") or []),
        "source": shot.get("source"),
        "in_sec": shot.get("in_sec"),
        "out_sec": shot.get("out_sec"),
        "visual": dict(shot.get("visual") or {}),
        "material_id": shot.get("source"),
        "from_approved_history": True,
        "target_duration_seconds": float(duration_seconds),
        "line": line,
        "intended_scenario": situation,
    }


def matching_history_shots(
    history: dict[str, Any] | None,
    *,
    line: str,
    situation: str,
) -> list[dict[str, Any]]:
    shots = (history or {}).get("shots") if isinstance(history, dict) else None
    if not isinstance(shots, list):
        return []
    ranked = []
    for shot in shots:
        if not isinstance(shot, dict) or not is_source_material(shot.get("source")):
            continue
        score = history_match_score(shot, line, situation)
        if score <= 0:
            continue
        ranked.append((score, shot))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [shot for _score, shot in ranked]


def normalize_shot(
    raw: dict[str, Any],
    *,
    product_model: str,
    case_id: str,
    line: str,
    situation: str,
) -> dict[str, Any] | None:
    source = raw.get("source") or raw.get("path")
    if not is_source_material(source if isinstance(source, str) else None):
        return None
    in_sec = raw.get("in_sec")
    if in_sec is None:
        in_sec = raw.get("source_in")
    out_sec = raw.get("out_sec")
    if out_sec is None:
        out_sec = raw.get("source_out")
    tags = raw.get("semantic_tags") or raw.get("scenario_tags") or []
    if not isinstance(tags, list):
        tags = []
    return {
        "product_model": product_model,
        "source": str(source),
        "in_sec": in_sec,
        "out_sec": out_sec,
        "line": line,
        "situation": situation,
        "semantic_tags": simple_tags(situation, [str(item) for item in tags]),
        "case_id": case_id,
        "visual": dict(raw.get("visual") or {}),
        "recorded_at": now_iso(),
    }


def record_shots(
    project_root: Path,
    product_model: str,
    case_id: str,
    adopted: list[dict[str, Any]],
) -> dict[str, Any]:
    history = load_history(project_root, product_model)
    by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    ordered: list[dict[str, Any]] = []
    for shot in history.get("shots") or []:
        if not isinstance(shot, dict):
            continue
        key = shot_key(shot)
        by_key[key] = shot
        ordered.append(shot)
    added = 0
    for raw in adopted:
        if not isinstance(raw, dict):
            continue
        line = str(raw.get("line") or "")
        situation = str(raw.get("situation") or raw.get("intended_scenario") or "")
        shot = normalize_shot(
            raw,
            product_model=product_model,
            case_id=case_id,
            line=line,
            situation=situation,
        )
        if shot is None:
            continue
        key = shot_key(shot)
        if key in by_key:
            previous = by_key[key]
            previous.update(shot)
        else:
            ordered.append(shot)
            by_key[key] = shot
            added += 1
    if len(ordered) > MAX_SHOTS:
        ordered = ordered[-MAX_SHOTS:]
    history["shots"] = ordered
    path = save_history(project_root, history)
    return {
        "status": "OK",
        "product_model": product_model,
        "path": path.as_posix(),
        "shot_count": len(ordered),
        "added": added,
    }


def overlay_cut(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key in ("source", "path", "in_sec", "out_sec", "source_in", "source_out", "visual", "semantic_tags", "scenario_tags"):
        if overlay.get(key) is not None:
            merged[key] = overlay[key]
    return merged


def adopted_cuts_from_case(
    project_root: Path,
    case_id: str,
    timeline_cuts: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    root = case_root(project_root, case_id)
    script_path = root / "approved-script.json"
    plan_path = root / "assembly-plan.json"
    script_cuts = []
    if script_path.is_file():
        script = json.loads(script_path.read_text(encoding="utf-8"))
        script_cuts = list(script.get("cuts") or [])
    by_id: dict[str, dict[str, Any]] = {}
    for cut in script_cuts:
        if isinstance(cut, dict) and cut.get("cut_id"):
            by_id[str(cut["cut_id"])] = dict(cut)
    if plan_path.is_file():
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        for cut in plan.get("cuts") or []:
            if not isinstance(cut, dict) or not cut.get("cut_id"):
                continue
            cut_id = str(cut["cut_id"])
            by_id[cut_id] = overlay_cut(by_id.get(cut_id) or {}, cut)
    receipts = root / "receipts"
    if receipts.is_dir():
        for path in sorted(receipts.glob("picture_swap*.json")):
            swap = json.loads(path.read_text(encoding="utf-8"))
            cuts = swap.get("cuts") if isinstance(swap, dict) else None
            if not isinstance(cuts, dict):
                continue
            for cut_id, overlay in cuts.items():
                if not isinstance(overlay, dict):
                    continue
                by_id[str(cut_id)] = overlay_cut(by_id.get(str(cut_id)) or {"cut_id": cut_id}, overlay)
    if timeline_cuts:
        for cut in timeline_cuts:
            if not isinstance(cut, dict) or not cut.get("cut_id"):
                continue
            cut_id = str(cut["cut_id"])
            by_id[cut_id] = overlay_cut(by_id.get(cut_id) or {}, cut)
    adopted: list[dict[str, Any]] = []
    order = [str(cut["cut_id"]) for cut in script_cuts if isinstance(cut, dict) and cut.get("cut_id")]
    if not order:
        order = sorted(by_id)
    for cut_id in order:
        item = by_id.get(cut_id)
        if not item:
            continue
        item["cut_id"] = cut_id
        adopted.append(item)
    return adopted


def record_case_final_timeline(
    project_root: Path,
    case_id: str,
    product_model: str,
    timeline_cuts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    adopted = adopted_cuts_from_case(project_root, case_id, timeline_cuts)
    return record_shots(project_root, product_model, case_id, adopted)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--product-model")
    parser.add_argument("--case-id")
    parser.add_argument("--match-json")
    parser.add_argument("--record-final", action="store_true")
    parser.add_argument("--timeline-json")
    args = parser.parse_args()
    root = Path(args.project_root)
    if args.record_final:
        if not args.case_id or not args.product_model:
            emit({"status": "OK", "recorded": False, "reason": "case_id and product_model required"})
            return 0
        timeline = json.loads(args.timeline_json) if args.timeline_json else None
        payload = record_case_final_timeline(root, args.case_id, args.product_model, timeline)
        emit(payload)
        return 0
    if args.match_json:
        if not args.product_model:
            emit({"status": "OK", "matches": []})
            return 0
        query = json.loads(args.match_json)
        history = load_history(root, args.product_model)
        matches = matching_history_shots(
            history,
            line=str(query.get("line") or ""),
            situation=str(query.get("situation") or ""),
        )
        emit({"status": "OK", "matches": matches, "count": len(matches)})
        return 0
    if args.product_model:
        payload = load_history(root, args.product_model)
        payload["status"] = "OK"
        emit(payload)
        return 0
    emit({"status": "OK", "shots": []})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
