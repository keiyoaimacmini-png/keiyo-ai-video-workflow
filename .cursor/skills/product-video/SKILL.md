---
name: product-video
description: Thin orchestrator for one new TikTok product video on this Mac. Use when the user invokes /product-video or asks to produce, resume, or deliver a product video. Dispatches one stage Skill at a time and chains automatically.
---

# /product-video

Orchestrator only. Do not generate TTS, select clips, export, or upload Drive here.

## Paths

- `PROJECT_ROOT`: this Git repository root
- `SKILL_ROOT`: this directory
- Do not load `produce-tiktok-product-video-portable` or `produce-tiktok-product-video-v3` Skills

## 3-touch

Usual operator input is only:

1. `/product-video` to start
2. exact `案Nで台本OK`
3. exact `完成・格納してください`

Do not ask the operator about anything that can be retried or auto-recovered. Human HOLDs are only login, CAPTCHA, 2FA, account choice, new terms/consent, Pro contract, extra purchase, new payment, missing source materials, or a missing product facts profile for a new model. Do not ask for product facts on each video when `config/product_video_product_facts_<MODEL>.v1.json` already exists.

## Every turn

```bash
python3 "${SKILL_ROOT}/scripts/dispatch.py" --project-root <PROJECT_ROOT> [--case-id <CASE_ID>] [--product-model <MODEL>] [--utterance "<latest user message>"] [--preflight-ready]
```

1. Read only the JSON.
2. If `action` is `run_preflight`, run the start-time preflight in this same turn. Do not create a new case. Do not regenerate an approved script. Preserve `case_id` and completed stages.
3. If `action` is `run_skill`, read **only** `.cursor/skills/<skill>/SKILL.md` and execute that stage.
4. After that stage succeeds, run dispatch again in the same turn.
5. Do not ask 「続けますか」「Continue?」「Proceed?」 between automatic stages.
6. Stop only when `action` is `stop`.

Stop reasons:

- `waiting_script_selection` — wait for exact `案Nで台本OK`
- `waiting_for_operator` — wait for exact `完成・格納してください`
- `hold` — genuine human or unrecoverable blocker
- `complete`

A stage listed in `completed_stages` must not rerun. Resume from `current_stage`.

## Preflight

Before a **new** case, and when dispatch returns `run_preflight` for a held case, check A–E in the background. Do not write media, generate TTS, or spend CapCut credits.

```bash
python3 "${SKILL_ROOT}/scripts/run_preflight.py" --project-root <PROJECT_ROOT> --product-model <MODEL> --live --observation-json <agent observations>
```

Python helper covers materials, Gemini CLI probe + text-only PONG, Chrome process/CDP, and Drive OAuth/folder. The agent must also, with at most 3 retries and no operator chatter:

- resolve the project Playwright MCP (`--cdp-endpoint=chrome`; do not hard-code a namespace)
- attach to the already-running Google Chrome.app
- open CapCut official Text to Speech (no Generate)
- confirm login and that Holiday Twist is selectable
- confirm ChatCut can list/create/inspect/edit

Pass those booleans as `--observation-json`. If several independent checks fail, keep going and report **開始前に直すこと** once. After the operator fixes them, one `/product-video` re-runs the full preflight and continues.

When the helper returns `READY`:

```bash
python3 "${SKILL_ROOT}/scripts/dispatch.py" --project-root <PROJECT_ROOT> --product-model <MODEL> [--case-id <CASE_ID>] --preflight-ready
```

After READY, do not bounce back for routine environment checks. `案Nで台本OK` continues NARRATION → ASSEMBLY → ROUGH_EDIT → WAITING_FOR_OPERATOR in this turn. `完成・格納してください` continues DELIVERY → Drive read-back → COMPLETE → purge in this turn.

Helper path:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/run_preflight.py" --project-root <PROJECT_ROOT> --product-model <MODEL>
```

## Retries

Transient MCP/CLI/connection failures: retry up to 3 times (namespace re-resolve, reconnect, tool list refresh if the host allows it). Do not loop. Do not retry login, CAPTCHA, 2FA, account choice, purchase, or missing materials. If recovery works, continue silently.
