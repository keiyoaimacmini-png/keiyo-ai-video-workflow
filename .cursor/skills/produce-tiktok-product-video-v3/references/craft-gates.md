# Craft gates

These checks run on the current draft **before** a checkpoint. They encode standing first-pass rules from `config/product-video-rules/`. Schema-valid is not quality-valid. A failing gate is `HOLD_CRAFT_QUALITY`. Repair the draft and rerun. Do not ask for an OK phrase while it fails. Do not wait for an operator correction to discover these misses.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/produce-tiktok-product-video-v3/scripts/validate_craft_quality.py" \
  --project-root <project-root> \
  --product-model <model> \
  --surface <script|picture|captions|tts-timing> \
  --artifact <artifact.json>
```

## script — before `台本OK`

Artifact: spoken dialogue (`product_video_craft_script.v1`, a script package, a Gemini draft, or a production payload `script` array).

Fail when:

- The six-stage spoken order is missing or reversed.
- `problem_resolution` restates `result`.
- A hook problem is closed by looks or blocked sunlight without a spoken solution to that problem.
- Non-CTA lines end in instruction-sheet register (`します` / `してみて` / `あるよ` / `できます`).

Use the portable Gemini paste renderer. Do not inject prior-correction examples.

## picture — before `粗編集OK`

Artifact: `product_video_picture_selection.v1` with, for each cut, `narrative_role`, the claimed action of that frozen line, the chosen range, compared candidates, and whether the chosen range defaults to the first N seconds.

Fail when:

- The chosen range is the first N seconds of a usable take without a compared alternative.
- `action_centered` is false, or `range_covers_claimed_action` is false.
- Consecutive cuts read as the same kind of shot continuing (place, distance, and camera angle). Related sequential actions are allowed. Different files are not enough. `look_reads_different_from_previous` is about that framing, not about topic closeness.
- No rejected-candidate reason exists when more than one usable range was available.

in/mid/out frames still belong to the portable media proof. This gate is the selection proof.

## captions — before `完成・書き出しOK`

Artifact: `product_video_caption_craft.v1` from **composed frames**, not caption JSON geometry.

Fail when JSON geometry is the only evidence, captions are not centered on screen, more than one visible layer remains, wrapping changed frozen characters, or prominence (weight, stroke, contrast band) is missing.

## tts-timing — before `完成・書き出しOK`

Artifact: `product_video_tts_craft.v1`. Still run the portable slack / track-pairing / timeline-integrity validators on their receipts.

Fail when a combined bulk clip is left on the timeline, per-cut generation is missing, a cut is inside speech or off the frozen line, speech is too fast to hear, unused picture was not trimmed to that cut's audible speech, or three-layer closure is missing.

## HOLD

`HOLD_CRAFT_QUALITY` preserves the current case. It is not `台本OK` / `粗編集OK` / `完成・書き出しOK`. Portable HOLDs from the safety engine still apply for login, materials, Drive, and unknown export/upload.
