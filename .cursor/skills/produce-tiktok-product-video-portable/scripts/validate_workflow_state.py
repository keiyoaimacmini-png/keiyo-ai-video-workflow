#!/usr/bin/env python3
"""Validate the forward-only product-video workflow state."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath


SCHEMA = "product_video_workflow_state.v1"
STAGES = [
    "PREFLIGHT",
    "SCRIPT_PREPARED",
    "SCRIPT_REVIEW",
    "ROUGH_EDIT",
    "ROUGH_REVIEW",
    "FINISHING",
    "FINAL_QA",
    "FINAL_REVIEW",
    "EXPORT_AND_DELIVERY",
    "COMPLETE",
]
ARTIFACTS = [
    "script_package",
    "production_payload",
    "execution_plan",
    "rough_edit",
    "finished_timeline",
    "final_qa",
    "export",
    "drive",
]
LEARNING_SNAPSHOTS = ["script", "edit", "delivery"]
APPROVALS = {
    "script": "台本OK",
    "rough_edit": "粗編集OK",
    "final_export": "完成・書き出しOK",
}
WORK_STAGES = [
    "PREFLIGHT",
    "SCRIPT_PREPARED",
    "ROUGH_EDIT",
    "FINISHING",
    "FINAL_QA",
    "EXPORT_AND_DELIVERY",
]
STAGE_ARTIFACT = {
    "PREFLIGHT": "script_package",
    "SCRIPT_PREPARED": "production_payload",
    "ROUGH_EDIT": "rough_edit",
    "FINISHING": "finished_timeline",
    "FINAL_QA": "final_qa",
    "EXPORT_AND_DELIVERY": "export",
}
APPROVAL_ARTIFACT = {
    "script": "production_payload",
    "rough_edit": "execution_plan",
    "final_export": "final_qa",
}
APPROVAL_LEARNING = {
    "script": "script",
    "rough_edit": "edit",
    "final_export": "delivery",
}
STAGE_LEARNING = {
    "PREFLIGHT": "script",
    "SCRIPT_PREPARED": "script",
    "ROUGH_EDIT": "edit",
    "FINISHING": "edit",
    "FINAL_QA": "edit",
    "EXPORT_AND_DELIVERY": "delivery",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MODEL = re.compile(r"^AN-[A-Z0-9]{4,6}$")


def initial_state(case_id: str, product_model: str, delivery_mode: str) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "case_id": case_id,
        "product_model": product_model,
        "stage": "PREFLIGHT",
        "delivery_mode": delivery_mode,
        "settings": None,
        "artifacts": {key: None for key in ARTIFACTS},
        "learning_snapshots": {key: None for key in LEARNING_SNAPSHOTS},
        "approvals": {
            key: {
                "status": "pending",
                "receipt": None,
                "bound_artifact_sha256": None,
                "bound_learning_snapshot_sha256": None,
            }
            for key in APPROVALS
        },
        "stage_receipts": [],
    }


def write_initial_state(output: Path, case_id: str, product_model: str, delivery_mode: str) -> None:
    if output.exists():
        fail(f"refusing to overwrite existing state: {output}")
    if not output.parent.is_dir():
        fail(f"state parent directory does not exist: {output.parent}")
    data = initial_state(case_id, product_model, delivery_mode)
    validate(data)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fail(message: str) -> None:
    raise ValueError(message)


def sha_or_none(value: object, label: str) -> None:
    if value is not None and (not isinstance(value, str) or not SHA256.fullmatch(value)):
        fail(f"{label} must be null or a lowercase SHA-256")


def artifact_record(value: object, label: str, artifact_root: Path | None) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        fail(f"{label} must contain exactly path and sha256")
    path_value = value["path"]
    if not isinstance(path_value, str) or not path_value or "\\" in path_value:
        fail(f"{label}.path must be a non-empty POSIX relative path")
    relative = PurePosixPath(path_value)
    if relative.is_absolute() or ".." in relative.parts or "." in relative.parts:
        fail(f"{label}.path must stay below the artifact root")
    sha_or_none(value["sha256"], f"{label}.sha256")
    if value["sha256"] is None:
        fail(f"{label}.sha256 cannot be null")
    if artifact_root is None:
        return
    root = artifact_root.resolve(strict=True)
    actual = (root / Path(*relative.parts)).resolve(strict=True)
    try:
        actual.relative_to(root)
    except ValueError:
        fail(f"{label}.path escapes the artifact root")
    if not actual.is_file():
        fail(f"{label}.path must resolve to a file")
    digest = hashlib.sha256(actual.read_bytes()).hexdigest()
    if digest != value["sha256"]:
        fail(f"{label}.sha256 does not match actual file bytes")


def parse_time(value: object, label: str) -> None:
    if not isinstance(value, str):
        fail(f"{label} must be an offset-aware timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        fail(f"{label} is not ISO-8601: {exc}")
    if parsed.tzinfo is None:
        fail(f"{label} must be offset-aware")


def validate(data: object, artifact_root: Path | None = None) -> None:
    if not isinstance(data, dict):
        fail("state must be a JSON object")
    expected = {
        "schema", "case_id", "product_model", "stage", "delivery_mode",
        "settings", "artifacts", "learning_snapshots", "approvals", "stage_receipts",
    }
    if set(data) != expected:
        fail(f"top-level keys must be exactly {sorted(expected)}")
    if data["schema"] != SCHEMA:
        fail(f"schema must be {SCHEMA}")
    if not isinstance(data["case_id"], str) or not data["case_id"].strip():
        fail("case_id must be a non-empty string")
    if not isinstance(data["product_model"], str) or not MODEL.fullmatch(data["product_model"]):
        fail("product_model must match ^AN-[A-Z0-9]{4,6}$")
    if data["stage"] not in STAGES:
        fail("unknown stage")
    stage_index = STAGES.index(data["stage"])
    if data["delivery_mode"] not in {"export_only", "drive"}:
        fail("delivery_mode must be export_only or drive")
    artifact_record(data["settings"], "settings", artifact_root)
    if stage_index > 0 and data["settings"] is None:
        fail("settings is required after PREFLIGHT")

    artifacts = data["artifacts"]
    if not isinstance(artifacts, dict) or set(artifacts) != set(ARTIFACTS):
        fail(f"artifacts keys must be exactly {ARTIFACTS}")
    for key in ARTIFACTS:
        artifact_record(artifacts[key], f"artifacts.{key}", artifact_root)

    learning_snapshots = data["learning_snapshots"]
    if not isinstance(learning_snapshots, dict) or set(learning_snapshots) != set(LEARNING_SNAPSHOTS):
        fail(f"learning_snapshots keys must be exactly {LEARNING_SNAPSHOTS}")
    for key in LEARNING_SNAPSHOTS:
        artifact_record(learning_snapshots[key], f"learning_snapshots.{key}", artifact_root)
    required_learning = {1: "script", 4: "edit", 7: "delivery"}
    for threshold, key in required_learning.items():
        if stage_index >= threshold and learning_snapshots[key] is None:
            fail(f"learning_snapshots.{key} is required at stage {data['stage']}")

    required_artifacts = {
        1: ["script_package"],
        2: ["production_payload"],
        4: ["execution_plan", "rough_edit"],
        6: ["finished_timeline"],
        7: ["final_qa"],
        9: ["export"],
    }
    for threshold, keys in required_artifacts.items():
        if stage_index >= threshold:
            for key in keys:
                if artifacts[key] is None:
                    fail(f"artifacts.{key} is required at stage {data['stage']}")
    if data["delivery_mode"] == "export_only" and artifacts["drive"] is not None:
        fail("artifacts.drive must be null for export_only")
    if data["stage"] == "COMPLETE" and data["delivery_mode"] == "drive" and artifacts["drive"] is None:
        fail("artifacts.drive is required for drive completion")

    approvals = data["approvals"]
    if not isinstance(approvals, dict) or set(approvals) != set(APPROVALS):
        fail(f"approvals keys must be exactly {list(APPROVALS)}")
    approval_thresholds = {"script": 3, "rough_edit": 5, "final_export": 8}
    for key, receipt_text in APPROVALS.items():
        record = approvals[key]
        if not isinstance(record, dict) or set(record) != {"status", "receipt", "bound_artifact_sha256", "bound_learning_snapshot_sha256"}:
            fail(f"approvals.{key} has invalid keys")
        should_be_approved = stage_index >= approval_thresholds[key]
        expected_status = "approved" if should_be_approved else "pending"
        if record["status"] != expected_status:
            fail(f"approvals.{key}.status must be {expected_status} at {data['stage']}")
        if should_be_approved:
            if record["receipt"] != receipt_text:
                fail(f"approvals.{key}.receipt must be {receipt_text}")
            if not isinstance(record["bound_artifact_sha256"], str) or not SHA256.fullmatch(record["bound_artifact_sha256"]):
                fail(f"approvals.{key}.bound_artifact_sha256 must be a SHA-256")
            expected_binding = artifacts[APPROVAL_ARTIFACT[key]]["sha256"]
            if record["bound_artifact_sha256"] != expected_binding:
                fail(f"approvals.{key} must bind artifacts.{APPROVAL_ARTIFACT[key]}")
            expected_learning_binding = learning_snapshots[APPROVAL_LEARNING[key]]["sha256"]
            if record["bound_learning_snapshot_sha256"] != expected_learning_binding:
                fail(f"approvals.{key} must bind learning_snapshots.{APPROVAL_LEARNING[key]}")
        elif record["receipt"] is not None or record["bound_artifact_sha256"] is not None or record["bound_learning_snapshot_sha256"] is not None:
            fail(f"pending approvals.{key} must have null receipt and binding")

    receipts = data["stage_receipts"]
    if not isinstance(receipts, list):
        fail("stage_receipts must be an array")
    expected_completed = [stage for stage in WORK_STAGES if STAGES.index(stage) < stage_index]
    if len(receipts) != len(expected_completed):
        fail(f"stage_receipts must close over completed work stages {expected_completed}")
    seen = set()
    for index, (receipt, expected_stage) in enumerate(zip(receipts, expected_completed), start=1):
        if not isinstance(receipt, dict) or set(receipt) != {"sequence", "completed_stage", "artifact_sha256", "learning_snapshot_sha256", "observed_at"}:
            fail(f"stage_receipts[{index - 1}] has invalid keys")
        if receipt["sequence"] != index:
            fail("stage receipt sequence must be contiguous from 1")
        if receipt["completed_stage"] != expected_stage or expected_stage in seen:
            fail("stage receipts must be unique and in workflow order")
        seen.add(expected_stage)
        if not isinstance(receipt["artifact_sha256"], str) or not SHA256.fullmatch(receipt["artifact_sha256"]):
            fail("stage receipt artifact_sha256 must be a lowercase SHA-256")
        expected_artifact = artifacts[STAGE_ARTIFACT[expected_stage]]["sha256"]
        if receipt["artifact_sha256"] != expected_artifact:
            fail(f"stage receipt {expected_stage} must bind artifacts.{STAGE_ARTIFACT[expected_stage]}")
        expected_learning = learning_snapshots[STAGE_LEARNING[expected_stage]]["sha256"]
        if receipt["learning_snapshot_sha256"] != expected_learning:
            fail(f"stage receipt {expected_stage} must bind learning_snapshots.{STAGE_LEARNING[expected_stage]}")
        parse_time(receipt["observed_at"], "stage receipt observed_at")


def self_test() -> None:
    zero = "0" * 64
    base = initial_state("AN-S182-example-001", "AN-S182", "export_only")
    validate(base)
    with tempfile.TemporaryDirectory(prefix="product-video-workflow-") as temp:
        output = Path(temp) / "state.json"
        write_initial_state(output, "AN-S182-example-001", "AN-S182", "export_only")
        validate(json.loads(output.read_text(encoding="utf-8")))
        try:
            write_initial_state(output, "AN-S182-example-001", "AN-S182", "export_only")
        except ValueError:
            pass
        else:
            fail("self-test failed to reject state overwrite")
    broken = json.loads(json.dumps(base, ensure_ascii=False))
    broken["stage"] = "ROUGH_EDIT"
    try:
        validate(broken)
    except ValueError:
        pass
    else:
        fail("self-test failed to reject a skipped workflow")
    complete = json.loads(json.dumps(base, ensure_ascii=False))
    complete.update({"stage": "COMPLETE", "settings": {"path": "config/settings.json", "sha256": zero}})
    complete["artifacts"].update({
        key: {"path": f"receipts/{key}.json", "sha256": f"{index:064x}"}
        for index, key in enumerate(ARTIFACTS, start=1) if key != "drive"
    })
    complete["learning_snapshots"] = {
        key: {"path": f"learning/{key}.md", "sha256": f"{index + 20:064x}"}
        for index, key in enumerate(LEARNING_SNAPSHOTS, start=1)
    }
    complete["approvals"] = {
        key: {
            "status": "approved",
            "receipt": receipt,
            "bound_artifact_sha256": complete["artifacts"][APPROVAL_ARTIFACT[key]]["sha256"],
            "bound_learning_snapshot_sha256": complete["learning_snapshots"][APPROVAL_LEARNING[key]]["sha256"],
        }
        for key, receipt in APPROVALS.items()
    }
    complete["stage_receipts"] = [
        {
            "sequence": i,
            "completed_stage": stage,
            "artifact_sha256": complete["artifacts"][STAGE_ARTIFACT[stage]]["sha256"],
            "learning_snapshot_sha256": complete["learning_snapshots"][STAGE_LEARNING[stage]]["sha256"],
            "observed_at": "2026-08-30T12:00:00+09:00",
        }
        for i, stage in enumerate(WORK_STAGES, start=1)
    ]
    validate(complete)
    wrong_binding = json.loads(json.dumps(complete, ensure_ascii=False))
    wrong_binding["approvals"]["rough_edit"]["bound_artifact_sha256"] = zero
    try:
        validate(wrong_binding)
    except ValueError:
        pass
    else:
        fail("self-test failed to reject a wrong approval binding")
    wrong_learning = json.loads(json.dumps(complete, ensure_ascii=False))
    wrong_learning["stage_receipts"][0]["learning_snapshot_sha256"] = zero
    try:
        validate(wrong_learning)
    except ValueError:
        pass
    else:
        fail("self-test failed to reject a wrong learning snapshot binding")
    wrong_approval_learning = json.loads(json.dumps(complete, ensure_ascii=False))
    wrong_approval_learning["approvals"]["final_export"]["bound_learning_snapshot_sha256"] = zero
    try:
        validate(wrong_approval_learning)
    except ValueError:
        pass
    else:
        fail("self-test failed to reject a wrong approval learning binding")

    with tempfile.TemporaryDirectory(prefix="product-video-workflow-e2e-") as temp:
        root = Path(temp) / "case"
        (root / "config").mkdir(parents=True)
        (root / "receipts").mkdir()
        (root / "learning").mkdir()

        def write_record(relative: str, content: str) -> dict[str, str]:
            target = root / relative
            target.write_text(content, encoding="utf-8")
            return {"path": relative, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}

        actual_settings = write_record("config/settings.json", '{"model":"AN-S182"}\n')
        actual_artifacts = {
            key: write_record(f"receipts/{key}.json", json.dumps({"artifact": key}) + "\n")
            for key in ARTIFACTS
        }
        actual_learning = {
            key: write_record(f"learning/{key}.md", f"# {key} learning\n")
            for key in LEARNING_SNAPSHOTS
        }
        artifact_thresholds = {
            "script_package": 1,
            "production_payload": 2,
            "execution_plan": 4,
            "rough_edit": 4,
            "finished_timeline": 6,
            "final_qa": 7,
            "export": 9,
        }
        learning_thresholds = {"script": 1, "edit": 4, "delivery": 7}
        approval_thresholds = {"script": 3, "rough_edit": 5, "final_export": 8}
        actual_complete: dict[str, object] | None = None

        for stage_index, stage in enumerate(STAGES):
            state = initial_state("AN-S182-actual-e2e", "AN-S182", "export_only")
            state["stage"] = stage
            if stage_index > 0:
                state["settings"] = actual_settings
            for key, threshold in artifact_thresholds.items():
                if stage_index >= threshold:
                    state["artifacts"][key] = actual_artifacts[key]
            for key, threshold in learning_thresholds.items():
                if stage_index >= threshold:
                    state["learning_snapshots"][key] = actual_learning[key]
            for key, threshold in approval_thresholds.items():
                if stage_index >= threshold:
                    state["approvals"][key] = {
                        "status": "approved",
                        "receipt": APPROVALS[key],
                        "bound_artifact_sha256": state["artifacts"][APPROVAL_ARTIFACT[key]]["sha256"],
                        "bound_learning_snapshot_sha256": state["learning_snapshots"][APPROVAL_LEARNING[key]]["sha256"],
                    }
            completed = [item for item in WORK_STAGES if STAGES.index(item) < stage_index]
            state["stage_receipts"] = [
                {
                    "sequence": sequence,
                    "completed_stage": completed_stage,
                    "artifact_sha256": state["artifacts"][STAGE_ARTIFACT[completed_stage]]["sha256"],
                    "learning_snapshot_sha256": state["learning_snapshots"][STAGE_LEARNING[completed_stage]]["sha256"],
                    "observed_at": "2026-08-31T12:00:00+09:00",
                }
                for sequence, completed_stage in enumerate(completed, start=1)
            ]
            validate(state, root)
            if stage == "COMPLETE":
                actual_complete = state

        assert actual_complete is not None
        drive_complete = json.loads(json.dumps(actual_complete, ensure_ascii=False))
        drive_complete["delivery_mode"] = "drive"
        drive_complete["artifacts"]["drive"] = actual_artifacts["drive"]
        validate(drive_complete, root)
        missing_drive = json.loads(json.dumps(drive_complete, ensure_ascii=False))
        missing_drive["artifacts"]["drive"] = None
        try:
            validate(missing_drive, root)
        except ValueError as exc:
            if "artifacts.drive is required" not in str(exc):
                raise
        else:
            fail("self-test failed to require Drive evidence for drive completion")

        final_path = root / actual_complete["artifacts"]["final_qa"]["path"]
        final_bytes = final_path.read_bytes()
        final_path.write_text("tampered\n", encoding="utf-8")
        try:
            validate(actual_complete, root)
        except ValueError as exc:
            if "does not match actual file bytes" not in str(exc):
                raise
        else:
            fail("self-test failed to reject an actual artifact byte mismatch")
        final_path.write_bytes(final_bytes)

        outside = Path(temp) / "outside.json"
        outside.write_text('{"outside":true}\n', encoding="utf-8")
        escape = root / "receipts" / "escape.json"
        escape.symlink_to(outside)
        escaped_state = json.loads(json.dumps(actual_complete, ensure_ascii=False))
        escaped_state["artifacts"]["script_package"] = {
            "path": "receipts/escape.json",
            "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
        }
        try:
            validate(escaped_state, root)
        except ValueError as exc:
            if "escapes the artifact root" not in str(exc):
                raise
        else:
            fail("self-test failed to reject a symlink escape")

    print("PASS validate_workflow_state self-test (10 actual-file stages, export and Drive completion)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("state", nargs="?", type=Path)
    parser.add_argument("--init-state", type=Path)
    parser.add_argument("--case-id")
    parser.add_argument("--product-model")
    parser.add_argument("--delivery-mode", choices=["export_only", "drive"])
    parser.add_argument("--expect-stage", choices=STAGES)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
            return 0
        if args.init_state is not None:
            if args.state is not None or args.expect_stage or args.artifact_root:
                parser.error("--init-state cannot be combined with validation arguments")
            if args.case_id is None or args.product_model is None or args.delivery_mode is None:
                parser.error("--init-state requires --case-id, --product-model, and --delivery-mode")
            write_initial_state(args.init_state, args.case_id, args.product_model, args.delivery_mode)
            print(f"INITIALIZED workflow-state stage=PREFLIGHT path={args.init_state}")
            return 0
        if args.state is None:
            parser.error("state is required unless --self-test is used")
        data = json.loads(args.state.read_text(encoding="utf-8"))
        validate(data, args.artifact_root)
        if args.expect_stage and data["stage"] != args.expect_stage:
            fail(f"expected stage {args.expect_stage}, got {data['stage']}")
        print(f"VALID workflow-state stage={data['stage']}")
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"INVALID workflow-state: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
