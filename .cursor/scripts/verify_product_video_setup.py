#!/usr/bin/env python3
"""Fail-closed skill and material preflight for Cursor product-video runs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_NAME = "produce-tiktok-product-video-portable"
SKILL_ROOT = REPO_ROOT / ".cursor" / "skills" / SKILL_NAME
SETTINGS_PATH = REPO_ROOT / "config" / "product_video_settings_AN-S182.v1.json"
EXPECTED_SETTINGS_SHA256 = "a90ee56e42e8ddfcc9c4fec7970bffcc1e4396bbe6dcd37df9a2f74b399e0afa"
MEDIA_SUFFIXES = {".mp4", ".mov", ".m4v", ".avi", ".webm", ".jpg", ".jpeg", ".png", ".webp"}
REQUIRED_SKILL_FILES = (
    "SKILL.md",
    "manifest.json",
    "references/checkpoint-contract.md",
    "references/core-invariants.md",
    "references/execution-plan-contract.md",
    "references/fast-path.md",
    "references/workflow-state-contract.md",
    "references/host-adapter-contract.md",
    "references/hold-registry.md",
    "references/payload-contract.md",
    "references/portability-notes.md",
    "references/product-and-material-contract.md",
    "references/self-repair.md",
    "stages/01-prepare-script.md",
    "stages/02-validate-script.md",
    "stages/03-build-rough-cut.md",
    "stages/04-finish.md",
    "stages/05-verify-timeline.md",
    "stages/06-deliver.md",
    "scripts/build_rule_snapshot.py",
    "scripts/validate_product_video_payload.py",
    "scripts/validate_workflow_state.py",
    "scripts/validate_execution_plan.py",
    "scripts/validate_nonfinal_slack.py",
    "scripts/validate_track_pairing.py",
    "scripts/validate_timeline_integrity.py",
    "scripts/purge_local_working_media.py",
    "scripts/prepare_bulk_tts_scene_gaps.py",
    "scripts/resolve_product_inputs.py",
)
SELF_TESTS = (
    "validate_product_video_payload.py",
    "validate_workflow_state.py",
    "validate_execution_plan.py",
    "validate_nonfinal_slack.py",
    "validate_track_pairing.py",
    "validate_timeline_integrity.py",
    "purge_local_working_media.py",
    "prepare_bulk_tts_scene_gaps.py",
    "resolve_product_inputs.py",
)
FORBIDDEN_TEXT = (
    ".codex/",
    "codex-project",
    "mcp__",
)
FORBIDDEN_PATH_PATTERNS = (
    ("macOS home path", re.compile(r"/Users/[^/\s]+/")),
    ("Linux home path", re.compile(r"/home/[^/\s]+/")),
    ("Windows home path", re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\\s]+\\")),
)
REQUIRED_TEXT = (
    ("SKILL.md", "does not block `COMPLETE`"),
    ("references/hold-registry.md", "HOLD_DRIVE_LOCAL_BYTES_UNAVAILABLE"),
    ("references/host-adapter-contract.md", "Do not encode the completed video as base64"),
    ("references/core-invariants.md", "Do not spawn a successor case to obtain Holiday Twist"),
    ("references/fast-path.md", "Do not pause after `粗編集OK` for Path 1"),
    ("references/checkpoint-contract.md", "in, midpoint, and out frames"),
    ("stages/03-build-rough-cut.md", "Do not use Motion Graphics as the viewer-facing caption layer"),
    ("stages/04-finish.md", "TTS sidecar"),
    ("stages/06-deliver.md", "Do not inline the completed video as base64"),
)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def validate_static() -> list[str]:
    errors: list[str] = []
    if SKILL_ROOT.name != SKILL_NAME:
        errors.append("skill folder name mismatch")
    for relative in REQUIRED_SKILL_FILES:
        path = SKILL_ROOT / relative
        if path.is_symlink() or not path.is_file():
            errors.append(f"missing or unsafe skill file: {relative}")
    actual_files = {
        path.relative_to(SKILL_ROOT).as_posix()
        for path in SKILL_ROOT.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    unexpected_files = actual_files - set(REQUIRED_SKILL_FILES)
    if unexpected_files:
        errors.append("unexpected skill files: " + ", ".join(sorted(unexpected_files)))
    if errors:
        return errors

    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(r"(?m)^name:\s*([^\s]+)\s*$", skill_text)
    if match is None or match.group(1) != SKILL_NAME:
        errors.append("SKILL.md name must match the Cursor skill folder")

    for path in sorted(SKILL_ROOT.rglob("*")):
        if path.is_symlink():
            errors.append(f"symlink is not allowed in the skill: {path.relative_to(SKILL_ROOT)}")
            continue
        if not path.is_file() or path.suffix.lower() not in {".md", ".py", ".json"}:
            continue
        text = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_TEXT:
            if forbidden.lower() in text.lower():
                errors.append(f"host-specific text in {path.relative_to(SKILL_ROOT)}: {forbidden}")
        for label, pattern in FORBIDDEN_PATH_PATTERNS:
            if pattern.search(text):
                errors.append(f"host-specific path in {path.relative_to(SKILL_ROOT)}: {label}")

    for relative, needle in REQUIRED_TEXT:
        text = (SKILL_ROOT / relative).read_text(encoding="utf-8")
        if needle not in text:
            errors.append(f"missing required guard text in {relative}: {needle}")

    if SETTINGS_PATH.is_symlink() or not SETTINGS_PATH.is_file():
        errors.append("canonical AN-S182 settings file is missing or unsafe")
    elif digest(SETTINGS_PATH) != EXPECTED_SETTINGS_SHA256:
        errors.append("canonical AN-S182 settings SHA-256 mismatch")

    if errors:
        return errors

    for script_name in SELF_TESTS:
        script = SKILL_ROOT / "scripts" / script_name
        result = subprocess.run(
            [sys.executable, str(script), "--self-test"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout).strip()
            errors.append(f"self-test failed for {script_name}: {message}")
    return errors


def resolve_case_inputs(product_model: str, require_materials: bool) -> tuple[list[str], dict]:
    command = [
        sys.executable,
        str(SKILL_ROOT / "scripts" / "resolve_product_inputs.py"),
        "--project-root",
        str(REPO_ROOT),
        "--product-model",
        product_model,
    ]
    if require_materials:
        command.append("--require-materials")
    result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return ["HOLD_PRODUCT_VIDEO_SETTINGS"], {}
    if not isinstance(payload, dict):
        return ["HOLD_PRODUCT_VIDEO_SETTINGS"], {}
    if payload.get("status") == "READY":
        return [], payload
    hold = payload.get("hold")
    return [hold if isinstance(hold, str) else "HOLD_PRODUCT_VIDEO_SETTINGS"], payload


def validate_materials(root: Path) -> tuple[list[str], dict]:
    errors: list[str] = []
    summary = {
        "folder": root.name,
        "media_file_count": 0,
        "probe_valid_media_count": 0,
        "distinct_media_sha256_count": 0,
    }
    if root.is_symlink() or not root.is_dir():
        return ["HOLD_INPUT_MATERIALS_REQUIRED"], summary

    media_files = sorted(
        path for path in root.rglob("*")
        if path.is_file() and not path.is_symlink() and path.suffix.lower() in MEDIA_SUFFIXES
    )
    valid_media: list[Path] = []
    for path in media_files:
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=format_name,duration", "-of", "json", str(path)],
                text=True,
                capture_output=True,
                check=False,
            )
        except FileNotFoundError:
            return ["HOLD_FFPROBE_REQUIRED"], summary
        if probe.returncode == 0:
            valid_media.append(path)

    hashes = {digest(path) for path in valid_media}
    summary.update(
        media_file_count=len(media_files),
        probe_valid_media_count=len(valid_media),
        distinct_media_sha256_count=len(hashes),
    )
    if len(valid_media) != len(media_files):
        errors.append("HOLD_MEDIA_PROBE_FAILED")
    if len(valid_media) < 8 or len(hashes) < 8:
        errors.append("HOLD_DISTINCT_MATERIALS_REQUIRED")
    return errors, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-materials", action="store_true")
    parser.add_argument("--product-model", default="AN-S182")
    args = parser.parse_args()

    static_errors = validate_static()
    if static_errors:
        print(json.dumps({"status": "FAIL", "errors": static_errors}, ensure_ascii=False, indent=2))
        return 1

    resolve_errors, resolved = resolve_case_inputs(args.product_model, require_materials=False)
    if resolve_errors:
        print(json.dumps({"status": "HOLD", "errors": resolve_errors, "resolved": resolved}, ensure_ascii=False, indent=2))
        return 2

    material_root = Path(resolved["material_root"])
    material_errors, material_summary = validate_materials(material_root)
    material_summary["product_model"] = args.product_model
    material_summary["settings_path"] = resolved.get("settings_path")
    material_summary["drive_folder_title"] = resolved.get("drive_folder_title")
    if material_errors and args.require_materials:
        print(json.dumps({"status": "HOLD", "errors": material_errors, "materials": material_summary, "resolved": resolved}, ensure_ascii=False, indent=2))
        return 2

    status = "READY" if not material_errors else "STATIC_READY_MATERIALS_PENDING"
    print(json.dumps({"status": status, "materials": material_summary, "resolved": resolved}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
