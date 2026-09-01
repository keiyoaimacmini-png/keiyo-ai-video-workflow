---
name: verify-tiktok-product-video-timeline
description: Independently verify every cut of a finished CapCut Web product-video timeline for source, captions, TTS, timing, playback, and safe-area correctness before Checkpoint 3. Use only when explicitly invoked or routed from produce-tiktok-product-video-portable at FINAL_QA, or to reverify an unapproved FINAL_REVIEW repair.
---

# Verify TikTok Product Video Timeline

Input stage must be `FINAL_QA`, or `FINAL_REVIEW` with `完成・書き出しOK` still pending after a bounded repair. Read the parent core invariants and workflow-state contract.

Use the same hash-bound edit-rule snapshot path registered in workflow state and verified during finishing. Do not read the live rule source as a replacement for the approved edit context.

Before creating the final-QA receipt, build and read the delivery-rule snapshot, register it as `learning_snapshots.delivery`, and bind its SHA-256 into the final-QA artifact so Checkpoint 3 can bind the exact delivery context:

```bash
python3 "${SKILL_ROOT}/scripts/build_rule_snapshot.py" --rules-root <rules-root> --stage delivery --product-model <model> --output <task-root>/learning-delivery.json
```

On an unapproved review revision, use a new versioned output such as `learning-delivery-r01.json` only if the active delivery context changed; otherwise keep the registered snapshot. Never overwrite or silently rebind a different prior snapshot.

## Verify all cuts, never a sample

Build an all-cut matrix with:

- `cut_id`, source asset ID/media SHA, source in/out, and timeline start/end;
- caption text, caption start/end, official template resource read-back, X/Y alignment, safe margins, and visible-layer count;
- narration-target flag, TTS text/preset/common speed/start/end, track identity, and cut containment;
- any BGM/SFX identity, timeline containment, level, and whether it obscures narration;
- boundary-frame visual change, source-audio mute state, and observed action match;
- playback result for clean start/end, intelligibility, overlap, duplication, truncation, spill, and caption/audio match.
- actual source start/end, caption start/end, TTS start/end, audible speech end, next-cut shared start, and `slack_frames` for every cut. Validate the resulting `product_video_nonfinal_slack_receipt.v1` with `${SKILL_ROOT}/scripts/validate_nonfinal_slack.py`; every non-final cut must have exact three-layer start/end equality and 0–1 audible-end slack, and only the configured final cut may declare the tail exception.
- source-clip identity and actual existence, exact source-audio track/clip mute (not low gain), and first-valid/midpoint/last-valid rendered-frame evidence for every cut. Each observed frame must contain the expected non-black source and exactly one rendered caption layer. Mute read-back is structured as the exact control, state `muted`, and null gain value; free text or attenuation values cannot pass.

Inspect the real player at every caption start, every caption boundary, and the final animation state. A centered coordinate in JSON is not visual proof. Exactly one visible text rendering may exist per cut. Verify the final CTA position separately.

For multi-track CapCut projects, expand the timeline vertically and compare the source clip, caption clip, and TTS clip belonging to the same `cut_id` at the same playhead. Never compare a caption or source against a visually adjacent clip from another track. Treat the official template's rendered entrance/exit animation separately from clip-edge timing: a partial rendered word at a static seek frame is not proof that the clip edge is late. Overview screenshots prove track structure only; they do not prove one- or two-frame equality. Zoom until the ruler scale gives at least 8 pixels per frame, capture every three-layer head and tail boundary, use the file's real extension/MIME, and bind independently observed source and caption edges to `product_video_track_pairing_receipt.v2`; bind TTS starts/ends and the exact three-layer equality in `product_video_nonfinal_slack_receipt.v1`. Validate both receipts before claiming exact equality.

```bash
python3 "${SKILL_ROOT}/scripts/validate_nonfinal_slack.py" <nonfinal-slack-receipt.json> --project-root <task-root>
python3 "${SKILL_ROOT}/scripts/validate_track_pairing.py" <track-pairing-receipt.json> --project-root <task-root>
```

After the non-final-slack and frame-level pairing receipts pass, write `product_video_timeline_integrity_receipt.v1`. It must hash-link those two actual receipts, reconcile their cut order and frame values, bind unique real JPEG evidence for each cut's first valid frame, midpoint, and last valid frame, prove exact source mute and source/caption/TTS presence, and record uninterrupted playback plus same-project reload. Validate it with:

```bash
python3 ${SKILL_ROOT}/scripts/validate_timeline_integrity.py <integrity-receipt.json> --project-root <task-root>
```

The static validator checks receipt closure and actual evidence bytes but does not observe CapCut itself. Create the receipt only from live UI/read-back evidence. If the active tool cannot hear reliably, structural checks may pass but auditory status stays pending. Put the full-listening checklist inside Checkpoint 3; do not create `音声確認OK`.

## Checkpoint 3

After all available checks pass, hash the all-cut QA receipt including the delivery-snapshot SHA, validated non-final-slack-receipt SHA, frame-level track-pairing-receipt SHA, and validated timeline-integrity-receipt SHA, then store `artifacts.final_qa`. On the normal path, record the `FINAL_QA` binding and advance to `FINAL_REVIEW`. During an unapproved `FINAL_REVIEW` recheck, replace only that current binding and remain at `FINAL_REVIEW`.

Show the actual editable timeline and review location, template resource, voice/common speed, per-cut closure, full playback, duplicate-text result, center/safe-area result, bounded repairs, remaining reserve, and the frozen delivery context. Stop only for exact `完成・書き出しOK`. Bind that approval to `artifacts.final_qa` and `learning_snapshots.delivery`. It authorizes one new export and, only when already fixed in the original scope, one new Drive upload/read-back and task-owned tab closure.
