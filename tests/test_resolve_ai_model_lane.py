#!/usr/bin/env python3
"""Repo test wrapper for assistant-model lane classification."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
RESOLVER = (
    REPO
    / ".cursor"
    / "skills"
    / "produce-tiktok-product-video-portable"
    / "scripts"
    / "resolve_ai_model_lane.py"
)


class ResolveAiModelLaneTests(unittest.TestCase):
    def test_self_test_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(RESOLVER), "--self-test"],
            cwd=REPO,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("SELF-TEST PASSED", result.stdout)

    def test_gemini_script_lane_ready(self) -> None:
        result = subprocess.run(
            [sys.executable, str(RESOLVER), "--model", "gemini-3.8-flash", "--stage", "PREFLIGHT"],
            cwd=REPO,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn('"lane": "script"', result.stdout)
        self.assertIn('"status": "READY"', result.stdout)

    def test_grok_cannot_start_script(self) -> None:
        result = subprocess.run(
            [sys.executable, str(RESOLVER), "--model", "cursor-grok-4.6-xhigh", "--stage", "PREFLIGHT"],
            cwd=REPO,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2, result.stderr or result.stdout)
        self.assertIn("HOLD_AI_MODEL_SCRIPT_LANE_REQUIRED", result.stdout)

    def test_gemini_cannot_enter_rough_edit(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(RESOLVER),
                "--model",
                "Gemini 3.8 Flash",
                "--stage",
                "SCRIPT_REVIEW",
                "--entering-rough-edit",
            ],
            cwd=REPO,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2, result.stderr or result.stdout)
        self.assertIn("HOLD_AI_MODEL_HANDOFF_REQUIRED", result.stdout)

    def test_handoff_card_uses_relative_paths(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(RESOLVER),
                "--print-handoff-card",
                "--case-id",
                "AN-S182-example-001",
                "--product-model",
                "AN-S182",
                "--task-root",
                "outputs/AN-S182-example-001",
                "--script-approved",
            ],
            cwd=REPO,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("/produce-tiktok-product-video-portable", result.stdout)
        self.assertIn("Grok 4.6", result.stdout)
        self.assertIn("outputs/AN-S182-example-001/product-video-workflow-state.v1.json", result.stdout)
        self.assertIn("ROUGH_EDIT", result.stdout)
        self.assertNotIn("/Users/", result.stdout)


if __name__ == "__main__":
    unittest.main()
