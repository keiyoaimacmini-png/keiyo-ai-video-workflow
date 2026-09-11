---
name: product-video-rough-edit
description: Place approved narration, selected video, and exact telop into a usable rough edit, then stop for the operator. Use only when /product-video dispatches ROUGH_EDIT.
disable-model-invocation: true
---

# ROUGH_EDIT

Read this file only when dispatch says `product-video-rough-edit`.

Use **one** editor project for this case. Create it if this case has none. Confirm its identity before placing clips. Do not create a successor project in a later stage.

Place:

- approved **source** narration audio (not pre-accelerated)
- ChatCut clip speed **1.2** on that audio item via `edit_item` `playbackRate` (not timeline preview speed, not a ChatCut voice regenerate)
- selected video from the assembly plan, trimmed to the sped narration span
- telop whose text **exactly** equals the approved script line, aligned to that same audio span

After `edit_item` sets `playbackRate` to 1.2, prove with `inspect_item` and:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/prove_tts_speed.py" --record-json '{"playback_rate":1.2,"speed_readback_source":"chatcut_item"}'
```

Record timeline start/end and measured playback duration from ChatCut. Do not copy the calculated `planned_duration_seconds` and call it measured. Do not apply 1.2 a second time. Do not FFmpeg-accelerate the source file.

Center telop with the editor caption program. On ChatCut, apply saved preset `product-video-center` once. Do not restyle from scratch. Visual wrap only; do not add, delete, or reorder characters.

Do not run AI craft scoring or a subjective final visual-quality review. Do not require `粗編集OK`.

When a usable rough edit exists, save the receipt, complete `ROUGH_EDIT` (this sets `WAITING_FOR_OPERATOR`), and tell the user:

粗編集まで完了しました。
手動で確認・修正してください。
修正完了後「完成・格納してください」と送ってください。

Then stop. Do not keep editing.
