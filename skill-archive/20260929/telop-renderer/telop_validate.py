#!/usr/bin/env python3
"""Phase 1 Telop JSON validator.

The validator is deliberately small and strict about the design-system values.
It does not alter input text or normalise JSON; a renderer receives only input
that has passed these checks.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
STYLE_PATH = ROOT / "styles.json"


class ValidationError(ValueError):
    """Raised when one Telop JSON object fails validation."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


def load_styles() -> dict[str, Any]:
    with STYLE_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _path_error(errors: list[str], path: str, message: str) -> None:
    errors.append(f"{path}: {message}")


def _validate_overflow(
    data: dict[str, Any],
    errors: list[str],
    styles: dict[str, Any],
    type_styles: dict[str, Any],
) -> None:
    """Reject wrapped content that cannot fit inside the fixed Phase 1 frame."""

    text = data.get("text")
    telop_type = data.get("type")
    font = data.get("font")
    elements = data.get("elements")
    emphasis = data.get("emphasis")
    if not isinstance(text, str) or not text or telop_type not in type_styles:
        return
    if not isinstance(font, dict) or "family" not in font:
        return
    if not isinstance(elements, list) or not elements:
        return
    for element in elements:
        if not isinstance(element, dict) or element.get("type") not in {"text", "emoji"}:
            return
        if not isinstance(element.get("value"), str):
            return
    if not isinstance(emphasis, dict) or not isinstance(emphasis.get("items"), list):
        return
    if any(
        not isinstance(item, dict) or not isinstance(item.get("text"), str)
        for item in emphasis["items"]
    ):
        return

    # Imported lazily because telop_common imports this validator.
    from telop_common import layout_for_type, make_tokens, wrap_tokens

    try:
        layout = layout_for_type(telop_type, styles)
    except (KeyError, TypeError, ValueError):
        return
    frame_height = layout["frame"].get("height")
    if not _is_number(frame_height):
        return
    lines = wrap_tokens(make_tokens(data), layout["max_width"], layout["font_size"])
    required_height = len(lines) * layout["line_height"]
    if required_height > float(frame_height):
        _path_error(
            errors,
            "text",
            f"wrapped content requires {required_height:g}px, exceeding frame height {float(frame_height):g}px",
        )


def _validate_timing(data: dict[str, Any], errors: list[str], require_timing: bool) -> None:
    timing_present = any(key in data for key in ("start", "end", "position"))
    if not require_timing and not timing_present:
        return

    for key in ("start", "end", "position"):
        if key not in data:
            _path_error(errors, key, "required for renderer input")

    start = data.get("start")
    end = data.get("end")
    if "start" in data:
        if not _is_number(start) or start < 0:
            _path_error(errors, "start", "must be a finite number >= 0")
    if "end" in data:
        if not _is_number(end) or end < 0:
            _path_error(errors, "end", "must be a finite number >= 0")
    if _is_number(start) and _is_number(end) and start >= end:
        _path_error(errors, "end", "must be greater than start")

    position = data.get("position")
    if not isinstance(position, dict):
        if "position" in data:
            _path_error(errors, "position", "must be an object with x and y")
        return
    for axis in ("x", "y"):
        value = position.get(axis)
        if not _is_number(value) or not 0 <= value <= 1:
            _path_error(errors, f"position.{axis}", "must be a finite number from 0 to 1")


def collect_errors(data: Any, require_timing: bool = True) -> list[str]:
    """Return all validation errors for one object without changing it."""

    errors: list[str] = []
    if not isinstance(data, dict):
        return ["$: must be a JSON object"]

    styles = load_styles()
    type_styles = styles.get("type_styles", {})
    types = set(type_styles)
    fonts = styles.get("fonts", {})
    font_definitions = {
        name: definition
        for name, definition in fonts.items()
        if name != "emoji" and isinstance(definition, dict)
    }
    font_families = set(font_definitions)
    defined_weights = {
        definition.get("weight")
        for definition in font_definitions.values()
        if isinstance(definition.get("weight"), int) and not isinstance(definition.get("weight"), bool)
    }
    colors = styles.get("colors", {})
    base_colors = set(styles.get("color_rules", {}).get("base", colors))
    emphasis_colors = set(styles.get("color_rules", {}).get("emphasis", colors))
    allowed_in = set(styles.get("motions", {}).get("in", []))
    allowed_out = set(styles.get("motions", {}).get("out", []))
    allowed_element_motions = set(styles.get("motions", {}).get("element", []))
    emoji_allowlist = set(styles.get("emoji_allowlist", []))
    avoided = set(styles.get("color_rules", {}).get("avoided", []))

    required = (
        "text",
        "type",
        "importance",
        "font",
        "text_style",
        "emphasis",
        "elements",
        "animation",
    )
    for key in required:
        if key not in data:
            _path_error(errors, key, "required")

    text = data.get("text")
    if not isinstance(text, str) or not text:
        _path_error(errors, "text", "must be a non-empty string")
    elif "\n" in text or "\r" in text:
        _path_error(errors, "text", "must not contain manual line breaks")
    elif any(emoji in text for emoji in emoji_allowlist):
        _path_error(errors, "text", "must not contain emoji; use an emoji element")

    telop_type = data.get("type")
    if telop_type not in types:
        _path_error(errors, "type", f"must be one of {sorted(types)}")

    if data.get("importance") not in {"NORMAL", "HIGH", "VERY_HIGH"}:
        _path_error(errors, "importance", "must be NORMAL, HIGH, or VERY_HIGH")

    font = data.get("font")
    selected_family = None
    if not isinstance(font, dict):
        _path_error(errors, "font", "must be an object")
    else:
        selected_family = font.get("family")
        if selected_family not in font_families:
            _path_error(errors, "font.family", f"must be one of {sorted(font_families)}")
        weight = font.get("weight")
        if not isinstance(weight, int) or isinstance(weight, bool) or weight not in defined_weights:
            _path_error(errors, "font.weight", f"must be one of the defined weights {sorted(defined_weights)}")
        elif selected_family in font_definitions:
            expected_weight = font_definitions[selected_family].get("weight")
            if weight != expected_weight:
                _path_error(errors, "font.weight", f"{selected_family} requires defined weight {expected_weight}")

    text_style = data.get("text_style")
    base_color = None
    outline_color = None
    if not isinstance(text_style, dict):
        _path_error(errors, "text_style", "must be an object")
    else:
        base_color = text_style.get("base_color")
        if base_color in avoided:
            _path_error(errors, "text_style.base_color", "dark navy/blue/purple colors are avoided")
        elif base_color not in base_colors:
            _path_error(errors, "text_style.base_color", f"must be one of {sorted(base_colors)}")
        outline = text_style.get("outline")
        if not isinstance(outline, dict):
            _path_error(errors, "text_style.outline", "must be an object")
        else:
            outline_color = outline.get("color")
            if outline_color != "black":
                if outline_color in avoided:
                    _path_error(errors, "text_style.outline.color", "dark navy/blue/purple colors are avoided")
                else:
                    _path_error(errors, "text_style.outline.color", "must be black")
            width = outline.get("width")
            if not _is_number(width) or not 0 < width <= 32:
                _path_error(errors, "text_style.outline.width", "must be a number from 0 (exclusive) to 32")

    emphasis = data.get("emphasis")
    emphasis_items: list[Any] = []
    if not isinstance(emphasis, dict):
        _path_error(errors, "emphasis", "must be an object")
    else:
        mode = emphasis.get("mode")
        if mode not in {"none", "full", "partial"}:
            _path_error(errors, "emphasis.mode", "must be none, full, or partial")
        items = emphasis.get("items")
        if not isinstance(items, list):
            _path_error(errors, "emphasis.items", "must be an array")
        else:
            emphasis_items = items
            if mode == "none" and items:
                _path_error(errors, "emphasis.items", "must be empty when mode is none")
            if mode == "full":
                if len(items) != 1:
                    _path_error(errors, "emphasis.items", "full mode requires exactly one item")
                elif isinstance(text, str) and isinstance(items[0], dict) and items[0].get("text") != text:
                    _path_error(errors, "emphasis.items[0].text", "full emphasis must equal text")
            if mode == "partial" and not 1 <= len(items) <= 2:
                _path_error(errors, "emphasis.items", "partial mode allows 1 or 2 items")
            seen_phrases: set[str] = set()
            for index, item in enumerate(items):
                item_path = f"emphasis.items[{index}]"
                if not isinstance(item, dict):
                    _path_error(errors, item_path, "must be an object")
                    continue
                phrase = item.get("text")
                color = item.get("color")
                if not isinstance(phrase, str) or not phrase:
                    _path_error(errors, f"{item_path}.text", "must be a non-empty string")
                elif isinstance(text, str) and phrase not in text:
                    _path_error(errors, f"{item_path}.text", "must exist literally in text")
                elif phrase in seen_phrases:
                    _path_error(errors, f"{item_path}.text", "must not duplicate another emphasis phrase")
                else:
                    seen_phrases.add(phrase)
                if color in avoided:
                    _path_error(errors, f"{item_path}.color", "dark navy/blue/purple colors are avoided")
                elif color not in emphasis_colors:
                    _path_error(errors, f"{item_path}.color", f"must be one of {sorted(emphasis_colors)}")

    elements = data.get("elements")
    text_parts: list[str] = []
    emoji_values: list[str] = []
    if not isinstance(elements, list) or not elements:
        _path_error(errors, "elements", "must be a non-empty array")
    else:
        has_text_element = False
        previous_emoji: str | None = None
        for index, element in enumerate(elements):
            element_path = f"elements[{index}]"
            if not isinstance(element, dict):
                _path_error(errors, element_path, "must be an object")
                continue
            element_type = element.get("type")
            value = element.get("value")
            if element_type == "text":
                has_text_element = True
                if not isinstance(value, str):
                    _path_error(errors, f"{element_path}.value", "text value must be a string")
                    previous_emoji = None
                else:
                    if not value:
                        _path_error(errors, f"{element_path}.value", "text value must not be empty")
                    text_parts.append(value)
                    previous_emoji = None
            elif element_type == "emoji":
                if value not in emoji_allowlist:
                    _path_error(errors, f"{element_path}.value", "emoji is not in the allowlist")
                else:
                    emoji_values.append(value)
                    if previous_emoji == value:
                        _path_error(errors, element_path, "identical emoji must not be consecutive")
                    previous_emoji = value
                if "animation" in element and element.get("animation") not in allowed_element_motions:
                    _path_error(
                        errors,
                        f"{element_path}.animation",
                        f"must be one of {sorted(allowed_element_motions)}",
                    )
            else:
                _path_error(errors, f"{element_path}.type", "must be text or emoji")
                previous_emoji = None
        if not has_text_element:
            _path_error(errors, "elements", "must contain at least one text element")

    if isinstance(text, str) and "".join(text_parts) != text:
        _path_error(errors, "elements", "concatenated text element values must equal text")

    max_emoji = 1 if telop_type == "NORMAL" else 2
    if len(emoji_values) > max_emoji:
        _path_error(errors, "elements", f"this telop type allows at most {max_emoji} emoji")

    animation = data.get("animation")
    if not isinstance(animation, dict):
        _path_error(errors, "animation", "must be an object")
    else:
        if animation.get("in") not in allowed_in:
            _path_error(errors, "animation.in", f"must be one of {sorted(allowed_in)}")
        if animation.get("out") not in allowed_out:
            _path_error(errors, "animation.out", f"must be one of {sorted(allowed_out)}")

    if base_color in base_colors:
        content_colors = {base_color}
        for item in emphasis_items:
            if isinstance(item, dict) and item.get("color") in emphasis_colors:
                content_colors.add(item["color"])
        if len(content_colors) > 2:
            _path_error(errors, "text_style/emphasis", "use about two content colors per telop")

    _validate_overflow(data, errors, styles, type_styles)
    _validate_timing(data, errors, require_timing)
    return errors


def validate_telop(data: Any, require_timing: bool = True) -> dict[str, Any]:
    """Validate and return the original object unchanged."""

    errors = collect_errors(data, require_timing=require_timing)
    if errors:
        raise ValidationError(errors)
    return data


def validate_file(path: str | Path, require_timing: bool = True) -> dict[str, Any]:
    file_path = Path(path)
    with file_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return validate_telop(data, require_timing=require_timing)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Phase 1 Telop JSON")
    parser.add_argument("json_files", nargs="+", help="JSON files to validate")
    parser.add_argument(
        "--stage",
        choices=("generation", "render"),
        default="render",
        help="generation permits missing start/end/position; render requires them",
    )
    args = parser.parse_args(argv)
    require_timing = args.stage == "render"
    failed = False
    for name in args.json_files:
        try:
            validate_file(name, require_timing=require_timing)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            failed = True
            print(f"INVALID {name}: {exc}", file=sys.stderr)
        else:
            print(f"VALID {name} stage={args.stage}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
