# Execution plan v1

The execution plan is a JSON sidecar validated together with the actual canonical payload. It adds bounded repair authority without changing the base payload schema.

## Immutable plan subject

The plan contains:

- `schema`: exact `product_video_execution_plan.v1`;
- the actual `production_payload_sha256`;
- checkpoint `rough_edit` and approval text `粗編集OK`;
- ordered `narration_target_cut_ids` and their derived counts/caps;
- the fixed allowed and forbidden action lists from the validator;
- `tts_input_sha256_by_cut`, derived from each cut's actual script dialogue, caption text and line breaks, TTS text, voice, speed, pitch, processing, and timeline in/out;
- `plan_sha256`, calculated over all immutable plan fields.

The current action contract explicitly allows one settings-bounded common TTS-speed adjustment and derived live-timeline video/caption timing adjustment. It forbids per-cut or out-of-settings voice-speed changes. Do not use the legacy blanket `speed_change_after_rough_approval` prohibition in a current plan because it incorrectly blocks the mandatory overflow/closure repair order.

The `timeline in/out` values included in `tts_input_sha256_by_cut` are approved generation windows and provenance, not a claim that the live video/caption boundaries are permanently fixed before real TTS exists. Keep the append-only generation history unchanged. After real playback, record final boundary closure in a separate `product_video_nonfinal_slack_receipt.v1`; never rewrite old generation events to make provisional timing look final.

Run the validator against the actual payload; do not hand-copy hashes from another video:

```bash
python3 ${SKILL_ROOT}/scripts/validate_execution_plan.py execution-plan.json --payload payload.json
```

Pending approval has null bindings. Approved state uses exact receipt `粗編集OK` and binds both the unchanged `plan_sha256` and production payload SHA. The actual base credit gate must independently carry the same approved receipt and current production/visible hashes.

For `narration: none`, the ordered target list and TTS-input map are empty and all generation caps are zero.

## Append-only event ledger

Each event contains exactly:

- sequence, `cut_id`, event type, and offset-aware observation time;
- the approved plan SHA, production payload SHA, and that cut's frozen TTS-input SHA;
- hashed current/result clip identity, related old clip identity, and verification receipt as required by the event type;
- the previous event SHA and current event SHA.

The first event's `previous_event_sha256` equals the approved `plan_sha256`; later events point to the previous event. Never truncate, reorder, replace, or rehash prior events.

When a settings-bounded payload rebind changes the TTS-input fingerprints without generating new audio, keep the old event file append-only and add `carried_event_ledger` to the new plan. It must bind the actual sibling file bytes, source plan SHA, terminal event SHA, event count, per-cut generation-request counts, and validator-derived remaining allowance. An approved plan with an empty current `events` array is invalid without this verified carry binding; a payload rebind never resets consumed TTS or credit allowance.

The validator sums carried and current generation-request events against both the per-cut and total caps. A cut with carried spend cannot restart `initial_generation_requested`; any later authorized mutation must preserve the carried state and use only a valid continuation, never a fresh current-ledger start that resets prior consumption.

Event order per repaired cut is:

`initial_generation_requested -> initial_generation_verified|initial_generation_failed -> defect_confirmed -> repair_generation_requested -> repair_generation_verified|repair_generation_failed`

After a verified repair, continue through exactly one branch:

- when a defective old clip exists: `defective_clip_replaced -> timing_resynced`;
- when the initial clip was absent: `replacement_clip_adopted -> timing_resynced`.

The TTS-input map is a JSON object keyed by the target cut set; object key order is not significant. Chronological cut order comes only from `narration_target_cut_ids`.

`hold` terminates that cut's event flow. A generation-request event is appended immediately after the credit-consuming request and consumes the allowance even if the outcome is unknown or failed.

Hash raw CapCut clip/resource identity locally; store only the SHA-256 in the portable execution plan. The verification receipt hash must cover the official project read-back, `cut_id`, task-owned status, frozen TTS input hash, timeline placement, audible result when available, and observation time. For replacement, it must cover both old and new clip identity hashes and prove the replacement was verified before the defective clip was disabled or removed.
