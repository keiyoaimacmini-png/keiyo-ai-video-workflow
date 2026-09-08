---
name: prepare-tiktok-product-video-script
description: Prepare the evidence-backed script package for one new TikTok product video from verified product facts and a Gemini dialogue draft. Do not inventory, hash, or watch source clips before 台本OK. Use only when explicitly invoked or routed from produce-tiktok-product-video-portable at PREFLIGHT, or for an unapproved SCRIPT_REVIEW revision.
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
2. Build a closed **product-information** manifest. Separate verified facts, review observations, hypotheses, and not obtained; close model provenance over every available company-authoritative material and HOLD on a conflict or invalid model. This is product pages and settings, not a video inventory. Do not hash or watch the material root. Do not probe, SHA, or play source clips. Do not record observed actions, usable ranges, or six winning files.
3. Resolve exactly one model-matched product settings file for **this** `product_model` (`config/product_video_settings_<model>.v1.json`) and hash its actual bytes. If it is missing, HOLD. Do not copy another model's settings. `--require-materials` only confirms that this model's material folder exists; it does not authorize hashing or watching every clip.
4. Retrieve any project-required generation context. Keep selected reusable patterns and their `not_to_copy` boundaries distinct. After verified facts exist, draft the selected **spoken** dialogue and per-line picture brief (`picture_must` / `picture_ideal`) with Antigravity CLI (`agy --print`) on this Mac, with Gemini 3.8 Flash. Gemini compares concepts internally and returns one draft; do not ask it for a twenty-candidate list. The picture brief is a planned requirement for footage that will be matched after `台本OK`, not a file pick and not a description of current inventory. Do not switch the Cursor parent model for script work. Do not call the Gemini API. Do not set `GEMINI_API_KEY`. Do not enable AI Credit overages. Do not use Gemini.app, Google Chrome.app, or the agent-controlled Cursor browser for this draft. Write a key-free brief with `product_model`, `cta_text`, and `verified_facts` only. Do not include `usable_shots`, observed actions, file names, hashes, or in/out. Render the Gemini prompt. Send that renderer output only. Do not append this stage file, `config/product-video-rules`, lessons, or product examples:

```bash
python3 "${SKILL_ROOT}/scripts/render_gemini_web_prompt.py" --brief <task-root>/gemini-web-brief.v1.json
python3 "${SKILL_ROOT}/scripts/send_gemini_cli_prompt.py" --prompt-file <task-root>/gemini-web-prompt.txt
```

Send only through `send_gemini_cli_prompt.py`. Do not screenshot, OCR, or Accessibility-hunt. Do not open Gemini.app, Google Chrome.app, or the agent-controlled browser for this draft. Do not call the Gemini API. Do not leave a paste for the operator. If the helper HOLDs, stop with that HOLD; do not rediscover a UI tree. `HOLD_GEMINI_CLI_NOT_VERIFIED` does not authorize an operator paste. If login, CAPTCHA, 2FA, account choice, recovery, or new consent is required, `HOLD_GEMINI_LOGIN_USER_ACTION_REQUIRED`. If the CLI model is not Gemini 3.8 Flash, `HOLD_GEMINI_MODEL_NOT_VERIFIED`. Do not ask the user to choose among concepts.
5. Select the strongest concept that supports the full six-stage progression and presents a solution to the hook problem at `problem_resolution` rather than restating `result`. Do not require a locked source file per caption at this stage.
6. Read the visible dialogue straight through without stage labels. If jumps, pronouns, glue, endings, or TikTok spoken taste fail, re-send through `send_gemini_cli_prompt.py` with the standing renderer prompt. Do not rewrite the six lines in Cursor as the first path. Checkpoint 1 presents that spoken script plus the hook problem and the spoken solution, not a locked cut table. Keep `picture_must` / `picture_ideal` with the package as the matching brief; do not bind SHA or in/out from them. Do not run `prove_source_range.py` in this stage.

## Output

Create one `product_video_script_package.v1` containing the closed product-information manifest and model provenance, selected concept, project generation-context provenance and `not_to_copy`, verified facts/evidence, complete ordered dialogue with `picture_must` / `picture_ideal`, exact punctuation and line breaks, cut IDs, Unicode count, estimated read time, settings SHA, and active-rule snapshot SHA. Persist a key-free Gemini CLI draft receipt when that path ran (selected dialogue, concept, and read-back that the model was Gemini 3.8 Flash). Do not store cookies, tokens, account identifiers, or session URLs. Do not require a twenty-candidate list from Gemini. Do not include source asset/path, media SHA, source in/out, or in/mid/out contact sheets.

Hash the package and store it as `artifacts.script_package`. On the normal path, record the `PREFLIGHT` binding and advance to `SCRIPT_PREPARED`. During an unapproved `SCRIPT_REVIEW` revision, replace only the current `PREFLIGHT` draft binding, remain at `SCRIPT_REVIEW`, and route the revised package through script validation again. Do not request approval from this skill and do not open or mutate CapCut.
