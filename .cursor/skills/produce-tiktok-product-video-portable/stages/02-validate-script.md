---
name: validate-tiktok-product-video-script
description: Convert and validate a prepared product-video script package into the canonical portable payload, then present Checkpoint 1. Use only when explicitly invoked or routed from produce-tiktok-product-video-portable at SCRIPT_PREPARED, or for an unapproved SCRIPT_REVIEW revision.
---

# Validate TikTok Product Video Script

Input stage must be `SCRIPT_PREPARED`, or `SCRIPT_REVIEW` with `台本OK` still pending for a user-requested revision. Read:

1. the parent core invariants, workflow-state contract, and model-routing contract;
2. `${SKILL_ROOT}/references/payload-contract.md` completely.

`SCRIPT_PREPARED` still requires Gemini 3.8 Flash. `SCRIPT_REVIEW` may be Gemini 3.8 Flash or Grok 4.6.

Do not read the full planning skill unless the user explicitly requests planning-only behavior.

## Build and validate

- Verify the script-package SHA against the actual file.
- Verify the script package's registered rule-snapshot file and actual bytes against its active-rule snapshot SHA. Do not rebuild it during this stage.
- Build one canonical production payload from that package and the actual model settings file.
- Preserve truthful free-text observed subjects; do not force a false person/product/hand category.
- Ensure the six stages, natural adjacent-line continuity, verified evidence, distinct source IDs and media hashes, exact CTA/settings values, timing estimates, final block, and exact pending approval plans all close.
- Run:

```bash
python3 ${SKILL_ROOT}/scripts/validate_product_video_payload.py payload.json --settings-root <project-root>
```

Resolve every deterministic error without inventing evidence or authority.

## Checkpoint 1

Hash the validated payload and store `artifacts.production_payload`. On the normal path, record the `SCRIPT_PREPARED` binding and advance to `SCRIPT_REVIEW`. During an unapproved `SCRIPT_REVIEW` revision, replace only that current draft binding and remain at `SCRIPT_REVIEW`.

Show the selected concept, complete script, punctuation, line breaks, source asset/path, source in/out, cut duration, Unicode count, estimated read time, evidence location, and review location. Generate and show the Grok 4.6 handoff card (relative task root only):

```bash
python3 "${SKILL_ROOT}/scripts/resolve_ai_model_lane.py" --print-handoff-card --case-id <case-id> --product-model <model> --task-root outputs/<case-id>
```

Stop only for exact `台本OK`. That approval authorizes rough visual editing in a separate new CapCut Web project **on Grok 4.6**; it does not authorize TTS, credits, finishing, export, or Drive, and it does not authorize CapCut work on Gemini 3.8 Flash.

Before advancing to `ROUGH_EDIT`:

```bash
python3 "${SKILL_ROOT}/scripts/resolve_ai_model_lane.py" --model "<observed-model-name>" --stage SCRIPT_REVIEW --entering-rough-edit
```

If this returns `HOLD_AI_MODEL_HANDOFF_REQUIRED`, record `台本OK` when it was received here, reprint the card with `--script-approved`, and stop. Do not open CapCut from Gemini 3.8 Flash.
