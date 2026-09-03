---
name: create-tiktok-product-video
description: Create a future new-product TikTok video plan and portable CapCut Web handoff with evidence-based product facts, per-cut media requirements, exact approval gates, and deterministic validation. Use for new TikTok product-video requests, not for changing existing video projects.
---

# Create TikTok Product Video

Use this skill only for a new product-video case. Never alter an existing project, draft, export, cloud item, database, favorite-monitor file, or external system.

## Start safely

1. Read the supplied product materials and record every item in a manifest. Separate verified facts, review observations, hypotheses, and not obtained; do not guess.
2. Put every available company observation in the manifest. `product_model_provenance` must close over all observed company models and be `verified`; a conflict is `HOLD_MODEL_UNVERIFIED`. Validate `^AN-[A-Z0-9]{4,6}$`.
3. If video exists, inspect it before selecting concepts. Use vision only when media sidecars do not establish the necessary visual evidence. Use UI only for session-bound retrieval or an already-approved CapCut action.
4. For a content concept, retrieve one `goal_axis` at a time from verified `favorite-context`; use reusable structure only and retain `not_to_copy`. Follow the project content-generation workflow when it is available.
5. Internally create and compare 20 unconfirmed concepts, select the strongest viable one without a separate concept-selection prompt, then build a canonical payload. Read [payload_contract.md](references/payload_contract.md) before drafting the payload or a portable handoff.
6. Require exactly one verified-model-matched `config/product_video_settings_<model>.v1.json`, hash it into the manifest, and create the canonical `product_settings` receipt containing the exact model/path/settings SHA-256 plus a hash-bound projection of CTA, voice, speed range, uniform caption template resource ID, and canonical final-cut catalog asset/range from that single file. Preserve the catalog ID literally (for example `A064`) and use a separate portable asset ID; when the catalog ID is not already portable, derive it exactly as `asset-` plus the lowercase catalog ID (for example `asset-a064`). Bind the reusable final block to both IDs, the settings SHA-256, and the video's common narration speed. Missing, duplicate, malformed, model/path/SHA-mismatched, ID-mapping-mismatched, or stale resolved settings are `HOLD_PRODUCT_VIDEO_SETTINGS`; do not duplicate or guess those values elsewhere.

## Script completeness gate

- A product video must form a complete progression: problem or hook -> product -> use or visible change -> result -> problem resolution -> CTA. `problem_resolution` shows how the observable result resolves the opening problem. Do not approve a script that omits a stage or only has a hook and CTA.
- Stage presence alone is not enough. Before selecting the winner from the 20 concepts and again before Checkpoint 1, read the visible dialogue straight through without stage labels and verify every adjacent line has a natural causal or conversational connection. The viewer must be able to follow why the observed problem or reaction leads to the product reveal, how the reveal leads to its use, and how the visible result answers the opening problem; pronouns or phrases such as “これ” must have an immediately understandable referent. Treat a sequence that validates structurally but feels like unrelated captions or makes an unexplained jump as a failed script, revise it inside Checkpoint 1, and rerun the affected hashes and validation. If verified facts and distinct supporting footage cannot supply a natural bridge, choose another concept or stop rather than inventing one. This continuity check creates no extra user checkpoint.
- Map every stage, including `problem_resolution`, to verified product facts and source footage that visibly supports the exact statement. One cut may cover adjacent stages only when both are clear; otherwise stop with `HOLD_SCRIPT_INCOMPLETE` or `HOLD_MEDIA_NOT_MATCHED`.
- Freeze the final wording, punctuation, and intended line breaks before TTS generation. Record each narration-target caption's Unicode code-point count and estimated read-aloud seconds, and require the estimate to fit its cut before generation. Any later wording or line-break change invalidates the payload hashes, edit approval, and prior TTS-placement verification.

## CapCut Web-only editor gate

- Perform approved editing only in the official CapCut Web editor in a browser. Do not open or operate the CapCut desktop application for this workflow.
- Before the first edit mutation, read back both the current page URL on the official `https://www.capcut.com/` origin and visible evidence that the page is the Web editor. A homepage, login page, desktop application, or appearance alone is not proof.
- If the official Web origin and active Web editor cannot both be verified, stop with `HOLD_CAPCUT_WEB_NOT_VERIFIED`. Do not substitute CapCut desktop, ChatCut, another editor, a local draft, or direct draft-file manipulation.
- An edit `OK` authorizes only the hash-bound edit in CapCut Web. It never authorizes touching an existing desktop draft or project.
- Treat every existing desktop project or draft as out of scope. Do not open, modify, rename, overwrite, move, or delete it unless the user separately identifies that exact desktop item and authorizes the specific action.

## Validate before requesting edit approval

- A verified problem/setup cut may use `product_visibility: "none"` when the actual source shows no product. Keep a non-empty `must_show` for the observed subject and never use that cut as evidence for an unobserved product claim.
- Record `semantics.subject` and every `must_show[*].subject` as truthful, non-empty descriptions of what is actually visible. Examples include person, product, hand, vehicle, landscape, and weather, but these are examples rather than an allowlist; never substitute an inaccurate category to satisfy validation.

Run the deterministic validator against the canonical payload:

```bash
python3 scripts/validate_product_video_payload.py payload.json
```

Run it from the project root containing `config/`, or pass `--settings-root <project-root>`. The validator hashes and parses the actual single model settings file; payload-internal manifest/receipt agreement alone is not trusted. It verifies canonical v4 hashes, strict schemas, the single model-matched product-settings receipt, the settings/common-speed-bound final block, the six-stage script flow, evidence-bound narration/voice/final-visual policies, ordered all-cut closure, checkpoint plans and receipts, production ordinal evidence, enum-derived media receipts or explicit asset holds, naming, portability, and cleanup preflight. Pending and not-applicable gates must already carry their exact checkpoint/action/count plan; approval only adds the exact receipt and never broadens it. It never repairs hashes or approvals. Completed-export read-back is the sole append-only outcome normalized for approval binding; changing the authorization plan still invalidates approvals. Run its self-test after changing the bundled validator:

```bash
python3 scripts/validate_product_video_payload.py --self-test
```

Resolve every error. Do not infer missing media, approval, or rights. Script, caption, and present TTS close exactly over every cut; final-cut text is `下からチェック！`, including when TTS is absent.

## Video-visible wording rules

- Use `下からチェック！` as the exact original-literal final-cut dialogue, caption, and present TTS text for every product video. Do not omit or normalize the full-width exclamation mark, add other words, or substitute a product-specific CTA.
- Keep the product model in manifest provenance, payload metadata, portable filenames, project names, and delivery paths, but omit it from video-visible or video-audible content by default. The exact model must not appear in `script.dialogue`, `captions.text`, or present `tts.text`.
- Do not remove or weaken model provenance to satisfy the visible-content rule. Internal identity verification and external delivery naming remain model-bound.
- Treat any change to these visible wording rules as a payload change that invalidates hashes and prior edit approval.

## Caption rendering gate

- Place every user-visible caption in the visual center of the frame. Center the text horizontally and use the central screen region; a bottom caption is not an acceptable substitute.
- Use a CapCut official text template for every caption. A standard subtitle card, manually styled text, ChatCut caption, or custom Motion Graphic does not satisfy this requirement.
- In the canonical payload, every caption sets `position: "center"` and carries `template_requirement: {"provider":"capcut","source":"official","resource_type":"text_template","resource_readback_required":true}`.
- Treat the template as verified only after reading back its actual CapCut resource ID and resource metadata from the approved CapCut Web draft. Desktop-draft metadata, appearance alone, a planned template name, or hand-authored styling is not proof.
- Verify the real CapCut Web player at the caption's visible start and final animation state. The complete rendering, including outline, shadow, and decoration, must be readable and fully inside the frame with clear margins.
- If CapCut Web cannot browse, apply, or read back a CapCut official template, stop with `HOLD_CAPCUT_TEMPLATE_NOT_APPLIED`. Do not silently replace it with another text system or switch to the desktop application.
- Keep every caption on the one CapCut official text template selected by the product settings file. Do not invent per-wording template selection; change the uniform template only after an explicit user rule update.

## Per-source caption, narration, and SFX rules

- Every canonical user-visible caption, including decorative captions with `narration_target: false`, must map to a different source asset and the visual must change when the caption changes. Reusing a `source_asset_id`, or a portable asset's `media_sha256` under another ID or path, is `HOLD_DISTINCT_ASSET_PER_CAPTION`. Different in/out ranges, splitting, duplicating, looping, cropping, speed, zoom, transition, or effect do not make a source distinct. The sole exception is the no-caption tail after the CTA, which may retain the canonical final asset.
- Every narration-target caption has exactly one corresponding narration clip on the editable timeline, and each narration reads that caption's wording. Treat whitespace and intentional line breaks as presentation-only; do not paraphrase, omit, combine, or split the spoken text across clips.
- Give each source clip exactly one caption. Give each narration-target caption exactly one narration clip. Both must begin at that source clip's timeline start, and neither may begin mid-source or extend beyond the source clip. Decorative text may omit TTS only when both its script and caption records explicitly set `narration_target: false`.
- Narration is required by default. Only a user-explicit, video-specific `narration: none` instruction may omit all TTS for that video; never carry that exception to another video or silently apply it to selected cuts.
- When the user has not specified a voice or preset, use the CapCut official `ホリデーツイスト` preset. The latest explicit video- or project-specific user choice overrides this default.
- Keep the narrator, CapCut voice preset, playback-speed multiplier, pitch, and voice processing consistent across the entire video. For TTS overflow, follow this exact order: (a) one common `1.2x`–`1.5x` TTS acceleration for every narration clip; (b) if still insufficient, replace the affected cut with a longer verified distinct source supporting the same statement; (c) if still insufficient, slow that video's caption/video while preserving its verified source range and truthful action. Record the ordered step statuses and SHA-bound evidence. Bind the historical prior range to its own portable asset media/sidecar hashes, require that prior asset ID and media SHA to be absent from all current selected cuts, prove that the replacement range is longer, and prove that slowdown extends timeline duration by `source duration / speed`. A slowed source is not distinct for any other caption. Never accelerate only some clips; disclose the resulting timing/speed at the next checkpoint.
- For every cut except the approved canonical final visual, trim the source clip and its caption to the narration end. Keep the final visual at its approved long or full source range by default even when its narration and caption end earlier; shorten it only on a video-specific explicit instruction.
- Sound effects are exempt from the per-source one-caption/one-narration count and their start/end alignment rules. Place and repeat SFX as the intended edit requires, while keeping them inside the video timeline and separately verifying that they do not obscure narration.
- In payload schema v4, bind a whole-video narration exception to an explicit user receipt, bind a non-default voice to an explicit override receipt, and bind the final long/full source range to its approved canonical asset receipt. Missing receipts are HOLD, not inferred approval.

## Voice placement and completion gate

- A TTS generation confirmation, credit deduction, preview, or success toast is not placement proof. After every generation, read back the editable timeline and verify that the expected narration clip actually exists on the expected TTS track for the expected cut, with the intended text, preset, speed, start, and end.
- Count the narration-target captions and the placed narration clips and require exact one-to-one closure. A missing clip is `HOLD_VOICE_NOT_ADDED`; do not report the video as complete, ready to export, or finished.
- After timeline read-back, automatically reconcile source clips, captions, narration-target captions, and placed TTS clips by `cut_id`. Require source count = caption count, narration-target caption count = TTS count, unique IDs, aligned starts, and cut containment; payload counts alone are not timeline proof.
- Play the complete timeline and audibly check every narration for presence, volume, intelligibility, matching caption, clean beginning and ending, overlap, duplication, and mid-sentence truncation. Also verify that no narration starts partway through its source or spills into the next source.
- If the current tool cannot hear or reliably judge the real playback, stop with `AWAITING_USER_AUDITORY_CONFIRMATION`. Structural metadata or waveform appearance alone cannot satisfy the auditory completion gate.

## Reusable final-cut block

- Define the canonical final catalog asset, its deterministic portable asset ID, source range, CTA caption, CTA TTS, uniform template, and voice policy once from the product settings file. `final_visual_policy.catalog_asset_id` preserves the settings literal and `final_visual_policy.asset_id` identifies the portable asset. Reuse the block without regenerating it only when both IDs, the settings SHA-256, and the video's common narration speed match the block's reuse key.
- A settings or common-speed change invalidates the reusable block. Placement still requires timeline read-back, and the approved long/full final visual must never be shortened merely because its caption or narration ends earlier.

## Three checkpoint approval and delivery boundaries

- Use at most three routine user checkpoints per video. At every checkpoint, state exactly what to inspect and its review location, and open/show it when supported. Any authorization-plan or visible-content change invalidates hashes, prohibition result, and every approval; never auto-rebind or reuse a stale receipt. An append-only, validator-checked export outcome may be recorded without changing the already-approved authorization subject, but it cannot broaden the approved action.
- Checkpoint 1 — script: show the selected concept and the full dialogue, punctuation, intended line breaks, selected source asset/path, exact source in/out, cut duration, Unicode character count, and estimated read seconds. Stop for exact `台本OK`. Revisions stay inside this checkpoint. `台本OK` authorizes rough visual edit only; it does not authorize TTS, credits, export, Drive, posting, send, cleanup, deletion, or overwrite.
- Checkpoint 2 — rough edit: show the actual review target/location and a rough CapCut Web edit with distinct selected sources, frozen captions, source ranges, timing, mute state, and the canonical final visual. State the exact narration-target-caption count and maximum first-attempt TTS/AI-credit spend, then stop for exact `粗編集OK`. It authorizes only finishing work, official template application, and one first-attempt TTS generation per narration target with necessary credits up to that disclosed count. It never authorizes a retry, credit purchase, export, Drive, posting, send, cleanup, deletion, or overwrite.
- Checkpoint 3 — final pre-export: show the actual review target/location and completed editable timeline after template/TTS/timing/full playback/read-back. Stop for exact `完成・書き出しOK`. It authorizes one new export. Only when the original request already specified Drive delivery and an exact destination scope, bind canonical request/destination subjects and their SHA-256 values; the same checkpoint then authorizes one new Drive upload plus read-back. Store the completed read-back as an append-only receipt with hashed file ID and parent scope, the exact current export filename, MIME type, byte size, a read-back time at or after export, and receipt hash. Never overwrite. Posting/publishing and external sends remain outside the three-checkpoint workflow and require a separate later request with its own destination/recipient subject and hash.
- Do not create routine extra prompts for concept selection, hook replacement, TTS/credits, auditory confirmation, timing adjustments, export, or qualifying Drive delivery. Resolve safe technical work inside the active checkpoint scope, consolidate material deltas into the next checkpoint, and HOLD instead of inventing authority. Existing `approval_gates` may share a checkpoint receipt only when that checkpoint explicitly disclosed and authorized every mapped action, remains bound to the current hashes, and stays within the scope above.
- For Camee Neo/OpenClaw-bound work, verify the HTTPS TikTok Shop destination before generation; otherwise hold. Run the prohibition policy after all visible text is final.
- After approved CapCut Web work, keep `Space/<model>/AI作成_<model>_<YYYY_MM_DD>` as the editable cloud project path. Before export, set `delivery.export_status: "pending"` with no `export_receipt`. When the download actually completes, record an offset-aware completion timestamp in `delivery.export_receipt.exported_at`, set `export_status: "completed"`, and derive the completed-video date from that timestamp in Asia/Tokyo rather than from payload creation time.
- Name each exported completed video exactly `YYYY_MMDD_<model>_AI作成<ordinal>` plus its file extension, using that real export-completion date and the verified production sequence marker (`①`, `②`, ... `⑳`). The sequence resets for every Asia/Tokyo actual export date plus exact model: the first completed export for that date/model is `①`. Before export, read a verified completed-export ledger for that exact scope and use `count + 1`; bind its verified timestamp, scope key, canonical snapshot SHA-256, and ordered prior-export records containing basename, export time, media SHA-256, and per-record SHA-256. Ambiguous, incomplete, fabricated-count, unordered, duplicate, or mismatched evidence is `HOLD_PRODUCTION_ORDINAL_UNVERIFIED`. Example: `2026_0826_AN-S182_AI作成①.mp4`. A payload created on an earlier day must still use the later actual export date.
- When qualifying Drive delivery is already within `完成・書き出しOK`, locate exactly one child folder whose title exactly equals the verified product model, check that the exact export filename does not already exist there, and upload as a new file only. If the model folder is absent, ambiguous, or already contains that filename, stop instead of guessing, creating an alternate name, or overwriting.
- After upload, read back the new Drive file's ID, exact title, MIME type, byte size, and parent folder ID. Require the title and MIME to exactly match the completed export receipt's filename, extension, and format; never accept an arbitrary extension. Do not report delivery complete from an upload request, progress indicator, or success toast alone.

## Chrome session lifecycle

- Use Chrome for the CapCut Web session. Treat CapCut authentication maintenance as browser-session recovery, not as edit approval or permission to change another project.
- If CapCut is logged out, stay on the official CapCut site, choose `TikTokでログイン`, and use only the TikTok session already signed in to Chrome or Chrome's saved-credential autofill. Do not display, copy, transcribe, log, export, or otherwise inspect a password or token. Do not switch to another login provider, account, or newly created identity.
- After authentication, read back the official CapCut Web origin, the signed-in editor state, and the exact intended new project before any edit mutation. If account choice is ambiguous, the saved session/autofill does not complete, or CAPTCHA, 2FA, recovery, new consent, or another user decision appears, stop with `HOLD_CAPCUT_LOGIN_USER_ACTION_REQUIRED`; never bypass it or guess.
- At the start of browser work, keep an internal task-owned list of only the Chrome tabs opened or used for this video; do not put tab IDs, account IDs, credentials, cookies, or session URLs in the portable payload or ordinary logs.
- After and only after Drive storage reaches verified read-back for the new video, close every task-owned Chrome tab used for its CapCut, TikTok-login, and Drive work. Read back that those exact tabs are gone. This standing instruction authorizes those tab closes without a fourth routine checkpoint.
- Never close an unrelated pre-existing tab or an entire mixed-use Chrome window, sign out, clear cookies/history/saved passwords, or change browser/account settings. If ownership of any tab is uncertain, leave it open and report `HOLD_TASK_TAB_IDENTITY_UNVERIFIED` rather than guessing. If Drive storage was not requested or has not reached verified read-back, do not trigger this storage-completion tab-close rule.

## Portable handoff and cleanup

Use classified stable asset IDs, SHA-256s, and normalized safe POSIX relative paths. Reject absolute paths, traversal, aliases, credentials, account IDs, and external-storage destinations.

Before cleanup, record a preflight only. Preserve originals, editable-project dependencies, shared assets, and uncertain items. List only hash-verified, explicitly approved `local_working_download` candidates by ID (never path); never delete or execute cleanup from this workflow.

## Model routing

Use routine deterministic work (manifest normalization, hashing, schema checks, naming, and validator runs) with a low-cost model or script. Use a frontier model for creative direction, evidence conflicts, and design QA. Escalate to vision only for insufficient sidecars, and browser UI only for session-bound retrieval or separately approved CapCut Web operations. Never route this workflow to the CapCut desktop app.
