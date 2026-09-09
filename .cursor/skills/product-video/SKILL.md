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

## Every turn

```bash
python3 "${SKILL_ROOT}/scripts/dispatch.py" --project-root <PROJECT_ROOT> [--case-id <CASE_ID>] [--product-model <MODEL>] [--utterance "<latest user message>"]
```

1. Read only the JSON.
2. If `action` is `run_skill`, read **only** `.cursor/skills/<skill>/SKILL.md` and execute that stage.
3. After that stage succeeds, run dispatch again in the same turn.
4. Do not ask 「続けますか」「Continue?」「Proceed?」 between automatic stages.
5. Stop only when `action` is `stop`.

Stop reasons:

- `waiting_script_selection` — wait for exact `案Nで台本OK`
- `waiting_for_operator` — wait for exact `完成・格納してください`
- `hold` — genuine technical blocker
- `complete`

A stage listed in `completed_stages` must not rerun. Resume from `current_stage`.
