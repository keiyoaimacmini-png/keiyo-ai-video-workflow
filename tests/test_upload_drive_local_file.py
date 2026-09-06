#!/usr/bin/env python3
"""Repo tests for the Drive local-path ingest helper."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def _clean_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key != "GOOGLE_DRIVE_ACCESS_TOKEN"}


REPO = Path(__file__).resolve().parent.parent
HELPER = (
    REPO
    / ".cursor"
    / "skills"
    / "produce-tiktok-product-video-portable"
    / "scripts"
    / "upload_drive_local_file.py"
)


class UploadDriveLocalFileTests(unittest.TestCase):
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

    def test_missing_auth_holds_without_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "clip.mp4"
            video.write_bytes(b"not-a-real-video")
            result = subprocess.run(
                [
                    sys.executable,
                    str(HELPER),
                    "--project-root",
                    str(root),
                    "--local-path",
                    str(video),
                    "--title",
                    video.name,
                    "--parent-title",
                    "AN-S182",
                ],
                cwd=REPO,
                text=True,
                capture_output=True,
                check=False,
                env=_clean_env(),
            )
        self.assertEqual(result.returncode, 2, result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["hold"], "HOLD_DRIVE_LOCAL_BYTES_UNAVAILABLE")
        dumped = json.dumps(payload)
        self.assertNotIn("ya29.", dumped)
        self.assertNotIn("refresh_token", dumped)
        self.assertNotIn("Bearer ", dumped)

    def test_login_from_agent_holds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(HELPER), "--project-root", tmp, "--login"],
                cwd=REPO,
                text=True,
                capture_output=True,
                check=False,
                env=_clean_env(),
            )
        self.assertEqual(result.returncode, 2, result.stderr or result.stdout)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["hold"], "HOLD_DRIVE_LOCAL_BYTES_UNAVAILABLE")
        self.assertIn("Terminal", payload["reason"])
