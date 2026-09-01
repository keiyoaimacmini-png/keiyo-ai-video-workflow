#!/usr/bin/env python3
"""Build a deterministic, provider-neutral active-rule snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


STAGES = ("script", "edit", "delivery")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_file(root: Path, relative: Path) -> Path | None:
    candidate = root / relative
    if not candidate.exists():
        return None
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError(f"rule input is not a regular non-symlink file: {relative.as_posix()}")
    resolved_root = root.resolve(strict=True)
    resolved = candidate.resolve(strict=True)
    if os.path.commonpath((str(resolved_root), str(resolved))) != str(resolved_root):
        raise ValueError(f"rule input escapes rules root: {relative.as_posix()}")
    return resolved


def build_snapshot(rules_root: Path | None, stage: str, product_model: str) -> dict:
    selected: list[dict] = []
    if rules_root is not None:
        if rules_root.is_symlink() or not rules_root.is_dir():
            raise ValueError("rules root must be a real directory")
        candidates = (
            Path("common.md"),
            Path("stages") / f"{stage}.md",
            Path("products") / product_model / "common.md",
            Path("products") / product_model / f"{stage}.md",
        )
        for relative in candidates:
            path = safe_file(rules_root, relative)
            if path is None:
                continue
            data = path.read_bytes()
            selected.append(
                {
                    "path": relative.as_posix(),
                    "sha256": sha256(data),
                    "text": data.decode("utf-8"),
                }
            )
    base = {
        "schema": "product_video_rule_snapshot.v1",
        "stage": stage,
        "product_model": product_model,
        "rules": selected,
    }
    canonical = json.dumps(base, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {**base, "snapshot_sha256": sha256(canonical)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rules-root", type=Path)
    parser.add_argument("--stage", choices=STAGES, required=True)
    parser.add_argument("--product-model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.output.exists() or args.output.is_symlink():
        print(f"refusing to overwrite output: {args.output}", file=sys.stderr)
        return 2
    if not args.output.parent.is_dir():
        print(f"output parent does not exist: {args.output.parent}", file=sys.stderr)
        return 2

    try:
        snapshot = build_snapshot(args.rules_root, args.stage, args.product_model)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    payload = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    args.output.write_text(payload, encoding="utf-8")
    print(sha256(payload.encode("utf-8")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
