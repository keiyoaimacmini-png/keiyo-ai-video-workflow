#!/usr/bin/env python3
"""Persistent per-file material durations. Measure a file at most once.

Do not probe every video in the library. Do not re-measure a file that already
has duration in this store, a sidecar md, or a previous inventory seed.
ChatCut placement is not a duration source.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from constants import PERSISTENT_MATERIAL_METADATA_RELATIVE
from paths import emit
from workflow_state import atomic_write

SCHEMA = "product_video_material_metadata.v1"
DURATION_KEYS = ("duration_sec", "source_duration_seconds", "file_duration_seconds", "duration")
SIDECAR_DURATION = re.compile(
    r"^(?:duration(?:_sec)?|source_duration|尺)\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*$",
    re.IGNORECASE,
)
SIDECAR_IN = re.compile(r"^(?:source_in|in_sec)\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*$", re.IGNORECASE)
SIDECAR_OUT = re.compile(r"^(?:source_out|out_sec)\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*$", re.IGNORECASE)


def _number(value: object, *, allow_zero: bool = False) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if allow_zero:
        return number if number >= 0 else None
    return number if number > 0 else None


def metadata_dir(project_root: Path) -> Path:
    return Path(project_root) / Path(*Path(PERSISTENT_MATERIAL_METADATA_RELATIVE).parts)


def metadata_path(project_root: Path, product_model: str) -> Path:
    return metadata_dir(project_root) / f"{product_model}.v1.json"


def empty_metadata(product_model: str) -> dict[str, Any]:
    return {"schema": SCHEMA, "product_model": product_model, "files": {}}


def load_metadata(project_root: Path, product_model: str) -> dict[str, Any]:
    path = metadata_path(project_root, product_model)
    if not path.is_file():
        return empty_metadata(product_model)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_metadata(product_model)
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return empty_metadata(product_model)
    if data.get("product_model") != product_model:
        return empty_metadata(product_model)
    files = data.get("files")
    if not isinstance(files, dict):
        data["files"] = {}
    return data


def save_metadata(project_root: Path, data: dict[str, Any]) -> Path:
    product_model = str(data["product_model"])
    path = metadata_path(project_root, product_model)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return path


def relative_key(source: str) -> str:
    posix = source.replace("\\", "/").lstrip("./")
    marker = "/product-video-inputs/"
    if marker in posix:
        rest = posix.split(marker, 1)[1]
        parts = rest.split("/", 1)
        return parts[1] if len(parts) == 2 else rest
    return posix


def lookup_entry(metadata: dict[str, Any], source: str) -> dict[str, Any] | None:
    files = metadata.get("files") if isinstance(metadata, dict) else None
    if not isinstance(files, dict):
        return None
    key = relative_key(source)
    direct = files.get(key)
    if isinstance(direct, dict):
        return direct
    name = Path(key).name.lower()
    for stored_key, entry in files.items():
        if not isinstance(entry, dict):
            continue
        if str(stored_key).replace("\\", "/").endswith("/" + key) or str(stored_key) == key:
            return entry
        if Path(str(stored_key)).name.lower() == name and name:
            return entry
    return None


def lookup_duration(metadata: dict[str, Any], source: str) -> float | None:
    entry = lookup_entry(metadata, source)
    if not entry:
        return None
    for key in DURATION_KEYS:
        duration = _number(entry.get(key))
        if duration is not None:
            return duration
    return None


def _range_pair(item: dict[str, Any]) -> tuple[float, float] | None:
    start = _number(item.get("source_in"), allow_zero=True)
    if start is None:
        start = _number(item.get("in_sec"), allow_zero=True)
    end = _number(item.get("source_out"))
    if end is None:
        end = _number(item.get("out_sec"))
    if start is None or end is None or end <= start:
        return None
    return (start, end)


def usable_ranges(metadata: dict[str, Any], source: str) -> list[tuple[float, float]]:
    entry = lookup_entry(metadata, source)
    if not entry:
        return []
    found: list[tuple[float, float]] = []
    for item in entry.get("usable_ranges") or entry.get("scene_ranges") or []:
        if not isinstance(item, dict):
            continue
        pair = _range_pair(item)
        if pair:
            found.append(pair)
    pair = _range_pair(entry)
    if pair:
        found.append(pair)
    return found


def parse_sidecar_md(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return payload
    in_sec = None
    out_sec = None
    for raw in text.splitlines():
        line = raw.strip()
        match = SIDECAR_DURATION.match(line)
        if match:
            payload["duration_sec"] = float(match.group(1))
            continue
        match = SIDECAR_IN.match(line)
        if match:
            in_sec = float(match.group(1))
            continue
        match = SIDECAR_OUT.match(line)
        if match:
            out_sec = float(match.group(1))
    if in_sec is not None and out_sec is not None and out_sec > in_sec:
        payload["source_in"] = in_sec
        payload["source_out"] = out_sec
        payload["usable_ranges"] = [{"source_in": in_sec, "source_out": out_sec}]
    return payload


def sidecar_paths(video: Path) -> list[Path]:
    return [
        video.with_suffix(".md"),
        video.with_suffix(video.suffix + ".md"),
        video.parent / f"{video.stem}.md",
    ]


def ingest_inventory(metadata: dict[str, Any], inventory: dict[str, Any]) -> int:
    added = 0
    files = metadata.setdefault("files", {})
    for asset in inventory.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        rel = str(asset.get("relative_path") or "").replace("\\", "/")
        duration = _number(asset.get("duration_sec"))
        if not rel or duration is None:
            continue
        current = files.get(rel)
        if isinstance(current, dict) and _number(current.get("duration_sec")) is not None:
            continue
        files[rel] = {
            "duration_sec": duration,
            "source": "inventory",
            "sha256": asset.get("sha256"),
        }
        added += 1
    return added


def seed_from_inventories(project_root: Path, product_model: str) -> dict[str, Any]:
    metadata = load_metadata(project_root, product_model)
    outputs = Path(project_root) / "outputs"
    if not outputs.is_dir():
        return metadata
    for inventory_path in sorted(outputs.glob("*/material-inventory.v1.json")):
        try:
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if inventory.get("product_model") not in {None, product_model}:
            continue
        ingest_inventory(metadata, inventory)
    if metadata.get("files"):
        save_metadata(project_root, metadata)
    return metadata


def probe_duration(video: Path) -> float | None:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        duration = float((result.stdout or "").strip())
    except ValueError:
        return None
    return duration if duration > 0 else None


def remember_duration(
    project_root: Path,
    product_model: str,
    source: str,
    duration: float,
    *,
    origin: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = load_metadata(project_root, product_model)
    key = relative_key(source)
    entry = dict(lookup_entry(metadata, source) or {})
    entry["duration_sec"] = float(duration)
    entry["source"] = origin
    if extra:
        entry.update(extra)
    metadata.setdefault("files", {})[key] = entry
    save_metadata(project_root, metadata)
    return entry


def ensure_duration(
    project_root: Path,
    product_model: str,
    source: str,
    *,
    video_path: Path | None = None,
) -> float | None:
    metadata = load_metadata(project_root, product_model)
    duration = lookup_duration(metadata, source)
    if duration is not None:
        return duration
    video = Path(video_path) if video_path is not None else Path(project_root) / source
    for sidecar in sidecar_paths(video):
        if not sidecar.is_file():
            continue
        parsed = parse_sidecar_md(sidecar)
        parsed_duration = _number(parsed.get("duration_sec"))
        if parsed_duration is None:
            continue
        remember_duration(
            project_root,
            product_model,
            source,
            parsed_duration,
            origin="sidecar_md",
            extra={key: parsed[key] for key in ("source_in", "source_out", "usable_ranges") if key in parsed},
        )
        return parsed_duration
    seeded = seed_from_inventories(project_root, product_model)
    duration = lookup_duration(seeded, source)
    if duration is not None:
        return duration
    if not video.is_file():
        return None
    probed = probe_duration(video)
    if probed is None:
        return None
    remember_duration(project_root, product_model, source, probed, origin="ffprobe")
    return probed


def duration_map(metadata: dict[str, Any]) -> dict[str, float]:
    mapping: dict[str, float] = {}
    for key, entry in (metadata.get("files") or {}).items():
        if not isinstance(entry, dict):
            continue
        duration = _number(entry.get("duration_sec"))
        if duration is None:
            continue
        mapping[str(key)] = duration
        mapping[Path(str(key)).name] = duration
    return mapping


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--product-model", required=True)
    parser.add_argument("--source")
    parser.add_argument("--seed", action="store_true")
    args = parser.parse_args()
    root = Path(args.project_root)
    if args.seed or not args.source:
        metadata = seed_from_inventories(root, args.product_model)
        emit(
            {
                "status": "OK",
                "product_model": args.product_model,
                "file_count": len(metadata.get("files") or {}),
                "path": metadata_path(root, args.product_model).as_posix(),
            }
        )
        return 0
    duration = ensure_duration(root, args.product_model, args.source)
    emit({"status": "OK" if duration is not None else "HOLD", "source": args.source, "duration_sec": duration})
    return 0 if duration is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
