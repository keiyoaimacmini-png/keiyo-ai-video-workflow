# Craft gates

Craft gates run on lightweight artifacts **before** a checkpoint. Schema-valid is not quality-valid. A failing gate is `HOLD_CRAFT_QUALITY`. Repair the draft and rerun. Do not ask for an OK phrase while it fails.

Load lessons for that surface, then validate:

```bash
python3 "${SKILL_ROOT}/scripts/validate_craft_quality.py" \
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
- An active script lesson's `bad` pair or `gate` matches.

Gemini paste text must include each active script lesson's rejected and accepted pair. Render with v3 `render_gemini_web_prompt.py`, not the portable renderer alone.

## picture — before `粗編集OK`

Artifact: `product_video_picture_selection.v1` with, for each cut, the claimed action, the chosen range, compared candidates, and whether the chosen range defaults to the first N seconds.

Fail when:

- The chosen range is the first N seconds of a usable take without a compared alternative.
- `action_centered` is false (in/mid/out do not show the claimed action as the point of the range).
- No rejected-candidate reason exists when more than one usable range was available.
- An active picture lesson matches.

in/mid/out frames still belong to the portable media proof. This gate is the **selection** proof.

## captions — before `完成・書き出しOK`

Artifact: `product_video_caption_craft.v1` from **composed frames**, not caption JSON geometry.

Fail when JSON geometry is the only evidence, captions are not centered on screen, more than one visible layer remains, wrapping changed frozen characters, or prominence (weight, stroke, contrast band) is missing.

## tts-timing — before `完成・書き出しOK`

Artifact: `product_video_tts_craft.v1`. Still run the portable slack / track-pairing / timeline-integrity validators on their receipts. This gate adds perceptual misses those receipts do not cover.

Fail when a combined bulk clip is left on the timeline, a cut is inside speech, a scene gap is outside 400–1200 ms, speech is too fast to hear, or three-layer closure is missing.

## HOLD

`HOLD_CRAFT_QUALITY` preserves the current case. It is not `台本OK` / `粗編集OK` / `完成・書き出しOK`. Portable HOLDs from the safety engine still apply for login, materials, Drive, and unknown export/upload.
