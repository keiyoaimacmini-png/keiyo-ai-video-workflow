---
name: deliver-tiktok-product-video
description: Calculate the verified export name, export once, and optionally upload/read back one new Drive file for an approved product video after 完成・書き出しOK. Use only when explicitly invoked or routed from produce-tiktok-product-video-portable at EXPORT_AND_DELIVERY.
---

# Deliver TikTok Product Video

Input stage must be `EXPORT_AND_DELIVERY` with exact `完成・書き出しOK` bound to the current final-QA artifact, delivery-rule snapshot, and authorization subjects. Read the parent core invariants and workflow-state contract.

Read the delivery-rule snapshot path registered in workflow state and verify its actual bytes against the final approval. Do not rebuild or replace it after `完成・書き出しOK`. Bind the same SHA into the `EXPORT_AND_DELIVERY` stage receipt and task-owned delivery-stage receipt.

## Export preflight

1. Read the actual current JST date immediately before export.
2. Read back the completed-export ledger for that exact JST date and product model. Verify ordered records, record hashes, snapshot hash, count, and scope; use count plus one. Never infer the ordinal.
3. Render `YYYY_MMDD_<model>_AI作成<①..⑳>.<ext>` and prove no exact-name collision in the local output and any approved Drive scope.
4. Reverify the exact approved editable project and current final-QA receipt. Read its hash-bound `product_video_timeline_integrity_receipt.v1` and rerun `validate_timeline_integrity.py` against the task root; HOLD rather than export if the binding, evidence bytes, linked timing/pairing receipts, source/caption/TTS counts, exact mute, frame coverage, full playback, or same-project reload closure fails.

Export once. A request acknowledgement, progress state, toast, or unknown result is not permission to retry. Read back the completed local file's exact name, MIME, byte size, media SHA-256, and export time; then hash and store the export receipt.

## Optional exact-scope Drive delivery

Run only when `delivery_mode` is `drive` and the original request/destination subjects are already exact and hash-bound. Locate exactly one approved model folder, reject collision, upload one new file, then read back new file identity, exact name, MIME, byte size, approved parent scope, and time. Store only the portable hashed receipt fields required by the production contract.

After verified Drive read-back, close only task-owned CapCut, TikTok-login, and Drive tabs and verify their absence. If ownership is unknown, leave them open and HOLD. For `export_only`, do not close tabs under the Drive-completion rule.

Append the `EXPORT_AND_DELIVERY` receipt and advance to `COMPLETE` only when the required export and optional Drive evidence are complete. Never post, publish, overwrite, clean up, or delete.
