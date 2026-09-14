#!/usr/bin/env python3
"""Build a local ChatCut execution plan before any editor placement."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from assembly import assemble_plan, write_plan
from caption_wrap import wrap_caption
from constants import NARRATION_SPEED
from approved_shots import load_history
from material_index import candidates_from_index, load_aliases, load_index
from paths import case_root, emit
from prove_tts_speed import clip_target_duration
from script_fidelity import assert_immutable, load_approved_script
from workflow_state import hold

SCHEMA = "product_video_edit_plan.v1"
FPS = 30
IMPORT_BATCH_SIZE = 4
CAPTION_PRESET = "product-video-center"


def edit_plan_path(project_root: Path, case_id: str) -> Path:
    return case_root(project_root, case_id) / "edit-plan.json"


def _seconds_to_frame(seconds: float, fps: int) -> int:
    return int(round(float(seconds) * fps))


def chatcut_execution_steps(plan: dict[str, Any]) -> list[dict[str, Any]]:
    cuts = [item for item in plan.get("cuts") or [] if isinstance(item, dict)]
    files: list[str] = []
    seen: set[str] = set()
    for cut in cuts:
        for key in ("narration_audio_path", "video_source"):
            path = cut.get(key)
            if isinstance(path, str) and path and path not in seen:
                seen.add(path)
                files.append(path)
    batches = [files[index : index + IMPORT_BATCH_SIZE] for index in range(0, len(files), IMPORT_BATCH_SIZE)]
    audio_adds = []
    rate_updates = []
    video_adds = []
    captions = []
    for cut in cuts:
        audio_adds.append(
            {
                "cut_id": cut["cut_id"],
                "type": "audio",
                "path": cut.get("narration_audio_path"),
                "fromFrame": cut.get("timeline_start_frame"),
                "durationInFrames": cut.get("duration_frames"),
            }
        )
        rate_updates.append(
            {
                "cut_id": cut["cut_id"],
                "playbackRate": NARRATION_SPEED,
            }
        )
        video_adds.append(
            {
                "cut_id": cut["cut_id"],
                "type": "video",
                "path": cut.get("video_source"),
                "fromFrame": cut.get("timeline_start_frame"),
                "durationInFrames": cut.get("duration_frames"),
                "sourceStartFromInSeconds": cut.get("source_in"),
            }
        )
        captions.append(
            {
                "cut_id": cut["cut_id"],
                "caption_text": cut.get("caption_text"),
                "caption_visual_wrap": cut.get("caption_visual_wrap"),
                "fromFrame": cut.get("timeline_start_frame"),
                "durationInFrames": cut.get("duration_frames"),
            }
        )
    steps: list[dict[str, Any]] = []
    for batch in batches:
        steps.append({"op": "import_batch", "paths": batch, "max_files": IMPORT_BATCH_SIZE})
    if audio_adds:
        steps.append({"op": "place_audio", "adds": audio_adds})
    if rate_updates:
        steps.append({"op": "set_playback_rate", "updates": rate_updates, "playbackRate": NARRATION_SPEED})
    if video_adds:
        steps.append({"op": "place_video", "adds": video_adds})
    steps.append({"op": "caption_preset", "preset": CAPTION_PRESET, "action": "preset_apply"})
    steps.append({"op": "place_captions", "cards": captions})
    return steps


def build_edit_plan(
    approved_script: dict[str, Any],
    assembly_plan: dict[str, Any],
    narration_manifest: dict[str, Any],
    *,
    fps: int = FPS,
) -> dict[str, Any]:
    clips = {clip["cut_id"]: clip for clip in narration_manifest.get("clips") or []}
    selected = {cut["cut_id"]: cut for cut in assembly_plan.get("cuts") or []}
    cuts: list[dict[str, Any]] = []
    cursor = 0.0
    for cut in approved_script.get("cuts") or []:
        cut_id = cut["cut_id"]
        line = cut["line"]
        fidelity = assert_immutable(line, line, role="edit_plan_line")
        if fidelity.get("status") != "OK":
            return fidelity
        clip = clips.get(cut_id)
        if not clip:
            return hold("HOLD_NARRATION_DURATION", f"missing narration duration for {cut_id}")
        target = clip_target_duration(clip)
        if target.get("status") != "OK":
            return hold(
                target.get("hold") or "HOLD_NARRATION_DURATION",
                target.get("reason") or f"invalid editorial duration for {cut_id}",
            )
        picture = selected.get(cut_id)
        if not isinstance(picture, dict):
            return hold("HOLD_ASSEMBLY_PLAN", f"missing assembly cut {cut_id}")
        wrap = wrap_caption(line)
        if wrap.get("status") != "OK":
            return wrap
        duration = float(target["target_duration_seconds"])
        start = cursor
        end = start + duration
        item = {
            "cut_id": cut_id,
            "line": line,
            "situation": cut.get("situation"),
            "narration_audio_path": clip.get("audio_path"),
            "source_duration_seconds": target["source_duration_seconds"],
            "editor_playback_rate": NARRATION_SPEED,
            "target_duration_seconds": duration,
            "video_source": picture.get("source") or picture.get("material_id") or picture.get("path"),
            "source_in": picture.get("source_in") if picture.get("source_in") is not None else picture.get("in_sec"),
            "source_out": picture.get("source_out") if picture.get("source_out") is not None else picture.get("out_sec"),
            "available_duration": picture.get("available_duration"),
            "timeline_start_seconds": start,
            "timeline_end_seconds": end,
            "timeline_start_frame": _seconds_to_frame(start, fps),
            "timeline_end_frame": _seconds_to_frame(end, fps),
            "duration_frames": max(1, _seconds_to_frame(end, fps) - _seconds_to_frame(start, fps)),
            "caption_text": wrap["caption_text"],
            "caption_visual_wrap": wrap["caption_visual_wrap"],
        }
        if item["available_duration"] is not None and float(item["available_duration"]) + 1e-9 < duration:
            return hold(
                "HOLD_MEDIA_NOT_MATCHED",
                f"{cut_id} available_duration < target_duration_seconds",
            )
        cuts.append(item)
        cursor = end
    plan = {
        "status": "OK",
        "schema": SCHEMA,
        "fps": fps,
        "editor_playback_rate": NARRATION_SPEED,
        "reselect_in_editor": False,
        "cuts": cuts,
    }
    plan["import_batches"] = [
        step["paths"] for step in chatcut_execution_steps(plan) if step.get("op") == "import_batch"
    ]
    plan["chatcut_steps"] = chatcut_execution_steps(plan)
    return plan


def write_edit_plan(project_root: Path, case_id: str, plan: dict[str, Any]) -> Path:
    dest = edit_plan_path(project_root, case_id)
    dest.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dest


def assemble_and_plan(
    project_root: Path,
    case_id: str,
    *,
    product_model: str,
    approved_script: dict[str, Any] | None = None,
    narration_manifest: dict[str, Any] | None = None,
    history: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(project_root)
    script = approved_script or load_approved_script(case_root(root, case_id) / "approved-script.json")
    if narration_manifest is None:
        narration_manifest = json.loads((case_root(root, case_id) / "narration-manifest.json").read_text(encoding="utf-8"))
    index = load_index(root, product_model)
    aliases = load_aliases(root, product_model)
    if history is None:
        history = load_history(root, product_model)
    candidates: dict[str, list[dict[str, Any]]] = {}
    for cut in script.get("cuts") or []:
        candidates[cut["cut_id"]] = candidates_from_index(
            index,
            line=cut["line"],
            situation=cut["situation"],
            folder_aliases=aliases,
        )
    assembled = assemble_plan(script, narration_manifest, candidates, history=history)
    if assembled.get("status") != "OK":
        return assembled
    write_plan(root, case_id, assembled)
    planned = build_edit_plan(script, assembled, narration_manifest)
    if planned.get("status") != "OK":
        return planned
    path = write_edit_plan(root, case_id, planned)
    planned["path"] = path.as_posix()
    planned["assembly_path"] = (case_root(root, case_id) / "assembly-plan.json").as_posix()
    return planned


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--product-model", required=True)
    args = parser.parse_args()
    payload = assemble_and_plan(Path(args.project_root), args.case_id, product_model=args.product_model)
    emit(payload)
    return 0 if payload.get("status") == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
