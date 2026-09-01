# Cursor Desktop app / Cloud Agent product-video instructions

## Required workflow

- For full product-video production, invoke `/produce-tiktok-product-video-portable` from `.cursor/skills/produce-tiktok-product-video-portable/` and follow its `SKILL.md`.
- Resolve `PROJECT_ROOT` to the repository root and `SKILL_ROOT` to `$PROJECT_ROOT/.cursor/skills/produce-tiktok-product-video-portable`.
- Before creating a case, run `python3 .cursor/scripts/verify_product_video_setup.py --require-materials`. Do not continue past its HOLD status.
- The canonical AN-S182 settings file is `config/product_video_settings_AN-S182.v1.json`. Do not infer or replace it.
- The material root is `PRODUCT_VIDEO_MATERIAL_ROOT` when set, otherwise `.runtime/product-video-inputs/AN-S182_コピー`.

## Approval and safety boundary

- Use only the exact routine approvals `台本OK`, `粗編集OK`, and `完成・書き出しOK`.
- Create a new case, task root, workflow state, and CapCut Web project. Do not modify or overwrite existing projects, exports, Drive objects, payloads, receipts, or source media.
- Keep product media, evidence frames, editable runtime artifacts, exports, credentials, cookies, tokens, account identifiers, and session identifiers out of Git, pull requests, and ordinary logs.
- Do not open a pull request, publish an artifact, post, send externally, purchase credit, retry an unknown export/upload, overwrite, clean up, or delete unless the user separately authorizes that exact action.
- Drive creation is allowed only when the original request fixed the exact scope and `完成・書き出しOK` is bound to the current final-QA receipt. Require exact new-file read-back.

## Cursor Desktop browser and human handoff

- Use the official CapCut Web origin in Chrome only when the Cursor Agent has an actual browser/editor control adapter. Never put CapCut or TikTok passwords in repository files or prompts.
- When login, CAPTCHA, 2FA, account choice, recovery, or new consent is required, stop with `HOLD_CAPCUT_LOGIN_USER_ACTION_REQUIRED` so the user can operate through Cursor Desktop.
- If the Cursor Agent lacks the browser/editor, rendered-frame, or audio capability required by the host-adapter contract, stop with the matching HOLD instead of claiming the edit is complete.
- If the Agent cannot reliably hear the full timeline, keep auditory verification pending at Checkpoint 3 and ask the user to listen on the same desktop. Do not add a fourth checkpoint.
