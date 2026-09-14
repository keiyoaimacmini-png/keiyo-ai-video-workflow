#!/usr/bin/env python3
"""Approved-script TTS queue. One session, all cuts, one manifest at the end."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from narration import record_clip, write_manifest
from paths import case_root, emit
from script_fidelity import load_approved_script
from workflow_state import atomic_write, hold

SCHEMA = "product_video_narration_queue.v1"
CUT_STEPS = (
    "clear",
    "write_frozen",
    "exact_readback",
    "generate",
    "credit_got_it",
    "capture",
    "save_duration",
)
BETWEEN_CUTS = {
    "skip_mcp_rediscovery": True,
    "skip_voice_reselect": True,
    "skip_page_research": True,
    "skip_holiday_twist_reselect": True,
    "skip_voice_id_resolve": True,
    "skip_chrome_preflight": True,
    "skip_dispatch": True,
    "skip_llm_plan": True,
    "skip_chat": True,
    "return_to_dispatch": False,
    "write_manifest": False,
}


def queue_path(project_root: Path, case_id: str) -> Path:
    return case_root(project_root, case_id) / "tts" / "queue.json"


def empty_queue(case_id: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "case_id": case_id,
        "setup": False,
        "cuts": [],
        "recorded": [],
        "manifest_written": False,
    }


def load_queue(project_root: Path, case_id: str) -> dict[str, Any]:
    path = queue_path(project_root, case_id)
    if not path.is_file():
        return empty_queue(case_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return empty_queue(case_id)
    if data.get("case_id") != case_id:
        return empty_queue(case_id)
    return data


def save_queue(project_root: Path, data: dict[str, Any]) -> Path:
    path = queue_path(project_root, data["case_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return path


def _approved_path(project_root: Path, case_id: str, approved_script_path: str | None) -> Path:
    if approved_script_path:
        return Path(approved_script_path)
    return case_root(project_root, case_id) / "approved-script.json"


def start_queue(
    project_root: Path,
    case_id: str,
    *,
    approved_script_path: str | None = None,
    session_setup: bool = False,
) -> dict[str, Any]:
    script = load_approved_script(_approved_path(project_root, case_id, approved_script_path))
    data = load_queue(project_root, case_id)
    existing = {item.get("cut_id"): item for item in data.get("cuts") or [] if isinstance(item, dict)}
    cuts = []
    for cut in script.get("cuts") or []:
        cut_id = cut["cut_id"]
        previous = existing.get(cut_id) or {}
        cuts.append(
            {
                "cut_id": cut_id,
                "line": cut["line"],
                "status": previous.get("status") or "pending",
                "clip": previous.get("clip"),
            }
        )
    data["cuts"] = cuts
    data["setup"] = bool(session_setup or data.get("setup"))
    save_queue(project_root, data)
    return next_action(project_root, case_id)


def remaining_cuts(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in data.get("cuts") or [] if item.get("status") != "recorded"]


def recorded_clips(data: dict[str, Any]) -> list[dict[str, Any]]:
    clips = []
    for item in data.get("cuts") or []:
        clip = item.get("clip")
        if item.get("status") == "recorded" and isinstance(clip, dict):
            clips.append(clip)
    return clips


def _session_policy(data: dict[str, Any]) -> dict[str, Any]:
    setup_needed = data.get("setup") is not True
    policy = dict(BETWEEN_CUTS)
    policy["setup_session"] = setup_needed
    if setup_needed:
        policy["skip_mcp_rediscovery"] = False
        policy["skip_page_research"] = False
        policy["skip_voice_reselect"] = False
        policy["skip_holiday_twist_reselect"] = False
        policy["skip_voice_id_resolve"] = False
        policy["skip_chrome_preflight"] = False
    policy["cut_steps"] = list(CUT_STEPS)
    return policy


def next_action(project_root: Path, case_id: str) -> dict[str, Any]:
    data = load_queue(project_root, case_id)
    leftover = remaining_cuts(data)
    policy = _session_policy(data)
    if not leftover:
        return {
            "status": "OK",
            "queue_complete": True,
            "return_to_dispatch": True,
            "write_manifest": not data.get("manifest_written"),
            "skip_chat": True,
            "skip_llm_plan": True,
            "skip_dispatch": False,
            "next_stage": "ASSEMBLY",
            "cut_count": len(data.get("cuts") or []),
            "recorded_count": len(recorded_clips(data)),
        }
    current = leftover[0]
    payload = {
        "status": "OK",
        "queue_complete": False,
        "cut_id": current["cut_id"],
        "line": current["line"],
        "remaining": [item["cut_id"] for item in leftover],
        "remaining_count": len(leftover),
        "cut_steps": list(CUT_STEPS),
        **policy,
        "return_to_dispatch": False,
        "write_manifest": False,
        "skip_chat": True,
        "skip_llm_plan": True,
        "skip_dispatch": True,
    }
    return payload


def mark_setup(project_root: Path, case_id: str) -> dict[str, Any]:
    data = load_queue(project_root, case_id)
    data["setup"] = True
    save_queue(project_root, data)
    return next_action(project_root, case_id)


def record_queue_clip(
    project_root: Path,
    case_id: str,
    *,
    cut_id: str,
    line: str,
    audio_path: str,
    source_duration_seconds: float,
) -> dict[str, Any]:
    clip = record_clip(
        cut_id=cut_id,
        line=line,
        audio_path=audio_path,
        source_duration_seconds=source_duration_seconds,
    )
    if clip.get("status") != "OK":
        return clip
    data = load_queue(project_root, case_id)
    found = False
    for item in data.get("cuts") or []:
        if item.get("cut_id") != cut_id:
            continue
        item["status"] = "recorded"
        item["clip"] = clip
        found = True
        data["setup"] = True
        break
    if not found:
        return hold("HOLD_NARRATION_AUDIO", f"queue is missing {cut_id}")
    save_queue(project_root, data)
    nxt = next_action(project_root, case_id)
    nxt["recorded_cut"] = cut_id
    nxt["skip_chat"] = True
    nxt["skip_llm_plan"] = True
    if nxt.get("queue_complete") is not True:
        nxt["return_to_dispatch"] = False
        nxt["write_manifest"] = False
        nxt["skip_dispatch"] = True
    return nxt


def finish_queue(project_root: Path, case_id: str) -> dict[str, Any]:
    data = load_queue(project_root, case_id)
    leftover = remaining_cuts(data)
    if leftover:
        return {
            "status": "OK",
            "queue_complete": False,
            "return_to_dispatch": False,
            "write_manifest": False,
            "skip_dispatch": True,
            "skip_chat": True,
            "remaining": [item["cut_id"] for item in leftover],
        }
    clips = recorded_clips(data)
    written = write_manifest(project_root, case_id, clips)
    data["manifest_written"] = True
    data["recorded"] = [clip.get("cut_id") for clip in clips]
    save_queue(project_root, data)
    return {
        "status": "OK",
        "queue_complete": True,
        "return_to_dispatch": True,
        "write_manifest": True,
        "skip_chat": True,
        "skip_llm_plan": True,
        "skip_dispatch": False,
        "next_stage": "ASSEMBLY",
        "clip_count": written.get("clip_count"),
        "path": written.get("path"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--approved-script")
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--next", action="store_true")
    parser.add_argument("--mark-setup", action="store_true")
    parser.add_argument("--finish", action="store_true")
    parser.add_argument("--record-cut")
    parser.add_argument("--line")
    parser.add_argument("--audio-path")
    parser.add_argument("--source-duration-seconds", type=float)
    args = parser.parse_args()
    root = Path(args.project_root)
    if args.start:
        payload = start_queue(root, args.case_id, approved_script_path=args.approved_script)
    elif args.mark_setup:
        payload = mark_setup(root, args.case_id)
    elif args.record_cut:
        payload = record_queue_clip(
            root,
            args.case_id,
            cut_id=args.record_cut,
            line=str(args.line or ""),
            audio_path=str(args.audio_path or ""),
            source_duration_seconds=float(args.source_duration_seconds or 0),
        )
    elif args.finish:
        payload = finish_queue(root, args.case_id)
    else:
        payload = next_action(root, args.case_id)
    emit(payload)
    return 0 if payload.get("status") == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
