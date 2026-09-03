---
name: build-tiktok-product-video-rough-cut
description: Build and verify the rough CapCut Web timeline for a new product video after 台本OK, freeze edit inputs, and present Checkpoint 2. Use only when explicitly invoked or routed from produce-tiktok-product-video-portable at ROUGH_EDIT, or for an unapproved ROUGH_REVIEW revision.
---

# Build TikTok Product Video Rough Cut

Input stage must be `ROUGH_EDIT`, or `ROUGH_REVIEW` with `粗編集OK` still pending for a user-requested revision. Exact `台本OK` must remain bound to the current production payload and script-rule snapshot. Read the parent's core invariants, workflow-state contract, and:

- `${SKILL_ROOT}/references/execution-plan-contract.md`

Build and read the active edit-rule snapshot before opening the case editor:

```bash
python3 "${SKILL_ROOT}/scripts/build_rule_snapshot.py" --rules-root <rules-root> --stage edit --product-model <model> --output <task-root>/learning-edit.json
```

Register its safe relative path and actual SHA-256 as `learning_snapshots.edit`, and bind the same SHA into the `ROUGH_EDIT` stage receipt and task-owned rough-edit receipt. Candidate notes are not production rules.

On an unapproved review revision, record the correction first. Build a new versioned file such as `learning-edit-r01.json` only when the active rule set changed; otherwise keep the existing registered snapshot. Never overwrite or silently rebind a different prior snapshot.

## Build the rough edit

1. Verify the official editor of record for this case. On the normal path create one separate new project; on a `ROUGH_REVIEW` revision reopen and verify the exact same task-owned project instead of creating another. Do not open a previous product's project. Do not create a successor CapCut Web case for Holiday Twist.
2. Import only selected assets. When the host ingest helper accepts local files, upload in that helper's maximum batch rather than one picker pass per clip. Asset upload is part of rough editing and has no extra checkpoint.
3. Build one source per caption, change the visual at every caption boundary, use exact ranges, mute source audio unless explicitly needed, and retain the canonical final visual for its approved full range.
4. Add the frozen captions with the case editor's caption program when it has one (ChatCut Caption Cards or CapCut native captions). Do not use Motion Graphics as the viewer-facing caption layer. Do not generate TTS yet. Official CapCut text templates are optional and are not a later HOLD.
5. Confirm the script-stage timing estimates against the real rough timeline. If wording, line breaks, common voice settings, source asset, source range, or payload hash must change, do not alter them under the existing `台本OK`; use the controlled reopen procedure and return to the revised Checkpoint 1.
6. Verify actual rough-timeline source identity/range/timing/mute/caption closure and absence of duplicate text layers.

Build and validate the payload-bound execution plan:

```bash
python3 ${SKILL_ROOT}/scripts/validate_execution_plan.py execution-plan.json --payload payload.json
```

## Checkpoint 2

Freeze wording, line breaks, voice/preset, common speed, source assets, ranges, payload hash, and plan hash. Store the execution-plan and rough-edit receipt hashes. On the normal path record the `ROUGH_EDIT` binding and advance to `ROUGH_REVIEW`; during an unapproved `ROUGH_REVIEW` revision replace only that current draft binding and remain at `ROUGH_REVIEW`.

Show the actual rough timeline and review location, distinct asset IDs/media hashes, frozen captions/ranges, common speed, timing, mute state, final visual, narration cut IDs, initial TTS ceiling `N`, per-cut repair reserve `N`, total ceiling `2N`, and no-purchase/no-source-change rule. Stop only for exact `粗編集OK`.
