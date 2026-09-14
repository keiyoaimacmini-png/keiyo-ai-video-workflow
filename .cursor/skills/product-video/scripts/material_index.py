#!/usr/bin/env python3
"""Persistent per-product material index. Refresh only changed files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Callable

from approved_shots import load_history, simple_tags
from constants import PERSISTENT_MATERIAL_INDEX_RELATIVE, VIDEO_EXTENSIONS
from material_duration import (
    ensure_duration,
    load_metadata,
    lookup_duration,
    parse_sidecar_md,
    relative_key,
    sidecar_paths,
)
from paths import emit
from workflow_state import atomic_write

SCHEMA = "product_video_material_index.v1"
ALIASES_SCHEMA = "product_video_material_semantic_aliases.v1"
MIN_ALIAS_CHARS = 2
SIDECAR_SITUATION = re.compile(r"^(?:situation|シチュエーション)\s*[:=]\s*(.+)$", re.IGNORECASE)
SIDECAR_TAGS = re.compile(r"^(?:tags?|semantic_tags?|scenario_tags?)\s*[:=]\s*(.+)$", re.IGNORECASE)
SIDECAR_FRAMING = re.compile(r"^(?:framing|camera_distance|画角|距離)\s*[:=]\s*(.+)$", re.IGNORECASE)
SIDECAR_SCENE = re.compile(
    r"^(?:scene(?:_range)?|usable_range)\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*[-~〜]\s*([0-9]+(?:\.[0-9]+)?)\s*(.*)$",
    re.IGNORECASE,
)
TOKEN_SPLIT = re.compile(r"[、。！？!?,.・/\s]+")


def index_dir(project_root: Path) -> Path:
    return Path(project_root) / Path(*Path(PERSISTENT_MATERIAL_INDEX_RELATIVE).parts)


def index_path(project_root: Path, product_model: str) -> Path:
    return index_dir(project_root) / f"{product_model}.v1.json"


def aliases_runtime_path(project_root: Path, product_model: str) -> Path:
    return index_dir(project_root) / f"{product_model}.semantic-aliases.v1.json"


def aliases_config_path(project_root: Path, product_model: str) -> Path:
    return Path(project_root) / "config" / f"product_video_material_aliases_{product_model}.v1.json"


def empty_index(product_model: str) -> dict[str, Any]:
    return {"schema": SCHEMA, "product_model": product_model, "files": {}}


def load_index(project_root: Path, product_model: str) -> dict[str, Any]:
    path = index_path(project_root, product_model)
    if not path.is_file():
        return empty_index(product_model)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_index(product_model)
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return empty_index(product_model)
    if data.get("product_model") != product_model:
        return empty_index(product_model)
    if not isinstance(data.get("files"), dict):
        data["files"] = {}
    return data


def save_index(project_root: Path, data: dict[str, Any]) -> Path:
    path = index_path(project_root, str(data["product_model"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return path


def file_stamp(video: Path) -> dict[str, Any]:
    stat = video.stat()
    sidecars = []
    for sidecar in sidecar_paths(video):
        if not sidecar.is_file():
            continue
        extra = sidecar.stat()
        sidecars.append(
            {
                "name": sidecar.name,
                "mtime_ns": extra.st_mtime_ns,
                "size": extra.st_size,
            }
        )
    return {"mtime_ns": stat.st_mtime_ns, "size": stat.st_size, "sidecars": sidecars}


def stamp_matches(entry: dict[str, Any] | None, stamp: dict[str, Any]) -> bool:
    if not isinstance(entry, dict):
        return False
    return (
        entry.get("mtime_ns") == stamp.get("mtime_ns")
        and entry.get("size") == stamp.get("size")
        and entry.get("sidecars") == stamp.get("sidecars")
    )


def parse_sidecar_fields(video: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    tags: list[str] = []
    ranges: list[dict[str, Any]] = []
    for sidecar in sidecar_paths(video):
        if not sidecar.is_file():
            continue
        parsed = parse_sidecar_md(sidecar)
        payload.update(parsed)
        try:
            text = sidecar.read_text(encoding="utf-8")
        except OSError:
            continue
        for raw in text.splitlines():
            line = raw.strip()
            match = SIDECAR_SITUATION.match(line)
            if match:
                payload["situation"] = match.group(1).strip().strip("「」")
                continue
            match = SIDECAR_TAGS.match(line)
            if match:
                tags.extend(part.strip() for part in re.split(r"[,、/]", match.group(1)) if part.strip())
                continue
            match = SIDECAR_FRAMING.match(line)
            if match:
                value = match.group(1).strip()
                payload["framing"] = value
                payload["camera_distance"] = value
                continue
            match = SIDECAR_SCENE.match(line)
            if match:
                start = float(match.group(1))
                end = float(match.group(2))
                if end > start:
                    ranges.append(
                        {
                            "source_in": start,
                            "source_out": end,
                            "label": match.group(3).strip() or None,
                        }
                    )
    if tags:
        payload["semantic_tags"] = simple_tags(str(payload.get("situation") or ""), tags)
    if ranges:
        payload["scene_ranges"] = ranges
    elif payload.get("source_in") is not None and payload.get("source_out") is not None:
        payload["scene_ranges"] = [
            {"source_in": payload["source_in"], "source_out": payload["source_out"]}
        ]
    return payload


def classification_folder(material_root: Path, video: Path) -> str:
    try:
        relative = video.resolve().relative_to(material_root.resolve())
    except ValueError:
        return video.parent.name
    parts = relative.parts
    if len(parts) > 1:
        return str(parts[0])
    return ""


def _tokens(*values: str) -> set[str]:
    found: set[str] = set()
    for value in values:
        for part in TOKEN_SPLIT.split(value or ""):
            if len(part) >= 2:
                found.add(part)
    return found


def _alias_list(values: Any) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    if not isinstance(values, list):
        return found
    for item in values:
        text = str(item or "").strip()
        if len(text) < MIN_ALIAS_CHARS or text in seen:
            continue
        seen.add(text)
        found.append(text)
    return found


def normalize_folder_aliases(payload: dict[str, Any] | None) -> dict[str, list[str]]:
    if not isinstance(payload, dict):
        return {}
    raw = payload.get("folder_aliases")
    if not isinstance(raw, dict):
        raw = payload.get("aliases")
    if not isinstance(raw, dict):
        return {}
    mapping: dict[str, list[str]] = {}
    for folder, values in raw.items():
        name = str(folder or "").strip()
        aliases = _alias_list(values)
        if name and aliases:
            mapping[name] = aliases
    return mapping


def _read_aliases_file(path: Path, product_model: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("schema") != ALIASES_SCHEMA:
        return None
    if data.get("product_model") != product_model:
        return None
    return data


def save_aliases(project_root: Path, data: dict[str, Any]) -> Path:
    product_model = str(data["product_model"])
    payload = {
        "schema": ALIASES_SCHEMA,
        "product_model": product_model,
        "folder_aliases": normalize_folder_aliases(data),
    }
    path = aliases_runtime_path(project_root, product_model)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return path


def load_aliases(project_root: Path, product_model: str) -> dict[str, list[str]]:
    root = Path(project_root)
    runtime_path = aliases_runtime_path(root, product_model)
    data = _read_aliases_file(runtime_path, product_model)
    if data is None:
        data = _read_aliases_file(aliases_config_path(root, product_model), product_model)
        if data is not None and not runtime_path.is_file():
            save_aliases(root, data)
    return normalize_folder_aliases(data)


def contained_in_script(needle: str, line: str, situation: str) -> bool:
    text = (needle or "").strip()
    if len(text) < MIN_ALIAS_CHARS:
        return False
    return text in (line or "") or text in (situation or "")


def meaning_match(
    entry: dict[str, Any],
    line: str,
    situation: str,
    *,
    folder_aliases: dict[str, list[str]] | None = None,
) -> bool:
    intended = (situation or "").strip()
    tags = [str(tag).strip() for tag in (entry.get("semantic_tags") or []) if str(tag).strip()]
    if intended and (entry.get("situation") == intended or intended in tags):
        return True
    for tag in tags:
        if contained_in_script(tag, line, situation):
            return True
    folder = str(entry.get("classification_folder") or "").strip()
    if folder and contained_in_script(folder, line, situation):
        return True
    aliases = (folder_aliases or {}).get(folder) or []
    return any(contained_in_script(str(alias), line, situation) for alias in aliases)


def available_from_entry(entry: dict[str, Any]) -> float | None:
    ranges = entry.get("scene_ranges") or []
    if ranges:
        first = ranges[0]
        try:
            return float(first["source_out"]) - float(first["source_in"])
        except (KeyError, TypeError, ValueError):
            return None
    duration = entry.get("full_duration")
    if isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration > 0:
        return float(duration)
    return None


def expand_entry(
    entry: dict[str, Any],
    *,
    line: str,
    situation: str,
    folder_aliases: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(entry, dict):
        return []
    valid = meaning_match(entry, line, situation, folder_aliases=folder_aliases)
    visual = {
        "framing": entry.get("framing") or "",
        "camera_distance": entry.get("camera_distance") or entry.get("framing") or "",
        "location": entry.get("classification_folder") or "",
        "subject": entry.get("situation") or entry.get("classification_folder") or "",
        "action": entry.get("situation") or "",
        "interaction": "",
        "movement": "",
        "camera_angle": "",
    }
    tags = list(entry.get("semantic_tags") or [])
    if entry.get("situation"):
        tags = simple_tags(str(entry.get("situation")), tags)
    if entry.get("classification_folder"):
        tags = simple_tags(str(entry.get("classification_folder")), tags)
    ranges = [item for item in (entry.get("scene_ranges") or []) if isinstance(item, dict)]
    if not ranges:
        ranges = [{}]
    candidates = []
    for item in ranges:
        start = item.get("source_in")
        end = item.get("source_out")
        candidate = {
            "semantic_valid": valid,
            "supported_line": None,
            "situation": entry.get("situation") or situation,
            "scenario_tags": tags,
            "source": entry.get("source"),
            "material_id": entry.get("source"),
            "source_duration_seconds": entry.get("full_duration"),
            "classification_folder": entry.get("classification_folder") or "",
            "visual": dict(visual),
        }
        if isinstance(start, (int, float)) and isinstance(end, (int, float)):
            candidate["source_in"] = float(start)
            candidate["source_out"] = float(end)
            candidate["in_sec"] = float(start)
            candidate["out_sec"] = float(end)
            candidate["available_duration"] = float(end) - float(start)
        else:
            duration = entry.get("full_duration")
            if isinstance(duration, (int, float)) and not isinstance(duration, bool):
                candidate["available_duration"] = float(duration)
        candidates.append(candidate)
    return candidates


def candidates_from_index(
    index: dict[str, Any],
    *,
    line: str,
    situation: str,
    folder_aliases: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    files = index.get("files") if isinstance(index, dict) else None
    if not isinstance(files, dict):
        return found
    aliases = folder_aliases if folder_aliases is not None else index.get("folder_aliases")
    mapping = aliases if isinstance(aliases, dict) else {}
    for entry in files.values():
        found.extend(expand_entry(entry, line=line, situation=situation, folder_aliases=mapping))
    return found


def attach_history(index: dict[str, Any], history: dict[str, Any] | None) -> None:
    shots = (history or {}).get("shots") if isinstance(history, dict) else None
    if not isinstance(shots, list):
        return
    files = index.setdefault("files", {})
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        source = str(shot.get("source") or "")
        if not source:
            continue
        key = relative_key(source)
        entry = files.get(key)
        if not isinstance(entry, dict):
            continue
        tags = simple_tags(str(shot.get("situation") or ""), list(shot.get("semantic_tags") or []))
        merged = simple_tags(str(entry.get("situation") or ""), list(entry.get("semantic_tags") or []) + tags)
        entry["semantic_tags"] = merged
        if not entry.get("situation") and shot.get("situation"):
            entry["situation"] = shot.get("situation")
        visual = shot.get("visual") if isinstance(shot.get("visual"), dict) else {}
        if visual.get("framing") and not entry.get("framing"):
            entry["framing"] = visual.get("framing")
            entry["camera_distance"] = visual.get("camera_distance") or visual.get("framing")


def iter_videos(material_root: Path) -> list[Path]:
    if not material_root.is_dir():
        return []
    found: list[Path] = []
    for path in sorted(material_root.rglob("*")):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            found.append(path)
    return found


def refresh_index(
    project_root: Path,
    product_model: str,
    material_root: Path,
    *,
    probe_fn: Callable[[Path], float | None] | None = None,
) -> dict[str, Any]:
    index = load_index(project_root, product_model)
    files = index.setdefault("files", {})
    refreshed = 0
    reused = 0
    probed = 0
    history = load_history(project_root, product_model)
    metadata = load_metadata(project_root, product_model)
    for video in iter_videos(material_root):
        try:
            source = video.resolve().relative_to(Path(project_root).resolve()).as_posix()
        except ValueError:
            source = str(video)
        key = relative_key(source)
        stamp = file_stamp(video)
        current = files.get(key)
        if stamp_matches(current, stamp):
            reused += 1
            continue
        sidecar = parse_sidecar_fields(video)
        duration = sidecar.get("duration_sec")
        if duration is None and isinstance(current, dict):
            duration = current.get("full_duration")
        if duration is None:
            duration = lookup_duration(metadata, source)
        if duration is None:
            if probe_fn is not None:
                duration = probe_fn(video)
                probed += 1
            else:
                duration = ensure_duration(project_root, product_model, source, video_path=video)
                probed += 1
        folder = classification_folder(material_root, video)
        ranges = sidecar.get("scene_ranges") or []
        entry = {
            "source": source,
            "relative_path": key,
            "full_duration": float(duration) if isinstance(duration, (int, float)) and not isinstance(duration, bool) else None,
            "scene_ranges": ranges,
            "semantic_tags": sidecar.get("semantic_tags") or simple_tags(folder),
            "situation": sidecar.get("situation") or "",
            "framing": sidecar.get("framing") or "",
            "camera_distance": sidecar.get("camera_distance") or sidecar.get("framing") or "",
            "classification_folder": folder,
            "mtime_ns": stamp["mtime_ns"],
            "size": stamp["size"],
            "sidecars": stamp["sidecars"],
        }
        if sidecar.get("source_in") is not None:
            entry["source_in"] = sidecar.get("source_in")
            entry["source_out"] = sidecar.get("source_out")
        entry["available_duration"] = available_from_entry(entry)
        files[key] = entry
        refreshed += 1
    attach_history(index, history)
    path = save_index(project_root, index)
    return {
        "status": "OK",
        "product_model": product_model,
        "path": path.as_posix(),
        "file_count": len(files),
        "refreshed": refreshed,
        "reused": reused,
        "probed": probed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--product-model", required=True)
    parser.add_argument("--material-root")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    root = Path(args.project_root)
    if args.refresh:
        material = Path(args.material_root) if args.material_root else root / ".runtime" / "product-video-inputs" / f"{args.product_model}_コピー"
        payload = refresh_index(root, args.product_model, material)
    else:
        index = load_index(root, args.product_model)
        payload = {
            "status": "OK",
            "product_model": args.product_model,
            "file_count": len(index.get("files") or {}),
            "path": index_path(root, args.product_model).as_posix(),
        }
    emit(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
