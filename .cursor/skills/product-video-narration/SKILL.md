---
name: product-video-narration
description: Generate 1.2x narration from the frozen approved script. Use only when /product-video dispatches NARRATION.
disable-model-invocation: true
---

# NARRATION

Read this file only when dispatch says `product-video-narration`.

Use only the approved script. Speed is always **1.2x**. Do not run a speed-selection algorithm.
SCRIPT LINE == NARRATION == TELOP. Do not trim, strip, ignore newlines or zero-width characters, or treat visible/OCR text as a match.

For every frozen line from `approved-script.json`:

1. Identify the CapCut TTS input field.
2. Completely empty it. Do not append.
3. Write that frozen line only.
4. Read the **actual** input/textarea/contenteditable value. Screenshots and OCR are not proof.
5. Compare with raw string exact equality. Diagnose mismatches with expected/actual length, Python `repr`, diff index, and Unicode code points.
6. On mismatch, clear completely, write the frozen line again, and re-read once. Input retries do not increment `generation_count_for_cut`.
7. Gate generation only after exact match:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/prepare_tts_field.py" --frozen-json '<json string>' --actual-json '<json string>' --attempt <1|2> --generation-count <n>
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/prove_tts_textarea.py" --record-json '<record>'
```

Generate only when `prepare_tts_field.py` reports `exact_match: true` **and** `prove_tts_textarea.py` returns `generate: true`. A tool-success JSON is not a match. If the second read-back still mismatches, or the actual field value cannot be obtained, stop with `HOLD_TTS_INPUT_FIELD_UNVERIFIED`. Do not click 生成 before exact match.

8. Save audio with the existing capture helper into the case TTS directory. Do not use Downloads or a save dialog.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/produce-tiktok-product-video-portable/scripts/capture_capcut_result_audio.py" --url <result-src> --output <task-root>/tts/<cut-id>.mp3
```
9. Measure actual playback duration. Record path + duration. Do not judge voice quality. Stop only for wrong text, mixed leftover text, missing audio, or corrupt/truncated output.

After every cut is recorded, write `narration-manifest.json` with speed `1.2` and complete `NARRATION`. Return to `/product-video`. Next stage is ASSEMBLY.
