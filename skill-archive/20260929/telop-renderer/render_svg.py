#!/usr/bin/env python3
"""Render one Telop JSON as a Chrome SVG screenshot."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from telop_common import (
    PREVIEW_BACKGROUND,
    ValidationError,
    animation_state,
    ensure_output_path,
    escape_attr,
    escape_text,
    load_telop,
    make_tokens,
    mid_time,
    screenshot_with_chrome,
    style_for,
    wrap_tokens,
    write_temp_source,
)


def svg_document(telop: dict[str, Any], background: str, time_s: float) -> str:
    style = style_for(telop)
    frame = style["frame"]
    canvas = style["canvas"]
    font_size = style["font_size"]
    line_height = style["line_height"]
    max_width = style["max_width"]
    lines = wrap_tokens(make_tokens(telop), max_width, font_size)
    state = animation_state(telop, time_s)
    center_x = canvas["width"] / 2.0
    center_y = frame["top"] + frame["height"] / 2.0
    total_height = len(lines) * line_height
    first_y = center_y - total_height / 2.0 + line_height / 2.0
    outline_width = style["outline_width"]

    background_markup = ""
    if background == "preview":
        background_markup = (
            f'<rect x="0" y="0" width="{canvas["width"]}" height="{canvas["height"]}" '
            f'fill="{PREVIEW_BACKGROUND}"/>'
        )

    lines_markup: list[str] = []
    for line_index, line in enumerate(lines):
        runs: list[str] = []
        for token in line:
            if token["kind"] == "emoji":
                family = style["emoji_family"]
                weight = 400
            else:
                family = style["font_family"]
                weight = style["font_weight"]
            runs.append(
                f'<tspan font-family="{escape_attr(family)}" font-weight="{weight}" '
                f'fill="{escape_attr(style["colors"][token["color"]])}" '
                f'stroke="{escape_attr(style["outline_color"])}" '
                f'stroke-width="{outline_width:g}" paint-order="stroke fill">'
                f"{escape_text(token['value'])}</tspan>"
            )
        y = first_y + line_index * line_height
        lines_markup.append(
            f'<text x="{center_x:g}" y="{y:g}" text-anchor="middle" '
            f'dominant-baseline="middle" font-family="{escape_attr(style["font_family"])}" '
            f'font-size="{font_size:g}px" font-weight="{style["font_weight"]}" '
            f'fill="{escape_attr(style["base_color"])}" '
            f'stroke="{escape_attr(style["outline_color"])}" '
            f'stroke-width="{outline_width:g}" paint-order="stroke fill">'
            + "".join(runs)
            + "</text>"
        )

    transform = (
        f"translate({center_x + state['translate_y'] * 0:g} {center_y + state['translate_y']:g}) "
        f"scale({state['scale']:.6f}) translate({-center_x:g} {-center_y:g})"
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{canvas['width']}" height="{canvas['height']}" viewBox="0 0 {canvas['width']} {canvas['height']}">
{background_markup}
<g opacity="{state['opacity']:.6f}" transform="{transform}">
{"".join(lines_markup)}
</g>
</svg>
"""


def render_telop(
    telop: dict[str, Any],
    output: str | Path,
    background: str = "transparent",
    time_s: float | None = None,
) -> Path:
    if background not in {"preview", "transparent"}:
        raise ValueError("background must be preview or transparent")
    # Phase 1 intentionally ignores JSON position; the fixed frame is the comparison baseline.
    if time_s is None:
        time_s = mid_time(telop)
    output_path = ensure_output_path(output)
    source = write_temp_source(svg_document(telop, background, time_s), ".svg", output_path.parent)
    try:
        return screenshot_with_chrome(source, output_path)
    finally:
        source.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render Telop JSON with SVG")
    parser.add_argument("json_file")
    parser.add_argument("--out", required=True, help="PNG output inside the renderer folder")
    parser.add_argument("--background", choices=("preview", "transparent"), default="preview")
    parser.add_argument("--time", type=float, default=None, help="absolute time in seconds")
    args = parser.parse_args(argv)
    try:
        telop = load_telop(args.json_file)
        output = render_telop(telop, args.out, args.background, args.time)
    except (OSError, ValueError, ValidationError, RuntimeError) as exc:
        print(f"render_svg: {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
