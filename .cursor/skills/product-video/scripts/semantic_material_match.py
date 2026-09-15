#!/usr/bin/env python3
"""One-batch Gemini semantic fallback for unresolved ASSEMBLY cuts.

Uses saved catalog / approved-shot TEXT only. Does not watch video, score
picture quality, or add aliases. Call at most once per case.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any, Callable

from paths import case_root, emit, helper_path
from workflow_state import atomic_write, hold

SCHEMA = "product_video_semantic_material_match.v1"
MATCH_FILENAME = "semantic-material-match.json"
SendFn = Callable[[str], Any]


def _number(value: object, *, allow_zero: bool = False) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            value = float(text)
        except ValueError:
            return None
    if not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if allow_zero:
        return number if number >= 0 else None
    return number if number > 0 else None


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


def make_scene_id(source: str, source_in: object, source_out: object) -> str:
    start = _number(source_in, allow_zero=True)
    end = _number(source_out)
    start_s = f"{start:.3f}" if start is not None else ""
    end_s = f"{end:.3f}" if end is not None else ""
    return f"{source}|{start_s}|{end_s}"


def scene_id_of(candidate: dict[str, Any]) -> str:
    existing = str(candidate.get("scene_id") or "").strip()
    if existing:
        return existing
    scene = candidate.get("catalog_scene") if isinstance(candidate.get("catalog_scene"), dict) else None
    source = str((scene or {}).get("source") or candidate.get("source") or candidate.get("material_id") or "")
    start = (scene or {}).get("source_in")
    if start is None:
        start = candidate.get("source_in", candidate.get("in_sec"))
    end = (scene or {}).get("source_out")
    if end is None:
        end = candidate.get("source_out", candidate.get("out_sec"))
    return make_scene_id(source, start, end)


def _has_scene_text(payload: dict[str, Any]) -> bool:
    if str(payload.get("factual_description") or "").strip():
        return True
    if str(payload.get("product_state") or "").strip():
        return True
    if str(payload.get("history_situation") or "").strip():
        return True
    return bool(
        _strings(payload.get("actions"))
        or _strings(payload.get("objects"))
        or _strings(payload.get("visible_features"))
    )


def _is_persistent_text_scene(candidate: dict[str, Any], payload: dict[str, Any] | None) -> bool:
    if payload is None:
        return False
    if payload.get("source_in") is None or payload.get("source_out") is None:
        return False
    from_catalog = candidate.get("from_visual_catalog") is True or isinstance(candidate.get("catalog_scene"), dict)
    from_history = candidate.get("from_approved_history") is True
    if not from_catalog and not from_history:
        return False
    return _has_scene_text(payload)


def _source_name(source: object) -> str:
    return Path(str(source or "")).name.lower()


def _range_key(source: object, start: object, end: object) -> tuple[str, float, float] | None:
    name = _source_name(source)
    start_n = _number(start, allow_zero=True)
    end_n = _number(end)
    if not name or start_n is None or end_n is None or end_n <= start_n:
        return None
    return (name, round(start_n, 3), round(end_n, 3))


def compact_scene_from_candidate(candidate: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None
    scene = candidate.get("catalog_scene") if isinstance(candidate.get("catalog_scene"), dict) else {}
    source = str(scene.get("source") or candidate.get("source") or candidate.get("material_id") or "")
    start = scene.get("source_in")
    if start is None:
        start = candidate.get("source_in", candidate.get("in_sec"))
    end = scene.get("source_out")
    if end is None:
        end = candidate.get("source_out", candidate.get("out_sec"))
    start_n = _number(start, allow_zero=True)
    end_n = _number(end)
    duration = _number(scene.get("duration"))
    if duration is None and start_n is not None and end_n is not None and end_n > start_n:
        duration = end_n - start_n
    if duration is None:
        duration = _number(candidate.get("available_duration"))
    history_situation = str(
        candidate.get("history_situation")
        or (candidate.get("situation") if candidate.get("from_approved_history") is True else "")
        or ""
    ).strip()
    payload = {
        "scene_id": make_scene_id(source, start_n, end_n),
        "source": source,
        "source_in": start_n,
        "source_out": end_n,
        "duration": duration,
        "factual_description": str(scene.get("factual_description") or candidate.get("situation") or "").strip(),
        "actions": _strings(scene.get("actions") or candidate.get("actions")),
        "objects": _strings(scene.get("objects") or candidate.get("scenario_tags") or candidate.get("objects")),
        "visible_features": _strings(scene.get("visible_features") or candidate.get("visible_features")),
        "product_state": str(scene.get("product_state") or "").strip(),
        "history_situation": history_situation,
    }
    if candidate.get("from_approved_history") is True:
        payload["from_approved_history"] = True
    if not _has_scene_text(payload):
        return None
    candidate["scene_id"] = payload["scene_id"]
    return payload


def merge_scene_payloads(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for payload in group:
            if not isinstance(payload, dict):
                continue
            scene_id = str(payload.get("scene_id") or "")
            if not scene_id or scene_id in seen:
                continue
            if payload.get("source_in") is None or payload.get("source_out") is None:
                continue
            if not _has_scene_text(payload):
                continue
            seen.add(scene_id)
            found.append(payload)
    return found


def collect_scene_payloads(candidates_by_cut: dict[str, list[dict[str, Any]]], cut_ids: list[str]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for cut_id in cut_ids:
        for candidate in candidates_by_cut.get(cut_id) or []:
            payload = compact_scene_from_candidate(candidate)
            if not _is_persistent_text_scene(candidate, payload) or payload is None:
                continue
            scene_id = payload["scene_id"]
            if scene_id in seen:
                continue
            seen.add(scene_id)
            found.append(payload)
    return found


def catalog_history_payloads(catalog: dict[str, Any] | None, history: dict[str, Any] | None) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    files = catalog.get("files") if isinstance(catalog, dict) else None
    if isinstance(files, dict):
        for entry in files.values():
            if not isinstance(entry, dict):
                continue
            for scene in entry.get("scenes") or []:
                if not isinstance(scene, dict):
                    continue
                payload = compact_scene_from_candidate(
                    {
                        "from_visual_catalog": True,
                        "catalog_scene": scene,
                        "source": scene.get("source") or entry.get("source"),
                        "source_in": scene.get("source_in"),
                        "source_out": scene.get("source_out"),
                    }
                )
                if payload is not None:
                    found.append(payload)
    shots = history.get("shots") if isinstance(history, dict) else None
    if isinstance(shots, list):
        for shot in shots:
            if not isinstance(shot, dict):
                continue
            payload = compact_scene_from_candidate(
                {
                    "from_approved_history": True,
                    "source": shot.get("source"),
                    "source_in": shot.get("in_sec", shot.get("source_in")),
                    "source_out": shot.get("out_sec", shot.get("source_out")),
                    "history_situation": shot.get("situation") or shot.get("history_situation"),
                    "situation": shot.get("situation") or shot.get("history_situation"),
                    "objects": shot.get("semantic_tags") or shot.get("objects"),
                    "visible_features": shot.get("semantic_tags") or shot.get("visible_features"),
                    "actions": shot.get("actions"),
                }
            )
            if payload is not None:
                found.append(payload)
    return merge_scene_payloads(found)


def build_semantic_prompt(cuts: list[dict[str, Any]], scenes: list[dict[str, Any]]) -> str:
    cut_rows = []
    for cut in cuts:
        cut_rows.append(
            {
                "cut_id": cut.get("cut_id"),
                "line": cut.get("line"),
                "situation": cut.get("situation") or cut.get("intended_scenario"),
                "target_duration_seconds": cut.get("target_duration_seconds"),
            }
        )
    scene_rows = []
    for scene in scenes:
        scene_rows.append(
            {
                "scene_id": scene.get("scene_id"),
                "source": scene.get("source"),
                "source_in": scene.get("source_in"),
                "source_out": scene.get("source_out"),
                "duration": scene.get("duration"),
                "factual_description": scene.get("factual_description"),
                "actions": scene.get("actions") or [],
                "objects": scene.get("objects") or [],
                "visible_features": scene.get("visible_features") or [],
                "product_state": scene.get("product_state") or "",
                "history_situation": scene.get("history_situation") or "",
            }
        )
    return (
        "あなたは商品動画の素材選定アシスタントです。\n"
        "文章中に同じ単語があるかではなく、そのsceneのTEXT metadataが表す映像が、"
        "そのセリフとsituationを視覚的に表現できるかだけを判定してください。\n"
        "metadataに書かれていない物体・動作・機能・効果を推測して追加しないでください。\n"
        "動画ファイル・画像・画質点数は使いません。以下のJSONだけを使ってください。\n"
        "duration が target_duration_seconds 未満のsceneは選ばないでください。\n"
        "表現できないcutは出力しないでください。各cutは最大1 sceneです。\n"
        "完成したJSONオブジェクトだけを出力してください。前置きやツール利用は不要です。\n"
        "形式:\n"
        '{"c1":{"scene_id":"...","source":"...","source_in":0,"source_out":1,"reason":"..."}}\n'
        f"cuts:\n{json.dumps(cut_rows, ensure_ascii=False, indent=2)}\n"
        f"scenes:\n{json.dumps(scene_rows, ensure_ascii=False, indent=2)}\n"
    )


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = (text or "").strip()
    if not stripped:
        return None
    found: list[dict[str, Any]] = []
    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            found.append(data)
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for index, char in enumerate(stripped):
        if char != "{":
            continue
        try:
            data, _end = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data not in found:
            found.append(data)
    if not found:
        return None

    def score(data: dict[str, Any]) -> int:
        nested = data.get("matches")
        if isinstance(nested, dict):
            return 100 + len(nested)
        cuts = [
            key
            for key in data
            if str(key).startswith("c") and str(key)[1:].isdigit() and isinstance(data.get(key), dict)
        ]
        if cuts:
            return 50 + len(cuts)
        return len(data)

    return max(found, key=score)


def _scene_indexes(scenes: list[dict[str, Any]] | None) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, float, float], dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_range: dict[tuple[str, float, float], dict[str, Any]] = {}
    for scene in scenes or []:
        if not isinstance(scene, dict):
            continue
        scene_id = str(scene.get("scene_id") or "").strip()
        if scene_id:
            by_id[scene_id] = scene
        key = _range_key(scene.get("source"), scene.get("source_in"), scene.get("source_out"))
        if key is not None:
            by_range[key] = scene
    return by_id, by_range


def resolve_semantic_match(
    value: dict[str, Any],
    *,
    allowed_scene_ids: set[str] | None = None,
    scenes: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    by_id, by_range = _scene_indexes(scenes)
    scene_id = str(value.get("scene_id") or "").strip()
    source = str(value.get("source") or "").strip()
    start = _number(value.get("source_in"), allow_zero=True)
    end = _number(value.get("source_out"))
    scene = by_id.get(scene_id) if scene_id else None
    if scene is None:
        key = _range_key(source, start, end)
        if key is not None:
            scene = by_range.get(key)
    if scene is None and scene_id:
        for stored_id, stored in by_id.items():
            if stored_id.endswith(scene_id) or Path(scene_id).name == Path(stored_id).name:
                scene = stored
                break
        if scene is None:
            name = _source_name(scene_id.split("|", 1)[0] or source)
            for stored in by_id.values():
                if _source_name(stored.get("source")) != name:
                    continue
                key = _range_key(stored.get("source"), stored.get("source_in"), stored.get("source_out"))
                got = _range_key(stored.get("source"), start, end)
                if key is not None and key == got:
                    scene = stored
                    break
    if scene is not None:
        scene_id = str(scene.get("scene_id") or scene_id)
        source = str(scene.get("source") or source)
        start = _number(scene.get("source_in"), allow_zero=True)
        end = _number(scene.get("source_out"))
    elif not scene_id:
        scene_id = make_scene_id(source, start, end)
    allowed = allowed_scene_ids
    if allowed is None and scenes:
        allowed = {str(item.get("scene_id") or "") for item in scenes if item.get("scene_id")}
    if allowed is not None and scene_id not in allowed:
        return None
    if start is None or end is None or end <= start:
        return None
    return {
        "scene_id": scene_id,
        "source": source,
        "source_in": start,
        "source_out": end,
        "reason": str(value.get("reason") or "").strip(),
        "duration": (end - start),
    }


def parse_semantic_matches(
    text: str,
    *,
    allowed_scene_ids: set[str] | None = None,
    scenes: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    parsed = _extract_json_object(text)
    if not isinstance(parsed, dict):
        return {}
    raw = parsed.get("matches") if isinstance(parsed.get("matches"), dict) else parsed
    matches: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        cut_id = str(key).strip()
        if not cut_id or cut_id in {"schema", "gemini_calls", "matches", "status", "hold"}:
            continue
        if not isinstance(value, dict):
            continue
        resolved = resolve_semantic_match(value, allowed_scene_ids=allowed_scene_ids, scenes=scenes)
        if resolved is None:
            continue
        matches[cut_id] = resolved
    return matches


def persist_matches(project_root: Path, case_id: str, matches: dict[str, dict[str, Any]], *, gemini_calls: int) -> Path:
    dest = case_root(project_root, case_id) / MATCH_FILENAME
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"schema": SCHEMA, "gemini_calls": int(gemini_calls)}
    for cut_id, match in matches.items():
        payload[cut_id] = {
            "scene_id": match.get("scene_id"),
            "source": match.get("source"),
            "source_in": match.get("source_in"),
            "source_out": match.get("source_out"),
            "reason": match.get("reason") or "",
        }
    atomic_write(dest, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return dest


def load_matches(project_root: Path, case_id: str) -> dict[str, dict[str, Any]]:
    path = case_root(project_root, case_id) / MATCH_FILENAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return parse_semantic_matches(json.dumps(data, ensure_ascii=False))


def candidate_from_match(match: dict[str, Any], scene: dict[str, Any] | None = None) -> dict[str, Any]:
    source = str((scene or {}).get("source") or match.get("source") or "")
    start = _number((scene or {}).get("source_in"), allow_zero=True)
    if start is None:
        start = _number(match.get("source_in"), allow_zero=True)
    end = _number((scene or {}).get("source_out"))
    if end is None:
        end = _number(match.get("source_out"))
    duration = None
    if start is not None and end is not None and end > start:
        duration = end - start
    catalog_scene = None
    if scene:
        catalog_scene = {
            "source": source,
            "source_in": start,
            "source_out": end,
            "duration": duration,
            "factual_description": scene.get("factual_description") or "",
            "actions": list(scene.get("actions") or []),
            "objects": list(scene.get("objects") or []),
            "visible_features": list(scene.get("visible_features") or []),
            "product_state": scene.get("product_state") or "",
        }
    candidate = {
        "from_semantic_fallback": True,
        "from_visual_catalog": catalog_scene is not None,
        "visual_match": True,
        "semantic_valid": True,
        "visual_match_score": 1,
        "search_aid": False,
        "supported_line": None,
        "source": source,
        "material_id": source,
        "source_in": start,
        "source_out": end,
        "in_sec": start,
        "out_sec": end,
        "available_duration": duration,
        "scene_id": str(match.get("scene_id") or make_scene_id(source, start, end)),
        "semantic_fallback_reason": str(match.get("reason") or ""),
        "situation": str((scene or {}).get("factual_description") or (scene or {}).get("history_situation") or ""),
        "history_situation": str((scene or {}).get("history_situation") or ""),
        "catalog_scene": catalog_scene,
        "visual": {
            "framing": "",
            "camera_distance": "",
            "location": "",
            "subject": " ".join(_strings((scene or {}).get("objects"))),
            "action": " ".join(_strings((scene or {}).get("actions"))),
            "interaction": "",
            "movement": "",
            "camera_angle": "",
        },
    }
    if (scene or {}).get("from_approved_history") is True or (scene or {}).get("history_situation"):
        candidate["from_approved_history"] = True
    return candidate


def _same_scene(candidate: dict[str, Any], match: dict[str, Any]) -> bool:
    scene_id = str(match.get("scene_id") or "")
    if scene_id and scene_id_of(candidate) == scene_id:
        return True
    key = _range_key(match.get("source"), match.get("source_in"), match.get("source_out"))
    cand_key = _range_key(
        candidate.get("source") or candidate.get("material_id"),
        candidate.get("source_in", candidate.get("in_sec")),
        candidate.get("source_out", candidate.get("out_sec")),
    )
    return key is not None and key == cand_key


def apply_semantic_matches(
    candidates_by_cut: dict[str, list[dict[str, Any]]],
    matches: dict[str, dict[str, Any]],
    *,
    scenes: list[dict[str, Any]] | None = None,
    targets: dict[str, float] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    by_id, _by_range = _scene_indexes(scenes)
    for cut_id, match in matches.items():
        duration = _number(match.get("duration"))
        if duration is None:
            start = _number(match.get("source_in"), allow_zero=True)
            end = _number(match.get("source_out"))
            if start is not None and end is not None and end > start:
                duration = end - start
        target = (targets or {}).get(cut_id)
        if target is not None and (duration is None or duration + 1e-9 < float(target)):
            continue
        marked = False
        pool = candidates_by_cut.setdefault(cut_id, [])
        for candidate in pool:
            if not _same_scene(candidate, match):
                continue
            candidate["from_semantic_fallback"] = True
            candidate["visual_match"] = True
            candidate["semantic_valid"] = True
            candidate["visual_match_score"] = max(int(candidate.get("visual_match_score") or 0), 1)
            candidate["semantic_fallback_reason"] = str(match.get("reason") or "")
            candidate["scene_id"] = str(match.get("scene_id") or scene_id_of(candidate))
            marked = True
        if not marked:
            scene = by_id.get(str(match.get("scene_id") or ""))
            pool.append(candidate_from_match(match, scene))
    return candidates_by_cut


def _response_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    if not isinstance(result, dict):
        return ""
    for key in ("last_text", "response", "text", "output"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def live_send_prompt(project_root: Path, prompt: str) -> dict[str, Any]:
    path = helper_path(project_root, "send_gemini_cli_prompt")
    spec = importlib.util.spec_from_file_location("send_gemini_cli_prompt", path)
    if spec is None or spec.loader is None:
        return hold("HOLD_GEMINI_CLI_NOT_VERIFIED", "send_gemini_cli_prompt helper is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.send_prompt(prompt)


def run_semantic_fallback(
    cuts: list[dict[str, Any]],
    scenes: list[dict[str, Any]],
    *,
    send_fn: SendFn | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    if not cuts or not scenes:
        return {"status": "OK", "matches": {}, "gemini_calls": 0, "skipped": True}
    targets = [_number(cut.get("target_duration_seconds")) for cut in cuts]
    min_target = min((item for item in targets if item is not None), default=None)
    if min_target is not None:
        scenes = [
            scene
            for scene in scenes
            if (_number(scene.get("duration")) or 0) + 1e-9 >= min_target
        ]
    if not scenes:
        return {"status": "OK", "matches": {}, "gemini_calls": 0, "skipped": True}
    prompt = build_semantic_prompt(cuts, scenes)
    if send_fn is None:
        if project_root is None:
            return hold("HOLD_GEMINI_CLI_NOT_VERIFIED", "semantic fallback needs Gemini transport")
        result = live_send_prompt(project_root, prompt)
    else:
        result = send_fn(prompt)
    if isinstance(result, dict) and result.get("status") == "HOLD":
        return result
    allowed = {str(scene.get("scene_id") or "") for scene in scenes if scene.get("scene_id")}
    matches = parse_semantic_matches(_response_text(result), allowed_scene_ids=allowed, scenes=scenes)
    return {"status": "OK", "matches": matches, "gemini_calls": 1, "prompt": prompt}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--print", action="store_true")
    args = parser.parse_args()
    matches = load_matches(args.project_root, args.case_id)
    emit({"status": "OK", "matches": matches, "count": len(matches)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
