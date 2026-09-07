# Methods to keep

These are the production methods. Values (product, media, settings, Drive folder title) change per case.

- One case = a new case ID, task root, workflow state, and editor-of-record project. Do not overwrite an existing video, project, export, Drive original, payload, or receipt.
- Routine approvals are only `台本OK`, `粗編集OK`, and `完成・書き出しOK`. Do not add a fourth checkpoint. Quality gates are internal and use `HOLD_CRAFT_QUALITY`.
- Product model, settings file `config/product_video_settings_<MODEL>.v1.json`, material root, and Drive parent title are per-case inputs. Do not reuse another product's settings, media, script, editor project, or Drive object.
- Checkpoint 1 dialogue is drafted in this Mac's logged-in Gemini.app at Gemini 3.8 Flash. Do not switch the Cursor parent model, call the Gemini API, or use Chrome.app / the agent browser for that draft.
- Spoken arc: `problem_or_hook -> product -> use_or_change -> result -> problem_resolution -> cta`. The hook names a viewer problem. `result` may show the visible change. `problem_resolution` must answer that same problem, not restate looks or blocked sunlight.
- Picture is confirmed at `粗編集OK`. Do not lock six source files before spoken lines exist. After lines exist, prove in/mid/out frames of the chosen range; do not default to the first N seconds of a usable take.
- Official Holiday Twist is the routine voice. Bulk paste frozen lines with a blank line between them, capture result-card audio into the case TTS directory, insert measured silent gaps, and split to one clip per narration-target caption.
- Viewer captions sit at screen center, prominent, one layer per cut. Wrap overflowing frozen lines visually without changing characters.
- For every non-final cut, source, caption, and TTS share the same start and end. Only the configured final cut may keep a visual-and-caption tail after narration.
- After exact `完成・書き出しOK` bound to the current final-QA receipt: export once, upload once with the portable `upload_drive_local_file.py`, read back, then purge this case's local working copies. If a step cannot be proven, HOLD. Do not guess.
