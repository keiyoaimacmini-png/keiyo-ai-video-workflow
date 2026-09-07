---
name: produce-tiktok-product-video-v3
description: Quality-first TikTok product-video production with craft gates and a lesson loop that carries operator corrections into the next case. Use when asked for produce-tiktok-product-video-v3, quality-first production, or learning from prior video fixes. Does not replace produce-tiktok-product-video-portable until the operator switches.
disable-model-invocation: true
---

# Produce TikTok Product Video v3

Use this file as the entrypoint. Resolve `SKILL_ROOT` to this directory. Resolve `PROJECT_ROOT` to the product project's trusted root. Resolve `SAFETY_SKILL_ROOT` to `$PROJECT_ROOT/.cursor/skills/produce-tiktok-product-video-portable`. Never infer those paths.

This skill adds craft gates and a lesson loop. Safety work (case isolation, payload schema, Drive, TTS capture, purge) is delegated to the portable skill's scripts and the matching portable stage file. Do not copy those procedures here. Do not edit the portable skill unless the operator explicitly promotes a safety change.

## Always load

Read completely:

1. [references/methods.md](references/methods.md)
2. [references/craft-gates.md](references/craft-gates.md)
3. [references/learning-loop.md](references/learning-loop.md)
4. [references/safety-engine.md](references/safety-engine.md)

Load active lessons before drafting:

```bash
python3 "${SKILL_ROOT}/scripts/load_lessons.py" --project-root <project-root> --product-model <model>
```

## Production loop

Follow the portable state machine. Insert a craft gate **before** each of the three checkpoints. A failed craft gate is `HOLD_CRAFT_QUALITY`, not a fourth checkpoint. Do not ask for `台本OK`, `粗編集OK`, or `完成・書き出しOK` while a craft gate fails.

| Portable state | Do this first | Craft gate | Then |
| --- | --- | --- | --- |
| `PREFLIGHT` / `SCRIPT_PREPARED` | Portable stages 01–02 | `script` | Ask `台本OK` only if craft passes |
| `ROUGH_EDIT` | Portable stage 03 | `picture` | Ask `粗編集OK` only if craft passes |
| `FINISHING` / `FINAL_QA` | Portable stages 04–05 | `captions` then `tts-timing` | Ask `完成・書き出しOK` only if both pass |
| `EXPORT_AND_DELIVERY` | Portable stage 06 | none | Drive 格納, then purge |

Gemini paste prompts must include rejected and accepted lesson examples:

```bash
python3 "${SKILL_ROOT}/scripts/render_gemini_web_prompt.py" --brief <task-root>/gemini-web-brief.v1.json --project-root <project-root>
```

Craft gates:

```bash
python3 "${SKILL_ROOT}/scripts/validate_craft_quality.py" --project-root <project-root> --product-model <model> --surface script --artifact <script-or-payload.json>
python3 "${SKILL_ROOT}/scripts/validate_craft_quality.py" --project-root <project-root> --product-model <model> --surface picture --artifact <picture-selection.json>
python3 "${SKILL_ROOT}/scripts/validate_craft_quality.py" --project-root <project-root> --product-model <model> --surface captions --artifact <caption-craft.json>
python3 "${SKILL_ROOT}/scripts/validate_craft_quality.py" --project-root <project-root> --product-model <model> --surface tts-timing --artifact <tts-craft.json>
```

Read the matching before-checkpoint file only when that checkpoint is next:

- [stages/01-before-script-ok.md](stages/01-before-script-ok.md)
- [stages/02-before-rough-ok.md](stages/02-before-rough-ok.md)
- [stages/03-before-final-ok.md](stages/03-before-final-ok.md)

On an operator correction, read [stages/04-record-correction.md](stages/04-record-correction.md) and record a lesson in the same turn. Quality lessons activate immediately. Safety changes stay pending until explicit `--i-confirm-safety-promote`.

## Do not

- Present a draft that failed a craft gate.
- Add a fourth routine checkpoint or a new OK phrase.
- Lengthen portable `core-invariants.md` instead of writing a lesson.
- Overwrite an existing case, editor project, export, Drive object, payload, or receipt.
- Switch the Cursor parent model, call the Gemini API, or treat the agent browser as Gemini.app or Chrome Drive.
