#!/usr/bin/env python3
"""Parse Gemini 3–5 script variants into compact JSON."""

from __future__ import annotations

import argparse
import json
import re
from typing import Any

from paths import emit
from script_grounding import parse_evidence_ids
from workflow_state import hold

VARIANT_RE = re.compile(
    r"【案\s*([1-9])\s*[：:]\s*(.+?)】",
    re.MULTILINE,
)
DURATION_RE = re.compile(r"想定完成尺：\s*約\s*(\d+)\s*秒")
CUT_RE = re.compile(
    r"カット\s*(\d+)\s*"
    r"(?:根拠ID\s*[：:]\s*([^\n]+)\s*)?"
    r"シチュエーション：\s*「(.*?)」\s*"
    r"セリフ：\s*「(.*?)」",
    re.DOTALL,
)


def parse_gemini_scripts(text: str) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        return hold("HOLD_SCRIPT_PARSE", "Gemini output is empty")
    starts = list(VARIANT_RE.finditer(text))
    if not starts:
        return hold("HOLD_SCRIPT_PARSE", "no variants found")
    variants: list[dict[str, Any]] = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        block = text[match.start() : end]
        variant_id = int(match.group(1))
        title = match.group(2).strip()
        duration_match = DURATION_RE.search(block)
        cuts: list[dict[str, Any]] = []
        for cut in CUT_RE.finditer(block):
            cuts.append(
                {
                    "cut_id": f"c{cut.group(1)}",
                    "index": int(cut.group(1)),
                    "evidence_ids": parse_evidence_ids(cut.group(2)),
                    "situation": cut.group(3).strip(),
                    "line": cut.group(4).strip(),
                }
            )
        if not cuts:
            return hold("HOLD_SCRIPT_PARSE", f"variant {variant_id} has no cuts")
        for cut in cuts:
            if not cut["line"] or not cut["situation"]:
                return hold("HOLD_SCRIPT_PARSE", f"variant {variant_id} has an empty line or situation")
        variants.append(
            {
                "variant_id": variant_id,
                "title": title,
                "estimated_seconds": int(duration_match.group(1)) if duration_match else None,
                "cuts": cuts,
            }
        )
    ids = [item["variant_id"] for item in variants]
    if len(ids) != len(set(ids)):
        return hold("HOLD_SCRIPT_PARSE", "duplicate variant ids")
    if len(variants) < 3 or len(variants) > 5:
        return hold("HOLD_SCRIPT_PARSE", f"expected 3-5 variants, got {len(variants)}")
    return {"status": "OK", "variant_count": len(variants), "variants": variants}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=argparse.FileType("r", encoding="utf-8"))
    args = parser.parse_args()
    text = args.input.read() if args.input else ""
    payload = parse_gemini_scripts(text)
    emit(payload)
    return 0 if payload.get("status") == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
