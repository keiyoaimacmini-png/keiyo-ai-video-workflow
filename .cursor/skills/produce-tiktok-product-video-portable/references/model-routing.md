# Assistant-model routing

This package does not bind Codex, Claude, or a vendor-specific subagent graph. It does bind two **lanes** for Cursor runs of this skill:

| Lane | Stages | Required assistant | Cursor model ID |
| --- | --- | --- | --- |
| Script | `PREFLIGHT`, `SCRIPT_PREPARED` | Gemini 3.8 Flash | `gemini-3.8-flash` |
| Either | `SCRIPT_REVIEW` only | Gemini 3.8 Flash **or** Grok 4.6 | either ID |
| Post-script | `ROUGH_EDIT` and every later stage | Grok 4.6 | `grok-4.6` |

Grok 4.6 family names such as `cursor-grok-4.6-xhigh` count as Grok 4.6. Gemini 3.7 Flash, Gemini 3.1 Pro, and Grok 4.5 do not. Product model strings such as `AN-S182` are unrelated.

This is **not** a fourth checkpoint. The only routine approval at Checkpoint 1 remains exact `台本OK`.

## Why the parent model cannot silently swap

Cursor Cloud Agents lock the parent model for that agent. Follow-up runs can change mode, not the parent model. Provider-specific subagent routing is an excluded host dependency. Browser / computer-use helpers may also pick their own model.

Therefore the **required** production path is a **session handoff**:

1. Start the case on Gemini 3.8 Flash.
2. At Checkpoint 1, show the model-handoff card with the copy-paste continuation prompt.
3. Switch the Desktop picker to Grok 4.6, or start a new Cloud Agent on Grok 4.6, before any CapCut work.
4. Never begin `ROUGH_EDIT` on Gemini 3.8 Flash.

## Observe the current model

Before `PREFLIGHT` and before entering `ROUGH_EDIT`, classify the live assistant:

```bash
python3 "${SKILL_ROOT}/scripts/resolve_ai_model_lane.py" --model "<observed-model-name>" --stage <STAGE>
```

When about to leave Checkpoint 1 for rough editing:

```bash
python3 "${SKILL_ROOT}/scripts/resolve_ai_model_lane.py" --model "<observed-model-name>" --stage SCRIPT_REVIEW --entering-rough-edit
```

Print the Checkpoint 1 card from actual case values (relative task root only):

```bash
python3 "${SKILL_ROOT}/scripts/resolve_ai_model_lane.py" --print-handoff-card --case-id <case-id> --product-model <model> --task-root outputs/<case-id>
```

Add `--script-approved` only after exact `台本OK` is already recorded.

If the host does not expose a model name, stop with `HOLD_AI_MODEL_IDENTITY_UNVERIFIED`. Ask for one of the two display names. That identity question is not a production approval.

## Script lane

A new case at `PREFLIGHT` or `SCRIPT_PREPARED` that is not Gemini 3.8 Flash is `HOLD_AI_MODEL_SCRIPT_LANE_REQUIRED`. Do not generate the twenty concepts or the script package on Grok 4.6. Tell the user to start a new Gemini 3.8 Flash session with `/produce-tiktok-product-video-portable` and this case's product inputs.

## Checkpoint 1 card

`SCRIPT_REVIEW` must show the selected script **and** the handoff card. Ask only for exact `台本OK`.

- Desktop: change the model picker to Grok 4.6, then send `台本OK` in that Grok turn, **or** send `台本OK` on Gemini and immediately continue in Grok with the printed prompt.
- Cloud Agent: send `台本OK` here if the script is accepted, then start a **new** Grok 4.6 Cloud Agent with the printed prompt. Do not expect this Gemini agent to become Grok.

## After `台本OK`

If the current session is already Grok 4.6, advance to `ROUGH_EDIT`.

If the current session is Gemini 3.8 Flash:

1. Record exact `台本OK` when it was received in this session.
2. Do not open CapCut and do not create the editor project.
3. Stop with `HOLD_AI_MODEL_HANDOFF_REQUIRED` and reprint the continuation prompt with `--script-approved`.
4. Optional convenience only: if this host actually lists a Grok 4.6 model for a general-purpose worker **and** the user asked for automatic internal switching, you MAY start **one** such worker with that same continuation prompt. The Gemini parent must still not edit. Browser helpers may still not be Grok 4.6, so CapCut-bound work should prefer a Grok 4.6 parent session. Never start a second production worker. Never treat a worker launch as proof that remaining stages ran on Grok 4.6.

Grok 4.6 continuation must reuse the existing case, task root, and workflow state. It must not create a new case. If `台本OK` is already bound, it must not ask for `台本OK` again.

## Post-script lane

Any `ROUGH_EDIT` or later work on a non-Grok-4.6 session is `HOLD_AI_MODEL_HANDOFF_REQUIRED`. Do not keep editing "just this once" on Gemini.
