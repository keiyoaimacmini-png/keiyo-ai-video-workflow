---
name: product-video-assembly-20260925
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
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/compile_material_ledger.py" --project-root <PROJECT_ROOT> --product-model <MODEL> --material-root <MATERIAL_ROOT>
```

Compile reads the open Obsidian vault and writes current notes into the visual catalog. If it returns `HOLD_OBSIDIAN_NOT_OPEN` or `HOLD_MATERIAL_LEDGER_VAULT_MISSING`, stop with that HOLD. If `status` is `needs_vision`, run `material_ledger_observe.py` for this model, then compile again. Do not place clips until compile returns `status` `OK`.

Do not place a clip on ChatCut to learn its duration. Do not re-watch or re-probe a file whose stamp still matches the index or catalog. Sidecar files that already have scene / situation / in-out / description are ingested without watching video. Folder name alone is not scene content.

Finish the **edit-plan locally** for every cut before ROUGH_EDIT:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/edit_plan.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --product-model <MODEL>
```

That helper ranks duration-passing catalog + history + index candidates, then writes `assembly-plan.json` and `edit-plan.json`. **MUST** follow 02 の Gate B (`${PROJECT_ROOT}/.cursor/skills/product-video/references/placement-gates.md`) before ChatCut. A weak result uses `HOLD_WEAK_VISUAL_MATCH` and is resolved by the Gate B procedure before placement.

Rank order:

1. semantic correctness for the frozen line / Gemini situation: human-adopted approved-shot history when line / situation / scene meaning is close, then deterministic visual catalog match on saved on-screen facts. Unresolved means that match produced no duration-passing candidate. For those cuts, host code uses the one duration-qualified scene when only one exists. When two or more remain, `edit_plan.py` returns `needs_jev_rank` and `jev-rank-requests.json`. Call `jev_rank` once per listed cut. `query` is that cut's `query`. `candidates` are that cut's `id` / `text` pairs. Do not send file bytes, passwords, or tokens. Adopt the top candidate only when the result says it answers the line, `action` is `auto`, and `coverage` is `complete`. `review`, `escalate`, incomplete coverage, or a ranking that does not say the top candidate answers are not a match. Write `outputs/<case>/jev-rank-results.json` as `{"cuts": {"<cut_id>": {"scene_id": "<candidate id>", "answers": true, "action": "auto", "coverage": "complete"}}}` using only ids from that cut, then run `edit_plan.py` again. Do not call Gemini for this meaning choice. Do not watch video, score picture quality, or add per-script aliases. Do not pick a meaning-mismatched clip just to change the look
2. `available_duration >= target_duration_seconds` (playbackRate 1.2); exclude before ranking. If a meaning-matched history / visual catalog / semantic-fallback scene is shorter than the target and the same file can hold a window of that length which fully contains the original scene range, extend only the shortage into adjacent frames (after the scene first, then before it). Do not restart from 0s, do not use the whole file as the scene, and do not change playback speed. Do not extend into a different catalog scene on the same file; stop at that boundary. If that window still cannot meet the target, stitch at most two meaning-matched scenes whose original ranges add up to the target. Stay inside each stitched scene's original `source_in` / `source_out`. Do not loop, freeze, or change playback speed. Prefer those two scenes over a meaning-mismatched `search_aid`. Do not repeat the same two-scene order on the next cut when another pair exists. Write `video_segments` only for those cuts; every other cut stays one segment
3. among duration-passing meaning-matched candidates, prefer adjacent visual variety. A different source file is not a different picture. Treat clips as similar when `framing`, `camera_distance`, `location`, `subject` / `objects`, `action`, and `product_state` are almost the same. Prefer the candidate with the larger `visual_diff_score` / adjacent visual diff versus the previous cut, and when possible also versus the cut before that so the same framing / subject / action / location do not run three times. If only one appropriate clip exists, use it; do not HOLD
4. then history / visual catalog match score
5. then spread sources across the whole video; if the same source is reused, use a different catalog scene range and do not repeat a 0s full-clip window. Source spread must not outrank adjacent visual variety
6. aliases / classification folder as candidate-search helpers only

Do not treat a single generic alias (`車内`, `ハンドル`, `設置`, `ミラー`, `日差し`) as proof that the picture matches the line. Do not copy the requested Gemini situation onto a material entry that has no situation. Keep requested situation as `intended_scenario`. Folder meaning is product-level, not per-script. Load `config/product_video_material_aliases_<MODEL>.v1.json` into `.runtime/product-video-material-index/<MODEL>.semantic-aliases.v1.json`. Do not rewrite material sidecars or aliases to match this case's frozen lines. Do not add a new quality HOLD.

If a candidate has `source_in` / `source_out` (or a scene range in md), `available_duration = source_out - source_in`. A full clip uses the md source duration. A history shot with a short range is not adopted, except the same-file shortage window above.

`edit-plan.json` already has narration duration, target duration, video source/in/out, timeline start/end, exact caption text, and display wrap. Cuts that needed two meaning-matched scenes also have `video_segments`. Do not leave wrap or clip choice for ChatCut.

Before locking that plan, read `edit_rules` in `config/product_video_product_facts_<MODEL>.v1.json`. Apply those product-note rules with the generic picture rules; product rules do not waive the generic rules. A product note may define additional HOLDs, but the note must be reflected in the plan or inspection evidence before the 01 acceptance condition is met.

製品ノートに定義された場合に返る停止コード：`HOLD_LAMP_COLOR_UNSTATED`、`HOLD_LAMP_COLOR_FRAME_REQUIRED`

- Do not place nearly the same subject, framing, distance, location, and action on adjacent cuts. A different file is still the same picture when those match.
- When the frozen line names a visible state, the chosen range must show that state. Do not use footage of a different state, and do not cover that cut with a graphic that also shows the other states.
- Use an official published still only when the chosen video would otherwise repeat the previous cut, the still matches that cut's telop, the video does not already perform the spoken action, and the cut is not the first cut. Do not put a still on every cut.
- That still sits on a higher track over the video, as the main image, with video still visible beside and below it. It does not fill the frame.
- Write any such overlay into `edit-plan.json` before ChatCut.

Prove only the chosen range, once per segment:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/prove_source_range.py" --source <file> --in-sec <in> --out-sec <out> --output-dir <task-root>/evidence/<cut-id>
```

Do not create a second editor project. Complete `ASSEMBLY`, return to `/product-video`. Next stage is ROUGH_EDIT.
