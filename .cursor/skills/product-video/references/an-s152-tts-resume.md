# AN-S152 TTS resume runbook

Resume only. Do not create a new product SKU, a new case, or a successor ChatCut project.

## Case facts

- Case: `pv-AN-S152-20260926T114914Z`
- Product: `AN-S152`
- Stage: `ROUGH_EDIT`
- ChatCut project (already exists): `1efe9c90-a18b-4655-abc8-93a5284067c3`
- Already on the timeline: V1 video + motion-graphic overlays
- Missing: Holiday Twist TTS is **not** placed
- Editor rate for this model: ChatCut audio `playbackRate` **1.5** (not 1.2)
- Known leftover: cut **c7** was planned with `visual_match: false` / score 0

This case is **provisional**. Do not tell the operator 粗編集 is done until the steps below finish.

Follow [placement-gates.md](placement-gates.md) gates A–D. Heartbeat at least every ~30s.

## 1. Target the existing ChatCut project

Target `1efe9c90-a18b-4655-abc8-93a5284067c3`. Do not `create_project`. Confirm V1 video + overlays are still there. Do not place or re-place video in this resume.

## 2. CapCut regenerate c1–c12

Use the existing NARRATION queue / CapCut official Text to Speech + Holiday Twist session on the already-running Chrome + Playwright MCP (`--cdp-endpoint=chrome`).

- Frozen line only, one cut at a time
- Do not paste c1–c12 as one bulk generate
- Do not put picture into CapCut
- Capture each new result with `capture_capcut_result_audio.py` into this case's `tts/` working directory
- Existing-balance `Credits will be consumed` → Got it. Do not buy credits or start a Pro contract

If a previous `*.mp3` is a corrupt CapCut AAC payload, treat it as invalid (Gate A). Do not import it. Do not retry a CDN URL that already 403'd.

## 3. Gate A — decode validate

After each capture, and again before any ChatCut audio import:

```bash
python3 .cursor/skills/product-video/scripts/validate_tts_audio.py \
  --project-root . --case-id pv-AN-S152-20260926T114914Z --manifest
```

Pass = audio stream + duration > 0 + ffmpeg decode sample. Extension is not trusted.

On fail: mark that cut invalid, move the file off the placement path, regenerate that cut only, then re-validate.

## 4. Import audio only (batch ≤ 4)

Only after every c1–c12 file passes Gate A:

- `import_media` sessions of **at most 4 audio files**
- Do not import video again
- Do not start video placement in parallel

## 5. Place TTS at playbackRate 1.5

Place one audio clip per cut on the existing narration spans. Set ChatCut clip `playbackRate` to **1.5**. Do not FFmpeg-accelerate the source. Do not apply 1.2.

## 6. Verify timeline

Read the timeline back. Prove:

- Every narration-target cut has an audio item
- `playbackRate` is 1.5
- Frozen line == placed audio identity (no leftover/wrong sentence file)
- V1 video + overlays are still the ones already on the project
- Captions still match frozen lines if they were already placed

This is `final_verify` for the resume, not a new visual-quality review.

## 7. c7 weak visual_match — still open

c7 is **not** resolved by placing TTS. Before asking the operator that 粗編集 is ready:

- Re-search the AN-S152 visual catalog for a duration-passing alternate with `visual_match` true and score ≥ 1, or
- Ask the operator to confirm the current c7 asset or pick an alternate (`cut_id`, score, current source/in/out, proposed options)

Do not leave `visual_match: false` / score 0 undisclosed.

## 8. Only then ask for 粗編集OK

When Gate A passed, audio is placed at 1.5, timeline verify passed, and c7 is either re-searched or explicitly waiting on the operator:

粗編集の音声まで置きました。ChatCut で確認・修正してください。
c7 の画が弱い場合は、そのカットだけ差し替えか承認が必要です。
確認後「粗編集OK」と送ってください。完成・格納は別フレーズです。

Do not export. Do not Drive 格納. Do not purge.
