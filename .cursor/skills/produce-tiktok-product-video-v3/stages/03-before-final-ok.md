# Before 完成・書き出しOK

Portable finishing and final QA may already have slack / pairing / integrity receipts. Do not ask `完成・書き出しOK` yet.

1. Inspect composed frames (not caption JSON) and write `product_video_caption_craft.v1`.
2. Run `validate_craft_quality.py --surface captions`.
3. Write `product_video_tts_craft.v1` from the actual timeline (`per_cut_generation`, combined clip, mid-speech cuts, frozen-line match, gap width, hearability, picture trimmed to speech, three-layer closure).
4. Run `validate_craft_quality.py --surface tts-timing`.
5. Rerun portable `validate_nonfinal_slack.py`, `validate_track_pairing.py`, and `validate_timeline_integrity.py` on their receipts.
6. If any craft or portable check fails, repair and rerun. Do not present Checkpoint 3.
7. If the host cannot hear the full timeline, keep auditory status pending inside Checkpoint 3. Do not add `音声確認OK`.
