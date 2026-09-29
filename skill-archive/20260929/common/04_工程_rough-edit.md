---
name: product-video-rough-edit-20260925
description: Place approved narration, selected video, and exact telop into a usable rough edit, then stop for the operator. Use only when /product-video dispatches ROUGH_EDIT.
disable-model-invocation: true
---

# ROUGH_EDIT

Read this file only when dispatch says `product-video-rough-edit`.

Use **one** editor project for this case. Create it if this case has none. Confirm its identity before placing clips. Do not create a successor project in a later stage.

Read `edit-plan.json`. Execute it. Do not reselect video. Do not rewrite telop. Do not invent a new cut plan. Duration already passed in ASSEMBLY. Do not judge, re-rank, or rebuild `chatcut_steps`.

This stage is **one-pass**. Stay in `product-video-rough-edit` until `final_verify` finishes. Do not return to `/product-video` dispatch between steps. Do not ask the LLM for a new plan. Do not write a per-cut receipt. Do not chat per cut.

Follow 02 の Gate A〜D. Gate definitions and acceptance criteria are not repeated here.

ChatCut is execution only. Run `chatcut_steps` in this order, one direction. Do not reorder. Do not mix audio and video in one import session.

1. `validate_tts` — run `validate_tts_audio.py --manifest` and proceed only under 02 の Gate A
2. `import_audio_batch` — valid audio only, max 4 files per `import_media` session
3. `place_audio` — one batched `edit_item` `adds` for every cut
4. `set_playback_rate` — one batched `edit_item` `updates` with `playbackRate 1.2` on every narration audio item. 1.2 is fixed for every product.
5. `import_video_batch` — wait until audio is valid and placed under 02 の Gate C. Video-only batches, max 4.
6. `place_video` — one batched `edit_item` `adds` from `chatcut_steps`. Most cuts are one video item. If a cut has `video_segments`, place those items back-to-back on the same video track for that narration span only. Do not reselect, loop, freeze, or change playback speed.
7. `caption_preset` — apply saved preset `product-video-center` once, then set the shared caption layout to left=108, top=316, width=864, height=287 on the 1080×1920 canvas. This is the operator-adjusted standard value. Do not leave the preset's initial top=1417.
8. `place_captions` — exact frozen line; use `caption_visual_wrap` for display newlines only. Prefer one tool call for all cards. If the public tool accepts only one card, write every card without inspect or replan between writes.
9. `final_verify` — the only verification pass.

Do not run video placement and TTS regeneration as parallel tracks. A half-finished ChatCut project with video and no valid audio is provisional, not done.

If a public ChatCut tool can process multiple items in one call, batch them. Never place → inspect → next cut → replan. Do not call `inspect_item` after each write. `inspect_item` may be 1-item-only; still wait until `final_verify` and then confirm all cuts together (`preview_timeline` first when that shows every item).

Record speed metrics only. After each step above, mark start/end (no chat):

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/timing.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --mark-step-start <project_setup|validate_tts|import_audio|place_audio|playback_rate|import_video|place_video|caption_preset|place_captions|final_verify>
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/timing.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --mark-step-end <same-step>
```

`project_setup` is create/target of this case's ChatCut project. Do not add other metrics.

In `final_verify` only, prove the fixed `playbackRate 1.2` from ChatCut item read-back:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/prove_tts_speed.py" --record-json '{"playback_rate":1.2,"speed_readback_source":"chatcut_item"}'
```

Record timeline start/end and measured playback duration from ChatCut. Do not copy the calculated `planned_duration_seconds` and call it measured. Do not apply 1.2 a second time. Do not FFmpeg-accelerate the source file.

Visual wrap only; do not add, delete, or reorder characters. `unwrap(caption_visual_wrap) == approved line`.

Do not run AI craft scoring or a subjective final visual-quality review. **MUST** Gate D: if placement/import/regenerate is expected to take >30s, emit a short heartbeat at least every ~30s (stage name + what just finished + next step). Do not stay silent through ChatCut import or CapCut regenerate.

When a usable rough edit exists, save the receipt, complete `ROUGH_EDIT` (this sets `WAITING_FOR_OPERATOR`), and tell the user the `on_success_message_ja` from dispatch (or `operator_message_ja` from the helper). That is one message. Drive未準備時の案内は dispatch が同じメッセージへ差し込む。Drive の正本は 04_工程_delivery.md。ログインや読戻しの手順をここに重複させない。Do not ask for extra operator steps.

Default:

粗編集まで完了しました。
手動で確認・修正してください。
修正完了後「完成・格納してください」と送ってください。

Then stop. Do not keep editing.
