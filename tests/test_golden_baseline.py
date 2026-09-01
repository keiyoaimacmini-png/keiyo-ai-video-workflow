from __future__ import annotations

import importlib.util
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("verify_golden_baseline", REPO / "scripts/verify_golden_baseline.py")
VERIFY = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(VERIFY)
BUILDER_SPEC = importlib.util.spec_from_file_location(
    "build_capcut_golden_baseline",
    REPO / "scripts/build_capcut_golden_baseline.py",
)
BUILDER = importlib.util.module_from_spec(BUILDER_SPEC)
assert BUILDER_SPEC.loader is not None
BUILDER_SPEC.loader.exec_module(BUILDER)


class GoldenBaselineTests(unittest.TestCase):
    def copy_baseline(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temp = tempfile.TemporaryDirectory()
        target = Path(temp.name) / "baseline"
        shutil.copytree(VERIFY.DEFAULT_ROOT, target)
        return temp, target

    def refresh_evidence(self, target: Path) -> None:
        names = sorted(VERIFY.REQUIRED_FILES - {"EVIDENCE.sha256"})
        lines = []
        for name in names:
            digest = hashlib.sha256((target / name).read_bytes()).hexdigest()
            lines.append(f"{digest}  {name}")
        (target / "EVIDENCE.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_current_baseline_passes_with_documented_holds(self):
        self.assertEqual([], VERIFY.verify(VERIFY.DEFAULT_ROOT))

    def test_caption_change_is_rejected(self):
        temp, target = self.copy_baseline()
        try:
            path = target / "caption-style.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["captions"][9]["text"] = "変更"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            errors = VERIFY.verify(target)
            self.assertTrue(any("caption mismatch: C10" in error for error in errors))
            self.assertTrue(any("evidence hash mismatch" in error for error in errors))
        finally:
            temp.cleanup()

    def test_missing_material_hold_is_not_silently_cleared(self):
        temp, target = self.copy_baseline()
        try:
            path = target / "material-map.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["materials"][3]["assets"][0]["reproduction_source_status"] = "verified"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            errors = VERIFY.verify(target)
            self.assertTrue(any("material receipt mismatch: C4" in error for error in errors))
        finally:
            temp.cleanup()

    def test_absolute_path_is_rejected(self):
        temp, target = self.copy_baseline()
        try:
            path = target / "baseline.manifest.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["bad"] = "/" + "Users" + "/example/private"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            errors = VERIFY.verify(target)
            self.assertTrue(any("non-portable or private value" in error for error in errors))
        finally:
            temp.cleanup()

    def test_media_file_is_rejected_by_exact_file_set(self):
        temp, target = self.copy_baseline()
        try:
            (target / "frame.jpg").write_bytes(b"not-an-image")
            self.assertTrue(any("baseline file set mismatch" in error for error in VERIFY.verify(target)))
        finally:
            temp.cleanup()

    def test_material_name_and_range_change_is_rejected_even_with_refreshed_evidence(self):
        temp, target = self.copy_baseline()
        try:
            path = target / "material-map.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            asset = payload["materials"][0]["assets"][0]
            asset["original_filename"] = "IMG_0001.MOV"
            asset["original_source_range_seconds"] = [0.0, 1.0]
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.refresh_evidence(target)
            self.assertTrue(any("material filename or range mismatch: C1" in error for error in VERIFY.verify(target)))
        finally:
            temp.cleanup()

    def test_empty_tts_is_rejected_even_when_declared_count_remains_ten(self):
        temp, target = self.copy_baseline()
        try:
            path = target / "audio-layout.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["tts"] = []
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.refresh_evidence(target)
            self.assertTrue(any("TTS row mapping or timing mismatch" in error for error in VERIFY.verify(target)))
        finally:
            temp.cleanup()

    def test_acceptance_fps_change_is_rejected_even_with_refreshed_evidence(self):
        temp, target = self.copy_baseline()
        try:
            path = target / "acceptance.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["exact_checks"]["fps"] = 25
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.refresh_evidence(target)
            self.assertTrue(any("acceptance canonical HOLD payload mismatch" in error for error in VERIFY.verify(target)))
        finally:
            temp.cleanup()

    def test_font_size_change_is_rejected_even_with_refreshed_evidence(self):
        temp, target = self.copy_baseline()
        try:
            path = target / "caption-style.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["captions"][0]["font_size"] = 1
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.refresh_evidence(target)
            self.assertTrue(any("caption visual style mismatch: C1" in error for error in VERIFY.verify(target)))
        finally:
            temp.cleanup()

    def test_every_material_semantic_field_is_rejected_after_evidence_refresh(self):
        mutations = [
            (0, "purpose", "別の目的"),
            (1, "must_show", ["別の必須条件"]),
            (2, "must_not_show", ["別の禁止条件"]),
            (3, "review_flags", None),
            (9, "review_flags", ["別の確認事項"]),
        ]
        for index, field, value in mutations:
            with self.subTest(cut=index + 1, field=field):
                temp, target = self.copy_baseline()
                try:
                    path = target / "material-map.json"
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    payload["materials"][index][field] = value
                    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    self.refresh_evidence(target)
                    self.assertTrue(any(
                        "material semantic declarations mismatch" in error
                        for error in VERIFY.verify(target)
                    ))
                finally:
                    temp.cleanup()

    def test_timeline_top_level_change_is_rejected_after_evidence_refresh(self):
        temp, target = self.copy_baseline()
        try:
            path = target / "timeline.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["physical_video_segment_count"] = 11
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.refresh_evidence(target)
            self.assertTrue(any(
                "timeline top-level declarations mismatch" in error
                for error in VERIFY.verify(target)
            ))
        finally:
            temp.cleanup()

    def test_caption_top_level_change_is_rejected_after_evidence_refresh(self):
        temp, target = self.copy_baseline()
        try:
            path = target / "caption-style.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["semantic_placement"] = "center"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.refresh_evidence(target)
            self.assertTrue(any(
                "caption top-level declarations mismatch" in error
                for error in VERIFY.verify(target)
            ))
        finally:
            temp.cleanup()

    def test_environment_identity_change_is_rejected_after_evidence_refresh(self):
        mutations = [
            ("captured_source_environment", "font_file", "fallback.ttf"),
            ("captured_source_environment", "tts_voice_speaker", "other-speaker"),
            ("windows_policy", "missing_tts_voice", "silently substitute"),
        ]
        for section, field, value in mutations:
            with self.subTest(section=section, field=field):
                temp, target = self.copy_baseline()
                try:
                    path = target / "environment.json"
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    payload[section][field] = value
                    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    self.refresh_evidence(target)
                    self.assertTrue(any(
                        "environment identity or Windows policy mismatch" in error
                        for error in VERIFY.verify(target)
                    ))
                finally:
                    temp.cleanup()

    def test_export_receipt_fields_are_rejected_after_evidence_refresh(self):
        mutations = [
            ("source", "inferred"),
            ("unknown", []),
            ("current_capcut_ui_readback", "verified"),
            ("policy", "export without readback"),
        ]
        for field, value in mutations:
            with self.subTest(field=field):
                temp, target = self.copy_baseline()
                try:
                    path = target / "export-settings.json"
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    payload[field] = value
                    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    self.refresh_evidence(target)
                    self.assertTrue(any(
                        "export source, target, unknown, readback, or policy mismatch" in error
                        for error in VERIFY.verify(target)
                    ))
                finally:
                    temp.cleanup()

    def test_full_acceptance_hold_payload_is_rejected_after_evidence_refresh(self):
        mutations = [
            ("hold_detail", None),
            ("hold_order", None),
            ("decision", "accepted"),
            ("external_effects_authorized", True),
        ]
        for mutation, _ in mutations:
            with self.subTest(mutation=mutation):
                temp, target = self.copy_baseline()
                try:
                    path = target / "acceptance.json"
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    if mutation == "hold_detail":
                        payload["holds"][0]["detail"] = "changed"
                    elif mutation == "hold_order":
                        payload["holds"][0], payload["holds"][1] = payload["holds"][1], payload["holds"][0]
                    elif mutation == "decision":
                        payload["decision"] = "accepted"
                    else:
                        payload["external_effects_authorized"] = True
                    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    self.refresh_evidence(target)
                    self.assertTrue(any(
                        "acceptance canonical HOLD payload mismatch" in error
                        for error in VERIFY.verify(target)
                    ))
                finally:
                    temp.cleanup()

    def test_manifest_receipt_changes_are_rejected_by_canonical_hash_after_evidence_refresh(self):
        mutations = [
            ("status", "accepted"),
            ("draft_info_sha256", "0" * 64),
            ("source_project_modified", True),
        ]
        for field, value in mutations:
            with self.subTest(field=field):
                temp, target = self.copy_baseline()
                try:
                    path = target / "baseline.manifest.json"
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    if field == "status":
                        payload[field] = value
                    else:
                        payload["source_receipt"][field] = value
                    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    self.refresh_evidence(target)
                    self.assertIn(
                        "canonical JSON hash mismatch: baseline.manifest.json",
                        VERIFY.verify(target),
                    )
                finally:
                    temp.cleanup()

    def test_timeline_segment_fields_are_rejected_by_canonical_hash_after_evidence_refresh(self):
        mutations = [
            ("scale", {"x": 1.1, "y": 1.0}),
            ("target_start_seconds", 0.1),
        ]
        for field, value in mutations:
            with self.subTest(field=field):
                temp, target = self.copy_baseline()
                try:
                    path = target / "timeline.json"
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    payload["cuts"][0]["physical_segments"][0][field] = value
                    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    self.refresh_evidence(target)
                    self.assertIn("canonical JSON hash mismatch: timeline.json", VERIFY.verify(target))
                finally:
                    temp.cleanup()

    def test_audio_fields_are_rejected_by_canonical_hash_after_evidence_refresh(self):
        mutations = [
            ("source_audio_policy", "audible"),
            ("tts_voice", "other-speaker"),
            ("sfx_resource", "changed-resource"),
        ]
        for field, value in mutations:
            with self.subTest(field=field):
                temp, target = self.copy_baseline()
                try:
                    path = target / "audio-layout.json"
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    if field == "source_audio_policy":
                        payload[field] = value
                    elif field == "tts_voice":
                        payload["tts"][0]["voice_speaker"] = value
                    else:
                        payload["sfx"][0]["resource_id"] = value
                    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    self.refresh_evidence(target)
                    self.assertIn("canonical JSON hash mismatch: audio-layout.json", VERIFY.verify(target))
                finally:
                    temp.cleanup()

    def test_material_receipts_are_rejected_by_canonical_hash_after_evidence_refresh(self):
        mutations = [
            ("asset_id", "A999"),
            ("sidecar_json_sha256", "0" * 64),
        ]
        for field, value in mutations:
            with self.subTest(field=field):
                temp, target = self.copy_baseline()
                try:
                    path = target / "material-map.json"
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    payload["materials"][0]["assets"][0][field] = value
                    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    self.refresh_evidence(target)
                    self.assertIn("canonical JSON hash mismatch: material-map.json", VERIFY.verify(target))
                finally:
                    temp.cleanup()

    def test_caption_seconds_are_rejected_by_canonical_hash_after_evidence_refresh(self):
        temp, target = self.copy_baseline()
        try:
            path = target / "caption-style.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["captions"][0]["target_duration_seconds"] = 1.9
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.refresh_evidence(target)
            self.assertIn("canonical JSON hash mismatch: caption-style.json", VERIFY.verify(target))
        finally:
            temp.cleanup()

    def test_source_selector_uses_exact_full_slowed_derivative_range(self):
        selector = BUILDER.source_selector(
            "##_draftpath_placeholder_x_##/Resources/C6_IMG_3893_0-2.833_slow3s.mp4",
            0,
            3_000_000,
            3_000_000,
        )
        self.assertEqual("IMG_3893.MOV", selector["original_filename"])
        self.assertEqual([0.0, 2.833], selector["original_source_range_seconds"])

    def test_source_selector_uses_exact_range_for_small_container_rounding(self):
        selector = BUILDER.source_selector(
            "##_draftpath_placeholder_x_##/Resources/C4A_IMG_3958_0-2.mp4",
            0,
            2_000_000,
            2_002_000,
        )
        self.assertEqual([0.0, 2.0], selector["original_source_range_seconds"])


if __name__ == "__main__":
    unittest.main()
