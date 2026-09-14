#!/usr/bin/env python3
"""Compact per-case wall-clock metrics. Do not chat these mid-run."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from paths import case_root, emit, receipts_dir
from workflow_state import atomic_write

SCHEMA = "product_video_timing.v1"
STAGE_KEYS = {
    "SCRIPT": "script",
    "NARRATION": "narration",
    "ASSEMBLY": "assembly_plan",
    "ROUGH_EDIT": "chatcut_placement",
    "DELIVERY": "export_drive",
}
ROUGH_EDIT_METRIC_KEYS = (
    "chatcut_project_setup_seconds",
    "import_seconds",
    "place_audio_seconds",
    "playback_rate_seconds",
    "place_video_seconds",
    "caption_preset_seconds",
    "place_captions_seconds",
    "final_verify_seconds",
    "rough_edit_total_seconds",
)
ROUGH_EDIT_STEP_TO_KEY = {
    "project_setup": "chatcut_project_setup_seconds",
    "import": "import_seconds",
    "place_audio": "place_audio_seconds",
    "playback_rate": "playback_rate_seconds",
    "place_video": "place_video_seconds",
    "caption_preset": "caption_preset_seconds",
    "place_captions": "place_captions_seconds",
    "final_verify": "final_verify_seconds",
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def _parse(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def timing_path(project_root: Path, case_id: str) -> Path:
    return case_root(project_root, case_id) / "timing.json"


def empty_timing(case_id: str) -> dict[str, Any]:
    return {"schema": SCHEMA, "case_id": case_id, "stages": {}, "metrics": {}}


def load_timing(project_root: Path, case_id: str) -> dict[str, Any]:
    path = timing_path(project_root, case_id)
    if not path.is_file():
        return empty_timing(case_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_timing(case_id)
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return empty_timing(case_id)
    data.setdefault("stages", {})
    data.setdefault("metrics", {})
    return data


def save_timing(project_root: Path, data: dict[str, Any]) -> Path:
    case_id = str(data["case_id"])
    path = timing_path(project_root, case_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return path


def count_picture_swaps(project_root: Path, case_id: str) -> int:
    folder = receipts_dir(project_root, case_id)
    if not folder.is_dir():
        return 0
    return sum(1 for path in folder.glob("picture_swap*.json") if path.is_file())


def summarize(data: dict[str, Any]) -> dict[str, Any]:
    stages = data.get("stages") if isinstance(data.get("stages"), dict) else {}
    metrics = dict(data.get("metrics") or {})

    def elapsed(name: str) -> float | None:
        item = stages.get(name) if isinstance(stages.get(name), dict) else None
        if not item:
            return None
        stored = item.get("elapsed_seconds")
        if isinstance(stored, (int, float)) and not isinstance(stored, bool):
            return float(stored)
        start = _parse(item.get("started_at"))
        end = _parse(item.get("ended_at"))
        if start is None or end is None:
            return None
        return max(0.0, (end - start).total_seconds())

    script = elapsed("SCRIPT")
    narration = elapsed("NARRATION")
    cut_count = metrics.get("cut_count")
    avg_tts = metrics.get("avg_tts_seconds_per_cut")
    if avg_tts is None and isinstance(narration, float) and isinstance(cut_count, int) and cut_count > 0:
        avg_tts = narration / cut_count
    summary = {
        "script_elapsed_seconds": script,
        "narration_started_at": (stages.get("NARRATION") or {}).get("started_at") if isinstance(stages.get("NARRATION"), dict) else None,
        "narration_ended_at": (stages.get("NARRATION") or {}).get("ended_at") if isinstance(stages.get("NARRATION"), dict) else None,
        "narration_elapsed_seconds": narration,
        "cut_count": cut_count,
        "avg_tts_seconds_per_cut": avg_tts,
        "assembly_plan_elapsed_seconds": elapsed("ASSEMBLY"),
        "chatcut_placement_elapsed_seconds": elapsed("ROUGH_EDIT"),
        "human_picture_swap_count": metrics.get("human_picture_swap_count"),
        "export_drive_elapsed_seconds": elapsed("DELIVERY"),
    }
    for key in ROUGH_EDIT_METRIC_KEYS:
        if key in metrics:
            summary[key] = metrics[key]
    return summary


def mark_stage_start(project_root: Path, case_id: str, stage: str) -> dict[str, Any]:
    if stage not in STAGE_KEYS:
        return {"status": "OK", "ignored": True}
    data = load_timing(project_root, case_id)
    stages = data.setdefault("stages", {})
    current = stages.get(stage) if isinstance(stages.get(stage), dict) else {}
    if not current.get("started_at"):
        current["started_at"] = _iso(_now())
    stages[stage] = current
    save_timing(project_root, data)
    return {"status": "OK", "stage": stage, "started_at": current["started_at"]}


def mark_stage_end(
    project_root: Path,
    case_id: str,
    stage: str,
    receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if stage not in STAGE_KEYS:
        return {"status": "OK", "ignored": True}
    data = load_timing(project_root, case_id)
    stages = data.setdefault("stages", {})
    current = dict(stages.get(stage) if isinstance(stages.get(stage), dict) else {})
    ended = _now()
    current["ended_at"] = _iso(ended)
    start = _parse(current.get("started_at"))
    if start is None:
        current["started_at"] = current["ended_at"]
        start = ended
    current["elapsed_seconds"] = max(0.0, (ended - start).total_seconds())
    stages[stage] = current
    metrics = data.setdefault("metrics", {})
    if stage == "NARRATION":
        cut_count = None
        if isinstance(receipt, dict):
            cut_count = receipt.get("clip_count") or receipt.get("cut_count")
        if isinstance(cut_count, int) and not isinstance(cut_count, bool):
            metrics["cut_count"] = cut_count
            if cut_count > 0:
                metrics["avg_tts_seconds_per_cut"] = current["elapsed_seconds"] / cut_count
    if stage in {"DELIVERY", "COMPLETE", "ROUGH_EDIT"}:
        metrics["human_picture_swap_count"] = count_picture_swaps(project_root, case_id)
    if stage == "ROUGH_EDIT":
        metrics["rough_edit_total_seconds"] = current["elapsed_seconds"]
    data["summary"] = summarize(data)
    save_timing(project_root, data)
    return {"status": "OK", "stage": stage, "summary": data["summary"]}


def record_rough_edit_metrics(project_root: Path, case_id: str, values: dict[str, Any]) -> dict[str, Any]:
    data = load_timing(project_root, case_id)
    metrics = data.setdefault("metrics", {})
    recorded: dict[str, float] = {}
    for key in ROUGH_EDIT_METRIC_KEYS:
        raw = values.get(key)
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            metrics[key] = float(raw)
            recorded[key] = float(raw)
    data["summary"] = summarize(data)
    save_timing(project_root, data)
    return {"status": "OK", "metrics": recorded}


def mark_rough_edit_step_start(project_root: Path, case_id: str, step: str) -> dict[str, Any]:
    if step not in ROUGH_EDIT_STEP_TO_KEY:
        return {"status": "OK", "ignored": True, "step": step}
    data = load_timing(project_root, case_id)
    rough = data.setdefault("stages", {}).setdefault("ROUGH_EDIT", {})
    marks = rough.setdefault("step_marks", {})
    current = marks.get(step) if isinstance(marks.get(step), dict) else {}
    if not current.get("started_at"):
        current["started_at"] = _iso(_now())
    marks[step] = current
    save_timing(project_root, data)
    return {"status": "OK", "step": step, "started_at": current["started_at"]}


def mark_rough_edit_step_end(project_root: Path, case_id: str, step: str) -> dict[str, Any]:
    key = ROUGH_EDIT_STEP_TO_KEY.get(step)
    if key is None:
        return {"status": "OK", "ignored": True, "step": step}
    data = load_timing(project_root, case_id)
    rough = data.setdefault("stages", {}).setdefault("ROUGH_EDIT", {})
    marks = rough.setdefault("step_marks", {})
    current = dict(marks.get(step) if isinstance(marks.get(step), dict) else {})
    ended = _now()
    current["ended_at"] = _iso(ended)
    start = _parse(current.get("started_at"))
    if start is None:
        current["started_at"] = current["ended_at"]
        start = ended
    elapsed = max(0.0, (ended - start).total_seconds())
    current["elapsed_seconds"] = elapsed
    marks[step] = current
    metrics = data.setdefault("metrics", {})
    metrics[key] = elapsed
    data["summary"] = summarize(data)
    save_timing(project_root, data)
    return {"status": "OK", "step": step, "metric": key, "elapsed_seconds": elapsed}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--mark-start")
    parser.add_argument("--mark-end")
    parser.add_argument("--mark-step-start")
    parser.add_argument("--mark-step-end")
    parser.add_argument("--record-rough-edit-json")
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args()
    root = Path(args.project_root)
    if args.mark_start:
        payload = mark_stage_start(root, args.case_id, args.mark_start)
    elif args.mark_end:
        payload = mark_stage_end(root, args.case_id, args.mark_end)
    elif args.mark_step_start:
        payload = mark_rough_edit_step_start(root, args.case_id, args.mark_step_start)
    elif args.mark_step_end:
        payload = mark_rough_edit_step_end(root, args.case_id, args.mark_step_end)
    elif args.record_rough_edit_json:
        payload = record_rough_edit_metrics(root, args.case_id, json.loads(args.record_rough_edit_json))
    else:
        data = load_timing(root, args.case_id)
        payload = {"status": "OK", "summary": summarize(data), "path": timing_path(root, args.case_id).as_posix()}
    emit(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
