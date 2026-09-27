---
name: product-video-script-20260925
description: Generate 3-5 Gemini script variants and wait for explicit 案Nで台本OK. Use only when /product-video dispatches SCRIPT.
disable-model-invocation: true
---

# SCRIPT

Read this file only when dispatch says `product-video-script`.
When this Skill's behavior changes, rename the folder and frontmatter `name` date (`YYYYMMDD`) together. Keep the logical dispatch id.

Read [gemini-script-instructions.md](../product-video/references/gemini-script-instructions.md) only to confirm the prompt template. Do not rewrite it.

Do not modify a completed case, approved script, export, or Drive object. This stage applies to the current new case only.

1. Compile the Obsidian material notes into the visual catalog before rendering the prompt. Obsidian must already be open on this Mac. Do not re-watch a video whose note matches that file's size and mtime.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/compile_material_ledger.py" --project-root <PROJECT_ROOT> --product-model <MODEL>
```

If the helper returns `HOLD_OBSIDIAN_NOT_OPEN` or `HOLD_MATERIAL_LEDGER_VAULT_MISSING`, stop with that HOLD. If `status` is `needs_vision`, watch only those files with Gemini 3.8 Flash stills, then compile again:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/material_ledger_observe.py" --project-root <PROJECT_ROOT> --product-model <MODEL>
```

The observer skips current notes. If it HOLDs, stop with that HOLD. Do not start the script until compile returns `status` `OK`.

2. Render the prompt from verified inputs. Pass `--product-model` so the prompt includes ledger scene descriptions and not file names or in/out. The helper attaches stable F-IDs to `PRODUCT_INFORMATION` and `PRODUCT_APPEAL_POINTS`. Identifier-only lines (型番 / JAN / ASIN / 商品コード) are not grounding facts:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/render_script_prompt.py" --project-root <PROJECT_ROOT> --product-model <MODEL> --product-information "<verified>" --appeal-points "<verified>" --campaign-focus "<optional>" --output <task-root>/gemini-script-prompt.txt
```

If `config/product_video_script_rules_<MODEL>.v1.json` exists, the renderer adds its `rules` to the campaign focus. Do not paste that file, or any other rule file, into the prompt by hand.

3. Send with the existing Gemini transport. Do not use Gemini.app, the Gemini API, or `GEMINI_API_KEY`:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/send_gemini_cli_prompt.py" --prompt-file <task-root>/gemini-script-prompt.txt
```

If that helper HOLDs, stop with that HOLD.

4. Parse, prove product grounding, and store variants:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/script_stage.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --gemini-output <task-root>/gemini-output.txt
```

Grounding is objective product-fact use in the spoken lines. Gemini 根拠ID values are hints, not a letter-perfect classification test. Do not HOLD only because a line's actual fact differs from the assigned F-ID. Do not add a subjective quality review.

If the helper returns `HOLD_SCRIPT_PRODUCT_GROUNDING`, repair the failing spoken lines in the same turn and run `script_stage.py` again. Do not stop the operator. Do not present variants that fail the check.

Repair only the failing lines, using the verified product facts already in the case:
- Drop a number that is not in those facts. Keep the fact that is already in the line.
- Replace 「慶洋エンジニアリング」 with the product type name from those facts. Do not add a new specification, effect, or number.
- Product script-rule violations use this same repair path.
- A spoken line that would play longer than about 3 seconds at 1.2x is too long. Shorten it or split it into another cut in this same repair. Keep one cut longer only when a single verified fact cannot be said in about 3 seconds. Do not add words to fill time. Do not write a line longer than one ledger scene can cover.

Repeat until `script_stage.py` returns `status` `OK`.

5. Present the 3–5 options in Japanese from `operator_variants`. Do **not** show `根拠ID` or `evidence_ids`. If you need a stripped copy:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/script_grounding.py" --present <task-root>/script-variants.json
```

Stop. Accept only exact `案Nで台本OK`. Do not convert another phrase into approval.

After approval, `/product-video` freezes the selected variant. Frozen lines omit grounding IDs. Every later line is immutable: SCRIPT LINE == NARRATION == TELOP.
