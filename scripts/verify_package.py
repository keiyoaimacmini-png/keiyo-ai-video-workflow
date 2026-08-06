#!/usr/bin/env python3
"""Fail-closed verifier for the portable KEIYO plugin repository."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path, PurePosixPath


PLUGIN_ID = "keiyo-product-video"
MARKETPLACE_ID = "keiyo-ai-video-workflow"
SKILL = "plugins/keiyo-product-video/skills/create-tiktok-product-video"
PINNED_SKILL_HASHES = {
    f"{SKILL}/SKILL.md": "4eb189bfb5f06399457c20a6d80f37e71de2835a04190b742c9e27e9dc21ae5f",
    f"{SKILL}/agents/openai.yaml": "18695ed5a17f88debe464682cd9f81cb79d94a302c81d7b2b6123347f1df081f",
    f"{SKILL}/references/payload_contract.md": "6d05f728b5fa87b842b9f3c2feeb608c773d17dd8cca8bb41c8e2ca05a7fbba6",
    f"{SKILL}/scripts/validate_product_video_payload.py": "de10506d1ab9ae6260df3a6d3ae43c524897cd3de643293b9a422a0f2462f6ee",
}
REQUIRED_FILES = {
    ".gitattributes",
    ".github/workflows/windows-verify.yml",
    ".agents/plugins/marketplace.json",
    ".gitignore",
    "README.md",
    "docs/INSTALL_SOL_ADVISOR_JA.md",
    "golden-baselines/an-s182/v1/EVIDENCE.sha256",
    "golden-baselines/an-s182/v1/README_JA.md",
    "golden-baselines/an-s182/v1/acceptance.json",
    "golden-baselines/an-s182/v1/audio-layout.json",
    "golden-baselines/an-s182/v1/baseline.manifest.json",
    "golden-baselines/an-s182/v1/caption-style.json",
    "golden-baselines/an-s182/v1/environment.json",
    "golden-baselines/an-s182/v1/export-settings.json",
    "golden-baselines/an-s182/v1/material-map.json",
    "golden-baselines/an-s182/v1/timeline.json",
    "golden-baselines/an-s182/v1/windows-reproduction.md",
    "golden-baselines/an-s182/v2/EVIDENCE.sha256",
    "golden-baselines/an-s182/v2/README_JA.md",
    "golden-baselines/an-s182/v2/acceptance.json",
    "golden-baselines/an-s182/v2/audio-layout.json",
    "golden-baselines/an-s182/v2/baseline.manifest.json",
    "golden-baselines/an-s182/v2/caption-style.json",
    "golden-baselines/an-s182/v2/environment.json",
    "golden-baselines/an-s182/v2/export-settings.json",
    "golden-baselines/an-s182/v2/material-map.json",
    "golden-baselines/an-s182/v2/timeline.json",
    "golden-baselines/an-s182/v2/windows-reproduction.md",
    "MANIFEST.sha256",
    "plugins/keiyo-product-video/.codex-plugin/plugin.json",
    "scripts/bootstrap.ps1",
    "scripts/bootstrap.sh",
    "scripts/build_capcut_golden_baseline.py",
    "scripts/install-sol-advisor.sh",
    "scripts/verify_golden_baseline.py",
    "scripts/verify_golden_baseline_v2.py",
    "scripts/verify-release.sh",
    "scripts/verify_package.py",
    "scripts/verify-windows.ps1",
    "tests/test_package_verifier.py",
    "tests/test_windows_automation.py",
    "tests/test_golden_baseline.py",
    "tests/test_golden_baseline_v2.py",
    *PINNED_SKILL_HASHES,
}
DENIED_SUFFIXES = {
    ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".mp3", ".wav", ".m4a",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".db", ".sqlite", ".sqlite3",
    ".zip", ".7z", ".tar", ".gz", ".pem", ".key", ".p12", ".mobileprovision",
}
FORBIDDEN_CONTENT = {
    "macOS user path": re.compile(b"/" + b"Users" + rb"/[A-Za-z0-9._-]+/"),
    "Google Drive folder destination": re.compile(b"https://drive.google.com/drive/" + b"folders/", re.I),
    "cloud provider local path": re.compile(b"Cloud" + b"Storage" + b"|Google" + rb"Drive-[^/\s]+", re.I),
    "project-local private memory": re.compile(rb"(?:^|[/'\"`])\.local/", re.M),
    "GitHub classic token": re.compile(b"gh" + rb"[pousr]_[A-Za-z0-9]{20,}"),
    "GitHub fine-grained token": re.compile(b"github" + rb"_pat_[A-Za-z0-9_]{20,}"),
    "OpenAI-style secret": re.compile(b"s" + rb"k-[A-Za-z0-9_-]{20,}"),
    "AWS access key": re.compile(b"AK" + rb"IA[0-9A-Z]{16}"),
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def safe_manifest_path(value: str) -> bool:
    if not value or "\\" in value or value.startswith(("/", "~")):
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


def parse_manifest(path: Path) -> tuple[dict[str, str], list[str]]:
    entries: dict[str, str] = {}
    errors: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return {}, [f"cannot read MANIFEST.sha256: {exc}"]
    previous = ""
    for line_number, line in enumerate(lines, 1):
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            errors.append(f"MANIFEST.sha256:{line_number}: invalid line")
            continue
        digest, relative = match.groups()
        if not safe_manifest_path(relative) or relative == "MANIFEST.sha256":
            errors.append(f"MANIFEST.sha256:{line_number}: unsafe or self-referential path")
        if relative in entries:
            errors.append(f"MANIFEST.sha256:{line_number}: duplicate path")
        if previous and relative <= previous:
            errors.append(f"MANIFEST.sha256:{line_number}: entries are not strictly sorted")
        previous = relative
        entries[relative] = digest
    return entries, errors


def distribution_files(root: Path) -> tuple[set[str], list[str]]:
    files: set[str] = set()
    errors: list[str] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if relative == ".git" or relative.startswith(".git/"):
            continue
        if path.is_symlink():
            errors.append(f"symlink forbidden: {relative}")
            continue
        if path.is_dir():
            if path.name in {"__pycache__", ".pytest_cache", ".local"}:
                errors.append(f"generated/private directory forbidden: {relative}")
            continue
        if not path.is_file():
            errors.append(f"non-regular file forbidden: {relative}")
            continue
        if relative != "MANIFEST.sha256":
            files.add(relative)
        if path.suffix.casefold() in DENIED_SUFFIXES:
            errors.append(f"binary, media, database, archive, or key file forbidden: {relative}")
    return files, errors


def validate_json(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        plugin = json.loads((root / "plugins/keiyo-product-video/.codex-plugin/plugin.json").read_text(encoding="utf-8"))
        if plugin.get("name") != PLUGIN_ID or plugin.get("skills") != "./skills/":
            errors.append("plugin.json identity or skills path mismatch")
        if plugin.get("version") != "1.0.0":
            errors.append("plugin.json version mismatch")
        interface = plugin.get("interface") or {}
        if interface.get("defaultPrompt") != ["Use $create-tiktok-product-video to prepare and validate a new TikTok product video payload."]:
            errors.append("plugin.json defaultPrompt mismatch")
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"invalid plugin.json: {exc}")
    try:
        market = json.loads((root / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
        rows = market.get("plugins", [])
        expected = {
            "name": PLUGIN_ID,
            "source": {"source": "local", "path": "./plugins/keiyo-product-video"},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": "Productivity",
        }
        if market.get("name") != MARKETPLACE_ID or rows != [expected]:
            errors.append("marketplace identity or plugin entry mismatch")
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"invalid marketplace.json: {exc}")
    return errors


def forbidden_content_errors(root: Path, relative_paths: set[str]) -> list[str]:
    errors: list[str] = []
    for relative in sorted(relative_paths):
        path = root / relative
        try:
            data = path.read_bytes()
        except OSError as exc:
            errors.append(f"cannot read {relative}: {exc}")
            continue
        if relative == ".gitignore":
            private_memory_rule = b"." + b"local/"
            data = b"\n".join(line for line in data.splitlines() if line.strip() != private_memory_rule)
        for label, pattern in FORBIDDEN_CONTENT.items():
            if pattern.search(data):
                errors.append(f"{label} forbidden in {relative}")
    return errors


def verify(root: Path) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    entries, manifest_errors = parse_manifest(root / "MANIFEST.sha256")
    files, tree_errors = distribution_files(root)
    errors.extend(manifest_errors)
    errors.extend(tree_errors)
    missing_required = REQUIRED_FILES - ({"MANIFEST.sha256"} | files)
    if missing_required:
        errors.append("missing required files: " + ", ".join(sorted(missing_required)))
    if files != set(entries):
        missing = files - set(entries)
        extra = set(entries) - files
        if missing:
            errors.append("files missing from manifest: " + ", ".join(sorted(missing)))
        if extra:
            errors.append("manifest references missing files: " + ", ".join(sorted(extra)))
    for relative, expected in entries.items():
        path = root / relative
        if path.is_file() and not path.is_symlink() and sha256(path) != expected:
            errors.append(f"hash mismatch: {relative}")
    for relative, expected in PINNED_SKILL_HASHES.items():
        path = root / relative
        if path.is_file() and sha256(path) != expected:
            errors.append(f"pinned skill hash mismatch: {relative}")
    errors.extend(validate_json(root))
    errors.extend(forbidden_content_errors(root, files))
    baseline_verifier_path = root / "scripts/verify_golden_baseline.py"
    if baseline_verifier_path.is_file():
        try:
            spec = importlib.util.spec_from_file_location("portable_verify_golden_baseline", baseline_verifier_path)
            if spec is None or spec.loader is None:
                errors.append("cannot load golden baseline verifier")
            else:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                errors.extend(
                    f"golden baseline: {error}"
                    for error in module.verify(root / "golden-baselines/an-s182/v1")
                )
        except Exception as exc:  # fail closed for a distribution verifier
            errors.append(f"golden baseline verifier failed: {exc}")
    current_baseline_verifier_path = root / "scripts/verify_golden_baseline_v2.py"
    if current_baseline_verifier_path.is_file():
        try:
            spec = importlib.util.spec_from_file_location(
                "portable_verify_golden_baseline_v2",
                current_baseline_verifier_path,
            )
            if spec is None or spec.loader is None:
                errors.append("cannot load golden baseline v2 verifier")
            else:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                errors.extend(
                    f"golden baseline v2: {error}"
                    for error in module.verify(root / "golden-baselines/an-s182/v2")
                )
        except Exception as exc:  # fail closed for a distribution verifier
            errors.append(f"golden baseline v2 verifier failed: {exc}")
    return errors


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    errors = verify(root)
    if errors:
        print("INVALID_PACKAGE")
        for error in sorted(set(errors)):
            print(f"- {error}")
        return 1
    print(f"PASS_PACKAGE files={len(distribution_files(root)[0])} manifest_sha256={sha256(root / 'MANIFEST.sha256')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
