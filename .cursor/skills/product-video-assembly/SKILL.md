---
name: product-video-assembly
description: Choose source clips from frozen lines, Gemini scenarios, and planned editorial narration durations. Use only when /product-video dispatches ASSEMBLY.
disable-model-invocation: true
---

# ASSEMBLY

Read this file only when dispatch says `product-video-assembly`.

Reuse the current material root from PREPARE. Do not inventory every file. Do not rewrite the approved script to fit a clip. Do not analyze the whole library and do not run AI picture scoring. Do not place anything on ChatCut in this stage.

Load history, refresh the persistent material index, and refresh the visual scene catalog. Unchanged files are reused; only mtime/size/sidecar changes are updated. Do not re-watch the whole library.

Unobserved files (`needs_observation` or empty `scenes`) are a **one-time product-library onboarding** job, not an ASSEMBLY re-watch. List them with `visual_catalog.py --list-unobserved`. Write objective on-screen scenes (`source` / `source_in` / `source_out` / `objects` / `actions` / `product_state` / `location` / `framing` / `camera_distance` / `visible_features` / `factual_description`) and apply with `--observe-json`. Skip files that already have scenes. Do not use the folder name as scene content. Do not score picture quality. After onboarding, later cases refresh only changed files.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/approved_shots.py" --project-root <PROJECT_ROOT> --product-model <MODEL>
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/material_index.py" --project-root <PROJECT_ROOT> --product-model <MODEL> --material-root <MATERIAL_ROOT> --refresh
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/visual_catalog.py" --project-root <PROJECT_ROOT> --product-model <MODEL> --material-root <MATERIAL_ROOT> --refresh
```

Do not place a clip on ChatCut to learn its duration. Do not re-watch or re-probe a file whose stamp still matches the index or catalog. Sidecar files that already have scene / situation / in-out / description are ingested without watching video. Folder name alone is not scene content.

Finish the **edit-plan locally** for every cut before ROUGH_EDIT:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/edit_plan.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --product-model <MODEL>
```

That helper ranks duration-passing catalog + history + index candidates, then writes `assembly-plan.json` and `edit-plan.json`. Rank order:

1. semantic correctness for the frozen line / Gemini situation: human-adopted approved-shot history when line / situation / scene meaning is close, then deterministic visual catalog match on saved on-screen facts, then semantic fallback for unresolved cuts only (one Gemini 3.8 Flash text-only batch on saved catalog / history TEXT: `factual_description`, `actions`, `objects`, `visible_features`, `product_state`, approved-shot situation). Unresolved means history / deterministic catalog matching produced no duration-passing candidate. Do not watch video, score picture quality, or add per-script aliases. Save `semantic-material-match.json`. Skip Gemini when the deterministic matcher already has a duration-passing candidate. Do not pick a meaning-mismatched clip just to change the look
2. `available_duration >= target_duration_seconds` (playbackRate 1.2); exclude before ranking. If a meaning-matched history / visual catalog / semantic-fallback scene is at most 0.5s short and the same file is long enough, pad only the shortage with `fit_window` so the original scene range stays fully inside. Do not restart from 0s, do not use the whole file as the scene, and do not change playback speed. If no single meaning-matched scene still meets the target, stitch at most two meaning-matched scenes whose original ranges add up to the target. Stay inside each scene's original `source_in` / `source_out`. Do not loop, freeze, or change playback speed. Prefer those two scenes over a meaning-mismatched `search_aid`. Do not repeat the same two-scene order on the next cut when another pair exists. Write `video_segments` only for those cuts; every other cut stays one segment
3. among duration-passing meaning-matched candidates, prefer adjacent visual variety. A different source file is not a different picture. Treat clips as similar when `framing`, `camera_distance`, `location`, `subject` / `objects`, `action`, and `product_state` are almost the same. Prefer the candidate with the larger `visual_diff_score` / adjacent visual diff versus the previous cut, and when possible also versus the cut before that so the same framing / subject / action / location do not run three times. If only one appropriate clip exists, use it; do not HOLD
4. then history / visual catalog match score
5. then spread sources across the whole video; if the same source is reused, use a different catalog scene range and do not repeat a 0s full-clip window. Source spread must not outrank adjacent visual variety
6. aliases / classification folder as candidate-search helpers only

Do not treat a single generic alias (`車内`, `ハンドル`, `設置`, `ミラー`, `日差し`) as proof that the picture matches the line. Do not copy the requested Gemini situation onto a material entry that has no situation. Keep requested situation as `intended_scenario`. Folder meaning is product-level, not per-script. Load `config/product_video_material_aliases_<MODEL>.v1.json` into `.runtime/product-video-material-index/<MODEL>.semantic-aliases.v1.json`. Do not rewrite material sidecars or aliases to match this case's frozen lines. Do not add a new quality HOLD.

If a candidate has `source_in` / `source_out` (or a scene range in md), `available_duration = source_out - source_in`. A full clip uses the md source duration. A history shot with a short range is not adopted, except the 0.5s same-file pad above.

`edit-plan.json` already has narration duration, target duration, video source/in/out, timeline start/end, exact caption text, and display wrap. Cuts that needed two meaning-matched scenes also have `video_segments`. Do not leave wrap or clip choice for ChatCut.

Prove only the chosen range, once per segment:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/produce-tiktok-product-video-portable/scripts/prove_source_range.py" --source <file> --in-sec <in> --out-sec <out> --output-dir <task-root>/evidence/<cut-id>
```

Do not create a second editor project. Complete `ASSEMBLY`, return to `/product-video`. Next stage is ROUGH_EDIT.
