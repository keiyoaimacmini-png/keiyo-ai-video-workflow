---
name: product-video-delivery
description: Export, verify, Drive-upload, read back, then purge after the operator says 完成・格納してください. Use only when /product-video dispatches DELIVERY.
disable-model-invocation: true
---

# DELIVERY

Read this file only when dispatch says `product-video-delivery`.

Required operator phrase: `完成・格納してください`. Do not accept `完成・書き出しOK` or `粗編集OK`.

1. Confirm the current case and editor project identity.
2. If export or upload status is `unknown` / `pending` / `in_progress`, observe that job. Do not blindly retry.
3. Export once. Verify the export job, then the local file (name, MIME, bytes, SHA-256).
4. In the same turn, upload with the existing helper. Do not inline video as base64. Do not open Chrome.app for 格納.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/produce-tiktok-product-video-portable/scripts/upload_drive_local_file.py" --project-root <PROJECT_ROOT> --local-path <export> --title <filename> --parent-title <MODEL> --mime-type video/mp4
```

5. Read back the new Drive file (exact name, MIME, size, parent title, time). COMPLETE only after that verification.
6. After COMPLETE and verified storage, dry-run then execute the existing purge helper. Never purge before verified delivery. Do not delete `.runtime/product-video-inputs`; that tree is a persistent shared product library, including videos and images in classification subfolders.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/produce-tiktok-product-video-portable/scripts/purge_local_working_media.py" --project-root <PROJECT_ROOT> --task-root <task-root> --case-id <CASE_ID>
python3 "${PROJECT_ROOT}/.cursor/skills/produce-tiktok-product-video-portable/scripts/purge_local_working_media.py" --project-root <PROJECT_ROOT> --task-root <task-root> --case-id <CASE_ID> --execute --i-confirm-destination-stored
```
