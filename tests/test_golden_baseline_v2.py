from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "verify_golden_baseline_v2",
    REPO / "scripts/verify_golden_baseline_v2.py",
)
VERIFY = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(VERIFY)


class GoldenBaselineV2Tests(unittest.TestCase):
    def copy_baseline(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temp = tempfile.TemporaryDirectory()
        target = Path(temp.name) / "baseline"
        shutil.copytree(VERIFY.DEFAULT_ROOT, target)
        return temp, target

    def refresh_evidence(self, target: Path) -> None:
        names = sorted(VERIFY.REQUIRED_FILES - {"EVIDENCE.sha256"})
        lines = [
            f"{hashlib.sha256((target / name).read_bytes()).hexdigest()}  {name}"
            for name in names
        ]
        (target / "EVIDENCE.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_current_v2_passes_with_documented_holds(self):
        self.assertEqual([], VERIFY.verify(VERIFY.DEFAULT_ROOT))

    def test_current_draft_receipt_matches(self):
        value = os.environ.get("AN_S182_DRAFT_INFO")
        if not value:
            self.skipTest("AN_S182_DRAFT_INFO is not set on this platform")
        draft = Path(value)
        self.assertEqual([], VERIFY.verify(VERIFY.DEFAULT_ROOT, draft))

    def test_c4_reversion_is_rejected_even_after_evidence_refresh(self):
        temp, target = self.copy_baseline()
        try:
            path = target / "material-map.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["materials"][3]["assets"][0]["original_filename"] = "IMG_3957.MOV"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.refresh_evidence(target)
            errors = VERIFY.verify(target)
            self.assertIn("canonical JSON hash mismatch: material-map.json", errors)
            self.assertIn("material mapping mismatch: C4", errors)
        finally:
            temp.cleanup()

    def test_c6_range_change_is_rejected_even_after_evidence_refresh(self):
        temp, target = self.copy_baseline()
        try:
            path = target / "timeline.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["cuts"][5]["physical_segments"][0]["source_range_seconds"] = [0.0, 3.0]
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.refresh_evidence(target)
            errors = VERIFY.verify(target)
            self.assertIn("canonical JSON hash mismatch: timeline.json", errors)
            self.assertIn("material mapping mismatch: C6", errors)
        finally:
            temp.cleanup()

    def test_absolute_path_is_rejected(self):
        temp, target = self.copy_baseline()
        try:
            path = target / "acceptance.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["private"] = "/" + "Users" + "/example/private"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.refresh_evidence(target)
            self.assertTrue(any("non-portable or private value" in error for error in VERIFY.verify(target)))
        finally:
            temp.cleanup()

    def test_media_file_is_rejected(self):
        temp, target = self.copy_baseline()
        try:
            (target / "clip.mp4").write_bytes(b"not media")
            self.assertIn("baseline file set mismatch", VERIFY.verify(target))
        finally:
            temp.cleanup()

    def test_acceptance_hold_change_is_rejected_after_evidence_refresh(self):
        temp, target = self.copy_baseline()
        try:
            path = target / "acceptance.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["holds"] = []
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.refresh_evidence(target)
            errors = VERIFY.verify(target)
            self.assertIn("canonical JSON hash mismatch: acceptance.json", errors)
            self.assertIn("acceptance holds mismatch", errors)
        finally:
            temp.cleanup()


if __name__ == "__main__":
    unittest.main()
