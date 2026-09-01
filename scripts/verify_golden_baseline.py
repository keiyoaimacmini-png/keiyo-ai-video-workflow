#!/usr/bin/env python3
"""Fail-closed verifier for the media-free AN-S182 CapCut golden baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = REPO / "golden-baselines/an-s182/v1"
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
    "baseline.manifest.json": "d4721a2997abd4a16a570ccdc29142a24b608c9a13acc28c8be7c228cb09a8c4",
    "timeline.json": "e2813116a04b9ccf128a3aa1c1d5531161d6b9fa862738d8035c00a7dfab18e2",
    "material-map.json": "f7e149c04e0d71ecb506ce1c6dc7fb0ec1c8a2bcac65ed0c6d84a08caf988a3b",
    "caption-style.json": "dddd0666564a9bb432b90cf6f5550f7e24bac27b9b28aa56e78f4c7baa24006f",
    "audio-layout.json": "a18c917fdc71cbaaccd443631e1578d290e2299f245a3f325f36fb6c735f3cdc",
    "environment.json": "8233d92dd0134de39f82899b6cb5cb2510344be0d308ffb6f04875a7984fa8b7",
    "export-settings.json": "ca395068c78a44a89062506796c140f85b5264c81aadc501c12727f30013b4d4",
    "acceptance.json": "df2beb6efca4a1d94a279d9b6ab4e3f455771a9d9307bc1455ca8b37e4a8e7a0",
}
EXPECTED_CAPTIONS = [
    ("C1", 0, 60, "夏の車、\n日差しがツライ…"),
    ("C2", 60, 60, "車内の暑さ対策に"),
    ("C3", 120, 60, "KEIYO\n傘型サンシェード"),
    ("C4", 180, 90, "傘みたいに開いて\n簡単設置"),
    ("C5", 270, 91, "UVカット率\n約99％"),
    ("C6", 360, 90, "チタンシルバー採用\n車内温度上昇を軽減"),
    ("C7", 450, 90, "閉じてまとめる"),
    ("C8", 540, 90, "折りたためて\nコンパクト収納"),
    ("C9", 630, 120, "10本骨仕様"),
    ("C10", 750, 137, "下のカートから\nチェックして"),
]
EXPECTED_CUTS = [
    ("C1", 0, 60, [("IMG_3977.MOV", 0, 60, [2.0, 4.0], 1.0)]),
    ("C2", 60, 120, [("IMG_3976.MOV", 60, 60, [6.5, 8.5], 1.0)]),
    ("C3", 120, 180, [("IMG_3920.MOV", 120, 60, [3.6, 5.6], 1.0)]),
    ("C4", 180, 270, [
        ("IMG_3957.MOV", 180, 60, [0.4, 2.0], 0.8),
        ("IMG_3957.MOV", 240, 30, [2.0, 3.0], 1.0),
    ]),
    ("C5", 270, 360, [("IMG_3956.MOV", 270, 90, [0.2, 3.2], 1.0)]),
    ("C6", 360, 450, [("IMG_3963.MOV", 360, 90, [0.3, 3.3], 1.0)]),
    ("C7", 450, 540, [
        ("IMG_0374.MOV", 450, 60, [0.0, 2.5], 1.25),
        ("IMG_0374.MOV", 510, 30, [2.4, 3.4], 1.0),
    ]),
    ("C8", 540, 630, [("IMG_0373.MOV", 540, 90, [68.0, 71.0], 1.0)]),
    ("C9", 630, 750, [("IMG_3958.MOV", 630, 120, [0.2, 4.2], 1.0)]),
    ("C10", 750, 891, [("IMG_3931.MOV", 750, 141, [0.0, 4.7], 1.0)]),
]
EXPECTED_TTS = [
    ("C1", 0, 57, 1.45614),
    ("C2", 60, 55, 1.2545456826446697),
    ("C3", 120, 57, 1.6),
    ("C4", 180, 87, 1.3),
    ("C5", 270, 87, 1.1839079310344829),
    ("C6", 360, 88, 1.72),
    ("C7", 450, 73, 1.0),
    ("C8", 540, 87, 1.38),
    ("C9", 630, 85, 1.0),
    ("C10", 750, 78, 1.0),
]
EXPECTED_SFX = [
    ("シンプルなWhoosh音", 1, 20, 4.28, 0.15171706676483154),
    ("シンプルなWhoosh音", 180, 20, 4.28, 0.15171706676483154),
    ("りんりん", 270, 61, 1.0, 0.15171706676483154),
    ("マウスのクリック音", 450, 6, 1.0, 0.15171706676483154),
    ("ポン！（口を手で叩いて鳴らす音）", 750, 11, 1.0, 0.15171706676483154),
]
EXPECTED_CAPTION_STYLE = {
    "font_title": "none",
    "font_file": "en.ttf",
    "font_size": 18.0,
    "bold": True,
    "fill_rgb": [1, 1, 1],
    "stroke_rgb": [0, 0, 0],
    "stroke_width": 0.0599999986588955,
    "has_shadow": False,
    "alignment": 1,
    "line_spacing": 0.02,
    "line_max_width": 0.82,
    "transform": {"x": 0.0, "y": 0.625},
    "scale": {"x": 1.0, "y": 1.0},
}
EXPECTED_MATERIAL_SEMANTICS = [
    {
        "cut_id": "C1",
        "purpose": "冒頭で夏の車内のつらさを即時に伝える",
        "must_show": ["車内の人物", "暑くて苦しそうな表情または姿勢"],
        "must_not_show": ["落ち着いた表情", "暑さが伝わらない中立的なリアクション"],
    },
    {
        "cut_id": "C2",
        "purpose": "暑さへの苛立ちをC1とは別のリアクションで強める",
        "must_show": ["運転席の人物", "苛立ちまたはうんざりした動作"],
        "must_not_show": ["C1と同じリアクション", "笑顔だけのカット"],
    },
    {
        "cut_id": "C3",
        "purpose": "商品を主役として初登場させる",
        "must_show": ["屋外", "商品全体", "商品をカメラまたは空へ向けて開く動作"],
        "must_not_show": ["商品が見切れる", "カメラと逆向きに開く", "比較用の別製品"],
    },
    {
        "cut_id": "C4",
        "purpose": "傘のように開いてフロントガラスへ設置できることを示す",
        "must_show": ["車内", "傘型の開閉動作", "フロントガラスへの設置過程"],
        "must_not_show": ["完成状態だけで設置動作が見えない", "比較用の別製品"],
    },
    {
        "cut_id": "C5",
        "purpose": "設置後の内側と広いカバー範囲を示す",
        "must_show": ["設置済み商品の黒い内側", "骨組み", "フロントガラスの広い被覆"],
        "must_not_show": ["UVカット率を映像だけで実測したように見せる表現"],
    },
    {
        "cut_id": "C6",
        "purpose": "チタンシルバー面と車外から見た被覆状態を示す",
        "must_show": ["車外正面", "銀色の面", "フロントガラス全体の被覆"],
        "must_not_show": ["黒い面だけ", "比較用の別製品"],
    },
    {
        "cut_id": "C7",
        "purpose": "閉じてまとめる動作を示す",
        "must_show": ["商品のクローズアップ", "閉じるまたは折りまとめる手元"],
        "must_not_show": ["開く動作だけ", "比較用の別製品"],
    },
    {
        "cut_id": "C8",
        "purpose": "収納時のコンパクトさを示す",
        "must_show": ["折りたたまれた商品", "手で持てるサイズ感"],
        "must_not_show": ["開いた商品", "比較用の別製品"],
    },
    {
        "cut_id": "C9",
        "purpose": "10本骨仕様を視覚的に補強する",
        "must_show": ["開いた商品", "骨組みが明瞭に見える構図"],
        "must_not_show": ["骨組みが隠れている", "別素材で本数が判別できない"],
    },
    {
        "cut_id": "C10",
        "purpose": "商品を再提示し、下方向の購入導線で締める",
        "must_show": ["設置済み商品", "人物の下向き指差し"],
        "must_not_show": ["商品が映らない", "指差す方向が不明", "CTAと逆方向の指差し"],
        "review_flags": ["人物の顔", "車両ブランド", "背景の建物"],
    },
]
EXPECTED_TIMELINE_TOP_LEVEL = {
    "schema_version": "keiyo.capcut_golden_baseline.v1",
    "canvas": {"ratio": "custom", "width": 1080, "height": 1920, "background": None},
    "fps": 30.0,
    "duration_seconds": 29.7,
    "duration_frames": 891,
    "logical_cut_count": 10,
    "physical_video_segment_count": 12,
    "caption_overlaps": [{
        "from_cut": "C5",
        "to_cut": "C6",
        "overlap_frames": 1,
        "status": "known_current_draft_defect",
    }],
}
EXPECTED_CAPTION_TOP_LEVEL = {
    "schema_version": "keiyo.capcut_golden_baseline.v1",
    "caption_count": 10,
    "semantic_placement": "upper_center",
}
EXPECTED_ENVIRONMENT = {
    "schema_version": "keiyo.capcut_golden_baseline.v1",
    "captured_source_environment": {
        "os": "mac",
        "capcut_version": "9.0.0",
        "fps": 30.0,
        "font_title": "none",
        "font_file": "en.ttf",
        "tts_voice_label": "ホリデーツイスト",
        "tts_voice_english_label": "Holiday Twist",
        "tts_voice_speaker": "ICL_en_male_oogie2",
        "tts_resource_id": "7438551608746578449",
        "sfx_names": [
            "シンプルなWhoosh音",
            "シンプルなWhoosh音",
            "りんりん",
            "マウスのクリック音",
            "ポン！（口を手で叩いて鳴らす音）",
        ],
    },
    "windows_policy": {
        "missing_font": "HOLD; require human-approved visually equivalent fallback",
        "missing_tts_voice": "HOLD; do not silently substitute another voice",
        "missing_sfx": "HOLD; do not silently substitute another effect",
        "capcut_version_difference": "record version and run structural plus human visual/audio comparison",
    },
}
EXPECTED_EXPORT_SETTINGS = {
    "schema_version": "keiyo.capcut_golden_baseline.v1",
    "source": "user_fixed_preference",
    "target": {
        "ai_uhd_enabled": True,
        "resolution": "4K",
        "frame_rate_fps": 30,
        "optical_flow_enabled": True,
        "bitrate_mbps": 100,
        "smart_hdr_enabled": True,
    },
    "unknown": ["container_format", "codec", "color_space", "audio_codec", "audio_bitrate"],
    "current_capcut_ui_readback": "not_verified_in_this_baseline_capture",
    "export_performed": False,
    "policy": "verify each visible setting immediately before any separately approved export",
}
EXPECTED_ACCEPTANCE = {
    "schema_version": "keiyo.capcut_golden_baseline_acceptance.v1",
    "baseline_id": "an-s182-mac-capcut-rakuten-v1",
    "decision": "pending_user_acceptance",
    "machine_result": "HOLD",
    "exact_checks": {
        "canvas": "1080x1920",
        "fps": 30,
        "duration_frames": 891,
        "logical_cut_count": 10,
        "caption_count": 10,
        "tts_count": 10,
        "sfx_count": 5,
        "bgm_count": 0,
        "source_audio_muted": True,
        "transition_count": 0,
        "video_effect_count": 0,
        "tts_voice_label": "ホリデーツイスト",
        "tts_voice_english_label": "Holiday Twist",
        "final_caption": "下のカートから\nチェックして",
    },
    "cross_os_tolerance": {
        "exact": [
            "cut order",
            "frame boundaries",
            "source filename and source range",
            "caption strings",
            "caption start and duration",
            "audio placement",
            "BGM absence",
            "source audio mute",
            "per-cut must_show and must_not_show",
        ],
        "manual_visual_review": [
            "caption readability and TikTok top clearance",
            "crop and subject prominence",
            "motion continuity",
            "TTS audibility and pronunciation",
            "SFX subjective fit",
        ],
        "not_required": [
            "pixel-identical rendering across macOS and Windows",
            "byte-identical video export",
            "identical font rasterization",
            "identical encoder output",
        ],
    },
    "holds": [
        {
            "code": "HOLD_ORIGINAL_MEDIA_UNAVAILABLE",
            "cuts": ["C4", "C6"],
            "detail": "IMG_3957.MOV and IMG_3963.MOV plus paired sidecars were not found in the current canonical asset catalog.",
        },
        {
            "code": "HOLD_CURRENT_DRAFT_CAPTION_OVERLAP",
            "cuts": ["C5", "C6"],
            "detail": "The current Mac draft has a one-frame overlap: C5 caption ends at frame 361 while C6 starts at frame 360.",
        },
        {
            "code": "HOLD_GOLDEN_REFERENCE_NOT_USER_ACCEPTED",
            "cuts": [],
            "detail": "The user has not yet accepted this captured Mac draft as the golden reference.",
        },
        {
            "code": "HOLD_SUBJECTIVE_AUDIO_NOT_AUDITIONED",
            "cuts": [],
            "detail": "Audio structure is verified, but voice and SFX quality have not been independently auditioned.",
        },
        {
            "code": "HOLD_EXPORT_SETTINGS_NOT_READ_BACK",
            "cuts": [],
            "detail": "The user-fixed 4K/30fps/100Mbps enhancement settings are recorded, but the current CapCut export UI was not read back and no export was performed.",
        },
        {
            "code": "HOLD_RIGHTS_PRIVACY_REVIEW",
            "cuts": ["C10"],
            "detail": "A person, vehicle brand, and background buildings are visible and require human rights/privacy review before distribution.",
        },
    ],
    "outcomes_not_measured": ["retention", "sales conversion", "comment rate"],
    "external_effects_authorized": False,
}


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
    evidence = root / "EVIDENCE.sha256"
    entries: dict[str, str] = {}
    try:
        lines = evidence.read_text(encoding="utf-8").splitlines()
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
    expected = REQUIRED_FILES - {"EVIDENCE.sha256"}
    if set(entries) != expected:
        errors.append("EVIDENCE.sha256 file set mismatch")
    for name, expected_digest in entries.items():
        path = root / name
        if not path.is_file() or sha256(path) != expected_digest:
            errors.append(f"evidence hash mismatch: {name}")
    return errors


def verify(root: Path, draft_info: Path | None = None) -> list[str]:
    errors: list[str] = []
    root = root.resolve()
    actual_files = {path.name for path in root.iterdir() if path.is_file()} if root.is_dir() else set()
    if actual_files != REQUIRED_FILES:
        errors.append("baseline file set mismatch")
    try:
        manifest = load_json(root / "baseline.manifest.json")
        timeline = load_json(root / "timeline.json")
        materials = load_json(root / "material-map.json")
        captions = load_json(root / "caption-style.json")
        audio = load_json(root / "audio-layout.json")
        environment = load_json(root / "environment.json")
        export_settings = load_json(root / "export-settings.json")
        acceptance = load_json(root / "acceptance.json")
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return errors + [f"cannot load baseline JSON: {exc}"]

    for name, expected_digest in EXPECTED_JSON_SHA256.items():
        if sha256(root / name) != expected_digest:
            errors.append(f"canonical JSON hash mismatch: {name}")

    if manifest.get("baseline_id") != "an-s182-mac-capcut-rakuten-v1":
        errors.append("baseline id mismatch")
    observed = manifest.get("observed_current_project") or {}
    exact_observed = {
        "fps": 30.0,
        "duration_seconds": 29.7,
        "duration_frames": 891,
        "logical_cuts": 10,
        "physical_video_segments": 12,
        "captions": 10,
        "tts": 10,
        "sfx": 5,
        "bgm": 0,
        "source_audio_muted": True,
        "transition_materials": 0,
        "video_effect_materials": 0,
        "app_version": "9.0.0",
        "source_os": "mac",
    }
    for key, value in exact_observed.items():
        if observed.get(key) != value:
            errors.append(f"observed project mismatch: {key}")
    if observed.get("canvas", {}).get("width") != 1080 or observed.get("canvas", {}).get("height") != 1920:
        errors.append("canvas mismatch")

    timeline_top_level = {key: value for key, value in timeline.items() if key != "cuts"}
    if timeline_top_level != EXPECTED_TIMELINE_TOP_LEVEL:
        errors.append("timeline top-level declarations mismatch")
    cuts = timeline.get("cuts") or []
    if len(cuts) != len(EXPECTED_CUTS):
        errors.append("timeline cut count mismatch")
    else:
        for row, expected in zip(cuts, EXPECTED_CUTS):
            cut_id, start, end, expected_segments = expected
            if (row.get("cut_id"), row.get("logical_start_frame"), row.get("logical_end_frame")) != (cut_id, start, end):
                errors.append(f"cut boundary mismatch: {cut_id}")
            actual_segments = [
                (
                    item.get("asset_ref"), item.get("target_start_frame"), item.get("target_duration_frames"),
                    item.get("source_range_seconds"), item.get("speed"),
                )
                for item in row.get("physical_segments") or []
            ]
            if actual_segments != expected_segments:
                errors.append(f"physical segment mismatch: {cut_id}")
            if any(item.get("source_audio_volume_linear") != 0.0 or item.get("keyframe_count") != 0 for item in row.get("physical_segments") or []):
                errors.append(f"video audio or keyframe mismatch: {cut_id}")
    caption_top_level = {key: value for key, value in captions.items() if key != "captions"}
    if caption_top_level != EXPECTED_CAPTION_TOP_LEVEL:
        errors.append("caption top-level declarations mismatch")
    rows = captions.get("captions") or []
    if len(rows) != len(EXPECTED_CAPTIONS):
        errors.append("caption count mismatch")
    else:
        for row, expected in zip(rows, EXPECTED_CAPTIONS):
            actual = (row.get("cut_id"), row.get("target_start_frame"), row.get("target_duration_frames"), row.get("text"))
            if actual != expected:
                errors.append(f"caption mismatch: {expected[0]}")
            actual_style = {key: row.get(key) for key in EXPECTED_CAPTION_STYLE}
            if actual_style != EXPECTED_CAPTION_STYLE:
                errors.append(f"caption visual style mismatch: {expected[0]}")

    material_rows = materials.get("materials") or []
    if [row.get("cut_id") for row in material_rows] != [f"C{i}" for i in range(1, 11)]:
        errors.append("material cut order mismatch")
    semantic_keys = ("cut_id", "purpose", "must_show", "must_not_show", "review_flags")
    actual_material_semantics = [
        {key: row[key] for key in semantic_keys if key in row}
        for row in material_rows
    ]
    if actual_material_semantics != EXPECTED_MATERIAL_SEMANTICS:
        errors.append("material semantic declarations mismatch")
    for row in material_rows:
        cut_id = row.get("cut_id")
        if not row.get("must_show") or not row.get("must_not_show"):
            errors.append(f"semantic selection rules missing: {cut_id}")
        statuses = {asset.get("reproduction_source_status") for asset in row.get("assets") or []}
        expected_status = {"hold_original_or_sidecar_unavailable"} if cut_id in {"C4", "C6"} else {"verified"}
        if statuses != expected_status:
            errors.append(f"material receipt mismatch: {cut_id}")
    if len(material_rows) == len(EXPECTED_CUTS):
        for row, expected in zip(material_rows, EXPECTED_CUTS):
            expected_assets = [(item[0], item[3]) for item in expected[3]]
            actual_assets = [
                (item.get("original_filename"), item.get("original_source_range_seconds"))
                for item in row.get("assets") or []
            ]
            if actual_assets != expected_assets:
                errors.append(f"material filename or range mismatch: {expected[0]}")

    if audio.get("tts_count") != 10 or audio.get("sfx_count") != 5 or audio.get("other_audio") != []:
        errors.append("audio counts mismatch")
    if audio.get("source_audio_all_zero") is not True or audio.get("bgm_policy") != "none":
        errors.append("audio policy mismatch")
    tts_rows = audio.get("tts") or []
    actual_tts = [
        (row.get("cut_id"), row.get("target_start_frame"), row.get("target_duration_frames"), row.get("speed"))
        for row in tts_rows
    ]
    if actual_tts != EXPECTED_TTS:
        errors.append("TTS row mapping or timing mismatch")
    if any(
        row.get("voice_label") != "ホリデーツイスト"
        or row.get("voice_speaker") != "ICL_en_male_oogie2"
        or row.get("resource_id") != "7438551608746578449"
        or row.get("volume_linear") != 1.0
        for row in tts_rows
    ):
        errors.append("TTS voice identity or volume mismatch")
    actual_sfx = [
        (row.get("name"), row.get("target_start_frame"), row.get("target_duration_frames"), row.get("speed"), row.get("volume_linear"))
        for row in audio.get("sfx") or []
    ]
    if actual_sfx != EXPECTED_SFX:
        errors.append("SFX identity, timing, speed, or volume mismatch")

    if environment != EXPECTED_ENVIRONMENT:
        errors.append("environment identity or Windows policy mismatch")
    if export_settings != EXPECTED_EXPORT_SETTINGS:
        errors.append("export source, target, unknown, readback, or policy mismatch")
    if acceptance != EXPECTED_ACCEPTANCE:
        errors.append("acceptance canonical HOLD payload mismatch")

    forbidden_patterns = [
        re.compile(r"/Users/", re.I),
        re.compile(r"[A-Z]:\\"),
        re.compile(r"https://drive\.google\.com/drive/folders/", re.I),
        re.compile(r"(?:^|[/\\])\.local(?:[/\\]|$)"),
    ]
    for payload_name, payload in (("manifest", manifest), ("timeline", timeline), ("materials", materials), ("captions", captions), ("audio", audio), ("environment", environment), ("export_settings", export_settings), ("acceptance", acceptance)):
        for value in iter_strings(payload):
            if any(pattern.search(value) for pattern in forbidden_patterns):
                errors.append(f"non-portable or private value in {payload_name}")
                break

    errors.extend(verify_evidence(root))
    if draft_info is not None:
        expected_hash = (manifest.get("source_receipt") or {}).get("draft_info_sha256")
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
        print("INVALID_GOLDEN_BASELINE")
        for error in sorted(set(errors)):
            print(f"- {error}")
        return 1
    print("PASS_GOLDEN_BASELINE status=HOLD known_holds=6 media_embedded=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
