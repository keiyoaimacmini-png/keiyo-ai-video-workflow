# HOLD registry

Use one most-specific code and describe the exact missing evidence, authority, or unambiguous state. HOLD preserves existing work and never grants retry, overwrite, cleanup, deletion, purchase, publish, or send authority.

| Code | Use when |
| --- | --- |
| `HOLD_MODEL_UNVERIFIED` | Product model evidence is missing or conflicting. |
| `HOLD_PRODUCT_VIDEO_SETTINGS` | The exact single model settings file, its bytes, or resolved values do not close. Do not copy another model's file. |
| `HOLD_INPUT_MATERIALS_REQUIRED` | This model's material root is missing, unsafe, or empty. Do not reuse another model's media. |
| `HOLD_SCRIPT_INCOMPLETE` | The six-stage script or required evidence is incomplete. |
| `HOLD_MEDIA_NOT_MATCHED` | The claimed visible action or exact source range is not verified from real media. |
| `HOLD_DISTINCT_ASSET_PER_CAPTION` | Visible captions do not map one-to-one to distinct asset IDs and media hashes. |
| `HOLD_FINAL_VISUAL_NOT_VERIFIED` | The configured canonical final asset/range/tail cannot be verified. |
| `HOLD_CAPCUT_WEB_NOT_VERIFIED` | Official editor origin, intended project, or editable timeline identity is not verified. |
| `HOLD_CAPCUT_LOGIN_USER_ACTION_REQUIRED` | Login needs ambiguous account choice, CAPTCHA, 2FA, recovery, new consent, or credential handling beyond existing session/autofill. |
| `HOLD_TTS_ALLOWANCE_EXHAUSTED` | Another TTS action would exceed the approved plan or per-cut reserve. |
| `HOLD_AUDITORY_CONFIRMATION_REQUIRED` | The host cannot reliably complete the required full-playback listening audit. |
| `HOLD_PRODUCTION_ORDINAL_UNVERIFIED` | The exact date/model export ledger, order, or hash does not close. |
| `HOLD_EXPORT_OUTCOME_UNKNOWN` | One export was submitted but its result cannot be unambiguously read back. |
| `HOLD_DRIVE_SCOPE_AMBIGUOUS` | The exact approved Drive parent is absent, duplicated, or mismatched. The parent must be the one folder titled with this product model. |
| `HOLD_NAME_COLLISION` | The exact output name already exists locally or in the approved Drive scope. |
| `HOLD_UPLOAD_OUTCOME_UNKNOWN` | One upload was submitted but its result cannot be unambiguously read back. |
| `HOLD_TASK_TAB_IDENTITY_UNVERIFIED` | The host cannot prove which browser tabs belong only to this case. |
| `HOLD_NEW_AUTHORITY_REQUIRED` | A required action is outside the frozen approvals and no more specific code applies. |
| `HOLD_POST_COMPLETE_PURGE_NOT_DUE` | A local working-media purge was requested before `COMPLETE` and bound `完成・書き出しOK`. |
| `HOLD_LOCAL_WORKING_MEDIA_IS_SOLE_COPY` | Purging would delete the only remaining completed video or an unverified destination. |
| `HOLD_MAC_LOCAL_WORKING_MEDIA_PURGE_REQUIRED` | The Cloud VM working copies are gone, and the operator Mac still needs the same relative purge. |
| `HOLD_BULK_TTS_LINE_ALIGNMENT_UNVERIFIED` | Bulk TTS cannot be split because frozen-line alignment is missing, mismatched, overlapping, or past the audio end. |
| `HOLD_BULK_TTS_SCENE_GAPS_UNVERIFIED` | The working copy does not contain one detectable silent scene-split gap per frozen-line boundary. |

The payload contract also uses `AWAITING_USER_AUDITORY_CONFIRMATION`; treat it as equivalent to `HOLD_AUDITORY_CONFIRMATION_REQUIRED` at the orchestration layer without changing a stored schema value.
