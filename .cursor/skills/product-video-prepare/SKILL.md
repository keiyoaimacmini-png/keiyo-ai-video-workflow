---
name: product-video-prepare
description: Prepare one new isolated product-video case from verified product inputs. Use only when /product-video dispatches PREPARE.
disable-model-invocation: true
---

# PREPARE

Read this file only when dispatch says `product-video-prepare`.

1. Resolve `PROJECT_ROOT`. Reuse the current material-management helper; do not redesign it:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/produce-tiktok-product-video-portable/scripts/resolve_product_inputs.py" --project-root <PROJECT_ROOT> --product-model <MODEL> --require-materials
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/prove_material_videos.py" --material-root <resolved material_root>
```

A material folder is not enough. There must be at least one regular, non-zero video file (`.mp4` `.mov` `.m4v` `.avi` `.mkv`, case-insensitive) under that root, including classification subfolders. Do not ffprobe or inspect every frame. If `video_count` is 0, stop with `HOLD_MATERIAL_VIDEO_REQUIRED` and do not start SCRIPT or TTS.

2. If dispatch has not created a case yet:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/prepare.py" --project-root <PROJECT_ROOT> --product-model <MODEL> --campaign-focus "<optional>" --facts-json <verified facts>
```

3. Build `PRODUCT_INFORMATION` and `PRODUCT_APPEAL_POINTS` only from verified product information, verified configuration, and explicit user instructions. Do not invent specifications, performance, effects, numerical claims, or unsupported benefits. If the user gave a campaign focus, store it as `USER_CAMPAIGN_FOCUS`.

4. Save the compact prepare receipt with `material_video_count` >= 1, then:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/complete_stage.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --stage PREPARE --receipt-json '{"status":"OK","material_video_count":<count>}'
```

5. Return to `/product-video` immediately. Do not ask to continue. Next stage is SCRIPT.
