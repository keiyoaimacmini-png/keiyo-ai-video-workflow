---
name: product-video-rough-edit
description: Place approved narration, selected video, and exact telop into a usable rough edit, then stop for the operator. Use only when /product-video dispatches ROUGH_EDIT.
disable-model-invocation: true
---

# ROUGH_EDIT

Read this file only when dispatch says `product-video-rough-edit`.

Use **one** editor project for this case. Create it if this case has none. Confirm its identity before placing clips. Do not create a successor project in a later stage.

Read `edit-plan.json`. Execute it. Do not reselect video. Do not rewrite telop. Do not invent a new cut plan. Duration already passed in ASSEMBLY.

ChatCut is execution only. Run `chatcut_steps` in order:

1. `import_batch` — unique audio + video paths, max 4 files per `import_media` session; repeat until the plan's batches are done
2. `place_audio` — one batched `edit_item` adds from the plan
3. `set_playback_rate` — `playbackRate=1.2` on those audio items
4. `place_video` — plan `source` / `source_in` / `source_out` trimmed to the sped narration span
5. `caption_preset` — apply saved preset `product-video-center` once
6. `place_captions` — exact frozen line; use `caption_visual_wrap` for display newlines only

Do not discover a short clip after placement and reselect. Do not decide wrap inside ChatCut.

After `edit_item` sets `playbackRate` to 1.2, prove with `inspect_item` and:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/prove_tts_speed.py" --record-json '{"playback_rate":1.2,"speed_readback_source":"chatcut_item"}'
```

Record timeline start/end and measured playback duration from ChatCut. Do not copy the calculated `planned_duration_seconds` and call it measured. Do not apply 1.2 a second time. Do not FFmpeg-accelerate the source file.

Visual wrap only; do not add, delete, or reorder characters. `unwrap(caption_visual_wrap) == approved line`.

Do not run AI craft scoring or a subjective final visual-quality review. Do not require `粗編集OK`. Do not chat progress between execution steps.

When a usable rough edit exists, save the receipt, complete `ROUGH_EDIT` (this sets `WAITING_FOR_OPERATOR`), and tell the user the `on_success_message_ja` from dispatch (or `operator_message_ja` from the helper). That is one message. If Drive is not READY, the same message already includes the Drive login hint. Do not send a second message. Do not ask for extra operator steps.

Default:

粗編集まで完了しました。
手動で確認・修正してください。
修正完了後「完成・格納してください」と送ってください。

When Drive is not READY, that same message is:

粗編集まで完了しました。
手動で確認・修正してください。
Drive格納準備:
リポジトリルートで
upload_drive_local_file.py --login
を済ませてください。
修正完了後「完成・格納してください」と送ってください。

Then stop. Do not keep editing.
