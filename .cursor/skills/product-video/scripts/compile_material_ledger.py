#!/usr/bin/env python3
"""Compile Obsidian material notes into the visual catalog.

Notes are the source of truth when their source size and mtime match the
video. This does not watch video. Missing or stale notes are listed for a
separate Gemini stills pass.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from material_duration import relative_key
from material_index import file_stamp, iter_videos
from paths import emit
from resolve_product_inputs import default_material_root
from visual_catalog import load_catalog, normalize_scene, refresh_catalog, save_catalog
from workflow_state import hold

HEADING = re.compile(r"^##\s+([0-9]+(?:\.[0-9]+)?)[–-]([0-9]+(?:\.[0-9]+)?)\s*$")
FIELD = re.compile(
    r"^(factual_description|objects|actions|product_state|location|framing|visible_features|product_visible|product_parts):\s*(.*)$"
)
LIST_SPLIT = re.compile(r"[、,]")


def ledger_root() -> Path:
    env = os.environ.get("PRODUCT_VIDEO_LEDGER_ROOT", "").strip()
    if env:
        return Path(env)
    return Path.home() / "Documents" / "product-video-materials"


def obsidian_running() -> bool:
    proc = subprocess.run(["pgrep", "-x", "Obsidian"], check=False, capture_output=True, text=True)
    return proc.returncode == 0 and bool((proc.stdout or "").strip())


def split_list(value: str) -> list[str]:
    return [item.strip() for item in LIST_SPLIT.split(value) if item.strip()]


def parse_note(text: str) -> tuple[dict[str, str], list[dict[str, Any]]]:
    meta: dict[str, str] = {}
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            raw = text[3:end]
            body = text[end + 4 :]
            for line in raw.splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                meta[key.strip()] = value.strip()
    scenes: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in body.splitlines():
        heading = HEADING.match(line.strip())
        if heading:
            if current is not None:
                scenes.append(current)
            current = {"source_in": float(heading.group(1)), "source_out": float(heading.group(2))}
            continue
        if current is None:
            continue
        field = FIELD.match(line.strip())
        if not field:
            continue
        key, value = field.group(1), field.group(2).strip()
        if key in {"objects", "actions", "visible_features", "product_parts"}:
            current[key] = split_list(value)
        else:
            current[key] = value
    if current is not None:
        scenes.append(current)
    return meta, scenes


def note_matches_video(meta: dict[str, str], video: Path) -> bool:
    stat = video.stat()
    return meta.get("source_size") == str(stat.st_size) and meta.get("source_mtime_ns") == str(stat.st_mtime_ns)


def scene_lines_from_catalog(catalog: dict[str, Any]) -> str:
    seen: set[str] = set()
    lines: list[str] = []
    files = catalog.get("files") if isinstance(catalog, dict) else None
    if not isinstance(files, dict):
        return ""
    for entry in files.values():
        if not isinstance(entry, dict):
            continue
        for scene in entry.get("scenes") or []:
            if not isinstance(scene, dict):
                continue
            parts = []
            for label, key in (
                ("画面", "factual_description"),
                ("物", "objects"),
                ("動作", "actions"),
                ("商品の状態", "product_state"),
                ("場所", "location"),
                ("画角", "framing"),
            ):
                value = scene.get(key)
                if isinstance(value, list):
                    text = "、".join(str(item).strip() for item in value if str(item).strip())
                else:
                    text = str(value or "").strip()
                if text:
                    parts.append(f"{label}: {text}")
            row = " / ".join(parts)
            if row and row not in seen:
                seen.add(row)
                lines.append(f"- {row}")
    return "\n".join(lines)


def compile_ledger(
    project_root: Path,
    product_model: str,
    *,
    material_root: Path | None = None,
    vault_root: Path | None = None,
    wait_for_sync: bool = True,
) -> dict[str, Any]:
    if not obsidian_running():
        return hold("HOLD_OBSIDIAN_NOT_OPEN", "Obsidian is not running on this Mac")
    root = vault_root or ledger_root()
    product_dir = root / product_model
    if wait_for_sync and not product_dir.is_dir():
        time.sleep(20)
    if not product_dir.is_dir():
        return hold("HOLD_MATERIAL_LEDGER_VAULT_MISSING", f"ledger folder is missing: {product_dir}")
    material = material_root or default_material_root(project_root, product_model)
    refresh_catalog(project_root, product_model, material)
    catalog = load_catalog(project_root, product_model)
    files = catalog.setdefault("files", {})
    videos = {path.resolve(): path for path in iter_videos(material)}
    applied = 0
    reused = 0
    needs_vision: list[str] = []
    for video in videos.values():
        rel = video.relative_to(material).as_posix()
        note = product_dir / Path(rel).with_suffix(".md")
        try:
            source = video.resolve().relative_to(project_root.resolve()).as_posix()
        except ValueError:
            source = str(video)
        key = relative_key(source)
        entry = files.get(key)
        if not isinstance(entry, dict):
            stamp = file_stamp(video)
            entry = {
                "source": source,
                "mtime_ns": stamp.get("mtime_ns"),
                "size": stamp.get("size"),
                "sidecars": stamp.get("sidecars") or [],
                "needs_observation": True,
                "scenes": [],
            }
            files[key] = entry
        if not note.is_file():
            needs_vision.append(rel)
            continue
        meta, raw_scenes = parse_note(note.read_text(encoding="utf-8"))
        if not note_matches_video(meta, video):
            needs_vision.append(rel)
            continue
        note_mtime = note.stat().st_mtime_ns
        if entry.get("ledger_note_mtime_ns") == note_mtime and entry.get("scenes"):
            reused += 1
            continue
        scenes = []
        for raw in raw_scenes:
            scene = normalize_scene({**raw, "source": source}, source=source)
            if scene is not None:
                scenes.append(scene)
        if not scenes:
            needs_vision.append(rel)
            continue
        entry["scenes"] = scenes
        entry["needs_observation"] = False
        entry["ledger_note_mtime_ns"] = note_mtime
        entry["source"] = source
        applied += 1
    path = save_catalog(project_root, catalog)
    payload: dict[str, Any] = {
        "status": "needs_vision" if needs_vision else "OK",
        "catalog": path.as_posix(),
        "applied": applied,
        "reused": reused,
        "needs_vision": needs_vision,
        "scene_text": scene_lines_from_catalog(catalog),
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--product-model", required=True)
    parser.add_argument("--material-root", type=Path)
    parser.add_argument("--vault-root", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        meta, scenes = parse_note(
            "---\nsource_size: 3\nsource_mtime_ns: 9\n---\n\n## 0.000–1.500\n"
            "factual_description: 手が機器を持つ\nobjects: 手、機器\nactions: 持つ\n"
            "product_state: 画面消灯\nlocation: 室内\nframing: クローズアップ\nvisible_features: 白いベゼル\n"
        )
        ok = (
            meta.get("source_size") == "3"
            and len(scenes) == 1
            and scenes[0]["objects"] == ["手", "機器"]
            and scenes[0]["source_out"] == 1.5
        )
        emit({"status": "OK" if ok else "HOLD", "hold": "" if ok else "SELF_TEST"})
        return 0 if ok else 2
    payload = compile_ledger(
        args.project_root.resolve(),
        args.product_model,
        material_root=args.material_root,
        vault_root=args.vault_root,
    )
    emit(payload)
    return 0 if payload.get("status") in {"OK", "needs_vision"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
