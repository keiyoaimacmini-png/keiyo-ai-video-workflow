#!/usr/bin/env python3
"""Read one product's video files with Gemini 3.8 Flash and write Obsidian notes.

The managed object is the video. Sampled frames are only the given seconds
inside that video, so Gemini does not invent in/out. No API key.
Stops if the model is wrong, the body is empty, or the model says it cannot see.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".cursor/skills/product-video/scripts"))

from constants import VIDEO_EXTENSIONS  # noqa: E402
from send_gemini_cli_prompt import (  # noqa: E402
    EFFORT_REQUIRED,
    MODEL_REQUIRED,
    extract_draft,
    extract_json_object,
    find_agy,
    model_matches,
    scrub_env,
)

MATERIAL = ROOT / ".runtime/product-video-inputs/AN-S151TLE"
VAULT = Path.home() / "Documents/product-video-materials/AN-S151TLE"
FRAMES = ROOT / ".runtime/product-video-ledger-frames/AN-S151TLE"
STATUS = FRAMES / "status.json"
PRODUCT_MODEL = "AN-S151TLE"
BATCH = 6
STILL_EXTENSIONS = frozenset({".heic", ".jpg", ".jpeg", ".png", ".webp"})


def duration_of(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    data = json.loads(proc.stdout or "{}")
    return float(data["format"]["duration"])


def sample_times(duration: float) -> list[float]:
    if duration <= 8:
        step = 1.5
    elif duration <= 30:
        step = 3.0
    elif duration <= 90:
        step = 6.0
    else:
        step = 10.0
    times: list[float] = []
    cursor = min(0.2, max(duration / 2, 0.0))
    while cursor < duration - 0.15:
        times.append(round(cursor, 1))
        cursor += step
    return times or [round(min(0.2, duration / 2), 1)]


def extract_frames(video: Path, times: list[float], dest: Path) -> list[tuple[float, Path]]:
    dest.mkdir(parents=True, exist_ok=True)
    made: list[tuple[float, Path]] = []
    for second in times:
        name = f"frame_{second:.1f}".replace(".", "_") + ".jpg"
        out = dest / name
        if not out.is_file() or out.stat().st_size == 0:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-ss", str(second), "-i", str(video),
                    "-frames:v", "1", "-vf", "scale=640:-2", str(out),
                ],
                check=False,
                capture_output=True,
            )
        if out.is_file() and out.stat().st_size > 0:
            made.append((second, out))
    return made


def parse_body(text: str) -> dict:
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", stripped, re.DOTALL)
    raw = fence.group(1) if fence else stripped
    start = raw.find("{")
    if start < 0:
        raise ValueError("no json object")
    data, _ = json.JSONDecoder().raw_decode(raw[start:])
    if not isinstance(data, dict):
        raise ValueError("json is not an object")
    return data


def product_brief(project_root: Path, product_model: str) -> str:
    from product_facts import load_product_facts_profile

    profile = load_product_facts_profile(project_root, product_model)
    if profile.get("status") != "OK":
        raise SystemExit(str(profile.get("hold") or "HOLD_PRODUCT_FACTS_REQUIRED"))
    lines = [f"- {item}" for item in list(profile.get("verified_facts") or []) + list(profile.get("appeal_points") or [])]
    if not lines:
        raise SystemExit("HOLD_PRODUCT_FACTS_REQUIRED")
    return "\n".join(lines)


def vision_prompt(product_model: str, brief: str, video_name: str, frame_lines: list[str]) -> str:
    return (
        "シェルコマンドは実行しないでください。ファイルも書き換えないでください。\n"
        f"読む対象は動画素材 {video_name} です。静止画素材の管理ではありません。\n"
        f"この動画の製品は {product_model} です。動画を読む前に確認した製品情報は次だけです。\n"
        f"{brief}\n"
        "この情報は、動画の中の物がこの製品かどうかを見分けるために使ってください。\n"
        "下の参照は、この動画の指定した秒に見えている画面です。その秒の前後で動画の中で何が起きているかを書いてください。\n"
        "参照が届いているなら seen は true です。白飛び、ピンボケ、被写体が特定できない場合も seen は true にし、"
        "factual_description にその事実を書いてください。参照自体が渡されていないときだけ seen を false にしてください。\n"
        "製品が映っていれば、製品名と見えている部位を factual_description と product_parts に書き、product_visible は true です。\n"
        "製品が映っていなければ product_visible は false、product_parts は空です。別の物をこの製品と呼ばないでください。\n"
        "画面に見えない重さ、寸法、解像度、価格、対応OSは書かないでください。\n"
        "ライトの色は、製品本体の発光部がその色と分かるときだけ書いてください。"
        "天面への映り込み、車のソケットやナビの光、白いスリットを、製品の青ライトや緑ライトや白ライトと呼ばないでください。\n"
        "秒数は作らないでください。渡した秒をそのまま second に書いてください。\n\n"
        + "\n".join(frame_lines)
        + "\n\n"
        '{"seen": true, "frames": [{"file":"", "second": 0.0, "factual_description":"", '
        '"objects":[], "actions":[], "product_state":"", "location":"", "framing":"", '
        '"visible_features":[], "product_visible": false, "product_parts":[]}]}\n'
    )


def coerce_visible(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    return None


def ask(video: Path, frames: list[tuple[float, Path]], dest: Path, brief: str) -> list[dict]:
    agy = find_agy()
    if not agy:
        raise SystemExit("HOLD_GEMINI_CLI_NOT_VERIFIED agy missing")
    lines = [f"{video.name} の {second:.1f}秒。参照は @{path.name}" for second, path in frames]
    prompt = vision_prompt(PRODUCT_MODEL, brief, video.name, lines)
    log = dest / "agy.log"
    cmd = [
        agy, "--print", prompt,
        "--output-format", "json",
        "--model", MODEL_REQUIRED,
        "--effort", EFFORT_REQUIRED,
        "--add-dir", str(dest),
        "--sandbox",
        "--disable-slash-commands",
        "--print-timeout", "3m",
        "--log-file", str(log),
    ]
    text = ""
    parsed = None
    blob = ""
    for attempt in range(1, 4):
        proc = subprocess.run(cmd, cwd=str(dest), env=scrub_env(), text=True, capture_output=True, timeout=200)
        blob = f"{proc.stdout or ''}\n{proc.stderr or ''}"
        parsed = extract_json_object(proc.stdout or "")
        text = extract_draft(parsed) or ""
        if text:
            break
        print(f"RETRY empty vision body {attempt}/3", flush=True)
    (dest / "last-draft.txt").write_text(text or "", encoding="utf-8")
    if not model_matches(parsed, blob, requested=MODEL_REQUIRED):
        raise SystemExit("HOLD_GEMINI_MODEL_NOT_VERIFIED")
    if not text:
        raise SystemExit("HOLD_GEMINI_CLI_NOT_VERIFIED empty vision body")
    data = parse_body(text)
    by_file = {path.name: second for second, path in frames}
    allowed = [second for second, _path in frames]
    rows = []
    for item in data.get("frames") or []:
        if not isinstance(item, dict):
            continue
        file_name = str(item.get("file") or "")
        second = by_file.get(file_name)
        if second is None:
            try:
                reported = float(item.get("second"))
            except (TypeError, ValueError):
                continue
            second = next((known for known in allowed if abs(known - reported) < 0.05), None)
        if second is None:
            continue
        if not str(item.get("factual_description") or "").strip():
            continue
        visible = coerce_visible(item.get("product_visible"))
        if visible is None:
            continue
        parts = item.get("product_parts")
        item["product_visible"] = visible
        item["product_parts"] = [
            str(part).strip() for part in parts if str(part).strip()
        ] if isinstance(parts, list) else []
        item["second"] = second
        rows.append(item)
    described = len(rows) == len(frames)
    if data.get("seen") is False and not described:
        raise SystemExit("HOLD_MATERIAL_LEDGER_VISION_UNVERIFIED")
    if not described:
        raise SystemExit(f"HOLD_MATERIAL_LEDGER_VISION_UNVERIFIED frames {len(rows)}/{len(frames)}")
    rows.sort(key=lambda row: float(row["second"]))
    return rows


def signature(row: dict) -> tuple:
    def norm(values: object) -> tuple:
        if not isinstance(values, list):
            return tuple()
        return tuple(sorted(str(value).strip() for value in values if str(value).strip()))

    return (
        norm(row.get("objects")),
        norm(row.get("actions")),
        str(row.get("product_state") or "").strip(),
        str(row.get("location") or "").strip(),
        str(row.get("framing") or "").strip(),
        norm(row.get("visible_features")),
        bool(row.get("product_visible")),
        norm(row.get("product_parts")),
    )


def scenes_from(rows: list[dict], duration: float) -> list[dict]:
    grouped: list[dict] = []
    for row in rows:
        if not grouped or signature(row) != signature(grouped[-1]):
            grouped.append(dict(row))
            grouped[-1]["source_in"] = float(row["second"])
        grouped[-1]["source_out_mark"] = float(row["second"])
        grouped[-1]["factual_description"] = str(row.get("factual_description") or "").strip()
    cuts = [float(item["source_in"]) for item in grouped]
    for index, item in enumerate(grouped):
        start = 0.0 if index == 0 else cuts[index]
        end = cuts[index + 1] if index + 1 < len(cuts) else duration
        if end <= start:
            end = min(duration, start + 0.1)
        item["source_in"] = round(start, 3)
        item["source_out"] = round(end, 3)
    return grouped


def yaml_list(values: object) -> str:
    if not isinstance(values, list):
        return ""
    return "、".join(str(value).strip() for value in values if str(value).strip())


def write_note(video: Path, duration: float, scenes: list[dict]) -> Path:
    rel = video.relative_to(MATERIAL)
    note = VAULT / rel.with_suffix(".md")
    note.parent.mkdir(parents=True, exist_ok=True)
    stat = video.stat()
    lines = [
        "---",
        "schema: product_video_material_note.v1",
        f"product_model: {PRODUCT_MODEL}",
        f"relative_path: {rel.as_posix()}",
        f"source_size: {stat.st_size}",
        f"source_mtime_ns: {stat.st_mtime_ns}",
        f"duration_sec: {duration:.3f}",
        "---",
        "",
    ]
    for scene in scenes:
        lines.append(f"## {scene['source_in']:.3f}–{scene['source_out']:.3f}")
        lines.append(f"factual_description: {scene.get('factual_description') or ''}")
        lines.append(f"objects: {yaml_list(scene.get('objects'))}")
        lines.append(f"actions: {yaml_list(scene.get('actions'))}")
        lines.append(f"product_state: {scene.get('product_state') or ''}")
        lines.append(f"location: {scene.get('location') or ''}")
        lines.append(f"framing: {scene.get('framing') or ''}")
        lines.append(f"visible_features: {yaml_list(scene.get('visible_features'))}")
        lines.append(f"product_visible: {'true' if scene.get('product_visible') else 'false'}")
        lines.append(f"product_parts: {yaml_list(scene.get('product_parts'))}")
        lines.append("")
    note.write_text("\n".join(lines), encoding="utf-8")
    return note


def note_current(video: Path) -> bool:
    rel = video.relative_to(MATERIAL)
    note = VAULT / rel.with_suffix(".md")
    if not note.is_file():
        return False
    text = note.read_text(encoding="utf-8")
    stat = video.stat()
    return f"source_size: {stat.st_size}" in text and f"source_mtime_ns: {stat.st_mtime_ns}" in text


def videos() -> list[Path]:
    found = [
        path for path in MATERIAL.rglob("*")
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    ]
    return sorted(found, key=lambda path: path.stat().st_size)


def stills() -> list[Path]:
    found = [
        path for path in MATERIAL.rglob("*")
        if path.is_file() and path.suffix.lower() in STILL_EXTENSIONS
    ]
    return sorted(found, key=lambda path: path.as_posix())


def still_frame(image: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / "frame_0_0.jpg"
    if not out.is_file() or out.stat().st_size == 0:
        if image.suffix.lower() in {".jpg", ".jpeg"}:
            shutil.copyfile(image, out)
        else:
            subprocess.run(
                ["sips", "-s", "format", "jpeg", str(image), "--out", str(out)],
                check=False,
                capture_output=True,
            )
    if not out.is_file() or out.stat().st_size == 0:
        raise SystemExit(f"HOLD_MATERIAL_LEDGER_VISION_UNVERIFIED still {image.name}")
    return out


def configure(project_root: Path, product_model: str, material_root: Path, vault_root: Path) -> None:
    global ROOT, MATERIAL, VAULT, FRAMES, STATUS, PRODUCT_MODEL
    ROOT = project_root
    PRODUCT_MODEL = product_model
    MATERIAL = material_root
    VAULT = vault_root / product_model
    FRAMES = project_root / ".runtime/product-video-ledger-frames" / product_model
    STATUS = FRAMES / "status.json"


def main() -> int:
    import argparse

    from resolve_product_inputs import default_material_root

    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--product-model", required=True)
    parser.add_argument("--material-root", type=Path)
    parser.add_argument("--vault-root", type=Path)
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    material_root = args.material_root or default_material_root(project_root, args.product_model)
    vault_root = args.vault_root or (Path.home() / "Documents" / "product-video-materials")
    env_vault = __import__("os").environ.get("PRODUCT_VIDEO_LEDGER_ROOT", "").strip()
    if args.vault_root is None and env_vault:
        vault_root = Path(env_vault)
    configure(project_root, args.product_model, Path(material_root), Path(vault_root))
    done = 0
    brief = product_brief(project_root, args.product_model)
    pending = [path for path in videos() if not note_current(path)]
    print(f"pending {len(pending)}", flush=True)
    for video in pending:
        rel = video.relative_to(MATERIAL).as_posix()
        length = duration_of(video)
        times = sample_times(length)
        dest = FRAMES / "work" / rel.replace("/", "__")
        frames = extract_frames(video, times, dest)
        print(f"START {rel} {length:.1f}s frames {len(frames)}", flush=True)
        rows: list[dict] = []
        for offset in range(0, len(frames), BATCH):
            rows.extend(ask(video, frames[offset:offset + BATCH], dest, brief))
        note = write_note(video, length, scenes_from(rows, length))
        done += 1
        print(f"WROTE {note} ({done}/{len(pending)})", flush=True)
        STATUS.write_text(json.dumps({"done": done, "last": rel}, ensure_ascii=False), encoding="utf-8")
    for image in stills():
        if note_current(image):
            continue
        rel = image.relative_to(MATERIAL).as_posix()
        dest = FRAMES / "work" / rel.replace("/", "__")
        frame = still_frame(image, dest)
        print(f"START {rel} still", flush=True)
        rows = ask(image, [(0.0, frame)], dest, brief)
        scene = dict(rows[0])
        scene["source_in"] = 0.0
        scene["source_out"] = 0.0
        note = write_note(image, 0.0, [scene])
        done += 1
        print(f"WROTE {note} ({done})", flush=True)
    print("QUEUE_COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
