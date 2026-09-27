#!/usr/bin/env python3
"""Decode-check narration files before ChatCut import. Extension is not trusted."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from paths import case_root, emit
from workflow_state import atomic_write, hold

HOLD_TTS_DECODE_INVALID = "HOLD_TTS_DECODE_INVALID"
INVALID_CLIPS_FILENAME = "invalid-clips.json"
DECODE_SECONDS = 1.0


def probe_audio(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,codec_type,sample_rate,channels",
            "-show_entries",
            "format=duration,size,format_name",
            "-of",
            "json",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or "ffprobe failed")
    payload = json.loads(result.stdout)
    streams = [
        stream
        for stream in (payload.get("streams") or [])
        if isinstance(stream, dict) and stream.get("codec_type") == "audio"
    ]
    if not streams:
        raise ValueError("audio stream missing")
    duration = float((payload.get("format") or {}).get("duration") or 0)
    if duration <= 0:
        raise ValueError("audio duration missing")
    stream = streams[0]
    return {
        "codec_name": stream.get("codec_name"),
        "sample_rate": int(stream["sample_rate"]) if stream.get("sample_rate") else None,
        "channels": int(stream["channels"]) if stream.get("channels") else None,
        "duration_seconds": duration,
        "format_name": (payload.get("format") or {}).get("format_name"),
    }


def decode_audio(path: Path, *, seconds: float = DECODE_SECONDS) -> dict[str, Any]:
    span = max(0.05, float(seconds))
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-v",
            "error",
            "-i",
            str(path),
            "-t",
            f"{span:.3f}",
            "-f",
            "null",
            "-",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError((result.stderr or result.stdout or "ffmpeg decode failed").strip())
    return {"decoded_seconds": span, "decode_ok": True}


def validate_audio_file(path: Path | str) -> dict[str, Any]:
    dest = Path(path)
    if not dest.is_file():
        return hold(HOLD_TTS_DECODE_INVALID, "narration file is missing", path=str(dest), valid=False)
    if dest.stat().st_size <= 0:
        return hold(HOLD_TTS_DECODE_INVALID, "narration file is empty", path=str(dest), valid=False)
    try:
        probe = probe_audio(dest)
        decode = decode_audio(dest, seconds=min(DECODE_SECONDS, float(probe["duration_seconds"])))
    except (OSError, ValueError, json.JSONDecodeError, TypeError) as exc:
        return hold(
            HOLD_TTS_DECODE_INVALID,
            str(exc) or "narration file failed decode",
            path=str(dest),
            valid=False,
            extension_trusted=False,
        )
    return {
        "status": "OK",
        "valid": True,
        "path": str(dest),
        "extension_trusted": False,
        **probe,
        **decode,
    }


def invalid_clips_path(project_root: Path, case_id: str) -> Path:
    return case_root(project_root, case_id) / "tts" / INVALID_CLIPS_FILENAME


def load_invalid_clips(project_root: Path, case_id: str) -> dict[str, Any]:
    path = invalid_clips_path(project_root, case_id)
    if not path.is_file():
        return {"schema": "product_video_invalid_tts.v1", "case_id": case_id, "clips": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema": "product_video_invalid_tts.v1", "case_id": case_id, "clips": []}
    if not isinstance(data, dict):
        return {"schema": "product_video_invalid_tts.v1", "case_id": case_id, "clips": []}
    clips = data.get("clips")
    if not isinstance(clips, list):
        data["clips"] = []
    return data


def mark_invalid(
    project_root: Path,
    case_id: str,
    *,
    cut_id: str,
    path: Path | str,
    reason: str,
) -> dict[str, Any]:
    src = Path(path)
    quarantined = None
    if src.is_file():
        dest_dir = case_root(project_root, case_id) / "tts" / "invalid"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{cut_id}{src.suffix or '.bin'}"
        if dest.resolve() != src.resolve():
            if dest.exists():
                dest.unlink()
            shutil.move(str(src), str(dest))
        quarantined = dest.as_posix()
    record = {
        "cut_id": cut_id,
        "path": src.as_posix(),
        "quarantined_path": quarantined,
        "reason": reason,
        "valid": False,
        "regenerate": True,
    }
    data = load_invalid_clips(project_root, case_id)
    kept = [item for item in data.get("clips") or [] if isinstance(item, dict) and item.get("cut_id") != cut_id]
    kept.append(record)
    data["clips"] = kept
    dest = invalid_clips_path(project_root, case_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(dest, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    payload = hold(
        HOLD_TTS_DECODE_INVALID,
        reason,
        cut_id=cut_id,
        path=src.as_posix(),
        quarantined_path=quarantined,
        valid=False,
        regenerate=True,
        invalid_clips_path=dest.as_posix(),
    )
    return payload


def _clip_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for clip in manifest.get("clips") or []:
        if not isinstance(clip, dict) or clip.get("telop_only") is True:
            continue
        path = clip.get("audio_path") or clip.get("path")
        cut_id = str(clip.get("cut_id") or "")
        if path and cut_id:
            rows.append({"cut_id": cut_id, "path": str(path)})
    return rows


def validate_paths(
    rows: list[dict[str, Any]],
    *,
    project_root: Path | None = None,
    case_id: str | None = None,
) -> dict[str, Any]:
    checked: list[dict[str, Any]] = []
    for row in rows:
        cut_id = str(row.get("cut_id") or "")
        path = Path(str(row.get("path") or ""))
        result = validate_audio_file(path)
        if result.get("valid") is True:
            checked.append({"cut_id": cut_id, "path": str(path), "valid": True})
            continue
        if project_root is not None and case_id:
            marked = mark_invalid(
                project_root,
                case_id,
                cut_id=cut_id or path.stem,
                path=path,
                reason=str(result.get("reason") or "narration file failed decode"),
            )
            marked["failed"] = [{"cut_id": cut_id, "path": str(path)}]
            marked["checked"] = checked
            return marked
        return hold(
            HOLD_TTS_DECODE_INVALID,
            str(result.get("reason") or "narration file failed decode"),
            cut_id=cut_id,
            path=str(path),
            valid=False,
            regenerate=True,
            checked=checked,
        )
    return {
        "status": "OK",
        "valid": True,
        "clip_count": len(checked),
        "checked": checked,
        "placement_ready": True,
    }


def validate_manifest(project_root: Path, case_id: str, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    if manifest is None:
        path = case_root(project_root, case_id) / "narration-manifest.json"
        if not path.is_file():
            return hold(HOLD_TTS_DECODE_INVALID, "narration-manifest.json is missing", valid=False)
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return hold(HOLD_TTS_DECODE_INVALID, "narration-manifest.json is unreadable", valid=False)
    if not isinstance(manifest, dict):
        return hold(HOLD_TTS_DECODE_INVALID, "narration manifest must be an object", valid=False)
    rows = _clip_rows(manifest)
    if not rows:
        return hold(HOLD_TTS_DECODE_INVALID, "narration manifest has no audio clips", valid=False)
    return validate_paths(rows, project_root=project_root, case_id=case_id)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--case-id")
    parser.add_argument("--audio-path", type=Path)
    parser.add_argument("--cut-id")
    parser.add_argument("--manifest", action="store_true")
    args = parser.parse_args()
    if args.manifest:
        if args.project_root is None or not args.case_id:
            parser.error("--manifest requires --project-root and --case-id")
        payload = validate_manifest(args.project_root, args.case_id)
    elif args.audio_path is not None:
        payload = validate_audio_file(args.audio_path)
        if payload.get("valid") is not True and args.project_root is not None and args.case_id:
            payload = mark_invalid(
                args.project_root,
                args.case_id,
                cut_id=str(args.cut_id or args.audio_path.stem),
                path=args.audio_path,
                reason=str(payload.get("reason") or "narration file failed decode"),
            )
    else:
        parser.error("use --manifest or --audio-path")
    emit(payload)
    return 0 if payload.get("status") == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
