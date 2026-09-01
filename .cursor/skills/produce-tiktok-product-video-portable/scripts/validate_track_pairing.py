#!/usr/bin/env python3
"""Validate independently observed same-cut source/caption edges and JPEG evidence."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import tempfile
from pathlib import Path


SCHEMA = "product_video_track_pairing_receipt.v2"
SHA_CHARS = set("0123456789abcdef")
TOP_KEYS = {
    "schema", "case_id", "product_model", "observed_at", "fps",
    "timeline_end_frame", "supersedes", "boundary_readback_basis",
    "evidence", "cuts", "pairing_result",
}
SUPERSEDES_KEYS = {"path", "sha256", "reason"}
BASIS_KEYS = {"editor_zoom", "ruler_tick_frames", "minimum_pixels_per_frame", "edge_alignment_method"}
EVIDENCE_KEYS = {
    "evidence_id", "relative_path", "sha256", "byte_size", "mime_type",
    "width", "height", "boundary_frame", "track_group", "coverage",
}
CUT_KEYS = {
    "cut_id", "source_asset_id", "source_start_frame", "source_end_frame",
    "caption_start_frame", "caption_end_frame", "head_delta_frames", "tail_delta_frames",
    "head_evidence_id", "tail_evidence_id", "source_edge_readback",
    "caption_edge_readback", "template_animation_seconds", "clip_edge_result",
    "render_animation_checked_separately",
}


def is_sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= SHA_CHARS


def is_frame(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def jpeg_dimensions(raw: bytes) -> tuple[int, int] | None:
    if len(raw) < 4 or raw[:2] != b"\xff\xd8":
        return None
    index = 2
    while index + 4 <= len(raw):
        if raw[index] != 0xFF:
            index += 1
            continue
        while index < len(raw) and raw[index] == 0xFF:
            index += 1
        if index >= len(raw):
            return None
        marker = raw[index]
        index += 1
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            continue
        if index + 2 > len(raw):
            return None
        length = int.from_bytes(raw[index:index + 2], "big")
        if length < 2 or index + length > len(raw):
            return None
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if length < 7:
                return None
            height = int.from_bytes(raw[index + 3:index + 5], "big")
            width = int.from_bytes(raw[index + 5:index + 7], "big")
            return (width, height) if width > 0 and height > 0 else None
        index += length
    return None


def validate(receipt: object, project_root: Path | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(receipt, dict):
        return ["receipt must be an object"]
    if set(receipt) != TOP_KEYS:
        return [f"top-level keys must equal {sorted(TOP_KEYS)}"]
    if receipt["schema"] != SCHEMA:
        errors.append(f"schema must equal {SCHEMA}")
    fps = receipt["fps"]
    if not isinstance(fps, int) or isinstance(fps, bool) or fps <= 0:
        errors.append("fps must be a positive integer")
    if not is_frame(receipt["timeline_end_frame"]):
        errors.append("timeline_end_frame must be a non-negative integer")

    supersedes = receipt["supersedes"]
    if not isinstance(supersedes, dict) or set(supersedes) != SUPERSEDES_KEYS:
        errors.append(f"supersedes must contain exactly {sorted(SUPERSEDES_KEYS)}")
    elif not is_sha(supersedes["sha256"]):
        errors.append("supersedes.sha256 must be lowercase SHA-256")

    basis = receipt["boundary_readback_basis"]
    if not isinstance(basis, dict) or set(basis) != BASIS_KEYS:
        errors.append(f"boundary_readback_basis must contain exactly {sorted(BASIS_KEYS)}")
    else:
        if basis["editor_zoom"] != "frame-level":
            errors.append("editor_zoom must equal frame-level")
        if not isinstance(basis["ruler_tick_frames"], int) or basis["ruler_tick_frames"] <= 0:
            errors.append("ruler_tick_frames must be positive")
        minimum_pixels = basis["minimum_pixels_per_frame"]
        if not isinstance(minimum_pixels, (int, float)) or isinstance(minimum_pixels, bool) or minimum_pixels < 8:
            errors.append("minimum_pixels_per_frame must be at least 8")
        if not isinstance(basis["edge_alignment_method"], str) or not basis["edge_alignment_method"]:
            errors.append("edge_alignment_method must be non-empty")

    evidence = receipt["evidence"]
    evidence_ids: set[str] = set()
    evidence_coverage: dict[str, set[str]] = {}
    evidence_boundary: dict[str, int] = {}
    evidence_frame_by_path: dict[str, int] = {}
    evidence_frame_by_sha: dict[str, int] = {}
    if not isinstance(evidence, list) or not evidence:
        errors.append("evidence must be a non-empty array")
        evidence = []
    for index, item in enumerate(evidence):
        prefix = f"evidence[{index}]"
        if not isinstance(item, dict) or set(item) != EVIDENCE_KEYS:
            errors.append(f"{prefix} must contain exactly {sorted(EVIDENCE_KEYS)}")
            continue
        evidence_id = item["evidence_id"]
        if not isinstance(evidence_id, str) or not evidence_id or evidence_id in evidence_ids:
            errors.append(f"{prefix}.evidence_id must be unique and non-empty")
            continue
        evidence_ids.add(evidence_id)
        if not is_sha(item["sha256"]):
            errors.append(f"{prefix}.sha256 must be lowercase SHA-256")
        if not isinstance(item["byte_size"], int) or item["byte_size"] <= 0:
            errors.append(f"{prefix}.byte_size must be positive")
        if item["mime_type"] != "image/jpeg":
            errors.append(f"{prefix}.mime_type must equal image/jpeg")
        for dimension in ("width", "height"):
            if not isinstance(item[dimension], int) or item[dimension] <= 0:
                errors.append(f"{prefix}.{dimension} must be positive")
        if not is_frame(item["boundary_frame"]):
            errors.append(f"{prefix}.boundary_frame must be non-negative")
        else:
            evidence_boundary[evidence_id] = item["boundary_frame"]
            for label, value, claims in (
                ("relative_path", item["relative_path"], evidence_frame_by_path),
                ("sha256", item["sha256"], evidence_frame_by_sha),
            ):
                if isinstance(value, str) and value:
                    prior_frame = claims.get(value)
                    if prior_frame is not None and prior_frame != item["boundary_frame"]:
                        errors.append(f"{prefix}.{label} cannot be reused for different boundary frames")
                    else:
                        claims[value] = item["boundary_frame"]
        if item["track_group"] not in {"front", "back"}:
            errors.append(f"{prefix}.track_group must be front or back")
        coverage = item["coverage"]
        if not isinstance(coverage, list) or not coverage:
            errors.append(f"{prefix}.coverage must be non-empty")
        elif any(not isinstance(value, str) or not value for value in coverage):
            errors.append(f"{prefix}.coverage must contain only non-empty edge IDs")
        elif len(coverage) != len(set(coverage)):
            errors.append(f"{prefix}.coverage must not contain duplicates")
        else:
            evidence_coverage[evidence_id] = set(coverage)
        relative = item["relative_path"]
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or Path(relative).suffix.lower() not in {".jpg", ".jpeg"}:
            errors.append(f"{prefix}.relative_path must be a relative .jpg/.jpeg path")
        elif project_root is not None:
            target = (project_root / relative).resolve()
            try:
                target.relative_to(project_root.resolve())
                raw = target.read_bytes()
            except (ValueError, OSError) as exc:
                errors.append(f"{prefix} evidence is unreadable under project root: {exc}")
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
    seen: set[str] = set()
    required_edge_ids: set[str] = set()
    previous_source_end: int | None = None
    previous_caption_end: int | None = None
    for index, cut in enumerate(cuts):
        prefix = f"cuts[{index}]"
        if not isinstance(cut, dict) or set(cut) != CUT_KEYS:
            errors.append(f"{prefix} must contain exactly {sorted(CUT_KEYS)}")
            continue
        cut_id = cut["cut_id"]
        if not isinstance(cut_id, str) or not cut_id or cut_id in seen:
            errors.append(f"{prefix}.cut_id must be unique and non-empty")
            continue
        seen.add(cut_id)
        if not isinstance(cut["source_asset_id"], str) or not cut["source_asset_id"]:
            errors.append(f"{prefix}.source_asset_id must be non-empty")
        for field in ("source_edge_readback", "caption_edge_readback"):
            if not isinstance(cut[field], str) or not cut[field]:
                errors.append(f"{prefix}.{field} must be non-empty")
        frame_fields = ("source_start_frame", "source_end_frame", "caption_start_frame", "caption_end_frame")
        for field in frame_fields:
            if not is_frame(cut[field]):
                errors.append(f"{prefix}.{field} must be a non-negative integer")
        if any(not is_frame(cut[field]) for field in frame_fields):
            continue
        if previous_source_end is not None and cut["source_start_frame"] != previous_source_end:
            errors.append(f"{prefix} source continuity mismatch")
        if previous_caption_end is not None and cut["caption_start_frame"] != previous_caption_end:
            errors.append(f"{prefix} caption continuity mismatch")
        if cut["source_end_frame"] <= cut["source_start_frame"]:
            errors.append(f"{prefix} source range must have positive duration")
        if cut["caption_end_frame"] <= cut["caption_start_frame"]:
            errors.append(f"{prefix} caption range must have positive duration")
        head_delta = cut["caption_start_frame"] - cut["source_start_frame"]
        tail_delta = cut["caption_end_frame"] - cut["source_end_frame"]
        if cut["head_delta_frames"] != head_delta or cut["tail_delta_frames"] != tail_delta:
            errors.append(f"{prefix} stored deltas do not match independently read edges")
        if head_delta != 0 or tail_delta != 0:
            errors.append(f"{prefix} source/caption edges must match exactly")
        for edge, field, expected_frame in (
            (f"{cut_id}:head", "head_evidence_id", cut["source_start_frame"]),
            (f"{cut_id}:tail", "tail_evidence_id", cut["source_end_frame"]),
        ):
            required_edge_ids.add(edge)
            evidence_id = cut[field]
            if evidence_id not in evidence_ids:
                errors.append(f"{prefix}.{field} must reference actual evidence")
            else:
                if edge not in evidence_coverage.get(evidence_id, set()):
                    errors.append(f"{prefix}.{field} coverage must include {edge}")
                if evidence_boundary.get(evidence_id) != expected_frame:
                    errors.append(f"{prefix}.{field} boundary_frame mismatch")
        if cut["clip_edge_result"] != "PASS":
            errors.append(f"{prefix}.clip_edge_result must be PASS")
        if cut["render_animation_checked_separately"] is not True:
            errors.append(f"{prefix} must separately check rendered animation")
        animation = cut["template_animation_seconds"]
        if not isinstance(animation, (int, float)) or isinstance(animation, bool) or animation < 0:
            errors.append(f"{prefix}.template_animation_seconds must be non-negative")
        previous_source_end = cut["source_end_frame"]
        previous_caption_end = cut["caption_end_frame"]
    covered_edges = set().union(*evidence_coverage.values()) if evidence_coverage else set()
    if covered_edges != required_edge_ids:
        errors.append("evidence coverage must equal the exact set of paired head/tail edge IDs")
    if cuts and (cuts[-1].get("source_end_frame") != receipt["timeline_end_frame"] or cuts[-1].get("caption_end_frame") != receipt["timeline_end_frame"]):
        errors.append("last source and caption edges must equal timeline_end_frame")
    if receipt["pairing_result"] != "PASS_ALL_CUTS_EXACT_EDGES_FRAME_LEVEL":
        errors.append("pairing_result must equal PASS_ALL_CUTS_EXACT_EDGES_FRAME_LEVEL")
    return errors


def self_test() -> int:
    jpeg = base64.b64decode(
        "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABBQJ//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAwEBPwF//8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAgBAgEBPwF//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQAGPwJ//8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPyF//9oADAMBAAIAAwAAAB//xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/EH//xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/EH//xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/EH//2Q=="
    )
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        head_raw = jpeg + b"head"
        tail_raw = jpeg + b"tail"
        head_image = root / "head.jpg"
        tail_image = root / "tail.jpg"
        head_image.write_bytes(head_raw)
        tail_image.write_bytes(tail_raw)
        base = {
            "schema": SCHEMA, "case_id": "case", "product_model": "AN-S182",
            "observed_at": "2026-08-31T15:00:00+09:00", "fps": 30,
            "timeline_end_frame": 20,
            "supersedes": {"path": "r01.json", "sha256": "0" * 64, "reason": "test"},
            "boundary_readback_basis": {
                "editor_zoom": "frame-level", "ruler_tick_frames": 3,
                "minimum_pixels_per_frame": 36.0, "edge_alignment_method": "same viewport",
            },
            "evidence": [
                {"evidence_id": "head", "relative_path": head_image.name, "sha256": hashlib.sha256(head_raw).hexdigest(),
                 "byte_size": len(head_raw), "mime_type": "image/jpeg", "width": 1, "height": 1,
                 "boundary_frame": 0, "track_group": "front", "coverage": ["cut-01:head"]},
                {"evidence_id": "tail", "relative_path": tail_image.name, "sha256": hashlib.sha256(tail_raw).hexdigest(),
                 "byte_size": len(tail_raw), "mime_type": "image/jpeg", "width": 1, "height": 1,
                 "boundary_frame": 20, "track_group": "front", "coverage": ["cut-01:tail"]},
            ],
            "cuts": [{
                "cut_id": "cut-01", "source_asset_id": "asset-1",
                "source_start_frame": 0, "source_end_frame": 20,
                "caption_start_frame": 0, "caption_end_frame": 20,
                "head_delta_frames": 0, "tail_delta_frames": 0,
                "head_evidence_id": "head", "tail_evidence_id": "tail",
                "source_edge_readback": "independent source", "caption_edge_readback": "independent caption",
                "template_animation_seconds": 0.1, "clip_edge_result": "PASS",
                "render_animation_checked_separately": True,
            }],
            "pairing_result": "PASS_ALL_CUTS_EXACT_EDGES_FRAME_LEVEL",
        }
        cases: list[tuple[str, dict]] = []
        for name in ("head", "tail", "hash", "path", "coverage", "non-jpeg", "dimensions", "replay"):
            cases.append((name, json.loads(json.dumps(base))))
        cases[0][1]["cuts"][0]["caption_start_frame"] = 1
        cases[1][1]["cuts"][0]["caption_end_frame"] = 19
        cases[2][1]["evidence"][0]["sha256"] = "1" * 64
        cases[3][1]["evidence"][0]["relative_path"] = "../edge.jpg"
        cases[4][1]["evidence"][0]["coverage"] = ["cut-99:head"]
        fake = root / "fake.jpg"
        fake.write_bytes(b"not-a-jpeg")
        cases[5][1]["evidence"][0].update({"relative_path": fake.name, "sha256": hashlib.sha256(fake.read_bytes()).hexdigest(), "byte_size": fake.stat().st_size})
        cases[6][1]["evidence"][0]["width"] = 2
        cases[7][1]["evidence"][1]["relative_path"] = cases[7][1]["evidence"][0]["relative_path"]
        cases[7][1]["evidence"][1]["sha256"] = cases[7][1]["evidence"][0]["sha256"]
        cases[7][1]["evidence"][1]["byte_size"] = cases[7][1]["evidence"][0]["byte_size"]
        if validate(base, root):
            print("SELF-TEST FAILED: valid fixture rejected")
            return 1
        for name, bad in cases:
            if not validate(bad, root):
                print(f"SELF-TEST FAILED: {name} mutation accepted")
                return 1
    print(f"SELF-TEST PASSED: {1 + len(cases)} cases")
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
        print(f"INVALID: {exc}")
        return 1
    errors = validate(receipt, args.project_root)
    if errors:
        for error in errors:
            print(f"INVALID: {error}")
        return 1
    print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
