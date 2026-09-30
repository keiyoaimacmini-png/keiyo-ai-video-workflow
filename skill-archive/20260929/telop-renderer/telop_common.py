#!/usr/bin/env python3
"""Shared, deterministic layout and Chrome screenshot helpers for Phase 1."""

from __future__ import annotations

import copy
import html
import json
import math
import signal
import os
import shutil
import subprocess
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Any

from telop_validate import ValidationError, load_styles, validate_telop


ROOT = Path(__file__).resolve().parent
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
PREVIEW_BACKGROUND = "#9AA1A8"
TRANSPARENT_BACKGROUND = "transparent"


def load_telop(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return validate_telop(data, require_timing=True)


def ensure_output_path(path: str | Path) -> Path:
    output = Path(path).expanduser().resolve()
    try:
        output.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError(f"output must be inside {ROOT}") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def layout_for_type(telop_type: str, styles: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the shared frame and typography metrics used by every renderer."""

    registry = load_styles() if styles is None else styles
    frame = registry["frame"]
    type_style = registry["type_styles"][telop_type]
    font_size = float(type_style["font_size"])
    line_height = font_size * float(type_style["line_height"])
    max_width = float(frame["width"]) - 2.0 * float(frame.get("padding", 24))
    return {
        "frame": frame,
        "type_style": type_style,
        "font_size": font_size,
        "line_height": line_height,
        "max_width": max_width,
    }


def style_for(telop: dict[str, Any]) -> dict[str, Any]:
    styles = load_styles()
    layout = layout_for_type(telop["type"], styles)
    font_key = telop["font"]["family"]
    runtime_font = styles["fonts"][font_key]
    colors = styles["colors"]
    outline = telop["text_style"]["outline"]
    return {
        "canvas": styles["canvas"],
        "frame": layout["frame"],
        "type_style": layout["type_style"],
        "font_size": layout["font_size"],
        "line_height": layout["line_height"],
        "max_width": layout["max_width"],
        "font_key": font_key,
        "font_family": runtime_font["family"],
        "font_weight": telop["font"]["weight"],
        "emoji_family": styles["fonts"]["emoji"]["family"],
        "colors": colors,
        "base_color": colors[telop["text_style"]["base_color"]],
        "outline_color": colors[outline["color"]],
        "outline_width": float(outline["width"]),
    }


def _emphasis_ranges(telop: dict[str, Any]) -> list[tuple[int, int, str]]:
    text = telop["text"]
    ranges: list[tuple[int, int, str]] = []
    for item in telop["emphasis"]["items"]:
        phrase = item["text"]
        start = text.find(phrase)
        if start >= 0:
            ranges.append((start, start + len(phrase), item["color"]))
    return ranges


def _color_for_index(index: int, base_color: str, ranges: list[tuple[int, int, str]]) -> str:
    for start, end, color in ranges:
        if start <= index < end:
            return color
    return base_color


def make_tokens(telop: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the declared element order while preserving every code point."""

    ranges = _emphasis_ranges(telop)
    base_color = telop["text_style"]["base_color"]
    font_key = telop["font"]["family"]
    tokens: list[dict[str, Any]] = []
    text_offset = 0
    for element in telop["elements"]:
        if element["type"] == "text":
            for character in element["value"]:
                tokens.append(
                    {
                        "kind": "text",
                        "value": character,
                        "color": _color_for_index(text_offset, base_color, ranges),
                        "font_key": font_key,
                    }
                )
                text_offset += 1
        else:
            tokens.append(
                {
                    "kind": "emoji",
                    "value": element["value"],
                    "color": base_color,
                    "font_key": "emoji",
                    "animation": element.get("animation"),
                }
            )
    return tokens


def token_width(token: dict[str, Any], font_size: float) -> float:
    if token["kind"] == "emoji":
        return font_size * 1.04
    character = token["value"]
    if character.isspace():
        return font_size * 0.45
    if unicodedata.combining(character):
        return 0.0
    if ord(character) < 128:
        return font_size * 0.58
    return font_size


KINSOKU_NO_LEADING = frozenset("！？、。）」』】〕〉》》…：；")


def _is_ascii_word_character(character: str) -> bool:
    return character.isascii() and (character.isalnum() or character in "_'")


def _japanese_script(character: str) -> str | None:
    codepoint = ord(character)
    category = unicodedata.category(character)
    if category[0] not in {"L", "N"}:
        return None
    if 0x3040 <= codepoint <= 0x309F:
        return "hiragana"
    if 0x30A0 <= codepoint <= 0x30FF:
        return "katakana"
    if 0x3400 <= codepoint <= 0x9FFF or 0xF900 <= codepoint <= 0xFAFF or codepoint == 0x3005:
        return "han"
    return None


def _break_units(tokens: list[dict[str, Any]], max_width: float, font_size: float) -> list[list[dict[str, Any]]]:
    """Build conservative break units for SVG and the shared overflow check.

    Chrome's ``auto-phrase`` is the HTML hint. SVG has no equivalent line
    breaker, so contiguous Japanese script runs and ASCII words remain whole
    when they fit. An overlong script run falls back to codepoint breaks. This
    avoids a morphology implementation while keeping both renderers and
    validation on the same deterministic path.
    """

    units: list[list[dict[str, Any]]] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token["kind"] != "text":
            units.append([token])
            index += 1
            continue

        character = token["value"]
        if character.isspace() or unicodedata.combining(character):
            if units:
                units[-1].append(token)
            else:
                units.append([token])
            index += 1
            continue

        if _is_ascii_word_character(character):
            end = index + 1
            while end < len(tokens):
                candidate = tokens[end]
                if candidate["kind"] != "text" or not _is_ascii_word_character(candidate["value"]):
                    break
                end += 1
            units.append(tokens[index:end])
            index = end
            continue

        script = _japanese_script(character)
        if script is not None:
            end = index + 1
            while end < len(tokens):
                candidate = tokens[end]
                if candidate["kind"] != "text" or _japanese_script(candidate["value"]) != script:
                    break
                end += 1
            japanese_run = tokens[index:end]
            run_width = sum(token_width(item, font_size) for item in japanese_run)
            if run_width <= max_width:
                units.append(japanese_run)
            else:
                units.extend([item] for item in japanese_run)
            index = end
            continue

        if character in KINSOKU_NO_LEADING and units:
            units[-1].append(token)
        else:
            units.append([token])
        index += 1
    return units


def wrap_tokens(tokens: list[dict[str, Any]], max_width: float, font_size: float) -> list[list[dict[str, Any]]]:
    lines: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_width = 0.0
    for unit in _break_units(tokens, max_width, font_size):
        width = sum(token_width(token, font_size) for token in unit)
        if current and current_width + width > max_width:
            lines.append(current)
            current = []
            current_width = 0.0
        current.extend(unit)
        current_width += width
    if current or not lines:
        lines.append(current)
    return lines


def escape_attr(value: Any) -> str:
    return html.escape(str(value), quote=True)


def escape_text(value: str) -> str:
    return html.escape(value, quote=False)


def animation_state(telop: dict[str, Any], time_s: float) -> dict[str, float]:
    start = float(telop["start"])
    end = float(telop["end"])
    total = max(end - start, 0.001)
    intro = min(0.16, total / 4.0)
    outro = min(0.16, total / 4.0)
    opacity = 1.0
    scale = 1.0
    translate_y = 0.0
    if time_s < start or time_s >= end:
        return {"opacity": 0.0, "scale": 1.0, "translate_y": 0.0}

    if time_s < start + intro:
        progress = max(0.0, min(1.0, (time_s - start) / intro))
        eased = 1.0 - (1.0 - progress) ** 3
        if telop["animation"]["in"] == "pop":
            scale = 0.84 + 0.16 * eased
        elif telop["animation"]["in"] == "soft_slide":
            translate_y = 28.0 * (1.0 - eased)

    if telop["animation"]["out"] == "fade_short" and time_s > end - outro:
        opacity = max(0.0, min(1.0, (end - time_s) / outro))
    return {"opacity": opacity, "scale": scale, "translate_y": translate_y}


def _chrome_command(output: Path, source: Path, profile_dir: Path) -> list[str]:
    return [
        str(CHROME),
        "--headless=new",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--disable-dev-shm-usage",
        "--disable-features=UseSkiaRenderer",
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--force-device-scale-factor=1",
        "--window-size=1080,1920",
        "--default-background-color=00000000",
        f"--user-data-dir={profile_dir}",
        f"--screenshot={output}",
        source.as_uri(),
    ]


def screenshot_with_chrome(source: Path, output: str | Path) -> Path:
    output_path = ensure_output_path(output)
    if not CHROME.is_file():
        raise RuntimeError(f"Chrome headless executable not found: {CHROME}")
    # Avoid treating a previous render as the new screenshot while Chrome starts.
    output_path.unlink(missing_ok=True)
    profile_dir = Path(tempfile.mkdtemp(prefix=".chrome-profile-", dir=str(output_path.parent)))
    process: subprocess.Popen[str] | None = None
    try:
        command = _chrome_command(output_path, source, profile_dir)
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline and not output_path.is_file():
            return_code = process.poll()
            if return_code is not None:
                stdout, stderr = process.communicate()
                detail = (stderr or stdout or "no Chrome output").strip()
                raise RuntimeError(f"Chrome headless screenshot failed ({return_code}): {detail}")
            time.sleep(0.05)
        if not output_path.is_file():
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate(timeout=5)
            detail = (stderr or stdout or "no screenshot before timeout").strip()
            raise RuntimeError(f"Chrome headless screenshot timed out: {detail}")
        # This Chrome build can keep its profile-backed parent open after writing.
        # The PNG is complete; close only the process group started for this render.
        if process.poll() is None:
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate(timeout=5)
        if process.returncode not in (0, -signal.SIGTERM, -signal.SIGKILL):
            detail = (stderr or stdout or "no Chrome output").strip()
            raise RuntimeError(f"Chrome headless screenshot failed ({process.returncode}): {detail}")
    finally:
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                process.communicate(timeout=5)
            except (subprocess.TimeoutExpired, OSError):
                pass
        shutil.rmtree(profile_dir, ignore_errors=True)
    return output_path


def write_temp_source(content: str, suffix: str, directory: Path) -> Path:
    fd, name = tempfile.mkstemp(prefix=".telop-", suffix=suffix, dir=str(directory))
    os.close(fd)
    path = Path(name)
    path.write_text(content, encoding="utf-8")
    return path


def mid_time(telop: dict[str, Any]) -> float:
    return (float(telop["start"]) + float(telop["end"])) / 2.0


def clone_for_clip(telop: dict[str, Any], duration: float) -> dict[str, Any]:
    cloned = copy.deepcopy(telop)
    cloned["start"] = 0.0
    cloned["end"] = duration
    return validate_telop(cloned, require_timing=True)
