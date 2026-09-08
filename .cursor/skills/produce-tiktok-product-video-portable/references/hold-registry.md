# HOLD registry

Use one most-specific code and describe the exact missing evidence, authority, or unambiguous state. HOLD preserves existing work and never grants retry, overwrite, cleanup, deletion, purchase, publish, or send authority.

| Code | Use when |
| --- | --- |
| `HOLD_MODEL_UNVERIFIED` | Product model evidence is missing or conflicting. |
| `HOLD_PRODUCT_VIDEO_SETTINGS` | The exact single model settings file, its bytes, or resolved values do not close. Do not copy another model's file. |
| `HOLD_INPUT_MATERIALS_REQUIRED` | This model's material root is missing or unsafe. Do not reuse another model's media. Do not hash or watch every clip before the script exists. |
| `HOLD_SCRIPT_INCOMPLETE` | The six-stage script is incomplete, or `problem_resolution` does not present a solution to the same problem named in the hook. |
| `HOLD_CRAFT_QUALITY` | A v3 craft gate failed before a routine checkpoint. Repair the draft and rerun `validate_craft_quality.py`. Do not ask for `台本OK`, `粗編集OK`, or `完成・書き出しOK` while this HOLD is current. |
| `HOLD_MEDIA_NOT_MATCHED` | After `台本OK`, no proven file/range shows the claimed `picture_must` action, or a numeric in/out exists but the in, midpoint, or out frame does not show that action. |
| `HOLD_DISTINCT_ASSET_PER_CAPTION` | Visible captions do not map one-to-one to distinct asset IDs and media hashes. |
| `HOLD_FINAL_VISUAL_NOT_VERIFIED` | The configured canonical final asset/range/tail cannot be verified, including when last-valid composed frames of that tail are missing. |
| `HOLD_CAPTION_TAIL_NOT_CLOSED` | The configured final cut's viewer caption does not hold through `timeline_end_frame` after TTS ends. ChatCut `cue_override` JSON is not proof. Do not clone the same TTS asset as a muted caption-hold. Do not replace Caption Cards with Motion Graphics. |
| `HOLD_CAPCUT_WEB_NOT_VERIFIED` | Official editor origin, intended project, or editable timeline identity is not verified. |
| `HOLD_CAPCUT_LOGIN_USER_ACTION_REQUIRED` | Login needs ambiguous account choice, CAPTCHA, 2FA, recovery, new consent, or credential handling beyond existing session/autofill. |
| `HOLD_GEMINI_CLI_NOT_VERIFIED` | Antigravity CLI (`agy`) is missing, failed a one-shot print, exhausted included quota, or tried to edit files. Do not buy AI credits. Do not enable overages. Do not call the Gemini API. This HOLD does not authorize an operator paste. Gemini.app, Google Chrome.app, and the agent-controlled Cursor browser are not substitutes. |
| `HOLD_GEMINI_LOGIN_USER_ACTION_REQUIRED` | Antigravity CLI login on this Mac needs Google sign-in, ambiguous account choice, CAPTCHA, 2FA, recovery, new consent, or eligibility verification. In Terminal run `agy` and complete login. Never paste passwords or API keys. |
| `HOLD_GEMINI_MODEL_NOT_VERIFIED` | The Antigravity CLI model is not exactly Gemini 3.8 Flash (`gemini-3.8-flash`). Do not use Auto, Pro, Flash-Lite, or another Flash label. |
| `HOLD_GEMINI_WEB_NOT_VERIFIED` | Legacy Gemini.app path. New drafts use `agy`. Do not fall back to Gemini.app. |
| `HOLD_GEMINI_TEMP_CHAT_NOT_VERIFIED` | Legacy Gemini.app 一時チャット path. New drafts use `agy --print` and do not send into Gemini.app. |
| `HOLD_TTS_ALLOWANCE_EXHAUSTED` | Another TTS action would exceed the approved plan or per-cut reserve. |
| `HOLD_CAPCUT_TTS_RESULT_BYTES_UNAVAILABLE` | Holiday Twist result-card audio bytes could not be saved into the case TTS working directory. Do not click オーディオのみ, do not use a save dialog, and do not ask the operator to press Save. |
| `HOLD_AUDITORY_CONFIRMATION_REQUIRED` | The host cannot reliably complete the required full-playback listening audit. |
| `HOLD_PRODUCTION_ORDINAL_UNVERIFIED` | The exact date/model export ledger, order, or hash does not close. |
| `HOLD_EXPORT_OUTCOME_UNKNOWN` | One export was submitted but its result cannot be unambiguously read back. |
| `HOLD_DRIVE_SCOPE_AMBIGUOUS` | The exact approved Drive parent is absent, duplicated, or mismatched. Drive name search is case-insensitive; keep only the folder whose title matches this product model in exact case. |
| `HOLD_DRIVE_LOCAL_BYTES_UNAVAILABLE` | The approved parent is proven, but `scripts/upload_drive_local_file.py` cannot send the completed local file (missing `.runtime/` Drive OAuth, failed refresh, or helper error). Ask the operator to run `--login` in Terminal. Do not inline the video as base64. Do not open Chrome.app for 格納. Do not screenshot-hunt Chrome.app. Do not create a same-name decoy. |
| `HOLD_DRIVE_WEB_NOT_VERIFIED` | Official Google Drive Web origin `https://drive.google.com/` was not used in this Mac's Google Chrome.app. Google Drive for desktop, a local sync mount, rclone, and the agent-controlled Cursor browser are not substitutes. Do not copy cookies. |
| `HOLD_DRIVE_LOGIN_USER_ACTION_REQUIRED` | Drive Web login on this Mac's Chrome.app needs ambiguous account choice, CAPTCHA, 2FA, recovery, new consent, or credential handling beyond the existing session. Never paste passwords. |
| `HOLD_NAME_COLLISION` | The exact output name already exists locally or in the approved Drive scope. |
| `HOLD_UPLOAD_OUTCOME_UNKNOWN` | One upload was submitted but its result cannot be unambiguously read back. |
| `HOLD_TASK_TAB_IDENTITY_UNVERIFIED` | The host cannot prove which browser tabs belong only to this case. Leave them open. After verified Drive read-back this HOLD does not block `COMPLETE`; it only withholds tab closure. |
| `HOLD_NEW_AUTHORITY_REQUIRED` | A required action is outside the frozen approvals and no more specific code applies. |
| `HOLD_POST_COMPLETE_PURGE_NOT_DUE` | A local working-media purge was requested before `COMPLETE` and bound `完成・書き出しOK`. |
| `HOLD_LOCAL_WORKING_MEDIA_IS_SOLE_COPY` | Purging would delete the only remaining completed video or an unverified destination. |
| `HOLD_MAC_LOCAL_WORKING_MEDIA_PURGE_REQUIRED` | This host is not the operator Mac (for example a Cloud VM). After this host's working copies are purged, the operator Mac still needs the same relative purge. User-facing check is Finder Downloads for the exact completed filename first; repo `outputs/<case-id>/` media and `out/<filename>` only if present. Missing copies are not a failure. |
| `HOLD_BULK_TTS_LINE_ALIGNMENT_UNVERIFIED` | Bulk TTS cannot be split because frozen-line alignment is missing, mismatched, overlapping, or past the audio end. |
| `HOLD_BULK_TTS_SCENE_GAPS_UNVERIFIED` | The working copy does not contain one detectable silent scene-split gap per frozen-line boundary. |

The payload contract also uses `AWAITING_USER_AUDITORY_CONFIRMATION`; treat it as equivalent to `HOLD_AUDITORY_CONFIRMATION_REQUIRED` at the orchestration layer without changing a stored schema value.
