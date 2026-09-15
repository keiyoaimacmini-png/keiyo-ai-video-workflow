---
name: product-video-rough-edit
description: Place approved narration, selected video, and exact telop into a usable rough edit, then stop for the operator. Use only when /product-video dispatches ROUGH_EDIT.
disable-model-invocation: true
---

# ROUGH_EDIT

Read this file only when dispatch says `product-video-rough-edit`.

Use **one** editor project for this case. Create it if this case has none. Confirm its identity before placing clips. Do not create a successor project in a later stage.

Read `edit-plan.json`. Execute it. Do not reselect video. Do not rewrite telop. Do not invent a new cut plan. Duration already passed in ASSEMBLY. Do not judge, re-rank, or rebuild `chatcut_steps`.

This stage is **one-pass**. Stay in `product-video-rough-edit` until `final_verify` finishes. Do not return to `/product-video` dispatch between steps. Do not ask the LLM for a new plan. Do not write a per-cut receipt. Do not chat per cut.

ChatCut is execution only. Run `chatcut_steps` in this order, one direction:

1. `import_batch` — unique audio + video paths, max 4 files per `import_media` session; repeat until the plan's batches are done
2. `place_audio` — one batched `edit_item` `adds` for every cut
3. `set_playback_rate` — one batched `edit_item` `updates` with `playbackRate=1.2` on those audio items
4. `place_video` — one batched `edit_item` `adds` from `chatcut_steps`. Most cuts are one video item. If a cut has `video_segments`, place those items back-to-back on the same video track for that narration span only. Do not reselect, loop, freeze, or change playback speed
5. `caption_preset` — apply saved preset `product-video-center` once
6. `place_captions` — exact frozen line; use `caption_visual_wrap` for display newlines only. Prefer one tool call for all cards. If the public tool accepts only one card, write every card without inspect or replan between writes
7. `final_verify` — the only verification pass

If a public ChatCut tool can process multiple items in one call, batch them. Never place → inspect → next cut → replan. Do not call `inspect_item` after each write. `inspect_item` may be 1-item-only; still wait until `final_verify` and then confirm all cuts together (`preview_timeline` first when that shows every item).

Record speed metrics only. After each step above, mark start/end (no chat):

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/timing.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --mark-step-start <project_setup|import|place_audio|playback_rate|place_video|caption_preset|place_captions|final_verify>
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/timing.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --mark-step-end <same-step>
```

`project_setup` is create/target of this case's ChatCut project. Do not add other metrics.

In `final_verify` only, prove `playbackRate` 1.2 from ChatCut item read-back:

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
