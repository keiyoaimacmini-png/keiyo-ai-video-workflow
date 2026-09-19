#!/usr/bin/env python3
"""Fail-closed check for the current /product-video layout."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ENTRY_SKILL = "product-video"
SKILL_DATE = "20260919"
ENTRY_ROOT = REPO_ROOT / ".cursor" / "skills" / ENTRY_SKILL
SETTINGS_PATH = REPO_ROOT / "config" / "product_video_settings_AN-S182.v1.json"
EXPECTED_SETTINGS_SHA256 = "ef6865669fcf07a3a71423881be716e7a5c34dd7d588c8aea8d80e986fbf9c5f"
LOGICAL_STAGE_SKILLS = (
    "product-video-prepare",
    "product-video-script",
    "product-video-narration",
    "product-video-assembly",
    "product-video-rough-edit",
    "product-video-delivery",
)
REMOVED_SKILL_DIRS = (
    "produce-tiktok-product-video-portable",
    "produce-tiktok-product-video-v3",
)
REQUIRED_HELPERS = (
    "resolve_product_inputs.py",
    "send_gemini_cli_prompt.py",
    "capture_capcut_result_audio.py",
    "prove_source_range.py",
    "upload_drive_local_file.py",
    "purge_local_working_media.py",
    "run_preflight.py",
    "dispatch.py",
)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def frontmatter_name(path: Path) -> str | None:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip()
    return None


def validate_static() -> list[str]:
    errors: list[str] = []
    entry = ENTRY_ROOT / "SKILL.md"
    if not entry.is_file():
        return ["missing /product-video entrypoint"]
    if frontmatter_name(entry) != ENTRY_SKILL:
        errors.append("entrypoint frontmatter name must stay product-video")
    skills_root = REPO_ROOT / ".cursor" / "skills"
    for removed in REMOVED_SKILL_DIRS:
        if (skills_root / removed).exists():
            errors.append(f"legacy skill still present: {removed}")
    for logical in LOGICAL_STAGE_SKILLS:
        dated = f"{logical}-{SKILL_DATE}"
        if (skills_root / logical).exists():
            errors.append(f"undated stage skill must not remain: {logical}")
        skill_md = skills_root / dated / "SKILL.md"
        if not skill_md.is_file():
            errors.append(f"missing dated skill: {dated}")
            continue
        if frontmatter_name(skill_md) != dated:
            errors.append(f"frontmatter name must match folder: {dated}")
    for name in REQUIRED_HELPERS:
        path = ENTRY_ROOT / "scripts" / name
        if not path.is_file():
            errors.append(f"missing helper: {name}")
    if SETTINGS_PATH.is_symlink() or not SETTINGS_PATH.is_file():
        errors.append("canonical AN-S182 settings file is missing or unsafe")
    elif digest(SETTINGS_PATH) != EXPECTED_SETTINGS_SHA256:
        errors.append("canonical AN-S182 settings SHA-256 mismatch")
    return errors


def resolve_case_inputs(product_model: str, require_materials: bool) -> tuple[list[str], dict]:
    command = [
        sys.executable,
        str(ENTRY_ROOT / "scripts" / "resolve_product_inputs.py"),
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


def material_folder_status(root: Path) -> tuple[list[str], dict]:
    summary = {"folder": root.name, "material_root_exists": False}
    if root.is_symlink() or not root.is_dir():
        return ["HOLD_INPUT_MATERIALS_REQUIRED"], summary
    summary["material_root_exists"] = True
    return [], summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-materials", action="store_true")
    parser.add_argument("--product-model", default="AN-S182")
    args = parser.parse_args()

    static_errors = validate_static()
    if static_errors:
        print(json.dumps({"status": "FAIL", "errors": static_errors}, ensure_ascii=False, indent=2))
        return 1

    resolve_errors, resolved = resolve_case_inputs(args.product_model, require_materials=args.require_materials)
    if resolve_errors:
        print(json.dumps({"status": "HOLD", "errors": resolve_errors, "resolved": resolved}, ensure_ascii=False, indent=2))
        return 2

    material_root = Path(resolved["material_root"])
    material_errors, material_summary = material_folder_status(material_root)
    material_summary["product_model"] = args.product_model
    material_summary["settings_path"] = resolved.get("settings_path")
    material_summary["drive_folder_title"] = resolved.get("drive_folder_title")
    if material_errors and args.require_materials:
        print(
            json.dumps(
                {
                    "status": "HOLD",
                    "errors": material_errors,
                    "materials": material_summary,
                    "resolved": resolved,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    status = "READY" if not material_errors else "STATIC_READY_MATERIALS_PENDING"
    print(json.dumps({"status": status, "materials": material_summary, "resolved": resolved}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
