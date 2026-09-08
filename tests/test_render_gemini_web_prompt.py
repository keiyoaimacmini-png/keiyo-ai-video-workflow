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
        self.assertIn("ドパガキに刺さるセリフ", result.stdout)
        self.assertIn("短い話し言葉", result.stdout)
        self.assertIn("24字を超えない", result.stdout)
        self.assertIn("使い方は動作を一言", result.stdout)
        self.assertNotIn("〜するだけ", result.stdout)
        self.assertIn("冒頭と同じ困りごとの解決を言う", result.stdout)
        self.assertIn("result の言い換えで終わらせない", result.stdout)
        self.assertIn("見た目や部分的な変化だけで、困りごと全体を解決したことにしない", result.stdout)
        self.assertIn("素材の事前確認を前提にしない", result.stdout)
        self.assertIn("取説調", result.stdout)
        self.assertNotIn("twenty_candidate_summary", result.stdout)
        self.assertNotIn("observed_actions", result.stdout)
        self.assertNotIn("傘型", result.stdout)
        self.assertNotIn("日差し", result.stdout)
        self.assertNotIn("AIza", result.stdout)

    def test_rejects_source_hash_fields(self) -> None:
        bad = json.loads(json.dumps(BRIEF))
        bad["note"] = "sha256:abc"
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
