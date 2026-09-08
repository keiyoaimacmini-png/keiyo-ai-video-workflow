---
name: validate-tiktok-product-video-script
description: Convert and validate a prepared product-video script package into the canonical portable payload, then present Checkpoint 1. Use only when explicitly invoked or routed from produce-tiktok-product-video-portable at SCRIPT_PREPARED, or for an unapproved SCRIPT_REVIEW revision.
---

# Validate TikTok Product Video Script

Input stage must be `SCRIPT_PREPARED`, or `SCRIPT_REVIEW` with `台本OK` still pending for a user-requested revision. Read:

1. the parent core invariants and workflow-state contract;
2. `${SKILL_ROOT}/references/payload-contract.md` completely.

Do not read the full planning skill unless the user explicitly requests planning-only behavior.

## Build and validate

- Verify the script-package SHA against the actual file.
- Verify the script package's registered rule-snapshot file and actual bytes against its active-rule snapshot SHA. Do not rebuild it during this stage.
- Build one canonical production payload from that package and the actual model settings file. For an unapproved script-review wording correction, do not rewrite hashes by hand. If the operator supplied exact lines, use `scripts/apply_spoken_lines.py` against the current package and payload. Otherwise re-send the standing renderer prompt through `scripts/send_gemini_cli_prompt.py`; do not append rules files or lessons, and do not Cursor-rewrite the six lines.
- Do not hash or watch the material root in this stage. Unmatched cuts use `additional_asset_required: true` with no source asset/in/out. `media_requirements` come from `picture_must` / `picture_ideal` as the planned brief, not from inspected files. The canonical final visual may stay `HOLD_FINAL_VISUAL_NOT_VERIFIED` until rough edit proves the configured file.
- Ensure the six stages, natural adjacent-line continuity, verified facts, exact CTA/settings values, timing estimates, and exact pending approval plans all close. Do not require distinct source IDs or media hashes at Checkpoint 1.
- Run:

```bash
python3 ${SKILL_ROOT}/scripts/validate_product_video_payload.py payload.json --settings-root <project-root>
```

Resolve every deterministic error without inventing evidence or authority.

## Craft gate

Before presenting Checkpoint 1, write `<task-root>/craft-script.v1.json` from the spoken lines. Then run:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/produce-tiktok-product-video-v3/scripts/validate_craft_quality.py" \
  --project-root <project-root> --product-model <model> --surface script --artifact <task-root>/craft-script.v1.json
```

`HOLD_CRAFT_QUALITY` blocks `台本OK`. Re-send the standing renderer prompt through `scripts/send_gemini_cli_prompt.py` and rerun. Do not append rule files or lessons. Do not Cursor-rewrite the six lines as the first path. Use `apply_spoken_lines.py` only when the operator supplied exact wording. Do not present Checkpoint 1 because the payload schema passed.

## Checkpoint 1

Hash the validated payload and store `artifacts.production_payload`. On the normal path, record the `SCRIPT_PREPARED` binding and advance to `SCRIPT_REVIEW`. During an unapproved `SCRIPT_REVIEW` revision, replace only that current draft binding and remain at `SCRIPT_REVIEW`.

Show the selected concept, the complete spoken script, punctuation, line breaks, six-stage order, the hook problem, and the spoken solution in `problem_resolution`. Those two must match: the resolution presents a solution to the same problem the hook named. A result line about looks or a partial visible change is not that solution. If they do not match, `HOLD_SCRIPT_INCOMPLETE` and do not ask `台本OK`. Keep `picture_must` / `picture_ideal` visible as the later matching brief. Stop only for exact `台本OK`. Do not make that stop wait on source asset/path, in/out, cut duration, or in/mid/out contact sheets; those are matched and proven after this approval, then confirmed at Checkpoint 2. That approval authorizes rough visual editing in a separate new editor-of-record project; it does not lock picture, and it does not authorize TTS, credits, finishing, export, or Drive.
