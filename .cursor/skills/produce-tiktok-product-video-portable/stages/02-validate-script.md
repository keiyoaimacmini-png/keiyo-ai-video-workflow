---
name: validate-tiktok-product-video-script
description: Convert and validate a prepared product-video script package into the canonical portable payload, then present Checkpoint 1. Use only when explicitly invoked or routed from produce-tiktok-product-video-portable at SCRIPT_PREPARED, or for an unapproved SCRIPT_REVIEW revision.
---

# Validate TikTok Product Video Script

Input stage must be `SCRIPT_PREPARED`, or `SCRIPT_REVIEW` with `台本OK` still pending for a user-requested revision. Read:

1. the parent core invariants and workflow-state contract;
2. `${SKILL_ROOT}/references/payload-contract.md` completely.

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

Show the selected concept, complete script, punctuation, line breaks, source asset/path, source in/out, cut duration, Unicode count, estimated read time, evidence location, the in/mid/out frames of each proposed range, and review location. Stop only for exact `台本OK`. That approval authorizes rough visual editing in a separate new editor-of-record project; it does not authorize TTS, credits, finishing, export, or Drive.
