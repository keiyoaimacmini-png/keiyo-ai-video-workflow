#!/usr/bin/env python3
"""Save CapCut Text to Speech result audio without a save dialog.

The source of truth is the result-card media URL (video/audio currentSrc,
typically mime_type=audio_mpeg). This helper writes those bytes into the
case TTS working directory.

It does not click オーディオのみ, does not use Finder / OS / embedded-browser
save dialogs, does not wait for ~/Downloads/CapCut_TTS_*, and does not ask
the operator to press Save. Stdout never reprints the source URL.
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


HOLD_BYTES = "HOLD_CAPCUT_TTS_RESULT_BYTES_UNAVAILABLE"
USER_AGENT = "Mozilla/5.0"


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def hold(reason: str) -> dict[str, str]:
    return {"status": "HOLD", "hold": HOLD_BYTES, "reason": reason}


def probe_audio(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,codec_type,sample_rate,channels",
            "-show_entries",
            "format=duration,size,format_name",
            "-of",
            "json",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or "ffprobe failed")
    payload = json.loads(result.stdout)
    streams = [
        stream
        for stream in (payload.get("streams") or [])
        if isinstance(stream, dict) and stream.get("codec_type") == "audio"
    ]
    if not streams:
        raise ValueError("audio stream missing")
    duration = float((payload.get("format") or {}).get("duration") or 0)
    if duration <= 0:
        raise ValueError("audio duration missing")
    stream = streams[0]
    return {
        "codec_name": stream.get("codec_name"),
        "sample_rate": int(stream["sample_rate"]) if stream.get("sample_rate") else None,
        "channels": int(stream["channels"]) if stream.get("channels") else None,
        "duration_seconds": duration,
        "format_name": (payload.get("format") or {}).get("format_name"),
    }


def download_bytes(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read()
    if not body:
        raise ValueError("empty response")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=str(dest.parent), delete=False, suffix=".part") as handle:
        handle.write(body)
        temp_path = Path(handle.name)
    temp_path.replace(dest)


def capture(url: str, dest: Path) -> dict[str, Any]:
    if dest.exists() or dest.is_symlink():
        return hold("refusing to overwrite existing TTS working file")
    try:
        download_bytes(url, dest)
        probe = probe_audio(dest)
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
        if dest.exists():
            dest.unlink()
        return hold("result-card audio bytes could not be saved as a valid audio file")
    return {
        "status": "OK",
        "path": str(dest),
        "sha256": sha256_file(dest),
        "bytes": dest.stat().st_size,
        "duration_seconds": probe["duration_seconds"],
        "codec_name": probe["codec_name"],
        "sample_rate": probe["sample_rate"],
        "channels": probe["channels"],
    }


def self_test() -> int:
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        if not condition:
            failures.append(name)

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "source.wav"
        ffmpeg = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=0.2",
                str(source),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if ffmpeg.returncode != 0:
            print("SELF-TEST FAILED: ffmpeg-sine")
            return 1
        handler = http.server.SimpleHTTPRequestHandler
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        cwd = Path.cwd()
        try:
            import os

            os.chdir(root)
            thread.start()
            url = f"http://127.0.0.1:{server.server_address[1]}/source.wav"
            dest = root / "captured.wav"
            first = capture(url, dest)
            check("ok-status", first.get("status") == "OK")
            check("writes-file", dest.is_file())
            check("duration", float(first.get("duration_seconds") or 0) > 0.1)
            second = capture(url, dest)
            check("overwrite-hold", second.get("hold") == HOLD_BYTES)
            missing = capture("http://127.0.0.1:1/missing.wav", root / "missing.wav")
            check("bad-url-hold", missing.get("hold") == HOLD_BYTES)
        finally:
            os.chdir(cwd)
            server.shutdown()
            server.server_close()

    if failures:
        print("SELF-TEST FAILED: " + ", ".join(failures))
        return 1
    print("SELF-TEST PASSED: capture_capcut_result_audio")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="Result-card media URL; never written to stdout")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.url is None or args.output is None:
        parser.error("--url and --output are required unless --self-test is used")
    payload = capture(args.url, args.output)
    emit(payload)
    return 0 if payload.get("status") == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
