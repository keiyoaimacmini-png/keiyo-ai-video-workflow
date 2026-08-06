from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("verify_package", REPO / "scripts/verify_package.py")
VERIFY = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(VERIFY)


class PackageVerifierTests(unittest.TestCase):
    def copy_repo(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temp = tempfile.TemporaryDirectory()
        target = Path(temp.name) / "repo"
        shutil.copytree(REPO, target, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
        return temp, target

    def test_current_package_passes(self):
        self.assertEqual([], VERIFY.verify(REPO))

    def test_manifest_path_rules(self):
        for value in ("file.txt", "a/b/c.json", ".agents/plugins/marketplace.json"):
            self.assertTrue(VERIFY.safe_manifest_path(value), value)
        for value in ("", "/etc/passwd", "../secret", "a/../b", "~/secret", "C:\\secret"):
            self.assertFalse(VERIFY.safe_manifest_path(value), value)

    def test_modified_skill_is_rejected(self):
        temp, target = self.copy_repo()
        try:
            path = target / VERIFY.SKILL / "SKILL.md"
            path.write_text(path.read_text(encoding="utf-8") + "\nmodified\n", encoding="utf-8")
            errors = VERIFY.verify(target)
            self.assertTrue(any("hash mismatch" in error for error in errors))
            self.assertTrue(any("pinned skill hash mismatch" in error for error in errors))
        finally:
            temp.cleanup()

    def test_unmanaged_file_is_rejected(self):
        temp, target = self.copy_repo()
        try:
            (target / "unexpected.txt").write_text("unexpected", encoding="utf-8")
            self.assertTrue(any("files missing from manifest" in error for error in VERIFY.verify(target)))
        finally:
            temp.cleanup()

    def test_local_path_is_rejected(self):
        temp, target = self.copy_repo()
        try:
            value = "/" + "Users" + "/example/private/file"
            (target / "README.md").write_text(value, encoding="utf-8")
            self.assertTrue(any("macOS user path" in error for error in VERIFY.verify(target)))
        finally:
            temp.cleanup()

    def test_drive_destination_is_rejected(self):
        temp, target = self.copy_repo()
        try:
            value = "https://drive.google.com/drive/" + "folders/example"
            (target / "README.md").write_text(value, encoding="utf-8")
            self.assertTrue(any("Google Drive folder destination" in error for error in VERIFY.verify(target)))
        finally:
            temp.cleanup()

    def test_secret_token_is_rejected(self):
        temp, target = self.copy_repo()
        try:
            value = "gh" + "p_abcdefghijklmnopqrstuvwxyz123456"
            (target / "README.md").write_text(value, encoding="utf-8")
            self.assertTrue(any("GitHub classic token" in error for error in VERIFY.verify(target)))
        finally:
            temp.cleanup()

    def test_media_file_is_rejected(self):
        temp, target = self.copy_repo()
        try:
            (target / "clip.mp4").write_bytes(b"not media")
            self.assertTrue(any("media" in error for error in VERIFY.verify(target)))
        finally:
            temp.cleanup()

    def test_symlink_is_rejected(self):
        temp, target = self.copy_repo()
        try:
            try:
                (target / "linked").symlink_to("README.md")
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink creation is unavailable on this platform: {exc}")
            self.assertTrue(any("symlink forbidden" in error for error in VERIFY.verify(target)))
        finally:
            temp.cleanup()

    def test_marketplace_tamper_is_rejected(self):
        temp, target = self.copy_repo()
        try:
            path = target / ".agents/plugins/marketplace.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["name"] = "other"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertTrue(any("marketplace identity" in error for error in VERIFY.verify(target)))
        finally:
            temp.cleanup()

    def test_release_and_sol_installs_are_separate(self):
        bootstrap = (REPO / "scripts/bootstrap.sh").read_text(encoding="utf-8")
        sol = (REPO / "scripts/install-sol-advisor.sh").read_text(encoding="utf-8")
        self.assertNotIn("install-sol-advisor.sh", bootstrap)
        self.assertIn("DannyMac180/sol-advisor", sol)
        self.assertIn("HOLD_MODEL_AVAILABILITY_UNVERIFIED", sol)
        self.assertIn('sol-advisor-terra-implementer.toml', sol)
        self.assertIn('sol-advisor-sol-reviewer.toml', sol)
        self.assertIn('gpt-5.6-terra', sol)
        self.assertIn('gpt-5.6-sol', sol)
        self.assertIn('model_reasoning_effort', sol)

    def test_bootstrap_requires_three_way_release_integrity(self):
        bootstrap = (REPO / "scripts/bootstrap.sh").read_text(encoding="utf-8")
        self.assertIn('MANIFEST.sha256', bootstrap)
        self.assertIn('HOLD_PLUGIN_SOURCE_PATH_MISMATCH', bootstrap)
        self.assertIn('status --porcelain=v1 --untracked-files=all', bootstrap)
        self.assertIn('find "$root" -type l', bootstrap)

    def test_plugin_release_metadata_is_exact(self):
        path = REPO / "plugins/keiyo-product-video/.codex-plugin/plugin.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual("1.0.0", payload["version"])
        self.assertEqual(
            ["Use $create-tiktok-product-video to prepare and validate a new TikTok product video payload."],
            payload["interface"]["defaultPrompt"],
        )


if __name__ == "__main__":
    unittest.main()
