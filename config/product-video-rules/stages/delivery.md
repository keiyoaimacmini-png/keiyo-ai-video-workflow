# Delivery-stage rules

Export once after exact `完成・書き出しOK`. Read back the new local export. When `delivery_mode` is `drive`, create one new Drive file and read it back. When `delivery_mode` is `export_only`, do not treat a working copy as stored until `destination-stored-receipt.v1.json` proves a durable copy that is not a local working copy.

After `COMPLETE` and that verified 格納:

1. Dry-run `scripts/purge_local_working_media.py` for this case only.
2. Execute only with `--execute --i-confirm-destination-stored`.
3. Remove this case's local working media, including completed-video copies, from the machine that runs the script.
4. If this host is not the operator Mac, stop with `HOLD_MAC_LOCAL_WORKING_MEDIA_PURGE_REQUIRED` and run the same relative purge there.
5. Keep receipts, settings, originals that are still the source of record, and the stored destination file.

Never post, overwrite, or retry an unknown export or upload.
