# Edit-stage rules

Official Holiday Twist is the only routine voice. Generate from frozen caption/script wording after `粗編集OK`. Do not offer a ChatCut substitute voice, a voice-identity reopen, or a new CapCut Web case to obtain that preset.

The case has one editor of record for picture, captions, mute, and export. If that editor cannot emit the CapCut official Holiday Twist preset, generate the audio on the official CapCut Text to Speech page only, one frozen line per narration-target cut. Do not paste every frozen line into one bulk render. Do not import picture into CapCut. After each result card exists, capture its media URL (`video`/`audio` currentSrc, typically `mime_type=audio_mpeg`) into the case TTS working directory with `scripts/capture_capcut_result_audio.py`. Do not click オーディオのみ. Do not use Finder, OS, or embedded-browser save dialogs. Do not wait for `~/Downloads/CapCut_TTS_*`. Do not ask the operator to press Save. If a save dialog appears, dismiss or ignore it and capture the result-card bytes instead. Do not regenerate a successful cut, and do not click さらに編集. Import that working copy into the case editor as that cut's TTS clip. This TTS sidecar is not a second editor and does not create a successor case.

Routine generation is one CapCut render per narration-target cut. Paste only that cut's frozen line. Do not insert ellipses, extra spoken punctuation, filler words, or blank-line scene separators as generation input. Each successful per-cut render consumes that cut's initial generation slot.

After capture:

1. Place that working copy as the cut's single TTS clip.
2. Close three-layer timing from that cut's audible speech end and the common speed.
3. Do not leave one combined narration clip on the timeline.
4. Do not use `scripts/prepare_bulk_tts_scene_gaps.py` on the routine path.

If a cut's speech cannot be read back, HOLD. Do not guess cut points inside speech. Align each cut to that frozen line's audible end. Trim unused picture head and tail so the remaining frames are the claimed action; do not speed the read-aloud so the showcase is unused.

Place final captions with the case editor's caption program (ChatCut Caption Cards or CapCut native captions). Do not use Motion Graphics as the viewer-facing caption layer. Place them at screen center with heavy weight, thick stroke, and a contrast band. Wrap overflowing frozen lines visually at existing punctuation; do not change wording. The last-cut tail may keep a matching centered hold after TTS ends.

Host-editor caption traps:

- Opacity zero is not removal proof. Exactly one visible caption layer per cut.
- If adjacent caption cards share a bulk-ASR token at a half-open boundary, reset the neighbors before rewriting the middle card.
- Do not refresh captions while a caption-hold audio track is muted.
- Composed viewer pixels beat caption JSON geometry (`top`, `offsetYRatio`). Centered on screen is required even when JSON reports another slot.
