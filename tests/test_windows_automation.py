from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
VERIFY_SCRIPT = REPO / "scripts/verify-windows.ps1"
BOOTSTRAP_SCRIPT = REPO / "scripts/bootstrap.ps1"
WORKFLOW = REPO / ".github/workflows/windows-verify.yml"
README = REPO / "README.md"
GITATTRIBUTES = REPO / ".gitattributes"


class WindowsAutomationContractTests(unittest.TestCase):
    def test_powershell_entrypoints_exist(self):
        self.assertTrue(VERIFY_SCRIPT.is_file())
        self.assertTrue(BOOTSTRAP_SCRIPT.is_file())

    def test_verify_script_has_fail_closed_contract(self):
        text = VERIFY_SCRIPT.read_text(encoding="utf-8")
        lowered = text.casefold()

        self.assertRegex(text, r"(?i)param\s*\(")
        self.assertRegex(text, r"(?i)\[string\]\s*\$ReportPath")
        for required in (
            "hold_windows_required",
            "hold_powershell_7_required",
            "hold_python_3_12_required",
            "-3.12",
            "verify_package.py",
            "verify_golden_baseline_v2.py",
            "validate_product_video_payload.py",
            "--self-test",
            "unittest",
            "discover",
            "--porcelain=v1",
            "--untracked-files=all",
            "__pycache__",
            ".pyc",
            "convertto-json",
        ):
            self.assertIn(required, lowered)

        for forbidden in (
            "git reset",
            "git clean",
            "git checkout",
            "git commit",
            "git push",
        ):
            self.assertNotIn(forbidden, lowered)

    def test_bootstrap_keeps_authentication_user_owned(self):
        text = BOOTSTRAP_SCRIPT.read_text(encoding="utf-8")
        lowered = text.casefold()
        self.assertIn("gh auth status", lowered)
        self.assertNotIn("--with-token", lowered)
        self.assertNotIn("github_token", lowered)
        self.assertNotIn("gh_token", lowered)
        self.assertIn("verify-windows.ps1", lowered)
        self.assertRegex(text, r"(?i)\[Parameter\(Mandatory\)\]\[string\]\$ExpectedCommit")
        self.assertIn(
            "@('plugin', 'marketplace', 'add', $expectedRepo, '--ref', $resolvedCommit)",
            text,
        )

    def test_git_normalizes_distribution_text_to_lf(self):
        self.assertEqual("* text=auto eol=lf\n", GITATTRIBUTES.read_text(encoding="utf-8"))

    def test_workflow_is_windows_python_312_and_report_only(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        lowered = text.casefold()
        self.assertIn("runs-on: windows-latest", lowered)
        self.assertIn('python-version: "3.12"', lowered)
        self.assertIn("shell: pwsh", lowered)
        self.assertIn("verify-windows.ps1", lowered)
        self.assertIn("-reportpath", lowered)
        self.assertIn("${{ runner.temp }}", lowered)
        self.assertIn("convertfrom-json", lowered)
        self.assertIn("keiyo.windows-verification.v1", lowered)
        self.assertIn("windows_required", lowered)
        self.assertIn("powershell_7_required", lowered)
        self.assertIn("status --porcelain=v1 --untracked-files=all", lowered)
        self.assertIn("__pycache__", lowered)
        self.assertIn("*.pyc", lowered)
        self.assertEqual(1, lowered.count("actions/upload-artifact@"))
        self.assertRegex(
            lowered,
            r"path:\s*\$\{\{\s*runner\.temp\s*\}\}\\windows-verification-report\.json",
        )
        self.assertNotIn("bootstrap.ps1", lowered)

    def test_readme_documents_user_owned_auth_and_scope_boundaries(self):
        text = README.read_text(encoding="utf-8")
        self.assertIn("Windows 11での1コマンド導入", text)
        self.assertIn("ユーザー本人", text)
        self.assertIn("bootstrap.ps1", text)
        self.assertIn("-ExpectedCommit", text)
        self.assertIn("verify-windows.ps1", text)
        for boundary in ("Google Drive", "CapCut", "公開", "課金", "外部送信"):
            self.assertIn(boundary, text)

    def test_powershell_files_parse_when_pwsh_is_available(self):
        pwsh = shutil.which("pwsh")
        if pwsh is None:
            self.skipTest("pwsh is not installed on this platform")

        for path in (VERIFY_SCRIPT, BOOTSTRAP_SCRIPT):
            command = (
                "$tokens=$null; $errors=$null; "
                "[System.Management.Automation.Language.Parser]::ParseFile("
                "$env:KEIYO_PS_PARSE_PATH,[ref]$tokens,[ref]$errors) > $null; "
                "if ($errors.Count -ne 0) { $errors | ForEach-Object { "
                "[Console]::Error.WriteLine($_.Message) }; exit 1 }"
            )
            environment = os.environ.copy()
            environment["KEIYO_PS_PARSE_PATH"] = str(path)
            completed = subprocess.run(
                [pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
                cwd=REPO,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)


if __name__ == "__main__":
    unittest.main()
