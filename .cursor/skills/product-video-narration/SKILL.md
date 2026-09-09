---
name: product-video-narration
description: Generate 1.2x narration from the frozen approved script. Use only when /product-video dispatches NARRATION.
disable-model-invocation: true
---

# NARRATION

Read this file only when dispatch says `product-video-narration`.

Use only the approved script. Speed is always **1.2x**. Do not run a speed-selection algorithm.

For every frozen line:

1. Target the CapCut TTS input field.
2. Replace the existing contents completely with that line only.
3. Read the field back.
4. Gate generation:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/produce-tiktok-product-video-portable/scripts/prove_tts_textarea.py" --record-json '<record>'
```

Generate only when that helper returns `generate: true`. A tool-success JSON is not a match.

5. Save audio with the existing capture helper into the case TTS directory. Do not use Downloads or a save dialog.
6. Measure actual playback duration. Record path + duration. Do not judge voice quality. Stop only for wrong text, mixed leftover text, missing audio, or corrupt/truncated output.

After every cut is recorded, write `narration-manifest.json` with speed `1.2` and complete `NARRATION`. Return to `/product-video`. Next stage is ASSEMBLY.
