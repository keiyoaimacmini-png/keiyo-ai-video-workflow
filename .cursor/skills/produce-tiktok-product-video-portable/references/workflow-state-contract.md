# Workflow state contract v1

The state file is task-owned operational control, not the portable production payload. Keep only safe identifiers and SHA-256 bindings.

## Normal forward stages

`PREFLIGHT -> SCRIPT_PREPARED -> SCRIPT_REVIEW -> ROUGH_EDIT -> ROUGH_REVIEW -> FINISHING -> FINAL_QA -> FINAL_REVIEW -> EXPORT_AND_DELIVERY -> COMPLETE`

The three review transitions require exact approval receipts:

- `SCRIPT_REVIEW -> ROUGH_EDIT`: `台本OK`
- `ROUGH_REVIEW -> FINISHING`: `粗編集OK`
- `FINAL_REVIEW -> EXPORT_AND_DELIVERY`: `完成・書き出しOK`

No other transition accepts or creates a routine approval.

## Controlled reopen after a user correction

Normal work never moves backward. A user correction that changes an already approved frozen input is the only reopen trigger. Before resetting the current state, preserve its exact bytes as a new versioned task-owned state file and hash a small reopen receipt containing the old state SHA-256, affected checkpoint, and observation time. Do not overwrite or delete the prior state or artifacts.

Reset the canonical current state to the earliest affected review stage, mark that checkpoint and every downstream approval pending, clear downstream current work bindings, and keep unrelated upstream approval bindings unchanged. Rebuild only the affected artifacts and request the same exact checkpoint text again. This is a revision of an existing checkpoint, not a new routine checkpoint type. Do not reopen merely to fix a task-owned placement defect already authorized by the current plan.

## Required fields

- `schema`: exact `product_video_workflow_state.v1`;
- `case_id`: new case identifier, never reused;
- `product_model`: exact verified model;
- `stage`: one forward stage;
- `delivery_mode`: `drive` by default in this Cursor workflow. Use `export_only` only when the original request explicitly required local-only export;
- `settings`: safe relative path plus lowercase SHA-256, or null only at `PREFLIGHT`;
- `artifacts`: fixed keys whose values are safe relative path plus lowercase SHA-256, or null;
- `learning_snapshots`: fixed `script`, `edit`, and `delivery` task-owned snapshot records;
- `approvals`: fixed script, rough-edit, and final-export records;
- `stage_receipts`: ordered current bindings for completed work stages.

Each non-null settings/artifact record has exactly `path` and `sha256`. Paths are POSIX relative paths contained under the supplied task artifact root; absolute paths, `..`, backslashes, symlinks escaping the root, missing files, and byte-hash mismatches are invalid. Artifact keys are `script_package`, `production_payload`, `execution_plan`, `rough_edit`, `finished_timeline`, `final_qa`, `export`, and `drive`. `drive` remains null for `export_only`.

The same actual-file rule applies to `learning_snapshots`. `script` is required after `PREFLIGHT`, `edit` after `ROUGH_EDIT`, and `delivery` at `FINAL_REVIEW`. The snapshot builder admits only active common, exact-stage, and optional exact-model rules; it excludes candidate, case, and superseded notes.

Each stage receipt contains only `sequence`, `completed_stage`, `artifact_sha256`, `learning_snapshot_sha256`, and offset-aware `observed_at`. Never store browser/account/session identifiers in it.

`stage_receipts` represent the current validated work, not an immutable history ledger. While the next checkpoint is still pending, a user-requested correction may replace only the affected downstream artifact and its current stage binding. Once an approval is recorded, its bound artifact and learning snapshot are immutable; changing either requires explicitly reopening that approval scope. Never alter an already approved upstream artifact as an incidental repair.

Bind work-stage receipts exactly: `PREFLIGHT` to `script_package`, `SCRIPT_PREPARED` to `production_payload`, `ROUGH_EDIT` to `rough_edit`, `FINISHING` to `finished_timeline`, `FINAL_QA` to `final_qa`, and `EXPORT_AND_DELIVERY` to `export`. Bind approvals exactly: `台本OK` to `production_payload`, `粗編集OK` to `execution_plan`, and `完成・書き出しOK` to `final_qa`.

Bind learning snapshots exactly: `PREFLIGHT` and `SCRIPT_PREPARED` to `script`; `ROUGH_EDIT`, `FINISHING`, and `FINAL_QA` to `edit`; `EXPORT_AND_DELIVERY` to `delivery`.

Every approval record also binds one active-learning context: `台本OK` to `script`, `粗編集OK` to `edit`, and `完成・書き出しOK` to `delivery`. Pending approvals carry null artifact and learning bindings.

Run the validator with `--artifact-root <task-root>` before reading a child skill, before a mutation, and after recording the result. A valid state proves artifact existence, hashes, and internal sequencing only; it does not prove external work happened.

After `COMPLETE` and verified destination storage, purge this case's local working media with `scripts/purge_local_working_media.py`. Keep the state file and bound receipt JSON. Do not treat those JSON bindings as permission to keep leftover `footage/`, `voice/`, `out/`, runtime input copies, or `Downloads/<completed_video_filename>` working copies.

Initialize a new state without hand-authoring its schema. The output parent must already exist and an existing file is never overwritten:

```bash
python3 ${SKILL_ROOT}/scripts/validate_workflow_state.py --init-state <task-root>/product-video-workflow-state.v1.json --case-id <case-id> --product-model <model> --delivery-mode <export_only|drive>
```
