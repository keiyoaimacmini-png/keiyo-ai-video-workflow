#!/usr/bin/env python3
"""Repo tests for product-video v3 craft gates and the lesson loop."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
V3 = REPO / ".cursor" / "skills" / "produce-tiktok-product-video-v3" / "scripts"
FIXTURES = REPO / ".cursor" / "skills" / "produce-tiktok-product-video-v3" / "tests" / "fixtures"


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=False,
    )


class ProductVideoV3Tests(unittest.TestCase):
    def test_record_lesson_self_test(self) -> None:
        result = run([str(V3 / "record_lesson.py"), "--self-test"])
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("SELF-TEST PASSED: record_lesson", result.stdout)

    def test_craft_quality_self_test_loads_seed_lesson(self) -> None:
        result = run(
            [str(V3 / "validate_craft_quality.py"), "--self-test", "--project-root", str(REPO)]
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("SELF-TEST PASSED: validate_craft_quality", result.stdout)

    def test_gemini_prompt_includes_rejected_and_accepted_pairs(self) -> None:
        result = run(
            [str(V3 / "render_gemini_web_prompt.py"), "--self-test", "--project-root", str(REPO)]
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("SELF-TEST PASSED: render_gemini_web_prompt", result.stdout)

    def test_ans182_sun_only_holds_before_script_ok(self) -> None:
        result = run(
            [
                str(V3 / "validate_craft_quality.py"),
                "--project-root",
                str(REPO),
                "--product-model",
                "AN-S182",
                "--surface",
                "script",
                "--artifact",
                str(FIXTURES / "ans182-heat-hook-sun-only.json"),
            ]
        )
        self.assertEqual(result.returncode, 2, result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["hold"], "HOLD_CRAFT_QUALITY")
        self.assertEqual(payload["defect"], "hook_closed_by_result_looks")

    def test_ans182_sun_only_not_restatement_holds(self) -> None:
        result = run(
            [
                str(V3 / "validate_craft_quality.py"),
                "--project-root",
                str(REPO),
                "--product-model",
                "AN-S182",
                "--surface",
                "script",
                "--artifact",
                str(FIXTURES / "ans182-heat-hook-sun-only-not-restatement.json"),
            ]
        )
        self.assertEqual(result.returncode, 2, result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["hold"], "HOLD_CRAFT_QUALITY")
        self.assertEqual(payload["defect"], "hook_closed_by_result_looks")

    def test_ans182_spoken_solution_passes(self) -> None:
        result = run(
            [
                str(V3 / "validate_craft_quality.py"),
                "--project-root",
                str(REPO),
                "--product-model",
                "AN-S182",
                "--surface",
                "script",
                "--artifact",
                str(FIXTURES / "ans182-heat-hook-solution.json"),
            ]
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "PASS")

    def test_load_lessons_returns_seed(self) -> None:
        result = run(
            [
                str(V3 / "load_lessons.py"),
                "--project-root",
                str(REPO),
                "--surface",
                "script",
                "--product-model",
                "AN-S182",
            ]
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        lessons = json.loads(result.stdout)
        self.assertTrue(any(item.get("id") == "hook-closed-by-result-looks" for item in lessons))
