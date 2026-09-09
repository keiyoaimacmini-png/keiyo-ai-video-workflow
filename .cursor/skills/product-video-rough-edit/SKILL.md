---
name: product-video-rough-edit
description: Place approved narration, selected video, and exact telop into a usable rough edit, then stop for the operator. Use only when /product-video dispatches ROUGH_EDIT.
disable-model-invocation: true
---

# ROUGH_EDIT

Read this file only when dispatch says `product-video-rough-edit`.

Create one new editor project for this case. Confirm its identity before placing clips.

Place:

- approved narration (1.2x, measured durations)
- selected video from the assembly plan
- telop whose text **exactly** equals the approved script line

Center telop with the editor caption program. On ChatCut, apply saved preset `product-video-center` once. Do not restyle from scratch. Visual wrap only; do not add, delete, or reorder characters.

Do not run AI craft scoring or a subjective final visual-quality review. Do not require `粗編集OK`.

When a usable rough edit exists, save the receipt, complete `ROUGH_EDIT` (this sets `WAITING_FOR_OPERATOR`), and tell the user:

粗編集まで完了しました。
手動で確認・修正してください。
修正完了後「完成・格納してください」と送ってください。

Then stop. Do not keep editing.
