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
```

2. If dispatch has not created a case yet:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/prepare.py" --project-root <PROJECT_ROOT> --product-model <MODEL> --campaign-focus "<optional>" --facts-json <verified facts>
```

3. Build `PRODUCT_INFORMATION` and `PRODUCT_APPEAL_POINTS` only from verified product information, verified configuration, and explicit user instructions. Do not invent specifications, performance, effects, numerical claims, or unsupported benefits. If the user gave a campaign focus, store it as `USER_CAMPAIGN_FOCUS`.

4. Save the compact prepare receipt, then:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/complete_stage.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --stage PREPARE --receipt-json '{"status":"OK"}'
```

5. Return to `/product-video` immediately. Do not ask to continue. Next stage is SCRIPT.
