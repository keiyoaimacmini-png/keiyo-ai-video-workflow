---
name: product-video-narration
description: Generate 1.2x narration from the frozen approved script. Use only when /product-video dispatches NARRATION.
disable-model-invocation: true
---

# NARRATION

Read this file only when dispatch says `product-video-narration`.

Use only the approved script. Speed is always **1.2x**. Do not run a speed-selection algorithm.
SCRIPT LINE == NARRATION == TELOP. Do not trim, strip, ignore newlines or zero-width characters, or treat visible/OCR/document-HTML text as a match.

Load this cut's `generation_count_for_cut` from `tts/generation-attempts.json`. Never reset it to 0 after a failed generate. If the previous outcome is `unknown`, do not submit again; observe the existing result.

For every frozen line from `approved-script.json`:

1. Identify the CapCut TTS input field.
2. Completely empty it. Do not append.
3. Write that frozen line only.
4. Prove the text CapCut will submit. Priority:
   1. CapCut editor internal model / effective editor value
   2. TTS submission application state
   3. contenteditable DOM nodes, only when user-authored text nodes are distinguished from CapCut-owned independent structural sentinel nodes
5. Do not use document HTML, preview, OCR, or visible text as proof. Do not `trim` / `strip` / Unicode-normalize / `replace("\u200B", "")`. Exclude U+200B only as a proven independent CapCut sentinel node. If that distinction is impossible, stop with `HOLD_TTS_INPUT_FIELD_UNVERIFIED`.
6. `effective_tts_text` must raw-equal the frozen line. On mismatch, clear, rewrite, and re-read once. Input retries do not increment `generation_count_for_cut`.
7. Read back the live CapCut speed value. `onSpeedChange(1.2)` is not proof. Generate only when `actual_speed == 1.2`. Otherwise `HOLD_TTS_SPEED_UNVERIFIED`.
8. Gate generation:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/resolve_tts_text.py" --frozen-json '<json string>' --observation-json '<observation>'
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/prepare_tts_field.py" --frozen-json '<json string>' --actual-json '<effective_tts_text json>' --attempt <1|2> --generation-count <n>
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/prove_tts_speed.py" --record-json '<speed record>'
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/tts_attempts.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --cut-id <cut-id> --may-generate
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/prove_tts_textarea.py" --record-json '<record>'
```

Generate only when text exact-match, `actual_speed == 1.2`, `prove_tts_textarea.py` returns `generate: true`, and `tts_attempts.py --may-generate` allows it. `MAX_GENERATIONS_PER_CUT` is 2. Do not click 生成 before those gates.

9. After CapCut answers, record the attempt even when there is no audio:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/tts_attempts.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --cut-id <cut-id> --record-outcome <success|failure|unknown>
```

A CapCut failure does not adopt audio. It still increments the cut's generation count.

10. On success, save audio with the existing capture helper into the case TTS directory. Do not use Downloads or a save dialog.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/produce-tiktok-product-video-portable/scripts/capture_capcut_result_audio.py" --url <result-src> --output <task-root>/tts/<cut-id>.mp3
```
11. Measure actual playback duration. Record path + duration. Do not judge voice quality. Stop only for wrong text, mixed leftover text, missing audio, or corrupt/truncated output.

After every cut is recorded, write `narration-manifest.json` with speed `1.2` and complete `NARRATION`. Return to `/product-video`. Next stage is ASSEMBLY.
