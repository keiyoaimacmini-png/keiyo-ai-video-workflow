#!/usr/bin/env python3
"""Resolve per-case product settings, material root, and Drive folder title.

Product model, settings file, and material folder change per case.
Checkpoint texts, validators, and delivery rules stay in the skill package.
This script never copies another model's settings, never writes media, and
never stores Drive IDs, URLs, tokens, or account identifiers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


MODEL_RE = re.compile(r"^AN-[A-Z0-9]{4,6}$")
SETTINGS_NAME = "product_video_settings_{model}.v1.json"
HOLD_MODEL = "HOLD_MODEL_UNVERIFIED"
HOLD_SETTINGS = "HOLD_PRODUCT_VIDEO_SETTINGS"
HOLD_MATERIALS = "HOLD_INPUT_MATERIALS_REQUIRED"
AN_S182_SETTINGS_SHA256 = "a90ee56e42e8ddfcc9c4fec7970bffcc1e4396bbe6dcd37df9a2f74b399e0afa"


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def default_material_root(project_root: Path, product_model: str) -> Path:
    return project_root / ".runtime" / "product-video-inputs" / f"{product_model}_コピー"


def resolve_material_root(project_root: Path, product_model: str, configured: str | None) -> Path:
    if configured:
        return Path(configured).expanduser()
    return default_material_root(project_root, product_model)


def settings_path_for(project_root: Path, product_model: str) -> Path:
    return project_root / "config" / SETTINGS_NAME.format(model=product_model)


def hold_payload(code: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": "HOLD", "hold": code}
    payload.update(extra)
    return payload


def resolve_product_inputs(
    project_root: Path,
    product_model: str,
    *,
    material_root_env: str | None = None,
    require_materials: bool = False,
) -> dict[str, Any]:
    if not MODEL_RE.fullmatch(product_model):
        return hold_payload(HOLD_MODEL, product_model=product_model)

    if project_root.is_symlink() or not project_root.is_dir():
        return hold_payload(HOLD_SETTINGS, reason="project_root must be a real directory")

    settings_path = settings_path_for(project_root, product_model)
    if settings_path.is_symlink() or not settings_path.is_file():
        return hold_payload(
            HOLD_SETTINGS,
            product_model=product_model,
            expected_settings_path=settings_path.as_posix(),
            reason="do not copy another model's settings file; add this model's exact file",
        )

    digest = sha256_file(settings_path)
    if product_model == "AN-S182" and digest != AN_S182_SETTINGS_SHA256:
        return hold_payload(
            HOLD_SETTINGS,
            product_model=product_model,
            expected_settings_path=settings_path.as_posix(),
            reason="canonical AN-S182 settings SHA-256 mismatch",
        )

    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return hold_payload(HOLD_SETTINGS, product_model=product_model, reason="settings JSON is unreadable")
    if not isinstance(settings, dict) or settings.get("product_model") != product_model:
        return hold_payload(
            HOLD_SETTINGS,
            product_model=product_model,
            reason="settings.product_model must equal the requested model",
        )

    material_root = resolve_material_root(project_root, product_model, material_root_env)
    materials_present = material_root.is_dir() and not material_root.is_symlink()
    payload: dict[str, Any] = {
        "status": "READY",
        "product_model": product_model,
        "settings_path": settings_path.as_posix(),
        "settings_sha256": digest,
        "material_root": material_root.as_posix(),
        "material_root_exists": materials_present,
        "drive_folder_title": product_model,
        "delivery_mode_default": "drive",
        "export_only_requires_explicit_request": True,
    }
    if require_materials and not materials_present:
        payload.update(hold_payload(HOLD_MATERIALS, **{k: v for k, v in payload.items() if k != "status" and k != "hold"}))
        payload["status"] = "HOLD"
        payload["hold"] = HOLD_MATERIALS
    return payload


def self_test() -> int:
    checks: list[tuple[str, bool]] = []

    def check(name: str, ok: bool) -> None:
        checks.append((name, ok))
        if not ok:
            raise AssertionError(name)

    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        config = root / "config"
        config.mkdir()
        an_dir = root / ".runtime" / "product-video-inputs" / "AN-S999_コピー"
        an_dir.mkdir(parents=True)
        settings = {
            "schema_version": "1",
            "status": "active",
            "product_model": "AN-S999",
            "cta": {"text": "下からチェック！", "literal_match_required": True},
        }
        settings_path = config / "product_video_settings_AN-S999.v1.json"
        settings_path.write_text(json.dumps(settings, ensure_ascii=False) + "\n", encoding="utf-8")

        ready = resolve_product_inputs(root, "AN-S999", require_materials=True)
        check("ready-new-model", ready.get("status") == "READY")
        check("settings-path-uses-model", ready.get("settings_path") == settings_path.as_posix())
        check("material-root-uses-model", ready.get("material_root") == an_dir.as_posix())
        check("drive-title-is-model", ready.get("drive_folder_title") == "AN-S999")
        check("delivery-default-drive", ready.get("delivery_mode_default") == "drive")

        missing_model = resolve_product_inputs(root, "NOT-A-MODEL")
        check("bad-model-hold", missing_model.get("hold") == HOLD_MODEL)

        other = resolve_product_inputs(root, "AN-Z001", require_materials=True)
        check("missing-settings-hold", other.get("hold") == HOLD_SETTINGS)
        check("does-not-reuse-s999-settings", "AN-S999" not in str(other.get("expected_settings_path", "")))

        no_materials = resolve_product_inputs(root, "AN-S999", material_root_env=str(root / "absent"), require_materials=True)
        check("missing-materials-hold", no_materials.get("hold") == HOLD_MATERIALS)

        env_root = root / "custom-materials"
        env_root.mkdir()
        env_ready = resolve_product_inputs(root, "AN-S999", material_root_env=str(env_root), require_materials=True)
        check("env-material-root", env_ready.get("material_root") == env_root.as_posix())
        check("env-ready", env_ready.get("status") == "READY")

        wrong_model_file = config / "product_video_settings_AN-Z002.v1.json"
        wrong_model_file.write_text(
            json.dumps({"schema_version": "1", "status": "active", "product_model": "AN-S999"}) + "\n",
            encoding="utf-8",
        )
        mismatch = resolve_product_inputs(root, "AN-Z002")
        check("settings-model-mismatch", mismatch.get("hold") == HOLD_SETTINGS)

    if not all(ok for _, ok in checks):
        print("SELF-TEST FAILED: resolve_product_inputs", flush=True)
        return 1
    print("SELF-TEST PASSED: resolve_product_inputs")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--product-model")
    parser.add_argument("--require-materials", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.project_root is None or args.product_model is None:
        parser.error("--project-root and --product-model are required unless --self-test is used")
    payload = resolve_product_inputs(
        args.project_root,
        args.product_model,
        material_root_env=os.environ.get("PRODUCT_VIDEO_MATERIAL_ROOT"),
        require_materials=args.require_materials,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("status") == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
