#!/usr/bin/env python3
"""Render a short deterministic transparent PNG sequence at 30 fps."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from render_html import render_telop as render_html_telop
from render_svg import render_telop as render_svg_telop
from telop_common import ValidationError, clone_for_clip, ensure_output_path, load_telop


def render_sequence(json_file: str | Path, output_root: str | Path, method: str, duration: float, fps: int) -> Path:
    original = load_telop(json_file)
    if duration <= 0 or fps <= 0:
        raise ValueError("duration and fps must be positive")
    clip = clone_for_clip(original, duration)
    frame_count = max(1, round(duration * fps))
    method_dir = ensure_output_path(Path(output_root) / method)
    renderer = render_html_telop if method == "html" else render_svg_telop
    for frame_index in range(frame_count):
        time_s = frame_index / fps
        output = method_dir / f"frame-{frame_index:03d}.png"
        renderer(clip, output, background="transparent", time_s=time_s)
    return method_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a short transparent PNG sequence")
    parser.add_argument("json_file")
    parser.add_argument("--out", required=True, help="sequence root inside the renderer folder")
    parser.add_argument("--method", choices=("html", "svg", "both"), default="both")
    parser.add_argument("--duration", type=float, default=0.4)
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args(argv)
    methods = ("html", "svg") if args.method == "both" else (args.method,)
    try:
        paths = [render_sequence(args.json_file, args.out, method, args.duration, args.fps) for method in methods]
    except (OSError, ValueError, ValidationError, RuntimeError) as exc:
        print(f"render_frames: {exc}", file=sys.stderr)
        return 1
    for path in paths:
        print(f"{path} ({len(list(path.glob('frame-*.png')))} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
