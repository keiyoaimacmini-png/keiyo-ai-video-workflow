# Methods to keep

These are the production methods. Values (product, media, settings, Drive folder title) change per case.

- One case = a new case ID, task root, workflow state, and editor-of-record project. Do not overwrite an existing video, project, export, Drive original, payload, or receipt.
- Routine approvals are only `台本OK`, `粗編集OK`, and `完成・書き出しOK`. Do not add a fourth checkpoint. Quality gates are internal and use `HOLD_CRAFT_QUALITY`.
- Product model, settings file `config/product_video_settings_<MODEL>.v1.json`, material root, and Drive parent title are per-case inputs. Do not reuse another product's settings, media, script, editor project, or Drive object.
- Checkpoint 1 dialogue is drafted in this Mac's logged-in Gemini.app at Gemini 3.8 Flash. The agent sends the prompt and reads the dialogue in the same turn. Do not ask the operator to paste. Do not switch the Cursor parent model, call the Gemini API, or use Chrome.app / the agent browser for that draft.
- Spoken arc: `problem_or_hook -> product -> use_or_change -> result -> problem_resolution -> cta`. The hook names a viewer problem. `result` may show the visible change. `problem_resolution` must answer that same problem, not restate looks or blocked sunlight. Spoken lines are short TikTok copy. Do not present Checkpoint 1 until the script craft check passes.
- Picture is confirmed at `粗編集OK`. Do not lock six source files before spoken lines exist. After lines exist, prove in/mid/out frames of the chosen range; do not default to the first N seconds of a usable take. Consecutive cuts must not continue the same place, distance, and camera angle. Related sequential actions are allowed. Trim unused source so the claimed action is the point of the range, then match that range to audible speech.
- Official Holiday Twist is the routine voice. Generate one render per narration-target cut (that cut's frozen line only), capture result-card audio into the case TTS directory without asking the operator to Save or download, and place one clip per caption. Do not bulk-paste every line.
- Do not stop a turn to ask the operator to confirm, watch, save, or download when the agent can do that work. Continue the same turn, or HOLD with one actionable operator step.
- Viewer captions sit at screen center, prominent, one layer per cut. Wrap overflowing frozen lines visually without changing characters.
- For every non-final cut, source, caption, and TTS share the same start and end. Only the configured final cut may keep a visual-and-caption tail after narration.
- After exact `完成・書き出しOK` bound to the current final-QA receipt: export once, and in that same turn upload once with the portable `upload_drive_local_file.py`, then read back. Do not open Chrome.app for 格納. A 16–22MB file should finish in tens of seconds. Then purge this case's local working copies. If a step cannot be proven, HOLD. Do not guess.
