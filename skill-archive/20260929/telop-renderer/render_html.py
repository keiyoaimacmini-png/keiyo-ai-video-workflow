#!/usr/bin/env python3
"""Render one Telop JSON as a Chrome HTML/CSS screenshot."""

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
    load_telop,
    make_tokens,
    mid_time,
    screenshot_with_chrome,
    style_for,
    wrap_tokens,
    write_temp_source,
    escape_attr,
    escape_text,
)


def _background_css(background: str) -> str:
    if background == "preview":
        return PREVIEW_BACKGROUND
    return "transparent"


def html_document(telop: dict[str, Any], background: str, time_s: float) -> str:
    style = style_for(telop)
    frame = style["frame"]
    font_size = style["font_size"]
    line_height = style["line_height"]
    max_width = style["max_width"]
    lines = wrap_tokens(make_tokens(telop), max_width, font_size)
    state = animation_state(telop, time_s)
    outline_width = style["outline_width"]

    line_markup: list[str] = []
    for line in lines:
        spans: list[str] = []
        for token in line:
            if token["kind"] == "emoji":
                font_family = style["emoji_family"]
                token_class = "emoji"
            else:
                font_family = style["font_family"]
                token_class = "text-glyph"
            spans.append(
                "<span class=\""
                + token_class
                + "\" style=\"font-family:'"
                + escape_attr(font_family)
                + "';color:"
                + escape_attr(style["colors"][token["color"]])
                + ";-webkit-text-stroke:"
                + escape_attr(f"{outline_width:g}px {style['outline_color']}")
                + ";\">"
                + escape_text(token["value"])
                + "</span>"
            )
        line_markup.append("<div class=\"line\">" + "".join(spans) + "</div>")

    transform = f"translateY({state['translate_y']:.4f}px) scale({state['scale']:.6f})"
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<style>
html, body {{ width:1080px; height:1920px; margin:0; overflow:hidden; }}
body {{ background:{_background_css(background)}; }}
#frame {{
  position:absolute; left:{frame['left']}px; top:{frame['top']}px;
  width:{frame['width']}px; height:{frame['height']}px;
  display:flex; align-items:center; justify-content:center;
  transform-origin:50% 50%; transform:{transform}; opacity:{state['opacity']:.6f};
}}
#caption {{
  width:100%; text-align:center; display:flex; flex-direction:column;
  align-items:center; justify-content:center;
  font-family:'{escape_attr(style['font_family'])}', sans-serif;
  font-weight:{style['font_weight']}; font-size:{font_size:g}px;
  line-height:{line_height:g}px; white-space:pre;
  word-break:auto-phrase; line-break:strict; overflow-wrap:normal;
  -webkit-font-smoothing:antialiased;
}}
.line {{ height:{line_height:g}px; line-height:{line_height:g}px; white-space:pre;
  word-break:auto-phrase; line-break:strict; overflow-wrap:normal; }}
.text-glyph, .emoji {{
  paint-order:stroke fill; stroke-linejoin:round;
  font-size:{font_size:g}px; font-weight:{style['font_weight']};
}}
.emoji {{ font-family:'{escape_attr(style['emoji_family'])}', sans-serif; font-weight:400; }}
</style>
</head>
<body>
<div id="frame"><div id="caption">{"".join(line_markup)}</div></div>
</body>
</html>
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
    source = write_temp_source(html_document(telop, background, time_s), ".html", output_path.parent)
    try:
        return screenshot_with_chrome(source, output_path)
    finally:
        source.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render Telop JSON with HTML/CSS")
    parser.add_argument("json_file")
    parser.add_argument("--out", required=True, help="PNG output inside the renderer folder")
    parser.add_argument("--background", choices=("preview", "transparent"), default="preview")
    parser.add_argument("--time", type=float, default=None, help="absolute time in seconds")
    args = parser.parse_args(argv)
    try:
        telop = load_telop(args.json_file)
        output = render_telop(telop, args.out, args.background, args.time)
    except (OSError, ValueError, ValidationError, RuntimeError) as exc:
        print(f"render_html: {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
