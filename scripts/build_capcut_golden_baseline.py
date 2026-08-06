#!/usr/bin/env python3
"""Build a sanitized, media-free CapCut golden baseline from one draft_info.json."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "keiyo.capcut_golden_baseline.v1"

CUT_SEMANTICS: dict[str, dict[str, Any]] = {
    "C1": {
        "purpose": "冒頭で夏の車内のつらさを即時に伝える",
        "must_show": ["車内の人物", "暑くて苦しそうな表情または姿勢"],
        "must_not_show": ["落ち着いた表情", "暑さが伝わらない中立的なリアクション"],
    },
    "C2": {
        "purpose": "暑さへの苛立ちをC1とは別のリアクションで強める",
        "must_show": ["運転席の人物", "苛立ちまたはうんざりした動作"],
        "must_not_show": ["C1と同じリアクション", "笑顔だけのカット"],
    },
    "C3": {
        "purpose": "商品を主役として初登場させる",
        "must_show": ["屋外", "商品全体", "商品をカメラまたは空へ向けて開く動作"],
        "must_not_show": ["商品が見切れる", "カメラと逆向きに開く", "比較用の別製品"],
    },
    "C4": {
        "purpose": "傘のように開いてフロントガラスへ設置できることを示す",
        "must_show": ["車内", "傘型の開閉動作", "フロントガラスへの設置過程"],
        "must_not_show": ["完成状態だけで設置動作が見えない", "比較用の別製品"],
    },
    "C5": {
        "purpose": "設置後の内側と広いカバー範囲を示す",
        "must_show": ["設置済み商品の黒い内側", "骨組み", "フロントガラスの広い被覆"],
        "must_not_show": ["UVカット率を映像だけで実測したように見せる表現"],
    },
    "C6": {
        "purpose": "チタンシルバー面と車外から見た被覆状態を示す",
        "must_show": ["車外正面", "銀色の面", "フロントガラス全体の被覆"],
        "must_not_show": ["黒い面だけ", "比較用の別製品"],
    },
    "C7": {
        "purpose": "閉じてまとめる動作を示す",
        "must_show": ["商品のクローズアップ", "閉じるまたは折りまとめる手元"],
        "must_not_show": ["開く動作だけ", "比較用の別製品"],
    },
    "C8": {
        "purpose": "収納時のコンパクトさを示す",
        "must_show": ["折りたたまれた商品", "手で持てるサイズ感"],
        "must_not_show": ["開いた商品", "比較用の別製品"],
    },
    "C9": {
        "purpose": "10本骨仕様を視覚的に補強する",
        "must_show": ["開いた商品", "骨組みが明瞭に見える構図"],
        "must_not_show": ["骨組みが隠れている", "別素材で本数が判別できない"],
    },
    "C10": {
        "purpose": "商品を再提示し、下方向の購入導線で締める",
        "must_show": ["設置済み商品", "人物の下向き指差し"],
        "must_not_show": ["商品が映らない", "指差す方向が不明", "CTAと逆方向の指差し"],
        "review_flags": ["人物の顔", "車両ブランド", "背景の建物"],
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def seconds(value: int | float | None) -> float | None:
    if value is None:
        return None
    return round(float(value) / 1_000_000, 6)


def frames(value: int | float, fps: float) -> int:
    return int(round(float(value) * fps / 1_000_000))


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_material_path(raw: str, project_root: Path) -> Path | None:
    match = re.fullmatch(r"##_draftpath_placeholder_[^#]+_##/(.+)", raw)
    if match:
        return project_root / match.group(1)
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else None


def source_selector(material_path: str, source_start_us: int, source_duration_us: int) -> dict[str, Any]:
    basename = Path(material_path).name
    original_match = re.search(r"(IMG_\d+)", basename, re.I)
    original_name = f"{original_match.group(1).upper()}.MOV" if original_match else basename
    snippet_range = re.search(r"_(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\.[^.]+$", basename)
    if snippet_range:
        base_start = float(snippet_range.group(1))
        original_start = base_start + source_start_us / 1_000_000
        original_end = original_start + source_duration_us / 1_000_000
    else:
        original_start = source_start_us / 1_000_000
        original_end = original_start + source_duration_us / 1_000_000
    return {
        "original_filename": original_name,
        "original_source_range_seconds": [round(original_start, 6), round(original_end, 6)],
        "project_resource_name": basename if "##_draftpath_placeholder_" in material_path else None,
    }


def build_asset_index(asset_root: Path | None) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    if asset_root is None or not asset_root.is_dir():
        return index
    for path in asset_root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            index.setdefault(path.name.casefold(), []).append(path)
    return index


def unique_index_path(index: dict[str, list[Path]], name: str) -> Path | None:
    matches = index.get(name.casefold(), [])
    return matches[0] if len(matches) == 1 else None


def material_receipt(
    original_name: str,
    material_path: str,
    project_resource_name: str | None,
    project_root: Path,
    asset_index: dict[str, list[Path]],
) -> dict[str, Any]:
    resolved = resolve_material_path(material_path, project_root)
    project_candidate = resolved if project_resource_name and resolved and resolved.is_file() else None
    canonical_candidate = unique_index_path(asset_index, original_name)
    json_sidecar = unique_index_path(asset_index, original_name + ".asset.json")
    md_sidecar = unique_index_path(asset_index, original_name + ".asset.md")
    sidecar_payload = load_json(json_sidecar) if json_sidecar else {}
    file_receipt = sidecar_payload.get("file") or {}
    caption_support = sidecar_payload.get("caption_support") or {}
    return {
        "asset_id": sidecar_payload.get("asset_id"),
        "original_media_status": (
            "verified_by_catalog_and_sidecar" if canonical_candidate and json_sidecar and md_sidecar
            else "hold_original_media_or_sidecar_unavailable"
        ),
        "original_media_sha256": None,
        "original_media_sha256_status": "not_computed_to_avoid_file_provider_download",
        "original_media_logical_size_bytes": file_receipt.get("logical_size_bytes"),
        "source_projection_sha256": caption_support.get("source_projection_sha256"),
        "project_resource_status": (
            "verified" if project_candidate else "hold_project_resource_unavailable"
            if project_resource_name else "not_applicable"
        ),
        "project_resource_sha256": sha256(project_candidate) if project_candidate else None,
        "project_resource_size_bytes": project_candidate.stat().st_size if project_candidate else None,
        "sidecar_json_sha256": sha256(json_sidecar) if json_sidecar else None,
        "sidecar_md_sha256": sha256(md_sidecar) if md_sidecar else None,
        "sidecar_status": "verified" if json_sidecar and md_sidecar else "hold_sidecar_unavailable",
        "reproduction_source_status": (
            "verified" if canonical_candidate and json_sidecar and md_sidecar
            else "hold_original_or_sidecar_unavailable"
        ),
    }


def text_payload(material: dict[str, Any]) -> dict[str, Any]:
    content = json.loads(material.get("content") or "{}")
    styles = content.get("styles") or []
    style = styles[0] if styles else {}
    strokes = style.get("strokes") or []
    stroke = strokes[0] if strokes else {}
    fill = ((style.get("fill") or {}).get("content") or {}).get("solid") or {}
    stroke_fill = ((stroke.get("content") or {}).get("solid") or {})
    font = style.get("font") or {}
    return {
        "text": content.get("text", ""),
        "font_title": material.get("font_title"),
        "font_file": Path(material.get("font_path") or font.get("path") or "").name or None,
        "font_size": material.get("font_size"),
        "bold": bool(style.get("bold")),
        "fill_rgb": fill.get("color"),
        "stroke_rgb": stroke_fill.get("color"),
        "stroke_width": stroke.get("width"),
        "has_shadow": bool(material.get("has_shadow")),
        "alignment": material.get("alignment"),
        "line_spacing": material.get("line_spacing"),
        "line_max_width": material.get("line_max_width"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft-info", required=True, type=Path)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--asset-root", type=Path)
    parser.add_argument("--captured-at", required=True)
    args = parser.parse_args()

    draft_path = args.draft_info.resolve()
    draft = load_json(draft_path)
    project_root = draft_path.parents[2]
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    fps = float(draft["fps"])
    duration_us = int(draft["duration"])
    materials = draft.get("materials") or {}
    video_materials = {row["id"]: row for row in materials.get("videos") or []}
    text_materials = {row["id"]: row for row in materials.get("texts") or []}
    audio_materials = {row["id"]: row for row in materials.get("audios") or []}
    tracks = draft.get("tracks") or []
    video_tracks = [row for row in tracks if row.get("type") == "video"]
    text_segments = sorted(
        [segment for track in tracks if track.get("type") == "text" for segment in track.get("segments") or []],
        key=lambda row: row["target_timerange"]["start"],
    )
    audio_segments = sorted(
        [segment for track in tracks if track.get("type") == "audio" for segment in track.get("segments") or []],
        key=lambda row: row["target_timerange"]["start"],
    )
    if len(video_tracks) != 1 or len(text_segments) != 10:
        raise SystemExit("expected exactly one video track and ten text segments")
    video_segments = sorted(video_tracks[0].get("segments") or [], key=lambda row: row["target_timerange"]["start"])
    asset_index = build_asset_index(args.asset_root.resolve() if args.asset_root else None)

    cuts: list[dict[str, Any]] = []
    material_map: list[dict[str, Any]] = []
    captions: list[dict[str, Any]] = []
    for index, caption_segment in enumerate(text_segments):
        start_us = int(caption_segment["target_timerange"]["start"])
        logical_end_us = int(text_segments[index + 1]["target_timerange"]["start"]) if index + 1 < len(text_segments) else duration_us
        material = text_materials[caption_segment["material_id"]]
        caption = text_payload(material)
        cut_id = f"C{index + 1}"
        caption_row = {
            "cut_id": cut_id,
            "target_start_seconds": seconds(start_us),
            "target_duration_seconds": seconds(caption_segment["target_timerange"]["duration"]),
            "target_start_frame": frames(start_us, fps),
            "target_duration_frames": frames(caption_segment["target_timerange"]["duration"], fps),
            "transform": (caption_segment.get("clip") or {}).get("transform"),
            "scale": (caption_segment.get("clip") or {}).get("scale"),
            **caption,
        }
        captions.append(caption_row)
        physical: list[dict[str, Any]] = []
        assets: list[dict[str, Any]] = []
        for segment in video_segments:
            target = segment["target_timerange"]
            segment_start = int(target["start"])
            segment_end = segment_start + int(target["duration"])
            if segment_start >= logical_end_us or segment_end <= start_us:
                continue
            video_material = video_materials[segment["material_id"]]
            selector = source_selector(
                video_material.get("path") or "",
                int((segment.get("source_timerange") or {}).get("start") or 0),
                int((segment.get("source_timerange") or {}).get("duration") or 0),
            )
            receipt = material_receipt(
                selector["original_filename"],
                video_material.get("path") or "",
                selector["project_resource_name"],
                project_root,
                asset_index,
            )
            physical.append({
                "target_start_seconds": seconds(segment_start),
                "target_duration_seconds": seconds(target["duration"]),
                "target_start_frame": frames(segment_start, fps),
                "target_duration_frames": frames(target["duration"], fps),
                "source_range_seconds": selector["original_source_range_seconds"],
                "speed": segment.get("speed"),
                "source_audio_volume_linear": segment.get("volume"),
                "transform": (segment.get("clip") or {}).get("transform"),
                "scale": (segment.get("clip") or {}).get("scale"),
                "keyframe_count": len(segment.get("keyframe_refs") or []),
                "asset_ref": selector["original_filename"],
            })
            assets.append({**selector, **receipt})
        cuts.append({
            "cut_id": cut_id,
            "logical_start_seconds": seconds(start_us),
            "logical_end_seconds": seconds(logical_end_us),
            "logical_start_frame": frames(start_us, fps),
            "logical_end_frame": frames(logical_end_us, fps),
            "physical_segments": physical,
        })
        material_map.append({"cut_id": cut_id, **CUT_SEMANTICS[cut_id], "assets": assets})

    caption_overlaps: list[dict[str, Any]] = []
    for current, following in zip(captions, captions[1:]):
        current_end = current["target_start_frame"] + current["target_duration_frames"]
        overlap_frames = current_end - following["target_start_frame"]
        if overlap_frames > 0:
            caption_overlaps.append({
                "from_cut": current["cut_id"],
                "to_cut": following["cut_id"],
                "overlap_frames": overlap_frames,
                "status": "known_current_draft_defect",
            })

    tts: list[dict[str, Any]] = []
    sfx: list[dict[str, Any]] = []
    other_audio: list[dict[str, Any]] = []
    for segment in audio_segments:
        material = audio_materials[segment["material_id"]]
        target = segment["target_timerange"]
        row = {
            "name": material.get("name"),
            "target_start_seconds": seconds(target["start"]),
            "target_duration_seconds": seconds(target["duration"]),
            "target_start_frame": frames(target["start"], fps),
            "target_duration_frames": frames(target["duration"], fps),
            "volume_linear": segment.get("volume"),
            "speed": segment.get("speed"),
        }
        if material.get("type") == "text_to_audio":
            cut_number = max(1, min(10, sum(1 for cut in cuts if cut["logical_start_seconds"] <= row["target_start_seconds"])))
            tts.append({
                "cut_id": f"C{cut_number}",
                **row,
                "voice_label": material.get("tone_effect_name") or material.get("tone_type"),
                "voice_type": material.get("tone_type"),
                "voice_speaker": material.get("tone_speaker"),
                "resource_id": material.get("resource_id"),
            })
        elif material.get("type") == "sound":
            sfx.append(row)
        else:
            other_audio.append({"type": material.get("type"), **row})

    timeline = {
        "schema_version": SCHEMA_VERSION,
        "canvas": draft.get("canvas_config"),
        "fps": fps,
        "duration_seconds": seconds(duration_us),
        "duration_frames": frames(duration_us, fps),
        "logical_cut_count": len(cuts),
        "physical_video_segment_count": len(video_segments),
        "caption_overlaps": caption_overlaps,
        "cuts": cuts,
    }
    caption_style = {
        "schema_version": SCHEMA_VERSION,
        "caption_count": len(captions),
        "semantic_placement": "upper_center",
        "captions": captions,
    }
    audio_layout = {
        "schema_version": SCHEMA_VERSION,
        "source_audio_policy": "muted",
        "source_audio_all_zero": all((segment.get("volume") or 0) == 0 for segment in video_segments),
        "bgm_policy": "none",
        "tts_count": len(tts),
        "tts": tts,
        "sfx_count": len(sfx),
        "sfx": sfx,
        "other_audio": other_audio,
        "subjective_audio_review": "not_auditioned",
    }
    environment = {
        "schema_version": SCHEMA_VERSION,
        "captured_source_environment": {
            "os": (draft.get("platform") or {}).get("os"),
            "capcut_version": (draft.get("platform") or {}).get("app_version"),
            "fps": fps,
            "font_title": captions[0].get("font_title") if captions else None,
            "font_file": captions[0].get("font_file") if captions else None,
            "tts_voice_label": tts[0].get("voice_label") if tts else None,
            "tts_voice_english_label": "Holiday Twist",
            "tts_voice_speaker": tts[0].get("voice_speaker") if tts else None,
            "tts_resource_id": tts[0].get("resource_id") if tts else None,
            "sfx_names": [row.get("name") for row in sfx],
        },
        "windows_policy": {
            "missing_font": "HOLD; require human-approved visually equivalent fallback",
            "missing_tts_voice": "HOLD; do not silently substitute another voice",
            "missing_sfx": "HOLD; do not silently substitute another effect",
            "capcut_version_difference": "record version and run structural plus human visual/audio comparison",
        },
    }
    export_settings = {
        "schema_version": SCHEMA_VERSION,
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
    material_payload = {
        "schema_version": SCHEMA_VERSION,
        "materials": material_map,
        "asset_identity_policy": "asset_id_plus_filename_plus_logical_size_plus_sidecar_hashes; original media hash intentionally not recomputed",
        "contains_media": False,
    }
    observed = {
        "project_name": args.project_name,
        "canvas": draft.get("canvas_config"),
        "fps": fps,
        "duration_seconds": seconds(duration_us),
        "duration_frames": frames(duration_us, fps),
        "logical_cuts": len(cuts),
        "physical_video_segments": len(video_segments),
        "captions": len(captions),
        "tts": len(tts),
        "sfx": len(sfx),
        "bgm": len(other_audio),
        "source_audio_muted": audio_layout["source_audio_all_zero"],
        "transition_materials": len(materials.get("transitions") or []),
        "video_effect_materials": len(materials.get("video_effects") or []),
        "app_version": (draft.get("platform") or {}).get("app_version"),
        "source_os": (draft.get("platform") or {}).get("os"),
    }
    baseline_manifest = {
        "schema_version": SCHEMA_VERSION,
        "baseline_id": "an-s182-mac-capcut-rakuten-v1",
        "product_model": "AN-S182",
        "captured_at": args.captured_at,
        "status": "hold_until_user_accepts_golden_reference",
        "source_receipt": {
            "project_name": args.project_name,
            "draft_info_sha256": sha256(draft_path),
            "source_project_modified": False,
        },
        "known_current_draft_defects": caption_overlaps,
        "observed_current_project": observed,
        "user_approved_preferences": {
            "tts_voice_label": "ホリデーツイスト",
            "tts_voice_english_label": "Holiday Twist",
            "bgm": "none",
            "caption_style": "simple_wide_upper_center_white_bold_black_outline_with_tiktok_top_clearance",
            "current_baseline_cta": "下のカートからチェックして",
            "future_workflow_cta": "下のカートからチェック",
        },
        "unverified_or_subjective": [
            "voice_quality_and_clarity",
            "sfx_subjective_quality",
            "pixel_exact_cross_os_rendering",
            "rights_and_privacy_acceptability",
            "export_settings_persistence",
            "retention_sales_and_comment_effect",
        ],
        "files": [
            "timeline.json",
            "material-map.json",
            "caption-style.json",
            "audio-layout.json",
            "environment.json",
            "export-settings.json",
            "acceptance.json",
        ],
    }
    payloads = {
        "baseline.manifest.json": baseline_manifest,
        "timeline.json": timeline,
        "material-map.json": material_payload,
        "caption-style.json": caption_style,
        "audio-layout.json": audio_layout,
        "environment.json": environment,
        "export-settings.json": export_settings,
    }
    for name, payload in payloads.items():
        (output_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
