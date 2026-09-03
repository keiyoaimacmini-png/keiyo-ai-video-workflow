# Edit-stage rules

Official Holiday Twist is the only routine voice. Generate from frozen caption/script wording after `粗編集OK`. Do not offer a ChatCut substitute voice, a voice-identity reopen, or a new CapCut Web case to obtain that preset.

The case has one editor of record for picture, captions, mute, and export. If that editor cannot emit the CapCut official Holiday Twist preset, generate the audio on the official CapCut Text to Speech page only (frozen lines separated by a blank line, one bulk render). Do not import picture into CapCut. Import the downloaded audio working copy into the case editor. This TTS sidecar is not a second editor and does not create a successor case.

Bulk generation is allowed as one CapCut render of every frozen narration line. Paste those lines with a blank line between them. Do not insert ellipses, extra spoken punctuation, or filler words.

After download:

1. Align each frozen line to the bulk audio.
2. Insert a measured silent scene-split gap, default 600 ms, allowed 400–1200 ms, using `scripts/prepare_bulk_tts_scene_gaps.py`.
3. Cut only at those gaps so each narration-target caption has exactly one TTS clip.
4. Trim gap silence from clip edges, then close three-layer timing with the common speed.

If alignment or the detectable gaps do not close, HOLD. Do not guess cut points inside speech. Per-cut generation remains valid and does not need this gap insert.

Do not shorten source or caption clips to match an isolated per-cut TTS file that is shorter than the bulk-aligned speech window. Three-layer ends follow the audible speech end of the bulk-aligned clip.

Place final captions with the case editor's caption program (ChatCut Caption Cards or CapCut native captions). Do not use Motion Graphics as the viewer-facing caption layer. Place them at screen center with heavy weight, thick stroke, and a contrast band. Wrap overflowing frozen lines visually at existing punctuation; do not change wording. The last-cut tail may keep a matching centered hold after TTS ends.

Host-editor caption traps:

- Opacity zero is not removal proof. Exactly one visible caption layer per cut.
- If adjacent caption cards share a bulk-ASR token at a half-open boundary, reset the neighbors before rewriting the middle card.
- Do not refresh captions while a caption-hold audio track is muted.
- Composed viewer pixels beat caption JSON geometry (`top`, `offsetYRatio`). Centered on screen is required even when JSON reports another slot.
