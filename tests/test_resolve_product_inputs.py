#!/usr/bin/env python3
"""Repo test wrapper for the portable product-input resolver."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
RESOLVER = REPO / ".cursor" / "skills" / "produce-tiktok-product-video-portable" / "scripts" / "resolve_product_inputs.py"


class ResolveProductInputsTests(unittest.TestCase):
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

    def test_an_s182_resolves_in_this_repo(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(RESOLVER),
                "--project-root",
                str(REPO),
                "--product-model",
                "AN-S182",
            ],
            cwd=REPO,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("product_video_settings_AN-S182.v1.json", result.stdout)
        self.assertIn('"drive_folder_title": "AN-S182"', result.stdout)
        self.assertIn('"delivery_mode_default": "drive"', result.stdout)

    def test_unknown_model_holds(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(RESOLVER),
                "--project-root",
                str(REPO),
                "--product-model",
                "AN-Z999",
            ],
            cwd=REPO,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("HOLD_PRODUCT_VIDEO_SETTINGS", result.stdout)


if __name__ == "__main__":
    unittest.main()
