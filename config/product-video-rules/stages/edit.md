# Edit-stage rules

Official Holiday Twist is the only routine voice. Generate from frozen caption/script wording after `粗編集OK`.

Bulk generation is allowed as one CapCut render of every frozen narration line. Paste those lines with a blank line between them. Do not insert ellipses, extra spoken punctuation, or filler words.

After download:

1. Align each frozen line to the bulk audio.
2. Insert a measured silent scene-split gap, default 600 ms, allowed 400–1200 ms, using `scripts/prepare_bulk_tts_scene_gaps.py`.
3. Cut only at those gaps so each narration-target caption has exactly one TTS clip.
4. Trim gap silence from clip edges, then close three-layer timing with the common speed.

If alignment or the detectable gaps do not close, HOLD. Do not guess cut points inside speech. Per-cut generation remains valid and does not need this gap insert.
