#!/usr/bin/env python3
"""Build a local ChatCut execution plan before any editor placement."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from assembly import assemble_plan, write_plan
from caption_wrap import wrap_caption
from constants import NARRATION_SPEED, TELOP_ONLY_DURATION_SECONDS
from approved_shots import load_history
from material_index import candidates_from_index, load_aliases, load_index
from visual_catalog import load_catalog
from paths import case_root, emit
from prove_tts_speed import case_allow_narration_rate, clip_target_duration, load_playback_override
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


def cut_video_segments(cut: dict[str, Any]) -> list[dict[str, Any]]:
    planned = cut.get("video_segments")
    if isinstance(planned, list) and planned:
        found = [item for item in planned if isinstance(item, dict) and item.get("source")]
        if found:
            return found
    source = cut.get("video_source")
    if not source:
        return []
    start = cut.get("source_in")
    end = cut.get("source_out")
    duration = cut.get("target_duration_seconds")
    return [
        {
            "source": source,
            "source_in": start,
            "source_out": end,
            "duration": duration,
        }
    ]


def chatcut_execution_steps(plan: dict[str, Any]) -> list[dict[str, Any]]:
    cuts = [item for item in plan.get("cuts") or [] if isinstance(item, dict)]
    fps = int(plan.get("fps") or FPS)
    files: list[str] = []
    seen: set[str] = set()
    for cut in cuts:
        paths = [cut.get("narration_audio_path")]
        paths.extend(seg.get("source") for seg in cut_video_segments(cut))
        for path in paths:
            if isinstance(path, str) and path and path not in seen:
                seen.add(path)
                files.append(path)
    batches = [files[index : index + IMPORT_BATCH_SIZE] for index in range(0, len(files), IMPORT_BATCH_SIZE)]
    audio_adds = []
    rate_updates = []
    video_adds = []
    captions = []
    for cut in cuts:
        if cut.get("telop_only") is not True and cut.get("narration_audio_path"):
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
                    "playbackRate": cut.get("editor_playback_rate") or NARRATION_SPEED,
                }
            )
        cursor = float(cut.get("timeline_start_seconds") or 0.0)
        remaining = float(cut.get("target_duration_seconds") or 0.0)
        if remaining <= 0 and cut.get("duration_frames"):
            remaining = float(cut["duration_frames"]) / float(fps)
        if cursor <= 0 and cut.get("timeline_start_frame"):
            cursor = float(cut["timeline_start_frame"]) / float(fps)
        for index, seg in enumerate(cut_video_segments(cut)):
            span = float(seg.get("duration") or 0.0)
            if span <= 0 and seg.get("source_in") is not None and seg.get("source_out") is not None:
                span = float(seg["source_out"]) - float(seg["source_in"])
            if span <= 0:
                span = remaining
            use = min(span, remaining) if remaining > 0 else span
            if use <= 0:
                continue
            start_frame = _seconds_to_frame(cursor, fps)
            end_frame = _seconds_to_frame(cursor + use, fps)
            video_add = {
                "cut_id": cut["cut_id"],
                "segment_index": index,
                "type": "video",
                "path": seg.get("source"),
                "fromFrame": start_frame,
                "durationInFrames": max(1, end_frame - start_frame),
                "sourceStartFromInSeconds": seg.get("source_in"),
                "timeline_start_seconds": cursor,
                "duration": use,
            }
            video_rate = seg.get("video_playback_rate")
            if isinstance(video_rate, (int, float)) and not isinstance(video_rate, bool) and float(video_rate) != 1.0:
                video_add["playbackRate"] = float(video_rate)
            video_adds.append(video_add)
            cursor += use
            remaining -= use
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
        steps.append(
            {
                "op": "set_playback_rate",
                "updates": rate_updates,
                "playbackRate": rate_updates[0]["playbackRate"] if rate_updates else NARRATION_SPEED,
            }
        )
    if video_adds:
        steps.append({"op": "place_video", "adds": video_adds})
        steps.append({"op": "caption_preset", "preset": CAPTION_PRESET, "action": "preset_apply"})
    if captions:
        steps.append({"op": "place_captions", "cards": captions})
    steps.append({"op": "final_verify"})
    return steps


def build_edit_plan(
    approved_script: dict[str, Any],
    assembly_plan: dict[str, Any],
    narration_manifest: dict[str, Any],
    *,
    fps: int = FPS,
    allow_rate: float | None = None,
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
        telop_only = cut.get("telop_only") is True
        clip = None if telop_only else clips.get(cut_id)
        if not telop_only and not clip:
            return hold("HOLD_NARRATION_DURATION", f"missing narration duration for {cut_id}")
        if telop_only:
            target = {
                "status": "OK",
                "source_duration_seconds": TELOP_ONLY_DURATION_SECONDS,
                "target_duration_seconds": TELOP_ONLY_DURATION_SECONDS,
            }
        else:
            target = clip_target_duration(clip, allow_rate=allow_rate)
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
        video_rate = picture.get("video_playback_rate")
        if not isinstance(video_rate, (int, float)) or isinstance(video_rate, bool) or float(video_rate) <= 0:
            video_rate = 1.0
        video_rate = float(video_rate)
        start = cursor
        end = start + duration
        segments = []
        cursor_seg = start
        remaining = duration
        raw_segments = picture.get("video_segments") if isinstance(picture.get("video_segments"), list) else []
        if raw_segments and video_rate == 1.0:
            for seg in raw_segments:
                if not isinstance(seg, dict) or not seg.get("source"):
                    continue
                span = float(seg.get("duration") or 0.0)
                if span <= 0 and seg.get("source_in") is not None and seg.get("source_out") is not None:
                    span = float(seg["source_out"]) - float(seg["source_in"])
                use = min(span, remaining)
                if use <= 0:
                    continue
                segments.append(
                    {
                        "source": seg.get("source"),
                        "source_in": seg.get("source_in"),
                        "source_out": float(seg.get("source_in") or 0.0) + use
                        if seg.get("source_in") is not None
                        else seg.get("source_out"),
                        "timeline_start": cursor_seg,
                        "duration": use,
                    }
                )
                cursor_seg += use
                remaining -= use
        if not segments:
            source_in = picture.get("source_in") if picture.get("source_in") is not None else picture.get("in_sec")
            source_out = picture.get("source_out") if picture.get("source_out") is not None else picture.get("out_sec")
            source_span = None
            if isinstance(source_in, (int, float)) and isinstance(source_out, (int, float)) and not isinstance(source_in, bool) and not isinstance(source_out, bool):
                source_span = float(source_out) - float(source_in)
            use_source = duration * video_rate
            if source_span is not None and source_span > 0:
                use_source = min(source_span, use_source)
            use_timeline = use_source / video_rate
            if source_span is not None and isinstance(source_in, (int, float)) and not isinstance(source_in, bool):
                source_out = float(source_in) + use_source
            segments = [
                {
                    "source": picture.get("source") or picture.get("material_id") or picture.get("path"),
                    "source_in": source_in,
                    "source_out": source_out,
                    "timeline_start": start,
                    "duration": use_timeline,
                    "video_playback_rate": video_rate,
                }
            ]
        available = sum(float(seg.get("duration") or 0.0) for seg in segments)
        item = {
            "cut_id": cut_id,
            "line": line,
            "situation": cut.get("situation"),
            "telop_only": telop_only,
            "narration_audio_path": None if telop_only else clip.get("audio_path"),
            "source_duration_seconds": target["source_duration_seconds"],
            "editor_playback_rate": None if telop_only else target.get("editor_playback_rate", NARRATION_SPEED),
            "video_playback_rate": video_rate,
            "target_duration_seconds": duration,
            "video_source": segments[0].get("source"),
            "source_in": segments[0].get("source_in"),
            "source_out": segments[0].get("source_out"),
            "available_duration": available,
            "video_segments": segments,
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
        "editor_playback_rate": cuts[0].get("editor_playback_rate") if cuts else NARRATION_SPEED,
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
    catalog = load_catalog(root, product_model)
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
            catalog=catalog,
        )
    file_durations: dict[str, float] = {}
    for entry in (index.get("files") or {}).values():
        if not isinstance(entry, dict):
            continue
        source = str(entry.get("source") or "")
        duration = entry.get("full_duration")
        if not source or not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0:
            continue
        file_durations[source] = float(duration)
    assembled = assemble_plan(
        script,
        narration_manifest,
        candidates,
        history=history,
        catalog=catalog,
        file_durations=file_durations,
        project_root=root,
        case_id=case_id,
    )
    if assembled.get("status") != "OK":
        return assembled
    write_plan(root, case_id, assembled)
    override = load_playback_override(root, case_id)
    allow_rate = case_allow_narration_rate(root, case_id)
    planned = build_edit_plan(
        script,
        assembled,
        narration_manifest,
        allow_rate=allow_rate if isinstance(allow_rate, float) else None,
    )
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
    return 0 if payload.get("status") in {"OK", "needs_jev_rank"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
