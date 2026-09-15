#!/usr/bin/env python3
"""Persistent per-product visual scene catalog.

Objective on-screen facts only. Not a quality score. Not a production-stage
re-watch of the whole library. Unchanged size/mtime/sidecar files are reused.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from approved_shots import load_history
from constants import GENERIC_CLASSIFIER_TOKENS, PERSISTENT_VISUAL_CATALOG_RELATIVE
from material_duration import relative_key
from material_index import (
    classification_folder,
    file_stamp,
    iter_videos,
    parse_sidecar_fields,
    stamp_matches,
)
from paths import emit
from workflow_state import atomic_write

SCHEMA = "product_video_visual_catalog.v1"
TOKEN_SPLIT = re.compile(r"[、。！？!?,.・/\s]+")


def catalog_dir(project_root: Path) -> Path:
    return Path(project_root) / Path(*Path(PERSISTENT_VISUAL_CATALOG_RELATIVE).parts)


def catalog_path(project_root: Path, product_model: str) -> Path:
    return catalog_dir(project_root) / f"{product_model}.v1.json"


def empty_catalog(product_model: str) -> dict[str, Any]:
    return {"schema": SCHEMA, "product_model": product_model, "files": {}}


def load_catalog(project_root: Path, product_model: str) -> dict[str, Any]:
    path = catalog_path(project_root, product_model)
    if not path.is_file():
        return empty_catalog(product_model)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_catalog(product_model)
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return empty_catalog(product_model)
    if data.get("product_model") != product_model:
        return empty_catalog(product_model)
    if not isinstance(data.get("files"), dict):
        data["files"] = {}
    return data


def save_catalog(project_root: Path, data: dict[str, Any]) -> Path:
    path = catalog_path(project_root, str(data["product_model"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return path


def _strings(values: Any) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return found
    for item in values:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        found.append(text)
    return found


def _number(value: object, *, allow_zero: bool = False) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if allow_zero:
        return number if number >= 0 else None
    return number if number > 0 else None


def is_generic_token(text: str) -> bool:
    return (text or "").strip() in GENERIC_CLASSIFIER_TOKENS


def distinctive_needles(*values: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        parts = [text, *TOKEN_SPLIT.split(text)]
        for part in parts:
            token = str(part or "").strip()
            if len(token) < 2 or is_generic_token(token) or token in seen:
                continue
            seen.add(token)
            found.append(token)
    return found


def sidecar_describes_scene(sidecar: dict[str, Any]) -> bool:
    ranges = sidecar.get("scene_ranges") if isinstance(sidecar, dict) else None
    has_range = False
    labels: list[str] = []
    if isinstance(ranges, list):
        for item in ranges:
            if not isinstance(item, dict):
                continue
            start = _number(item.get("source_in"), allow_zero=True)
            end = _number(item.get("source_out"))
            if start is None or end is None or end <= start:
                continue
            has_range = True
            label = str(item.get("label") or "").strip()
            if label:
                labels.append(label)
    if not has_range:
        start = _number(sidecar.get("source_in"), allow_zero=True)
        end = _number(sidecar.get("source_out"))
        has_range = start is not None and end is not None and end > start
    content = str(sidecar.get("situation") or "").strip() or labels or _strings(sidecar.get("semantic_tags"))
    return bool(has_range and content)


def normalize_scene(raw: dict[str, Any], *, source: str) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    start = _number(raw.get("source_in"), allow_zero=True)
    if start is None:
        start = _number(raw.get("in_sec"), allow_zero=True)
    end = _number(raw.get("source_out"))
    if end is None:
        end = _number(raw.get("out_sec"))
    if start is None or end is None or end <= start:
        return None
    description = str(raw.get("factual_description") or raw.get("situation") or raw.get("label") or "").strip()
    objects = _strings(raw.get("objects"))
    features = _strings(raw.get("visible_features"))
    tags = _strings(raw.get("semantic_tags") or raw.get("scenario_tags"))
    for tag in tags:
        if tag not in objects and not is_generic_token(tag):
            objects.append(tag)
        if tag not in features and not is_generic_token(tag):
            features.append(tag)
    return {
        "source": str(raw.get("source") or source),
        "source_in": float(start),
        "source_out": float(end),
        "duration": float(end) - float(start),
        "objects": objects,
        "actions": _strings(raw.get("actions")),
        "product_state": str(raw.get("product_state") or "").strip(),
        "location": str(raw.get("location") or "").strip(),
        "visible_features": features,
        "framing": str(raw.get("framing") or "").strip(),
        "factual_description": description,
    }


def scenes_from_sidecar(source: str, sidecar: dict[str, Any]) -> list[dict[str, Any]]:
    scenes: list[dict[str, Any]] = []
    ranges = sidecar.get("scene_ranges") if isinstance(sidecar.get("scene_ranges"), list) else []
    if not ranges and sidecar.get("source_in") is not None and sidecar.get("source_out") is not None:
        ranges = [{"source_in": sidecar.get("source_in"), "source_out": sidecar.get("source_out")}]
    situation = str(sidecar.get("situation") or "").strip()
    tags = _strings(sidecar.get("semantic_tags"))
    framing = str(sidecar.get("framing") or sidecar.get("camera_distance") or "").strip()
    for item in ranges:
        if not isinstance(item, dict):
            continue
        scene = normalize_scene(
            {
                "source": source,
                "source_in": item.get("source_in"),
                "source_out": item.get("source_out"),
                "objects": tags,
                "visible_features": tags,
                "framing": framing,
                "factual_description": str(item.get("label") or "").strip() or situation,
                "semantic_tags": tags,
            },
            source=source,
        )
        if scene is not None:
            scenes.append(scene)
    return scenes


def scenes_from_history(history: dict[str, Any] | None, source: str) -> list[dict[str, Any]]:
    shots = (history or {}).get("shots") if isinstance(history, dict) else None
    if not isinstance(shots, list):
        return []
    scenes: list[dict[str, Any]] = []
    seen: set[tuple[float, float]] = set()
    source_key = relative_key(source)
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        shot_source = str(shot.get("source") or "")
        if relative_key(shot_source) != source_key and shot_source != source:
            continue
        scene = normalize_scene(
            {
                "source": source,
                "source_in": shot.get("in_sec"),
                "source_out": shot.get("out_sec"),
                "objects": shot.get("semantic_tags"),
                "visible_features": shot.get("semantic_tags"),
                "location": ((shot.get("visual") or {}) if isinstance(shot.get("visual"), dict) else {}).get("location"),
                "framing": ((shot.get("visual") or {}) if isinstance(shot.get("visual"), dict) else {}).get("framing"),
                "factual_description": shot.get("situation") or "",
                "semantic_tags": shot.get("semantic_tags"),
            },
            source=source,
        )
        if scene is None:
            continue
        key = (round(scene["source_in"], 3), round(scene["source_out"], 3))
        if key in seen:
            continue
        seen.add(key)
        scenes.append(scene)
    return scenes


def scene_text(scene: dict[str, Any] | None) -> str:
    if not isinstance(scene, dict):
        return ""
    parts = [
        *(_strings(scene.get("objects"))),
        *(_strings(scene.get("actions"))),
        *(_strings(scene.get("visible_features"))),
        str(scene.get("product_state") or ""),
        str(scene.get("location") or ""),
        str(scene.get("framing") or ""),
        str(scene.get("factual_description") or ""),
        str(scene.get("situation") or ""),
    ]
    return "\n".join(part for part in parts if str(part).strip())


def scene_match_score(scene: dict[str, Any] | None, line: str, intended: str) -> int:
    if not isinstance(scene, dict):
        return 0
    request = f"{line or ''}\n{intended or ''}"
    hay = scene_text(scene)
    if not hay.strip() or not request.strip():
        return 0
    score = 0
    for needle in distinctive_needles(
        *(_strings(scene.get("objects"))),
        *(_strings(scene.get("actions"))),
        *(_strings(scene.get("visible_features"))),
        str(scene.get("product_state") or ""),
        str(scene.get("factual_description") or ""),
    ):
        if needle in request:
            score += 2 if len(needle) >= 4 else 1
    for needle in distinctive_needles(line or "", intended or ""):
        if needle in hay:
            score += 1
    return score


def lookup_catalog_file(catalog: dict[str, Any] | None, source: str) -> dict[str, Any] | None:
    files = catalog.get("files") if isinstance(catalog, dict) else None
    if not isinstance(files, dict):
        return None
    key = relative_key(source)
    direct = files.get(key)
    if isinstance(direct, dict):
        return direct
    for stored, entry in files.items():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("source") or "") == source or str(stored) == key:
            return entry
        if Path(str(stored)).name == Path(key).name and Path(key).name:
            return entry
    return None


def empty_file_entry(source: str, stamp: dict[str, Any], *, folder: str = "") -> dict[str, Any]:
    return {
        "source": source,
        "mtime_ns": stamp.get("mtime_ns"),
        "size": stamp.get("size"),
        "sidecars": stamp.get("sidecars") or [],
        "discovery_folder": folder,
        "needs_observation": True,
        "scenes": [],
    }


def apply_observed_scenes(catalog: dict[str, Any], observations: list[dict[str, Any]]) -> dict[str, Any]:
    files = catalog.setdefault("files", {})
    for raw in observations:
        if not isinstance(raw, dict):
            continue
        source = str(raw.get("source") or "")
        if not source:
            continue
        scene = normalize_scene(raw, source=source)
        if scene is None:
            continue
        key = relative_key(source)
        entry = files.get(key)
        if not isinstance(entry, dict):
            entry = {
                "source": source,
                "discovery_folder": "",
                "needs_observation": False,
                "scenes": [],
            }
            files[key] = entry
        scenes = [item for item in (entry.get("scenes") or []) if isinstance(item, dict)]
        scene_key = (round(scene["source_in"], 3), round(scene["source_out"], 3))
        replaced = False
        for index, existing in enumerate(scenes):
            existing_key = (
                round(float(existing.get("source_in") or 0), 3),
                round(float(existing.get("source_out") or 0), 3),
            )
            if existing_key == scene_key:
                scenes[index] = scene
                replaced = True
                break
        if not replaced:
            scenes.append(scene)
        entry["scenes"] = scenes
        entry["needs_observation"] = False
        entry["source"] = source
    return catalog


def refresh_catalog(
    project_root: Path,
    product_model: str,
    material_root: Path,
    *,
    history: dict[str, Any] | None = None,
    observations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    catalog = load_catalog(project_root, product_model)
    files = catalog.setdefault("files", {})
    if history is None:
        history = load_history(project_root, product_model)
    refreshed = 0
    reused = 0
    observed = 0
    sidecar_ingested = 0
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
        folder = classification_folder(material_root, video)
        entry = empty_file_entry(source, stamp, folder=folder)
        if sidecar_describes_scene(sidecar):
            entry["scenes"] = scenes_from_sidecar(source, sidecar)
            entry["needs_observation"] = False
            sidecar_ingested += 1
        else:
            history_scenes = scenes_from_history(history, source)
            if history_scenes:
                entry["scenes"] = history_scenes
                entry["needs_observation"] = False
                observed += 1
            else:
                entry["scenes"] = []
                entry["needs_observation"] = True
        files[key] = entry
        refreshed += 1
    if observations:
        apply_observed_scenes(catalog, observations)
    path = save_catalog(project_root, catalog)
    return {
        "status": "OK",
        "product_model": product_model,
        "path": path.as_posix(),
        "file_count": len(files),
        "refreshed": refreshed,
        "reused": reused,
        "sidecar_ingested": sidecar_ingested,
        "history_ingested": observed,
        "needs_observation": sum(
            1 for item in files.values() if isinstance(item, dict) and item.get("needs_observation") is True
        ),
    }


def candidates_from_catalog(
    catalog: dict[str, Any] | None,
    *,
    line: str,
    situation: str,
) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    files = catalog.get("files") if isinstance(catalog, dict) else None
    if not isinstance(files, dict):
        return found
    for entry in files.values():
        if not isinstance(entry, dict):
            continue
        source = str(entry.get("source") or "")
        scenes = [item for item in (entry.get("scenes") or []) if isinstance(item, dict)]
        for scene in scenes:
            score = scene_match_score(scene, line, situation)
            candidate = {
                "semantic_valid": score > 0,
                "visual_match": score > 0,
                "visual_match_score": score,
                "search_aid": False,
                "supported_line": None,
                "situation": str(scene.get("factual_description") or ""),
                "intended_scenario": situation,
                "scenario_tags": list(scene.get("objects") or []) + list(scene.get("visible_features") or []),
                "source": scene.get("source") or source,
                "material_id": scene.get("source") or source,
                "source_in": scene.get("source_in"),
                "source_out": scene.get("source_out"),
                "in_sec": scene.get("source_in"),
                "out_sec": scene.get("source_out"),
                "available_duration": scene.get("duration"),
                "classification_folder": entry.get("discovery_folder") or "",
                "catalog_scene": scene,
                "from_visual_catalog": True,
                "visual": {
                    "framing": scene.get("framing") or "",
                    "camera_distance": scene.get("framing") or "",
                    "location": scene.get("location") or "",
                    "subject": " ".join(_strings(scene.get("objects"))),
                    "action": " ".join(_strings(scene.get("actions"))),
                    "interaction": "",
                    "movement": "",
                    "camera_angle": "",
                },
            }
            found.append(candidate)
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--product-model", required=True)
    parser.add_argument("--material-root")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--observe-json")
    args = parser.parse_args()
    root = Path(args.project_root)
    observations = json.loads(args.observe_json) if args.observe_json else None
    if args.refresh:
        material = (
            Path(args.material_root)
            if args.material_root
            else root / ".runtime" / "product-video-inputs" / f"{args.product_model}_コピー"
        )
        payload = refresh_catalog(root, args.product_model, material, observations=observations)
    else:
        catalog = load_catalog(root, args.product_model)
        if observations:
            apply_observed_scenes(catalog, observations)
            save_catalog(root, catalog)
        payload = {
            "status": "OK",
            "product_model": args.product_model,
            "file_count": len(catalog.get("files") or {}),
            "path": catalog_path(root, args.product_model).as_posix(),
            "needs_observation": sum(
                1
                for item in (catalog.get("files") or {}).values()
                if isinstance(item, dict) and item.get("needs_observation") is True
            ),
        }
    emit(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
