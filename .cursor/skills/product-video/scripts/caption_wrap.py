#!/usr/bin/env python3
"""Display-only Japanese telop wrap. Frozen characters stay unchanged."""

from __future__ import annotations

import argparse
import json
import re
from typing import Any

from paths import emit
from workflow_state import hold

MAX_LINE_CHARS = 14
PROTECTED_PHRASES = tuple(
    sorted(
        (
            "チタンシルバー",
            "サンシェード",
            "フロントガラス",
            "ルームミラー",
            "コーティング",
            "パーセント",
            "UVカット",
            "UPF",
        ),
        key=len,
        reverse=True,
    )
)
NUMBER_UNIT = re.compile(r"約?\d+(?:\.\d+)?(?:パーセント|％|%|本|秒|枚|分|度|倍|層)")
TRAIL_PUNCT = set("、。！？!?.,")
PARTICLES = ("から", "まで", "より", "だけ", "って", "など", "は", "が", "を", "に", "で", "と", "も", "の", "へ", "や", "か", "ね", "よ", "な", "ば", "て")


def unwrap_visual(wrapped: str) -> str:
    return (wrapped or "").replace("\n", "")


def visual_wrap_ok(frozen: str, wrapped: str) -> bool:
    return unwrap_visual(wrapped) == frozen


def _is_particle(atom: str) -> bool:
    return atom in PARTICLES


def _tokenize(text: str) -> list[str]:
    atoms: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        matched = None
        number = NUMBER_UNIT.match(text, index)
        if number:
            matched = number.group(0)
        else:
            rest = text[index:]
            for phrase in PROTECTED_PHRASES:
                if rest.startswith(phrase):
                    matched = phrase
                    break
            if matched is None and rest.startswith("UV"):
                matched = "UV"
        if matched is None:
            for particle in PARTICLES:
                if text.startswith(particle, index):
                    matched = particle
                    break
        if matched is None:
            matched = text[index]
        atoms.append(matched)
        index += len(matched)
    return atoms


def _fix_short_lines(lines: list[str]) -> list[str]:
    if not lines:
        return lines
    fixed = list(lines)
    changed = True
    while changed:
        changed = False
        merged: list[str] = []
        index = 0
        while index < len(fixed):
            line = fixed[index]
            nxt = fixed[index + 1] if index + 1 < len(fixed) else None
            if len(line) == 1 and merged:
                merged[-1] += line
                changed = True
                index += 1
                continue
            if nxt is not None and (len(nxt) == 1 or _is_particle(nxt)):
                merged.append(line + nxt)
                changed = True
                index += 2
                continue
            if nxt is not None and _is_particle(line):
                merged.append(line + nxt)
                changed = True
                index += 2
                continue
            merged.append(line)
            index += 1
        fixed = merged
    return fixed


def wrap_caption(frozen: str, *, max_line_chars: int = MAX_LINE_CHARS) -> dict[str, Any]:
    if not isinstance(frozen, str):
        return hold("HOLD_SCRIPT_LINE_IMMUTABLE", "caption frozen line must be a string")
    if "\n" in frozen:
        return {
            "status": "OK",
            "caption_text": frozen,
            "caption_visual_wrap": frozen,
            "lines": frozen.split("\n"),
        }
    if len(frozen) <= max_line_chars:
        return {
            "status": "OK",
            "caption_text": frozen,
            "caption_visual_wrap": frozen,
            "lines": [frozen],
        }
    atoms = _tokenize(frozen)
    lines: list[str] = []
    current = ""
    for atom in atoms:
        if not current:
            current = atom
            continue
        candidate = current + atom
        prefer_break = current[-1:] in TRAIL_PUNCT
        over = len(candidate) > max_line_chars
        particle_next = _is_particle(atom)
        if over and not particle_next and len(current) >= 2:
            lines.append(current)
            current = atom
            continue
        if prefer_break and len(candidate) >= max_line_chars - 1 and not particle_next:
            lines.append(current)
            current = atom
            continue
        current = candidate
    if current:
        lines.append(current)
    lines = _fix_short_lines(lines)
    wrapped = "\n".join(lines)
    if unwrap_visual(wrapped) != frozen:
        return hold("HOLD_SCRIPT_LINE_IMMUTABLE", "visual wrap changed frozen characters")
    if any(len(line) == 1 for line in lines):
        wrapped = frozen
        lines = [frozen]
    return {
        "status": "OK",
        "caption_text": frozen,
        "caption_visual_wrap": wrapped,
        "lines": lines,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen")
    parser.add_argument("--frozen-json")
    parser.add_argument("--max-line-chars", type=int, default=MAX_LINE_CHARS)
    args = parser.parse_args()
    frozen = args.frozen
    if args.frozen_json:
        frozen = json.loads(args.frozen_json)
    payload = wrap_caption(str(frozen or ""), max_line_chars=args.max_line_chars)
    emit(payload)
    return 0 if payload.get("status") == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
