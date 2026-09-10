#!/usr/bin/env python3
"""Resolve the text CapCut will submit for TTS. Never use a substitute string.

Priority:
1. CapCut editor internal model / effective editor value
2. TTS submission application state
3. contenteditable DOM nodes, only when user-authored text nodes are
   distinguished from CapCut-owned structural sentinel nodes

Never trim, strip, Unicode-normalize, or replace U+200B. Never treat
document HTML, preview, OCR, or visible text as proof. U+200B may be
excluded only as an independent CapCut structural sentinel node.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

HOLD_FIELD = "HOLD_TTS_INPUT_FIELD_UNVERIFIED"
FORBIDDEN_PROOF_SOURCES = frozenset(
    {
        "document_html",
        "document_html_line_text",
        "preview_text",
        "ocr_text",
        "visible_text",
    }
)
SENTINEL_ZWSP = "\u200b"


def _hold(reason: str, **extra: Any) -> dict[str, Any]:
    payload = {
        "status": "HOLD",
        "hold": HOLD_FIELD,
        "generate": False,
        "exact_match": False,
        "effective_tts_text": None,
        "reason": reason,
    }
    payload.update(extra)
    return payload


def _ok(text: str, source: str, **extra: Any) -> dict[str, Any]:
    payload = {
        "status": "OK",
        "hold": None,
        "effective_tts_text": text,
        "readback_source": source,
        "reason": None,
    }
    payload.update(extra)
    return payload


def _is_string(value: object) -> bool:
    return isinstance(value, str)


def _from_dom_nodes(nodes: object) -> dict[str, Any]:
    if not isinstance(nodes, list) or not nodes:
        return _hold("contenteditable DOM nodes are unavailable")
    user_parts: list[str] = []
    sentinel_count = 0
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            return _hold("DOM node must be an object", node_index=index)
        kind = node.get("kind")
        text = node.get("text")
        if not _is_string(text):
            return _hold("DOM node text must be a string", node_index=index)
        if kind == "unknown":
            return _hold(
                "U+200B or node kind cannot be classified as user text vs CapCut sentinel",
                node_index=index,
            )
        if kind == "structural_sentinel":
            if node.get("independent") is not True:
                return _hold(
                    "CapCut sentinel must be an independent node, not characters inside user text",
                    node_index=index,
                )
            evidence = node.get("evidence")
            if not isinstance(evidence, str) or not evidence.strip():
                return _hold("CapCut sentinel requires DOM or application-state evidence", node_index=index)
            if text != SENTINEL_ZWSP:
                return _hold(
                    "structural sentinel text is not a proven CapCut empty marker",
                    node_index=index,
                )
            sentinel_count += 1
            continue
        if kind == "user_authored":
            if SENTINEL_ZWSP in text:
                return _hold(
                    "U+200B inside a user-authored node cannot be classified as a sentinel",
                    node_index=index,
                )
            user_parts.append(text)
            continue
        return _hold("DOM node kind must be user_authored, structural_sentinel, or unknown", node_index=index)
    return _ok(
        "".join(user_parts),
        "user_authored_dom_nodes",
        sentinel_nodes=sentinel_count,
        user_authored_nodes=len(user_parts),
    )


def resolve_effective_tts_text(observation: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(observation, dict):
        return _hold("observation must be an object")

    proof_source = observation.get("proof_source")
    if proof_source in FORBIDDEN_PROOF_SOURCES:
        return _hold(
            "document HTML, preview, OCR, or visible text is not TTS input proof",
            rejected_proof_source=proof_source,
        )

    if "editor_model_text" in observation:
        value = observation.get("editor_model_text")
        if not _is_string(value):
            return _hold("editor internal model text is unavailable")
        return _ok(value, "editor_model")

    if "submission_text" in observation:
        value = observation.get("submission_text")
        if not _is_string(value):
            return _hold("TTS submission application state is unavailable")
        return _ok(value, "submission_state")

    if "dom_nodes" in observation:
        return _from_dom_nodes(observation.get("dom_nodes"))

    inner = observation.get("inner_text")
    if inner is None:
        return _hold("actual TTS input value unavailable")
    if not _is_string(inner):
        return _hold("contenteditable innerText must be a string")
    if SENTINEL_ZWSP in inner:
        return _hold(
            "U+200B cannot be classified as user text vs CapCut sentinel",
            ignored_document_html=bool(
                observation.get("document_html_line_text") is not None or observation.get("document_html") is not None
            ),
        )
    return _ok(inner, "actual_textarea_value")


def compare_effective_to_frozen(frozen_line: str, observation: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(frozen_line, str) or frozen_line == "":
        return _hold("frozen_line must be the approved non-empty line")
    resolved = resolve_effective_tts_text(observation)
    if resolved.get("status") != "OK":
        return resolved
    effective = resolved.get("effective_tts_text")
    if effective != frozen_line:
        return _hold(
            "effective_tts_text is not exactly the frozen line",
            effective_tts_text=effective,
            readback_source=resolved.get("readback_source"),
            frozen_line=frozen_line,
        )
    resolved["exact_match"] = True
    resolved["generate"] = False
    resolved["frozen_line"] = frozen_line
    return resolved


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen-json", help="JSON string of the frozen line")
    parser.add_argument("--observation-json", required=True, help="JSON object of TTS text proof fields")
    args = parser.parse_args()
    observation = json.loads(args.observation_json)
    if args.frozen_json is None:
        payload = resolve_effective_tts_text(observation)
    else:
        payload = compare_effective_to_frozen(json.loads(args.frozen_json), observation)
    emit(payload)
    return 0 if payload.get("status") == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
