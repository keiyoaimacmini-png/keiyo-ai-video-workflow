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
MIN_KEEP_CHARS = 3
PROTECTED_PHRASES = tuple(
    sorted(
        (
            "チタンシルバー",
            "フロントガラス",
            "ルームミラー",
            "サンシェード",
            "コーティング",
            "へたりにくい",
            "パーセント",
            "V字カット",
            "UVカット",
            "UPF40以上",
            "一発装着",
            "多くない",
            "ブロック",
            "一発",
            "UPF",
        ),
        key=len,
        reverse=True,
    )
)
UV_MEASURE = re.compile(r"UV約?\d+(?:\.\d+)?(?:パーセント|％|%)")
UPF_UNIT = re.compile(r"UPF\s?\d+\s*以上")
NUMBER_UNIT = re.compile(r"約?\d+(?:\.\d+)?(?:パーセント|％|%|本骨|本|秒|枚|分|度|倍|層)")
KATAKANA_RUN = re.compile(r"[\u30A0-\u30FFー]+")
TRAIL_PUNCT = set("、。！？!?.,…")
PARTICLES = (
    "から",
    "まで",
    "より",
    "だけ",
    "って",
    "など",
    "なら",
    "は",
    "が",
    "を",
    "に",
    "で",
    "と",
    "も",
    "の",
    "へ",
    "や",
    "か",
    "ね",
    "よ",
    "な",
    "ば",
    "て",
)
CLAUSE_ENDINGS = (
    "けれど",
    "けど",
    "ので",
    "のに",
    "から",
    "まで",
    "なら",
    "して",
    "れて",
    "って",
    "たら",
    "では",
    "でも",
    "で",
    "て",
)
CONNECTORS = set("&＆")
MEASURE_ENDINGS = ("パーセント", "％", "%", "本骨")


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
        rest = text[index:]
        uv = UV_MEASURE.match(rest)
        upf = UPF_UNIT.match(rest)
        number = NUMBER_UNIT.match(rest)
        kana = KATAKANA_RUN.match(rest)
        if uv:
            matched = uv.group(0)
        elif upf:
            matched = upf.group(0)
        elif number:
            matched = number.group(0)
        else:
            for phrase in PROTECTED_PHRASES:
                if rest.startswith(phrase):
                    matched = phrase
                    break
            if matched is None and rest.startswith("UV"):
                matched = "UV"
            if matched is None and kana:
                matched = kana.group(0)
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


def _starts_with_protected(text: str) -> bool:
    if UV_MEASURE.match(text) or UPF_UNIT.match(text) or NUMBER_UNIT.match(text):
        return True
    return any(text.startswith(phrase) for phrase in PROTECTED_PHRASES) or text.startswith("UV")


def _ends_with_measure(text: str) -> bool:
    return any(text.endswith(end) for end in MEASURE_ENDINGS) or bool(UV_MEASURE.search(text[-12:]))


def _reattach_leading_punct(lines: list[str]) -> list[str]:
    if not lines:
        return lines
    fixed: list[str] = [lines[0]]
    for line in lines[1:]:
        while line and line[0] in TRAIL_PUNCT and fixed:
            fixed[-1] += line[0]
            line = line[1:]
        if line:
            fixed.append(line)
    return [line for line in fixed if line]


def _fix_short_lines(lines: list[str]) -> list[str]:
    if not lines:
        return lines
    fixed = _reattach_leading_punct(lines)
    changed = True
    while changed:
        changed = False
        merged: list[str] = []
        index = 0
        while index < len(fixed):
            line = fixed[index]
            nxt = fixed[index + 1] if index + 1 < len(fixed) else None
            if len(line) <= 2 and merged:
                merged[-1] += line
                changed = True
                index += 1
                continue
            if nxt is not None and (len(nxt) <= 2 or _is_particle(nxt)):
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
    return _reattach_leading_punct(fixed)


def _valid_break(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if len(left) < MIN_KEEP_CHARS or len(right) <= 2:
        return False
    if right[0] in TRAIL_PUNCT:
        return False
    if _is_particle(right) or _is_particle(left):
        return False
    return True


def _score_break(left: str, right: str, max_line_chars: int) -> int:
    score = 0
    if left[-1:] in TRAIL_PUNCT:
        score += 150
    if _ends_with_measure(left):
        score += 120
    if any(left.endswith(end) for end in CLAUSE_ENDINGS):
        score += 90
    if _starts_with_protected(right):
        score += 80
    if any(left.endswith(particle) for particle in PARTICLES):
        score += 50
    score += max(0, 40 - abs(len(left) - max_line_chars) * 5)
    if len(left) > max_line_chars:
        score -= 40 * (len(left) - max_line_chars)
    if right[:1] in CONNECTORS:
        score -= 50
    return score


def _choose_break(atoms: list[str], max_line_chars: int, *, allow_fit: bool = False) -> int | None:
    prefixes: list[str] = []
    current = ""
    for atom in atoms:
        current += atom
        prefixes.append(current)
    remaining = prefixes[-1] if prefixes else ""
    fits = len(remaining) <= max_line_chars
    if fits and not allow_fit:
        return None
    window_lo = max(MIN_KEEP_CHARS, max_line_chars - 6)
    window_hi = max_line_chars + 1
    candidates: list[int] = []
    for index, left in enumerate(prefixes[:-1], start=1):
        right = remaining[len(left) :]
        if not _valid_break(left, right):
            continue
        linguistic = (
            left[-1:] in TRAIL_PUNCT
            or _ends_with_measure(left)
            or any(left.endswith(end) for end in CLAUSE_ENDINGS)
            or _starts_with_protected(right)
            or any(left.endswith(particle) for particle in PARTICLES)
        )
        strong = (
            left[-1:] in TRAIL_PUNCT
            or _ends_with_measure(left)
            or _starts_with_protected(right)
        )
        in_window = window_lo <= len(left) <= window_hi
        if fits and allow_fit:
            if strong:
                candidates.append(index)
            continue
        if linguistic or in_window:
            candidates.append(index)
    if not candidates and not (fits and allow_fit):
        for index, left in enumerate(prefixes[:-1], start=1):
            right = remaining[len(left) :]
            if _valid_break(left, right) and len(left) <= max_line_chars:
                candidates.append(index)
    if not candidates:
        return None
    best = max(
        candidates,
        key=lambda index: (
            _score_break(prefixes[index - 1], remaining[len(prefixes[index - 1]) :], max_line_chars),
            -abs(len(prefixes[index - 1]) - max_line_chars),
        ),
    )
    left = prefixes[best - 1]
    right = remaining[len(left) :]
    if fits and allow_fit and _score_break(left, right, max_line_chars) < 80:
        return None
    return best


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
    atoms = _tokenize(frozen)
    lines: list[str] = []
    pending = list(atoms)
    first = True
    while pending:
        joined = "".join(pending)
        fits = len(joined) <= max_line_chars
        if fits and not first:
            lines.append(joined)
            break
        split_at = _choose_break(pending, max_line_chars, allow_fit=fits and first)
        if split_at is None:
            lines.append(joined)
            break
        lines.append("".join(pending[:split_at]))
        pending = pending[split_at:]
        first = False
    lines = _fix_short_lines(lines)
    wrapped = "\n".join(lines)
    if unwrap_visual(wrapped) != frozen:
        return hold("HOLD_SCRIPT_LINE_IMMUTABLE", "visual wrap changed frozen characters")
    if any(len(line) <= 1 for line in lines):
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
