---
name: product-video-delivery-20260919
description: Export, verify, Drive-upload, read back, then purge after the operator says 完成・格納してください. Use only when /product-video dispatches DELIVERY.
disable-model-invocation: true
---

# DELIVERY

Read this file only when dispatch says `product-video-delivery`.
When this Skill's behavior changes, rename the folder and frontmatter `name` date (`YYYYMMDD`) together. Keep the logical dispatch id.

Required operator phrase: `完成・格納してください`. Do not accept `完成・書き出しOK` or `粗編集OK`.

0. Before export, re-check Drive readiness. Dispatch already gates this; if you are in DELIVERY, prove again:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/delivery.py" --prove-drive --project-root <PROJECT_ROOT> --product-model <MODEL> --live
```

If Drive is not READY, do not export. Report only that Drive OAuth login is required (`upload_drive_local_file.py --login` at the repo root). Stay on WAITING_FOR_OPERATOR. After login, the same `完成・格納してください` resumes. Do not invent a new HOLD.

If Drive is READY: export → upload → read-back → COMPLETE → purge.

1. Confirm the current case and editor project identity.
2. If export or upload status is `unknown` / `pending` / `in_progress`, observe that job. Do not blindly retry.
3. Export once. Verify the export job, then the local file (name, MIME, bytes, SHA-256).
4. In the same turn, upload with the existing helper. Do not inline video as base64. Do not open Chrome.app for 格納.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/upload_drive_local_file.py" --project-root <PROJECT_ROOT> --local-path <export> --title <filename> --parent-title <MODEL> --mime-type video/mp4
```

5. Read back the new Drive file (exact name, MIME, size, parent title, time). COMPLETE only after that verification.
6. Record the **final** timeline's adopted source/range into product-level shot history. Use the editor timeline after operator picture swaps, not the first ASSEMBLY draft. Do not store the completed export. Do not modify source videos.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/approved_shots.py" --project-root <PROJECT_ROOT> --product-model <MODEL> --case-id <CASE_ID> --record-final [--timeline-json '<final cuts>']
```

7. After COMPLETE and verified storage, dry-run then execute the existing purge helper. Never purge before verified delivery. Do not delete `.runtime/product-video-inputs`, `.runtime/product-video-approved-shots`, `.runtime/product-video-material-metadata`, `.runtime/product-video-material-index`, or `.runtime/product-video-visual-catalog`.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/purge_local_working_media.py" --project-root <PROJECT_ROOT> --task-root <task-root> --case-id <CASE_ID>
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/purge_local_working_media.py" --project-root <PROJECT_ROOT> --task-root <task-root> --case-id <CASE_ID> --execute --i-confirm-destination-stored
```
