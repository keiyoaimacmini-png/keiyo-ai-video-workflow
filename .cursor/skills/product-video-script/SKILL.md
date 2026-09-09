---
name: product-video-script
description: Generate 3-5 Gemini script variants and wait for explicit 案Nで台本OK. Use only when /product-video dispatches SCRIPT.
disable-model-invocation: true
---

# SCRIPT

Read this file only when dispatch says `product-video-script`.

Read [gemini-script-instructions.md](../product-video/references/gemini-script-instructions.md) only to confirm the prompt template. Do not rewrite it.

1. Render the prompt from verified inputs:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/render_script_prompt.py" --project-root <PROJECT_ROOT> --product-information "<verified>" --appeal-points "<verified>" --campaign-focus "<optional>" --output <task-root>/gemini-script-prompt.txt
```

2. Send with the existing Gemini transport. Do not use Gemini.app, the Gemini API, or `GEMINI_API_KEY`:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/produce-tiktok-product-video-portable/scripts/send_gemini_cli_prompt.py" --prompt-file <task-root>/gemini-script-prompt.txt
```

If that helper HOLDs, stop with that HOLD.

3. Parse and store variants:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/script_stage.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --gemini-output <task-root>/gemini-output.txt
```

4. Present the 3–5 options in Japanese. Stop. Accept only exact `案Nで台本OK`. Do not convert another phrase into approval.

After approval, `/product-video` freezes the selected variant. Every later line is immutable: SCRIPT LINE == NARRATION == TELOP.
