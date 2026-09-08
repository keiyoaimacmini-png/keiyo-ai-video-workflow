#!/usr/bin/env python3
"""Repo tests for the Antigravity CLI Gemini sender."""

from __future__ import annotations

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
    / "send_gemini_cli_prompt.py"
)


class SendGeminiCliPromptTests(unittest.TestCase):
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

    def test_empty_prompt_holds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prompt.txt"
            path.write_text(" \n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(HELPER), "--prompt-file", str(path)],
                cwd=REPO,
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("HOLD_GEMINI_CLI_NOT_VERIFIED", result.stdout)
