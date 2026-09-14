---
name: product-video-assembly
description: Choose source clips from frozen lines, Gemini scenarios, and planned editorial narration durations. Use only when /product-video dispatches ASSEMBLY.
disable-model-invocation: true
---

# ASSEMBLY

Read this file only when dispatch says `product-video-assembly`.

Reuse the current material root from PREPARE. Do not inventory every file. Do not rewrite the approved script to fit a clip. Do not analyze the whole library and do not run AI picture scoring. Do not place anything on ChatCut in this stage.

Load history and refresh the persistent material index. Unchanged files are reused from `.runtime/product-video-material-index/<MODEL>.v1.json`; only mtime/size/sidecar changes are updated.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/approved_shots.py" --project-root <PROJECT_ROOT> --product-model <MODEL>
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/material_index.py" --project-root <PROJECT_ROOT> --product-model <MODEL> --material-root <MATERIAL_ROOT> --refresh
```

Do not place a clip on ChatCut to learn its duration. Do not re-watch or re-probe a file whose stamp still matches the index.

Finish the **edit-plan locally** for every cut before ROUGH_EDIT:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/edit_plan.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --product-model <MODEL>
```

That helper ranks duration-passing index + history candidates, then writes `assembly-plan.json` and `edit-plan.json`. Rank order:

1. the frozen line's meaning (sidecar situation exact, sidecar tags, classification folder, then product-level folder aliases)
2. `available_duration >= target_duration_seconds` (playbackRate 1.2); exclude before ranking
3. Gemini situation
4. approved-shot history
5. avoid the same source and framing as the previous cut

Folder meaning is product-level, not per-script. Load `config/product_video_material_aliases_<MODEL>.v1.json` into `.runtime/product-video-material-index/<MODEL>.semantic-aliases.v1.json`. Do not rewrite material sidecars to match this case's frozen lines. Do not add per-script aliases. Do not add a new quality HOLD.

If a candidate has `source_in` / `source_out` (or a scene range in md), `available_duration = source_out - source_in`. A full clip uses the md source duration. A history shot with a short range is not adopted.

`edit-plan.json` already has narration duration, target duration, video source/in/out, timeline start/end, exact caption text, and display wrap. Do not leave wrap or clip choice for ChatCut.

Prove only the chosen range:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/produce-tiktok-product-video-portable/scripts/prove_source_range.py" --source <file> --in-sec <in> --out-sec <out> --output-dir <task-root>/evidence/<cut-id>
```

Do not create a second editor project. Complete `ASSEMBLY`, return to `/product-video`. Next stage is ROUGH_EDIT.
