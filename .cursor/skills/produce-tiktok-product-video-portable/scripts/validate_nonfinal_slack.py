#!/usr/bin/env python3
"""Validate frame-exact closure of product-video cuts after real TTS playback."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import wave
from pathlib import Path


SCHEMA = "product_video_nonfinal_slack_receipt.v1"
SHA256_HEX_LENGTH = 64
REQUIRED_KEYS = {
    "cut_id",
    "is_final",
    "narration_target",
    "timeline_start_frame",
    "video_end_frame",
    "caption_end_frame",
    "tts_start_frame",
    "tts_clip_end_frame",
    "audible_speech_end_frame",
    "next_cut_start_frame",
    "slack_frames",
    "tail_exception",
}
LEGACY_KEYS = REQUIRED_KEYS - {"narration_target"}
REQUIRED_TOP_KEYS = {
    "schema", "case_id", "product_model", "observed_at", "fps",
    "final_cut_id", "playback_audio_relative_path", "playback_audio_sha256",
    "playback_audio_bytes", "playback_audio_duration_seconds",
    "playback_asr_relative_path", "playback_asr_sha256",
    "asr_first_speech_seconds", "asr_last_speech_seconds",
    "timeline_timecode", "timeline_end_frame", "readback_basis", "cuts",
}


def is_frame(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def validate(receipt: object, project_root: Path | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(receipt, dict):
        return ["receipt must be a JSON object"]
    if receipt.get("schema") != SCHEMA:
        errors.append(f"schema must equal {SCHEMA}")
    missing_top = sorted(REQUIRED_TOP_KEYS - set(receipt))
    if missing_top:
        errors.append(f"receipt missing top-level keys: {', '.join(missing_top)}")
    fps = receipt.get("fps")
    if not isinstance(fps, int) or isinstance(fps, bool) or fps <= 0:
        errors.append("fps must be a positive integer")
    cuts = receipt.get("cuts")
    if not isinstance(cuts, list) or not cuts:
        errors.append("cuts must be a non-empty array")
        return errors
    has_narration = any(
        isinstance(cut, dict) and cut.get("narration_target", True) is not False
        for cut in cuts
    )

    timeline_timecode = receipt.get("timeline_timecode")
    match = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2})", timeline_timecode or "")
    if match and isinstance(fps, int) and fps > 0:
        minutes, seconds, frames = (int(value) for value in match.groups())
        expected_end = (minutes * 60 + seconds) * fps + frames
        if frames >= fps or receipt.get("timeline_end_frame") != expected_end:
            errors.append("timeline_timecode must frame-exactly match timeline_end_frame")
    else:
        errors.append("timeline_timecode must be MM:SS:FF")

    playback_fields = (
        "playback_audio_relative_path", "playback_audio_sha256", "playback_audio_bytes",
        "playback_audio_duration_seconds", "playback_asr_relative_path", "playback_asr_sha256",
        "asr_first_speech_seconds", "asr_last_speech_seconds",
    )
    if has_narration:
        playback_sha = receipt.get("playback_audio_sha256")
        if not (
            isinstance(playback_sha, str)
            and len(playback_sha) == SHA256_HEX_LENGTH
            and all(char in "0123456789abcdef" for char in playback_sha)
        ):
            errors.append("playback_audio_sha256 must be 64 lowercase hexadecimal characters")
        if project_root is not None:
            for label, path_key, sha_key in (
                ("playback audio", "playback_audio_relative_path", "playback_audio_sha256"),
                ("playback ASR", "playback_asr_relative_path", "playback_asr_sha256"),
            ):
                relative = receipt.get(path_key)
                if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
                    errors.append(f"{path_key} must be a safe relative path")
                    continue
                resolved = (project_root / relative).resolve()
                try:
                    resolved.relative_to(project_root.resolve())
                    raw = resolved.read_bytes()
                except (ValueError, OSError) as exc:
                    errors.append(f"{label} is not readable under project root: {exc}")
                    continue
                if hashlib.sha256(raw).hexdigest() != receipt.get(sha_key):
                    errors.append(f"{label} SHA-256 mismatch")
                if label == "playback audio":
                    if len(raw) != receipt.get("playback_audio_bytes"):
                        errors.append("playback audio byte size mismatch")
                    try:
                        with wave.open(str(resolved), "rb") as handle:
                            duration = handle.getnframes() / handle.getframerate()
                    except (wave.Error, OSError, ZeroDivisionError) as exc:
                        errors.append(f"playback audio WAV is invalid: {exc}")
                    else:
                        claimed = receipt.get("playback_audio_duration_seconds")
                        if not isinstance(claimed, (int, float)) or abs(duration - claimed) > 0.001:
                            errors.append("playback audio duration mismatch")
                else:
                    try:
                        asr = json.loads(raw)
                        segments = asr["segments"]
                        first = float(segments[0]["start"])
                        last = float(segments[-1]["end"])
                    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
                        errors.append(f"playback ASR timestamps are invalid: {exc}")
                    else:
                        if abs(first - receipt.get("asr_first_speech_seconds", -1)) > 0.001:
                            errors.append("ASR first-speech timestamp mismatch")
                        if abs(last - receipt.get("asr_last_speech_seconds", -1)) > 0.001:
                            errors.append("ASR last-speech timestamp mismatch")
    elif any(receipt.get(field) is not None for field in playback_fields):
        errors.append("narration:none requires null playback audio/ASR fields")

    final_cut_id = receipt.get("final_cut_id")
    if not isinstance(final_cut_id, str) or not final_cut_id:
        errors.append("final_cut_id must be a non-empty string")
    seen: set[str] = set()
    final_count = 0
    previous_end: int | None = None
    for index, cut in enumerate(cuts):
        prefix = f"cuts[{index}]"
        if not isinstance(cut, dict):
            errors.append(f"{prefix} must be an object")
            continue
        keys = set(cut)
        if keys not in (REQUIRED_KEYS, LEGACY_KEYS):
            errors.append(f"{prefix} keys must equal current or legacy schema")
            continue
        narration_target = cut.get("narration_target", True)
        if not isinstance(narration_target, bool):
            errors.append(f"{prefix}.narration_target must be boolean")
            continue
        cut_id = cut.get("cut_id")
        if not isinstance(cut_id, str) or not cut_id:
            errors.append(f"{prefix}.cut_id must be a non-empty string")
        elif cut_id in seen:
            errors.append(f"duplicate cut_id: {cut_id}")
        else:
            seen.add(cut_id)

        base_frames = ("timeline_start_frame", "video_end_frame", "caption_end_frame")
        if any(not is_frame(cut.get(field)) for field in base_frames):
            errors.append(f"{prefix} timeline/video/caption frames must be non-negative integers")
            continue
        start = cut["timeline_start_frame"]
        video_end = cut["video_end_frame"]
        caption_end = cut["caption_end_frame"]
        if previous_end is not None and start != previous_end:
            errors.append(f"{prefix} starts at {start}, expected contiguous frame {previous_end}")
        if video_end <= start:
            errors.append(f"{prefix}.video_end_frame must be after timeline_start_frame")
        if caption_end != video_end:
            errors.append(f"{prefix}.caption_end_frame must equal video_end_frame")

        if narration_target:
            tts_fields = ("tts_start_frame", "tts_clip_end_frame", "audible_speech_end_frame", "slack_frames")
            if any(not is_frame(cut.get(field)) for field in tts_fields):
                errors.append(f"{prefix} narrated TTS fields must be non-negative integers")
                previous_end = video_end
                continue
            tts_start = cut["tts_start_frame"]
            tts_clip_end = cut["tts_clip_end_frame"]
            audible_end = cut["audible_speech_end_frame"]
            slack = cut["slack_frames"]
            if tts_start != start:
                errors.append(f"{prefix}.tts_start_frame must equal timeline_start_frame")
            if not (start <= audible_end <= tts_clip_end <= video_end):
                errors.append(f"{prefix} must satisfy start <= audible end <= TTS clip end <= video end")
        else:
            if any(cut.get(field) is not None for field in (
                "tts_start_frame", "tts_clip_end_frame", "audible_speech_end_frame", "slack_frames"
            )):
                errors.append(f"{prefix} narration:none requires null TTS/audible/slack fields")

        is_final = cut.get("is_final")
        tail_exception = cut.get("tail_exception")
        if is_final is True:
            final_count += 1
            if index != len(cuts) - 1:
                errors.append(f"{prefix} is final but is not the last cut")
            if cut_id != final_cut_id:
                errors.append(f"{prefix}.cut_id must equal final_cut_id")
            if tail_exception is not True:
                errors.append(f"{prefix}.tail_exception must be true")
            if cut.get("next_cut_start_frame") is not None:
                errors.append(f"{prefix}.next_cut_start_frame must be null")
            if narration_target and cut["slack_frames"] != video_end - cut["audible_speech_end_frame"]:
                errors.append(f"{prefix}.slack_frames must equal video_end_frame - audible_speech_end_frame")
        elif is_final is False:
            next_start = cut.get("next_cut_start_frame")
            if not is_frame(next_start):
                errors.append(f"{prefix}.next_cut_start_frame must be a non-negative integer")
            elif video_end != next_start:
                errors.append(f"{prefix}.video_end_frame must equal next_cut_start_frame")
            if tail_exception is not False:
                errors.append(f"{prefix}.tail_exception must be false")
            if narration_target:
                if is_frame(next_start) and cut["slack_frames"] != next_start - cut["audible_speech_end_frame"]:
                    errors.append(f"{prefix}.slack_frames must equal next_cut_start_frame - audible_speech_end_frame")
                if cut["tts_clip_end_frame"] != video_end:
                    errors.append(f"{prefix}.tts_clip_end_frame must equal video_end_frame")
                if cut["slack_frames"] not in (0, 1):
                    errors.append(f"{prefix}.slack_frames must be 0 or 1 for a non-final cut")
        else:
            errors.append(f"{prefix}.is_final must be boolean")
        previous_end = video_end

    if final_count != 1:
        errors.append(f"exactly one final cut is required; found {final_count}")
    timeline_end = receipt.get("timeline_end_frame")
    if cuts and isinstance(cuts[-1], dict):
        if cuts[-1].get("video_end_frame") != timeline_end or cuts[-1].get("caption_end_frame") != timeline_end:
            errors.append("final video and caption must both persist through timeline_end_frame")
    return errors


def self_test() -> int:
    base = {
        "schema": SCHEMA,
        "case_id": "narration-none-case",
        "product_model": "AN-S182",
        "observed_at": "2026-08-31T22:00:00+09:00",
        "fps": 30,
        "final_cut_id": "cut-02",
        "playback_audio_relative_path": None,
        "playback_audio_sha256": None,
        "playback_audio_bytes": None,
        "playback_audio_duration_seconds": None,
        "playback_asr_relative_path": None,
        "playback_asr_sha256": None,
        "asr_first_speech_seconds": None,
        "asr_last_speech_seconds": None,
        "timeline_timecode": "00:00:20",
        "timeline_end_frame": 20,
        "readback_basis": "visual-only test",
        "cuts": [
            {"cut_id": "cut-01", "is_final": False, "narration_target": False,
             "timeline_start_frame": 0, "video_end_frame": 10, "caption_end_frame": 10,
             "tts_start_frame": None, "tts_clip_end_frame": None,
             "audible_speech_end_frame": None, "next_cut_start_frame": 10,
             "slack_frames": None, "tail_exception": False},
            {"cut_id": "cut-02", "is_final": True, "narration_target": False,
             "timeline_start_frame": 10, "video_end_frame": 20, "caption_end_frame": 20,
             "tts_start_frame": None, "tts_clip_end_frame": None,
             "audible_speech_end_frame": None, "next_cut_start_frame": None,
             "slack_frames": None, "tail_exception": True},
        ],
    }
    if validate(base):
        print("SELF-TEST FAILED: narration:none fixture rejected")
        return 1
    bad_tts = copy.deepcopy(base)
    bad_tts["cuts"][0]["tts_start_frame"] = 0
    if not validate(bad_tts):
        print("SELF-TEST FAILED: narration:none TTS mutation accepted")
        return 1
    bad_audio = copy.deepcopy(base)
    bad_audio["playback_audio_relative_path"] = "unexpected.wav"
    if not validate(bad_audio):
        print("SELF-TEST FAILED: narration:none playback-audio mutation accepted")
        return 1
    print("SELF-TEST PASSED: 3 narration:none cases")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", nargs="?", type=Path)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.receipt is None:
        parser.error("receipt is required unless --self-test is used")
    if args.project_root is None:
        parser.error("--project-root is required unless --self-test is used")
    try:
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    errors = validate(receipt, args.project_root)
    if errors:
        for error in errors:
            print(f"INVALID: {error}", file=sys.stderr)
        return 1
    print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
