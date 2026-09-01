#!/usr/bin/env python3
"""Validate all-cut source/caption/TTS presence, rendering, mute, and playback evidence."""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import sys
import tempfile
import wave
from datetime import datetime
from pathlib import Path

from validate_nonfinal_slack import validate as validate_nonfinal_slack
from validate_track_pairing import jpeg_dimensions, validate as validate_track_pairing


SCHEMA = "product_video_timeline_integrity_receipt.v1"
SHA_CHARS = set("0123456789abcdef")
TOP_KEYS = {
    "schema", "case_id", "product_model", "observed_at", "fps",
    "final_cut_id", "timeline_end_frame", "linked_receipts", "counts",
    "frame_evidence", "cuts", "full_playback", "integrity_result",
}
LINKED_KEYS = {"nonfinal_slack", "track_pairing"}
LINK_KEYS = {"path", "sha256"}
COUNT_KEYS = {"sources", "captions", "narration_targets", "tts"}
EVIDENCE_KEYS = {
    "evidence_id", "relative_path", "sha256", "byte_size", "mime_type",
    "width", "height", "cut_id", "position", "frame", "source_rendered",
    "black_frame", "caption_rendered", "visible_caption_layer_count",
}
CUT_KEYS = {
    "cut_id", "is_final", "narration_target", "source_asset_id",
    "source_media_sha256", "source_clip_identity_sha256s",
    "caption_clip_identity_sha256", "tts_clip_identity_sha256",
    "source_start_frame", "source_end_frame", "caption_start_frame",
    "caption_end_frame", "tts_start_frame", "tts_end_frame",
    "source_clip_present", "caption_clip_present", "tts_clip_present",
    "source_audio_muted", "mute_mechanism", "mute_readback",
    "observed_action_match",
}
MUTE_READBACK_KEYS = {"control", "state", "gain_db"}
PLAYBACK_KEYS = {
    "start_frame", "end_frame", "uninterrupted",
    "all_cut_boundaries_observed_during_playback", "black_interval_detected",
    "missing_narration_detected", "unexpected_source_audio_detected",
    "duplicate_caption_detected", "truncation_detected", "overlap_detected",
    "observed_narration_cut_ids", "same_project_reloaded",
    "post_reload_playback_completed",
}
POSITIONS = ("start_after_boundary", "midpoint", "last_valid")


def is_sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= SHA_CHARS


def is_frame(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def safe_file(root: Path, relative: object) -> tuple[Path | None, str | None]:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        return None, "must be a non-empty relative path"
    target = (root / relative).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None, "must stay under project root"
    if target.is_symlink():
        return None, "must not be a symlink"
    return target, None


def read_linked(
    receipt: dict,
    project_root: Path | None,
    errors: list[str],
) -> tuple[dict | None, dict | None]:
    linked = receipt.get("linked_receipts")
    if not isinstance(linked, dict) or set(linked) != LINKED_KEYS:
        errors.append(f"linked_receipts must contain exactly {sorted(LINKED_KEYS)}")
        return None, None
    loaded: dict[str, dict | None] = {key: None for key in LINKED_KEYS}
    for key in sorted(LINKED_KEYS):
        record = linked.get(key)
        if not isinstance(record, dict) or set(record) != LINK_KEYS:
            errors.append(f"linked_receipts.{key} must contain exactly {sorted(LINK_KEYS)}")
            continue
        if not is_sha(record.get("sha256")):
            errors.append(f"linked_receipts.{key}.sha256 must be lowercase SHA-256")
        if project_root is None:
            continue
        target, path_error = safe_file(project_root, record.get("path"))
        if path_error:
            errors.append(f"linked_receipts.{key}.path {path_error}")
            continue
        try:
            raw = target.read_bytes()
            parsed = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"linked_receipts.{key} is unreadable JSON: {exc}")
            continue
        if hashlib.sha256(raw).hexdigest() != record.get("sha256"):
            errors.append(f"linked_receipts.{key} SHA-256 mismatch")
        nested_errors = (
            validate_nonfinal_slack(parsed, project_root)
            if key == "nonfinal_slack"
            else validate_track_pairing(parsed, project_root)
        )
        if nested_errors:
            errors.extend(f"linked_receipts.{key}: {item}" for item in nested_errors)
        loaded[key] = parsed
    return loaded["nonfinal_slack"], loaded["track_pairing"]


def validate(receipt: object, project_root: Path | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(receipt, dict):
        return ["receipt must be an object"]
    if set(receipt) != TOP_KEYS:
        return [f"top-level keys must equal {sorted(TOP_KEYS)}"]
    if project_root is None:
        errors.append("project_root is required to validate linked receipts and evidence bytes")
    if receipt["schema"] != SCHEMA:
        errors.append(f"schema must equal {SCHEMA}")
    for field in ("case_id", "product_model", "final_cut_id"):
        if not isinstance(receipt[field], str) or not receipt[field]:
            errors.append(f"{field} must be a non-empty string")
    try:
        observed = datetime.fromisoformat(receipt["observed_at"])
        if observed.utcoffset() is None:
            raise ValueError("timezone missing")
    except (TypeError, ValueError):
        errors.append("observed_at must be an offset-aware ISO-8601 timestamp")
    fps = receipt["fps"]
    if not isinstance(fps, int) or isinstance(fps, bool) or fps <= 0:
        errors.append("fps must be a positive integer")
    if not is_frame(receipt["timeline_end_frame"]):
        errors.append("timeline_end_frame must be a non-negative integer")

    slack, pairing = read_linked(receipt, project_root, errors)

    counts = receipt["counts"]
    if not isinstance(counts, dict) or set(counts) != COUNT_KEYS:
        errors.append(f"counts must contain exactly {sorted(COUNT_KEYS)}")
        counts = {}
    elif any(not isinstance(counts[key], int) or isinstance(counts[key], bool) or counts[key] < 0 for key in COUNT_KEYS):
        errors.append("all counts must be non-negative integers")

    evidence = receipt["frame_evidence"]
    evidence_by_cut: dict[str, dict[str, dict]] = {}
    evidence_ids: set[str] = set()
    evidence_hashes: set[str] = set()
    if not isinstance(evidence, list) or not evidence:
        errors.append("frame_evidence must be a non-empty array")
        evidence = []
    for index, item in enumerate(evidence):
        prefix = f"frame_evidence[{index}]"
        if not isinstance(item, dict) or set(item) != EVIDENCE_KEYS:
            errors.append(f"{prefix} must contain exactly {sorted(EVIDENCE_KEYS)}")
            continue
        evidence_id = item["evidence_id"]
        cut_id = item["cut_id"]
        position = item["position"]
        if not isinstance(evidence_id, str) or not evidence_id or evidence_id in evidence_ids:
            errors.append(f"{prefix}.evidence_id must be unique and non-empty")
            continue
        evidence_ids.add(evidence_id)
        if not isinstance(cut_id, str) or not cut_id:
            errors.append(f"{prefix}.cut_id must be non-empty")
            continue
        if position not in POSITIONS:
            errors.append(f"{prefix}.position must be one of {POSITIONS}")
            continue
        if position in evidence_by_cut.setdefault(cut_id, {}):
            errors.append(f"{prefix} duplicates {cut_id}:{position}")
        evidence_by_cut[cut_id][position] = item
        if not is_frame(item["frame"]):
            errors.append(f"{prefix}.frame must be a non-negative integer")
        if not is_sha(item["sha256"]):
            errors.append(f"{prefix}.sha256 must be lowercase SHA-256")
        elif item["sha256"] in evidence_hashes:
            errors.append(f"{prefix}.sha256 must be unique across observed frames")
        else:
            evidence_hashes.add(item["sha256"])
        if not isinstance(item["byte_size"], int) or item["byte_size"] <= 0:
            errors.append(f"{prefix}.byte_size must be positive")
        if item["mime_type"] != "image/jpeg":
            errors.append(f"{prefix}.mime_type must equal image/jpeg")
        if item["source_rendered"] is not True or item["black_frame"] is not False:
            errors.append(f"{prefix} must prove a rendered, non-black source frame")
        if item["caption_rendered"] is not True or item["visible_caption_layer_count"] != 1:
            errors.append(f"{prefix} must prove exactly one rendered caption layer")
        if project_root is not None:
            target, path_error = safe_file(project_root, item["relative_path"])
            if path_error or Path(item["relative_path"]).suffix.lower() not in {".jpg", ".jpeg"}:
                errors.append(f"{prefix}.relative_path must be a safe .jpg/.jpeg path")
            else:
                try:
                    raw = target.read_bytes()
                except OSError as exc:
                    errors.append(f"{prefix} evidence is unreadable: {exc}")
                else:
                    if len(raw) != item["byte_size"]:
                        errors.append(f"{prefix} byte size mismatch")
                    if hashlib.sha256(raw).hexdigest() != item["sha256"]:
                        errors.append(f"{prefix} SHA-256 mismatch")
                    dimensions = jpeg_dimensions(raw)
                    if dimensions is None:
                        errors.append(f"{prefix} is not a decodable JPEG structure")
                    elif dimensions != (item["width"], item["height"]):
                        errors.append(f"{prefix} JPEG dimensions mismatch")

    cuts = receipt["cuts"]
    if not isinstance(cuts, list) or not cuts:
        errors.append("cuts must be a non-empty array")
        cuts = []
    cut_ids: list[str] = []
    narration_ids: list[str] = []
    media_shas: set[str] = set()
    source_clip_shas: set[str] = set()
    caption_clip_shas: set[str] = set()
    tts_clip_shas: set[str] = set()
    final_count = 0
    previous_end: int | None = None
    for index, cut in enumerate(cuts):
        prefix = f"cuts[{index}]"
        if not isinstance(cut, dict) or set(cut) != CUT_KEYS:
            errors.append(f"{prefix} must contain exactly {sorted(CUT_KEYS)}")
            continue
        cut_id = cut["cut_id"]
        if not isinstance(cut_id, str) or not cut_id or cut_id in cut_ids:
            errors.append(f"{prefix}.cut_id must be unique and non-empty")
            continue
        cut_ids.append(cut_id)
        is_final = cut["is_final"]
        if not isinstance(is_final, bool):
            errors.append(f"{prefix}.is_final must be boolean")
        elif is_final:
            final_count += 1
            if index != len(cuts) - 1 or cut_id != receipt["final_cut_id"]:
                errors.append(f"{prefix} final cut must be last and match final_cut_id")
        for presence in ("source_clip_present", "caption_clip_present"):
            if cut[presence] is not True:
                errors.append(f"{prefix}.{presence} must be true")
        if not isinstance(cut["source_asset_id"], str) or not cut["source_asset_id"]:
            errors.append(f"{prefix}.source_asset_id must be non-empty")
        media_sha = cut["source_media_sha256"]
        if not is_sha(media_sha) or media_sha in media_shas:
            errors.append(f"{prefix}.source_media_sha256 must be unique lowercase SHA-256")
        else:
            media_shas.add(media_sha)
        source_identities = cut["source_clip_identity_sha256s"]
        if not isinstance(source_identities, list) or not source_identities:
            errors.append(f"{prefix}.source_clip_identity_sha256s must be non-empty")
        else:
            for identity in source_identities:
                if not is_sha(identity) or identity in source_clip_shas:
                    errors.append(f"{prefix} source clip identities must be unique lowercase SHA-256")
                else:
                    source_clip_shas.add(identity)
        caption_identity = cut["caption_clip_identity_sha256"]
        if not is_sha(caption_identity) or caption_identity in caption_clip_shas:
            errors.append(f"{prefix}.caption_clip_identity_sha256 must be unique lowercase SHA-256")
        else:
            caption_clip_shas.add(caption_identity)
        frame_fields = ("source_start_frame", "source_end_frame", "caption_start_frame", "caption_end_frame")
        if any(not is_frame(cut[field]) for field in frame_fields):
            errors.append(f"{prefix} source/caption frames must be non-negative integers")
            continue
        start = cut["source_start_frame"]
        end = cut["source_end_frame"]
        if end <= start:
            errors.append(f"{prefix} source range must have positive duration")
        if previous_end is not None and start != previous_end:
            errors.append(f"{prefix} must start at previous source end")
        if cut["caption_start_frame"] != start or cut["caption_end_frame"] != end:
            errors.append(f"{prefix} source and caption edges must match exactly")
        mechanism = cut["mute_mechanism"]
        if cut["source_audio_muted"] is not True or mechanism not in {"track_mute", "clip_mute"}:
            errors.append(f"{prefix} source audio must use exact track_mute or clip_mute")
        mute_readback = cut["mute_readback"]
        if not isinstance(mute_readback, dict) or set(mute_readback) != MUTE_READBACK_KEYS:
            errors.append(f"{prefix}.mute_readback must contain exactly {sorted(MUTE_READBACK_KEYS)}")
        else:
            expected_control = {
                "track_mute": "track_mute_control",
                "clip_mute": "clip_mute_control",
            }.get(mechanism)
            if mute_readback["control"] != expected_control:
                errors.append(f"{prefix}.mute_readback.control must match mute_mechanism")
            if mute_readback["state"] != "muted" or mute_readback["gain_db"] is not None:
                errors.append(f"{prefix}.mute_readback must prove muted state without gain attenuation")
        if cut["observed_action_match"] is not True:
            errors.append(f"{prefix}.observed_action_match must be true")

        narration = cut["narration_target"]
        if not isinstance(narration, bool):
            errors.append(f"{prefix}.narration_target must be boolean")
        elif narration:
            narration_ids.append(cut_id)
            if cut["tts_clip_present"] is not True:
                errors.append(f"{prefix}.tts_clip_present must be true")
            tts_identity = cut["tts_clip_identity_sha256"]
            if not is_sha(tts_identity) or tts_identity in tts_clip_shas:
                errors.append(f"{prefix}.tts_clip_identity_sha256 must be unique lowercase SHA-256")
            else:
                tts_clip_shas.add(tts_identity)
            if not is_frame(cut["tts_start_frame"]) or not is_frame(cut["tts_end_frame"]):
                errors.append(f"{prefix} TTS frames must be non-negative integers")
            else:
                if cut["tts_start_frame"] != start:
                    errors.append(f"{prefix}.tts_start_frame must equal source start")
                if is_final:
                    if not start < cut["tts_end_frame"] <= end:
                        errors.append(f"{prefix} final TTS must end within the final source/caption range")
                elif cut["tts_end_frame"] != end:
                    errors.append(f"{prefix} non-final TTS end must equal source/caption end")
        else:
            if any(cut[field] is not None for field in ("tts_clip_identity_sha256", "tts_start_frame", "tts_end_frame")):
                errors.append(f"{prefix} non-narration cut must have null TTS identity/start/end")
            if cut["tts_clip_present"] is not False:
                errors.append(f"{prefix}.tts_clip_present must be false for non-narration")

        expected_frames = {
            "start_after_boundary": start,
            "midpoint": start + (end - start - 1) // 2,
            "last_valid": end - 1,
        }
        observed_positions = evidence_by_cut.get(cut_id, {})
        if set(observed_positions) != set(POSITIONS):
            errors.append(f"{prefix} must have exactly start, midpoint, and last-valid frame evidence")
        else:
            for position, expected in expected_frames.items():
                if observed_positions[position]["frame"] != expected:
                    errors.append(f"{prefix} {position} evidence must be frame {expected}")
        previous_end = end

    if final_count != 1:
        errors.append(f"exactly one final cut is required; found {final_count}")
    if cuts and cuts[-1].get("source_end_frame") != receipt["timeline_end_frame"]:
        errors.append("last source end must equal timeline_end_frame")
    if set(evidence_by_cut) != set(cut_ids):
        errors.append("frame evidence cut IDs must exactly equal receipt cut IDs")
    expected_counts = {
        "sources": len(cut_ids), "captions": len(cut_ids),
        "narration_targets": len(narration_ids), "tts": len(tts_clip_shas),
    }
    if counts and counts != expected_counts:
        errors.append(f"counts must equal {expected_counts}")

    playback = receipt["full_playback"]
    if not isinstance(playback, dict) or set(playback) != PLAYBACK_KEYS:
        errors.append(f"full_playback must contain exactly {sorted(PLAYBACK_KEYS)}")
    else:
        if playback["start_frame"] != 0 or playback["end_frame"] != receipt["timeline_end_frame"]:
            errors.append("full playback must cover frame 0 through timeline_end_frame")
        required_true = (
            "uninterrupted", "all_cut_boundaries_observed_during_playback",
            "same_project_reloaded", "post_reload_playback_completed",
        )
        required_false = (
            "black_interval_detected", "missing_narration_detected",
            "unexpected_source_audio_detected", "duplicate_caption_detected",
            "truncation_detected", "overlap_detected",
        )
        for field in required_true:
            if playback[field] is not True:
                errors.append(f"full_playback.{field} must be true")
        for field in required_false:
            if playback[field] is not False:
                errors.append(f"full_playback.{field} must be false")
        if playback["observed_narration_cut_ids"] != narration_ids:
            errors.append("observed_narration_cut_ids must exactly equal narration targets in order")

    for name, nested in (("nonfinal_slack", slack), ("track_pairing", pairing)):
        if nested is None:
            continue
        for field in ("case_id", "product_model", "fps", "final_cut_id", "timeline_end_frame"):
            if field in nested and nested[field] != receipt[field]:
                errors.append(f"linked_receipts.{name}.{field} mismatch")
        nested_cuts = nested.get("cuts", [])
        if [item.get("cut_id") for item in nested_cuts] != cut_ids:
            errors.append(f"linked_receipts.{name} cut order mismatch")
    if pairing is not None:
        for current, paired in zip(cuts, pairing.get("cuts", [])):
            if current.get("source_asset_id") != paired.get("source_asset_id"):
                errors.append(f"{current.get('cut_id')} source_asset_id disagrees with track pairing")
            for current_field, paired_field in (
                ("source_start_frame", "source_start_frame"),
                ("source_end_frame", "source_end_frame"),
                ("caption_start_frame", "caption_start_frame"),
                ("caption_end_frame", "caption_end_frame"),
            ):
                if current.get(current_field) != paired.get(paired_field):
                    errors.append(f"{current.get('cut_id')} {current_field} disagrees with track pairing")
    if slack is not None:
        for current, timed in zip(cuts, slack.get("cuts", [])):
            if current.get("narration_target") != timed.get("narration_target", True):
                errors.append(f"{current.get('cut_id')} narration_target disagrees with nonfinal slack")
            comparisons = (
                ("source_start_frame", "timeline_start_frame"),
                ("source_end_frame", "video_end_frame"),
                ("caption_end_frame", "caption_end_frame"),
                ("tts_start_frame", "tts_start_frame"),
                ("tts_end_frame", "tts_clip_end_frame"),
            )
            for current_field, timed_field in comparisons:
                if current.get(current_field) != timed.get(timed_field):
                    errors.append(f"{current.get('cut_id')} {current_field} disagrees with nonfinal slack")

    if receipt["integrity_result"] != "PASS_ALL_CUTS_RENDERED_SYNCED_MUTED_PLAYED_RELOADED":
        errors.append("integrity_result must equal PASS_ALL_CUTS_RENDERED_SYNCED_MUTED_PLAYED_RELOADED")
    return errors


def self_test() -> int:
    jpeg = base64.b64decode(
        "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABBQJ//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAwEBPwF//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAgEBPwF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQAGPwJ//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPyF//9oADAMBAAIAAwAAAB//xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/EH//xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/EH//xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/EH//2Q=="
    )
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        images: list[tuple[str, bytes]] = []
        for index in range(10):
            name = f"frame-{index}.jpg"
            raw = jpeg + bytes([index])
            (root / name).write_bytes(raw)
            images.append((name, raw))

        wav_path = root / "playback.wav"
        with wave.open(str(wav_path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8000)
            handle.writeframes(b"\0\0" * 8000)
        asr_path = root / "playback.json"
        asr_path.write_text(json.dumps({"segments": [{"start": 0.0, "end": 0.5}]}), encoding="utf-8")

        slack = {
            "schema": "product_video_nonfinal_slack_receipt.v1", "case_id": "case",
            "product_model": "AN-S182", "observed_at": "2026-08-31T18:00:00+09:00",
            "fps": 30, "final_cut_id": "cut-02", "playback_audio_relative_path": wav_path.name,
            "playback_audio_sha256": hashlib.sha256(wav_path.read_bytes()).hexdigest(),
            "playback_audio_bytes": wav_path.stat().st_size, "playback_audio_duration_seconds": 1.0,
            "playback_asr_relative_path": asr_path.name,
            "playback_asr_sha256": hashlib.sha256(asr_path.read_bytes()).hexdigest(),
            "asr_first_speech_seconds": 0.0, "asr_last_speech_seconds": 0.5,
            "timeline_timecode": "00:00:20", "timeline_end_frame": 20,
            "readback_basis": "test",
            "cuts": [
                {"cut_id": "cut-01", "is_final": False, "narration_target": True, "timeline_start_frame": 0,
                 "video_end_frame": 10, "caption_end_frame": 10, "tts_start_frame": 0,
                 "tts_clip_end_frame": 10, "audible_speech_end_frame": 10,
                 "next_cut_start_frame": 10, "slack_frames": 0, "tail_exception": False},
                {"cut_id": "cut-02", "is_final": True, "narration_target": True, "timeline_start_frame": 10,
                 "video_end_frame": 20, "caption_end_frame": 20, "tts_start_frame": 10,
                 "tts_clip_end_frame": 16, "audible_speech_end_frame": 16,
                 "next_cut_start_frame": None, "slack_frames": 4, "tail_exception": True},
            ],
        }
        slack_path = root / "slack.json"
        slack_path.write_text(json.dumps(slack), encoding="utf-8")

        pairing_evidence = []
        coverage = (("cut-01:head", 0), ("cut-01:tail", 10), ("cut-02:head", 10), ("cut-02:tail", 20))
        for index, (edge, frame) in enumerate(coverage):
            name, raw = images[index]
            pairing_evidence.append({
                "evidence_id": f"pair-{index}", "relative_path": name,
                "sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw),
                "mime_type": "image/jpeg", "width": 1, "height": 1,
                "boundary_frame": frame, "track_group": "front", "coverage": [edge],
            })
        pairing = {
            "schema": "product_video_track_pairing_receipt.v2", "case_id": "case",
            "product_model": "AN-S182", "observed_at": "2026-08-31T18:00:00+09:00",
            "fps": 30, "timeline_end_frame": 20,
            "supersedes": {"path": "old.json", "sha256": "0" * 64, "reason": "test"},
            "boundary_readback_basis": {"editor_zoom": "frame-level", "ruler_tick_frames": 3,
                "minimum_pixels_per_frame": 36.0, "edge_alignment_method": "same viewport"},
            "evidence": pairing_evidence,
            "cuts": [
                {"cut_id": "cut-01", "source_asset_id": "asset-1", "source_start_frame": 0,
                 "source_end_frame": 10, "caption_start_frame": 0, "caption_end_frame": 10,
                 "head_delta_frames": 0, "tail_delta_frames": 0, "head_evidence_id": "pair-0",
                 "tail_evidence_id": "pair-1", "source_edge_readback": "source",
                 "caption_edge_readback": "caption", "template_animation_seconds": 0.1,
                 "clip_edge_result": "PASS", "render_animation_checked_separately": True},
                {"cut_id": "cut-02", "source_asset_id": "asset-2", "source_start_frame": 10,
                 "source_end_frame": 20, "caption_start_frame": 10, "caption_end_frame": 20,
                 "head_delta_frames": 0, "tail_delta_frames": 0, "head_evidence_id": "pair-2",
                 "tail_evidence_id": "pair-3", "source_edge_readback": "source",
                 "caption_edge_readback": "caption", "template_animation_seconds": 0.1,
                 "clip_edge_result": "PASS", "render_animation_checked_separately": True},
            ],
            "pairing_result": "PASS_ALL_CUTS_EXACT_EDGES_FRAME_LEVEL",
        }
        pairing_path = root / "pairing.json"
        pairing_path.write_text(json.dumps(pairing), encoding="utf-8")

        frames = []
        positions = (("cut-01", 0, 10), ("cut-02", 10, 20))
        image_index = 4
        for cut_id, start, end in positions:
            for position, frame in (
                ("start_after_boundary", start),
                ("midpoint", start + (end - start - 1) // 2),
                ("last_valid", end - 1),
            ):
                name, raw = images[image_index]
                image_index += 1
                frames.append({
                    "evidence_id": f"render-{cut_id}-{position}", "relative_path": name,
                    "sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw),
                    "mime_type": "image/jpeg", "width": 1, "height": 1,
                    "cut_id": cut_id, "position": position, "frame": frame,
                    "source_rendered": True, "black_frame": False,
                    "caption_rendered": True, "visible_caption_layer_count": 1,
                })

        base = {
            "schema": SCHEMA, "case_id": "case", "product_model": "AN-S182",
            "observed_at": "2026-08-31T18:00:00+09:00", "fps": 30,
            "final_cut_id": "cut-02", "timeline_end_frame": 20,
            "linked_receipts": {
                "nonfinal_slack": {"path": slack_path.name, "sha256": hashlib.sha256(slack_path.read_bytes()).hexdigest()},
                "track_pairing": {"path": pairing_path.name, "sha256": hashlib.sha256(pairing_path.read_bytes()).hexdigest()},
            },
            "counts": {"sources": 2, "captions": 2, "narration_targets": 2, "tts": 2},
            "frame_evidence": frames,
            "cuts": [
                {"cut_id": "cut-01", "is_final": False, "narration_target": True,
                 "source_asset_id": "asset-1", "source_media_sha256": "1" * 64,
                 "source_clip_identity_sha256s": ["2" * 64], "caption_clip_identity_sha256": "3" * 64,
                 "tts_clip_identity_sha256": "4" * 64, "source_start_frame": 0,
                 "source_end_frame": 10, "caption_start_frame": 0, "caption_end_frame": 10,
                 "tts_start_frame": 0, "tts_end_frame": 10, "source_clip_present": True,
                 "caption_clip_present": True, "tts_clip_present": True,
                 "source_audio_muted": True, "mute_mechanism": "track_mute",
                 "mute_readback": {"control": "track_mute_control", "state": "muted", "gain_db": None},
                 "observed_action_match": True},
                {"cut_id": "cut-02", "is_final": True, "narration_target": True,
                 "source_asset_id": "asset-2", "source_media_sha256": "5" * 64,
                 "source_clip_identity_sha256s": ["6" * 64], "caption_clip_identity_sha256": "7" * 64,
                 "tts_clip_identity_sha256": "8" * 64, "source_start_frame": 10,
                 "source_end_frame": 20, "caption_start_frame": 10, "caption_end_frame": 20,
                 "tts_start_frame": 10, "tts_end_frame": 16, "source_clip_present": True,
                 "caption_clip_present": True, "tts_clip_present": True,
                 "source_audio_muted": True, "mute_mechanism": "clip_mute",
                 "mute_readback": {"control": "clip_mute_control", "state": "muted", "gain_db": None},
                 "observed_action_match": True},
            ],
            "full_playback": {"start_frame": 0, "end_frame": 20, "uninterrupted": True,
                "all_cut_boundaries_observed_during_playback": True, "black_interval_detected": False,
                "missing_narration_detected": False, "unexpected_source_audio_detected": False,
                "duplicate_caption_detected": False, "truncation_detected": False,
                "overlap_detected": False, "observed_narration_cut_ids": ["cut-01", "cut-02"],
                "same_project_reloaded": True, "post_reload_playback_completed": True},
            "integrity_result": "PASS_ALL_CUTS_RENDERED_SYNCED_MUTED_PLAYED_RELOADED",
        }
        if validate(base, root):
            print("SELF-TEST FAILED: valid fixture rejected")
            for error in validate(base, root):
                print(error)
            return 1

        none_slack = copy.deepcopy(slack)
        for cut in none_slack["cuts"]:
            cut["narration_target"] = False
            for field in ("tts_start_frame", "tts_clip_end_frame", "audible_speech_end_frame", "slack_frames"):
                cut[field] = None
        for field in (
            "playback_audio_relative_path", "playback_audio_sha256", "playback_audio_bytes",
            "playback_audio_duration_seconds", "playback_asr_relative_path", "playback_asr_sha256",
            "asr_first_speech_seconds", "asr_last_speech_seconds",
        ):
            none_slack[field] = None
        none_slack_path = root / "slack-none.json"
        none_slack_path.write_text(json.dumps(none_slack), encoding="utf-8")
        none_base = copy.deepcopy(base)
        none_base["linked_receipts"]["nonfinal_slack"] = {
            "path": none_slack_path.name,
            "sha256": hashlib.sha256(none_slack_path.read_bytes()).hexdigest(),
        }
        none_base["counts"].update({"narration_targets": 0, "tts": 0})
        for cut in none_base["cuts"]:
            cut["narration_target"] = False
            cut["tts_clip_identity_sha256"] = None
            cut["tts_start_frame"] = None
            cut["tts_end_frame"] = None
            cut["tts_clip_present"] = False
        none_base["full_playback"]["observed_narration_cut_ids"] = []
        if validate(none_base, root):
            print("SELF-TEST FAILED: narration:none integrity fixture rejected")
            for error in validate(none_base, root):
                print(error)
            return 1

        cases: list[tuple[str, dict]] = []
        for name in ("source-missing", "black-frame", "not-muted", "duplicate-caption",
                     "tts-missing", "boundary", "evidence-reuse", "playback", "media-reuse",
                     "attenuated-readback", "source-identity"):
            cases.append((name, copy.deepcopy(base)))
        cases[0][1]["cuts"][0]["source_clip_present"] = False
        cases[1][1]["frame_evidence"][0]["black_frame"] = True
        cases[2][1]["cuts"][0]["source_audio_muted"] = False
        cases[3][1]["frame_evidence"][0]["visible_caption_layer_count"] = 2
        cases[4][1]["cuts"][0]["tts_clip_present"] = False
        cases[5][1]["cuts"][0]["caption_end_frame"] = 9
        cases[6][1]["frame_evidence"][1]["sha256"] = cases[6][1]["frame_evidence"][0]["sha256"]
        cases[7][1]["full_playback"]["post_reload_playback_completed"] = False
        cases[8][1]["cuts"][1]["source_media_sha256"] = cases[8][1]["cuts"][0]["source_media_sha256"]
        cases[9][1]["cuts"][0]["mute_readback"] = {
            "control": "track_mute_control", "state": "attenuated", "gain_db": -60.1,
        }
        cases[10][1]["cuts"][0]["source_asset_id"] = "wrong-asset"
        for name, bad in cases:
            if not validate(bad, root):
                print(f"SELF-TEST FAILED: {name} mutation accepted")
                return 1
        if not validate(base, None):
            print("SELF-TEST FAILED: missing project root accepted")
            return 1
    print(f"SELF-TEST PASSED: {3 + len(cases)} cases")
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
