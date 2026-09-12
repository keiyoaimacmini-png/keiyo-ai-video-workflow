---
name: product-video-script
description: Generate 3-5 Gemini script variants and wait for explicit 案Nで台本OK. Use only when /product-video dispatches SCRIPT.
disable-model-invocation: true
---

# SCRIPT

Read this file only when dispatch says `product-video-script`.

Read [gemini-script-instructions.md](../product-video/references/gemini-script-instructions.md) only to confirm the prompt template. Do not rewrite it.

Do not modify a completed case, approved script, export, or Drive object. This stage applies to the current new case only.

1. Render the prompt from verified inputs. The helper attaches stable F-IDs to `PRODUCT_INFORMATION` and `PRODUCT_APPEAL_POINTS`. Identifier-only lines (型番 / JAN / ASIN / 商品コード) are not grounding facts:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/render_script_prompt.py" --project-root <PROJECT_ROOT> --product-information "<verified>" --appeal-points "<verified>" --campaign-focus "<optional>" --output <task-root>/gemini-script-prompt.txt
```

2. Send with the existing Gemini transport. Do not use Gemini.app, the Gemini API, or `GEMINI_API_KEY`:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/produce-tiktok-product-video-portable/scripts/send_gemini_cli_prompt.py" --prompt-file <task-root>/gemini-script-prompt.txt
```

If that helper HOLDs, stop with that HOLD.

3. Parse, prove product grounding, and store variants:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/script_stage.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --gemini-output <task-root>/gemini-output.txt
```

Grounding is objective product-fact use in the spoken lines. Gemini 根拠ID values are hints, not a letter-perfect classification test. Do not HOLD only because a line's actual fact differs from the assigned F-ID. Do not add a subjective quality review.

If the helper returns `HOLD_SCRIPT_PRODUCT_GROUNDING` and `regenerate` is true, send the **same** rendered prompt once more and run `script_stage.py` again. Do not present variants. Do not regenerate a third time.

If the second output also fails grounding, or `regenerate` is false, stop with `HOLD_SCRIPT_PRODUCT_GROUNDING`.

4. Present the 3–5 options in Japanese from `operator_variants`. Do **not** show `根拠ID` or `evidence_ids`. If you need a stripped copy:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/script_grounding.py" --present <task-root>/script-variants.json
```

Stop. Accept only exact `案Nで台本OK`. Do not convert another phrase into approval.

After approval, `/product-video` freezes the selected variant. Frozen lines omit grounding IDs. Every later line is immutable: SCRIPT LINE == NARRATION == TELOP.
