---
name: product-video
description: Thin orchestrator for one new TikTok product video on this Mac. Use when the user invokes /product-video or asks to produce, resume, or deliver a product video. Dispatches one stage Skill at a time and chains automatically.
---

# /product-video

Orchestrator only. Do not generate TTS, select clips, export, or upload Drive here.

## Paths

- `PROJECT_ROOT`: this Git repository root
- `SKILL_ROOT`: this directory
- Public entrypoint is `/product-video`.
- Stage Skills use dated folders; dispatch `skill` stays the undated logical id. The stage folder and frontmatter name use `<logical>-YYYYMMDD`.

## Skill dates

Stage Skill folders and frontmatter names are `<logical>-YYYYMMDD`. Change both on a production-behavior change. Do not keep the previous dated folder.
Do not date this `/product-video` entrypoint. Typo/comment-only edits do not change the date.

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
3. If `action` is `run_skill`, read **only** `.cursor/skills/<skill_dir>/SKILL.md` and execute that stage. `skill` is the stable logical id. `skill_dir` is the current dated folder.
4. After that stage succeeds, run dispatch again in the same turn.
5. Do not ask 「続けますか」「Continue?」「Proceed?」 between automatic stages.
6. Stop only when `action` is `stop`.

Stop reasons:

- `waiting_script_selection` — wait for exact `案Nで台本OK`
- `waiting_for_operator` — wait for exact `完成・格納してください`
- `hold` — genuine human or unrecoverable blocker. Script grounding and script-rule failures are not operator stops. Repair those drafts in the same turn and continue until the variants can be presented.
- `operator_paused` — this product video stays held until the operator says to resume
- `complete`

A stage listed in `completed_stages` must not rerun. Resume from `current_stage`.

## 完了の受理条件（司令塔）

工程の完了報告、stage status、receipt だけでは完了を受理しない。次の証拠を司令塔が確認できるまで、工程は未受理として扱う。

- 失敗台帳（`product-video-materials/共通/失敗台帳.md`）の各項目に「対象工程」フィールドを持たせ、値は PREPARE/SCRIPT/NARRATION/ASSEMBLY/ROUGH_EDIT/DELIVERY の1つ以上とする。工程の完了時は、「対象工程」に当該工程を含む項目だけを対象に、「確認する証拠」が揃っていることを司令塔が確認する。対象項目に未確認の項目が一つでもあれば、その工程の完了を受理しない。
- 失敗が起きたら、各工程の本文へ注意書きを増やして分散させず、失敗台帳の当該工程を対象とする項目へ1件登録する。製品ノート由来の失敗は製品ノートの所有者が失敗台帳側を修正する。その項目の再発防止条件を、この司令塔の受理条件へ反映してから受理する。
- 製品ノートのルールは、台本生成・検査へ反映された証拠（Gemini に渡した内容、生成結果、edit-plan、選択範囲の確認など）を司令塔が確認するまで「有効」と扱わない。ノートに書いてあるだけでは受理条件を満たさない。

dispatch.py はこの条件を検査しない。照合は司令塔（LLM）が手で行う。コード化は CHANGES の未実装項目を参照

配置・再生成・進捗通知の Gate A〜D は **02 の正本**だけを参照する。各工程でゲート本文を複製して判断を増やさない。

## 配置ゲートの参照

配置ゲートの正本は `02_共通_配置ゲート.md` と `${PROJECT_ROOT}/.cursor/skills/product-video/references/placement-gates.md` です。01 と工程文書は、必要な Gate X への参照だけを持ち、判定条件は 02 に従います。

## Preflight

Before a **new** case, and when dispatch returns `run_preflight` for a held case, check blocking items in the background. Do not write media, generate TTS, or spend CapCut credits.

**BLOCKING** (any failure HOLDs start): materials, Gemini, Chrome / MCP, CapCut TTS, Holiday Twist, ChatCut.

Drive OAuth and Drive parent-folder readiness may be checked here, but Drive login, upload, read-back, and purge instructions are canonical in `04_工程_delivery.md`. Do not duplicate those instructions in this file or in another stage. A Drive-only start warning does not HOLD the whole case; delivery readiness is checked again at DELIVERY.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/run_preflight.py" --project-root <PROJECT_ROOT> --product-model <MODEL> --live --observation-json <agent observations>
```

Python helper covers materials, Gemini CLI probe + text-only PONG, Chrome process/CDP, and Drive OAuth/folder. The agent must also, with at most 3 retries and no operator chatter:

- resolve the project Playwright MCP (`--cdp-endpoint=chrome`; do not hard-code a namespace)
- attach to the already-running Google Chrome.app
- open CapCut official Text to Speech (no Generate)
- confirm login and that Holiday Twist is selectable
- confirm ChatCut can list/create/inspect/edit

Pass those booleans as `--observation-json`. If several **blocking** checks fail, keep going and report **開始前に直すこと** once. After the operator fixes them, one `/product-video` re-runs the full preflight and continues.

When the helper returns `READY` (including a Drive-only warning):

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/dispatch.py" --project-root <PROJECT_ROOT> --product-model <MODEL> [--case-id <CASE_ID>] --preflight-ready
```

After READY, do not bounce back for routine environment checks. `案Nで台本OK` continues NARRATION → ASSEMBLY → ROUGH_EDIT → WAITING_FOR_OPERATOR in this turn. During NARRATION, stay in the current stage until the queue helper says `queue_complete`; do not re-dispatch between cuts. During ROUGH_EDIT, run `edit-plan.json` `chatcut_steps` in one pass and follow 02 の Gate C. `完成・格納してください` continues only after Drive is READY; then DELIVERY → Drive read-back → COMPLETE → purge in this turn. If Drive is still not READY, do not export; use the single delivery instruction and wait for the same phrase.

## テロップ設計（設計段階）
設計書の正本は Obsidian `product-video-materials/共通/テロップ/`。Phase 1 の間は現行の固定字幕位置と ChatCut の字幕手順が有効。設計書の内容は、有効化(コード対応)まで現行動作を変えない。

## Retries

Transient MCP/CLI/connection failures: retry up to 3 times (namespace re-resolve, reconnect, tool list refresh if the host allows it). Do not loop. Do not retry login, CAPTCHA, 2FA, account choice, purchase, or missing materials. If recovery works, continue silently.
