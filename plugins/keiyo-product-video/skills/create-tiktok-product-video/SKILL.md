---
name: create-tiktok-product-video
description: Create a future new-product TikTok video plan and portable CapCut handoff with evidence-based product facts, per-cut media requirements, exact approval gates, and deterministic validation. Use for new TikTok product-video requests, not for changing existing video projects.
---

# Create TikTok Product Video

Use this skill only for a new product-video case. Never alter an existing project, draft, export, cloud item, database, favorite-monitor file, or external system.

## Start safely

1. Read the supplied product materials and record every item in a manifest. Separate verified facts, review observations, hypotheses, and not obtained; do not guess.
2. Put every available company observation in the manifest. `product_model_provenance` must close over all observed company models and be `verified`; a conflict is `HOLD_MODEL_UNVERIFIED`. Validate `^AN-[A-Z0-9]{4}$`.
3. If video exists, inspect it before selecting concepts. Use vision only when media sidecars do not establish the necessary visual evidence. Use UI only for session-bound retrieval or an already-approved CapCut action.
4. For a content concept, retrieve one `goal_axis` at a time from verified `favorite-context`; use reusable structure only and retain `not_to_copy`. Follow the project content-generation workflow when it is available.
5. Create 20 unconfirmed concepts, let the user select one, then build a canonical payload. Read [payload_contract.md](references/payload_contract.md) before drafting the payload or a portable handoff.

## Validate before requesting edit approval

Run the deterministic validator against the canonical payload:

```bash
python3 scripts/validate_product_video_payload.py payload.json
```

It verifies canonical hashes, strict schemas, complete workflow payloads, all-cut closure, enum-derived media receipts or explicit asset holds, gates, naming, portability, and cleanup preflight. It never repairs hashes or approvals. Run its self-test after changing the bundled validator:

```bash
python3 scripts/validate_product_video_payload.py --self-test
```

Resolve every error. Do not infer missing media, approval, or rights. Script, caption, and present TTS close exactly over every cut; final-cut text is `下のカートからチェック`, including when TTS is absent.

## Approval and delivery boundaries

- Show the project's exact approval prompt and wait for an exact `OK` before any ChatCut or CapCut edit.
- A payload change invalidates hashes, prohibition result, and every approval. Never auto-rebind or reuse an approval.
- Require separate explicit approval for export, cloud sync/upload, publish, credit spend, and external send. An edit `OK` does not grant them.
- For Camee Neo/OpenClaw-bound work, verify the HTTPS TikTok Shop destination before generation; otherwise hold. Run the prohibition policy after all visible text is final.
- After approved CapCut work, use `Space/<model>/AI作成_<model>_<YYYY_MM_DD>` as the cloud project path. The completed-video basename is exactly `AI作成_<model>_<YYYY_MM_DD>`; its external destination is configured outside this portable skill.

## Portable handoff and cleanup

Use classified stable asset IDs, SHA-256s, and normalized safe POSIX relative paths. Reject absolute paths, traversal, aliases, credentials, account IDs, and external-storage destinations.

Before cleanup, record a preflight only. Preserve originals, editable-project dependencies, shared assets, and uncertain items. List only hash-verified, explicitly approved `local_working_download` candidates by ID (never path); never delete or execute cleanup from this workflow.

## Model routing

Use routine deterministic work (manifest normalization, hashing, schema checks, naming, and validator runs) with a low-cost model or script. Use a frontier model for creative direction, evidence conflicts, and design QA. Escalate to vision only for insufficient sidecars, and UI only for session-bound retrieval or separately approved CapCut operations.
