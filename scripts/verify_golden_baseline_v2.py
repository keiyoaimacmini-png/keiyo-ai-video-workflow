#!/usr/bin/env python3
"""Fail-closed verifier for the accepted current AN-S182 Mac baseline v2."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = REPO / "golden-baselines/an-s182/v2"
REQUIRED_FILES = {
    "README_JA.md",
    "acceptance.json",
    "audio-layout.json",
    "baseline.manifest.json",
    "caption-style.json",
    "EVIDENCE.sha256",
    "environment.json",
    "export-settings.json",
    "material-map.json",
    "timeline.json",
    "windows-reproduction.md",
}
EXPECTED_JSON_SHA256 = {
    "acceptance.json": "037004563145d4b0270f4431e4ff29c42692070395a78c29725fdbdaa4630a84",
    "audio-layout.json": "3478c7923943604af109ee331bbae9163c620736cf305de19206ab804445717a",
    "baseline.manifest.json": "486e44305a330b70c198f5837b5ed11818e51567710390d7df61ca4ba3761543",
    "caption-style.json": "dddd0666564a9bb432b90cf6f5550f7e24bac27b9b28aa56e78f4c7baa24006f",
    "environment.json": "8233d92dd0134de39f82899b6cb5cb2510344be0d308ffb6f04875a7984fa8b7",
    "export-settings.json": "fcd0ecc75442fca7956cfd1cb506206fb9a672bf3c9ece234f2c00927983a3e9",
    "material-map.json": "3b0508f3a6de865b6b2baa867bf2a03bc9710800f0aa27daa934ae87db1a7113",
    "timeline.json": "4164b4a468a2a02672378c32416b41f4872f2c3834f84060bf0e82f04d632bdc",
}
EXPECTED_CUTS = [
    ("C1", 0, 60, [("IMG_3977.MOV", [2.0, 4.0])]),
    ("C2", 60, 120, [("IMG_3976.MOV", [6.5, 8.5])]),
    ("C3", 120, 180, [("IMG_3920.MOV", [3.6, 5.6])]),
    ("C4", 180, 270, [("IMG_3958.MOV", [0.0, 2.0]), ("IMG_3958.MOV", [2.0, 3.0])]),
    ("C5", 270, 360, [("IMG_3956.MOV", [0.2, 3.2])]),
    ("C6", 360, 450, [("IMG_3893.MOV", [0.0, 2.833])]),
    ("C7", 450, 540, [("IMG_0374.MOV", [0.0, 2.5]), ("IMG_0374.MOV", [2.4, 3.4])]),
    ("C8", 540, 630, [("IMG_0373.MOV", [68.0, 71.0])]),
    ("C9", 630, 750, [("IMG_3958.MOV", [0.2, 4.2])]),
    ("C10", 750, 891, [("IMG_3931.MOV", [0.0, 4.7])]),
]
EXPECTED_HOLDS = [
    "HOLD_WINDOWS_CAPCUT_ENVIRONMENT_NOT_VERIFIED",
    "HOLD_WINDOWS_SUBJECTIVE_AUDIO_EQUIVALENCE_NOT_AUDITIONED",
    "HOLD_DESIRED_EXPORT_FEATURES_UNAVAILABLE_ON_MAC",
    "HOLD_RIGHTS_PRIVACY_REVIEW",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item)


def verify_evidence(root: Path) -> list[str]:
    errors: list[str] = []
    entries: dict[str, str] = {}
    try:
        lines = (root / "EVIDENCE.sha256").read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [f"cannot read EVIDENCE.sha256: {exc}"]
    previous = ""
    for line_number, line in enumerate(lines, 1):
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        if not match:
            errors.append(f"EVIDENCE.sha256:{line_number}: invalid line")
            continue
        digest, name = match.groups()
        if name == "EVIDENCE.sha256" or name in entries:
            errors.append(f"EVIDENCE.sha256:{line_number}: invalid duplicate or self-reference")
        if previous and name <= previous:
            errors.append(f"EVIDENCE.sha256:{line_number}: not strictly sorted")
        previous = name
        entries[name] = digest
    if set(entries) != REQUIRED_FILES - {"EVIDENCE.sha256"}:
        errors.append("EVIDENCE.sha256 file set mismatch")
    for name, expected in entries.items():
        path = root / name
        if not path.is_file() or sha256(path) != expected:
            errors.append(f"evidence hash mismatch: {name}")
    return errors


def verify(root: Path = DEFAULT_ROOT, draft_info: Path | None = None) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    actual_files = {path.name for path in root.iterdir() if path.is_file()} if root.is_dir() else set()
    if actual_files != REQUIRED_FILES:
        errors.append("baseline file set mismatch")
    try:
        payloads = {
            name: load_json(root / name)
            for name in EXPECTED_JSON_SHA256
        }
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return errors + [f"cannot load baseline JSON: {exc}"]

    for name, expected in EXPECTED_JSON_SHA256.items():
        if sha256(root / name) != expected:
            errors.append(f"canonical JSON hash mismatch: {name}")

    manifest = payloads["baseline.manifest.json"]
    timeline = payloads["timeline.json"]
    materials = payloads["material-map.json"]
    captions = payloads["caption-style.json"]
    audio = payloads["audio-layout.json"]
    export_settings = payloads["export-settings.json"]
    acceptance = payloads["acceptance.json"]

    if manifest.get("baseline_id") != "an-s182-mac-capcut-current-v2":
        errors.append("baseline id mismatch")
    if manifest.get("status") != "accepted_mac_reference_pending_windows_validation":
        errors.append("baseline status mismatch")
    receipt = manifest.get("source_receipt") or {}
    if receipt.get("project_name") != "AI作成_AN-S182_2026_08_06" or receipt.get("source_project_modified") is not False:
        errors.append("source project receipt mismatch")
    characteristics = manifest.get("known_current_reference_characteristics") or []
    expected_characteristic = [{
        "from_cut": "C5",
        "to_cut": "C6",
        "overlap_frames": 1,
        "status": "accepted_reference_characteristic",
    }]
    if characteristics != expected_characteristic:
        errors.append("accepted reference characteristic mismatch")

    if (
        timeline.get("fps") != 30.0
        or timeline.get("duration_frames") != 891
        or timeline.get("logical_cut_count") != 10
        or timeline.get("physical_video_segment_count") != 12
    ):
        errors.append("timeline top-level mismatch")
    overlaps = timeline.get("caption_overlaps") or []
    if [(row.get("from_cut"), row.get("to_cut"), row.get("overlap_frames")) for row in overlaps] != [("C5", "C6", 1)]:
        errors.append("caption overlap mismatch")
    cuts = timeline.get("cuts") or []
    material_rows = materials.get("materials") or []
    if len(cuts) != 10 or len(material_rows) != 10:
        errors.append("cut or material count mismatch")
    else:
        for cut, material, expected in zip(cuts, material_rows, EXPECTED_CUTS):
            cut_id, start, end, expected_assets = expected
            if (cut.get("cut_id"), cut.get("logical_start_frame"), cut.get("logical_end_frame")) != (cut_id, start, end):
                errors.append(f"cut boundary mismatch: {cut_id}")
            timeline_assets = [
                (row.get("asset_ref"), row.get("source_range_seconds"))
                for row in cut.get("physical_segments") or []
            ]
            material_assets = [
                (row.get("original_filename"), row.get("original_source_range_seconds"))
                for row in material.get("assets") or []
            ]
            if timeline_assets != expected_assets or material_assets != expected_assets:
                errors.append(f"material mapping mismatch: {cut_id}")
            if not material.get("must_show") or not material.get("must_not_show"):
                errors.append(f"semantic selection rules missing: {cut_id}")
            if any(row.get("reproduction_source_status") != "verified" for row in material.get("assets") or []):
                errors.append(f"material receipt not verified: {cut_id}")

    caption_rows = captions.get("captions") or []
    if captions.get("caption_count") != 10 or len(caption_rows) != 10:
        errors.append("caption count mismatch")
    elif caption_rows[-1].get("text") != "下のカートから\nチェックして":
        errors.append("final caption mismatch")
    if audio.get("tts_count") != 10 or len(audio.get("tts") or []) != 10:
        errors.append("TTS count mismatch")
    if audio.get("sfx_count") != 5 or len(audio.get("sfx") or []) != 5:
        errors.append("SFX count mismatch")
    if audio.get("source_audio_all_zero") is not True or audio.get("bgm_policy") != "none" or audio.get("other_audio") != []:
        errors.append("audio policy mismatch")
    if any(row.get("voice_label") != "ホリデーツイスト" for row in audio.get("tts") or []):
        errors.append("TTS voice mismatch")

    desired = export_settings.get("desired_target") or {}
    observed_export = export_settings.get("accepted_mac_export_observed") or {}
    if desired != {
        "ai_uhd_enabled": True,
        "resolution": "4K",
        "frame_rate_fps": 30,
        "optical_flow_enabled": True,
        "bitrate_mbps": 100,
        "smart_hdr_enabled": True,
    }:
        errors.append("desired export target mismatch")
    if (
        observed_export.get("resolution_pixels") != "2160x3840"
        or observed_export.get("frame_rate_fps") != 30
        or observed_export.get("bitrate_target_mbps") != 100
        or observed_export.get("codec") != "H.264"
        or observed_export.get("color_space") != "Rec.709 SDR"
        or observed_export.get("user_confirmed_drive_playback") is not True
        or observed_export.get("local_export_removed_after_user_approval") is not True
    ):
        errors.append("accepted Mac export receipt mismatch")

    if acceptance.get("decision") != "user_accepted_current_mac_reference" or acceptance.get("machine_result") != "HOLD":
        errors.append("acceptance decision mismatch")
    if [row.get("code") for row in acceptance.get("holds") or []] != EXPECTED_HOLDS:
        errors.append("acceptance holds mismatch")
    exact = acceptance.get("exact_checks") or {}
    if exact.get("c4_sources") != [["IMG_3958.MOV", 0.0, 2.0], ["IMG_3958.MOV", 2.0, 3.0]]:
        errors.append("accepted C4 source mismatch")
    if exact.get("c6_source") != ["IMG_3893.MOV", 0.0, 2.833]:
        errors.append("accepted C6 source mismatch")
    if acceptance.get("external_effects_authorized") is not False:
        errors.append("external effect gate mismatch")

    forbidden_patterns = [
        re.compile(r"/Users/", re.I),
        re.compile(r"[A-Z]:\\"),
        re.compile(r"https://drive\.google\.com/drive/folders/", re.I),
        re.compile(r"(?:^|[/\\])\.local(?:[/\\]|$)"),
    ]
    for name, payload in payloads.items():
        if any(any(pattern.search(value) for pattern in forbidden_patterns) for value in iter_strings(payload)):
            errors.append(f"non-portable or private value in {name}")

    errors.extend(verify_evidence(root))
    if draft_info is not None:
        expected_hash = receipt.get("draft_info_sha256")
        if not draft_info.is_file() or sha256(draft_info) != expected_hash:
            errors.append("current draft_info SHA-256 mismatch")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--draft-info", type=Path)
    args = parser.parse_args()
    errors = verify(args.root, args.draft_info)
    if errors:
        print("INVALID_GOLDEN_BASELINE_V2")
        for error in sorted(set(errors)):
            print(f"- {error}")
        return 1
    print("PASS_GOLDEN_BASELINE_V2 status=HOLD known_holds=4 media_embedded=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
