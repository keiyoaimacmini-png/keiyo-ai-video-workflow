#!/usr/bin/env python3

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

from render_html import html_document, render_telop
from render_svg import svg_document
from telop_common import layout_for_type, make_tokens, style_for, wrap_tokens
from telop_validate import ValidationError, validate_telop


ROOT = Path(__file__).resolve().parent


class _LineParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []
        self._current: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "div" and dict(attrs).get("class") == "line":
            self._current = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self._current is not None:
            self.lines.append("".join(self._current))
            self._current = None

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current.append(data)


def valid_case() -> dict:
    with (ROOT / "samples" / "emphasis.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


class TelopValidatorTests(unittest.TestCase):
    def test_valid_case(self) -> None:
        case = valid_case()
        self.assertIs(validate_telop(case), case)

    def test_defined_font_differing_from_type_default_passes(self) -> None:
        case = valid_case()
        case["font"] = {"family": "rounded_bold", "weight": 700}
        self.assertIs(validate_telop(case), case)

    def test_undefined_font_fails(self) -> None:
        case = valid_case()
        case["font"] = {"family": "not_defined", "weight": 700}
        with self.assertRaises(ValidationError):
            validate_telop(case)

    def test_undefined_font_weight_fails(self) -> None:
        case = valid_case()
        case["font"]["weight"] = 800
        with self.assertRaises(ValidationError):
            validate_telop(case)

    def test_invalid_enum(self) -> None:
        case = valid_case()
        case["type"] = "UNKNOWN"
        with self.assertRaises(ValidationError):
            validate_telop(case)

    def test_invalid_too_many_emoji(self) -> None:
        case = valid_case()
        case["elements"] = [
            {"type": "text", "value": case["text"]},
            {"type": "emoji", "value": "📱"},
            {"type": "emoji", "value": "✨"},
            {"type": "emoji", "value": "🔥"},
        ]
        with self.assertRaises(ValidationError):
            validate_telop(case)

    def test_invalid_element_animation(self) -> None:
        case = valid_case()
        case["elements"][-1]["animation"] = "fade_short"
        with self.assertRaises(ValidationError):
            validate_telop(case)

    def test_invalid_consecutive_identical_emoji(self) -> None:
        case = valid_case()
        case["elements"] = [
            {"type": "text", "value": case["text"]},
            {"type": "emoji", "value": "📱", "animation": "pop"},
            {"type": "emoji", "value": "📱", "animation": "pop"},
        ]
        with self.assertRaises(ValidationError):
            validate_telop(case)

    def test_invalid_avoided_color(self) -> None:
        case = valid_case()
        case["text_style"]["base_color"] = "dark_navy"
        with self.assertRaises(ValidationError):
            validate_telop(case)

    def test_invalid_more_than_two_content_colors(self) -> None:
        case = valid_case()
        case["emphasis"] = {
            "mode": "partial",
            "items": [
                {"text": "これ", "color": "yellow"},
                {"text": "スマホ", "color": "red"},
            ],
        }
        with self.assertRaises(ValidationError):
            validate_telop(case)

    def test_invalid_full_mode_mismatch(self) -> None:
        case = valid_case()
        case["emphasis"]["mode"] = "full"
        case["emphasis"]["items"] = [{"text": "スマホだけで", "color": "yellow"}]
        with self.assertRaises(ValidationError):
            validate_telop(case)

    def test_invalid_timing(self) -> None:
        case = valid_case()
        case["end"] = case["start"]
        with self.assertRaises(ValidationError):
            validate_telop(case)

    def test_invalid_invariant(self) -> None:
        case = valid_case()
        case["elements"][0]["value"] = "本文が違う"
        with self.assertRaises(ValidationError):
            validate_telop(case)

    def test_invalid_nonexistent_emphasis_phrase(self) -> None:
        case = valid_case()
        case["emphasis"]["items"][0]["text"] = "存在しない語"
        with self.assertRaises(ValidationError):
            validate_telop(case)

    def test_overflow_just_fits(self) -> None:
        case = valid_case()
        case["text"] = "あ" * 14
        case["type"] = "HOOK"
        case["importance"] = "VERY_HIGH"
        case["emphasis"] = {"mode": "full", "items": [{"text": case["text"], "color": "yellow"}]}
        case["elements"] = [{"type": "text", "value": case["text"]}]
        self.assertIs(validate_telop(case), case)

    def test_overflow_rejected(self) -> None:
        case = valid_case()
        case["text"] = "あ" * 15
        case["type"] = "HOOK"
        case["importance"] = "VERY_HIGH"
        case["emphasis"] = {"mode": "full", "items": [{"text": case["text"], "color": "yellow"}]}
        case["elements"] = [{"type": "text", "value": case["text"]}]
        with self.assertRaises(ValidationError):
            validate_telop(case)

    def test_wrap_tokens(self) -> None:
        tokens = make_tokens(valid_case())
        lines = wrap_tokens(tokens, max_width=2.0, font_size=1.0)
        self.assertEqual(
            [[token["value"] for token in line] for line in lines],
            [["こ", "れ"], ["ス", "マ"], ["ホ", "だ"], ["け", "で"], ["簡", "単"], ["に"], ["操", "作"], ["で", "き"], ["る"], ["📱"]],
        )

    def test_target_phrase_and_kinsoku_wrap(self) -> None:
        case = valid_case()
        lines = wrap_tokens(make_tokens(case), max_width=816.0, font_size=82.0)
        values = ["".join(token["value"] for token in line) for line in lines]
        self.assertEqual(values, ["これスマホだけで", "簡単に操作できる📱"])
        self.assertTrue(all(line and line[0]["value"] not in "！？、。」" for line in lines))

    def test_shared_layout_metrics(self) -> None:
        case = valid_case()
        layout = layout_for_type(case["type"])
        style = style_for(case)
        self.assertEqual(layout["frame"]["height"], 287)
        self.assertEqual(style["font_size"], layout["font_size"])
        self.assertEqual(style["line_height"], layout["line_height"])
        self.assertEqual(style["max_width"], layout["max_width"])

    def test_renderers_use_shared_line_breaks(self) -> None:
        case = valid_case()
        expected = ["".join(token["value"] for token in line) for line in wrap_tokens(make_tokens(case), 816.0, 82.0)]

        html = html_document(case, "transparent", 1.0)
        parser = _LineParser()
        parser.feed(html)
        self.assertEqual(parser.lines, expected)
        self.assertIn("word-break:auto-phrase", html)
        self.assertIn("line-break:strict", html)

        svg_root = ElementTree.fromstring(svg_document(case, "transparent", 1.0))
        namespace = "{http://www.w3.org/2000/svg}"
        svg_lines = ["".join(element.itertext()) for element in svg_root.findall(f"{namespace}g/{namespace}text")]
        self.assertEqual(svg_lines, expected)


class TransparentRenderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix=".test-render-", dir=str(ROOT)))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_transparent_png_has_alpha(self) -> None:
        output = self.temp_dir / "transparent.png"
        render_telop(valid_case(), output, background="transparent", time_s=1.0)
        payload = output.read_bytes()
        self.assertEqual(payload[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(payload[25], 6, "PNG color type must be RGBA (6)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
