---
name: deliver-tiktok-product-video
description: Calculate the verified export name, export once, and upload/read back one new Drive file for an approved product video after 完成・書き出しOK unless the original request required export_only. Use only when explicitly invoked or routed from produce-tiktok-product-video-portable at EXPORT_AND_DELIVERY.
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

## Drive 格納

Default `delivery_mode` is `drive`. Run this after the new export read-back in the same turn. Before export, already prove the JST ledger ordinal and that the exact name is absent from local output and the approved Drive parent. Do not rebuild bound receipts or hunt a browser UI.

Locate exactly one parent folder whose title matches the verified product model in exact case. Upload one new file from local bytes. Do not inline the completed video as base64 in a tool argument.

Drive ingest, in order:

1. Prove exactly one parent folder whose title matches this product model in exact case and no same-name file (adapter search is enough; do not screenshot Drive). Drive name search is case-insensitive; keep only the exact-title folder.
2. Create the new file with `${SKILL_ROOT}/scripts/upload_drive_local_file.py` from the local export path. Bytes stay on the filesystem and HTTPS; they never enter a chat or tool argument.

```bash
python3 "${SKILL_ROOT}/scripts/upload_drive_local_file.py" --project-root <project-root> --local-path <export-path> --title <completed_video_filename> --parent-title <model> --mime-type video/mp4
```

3. Read back through the Drive adapter: exact name, MIME, byte size, new identity, parent scope, and time at or after export. A 16–22MB local file should finish this helper upload in tens of seconds. Minutes of wait mean the helper was not used or a HOLD was left sitting.
4. If the helper HOLDs for missing runtime OAuth, stop with `HOLD_DRIVE_LOCAL_BYTES_UNAVAILABLE`. Tell the operator to place a Desktop OAuth client at `.runtime/drive-oauth-client.json` and run the same script with `--login` from the repository root in Terminal, not from the home directory. Do not run `--login` from the agent. Do not open Chrome.app for 格納. Do not screenshot, OCR, Accessibility-hunt, or click-hunt Google Chrome.app. Do not use Google Drive for desktop, a local sync mount, rclone, or the agent-controlled browser.

Missing or duplicate model-titled folders are `HOLD_DRIVE_SCOPE_AMBIGUOUS`. Drive login, CAPTCHA, 2FA, recovery, or account choice for an already-open Chrome session is `HOLD_DRIVE_LOGIN_USER_ACTION_REQUIRED`. Match new file identity, exact name, MIME, byte size, approved parent scope, and time. Store only the portable hashed receipt fields required by the production contract. Never write raw Drive IDs into Git. Never create a same-name empty or path-string decoy. Do not copy the export into `Downloads/`.

Skip Drive only when `delivery_mode` is `export_only` because the original request explicitly required local-only export. If the parent is proven but no local-byte ingest path exists, `HOLD_DRIVE_LOCAL_BYTES_UNAVAILABLE`. Phrases such as `編集が完了した` do not authorize this stage.

After verified Drive read-back, close only task-owned CapCut, TikTok-login, and Drive tabs and verify their absence. If ownership is unknown, leave them open and record `HOLD_TASK_TAB_IDENTITY_UNVERIFIED`; that HOLD does not block `COMPLETE`. For `export_only`, do not close tabs under the Drive-completion rule.

Append the `EXPORT_AND_DELIVERY` receipt and advance to `COMPLETE` only when the required export and, for `drive`, Drive evidence are complete. Never post, publish, overwrite, or delete originals, Drive stored objects, receipts, or another case.

## Local working-copy purge after verified storage

After `COMPLETE` and verified destination storage, purge this case's local working media so product materials and completed-video copies do not remain on the production host. Ver2 production host is the operator Mac.

1. Prove destination storage: Drive read-back for `delivery_mode: drive`, or `destination-stored-receipt.v1.json` for `export_only` showing a durable copy that is not a local working copy.
2. Dry-run `scripts/purge_local_working_media.py` for this case only.
3. Execute only with `--execute --i-confirm-destination-stored`.
4. Keep JSON receipts, settings, git-tracked files, originals that are still the source of record, and the stored destination file.
5. If another case is not `COMPLETE`, leave shared `footage/`, `voice/`, and `.runtime/product-video-inputs/` in place.
6. If this host is not the operator Mac, purge this host first, then stop with `HOLD_MAC_LOCAL_WORKING_MEDIA_PURGE_REQUIRED`. Tell the operator the stored original is the Drive folder titled with this product model. On the Mac, check Finder Downloads for `Downloads/<completed_video_filename>` first, then repo-relative `outputs/<case-id>/` media and `out/<completed_video_filename>` only if those copies exist. Missing copies are not a failure.
7. If the local file is the only remaining completed video, stop with `HOLD_LOCAL_WORKING_MEDIA_IS_SOLE_COPY`.
