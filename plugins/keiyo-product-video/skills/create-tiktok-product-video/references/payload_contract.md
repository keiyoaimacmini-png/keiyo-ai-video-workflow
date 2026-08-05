# Portable payload contract

Use this strict schema for future new-product work. Reject unknown fields and legacy aliases; never put a machine path, account ID, secret, or external-storage destination in the payload.

## Provenance and media

Each available company-authoritative manifest material records `material_id`, `sha256`, `access_status: "available"`, and `observed_product_models`. `product_model_provenance` closes over every such material with `status: "verified"`, exact material IDs/SHA-256s, and one observed model. A company-observation conflict is recorded as `status: "conflict"` and stops with `HOLD_MODEL_UNVERIFIED`.

Each cut has `media_requirements` with controlled `semantics`, exact `canonical_description`, structured `must_show`, and structured `must_not_show`. It has exactly one of:

- `matched_sidecar_receipt`: exact asset ID, sidecar SHA-256/path, `status: "verified"`, canonical requirements SHA-256, and `matched_fields: ["canonical_description", "semantics", "must_show", "must_not_show"]`.
- `additional_asset_required: true`: this blocks an approved edit.

Use controlled `semantics` (`subject`, `action`, `composition`, `product_visibility`, `text_visibility`) and its exact generated `canonical_description`; freeform media descriptions are invalid. Canonical cuts carry source/timeline ranges and editor fields. Script, captions, and TTS carry their cut timeline; captions/TTS also carry their editor fields.

`script`, `captions`, and present `tts` each close exactly over all cut IDs. The final script dialogue, caption text, and present TTS text exactly equal `下のカートからチェック`.

Each non-HOLD cut's `source_asset_id` must exactly equal its receipt asset ID. An `additional_asset_required` cut has no source asset/in/out fields. `manifest_ref` is ordered, duplicate-free, and exactly mirrors manifest ID/SHA order. Facts cite `material_refs` containing both a manifest ID and its exact SHA. Caption and present TTS ranges are contained within their corresponding cut. `post_set` is mandatory; QA has exactly the eight prescribed unique axes, maxima, and total.

Script, caption, and present TTS ranges are all contained within their cut. `facts_used.classification` is exactly `verified_fact`. QA metrics are exactly `watch_retention`, `comment_rate`, `save_rate`, `share_rate`, and `purchase_rate`, each `not_measured`. Manifest uses `source_location` only: either HTTPS or a safe relative path; `source_reference` is rejected.

Every cut, source, script, caption, and present TTS time range uses a non-bool int handled exactly or a finite float, with `0 <= start < end <= 86400`. Reject non-numbers, strings, nulls, NaN, infinity, negatives, zero-length, reversed ranges, and huge ints before containment checks.

## Integrity, routing, and portability

The validator computes `integrity.production_payload_sha256` and `integrity.visible_content_sha256`; it does not write them. Every approval and required routing receipt binds both exact hashes. OpenClaw requires a passed, checked-last prohibition receipt with `matched_rule_ids: []`. Camee Neo/OpenClaw also requires a verified `https://shop.tiktok.com/view/product/<numeric-id>` receipt with matching `product_id`, no userinfo, and no nonstandard port.

`created_at` is offset-aware. Its Asia/Tokyo date must produce `Space/<model>/AI作成_<model>_<YYYY_MM_DD>` and the identical completed-video basename. Portable assets include stable ID, media/sidecar SHA-256, safe POSIX relative paths, and classification flags (`original`, `editable_project_dependency`, `shared`, `uncertain`).

`cleanup_preflight` is preflight-only and has no path, execute, delete, or unknown field. Candidates cross-check a known asset by ID/media SHA and must be hash-verified local working downloads that are not original, dependency, shared, or uncertain.

The canonical payload also carries `goal_axis`, patterns, facts, hypotheses, audio, post set, eight-axis design QA, risk register, manifest closure, component hashes, and portable setup instructions. Each nested object is allowlisted; component hashes are validator-recomputed.
