---
name: produce-tiktok-product-video-v3
description: Legacy craft-check package. Not the production entry. Use /product-video instead. Not invoked by the new runtime.
disable-model-invocation: true
---

# Product-video craft checks (legacy)

Production starts from `/product-video`. This directory is not on the new runtime path. Standing quality rules live in `$PROJECT_ROOT/config/product-video-rules/`. Do not copy Drive, TTS, or payload procedures here.

Resolve `PROJECT_ROOT` to the product project's trusted root. Resolve `SAFETY_SKILL_ROOT` to `$PROJECT_ROOT/.cursor/skills/produce-tiktok-product-video-portable`.

## Always load

1. [references/methods.md](references/methods.md)
2. [references/craft-gates.md](references/craft-gates.md)
3. [references/safety-engine.md](references/safety-engine.md)

Do not load chat transcripts or correction archives as rules. Do not ask for an OK phrase to discover a miss.

## When portable invokes a check

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/produce-tiktok-product-video-v3/scripts/validate_craft_quality.py" \
  --project-root <project-root> --product-model <model> --surface <script|picture|captions|tts-timing> --artifact <artifact.json>
```

A fail is `HOLD_CRAFT_QUALITY`. Repair the current draft and rerun. Schema-valid is not quality-valid.

Read the matching file only when that checkpoint is next:

- [stages/01-before-script-ok.md](stages/01-before-script-ok.md)
- [stages/02-before-rough-ok.md](stages/02-before-rough-ok.md)
- [stages/03-before-final-ok.md](stages/03-before-final-ok.md)

## Do not

- Start a case from this skill.
- Present a draft that failed a craft check.
- Add a fourth routine checkpoint or a new OK phrase.
- Record operator 指摘 as the way the next case learns a standing rule. Put a standing rule once in `config/product-video-rules/`.
- Overwrite an existing case, editor project, export, Drive object, payload, or receipt.
