# Learning loop

Operator corrections become lesson objects. Do not grow portable markdown instead.

Store under `$PROJECT_ROOT/config/product-video-lessons/`.

| Path | Meaning |
| --- | --- |
| `active/{script,picture,captions,tts-timing}/` | Quality lessons loaded by the next case |
| `pending-safety/` | Safety changes waiting for explicit promote |

## Record in the same turn as the fix

Quality (default). Next PREFLIGHT loads it automatically:

```bash
python3 "${SKILL_ROOT}/scripts/record_lesson.py" \
  --project-root <project-root> \
  --surface script \
  --defect hook_closed_by_result_looks \
  --bad-file <bad.json> \
  --good-file <good.json>
```

Safety (checkpoints, overwrite rules, Drive/TTS procedure, HOLD definitions). Do not edit the portable skill. Write pending only:

```bash
python3 "${SKILL_ROOT}/scripts/record_lesson.py" \
  --project-root <project-root> \
  --surface script \
  --defect <id> \
  --safety \
  --note "<what would change in the safety engine>"
```

Promote a pending safety lesson only after the operator says to leave it for later cases **and** to change the safety engine. That still does not rewrite portable files; it marks the pending record acknowledged:

```bash
python3 "${SKILL_ROOT}/scripts/record_lesson.py" \
  --project-root <project-root> \
  --promote-id <id> \
  --i-confirm-safety-promote
```

## Lesson fields

`schema` `product_video_lesson.v1`: `id`, `surface`, `defect`, `auto`, `status`, `bad`, `good`, `gate`, optional `product_models`, optional `note`.

- `auto: true` and `status: active` for quality.
- `auto: false` and `status: pending` or `acknowledged` for safety.
- Empty `product_models` applies to every model.

Do not read case archives, chat transcripts, or portable `candidate` notes as global rules. Only `active/` lessons and the built-in craft gates apply.
