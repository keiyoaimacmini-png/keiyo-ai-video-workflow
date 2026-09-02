---
name: prepare-tiktok-product-video-script
description: Prepare the evidence-backed script package for one new TikTok product video by inspecting materials, comparing twenty concepts, and selecting a natural six-stage script. Use only when explicitly invoked or routed from produce-tiktok-product-video-portable at PREFLIGHT, or for an unapproved SCRIPT_REVIEW revision.
---

# Prepare TikTok Product Video Script

Input stage must be `PREFLIGHT`, or `SCRIPT_REVIEW` with `台本OK` still pending for a user-requested revision. Read the parent's `references/core-invariants.md` and `references/workflow-state-contract.md`, then validate the state.

Build the active script-rule snapshot before concept work, then read it completely:

```bash
python3 "${SKILL_ROOT}/scripts/build_rule_snapshot.py" --rules-root <rules-root> --stage script --product-model <model> --output <task-root>/learning-script.json
```

Register its safe relative path and actual SHA-256 as `learning_snapshots.script`, and bind the same SHA into the `PREFLIGHT` stage receipt and script package. Do not read candidate or case archives as global rules.

On an unapproved review revision, record the correction first. Build a new versioned file such as `learning-script-r01.json` only when the active rule set changed; otherwise keep the existing registered snapshot. Never overwrite or silently rebind a different prior snapshot.

## Prepare once

1. Read project instructions and local project context.
2. Build a closed material manifest. Separate verified facts, review observations, hypotheses, and not obtained; close model provenance over every available company-authoritative material and HOLD on a conflict or invalid model.
3. Resolve exactly one model-matched product settings file for **this** `product_model` (`config/product_video_settings_<model>.v1.json`) and hash its actual bytes. If it is missing, HOLD. Do not copy another model's settings.
4. Inventory candidate media from the resolved material root without copying or changing originals. Record safe relative path, asset ID, media SHA-256, duration, exact observed subject/action, usable source ranges, and evidence location. Do not inventory another model's folder as a substitute.
5. Inspect the real frames needed to support each proposed line. Labels and sidecars are leads, not proof of an exact reaction, direction, stage, or completion state.
6. Retrieve any project-required generation context. Keep selected reusable patterns and their `not_to_copy` boundaries distinct. Internally compare twenty executable concepts; do not ask the user to choose among them.
7. Select the strongest concept that supports the full six-stage progression and one distinct source/media SHA per visible caption.
8. Read the visible dialogue straight through without stage labels. Repair unexplained jumps, unclear pronouns, and weak causal connections before selection.

## Output

Create one `product_video_script_package.v1` containing the closed material manifest and model provenance, selected concept, twenty-candidate comparison summary, project generation-context provenance and `not_to_copy`, verified facts/evidence, complete ordered dialogue, exact punctuation and line breaks, cut IDs, source asset/path and SHA, source in/out, cut duration, Unicode count, estimated read time, settings SHA, active-rule snapshot SHA, and canonical final-cut binding.

Hash the package and store it as `artifacts.script_package`. On the normal path, record the `PREFLIGHT` binding and advance to `SCRIPT_PREPARED`. During an unapproved `SCRIPT_REVIEW` revision, replace only the current `PREFLIGHT` draft binding, remain at `SCRIPT_REVIEW`, and route the revised package through script validation again. Do not request approval from this skill and do not open or mutate CapCut.
