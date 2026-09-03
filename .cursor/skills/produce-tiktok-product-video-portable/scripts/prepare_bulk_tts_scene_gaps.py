#!/usr/bin/env python3
"""Insert measured silent scene gaps into one bulk Holiday Twist TTS file, then split."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any


ALIGNMENT_SCHEMA = "product_video_bulk_tts_line_alignment.v1"
RECEIPT_SCHEMA = "product_video_bulk_tts_scene_gaps_receipt.v1"
HOLD_ALIGNMENT = "HOLD_BULK_TTS_LINE_ALIGNMENT_UNVERIFIED"
HOLD_GAPS = "HOLD_BULK_TTS_SCENE_GAPS_UNVERIFIED"
DEFAULT_GAP_MS = 600
MIN_GAP_MS = 400
MAX_GAP_MS = 1200
TIME_SLOP_SECONDS = 0.01


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def normalize_text(value: str) -> str:
    return "".join(value.split())


def bulk_tts_paste_text(lines: list[str]) -> str:
    return "\n\n".join(line.strip() for line in lines)


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a JSON object")
    return data


def parse_alignment(data: dict[str, Any]) -> tuple[list[dict[str, Any]] | None, str | None]:
    if data.get("schema") != ALIGNMENT_SCHEMA:
        return None, HOLD_ALIGNMENT
    rows = data.get("lines")
    if not isinstance(rows, list) or len(rows) < 2:
        return None, HOLD_ALIGNMENT
    parsed: list[dict[str, Any]] = []
    previous_end = 0.0
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            return None, HOLD_ALIGNMENT
        cut_id = row.get("cut_id")
        text = row.get("text")
        start = row.get("start_seconds")
        end = row.get("end_seconds")
        if not isinstance(cut_id, str) or not cut_id.strip():
            return None, HOLD_ALIGNMENT
        if not isinstance(text, str) or not normalize_text(text):
            return None, HOLD_ALIGNMENT
        if not isinstance(start, (int, float)) or isinstance(start, bool) or start < 0:
            return None, HOLD_ALIGNMENT
        if not isinstance(end, (int, float)) or isinstance(end, bool) or end <= start:
            return None, HOLD_ALIGNMENT
        start_f = float(start)
        end_f = float(end)
        if index > 0 and start_f + TIME_SLOP_SECONDS < previous_end:
            return None, HOLD_ALIGNMENT
        parsed.append(
            {
                "cut_id": cut_id,
                "text": text,
                "start_seconds": start_f,
                "end_seconds": end_f,
                "duration_seconds": end_f - start_f,
            }
        )
        previous_end = end_f
    cut_ids = [row["cut_id"] for row in parsed]
    if len(set(cut_ids)) != len(cut_ids):
        return None, HOLD_ALIGNMENT
    return parsed, None


def match_frozen_lines(rows: list[dict[str, Any]], frozen: list[dict[str, str]]) -> str | None:
    if len(rows) != len(frozen):
        return HOLD_ALIGNMENT
    for row, expected in zip(rows, frozen):
        if row["cut_id"] != expected["cut_id"]:
            return HOLD_ALIGNMENT
        if normalize_text(row["text"]) != normalize_text(expected["text"]):
            return HOLD_ALIGNMENT
    return None


def probe_audio(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=sample_rate,channels,channel_layout",
            "-show_entries",
            "format=duration",
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
    streams = payload.get("streams") or []
    if not streams:
        raise ValueError("audio stream missing")
    stream = streams[0]
    sample_rate = int(stream["sample_rate"])
    channels = int(stream.get("channels") or 1)
    layout = stream.get("channel_layout") or ("mono" if channels == 1 else "stereo")
    duration = float(payload["format"]["duration"])
    return {
        "sample_rate": sample_rate,
        "channels": channels,
        "channel_layout": layout,
        "duration": duration,
    }


def run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run(args, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or "ffmpeg failed")


def padded_filter(rows: list[dict[str, Any]], gap_seconds: float, layout: str, sample_rate: int) -> str:
    parts: list[str] = []
    labels: list[str] = []
    for index, row in enumerate(rows):
        parts.append(
            f"[0:a]atrim=start={row['start_seconds']}:end={row['end_seconds']},asetpts=PTS-STARTPTS[a{index}]"
        )
        labels.append(f"[a{index}]")
        if index < len(rows) - 1:
            parts.append(
                f"anullsrc=r={sample_rate}:cl={layout}:d={gap_seconds},aformat=sample_rates={sample_rate}:channel_layouts={layout}[s{index}]"
            )
            labels.append(f"[s{index}]")
    parts.append("".join(labels) + f"concat=n={len(labels)}:v=0:a=1[out]")
    return ";".join(parts)


def write_padded_audio(audio: Path, rows: list[dict[str, Any]], gap_seconds: float, output: Path, probe: dict[str, Any]) -> None:
    filt = padded_filter(rows, gap_seconds, probe["channel_layout"], probe["sample_rate"])
    run_ffmpeg(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-i",
            str(audio),
            "-filter_complex",
            filt,
            "-map",
            "[out]",
            str(output),
        ]
    )


def write_scene_clips(audio: Path, rows: list[dict[str, Any]], output_dir: Path) -> list[dict[str, Any]]:
    written: list[dict[str, Any]] = []
    for row in rows:
        dest = output_dir / f"{row['cut_id']}.wav"
        if dest.exists() or dest.is_symlink():
            raise ValueError(f"refusing to overwrite {dest}")
        run_ffmpeg(
            [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-i",
                str(audio),
                "-ss",
                f"{row['start_seconds']:.6f}",
                "-to",
                f"{row['end_seconds']:.6f}",
                "-c:a",
                "pcm_s16le",
                str(dest),
            ]
        )
        written.append(
            {
                "cut_id": row["cut_id"],
                "path": dest.name,
                "sha256": sha256_file(dest),
                "bytes": dest.stat().st_size,
                "speech_start_seconds": row["start_seconds"],
                "speech_end_seconds": row["end_seconds"],
            }
        )
    return written


def padded_timeline(rows: list[dict[str, Any]], gap_seconds: float) -> list[dict[str, Any]]:
    cursor = 0.0
    timeline: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        start = cursor
        end = start + row["duration_seconds"]
        timeline.append(
            {
                "cut_id": row["cut_id"],
                "speech_start_seconds": start,
                "speech_end_seconds": end,
                "split_gap_after_seconds": None if index == len(rows) - 1 else gap_seconds,
            }
        )
        cursor = end + (0.0 if index == len(rows) - 1 else gap_seconds)
    return timeline


def expected_padded_duration(rows: list[dict[str, Any]], gap_seconds: float) -> float:
    speech = sum(row["duration_seconds"] for row in rows)
    return speech + gap_seconds * (len(rows) - 1)


def count_silences(path: Path, noise_db: str = "-40dB", min_duration: float = 0.35) -> int:
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(path),
            "-af",
            f"silencedetect=noise={noise_db}:d={min_duration}",
            "-f",
            "null",
            "-",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or "silencedetect failed")
    text = result.stderr
    return text.count("silence_start:")


def prepare(
    audio: Path,
    alignment: dict[str, Any],
    frozen_lines: list[dict[str, str]] | None,
    output_dir: Path,
    gap_ms: int,
) -> tuple[int, dict[str, Any]]:
    if gap_ms < MIN_GAP_MS or gap_ms > MAX_GAP_MS:
        return 2, {"hold": HOLD_GAPS, "error": f"gap_ms must be {MIN_GAP_MS}-{MAX_GAP_MS}"}
    rows, hold = parse_alignment(alignment)
    if hold or rows is None:
        return 2, {"hold": hold or HOLD_ALIGNMENT}
    if frozen_lines is not None:
        mismatch = match_frozen_lines(rows, frozen_lines)
        if mismatch:
            return 2, {"hold": mismatch, "error": "alignment text/cut_id must equal frozen lines"}
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError("output dir is not a directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    padded_path = output_dir / "bulk-with-scene-gaps.wav"
    receipt_path = output_dir / "bulk-tts-scene-gaps-receipt.v1.json"
    scenes_dir = output_dir / "scenes"
    for path in (padded_path, receipt_path):
        if path.exists() or path.is_symlink():
            raise ValueError(f"refusing to overwrite {path}")
    if scenes_dir.exists() and any(scenes_dir.iterdir()):
        raise ValueError(f"refusing to overwrite {scenes_dir}")
    scenes_dir.mkdir(parents=True, exist_ok=True)
    probe = probe_audio(audio)
    last_end = rows[-1]["end_seconds"]
    if last_end - TIME_SLOP_SECONDS > probe["duration"]:
        return 2, {"hold": HOLD_ALIGNMENT, "error": "alignment extends past audio duration"}
    gap_seconds = gap_ms / 1000.0
    write_padded_audio(audio, rows, gap_seconds, padded_path, probe)
    scenes = write_scene_clips(audio, rows, scenes_dir)
    silence_count = count_silences(padded_path)
    expected_gaps = len(rows) - 1
    if silence_count < expected_gaps:
        return 2, {
            "hold": HOLD_GAPS,
            "error": "padded file does not contain one detectable silence per scene boundary",
            "expected_gaps": expected_gaps,
            "detected_silence_starts": silence_count,
        }
    timeline = padded_timeline(rows, gap_seconds)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "hold": None,
        "source_audio_sha256": sha256_file(audio),
        "gap_ms": gap_ms,
        "paste_text": bulk_tts_paste_text([row["text"] for row in rows]),
        "expected_padded_duration_seconds": expected_padded_duration(rows, gap_seconds),
        "padded_audio": {
            "path": padded_path.name,
            "sha256": sha256_file(padded_path),
            "bytes": padded_path.stat().st_size,
        },
        "timeline": timeline,
        "scenes": scenes,
        "detected_silence_starts": silence_count,
    }
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt["receipt_path"] = receipt_path.name
    return 0, receipt


def write_sine_wav(path: Path, duration: float, frequency: float, sample_rate: int = 16000) -> None:
    n = int(sample_rate * duration)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        frames = bytearray()
        for index in range(n):
            sample = int(16000 * math.sin(2 * math.pi * frequency * (index / sample_rate)))
            frames += int(sample).to_bytes(2, "little", signed=True)
        handle.writeframes(bytes(frames))


def concat_wavs(paths: list[Path], output: Path) -> None:
    inputs: list[str] = []
    for path in paths:
        inputs.extend(["-i", str(path)])
    n = len(paths)
    labels = "".join(f"[{index}:a]" for index in range(n))
    run_ffmpeg(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            *inputs,
            "-filter_complex",
            f"{labels}concat=n={n}:v=0:a=1[out]",
            "-map",
            "[out]",
            str(output),
        ]
    )


def self_test() -> int:
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        if not condition:
            failures.append(name)

    paste = bulk_tts_paste_text(["一行目。", "二行目。", "三行目。"])
    check("paste-blank-lines", paste == "一行目。\n\n二行目。\n\n三行目。")
    check("no-ellipsis", "…" not in paste and "..." not in paste)

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        bursts = []
        for index, freq in enumerate((440.0, 550.0, 660.0), start=1):
            path = root / f"burst-{index}.wav"
            write_sine_wav(path, 0.25, freq)
            bursts.append(path)
        tiny = root / "tiny-gap.wav"
        write_sine_wav(tiny, 0.04, 50.0)
        source = root / "bulk.wav"
        concat_wavs([bursts[0], tiny, bursts[1], tiny, bursts[2]], source)
        alignment = {
            "schema": ALIGNMENT_SCHEMA,
            "lines": [
                {"cut_id": "cut-01", "text": "一行目。", "start_seconds": 0.0, "end_seconds": 0.25},
                {"cut_id": "cut-02", "text": "二行目。", "start_seconds": 0.29, "end_seconds": 0.54},
                {"cut_id": "cut-03", "text": "三行目。", "start_seconds": 0.58, "end_seconds": 0.83},
            ],
        }
        frozen = [{"cut_id": f"cut-0{i}", "text": line} for i, line in enumerate(("一行目。", "二行目。", "三行目。"), start=1)]
        out = root / "out"
        code, payload = prepare(source, alignment, frozen, out, DEFAULT_GAP_MS)
        check("prepare-ok", code == 0)
        check("writes-padded", (out / "bulk-with-scene-gaps.wav").is_file())
        check("writes-three-scenes", all((out / "scenes" / f"cut-0{i}.wav").is_file() for i in range(1, 4)))
        check("two-or-more-silences", int(payload.get("detected_silence_starts") or 0) >= 2)
        padded_duration = probe_audio(out / "bulk-with-scene-gaps.wav")["duration"]
        check("padded-near-1.95s", abs(padded_duration - 1.95) < 0.12)

        bad_text = json.loads(json.dumps(alignment))
        bad_text["lines"][0]["text"] = "違う文言。"
        code, payload = prepare(source, bad_text, frozen, root / "bad-text", DEFAULT_GAP_MS)
        check("text-mismatch-hold", code == 2 and payload.get("hold") == HOLD_ALIGNMENT)

        overlap = json.loads(json.dumps(alignment))
        overlap["lines"][1]["start_seconds"] = 0.10
        code, payload = prepare(source, overlap, frozen, root / "overlap", DEFAULT_GAP_MS)
        check("overlap-hold", code == 2 and payload.get("hold") == HOLD_ALIGNMENT)

        code, payload = prepare(source, alignment, frozen, out, 50)
        check("gap-range-hold", code == 2 and payload.get("hold") == HOLD_GAPS)

    if failures:
        print("SELF-TEST FAILED: " + ", ".join(failures))
        return 1
    print("SELF-TEST PASSED: prepare_bulk_tts_scene_gaps")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--alignment", type=Path)
    parser.add_argument("--frozen-lines", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--gap-ms", type=int, default=DEFAULT_GAP_MS)
    parser.add_argument("--print-paste", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.print_paste:
        if args.frozen_lines is None and args.alignment is None:
            parser.error("--print-paste requires --frozen-lines or --alignment")
        source = load_json(args.frozen_lines or args.alignment)
        rows = source.get("lines")
        if not isinstance(rows, list):
            print(json.dumps({"hold": HOLD_ALIGNMENT}, ensure_ascii=False, indent=2))
            return 2
        texts = [row.get("text") for row in rows if isinstance(row, dict) and isinstance(row.get("text"), str)]
        print(bulk_tts_paste_text(texts))
        return 0
    if args.audio is None or args.alignment is None or args.output_dir is None:
        parser.error("--audio, --alignment, and --output-dir are required unless --self-test is used")
    try:
        alignment = load_json(args.alignment)
        frozen = None
        if args.frozen_lines is not None:
            frozen_payload = load_json(args.frozen_lines)
            rows = frozen_payload.get("lines")
            if not isinstance(rows, list):
                raise ValueError("frozen lines must contain a lines array")
            frozen = [{"cut_id": row["cut_id"], "text": row["text"]} for row in rows]
        code, payload = prepare(args.audio, alignment, frozen, args.output_dir, args.gap_ms)
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
