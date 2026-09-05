#!/usr/bin/env python3
"""Repo tests for the Gemini Web paste-prompt renderer."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
HELPER = (
    REPO
    / ".cursor"
    / "skills"
    / "produce-tiktok-product-video-portable"
    / "scripts"
    / "render_gemini_web_prompt.py"
)
BRIEF = {
    "schema": "product_video_gemini_web_brief.v1",
    "product_model": "AN-S182",
    "cta_text": "下からチェック！",
    "verified_facts": ["仮眠が続かない"],
    "usable_shots": [{"asset_id": "asset-a", "observed_action": "shade opens"}],
}


class RenderGeminiWebPromptTests(unittest.TestCase):
    def test_self_test_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(HELPER), "--self-test"],
            cwd=REPO,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("SELF-TEST PASSED", result.stdout)

    def test_renders_pasteable_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "brief.json"
            path.write_text(json.dumps(BRIEF, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(HELPER), "--brief", str(path)],
                cwd=REPO,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("下からチェック！", result.stdout)
        self.assertIn("problem_or_hook", result.stdout)
        self.assertNotIn("AIza", result.stdout)

    def test_rejects_source_hash_fields(self) -> None:
        bad = json.loads(json.dumps(BRIEF))
        bad["usable_shots"][0]["sha256"] = "abc"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "brief.json"
            path.write_text(json.dumps(bad), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(HELPER), "--brief", str(path)],
                cwd=REPO,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 2)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["hold"], "HOLD_SCRIPT_INCOMPLETE")
