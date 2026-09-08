#!/usr/bin/env python3
"""Extract in, midpoint, and out frames for one selected source range.

Call this after `台本OK`, for ranges chosen from `picture_must` only. Do not
hash or watch the material root first. Do not default to the first N seconds,
and do not hand-write ffmpeg per cut.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


HOLD_MEDIA = "HOLD_MEDIA_NOT_MATCHED"


def hold(code: str, reason: str) -> dict[str, str]:
    return {"status": "HOLD", "hold": code, "reason": reason}


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def extract_frame(source: Path, seconds: float, dest: Path) -> float:
    attempts = [seconds]
    for frames_back in (1, 2):
        earlier = round(seconds - (frames_back / 30.0), 6)
        if earlier >= 0 and earlier not in attempts:
            attempts.append(earlier)
    last_error = "ffmpeg failed"
    for attempt in attempts:
        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{attempt:.6f}",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-q:v",
                "3",
                "-pix_fmt",
                "yuvj420p",
                str(dest),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and dest.is_file() and dest.stat().st_size >= 32:
            return attempt
        last_error = result.stderr.strip() or f"ffmpeg failed for {dest.name}"
    raise RuntimeError(last_error)


def prove_range(source: Path, in_sec: float, out_sec: float, output_dir: Path) -> dict[str, Any]:
    if in_sec < 0 or out_sec <= in_sec:
        return hold(HOLD_MEDIA, "source range must have in < out")
    if not source.is_file():
        return hold(HOLD_MEDIA, f"source is missing: {source}")
    output_dir.mkdir(parents=True, exist_ok=True)
    mid = (in_sec + out_sec) / 2
    frames = {
        "in": (in_sec, output_dir / "in.jpg"),
        "mid": (mid, output_dir / "mid.jpg"),
        "out": (out_sec, output_dir / "out.jpg"),
    }
    written = {}
    for name, (seconds, dest) in frames.items():
        used = extract_frame(source, seconds, dest)
        written[name] = {
            "path": dest.as_posix(),
            "seconds": used,
            "sha256": sha256_file(dest),
            "bytes": dest.stat().st_size,
        }

    receipt = {
        "status": "OK",
        "source": source.as_posix(),
        "source_sha256": sha256_file(source),
        "source_in": in_sec,
        "source_out": out_sec,
        "frames": written,
    }
    receipt_path = output_dir / "range-proof.v1.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt["receipt"] = receipt_path.as_posix()
    return receipt


def self_test() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        source = root / "clip.mp4"
        made = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=64x64:d=2",
                str(source),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if made.returncode != 0:
            print("SELF-TEST FAILED: prove_source_range ffmpeg unavailable", flush=True)
            return 1
        dest = root / "frames"
        result = prove_range(source, 0.0, 1.5, dest)
        ok = result.get("status") == "OK"
        ok = ok and (dest / "in.jpg").is_file() and (dest / "mid.jpg").is_file() and (dest / "out.jpg").is_file()
        missing = prove_range(root / "nope.mov", 0.0, 1.0, dest / "missing")
        if not ok or missing.get("hold") != HOLD_MEDIA:
            print("SELF-TEST FAILED: prove_source_range", flush=True)
            return 1
    print("SELF-TEST PASSED: prove_source_range")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path)
    parser.add_argument("--in-sec", type=float)
    parser.add_argument("--out-sec", type=float)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.source is None or args.in_sec is None or args.out_sec is None or args.output_dir is None:
        parser.error("--source --in-sec --out-sec --output-dir are required")
    try:
        payload = prove_range(args.source, args.in_sec, args.out_sec, args.output_dir)
        emit(payload)
        return 0 if payload.get("status") == "OK" else 2
    except (OSError, RuntimeError) as exc:
        emit(hold(HOLD_MEDIA, str(exc)))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
