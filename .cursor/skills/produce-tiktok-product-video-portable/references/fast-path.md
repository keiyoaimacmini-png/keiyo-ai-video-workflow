# Fast normal path

## 1. One preflight pass

- Read project instructions and local project context once.
- Resolve exactly one product settings file and hash it. Confirm this model's material folder exists. Do not hash or watch the material root.
- Draft the selected dialogue and per-line picture brief with Antigravity CLI (`agy --print`) on this Mac, with Gemini 3.8 Flash. The Gemini brief is `verified_facts` plus the internal product model. Do not send inventory, `usable_shots`, or observed actions. Gemini compares concepts internally and returns one draft; do not ask it for a twenty-candidate list. Do not switch the Cursor parent model. Do not call the Gemini API. Do not set `GEMINI_API_KEY`. Do not enable AI Credit overages. Do not use Gemini.app, Google Chrome.app, or the agent-controlled browser for that draft. Render with `scripts/render_gemini_web_prompt.py` and send that output only with `scripts/send_gemini_cli_prompt.py`. Do not append rule files, lessons, or product examples. Do not screenshot, OCR, or Accessibility-hunt. Do not ask the operator to paste. If login, CAPTCHA, 2FA, or account choice is required, `HOLD_GEMINI_LOGIN_USER_ACTION_REQUIRED`. If `agy` is missing or the one-shot fails, `HOLD_GEMINI_CLI_NOT_VERIFIED`. If the model is not Gemini 3.8 Flash, `HOLD_GEMINI_MODEL_NOT_VERIFIED`.
- Verify the six-stage script and that `problem_resolution` presents a solution to the same hook problem. Unmatched cuts stay `additional_asset_required`. Wording-only corrections use `scripts/apply_spoken_lines.py`.
- Stop Checkpoint 1 on the spoken script only. Source path, in/out, and contact sheets wait until after `台本OK`.
- Resolve the canonical final visual from **this** model's settings as the later matching target. Default Drive destination is the one folder titled with this product model unless the original request explicitly required `export_only`.
- Build and validate the canonical payload before Checkpoint 1. Do not run `prove_source_range.py` before `台本OK`.

Run independent read-only checks in parallel where the active environment supports it. Preserve one canonical payload and one execution plan; do not duplicate them per operation.

## 2. Rough edit after `台本OK`

- Match `picture_must` (and rank with `picture_ideal`) to files. Use `.asset.md` interval tables when they exist. Do not hash or watch the whole material root.
- Prove only the selected ranges with `scripts/prove_source_range.py`. Hash only those selected files. Do not default to the first N seconds of a usable take. Bind those sources on a new payload with the same visible-content hash.
- Read back the case editor of record and create a different new project. Do not create a successor CapCut Web case for Holiday Twist.
- Import only the selected assets in the host ingest helper's maximum batch when that helper exists.
- Apply the exact frozen captions with the case editor's caption program; do not use Motion Graphics as the caption layer; do not generate TTS yet.
- Verify distinct assets, source ranges, visual changes at caption boundaries, mute state, timing, and the full canonical final visual.
- Confirm the approved payload timing against the actual rough timeline. If wording, facts, or stage order must change, preserve the current evidence and return to a revised Checkpoint 1; never rebind the existing `台本OK`. If only the source asset or range must change, stay at Checkpoint 2, write a new versioned payload with the same visible-content hash, and do not ask for `台本OK` again. A later settings-bounded common-speed adjustment is a finish-time value, not a Checkpoint 1 reopen trigger.
- Build the hash-bound execution plan and request Checkpoint 2.

Do not create a separate upload checkpoint.

## 3. Finish after `粗編集OK`

- Validate the approved execution plan before any credit-consuming action.
- Place centered, prominent, visually wrapped captions with the case editor's caption program. On ChatCut, apply `product-video-center` once (Dela Gothic One, white fill, 14px black stroke, drop shadow, highlight off, no background band). Do not add a caption background band. Do not write wrap-limit or pacing fields after custom cards exist, and do not refresh. Official CapCut text templates are optional and never a HOLD. If one card still clips after wrap, shrink that card only; do not regenerate TTS. The final caption must hold through the last timeline frame. Do not clone the same TTS asset to extend ChatCut cards. `cue_override` JSON is not proof.
- Generate official Holiday Twist immediately, one frozen line per narration-target cut. If the editor of record cannot emit that preset, use the CapCut Text to Speech sidecar (no picture, no substitute voice, no new case, no bulk paste of every line). Capture each result-card audio bytes into the case TTS directory with `scripts/capture_capcut_result_audio.py`. Do not click オーディオのみ, do not use a save dialog, do not wait for `~/Downloads/CapCut_TTS_*`, do not ask the operator to press Save, do not regenerate a successful cut, and do not click さらに編集. Do not pause for a Path 1 / Path 2 choice.
- Generate one Holiday Twist render per narration-target cut. Paste only that cut's frozen line. Do not bulk-paste every line. Place one TTS clip per caption. Three-layer ends follow that cut's audible speech end.
- Enter self-repair only for the failing cut. Preserve already verified cuts.
- Apply a settings-bounded common TTS speed when needed, then retime the derived source/caption/TTS boundaries together. Do not change source asset/range, visible action, wording, line breaks, or voice identity after approval; HOLD only when one of those frozen inputs or an out-of-settings speed would be required.
- Reconcile all source, caption, narration-target, and TTS records by `cut_id`.
- For every cut, prove source-clip existence, exact source mute, one caption layer, and non-black first/mid/last rendered frames.
- Play the full timeline after structural closure, observe every boundary, reload the same saved project, and repeat the completion check.
- Verify caption safe areas at visible start and final animation state.
- Validate the non-final-slack, frame-level track-pairing, and timeline-integrity receipts and bind all three into final QA.
- Request Checkpoint 3 only after the editable timeline is actually complete. Put the editor link, structural result, and (when needed) the Japanese listening checklist in that same stop message.

## 4. Export and delivery after `完成・書き出しOK`

- Read back the exact date/model ordinal ledger and the Drive parent/collision state immediately before export, in the same preflight pass. The filename date is that JST **格納日**, not the case ID or editor project date.
- Confirm the exact name does not already exist in the output and qualifying Drive scope.
- Export once and verify the local completed file receipt.
- If pre-authorized by `完成・書き出しOK` and `delivery_mode: drive`, upload in that same turn with `scripts/upload_drive_local_file.py` from the local export into the folder whose title matches this product model in exact case. Do not inline the video as base64. Do not open Chrome.app for 格納. Do not screenshot, OCR, or click-hunt Chrome.app. If the helper HOLDs, stop; do not fall through to a Drive Web UI loop. Do not use Google Drive for desktop. Do not copy into Downloads. A 16–22MB file should finish in tens of seconds.
- Read back the new Drive file identity, exact name, MIME, byte size, parent scope, and time.
- Close only task-owned Chrome tabs after Drive read-back. Unknown ownership leaves tabs open and does not block `COMPLETE`.

Never interpret a request acknowledgement or progress display as a completed export or delivery.

## Skip these time sinks

Do not spend a turn on work that already failed this product:

- Do not hash or watch the material root before `台本OK`. Do not make `台本OK` wait on contact sheets. After that approval, prove and import only selected ranges.
- Do not reopen `台本OK` for a picture-only source swap. That is Checkpoint 2.
- Do not stall overnight waiting for a browser, download, or login. Same turn: either continue or stop with the matching HOLD so the operator can act.
- Do not screenshot, OCR, or Accessibility-hunt Gemini.app or Google Chrome.app. Send Gemini drafts only with `scripts/send_gemini_cli_prompt.py`. If that helper HOLDs, stop. Do not dump `entire contents` or rediscover a UI tree. Do not ask the operator to paste.
- Do not rewrite production-payload hashes by hand after a dialogue correction. Use `scripts/apply_spoken_lines.py`.
- Do not hand-write ffmpeg contact sheets. Use `scripts/prove_source_range.py`.
- Do not pause after `粗編集OK` for Path 1 (substitute voice) or Path 2 (new CapCut case). Continue into Holiday Twist immediately.
- Do not transcode or rebuild picture on CapCut to obtain Holiday Twist. Use the TTS sidecar.
- Do not replace Caption Cards with Motion Graphics at finish. Keep the rough caption program and apply `product-video-center`. Do not restyle from scratch. Do not rematerialize custom cards with wrap-limit writes or `refresh`.
- Do not clone the same TTS asset as a muted caption-hold. Do not treat ChatCut `cue_override` success as a closed final tail.
- Do not export on `完成・書き出しOK` while the case is still `FINISHING`. Bind that phrase only at `FINAL_REVIEW` to the current final-QA receipt.
- Do not paste a new CapCut TTS line on leftover textarea text. Prove one frozen line per result card.
- Do not paste every frozen line into one bulk Holiday Twist render.
- Do not default a source range to the first N seconds of a usable take. Prove in, midpoint, and out frames first.
- Do not inline the completed video as base64 in a Drive create. Use `scripts/upload_drive_local_file.py`, then adapter read-back.
- Do not copy the export into Downloads.
- After `完成・書き出しOK`, do not rebuild already-bound receipts or docs. Ledger, collision, export, same-turn local ingest, adapter read-back. Do not leave 格納 for a later turn.
- Do not add `音声確認OK`. Put the Japanese listening checklist in the Checkpoint 3 stop message.
- Do not delay `COMPLETE` for unknown tab ownership. Leave those tabs open.
- On this Mac, check Finder Downloads for the exact completed filename first, then repo `outputs/` and `out/` only if those copies exist. Missing copies are not a failure.
