---
name: produce-tiktok-product-video-portable
description: Provider-neutral workflow for producing one new TikTok product video through script, CapCut Web editing, final verification, export, and optional exact-scope Drive delivery with exactly three routine checkpoints.
---

# Produce TikTok Product Video — Portable

Use this file as the entrypoint. Resolve `SKILL_ROOT` to the directory containing this file. Resolve `PROJECT_ROOT` to the product project's trusted root. Never infer either path.

This package is assistant-provider neutral. The host must supply the capabilities in [references/host-adapter-contract.md](references/host-adapter-contract.md). A missing capability does not relax a rule: stop with the most specific HOLD state.

## Always load

Read completely:

1. [references/core-invariants.md](references/core-invariants.md)
2. [references/workflow-state-contract.md](references/workflow-state-contract.md)
3. [references/host-adapter-contract.md](references/host-adapter-contract.md)

For every production, create a new case ID, a new task root under `<project-root>/outputs/<case-id>/`, a new workflow state, and a separate new CapCut Web project. Never reuse or overwrite an existing case, video, editor project, export, Drive object, payload, or receipt.

Initialize state with the included validator:

```bash
python3 "${SKILL_ROOT}/scripts/validate_workflow_state.py" --init-state <task-root>/product-video-workflow-state.v1.json --case-id <case-id> --product-model <model> --delivery-mode <export_only|drive>
```

Validate state against actual artifact bytes before reading a stage file, before every mutation, and after recording every result:

```bash
python3 "${SKILL_ROOT}/scripts/validate_workflow_state.py" <task-root>/product-video-workflow-state.v1.json --artifact-root <task-root>
```

## Route exactly one stage

Read only the stage file matching the current state:

| Current state | Stage file | Successful next state |
| --- | --- | --- |
| `PREFLIGHT` | [stages/01-prepare-script.md](stages/01-prepare-script.md) | `SCRIPT_PREPARED` |
| `SCRIPT_PREPARED` | [stages/02-validate-script.md](stages/02-validate-script.md) | `SCRIPT_REVIEW` |
| `ROUGH_EDIT` | [stages/03-build-rough-cut.md](stages/03-build-rough-cut.md) | `ROUGH_REVIEW` |
| `FINISHING` | [stages/04-finish.md](stages/04-finish.md) | `FINAL_QA` |
| `FINAL_QA` | [stages/05-verify-timeline.md](stages/05-verify-timeline.md) | `FINAL_REVIEW` |
| `EXPORT_AND_DELIVERY` | [stages/06-deliver.md](stages/06-deliver.md) | `COMPLETE` |

Review states are approval boundaries, not production stages:

- `SCRIPT_REVIEW`: accept only exact `台本OK`, append its receipt, then advance to `ROUGH_EDIT`.
- `ROUGH_REVIEW`: accept only exact `粗編集OK`, append its receipt, then advance to `FINISHING`.
- `FINAL_REVIEW`: accept only exact `完成・書き出しOK`, append its receipt, then advance to `EXPORT_AND_DELIVERY`.

Never infer approval, rename approval text, add a routine checkpoint, or skip a state.

## Corrections and repairs

A correction before approval stays at the same review state and rebuilds only affected downstream draft artifacts. A correction to an already approved frozen input uses the controlled-reopen procedure in the workflow-state contract and returns to the earliest affected existing checkpoint. Never invent a fourth checkpoint or retain a stale approval binding.

A settings-bounded common TTS-speed adjustment and the derived three-layer timing closure are authorized finish-time values under `粗編集OK`. They do not reopen approval unless the speed leaves the configured range or a frozen input changes.

Read [references/self-repair.md](references/self-repair.md) only after a real incident. Preserve unaffected verified cuts. Unknown export or upload outcomes are observation-only; never retry them automatically.

When work cannot safely continue, select the most specific package-local code from [references/hold-registry.md](references/hold-registry.md). HOLD preserves current work and grants no new action.

## Completion

`FINAL_QA` may pass only when the final-QA artifact hash-binds valid non-final-slack, frame-level track-pairing, and timeline-integrity receipts. Static validators prove file and receipt closure only; they do not prove live editing, playback, export, delivery, or browser-tab state.

`COMPLETE` requires a verified new export receipt. When exact Drive delivery was fixed in the original request, it also requires one verified new Drive object, exact parent-scope read-back, and closure of only task-owned browser tabs.

After `COMPLETE` and verified destination storage, purge this case's local working media on every machine that held a copy. Dry-run first, then execute. This standing instruction is not a fourth checkpoint.

```bash
python3 "${SKILL_ROOT}/scripts/purge_local_working_media.py" --project-root <project-root> --task-root <task-root> --case-id <case-id>
python3 "${SKILL_ROOT}/scripts/purge_local_working_media.py" --project-root <project-root> --task-root <task-root> --case-id <case-id> --execute --i-confirm-destination-stored
```

Do not delete originals, Drive stored objects, git-tracked files, JSON receipts, settings, or another case. If `delivery_mode` is `export_only`, require `destination-stored-receipt.v1.json` proving a durable copy that is not a local working copy. If this host is not the operator Mac, stop after the VM purge with `HOLD_MAC_LOCAL_WORKING_MEDIA_PURGE_REQUIRED` and run the same relative command on the Mac.
