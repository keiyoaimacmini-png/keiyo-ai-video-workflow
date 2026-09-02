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

## Filesystem and process adapter

The host must be able to:

- read actual bytes, inspect MIME/type, compute SHA-256, and write new versioned task files;
- refuse overwrite by default;
- run Python 3 validators and preserve their exact exit status;
- resolve safe relative paths under trusted roots and reject escape or symlink ambiguity;
- obtain the real current time in the requested timezone.

Validator success never substitutes for live editor or storage read-back.

## Browser/editor adapter

The host must operate one editor for the whole case: the official CapCut Web editor, or a host-provided editor control surface that can create a separate new project, inspect timeline layers, inspect real frames, place captions and TTS, play the result, reload the same saved project, and export. Do not mix two editors in one case. CapCut official template resource IDs apply only when that editor is CapCut Web.

The host must track task ownership internally without persisting sensitive tab/session values in portable artifacts. It must not close unrelated tabs or windows.

If login is lost, use only the official site and an already-authorized browser session or saved autofill. Do not display, read, copy, log, or export credentials, cookies, or tokens. Account ambiguity, CAPTCHA, 2FA, recovery, or new consent requires `HOLD_CAPCUT_LOGIN_USER_ACTION_REQUIRED`.

## Visual and audio evidence adapter

The host must inspect real rendered frames, not only timeline JSON. It must support:

- first valid, representative midpoint, and last valid frame evidence for every cut;
- frame-level source/caption/TTS boundary inspection at sufficient zoom;
- official template resource metadata read-back;
- uninterrupted full playback and same-project reload verification;
- audible speech verification, including missing, truncated, duplicated, overlapping, or residual source audio.

If the host cannot reliably hear audio, it may complete structural checks but must keep auditory status pending and expose the full listening checklist at Checkpoint 3. It must not claim completion from waveform presence alone.

## Optional Drive adapter

Use for the default `drive` completion path, or when the original request fixed Drive 格納. The adapter must locate exactly one parent folder whose title is the verified product model, prove no same-name collision, create one new file, and read back exact name, MIME, byte size, new object identity, parent scope, and observation time. Never persist raw Drive IDs in git-tracked files. `export_only` is allowed only when the original request explicitly required local-only export.

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
