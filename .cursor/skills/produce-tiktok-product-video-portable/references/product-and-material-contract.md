# Product, material, and delivery contract

This contract is the portable source of truth for values that change from one video to the next. The skill package stays the same. The product, the source media, the settings file, and the Drive folder title change.

Never copy another product's settings, script, cuts, captions, TTS, CapCut/ChatCut project, export, or Drive object into a new case.

## What stays the same

- Exactly three routine approvals: `台本OK`, `粗編集OK`, `完成・書き出しOK`.
- Six-stage script: `problem_or_hook -> product -> use_or_change -> result -> problem_resolution -> cta`.
- One new case, one new task root, one new editor project, no overwrite.
- Official Holiday Twist narration, one TTS clip per narration-target caption, settings-bounded common speed, three-layer timing.
- Centered, non-duplicated captions. Visual wrapping may insert display line breaks without changing frozen characters.
- After exact `完成・書き出しOK` bound to the current final-QA receipt: export once, then store one new Drive file unless the original request explicitly required `export_only`.
- After `COMPLETE` and verified 格納, purge this case's local working copies.

## What changes per product and per case

| Input | How to resolve | Never |
| --- | --- | --- |
| `product_model` | Exact user-supplied model matching `^AN-[A-Z0-9]{4,6}$`, then close provenance over this case's materials | Infer from a previous case, neighboring folder, or AN-S182 default when the user named another model |
| Settings | Exactly `config/product_video_settings_<product_model>.v1.json` | Copy AN-S182 or any other model file and rename it |
| Material root | `PRODUCT_VIDEO_MATERIAL_ROOT` if set, else `.runtime/product-video-inputs/<product_model>_コピー` | Reuse another model's media, Git-tracked media, or a previous case's import staging |
| Canonical final cut | The `final_cut_block` inside that model's settings file | Borrow another model's CTA clip or range |
| Caption template / voice | That model's `caption_template` and `narration` | Keep a previous project's template, font, or voice identity |
| Drive parent | Exactly one folder whose **title** is the verified `product_model` | Hard-code Drive IDs, URLs, or a folder named for a different model |
| Case / editor project | New case ID, new `outputs/<case-id>/`, new editor project | Reuse or overwrite an existing project, export, or receipt |

Resolve those inputs before creating a case:

```bash
python3 "${SKILL_ROOT}/scripts/resolve_product_inputs.py" \
  --project-root <project-root> \
  --product-model <model> \
  --require-materials
```

Do not continue past a HOLD result. A missing settings file is `HOLD_PRODUCT_VIDEO_SETTINGS`. Do not generate a substitute from another model.

AN-S182 is one current product in this repository. Its settings SHA-256 is pinned because that file is the verified canonical file for that model only. A new model gets its own file, its own materials, and its own Drive folder title.

## New product onboarding

1. Confirm the model string and that company-authoritative materials observe only that model.
2. Add `config/product_video_settings_<MODEL>.v1.json` with that model's CTA, official caption template, narration bounds, and canonical final-cut block. Hash the actual bytes.
3. Place this model's source media under the resolved material root. Do not commit media.
4. Optionally add `config/product-video-rules/products/<MODEL>/` for model-specific rules. Common and stage rules already apply.
5. On Drive, require exactly one parent folder titled `<MODEL>`. If it is missing or duplicated, `HOLD_DRIVE_SCOPE_AMBIGUOUS`.
6. Start a **new** case. Do not reopen an AN-S182 case to produce a different product.

## Default Drive 格納 after edit completion

This Cursor workflow's standing completion is Drive storage.

- Initialize new cases with `delivery_mode: drive` when the original request includes 格納 / Drive / ドライブ, or when it does not explicitly require local-only export.
- Initialize `export_only` only when the original request explicitly says 書き出しのみ / export_only / ローカルのみ.
- Exact `完成・書き出しOK` bound to the current final-QA receipt authorizes one new export and, for `drive`, one new Drive file plus exact parent read-back.
- `編集が完了した` / `格納して` is not a substitute for `完成・書き出しOK`.
- Do not upload a working copy, a ChatCut/CapCut preview, or an unverified export.
- Do not treat a local `out/` file as 格納.

Drive receipts store only hashed identity and safe metadata. Raw Drive IDs, URLs, and account identifiers stay out of Git, payloads, and ordinary logs.

## Caption layout that is not product-specific

These values apply to every product unless that model's settings override them:

- Place viewer-facing captions at **screen center**.
- If a frozen line overflows the safe width, wrap it visually at an existing punctuation or phrase boundary. Do not add, delete, or reorder characters. Spoken `tts.text` stays the frozen line.
- Make captions prominent: heavy weight, thick dark stroke, contrast band, and optional current-word highlight.
- Keep exactly one caption layer per cut. The canonical final cut may hold its last caption through the approved tail with a matching centered overlay after TTS ends.
- Script line breaks (which words belong to which cut) remain frozen at `粗編集OK`. On-screen wrapping inside a cut is layout, not a new script line.

## Operator sequence

Use this sequence on any PC that has the skill package, that product's settings file, and that product's materials.

1. Clone this repository. Do not commit media, exports, credentials, or Drive IDs.
2. Resolve `PROJECT_ROOT` and `SKILL_ROOT`. Run `resolve_product_inputs.py` and `verify_product_video_setup.py --product-model <MODEL> --require-materials`.
3. `PREFLIGHT`: inventory **this** model's materials, hash settings, compare twenty concepts internally, write a new script package. Advance to Checkpoint 1. Stop for exact `台本OK`.
4. `ROUGH_EDIT`: create a **new** editor project. One distinct source per caption. Frozen captions as rough text. No TTS yet. Stop for exact `粗編集OK`.
5. `FINISHING`: official template from **this** model's settings (or HOLD if the host cannot apply it), Holiday Twist from frozen lines, bulk scene-gap split when generated in bulk, three-layer timing, centered prominent captions.
6. `FINAL_QA`: all-cut source/caption/TTS, mute, frames, playback, reload, safe area. Stop for exact `完成・書き出しOK`. If the host cannot hear, keep auditory verification pending at this same checkpoint.
7. `EXPORT_AND_DELIVERY`: one new export name, export once, Drive-store into the folder titled `<MODEL>`, read back. Then `COMPLETE`.
8. Purge this case's local working media on every machine that held a copy.

CapCut Web is the editor named by CapCut template resource IDs. A host editor adapter may run the same stages only when it can create a new project, inspect real frames, place captions/TTS, and export, and only for this case. Do not mix two editors in one case. Do not claim a CapCut resource read-back from a different editor.
