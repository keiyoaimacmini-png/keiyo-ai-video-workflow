#!/usr/bin/env python3
"""Purge task-owned local working media after COMPLETE and verified storage."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Any


STATE_SCHEMA = "product_video_workflow_state.v1"
DESTINATION_SCHEMA = "product_video_destination_stored_receipt.v1"
PURGE_RECEIPT_SCHEMA = "product_video_local_working_media_purge_receipt.v1"
MEDIA_SUFFIXES = {
    ".mp4",
    ".mov",
    ".m4v",
    ".avi",
    ".webm",
    ".mkv",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".bmp",
    ".mp3",
    ".wav",
    ".ogg",
    ".m4a",
    ".aac",
    ".flac",
    ".aiff",
}
SHARED_RELATIVE_ROOTS = (
    "footage",
    "voice",
    ".runtime/product-video-inputs",
)
DESTINATION_KINDS = {"drive", "durable_store_readback"}
HOLD_NOT_DUE = "HOLD_POST_COMPLETE_PURGE_NOT_DUE"
HOLD_SOLE_COPY = "HOLD_LOCAL_WORKING_MEDIA_IS_SOLE_COPY"
HOLD_MAC = "HOLD_MAC_LOCAL_WORKING_MEDIA_PURGE_REQUIRED"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def posix_relative(root: Path, path: Path) -> str:
    return Path(os.path.relpath(path, root)).as_posix()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a JSON object")
    return data


def is_git_tracked(project_root: Path, path: Path) -> bool:
    try:
        relative = posix_relative(project_root, path)
    except ValueError:
        return False
    result = subprocess.run(
        ["git", "-C", str(project_root), "ls-files", "--error-unmatch", relative],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def contained_in(root: Path, path: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=True))
    except (OSError, ValueError):
        return False
    return True


def workflow_state_path(task_root: Path) -> Path:
    return task_root / "product-video-workflow-state.v1.json"


def bound_task_files(task_root: Path, state: dict[str, Any]) -> set[Path]:
    bound: set[Path] = {workflow_state_path(task_root).resolve(strict=False)}
    records: list[Any] = [state.get("settings")]
    artifacts = state.get("artifacts")
    if isinstance(artifacts, dict):
        records.extend(artifacts.values())
    snapshots = state.get("learning_snapshots")
    if isinstance(snapshots, dict):
        records.extend(snapshots.values())
    for record in records:
        if not isinstance(record, dict):
            continue
        relative = record.get("path")
        if not isinstance(relative, str) or not relative:
            continue
        posix = PurePosixPath(relative)
        if posix.is_absolute() or ".." in posix.parts:
            continue
        bound.add((task_root / Path(*posix.parts)).resolve(strict=False))
    return bound


def find_completed_filename(obj: object) -> str | None:
    if isinstance(obj, dict):
        value = obj.get("completed_video_filename")
        if isinstance(value, str) and value and "/" not in value and "\\" not in value and ".." not in value:
            suffix = Path(value).suffix.lower()
            if suffix in MEDIA_SUFFIXES:
                return value
        for child in obj.values():
            found = find_completed_filename(child)
            if found:
                return found
    elif isinstance(obj, list):
        for child in obj:
            found = find_completed_filename(child)
            if found:
                return found
    return None


def other_in_progress_cases(project_root: Path, case_id: str) -> list[str]:
    found: list[str] = []
    outputs = project_root / "outputs"
    if not outputs.is_dir():
        return found
    for state_file in sorted(outputs.glob("*/product-video-workflow-state.v1.json")):
        other_id = state_file.parent.name
        if other_id == case_id:
            continue
        try:
            if state_file.is_symlink():
                found.append(other_id)
                continue
            data = load_json(state_file)
            if data.get("stage") != "COMPLETE":
                found.append(other_id)
        except (OSError, json.JSONDecodeError, ValueError):
            found.append(other_id)
    return found


def validate_destination_receipt(data: dict[str, Any], case_id: str) -> list[str]:
    errors: list[str] = []
    if data.get("schema") != DESTINATION_SCHEMA:
        errors.append(f"schema must be {DESTINATION_SCHEMA}")
    if data.get("case_id") != case_id:
        errors.append("destination receipt case_id mismatch")
    filename = data.get("completed_video_filename")
    if not isinstance(filename, str) or not filename or "/" in filename or "\\" in filename:
        errors.append("completed_video_filename must be a basename")
    digest = data.get("completed_video_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or digest != digest.lower() or any(ch not in "0123456789abcdef" for ch in digest):
        errors.append("completed_video_sha256 must be a lowercase SHA-256")
    if data.get("destination_kind") not in DESTINATION_KINDS:
        errors.append("destination_kind must be drive or durable_store_readback")
    if data.get("local_working_copies_are_not_the_destination") is not True:
        errors.append("local working copies must not be the destination")
    return errors


def destination_gate(
    state: dict[str, Any],
    case_id: str,
    destination_receipt: dict[str, Any] | None,
) -> str | None:
    if state.get("schema") != STATE_SCHEMA:
        return HOLD_NOT_DUE
    if state.get("case_id") != case_id:
        return HOLD_NOT_DUE
    if state.get("stage") != "COMPLETE":
        return HOLD_NOT_DUE
    approvals = state.get("approvals")
    if not isinstance(approvals, dict):
        return HOLD_NOT_DUE
    final_export = approvals.get("final_export")
    if not isinstance(final_export, dict) or final_export.get("status") != "approved" or final_export.get("receipt") != "完成・書き出しOK":
        return HOLD_NOT_DUE
    artifacts = state.get("artifacts")
    if not isinstance(artifacts, dict) or not isinstance(artifacts.get("export"), dict):
        return HOLD_SOLE_COPY
    mode = state.get("delivery_mode")
    if mode == "drive":
        if not isinstance(artifacts.get("drive"), dict):
            return HOLD_SOLE_COPY
        return None
    if mode != "export_only":
        return HOLD_NOT_DUE
    if destination_receipt is None:
        return HOLD_SOLE_COPY
    if validate_destination_receipt(destination_receipt, case_id):
        return HOLD_SOLE_COPY
    return None


def collect_candidates(
    project_root: Path,
    task_root: Path,
    case_id: str,
    completed_filename: str | None,
    home_downloads: Path,
    skip_shared: bool,
    bound: set[Path],
    expected_download_sha256: str | None,
) -> tuple[list[Path], list[dict[str, str]]]:
    candidates: list[Path] = []
    skipped: list[dict[str, str]] = []

    def consider(path: Path) -> None:
        if not path.exists() or path.is_symlink() or not path.is_file():
            return
        resolved = path.resolve(strict=False)
        if resolved in bound:
            label = posix_relative(project_root, path) if contained_in(project_root, path) else path.name
            skipped.append({"path": label, "reason": "bound_receipt"})
            return
        if path.suffix.lower() not in MEDIA_SUFFIXES:
            return
        if contained_in(project_root, path) and is_git_tracked(project_root, path):
            skipped.append({"path": posix_relative(project_root, path), "reason": "git_tracked"})
            return
        candidates.append(path)

    outputs_case = project_root / "outputs" / case_id
    if outputs_case.is_dir() and not outputs_case.is_symlink() and contained_in(project_root, outputs_case):
        for path in outputs_case.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            consider(path)

    out_dir = project_root / "out"
    if out_dir.is_dir() and not out_dir.is_symlink() and contained_in(project_root, out_dir):
        for path in out_dir.iterdir():
            if path.is_symlink() or not path.is_file():
                continue
            name = path.name
            if case_id in name or (completed_filename and name == completed_filename):
                consider(path)

    if skip_shared:
        for relative in SHARED_RELATIVE_ROOTS:
            skipped.append({"path": relative, "reason": "shared_in_use_by_in_progress_case"})
    else:
        for relative in SHARED_RELATIVE_ROOTS:
            root = project_root / Path(*PurePosixPath(relative).parts)
            if not root.exists() or root.is_symlink():
                continue
            if not contained_in(project_root, root):
                continue
            if root.is_file():
                consider(root)
                continue
            for path in root.rglob("*"):
                if path.is_symlink() or not path.is_file():
                    continue
                consider(path)

    if completed_filename:
        download = home_downloads / completed_filename
        if download.exists() and not download.is_symlink() and download.is_file():
            if download.suffix.lower() in MEDIA_SUFFIXES:
                if expected_download_sha256 and sha256_file(download) != expected_download_sha256:
                    skipped.append({"path": f"Downloads/{completed_filename}", "reason": "sha256_mismatch"})
                else:
                    consider(download)

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique, skipped


def next_receipt_path(task_root: Path) -> Path:
    primary = task_root / "local-working-media-purge-receipt.v1.json"
    if not primary.exists() and not primary.is_symlink():
        return primary
    index = 1
    while True:
        candidate = task_root / f"local-working-media-purge-receipt-r{index:02d}.v1.json"
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
        index += 1


def host_kind() -> str:
    return "darwin" if sys.platform == "darwin" else "other"


def mac_checklist(case_id: str, completed_filename: str | None, skip_shared: bool) -> list[str]:
    items = [f"outputs/{case_id}/ (media files only)"]
    if completed_filename:
        items.append(f"out/{completed_filename}")
        items.append(f"Downloads/{completed_filename}")
    else:
        items.append(f"out/ files whose names contain {case_id}")
    if not skip_shared:
        items.extend(list(SHARED_RELATIVE_ROOTS))
    return items


def result_payload(
    case_id: str,
    mode: str,
    hold: str | None,
    deleted: list[dict[str, Any]],
    planned: list[dict[str, Any]],
    skipped: list[dict[str, str]],
    completed_filename: str | None,
    skip_shared: bool,
    receipt_path: str | None,
) -> dict[str, Any]:
    kind = host_kind()
    mac_status = "not_applicable_dry_run"
    if mode == "execute" and hold is None:
        mac_status = "completed_on_this_host" if kind == "darwin" else HOLD_MAC
    return {
        "schema": PURGE_RECEIPT_SCHEMA,
        "case_id": case_id,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "host_kind": kind,
        "mode": mode,
        "hold": hold,
        "completed_video_filename": completed_filename,
        "planned": planned,
        "deleted": deleted,
        "skipped": skipped,
        "mac_relative_checklist": mac_checklist(case_id, completed_filename, skip_shared),
        "mac_purge": mac_status,
        "receipt_path": receipt_path,
    }


def plan_entries(project_root: Path, paths: list[Path]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in paths:
        if contained_in(project_root, path):
            location = posix_relative(project_root, path)
            area = "project"
        else:
            location = f"Downloads/{path.name}"
            area = "home_downloads"
        entries.append(
            {
                "path": location,
                "area": area,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return entries


def load_destination_receipt(path: Path | None, task_root: Path) -> dict[str, Any] | None:
    candidates = []
    if path is not None:
        candidates.append(path)
    else:
        candidates.append(task_root / "destination-stored-receipt.v1.json")
    for candidate in candidates:
        if candidate.exists() and not candidate.is_symlink() and candidate.is_file():
            return load_json(candidate)
    return None


def run_purge(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    project_root = args.project_root.resolve(strict=True)
    task_root = args.task_root.resolve(strict=True)
    if not contained_in(project_root, task_root):
        raise ValueError("task root must stay under project root")
    if task_root.is_symlink() or project_root.is_symlink():
        raise ValueError("project root and task root must not be symlinks")
    state = load_json(workflow_state_path(task_root))
    destination = load_destination_receipt(args.destination_stored_receipt, task_root)
    hold = destination_gate(state, args.case_id, destination)
    completed_filename = args.completed_video_filename
    if completed_filename is None and destination is not None:
        value = destination.get("completed_video_filename")
        if isinstance(value, str):
            completed_filename = value
    if completed_filename is None:
        export_record = state.get("artifacts", {}).get("export") if isinstance(state.get("artifacts"), dict) else None
        if isinstance(export_record, dict) and isinstance(export_record.get("path"), str):
            export_path = task_root / Path(*PurePosixPath(export_record["path"]).parts)
            if export_path.is_file() and not export_path.is_symlink() and export_path.suffix.lower() == ".json":
                try:
                    completed_filename = find_completed_filename(load_json(export_path))
                except (OSError, json.JSONDecodeError, ValueError):
                    completed_filename = None
    in_progress = other_in_progress_cases(project_root, args.case_id)
    skip_shared = bool(in_progress)
    bound = bound_task_files(task_root, state)
    home_downloads = args.home_downloads_dir.expanduser().resolve(strict=False)
    expected_download_sha256 = None
    if destination is not None:
        digest = destination.get("completed_video_sha256")
        if isinstance(digest, str) and len(digest) == 64:
            expected_download_sha256 = digest
    if hold is not None:
        payload = result_payload(args.case_id, "blocked", hold, [], [], [], completed_filename, skip_shared, None)
        return 2, payload
    if args.execute and not args.i_confirm_destination_stored:
        payload = result_payload(
            args.case_id,
            "blocked",
            HOLD_SOLE_COPY,
            [],
            [],
            [{"path": "--i-confirm-destination-stored", "reason": "required_for_execute"}],
            completed_filename,
            skip_shared,
            None,
        )
        return 2, payload
    candidates, skipped = collect_candidates(
        project_root,
        task_root,
        args.case_id,
        completed_filename,
        home_downloads,
        skip_shared,
        bound,
        expected_download_sha256,
    )
    planned = plan_entries(project_root, candidates)
    mode = "execute" if args.execute else "dry-run"
    deleted: list[dict[str, Any]] = []
    receipt_path: str | None = None
    if args.execute:
        deleted = []
        for path, entry in zip(candidates, planned):
            path.unlink()
            deleted.append({"path": entry["path"], "area": entry["area"], "sha256": entry["sha256"], "bytes": entry["bytes"]})
        receipt_file = next_receipt_path(task_root)
        payload = result_payload(args.case_id, mode, None, deleted, planned, skipped, completed_filename, skip_shared, posix_relative(project_root, receipt_file))
        receipt_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        receipt_path = posix_relative(project_root, receipt_file)
        payload["receipt_path"] = receipt_path
        return 0, payload
    payload = result_payload(args.case_id, mode, None, deleted, planned, skipped, completed_filename, skip_shared, receipt_path)
    return 0, payload


def write_state(task_root: Path, case_id: str, stage: str, delivery_mode: str, with_drive: bool) -> None:
    zero = "0" * 64
    artifacts = {
        "script_package": {"path": "receipts/script_package.json", "sha256": f"{1:064x}"},
        "production_payload": {"path": "receipts/production_payload.json", "sha256": f"{2:064x}"},
        "execution_plan": {"path": "receipts/execution_plan.json", "sha256": f"{3:064x}"},
        "rough_edit": {"path": "receipts/rough_edit.json", "sha256": f"{4:064x}"},
        "finished_timeline": {"path": "receipts/finished_timeline.json", "sha256": f"{5:064x}"},
        "final_qa": {"path": "receipts/final_qa.json", "sha256": f"{6:064x}"},
        "export": {"path": "receipts/export.json", "sha256": f"{7:064x}"},
        "drive": {"path": "receipts/drive.json", "sha256": f"{8:064x}"} if with_drive else None,
    }
    state = {
        "schema": STATE_SCHEMA,
        "case_id": case_id,
        "product_model": "AN-S182",
        "stage": stage,
        "delivery_mode": delivery_mode,
        "settings": {"path": "receipts/settings.json", "sha256": zero},
        "artifacts": artifacts,
        "learning_snapshots": {
            "script": {"path": "learning/script.md", "sha256": f"{21:064x}"},
            "edit": {"path": "learning/edit.md", "sha256": f"{22:064x}"},
            "delivery": {"path": "learning/delivery.md", "sha256": f"{23:064x}"},
        },
        "approvals": {
            "script": {"status": "approved" if stage == "COMPLETE" else "pending", "receipt": "台本OK" if stage == "COMPLETE" else None, "bound_artifact_sha256": artifacts["production_payload"]["sha256"] if stage == "COMPLETE" else None, "bound_learning_snapshot_sha256": f"{21:064x}" if stage == "COMPLETE" else None},
            "rough_edit": {"status": "approved" if stage == "COMPLETE" else "pending", "receipt": "粗編集OK" if stage == "COMPLETE" else None, "bound_artifact_sha256": artifacts["execution_plan"]["sha256"] if stage == "COMPLETE" else None, "bound_learning_snapshot_sha256": f"{22:064x}" if stage == "COMPLETE" else None},
            "final_export": {"status": "approved" if stage == "COMPLETE" else "pending", "receipt": "完成・書き出しOK" if stage == "COMPLETE" else None, "bound_artifact_sha256": artifacts["final_qa"]["sha256"] if stage == "COMPLETE" else None, "bound_learning_snapshot_sha256": f"{23:064x}" if stage == "COMPLETE" else None},
        },
        "stage_receipts": [],
    }
    (task_root / "receipts").mkdir(parents=True, exist_ok=True)
    (task_root / "learning").mkdir(parents=True, exist_ok=True)
    (task_root / "receipts" / "export.json").write_text(
        json.dumps({"completed_video_filename": f"{case_id}.mp4"}, ensure_ascii=False),
        encoding="utf-8",
    )
    workflow_state_path(task_root).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def self_test() -> int:
    import tempfile

    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        if not condition:
            failures.append(name)

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "repo"
        case_id = "AN-S182-20260902-purge"
        task_root = root / "outputs" / case_id
        downloads = Path(directory) / "Downloads"
        for path in (
            root / "footage",
            root / "voice",
            root / "out",
            root / ".runtime" / "product-video-inputs" / "AN-S182_コピー",
            task_root / "import-staging",
            downloads,
        ):
            path.mkdir(parents=True, exist_ok=True)
        write_state(task_root, case_id, "COMPLETE", "drive", True)
        files = {
            root / "footage" / "clip.mp4": b"footage-bytes",
            root / "voice" / "capcut-tts.ogg": b"voice-bytes",
            root / "out" / f"{case_id}.mp4": b"export-bytes",
            root / ".runtime" / "product-video-inputs" / "AN-S182_コピー" / "src.mp4": b"runtime-bytes",
            task_root / "import-staging" / "frame.jpg": b"frame-bytes",
            task_root / "keep.json": b'{"keep":true}\n',
            downloads / f"{case_id}.mp4": b"download-bytes",
        }
        for path, data in files.items():
            path.write_bytes(data)

        dry = argparse.Namespace(
            project_root=root,
            task_root=task_root,
            case_id=case_id,
            execute=False,
            i_confirm_destination_stored=False,
            destination_stored_receipt=None,
            completed_video_filename=f"{case_id}.mp4",
            home_downloads_dir=downloads,
        )
        code, payload = run_purge(dry)
        check("dry-run-ok", code == 0 and payload["mode"] == "dry-run")
        check("dry-run-keeps-files", all(path.exists() for path in files))
        planned_paths = {entry["path"] for entry in payload["planned"]}
        check("plans-case-media", "outputs/AN-S182-20260902-purge/import-staging/frame.jpg" in planned_paths)
        check("plans-export", f"out/{case_id}.mp4" in planned_paths)
        check("plans-downloads", f"Downloads/{case_id}.mp4" in planned_paths)
        check("does-not-plan-json", "outputs/AN-S182-20260902-purge/keep.json" not in planned_paths)

        early = argparse.Namespace(**{**dry.__dict__, "execute": True, "i_confirm_destination_stored": True})
        write_state(task_root, case_id, "ROUGH_EDIT", "drive", True)
        code, payload = run_purge(early)
        check("blocks-before-complete", code == 2 and payload["hold"] == HOLD_NOT_DUE)
        check("early-keeps-files", (root / "out" / f"{case_id}.mp4").exists())
        write_state(task_root, case_id, "COMPLETE", "drive", True)

        no_confirm = argparse.Namespace(**{**dry.__dict__, "execute": True, "i_confirm_destination_stored": False})
        code, payload = run_purge(no_confirm)
        check("execute-needs-confirm", code == 2)

        export_only = argparse.Namespace(**{**dry.__dict__, "execute": True, "i_confirm_destination_stored": True})
        write_state(task_root, case_id, "COMPLETE", "export_only", False)
        code, payload = run_purge(export_only)
        check("export-only-without-receipt", code == 2 and payload["hold"] == HOLD_SOLE_COPY)
        receipt = {
            "schema": DESTINATION_SCHEMA,
            "case_id": case_id,
            "completed_video_filename": f"{case_id}.mp4",
            "completed_video_sha256": sha256_bytes(b"export-bytes"),
            "destination_kind": "durable_store_readback",
            "local_working_copies_are_not_the_destination": True,
        }
        receipt_path = task_root / "destination-stored-receipt.v1.json"
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_state(task_root, case_id, "COMPLETE", "export_only", False)
        code, payload = run_purge(dry)
        check("export-only-with-receipt", code == 0 and payload["mode"] == "dry-run")
        receipt_path.unlink()
        write_state(task_root, case_id, "COMPLETE", "drive", True)

        other = root / "outputs" / "AN-S182-other" / "product-video-workflow-state.v1.json"
        other.parent.mkdir(parents=True, exist_ok=True)
        other.write_text(json.dumps({"stage": "ROUGH_EDIT"}, ensure_ascii=False), encoding="utf-8")
        code, payload = run_purge(dry)
        skipped_reasons = {item["reason"] for item in payload["skipped"]}
        check("skips-shared-when-other-in-progress", "shared_in_use_by_in_progress_case" in skipped_reasons)
        planned_paths = {entry["path"] for entry in payload["planned"]}
        check("still-plans-case-export", f"out/{case_id}.mp4" in planned_paths)
        check("does-not-plan-shared-footage", "footage/clip.mp4" not in planned_paths)
        other.unlink()
        other.parent.rmdir()

        execute = argparse.Namespace(**{**dry.__dict__, "execute": True, "i_confirm_destination_stored": True})
        code, payload = run_purge(execute)
        check("execute-ok", code == 0)
        check("deletes-media", not (root / "out" / f"{case_id}.mp4").exists())
        check("deletes-footage", not (root / "footage" / "clip.mp4").exists())
        check("deletes-download", not (downloads / f"{case_id}.mp4").exists())
        check("keeps-json", (task_root / "keep.json").exists())
        check("keeps-state", workflow_state_path(task_root).exists())
        check("writes-receipt", (task_root / "local-working-media-purge-receipt.v1.json").is_file())
        if host_kind() == "darwin":
            check("mac-host-complete", payload["mac_purge"] == "completed_on_this_host")
        else:
            check("mac-hold-on-vm", payload["mac_purge"] == HOLD_MAC)

        (root / "out" / f"{case_id}.mp4").write_bytes(b"leftover")
        code, payload = run_purge(execute)
        check("second-execute-no-overwrite", not (task_root / "local-working-media-purge-receipt.v1.json").is_symlink())
        check("second-receipt-versioned", (task_root / "local-working-media-purge-receipt-r01.v1.json").is_file())
        check("second-deletes-leftover", not (root / "out" / f"{case_id}.mp4").exists())

    if failures:
        print("SELF-TEST FAILED: " + ", ".join(failures))
        return 1
    print("SELF-TEST PASSED: purge_local_working_media")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--task-root", type=Path)
    parser.add_argument("--case-id")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--i-confirm-destination-stored", action="store_true")
    parser.add_argument("--destination-stored-receipt", type=Path)
    parser.add_argument("--completed-video-filename")
    parser.add_argument("--home-downloads-dir", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.project_root is None or args.task_root is None or args.case_id is None:
        parser.error("--project-root, --task-root, and --case-id are required unless --self-test is used")
    try:
        code, payload = run_purge(args)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
