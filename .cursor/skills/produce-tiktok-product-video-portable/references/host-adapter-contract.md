# Host adapter contract

The workflow is independent of any assistant vendor, but the host must implement the capabilities below. Tool names are deliberately unspecified.

## Required path bindings

- `SKILL_ROOT`: this package directory.
- `PROJECT_ROOT`: trusted product-project root containing `config/` and source materials.
- `TASK_ROOT`: new case directory contained under `<project-root>/outputs/`.
- `RULES_ROOT`: optional local directory of active reusable production rules. If `<project-root>/config/product-video-rules` exists as a real directory, use it. If absent, omit the entire `--rules-root <rules-root>` option and generate an empty, hash-bound snapshot with the bundled snapshot builder.
- Product settings: `<project-root>/config/product_video_settings_<product_model>.v1.json` only.
- Material root: `PRODUCT_VIDEO_MATERIAL_ROOT` if set, otherwise `<project-root>/.runtime/product-video-inputs/<product_model>_コピー`.

Never place credential, cookie, token, account, browser-session, or raw remote-object identifiers in portable payloads or ordinary logs.

## Production host (v2)

Default production is the operator Mac desktop agent that can read local materials under the trusted project root. A remote cloud VM is not the default host. The agent-controlled browser is not the user's everyday browser application; do not assume CapCut or TikTok sessions saved there. If a required login cannot complete from the agent-controlled browser, stop with `HOLD_CAPCUT_LOGIN_USER_ACTION_REQUIRED`.

## Filesystem and process adapter

The host must be able to:

- read actual bytes, inspect MIME/type, compute SHA-256, and write new versioned task files;
- refuse overwrite by default;
- run Python 3 validators and preserve their exact exit status;
- resolve safe relative paths under trusted roots and reject escape or symlink ambiguity;
- obtain the real current time in the requested timezone.

Validator success never substitutes for live editor or storage read-back.

## Browser/editor adapter

The host must operate one editor of record for the whole case: the official CapCut Web editor, or a host-provided editor control surface that can create a separate new project, inspect timeline layers, inspect real frames, place captions, play the result, reload the same saved project, and export. Do not mix two picture timelines or two editor projects in one case. CapCut official template resource IDs apply only when that editor of record is CapCut Web.

Official Holiday Twist is still the routine voice when the editor of record is not CapCut Web. In that case the host must generate that preset on the official CapCut Text to Speech page only, without importing picture, then import the audio working copy into the editor of record. That TTS sidecar is not a second case and not a substitute voice. Do not offer a ChatCut voice picker or a new CapCut Web project to obtain Holiday Twist.

The host must track task ownership internally without persisting sensitive tab/session values in portable artifacts. It must not close unrelated tabs or windows.

If login is lost, use only the official site and an already-authorized browser session or saved autofill. Do not display, read, copy, log, or export credentials, cookies, or tokens. For CapCut or TikTok, account ambiguity, CAPTCHA, 2FA, recovery, or new consent requires `HOLD_CAPCUT_LOGIN_USER_ACTION_REQUIRED`. For the Checkpoint 1 script draft, open only `https://gemini.google.com/` in this Mac's Google Chrome.app. Do not use the agent-controlled browser as a substitute for that Chrome session. Do not switch the Cursor parent model to write the script. Select Gemini 3.8 Flash and read that label back; any other picker value is `HOLD_GEMINI_MODEL_NOT_VERIFIED`. Treat login, CAPTCHA, 2FA, recovery, or new consent as `HOLD_GEMINI_LOGIN_USER_ACTION_REQUIRED`. Missing Chrome Gemini origin is `HOLD_GEMINI_WEB_NOT_VERIFIED`; write the key-free paste prompt with `scripts/render_gemini_web_prompt.py` so the operator can finish the chat in Chrome. Do not call the Gemini API for that draft. Never put Google, Gemini, CapCut, or TikTok passwords in repository files or prompts.

## Visual and audio evidence adapter

The host must inspect real rendered frames, not only timeline JSON. It must support:

- first valid, representative midpoint, and last valid frame evidence for every cut;
- frame-level source/caption/TTS boundary inspection at sufficient zoom;
- caption visual proof from composed frames (centered, prominent, one layer per cut). JSON `top` / `offsetYRatio` is not proof. Official CapCut template metadata only when that editor is CapCut Web and a template was actually applied;
- uninterrupted full playback and same-project reload verification;
- audible speech verification, including missing, truncated, duplicated, overlapping, or residual source audio.

If the host cannot reliably hear audio, it may complete structural checks but must keep auditory status pending and expose the full listening checklist at Checkpoint 3. It must not claim completion from waveform presence alone.

## Optional Drive adapter

Use for the default `drive` completion path, or when the original request fixed Drive 格納. The adapter must locate exactly one parent folder whose title is the verified product model, prove no same-name collision, create one new file from local bytes, and read back exact name, MIME, byte size, new object identity, parent scope, and observation time. Never persist raw Drive IDs in git-tracked files. `export_only` is allowed only when the original request explicitly required local-only export.

Do not encode the completed video as base64 in a tool argument. Do not attempt a Drive create that inlines completed-video bytes. Prefer a local-path or upload-session ingest. If that is unavailable, one already-authenticated Drive UI upload into the proven parent is allowed, then adapter read-back. Do not create a same-name empty or path-string decoy. If the parent is proven but no local-byte path exists, `HOLD_DRIVE_LOCAL_BYTES_UNAVAILABLE`.

Unknown result, missing folder, multiple matching folders, collision, or mismatched read-back is a HOLD. Never overwrite, rename around a collision, or automatically retry an unknown upload.

## Rule snapshot adapter

Reusable rules are input data, not hidden assistant memory. The portable convention is:

```text
<rules-root>/common.md
<rules-root>/stages/<script|edit|delivery>.md
<rules-root>/products/<model>/common.md
<rules-root>/products/<model>/<script|edit|delivery>.md
```

Only existing regular files from those exact locations are included, in that order. Use `scripts/build_rule_snapshot.py` to create an immutable task-owned JSON snapshot. Candidate notes, case archives, chat history, and unreviewed suggestions are not active rules.
