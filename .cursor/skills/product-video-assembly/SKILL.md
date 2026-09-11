---
name: product-video-assembly
description: Choose source clips from frozen lines, Gemini scenarios, and planned editorial narration durations. Use only when /product-video dispatches ASSEMBLY.
disable-model-invocation: true
---

# ASSEMBLY

Read this file only when dispatch says `product-video-assembly`.

Reuse the current material root from PREPARE. Do not inventory every file. Do not rewrite the approved script to fit a clip.

For each cut, inputs are:

- frozen approved line
- Gemini intended scenario
- planned editorial narration duration (`source_duration_seconds / 1.2`), not the raw source-file length

Preference:

1. Material must support the approved line.
2. Prefer a clip that reproduces the intended scenario.
3. Among valid candidates, prefer visual variety versus the previous cut.

If an exact scenario match is missing, use the closest semantically valid clip. Do not invent a new claim. Do not search forever.

Keep a compact shot plan on disk. Compare neighboring selected cuts from that plan, not from rereading all media.

Prove only the chosen range:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/produce-tiktok-product-video-portable/scripts/prove_source_range.py" --source <file> --in-sec <in> --out-sec <out> --output-dir <task-root>/evidence/<cut-id>
```

Do not place ChatCut clips here if ROUGH_EDIT already owns the case editor project. Do not create a second editor project.

Write `assembly-plan.json`, complete `ASSEMBLY`, return to `/product-video`. Next stage is ROUGH_EDIT.
