# Delivery-stage rules

Export once after exact `完成・書き出しOK`. Read back the new local export. Default completion is Drive 格納 into the one folder titled with this product model, then exact read-back. Use `export_only` only when the original request explicitly required local-only export; then do not treat a working copy as stored until `destination-stored-receipt.v1.json` proves a durable copy that is not a local working copy. `編集が完了した` is not this approval.

Before export, read the JST date/model ledger and prove no exact-name collision in local output and the approved Drive parent. Do not wait until after download to discover a collision.

Drive ingest, in order:

1. Prove exactly one parent folder titled with this product model and no same-name file.
2. Create one new file from local bytes. Do not inline the completed video as base64 in a tool argument.
3. If the Drive adapter cannot take a local path or upload session, upload once through the already-authenticated Drive UI into that proven parent, then read back through the adapter.
4. Match exact name, MIME, byte size, new identity, parent scope, and time at or after export.
5. Never create a same-name empty or path-string decoy. Never retry an unknown upload.

If the parent is proven but no local-byte path exists, `HOLD_DRIVE_LOCAL_BYTES_UNAVAILABLE`.

After `COMPLETE` and that verified 格納:

1. Dry-run `scripts/purge_local_working_media.py` for this case only.
2. Execute only with `--execute --i-confirm-destination-stored`.
3. Remove this case's local working media, including completed-video copies, from the machine that runs the script.
4. If this host is not the operator Mac, purge this host first, then stop with `HOLD_MAC_LOCAL_WORKING_MEDIA_PURGE_REQUIRED`. Tell the operator the stored original is the Drive model-titled folder; on the Mac check Finder Downloads for the exact completed filename first, then repo-relative `outputs/<case-id>/` media and `out/<completed_video_filename>` only if those copies exist. Missing copies are not a failure.
5. Keep receipts, settings, originals that are still the source of record, and the stored destination file.

Uncertain browser-tab ownership is `HOLD_TASK_TAB_IDENTITY_UNVERIFIED`. Leave those tabs open. That HOLD does not block `COMPLETE` after verified Drive read-back.

Never post, overwrite, or retry an unknown export or upload.
