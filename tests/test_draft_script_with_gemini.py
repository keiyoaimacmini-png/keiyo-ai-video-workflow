#!/usr/bin/env python3
"""Repo test wrapper for the Gemini script-draft helper."""

from __future__ import annotations

import json
import os
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
    / "draft_script_with_gemini.py"
)
BRIEF = {
    "schema": "product_video_gemini_script_brief.v1",
    "product_model": "AN-S182",
    "verified_facts": ["仮眠が続かない"],
    "usable_shots": [{"asset_id": "asset-a", "observed_action": "shade opens"}],
    "cta_text": "下からチェック！",
}


def _env_without_keys() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key not in {"GEMINI_API_KEY", "GOOGLE_API_KEY"}
    }


class DraftScriptWithGeminiTests(unittest.TestCase):
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

    def test_missing_key_holds_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            brief_path = Path(tmp) / "brief.json"
            brief_path.write_text(json.dumps(BRIEF, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(HELPER), "--brief", str(brief_path)],
                cwd=REPO,
                text=True,
                capture_output=True,
                check=False,
                env=_env_without_keys(),
            )
        self.assertEqual(result.returncode, 2, result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "HOLD")
        self.assertEqual(payload["hold"], "HOLD_GEMINI_SCRIPT_API_UNAVAILABLE")
        self.assertNotIn("AIza", result.stdout + result.stderr)

    def test_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            brief_path = Path(tmp) / "brief.json"
            output_path = Path(tmp) / "draft.json"
            brief_path.write_text(json.dumps(BRIEF, ensure_ascii=False), encoding="utf-8")
            output_path.write_text("existing\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(HELPER),
                    "--brief",
                    str(brief_path),
                    "--output",
                    str(output_path),
                ],
                cwd=REPO,
                text=True,
                capture_output=True,
                check=False,
                env=_env_without_keys(),
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("refusing to overwrite output", result.stderr)
            self.assertEqual(output_path.read_text(encoding="utf-8"), "existing\n")
