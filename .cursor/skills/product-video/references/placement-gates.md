# ChatCut placement MUST gates (A–D)

Use these gates on every case. They exist because AN-S152 (`pv-AN-S152-20260926T114914Z`) placed video before corrupt TTS was found, placed a `visual_match: false` / score 0 cut, and ran audio and video as independent tracks.

Do not treat file extensions, tool-success JSON, or a filled ChatCut timeline as proof.

## Gate A — TTS pre-placement decode

**MUST** run before any ChatCut audio import or `place_audio`.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/validate_tts_audio.py" \
  --project-root <PROJECT_ROOT> --case-id <CASE_ID> --manifest
```

For one file:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/validate_tts_audio.py" --audio-path <path> --cut-id <cut-id>
```

Pass criteria (all required; extension/name is **not** a pass):

1. Regular file, size > 0
2. `ffprobe` reports at least one `codec_type=audio` stream
3. Container `duration` > 0
4. `ffmpeg` decodes a sample (`-t 1` or the full file if shorter) to null with exit 0 and no error on stderr

A `.mp3` that is a broken CapCut AAC payload **MUST** fail. CDN 403 / missing bytes **MUST** fail.

On fail:

- Do **not** import or place that file
- Mark the clip invalid (`outputs/<case>/tts/invalid-clips.json`) and move the bytes off the placement path (`outputs/<case>/tts/invalid/`)
- Immediately regenerate that cut on the existing CapCut Holiday Twist session / `product-video-narration` queue
- Re-run Gate A on the new file before it re-enters the placement path

Do not write a failed file into `narration-manifest.json`.

## Gate B — Weak visual_match early stop

**MUST** run at ASSEMBLY / `edit_plan.py` time, **before** ChatCut video placement.

Existing threshold: `visual_match` is true **and** `visual_match_score >= 1` (same as `score > 0` in `annotate_visual_match`).

Any narration-target cut below that threshold **MUST** either:

1. Search the catalog / remaining duration-passing candidates, adopt a passing alternate, and rewrite `assembly-plan.json` / `edit-plan.json`, or
2. Stop with `HOLD_WEAK_VISUAL_MATCH` and ask the operator **in that turn** with `cut_id`, score, current asset (source + in/out), and proposed alternate options

`edit_plan.py` already calls this gate. Do not write a lockable `edit-plan.json` while any cut is still weak unless `outputs/<case>/operator-visual-match.json` records an explicit operator accept for that cut.

Placement **MUST NOT** proceed past that cut until it is resolved. Do not discover a weak match only after ChatCut is filled.

## Gate C — Serialize audio, then lock video

**MUST** order:

1. Gate A on every narration file
2. Import valid audio only (`import_audio_batch`, max 4 files per `import_media` session)
3. `place_audio` + `set_playback_rate`
4. Only then import video / place video / captions (`import_video_batch` → `place_video` → `caption_preset` → `place_captions` → `final_verify`)

Do **not** run video placement and TTS regeneration/placement as independent parallel tracks. If any audio is invalid or still regenerating, keep ChatCut video placement deferred. A project that already has video from an older run is provisional until Gate A + audio placement succeed; do not tell the operator 粗編集 is done.

`edit-plan.json` `chatcut_steps` encodes this order. Do not reorder it. Do not mix audio and video in the same import batch.

## Gate D — Progress heartbeats

Any placement, import, regenerate, or decode-wait expected to take **> 30 seconds MUST** emit a short operator-facing progress line at least every ~30 seconds:

- stage name
- what just finished
- next step

Example: `ROUGH_EDIT: Gate A passed (12/12). Next: import_audio_batch 1/3.`

Do not stay silent through CapCut regenerate queues or ChatCut import. Timing numbers still go only to `timing.json`; heartbeats are the exception to “no mid-stage chat.” Successful individual NARRATION cuts still skip a per-cut celebration; a 30s heartbeat during a long queue is required.
