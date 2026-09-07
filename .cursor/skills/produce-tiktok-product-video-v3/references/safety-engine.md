# Safety engine (delegate)

`SAFETY_SKILL_ROOT` is `$PROJECT_ROOT/.cursor/skills/produce-tiktok-product-video-portable`.

Call those scripts. Read only the portable stage file that matches the current workflow state. Do not paste TTS, Drive, or payload-contract text into v3 files.

| Job | Script under `SAFETY_SKILL_ROOT/scripts/` |
| --- | --- |
| Product / materials | `resolve_product_inputs.py` |
| Workflow state | `validate_workflow_state.py` |
| Payload schema | `validate_product_video_payload.py` |
| Execution plan | `validate_execution_plan.py` |
| Portable Gemini brief check | `render_gemini_web_prompt.py` (v3 wraps this; do not paste from it alone) |
| Rule snapshot (portable) | `build_rule_snapshot.py` |
| Bulk TTS gaps | `prepare_bulk_tts_scene_gaps.py` |
| Three-layer slack | `validate_nonfinal_slack.py` |
| Track pairing | `validate_track_pairing.py` |
| Timeline integrity | `validate_timeline_integrity.py` |
| Drive upload | `upload_drive_local_file.py` |
| Local purge | `purge_local_working_media.py` |

Portable stages remain:

| State | File |
| --- | --- |
| `PREFLIGHT` | `stages/01-prepare-script.md` |
| `SCRIPT_PREPARED` | `stages/02-validate-script.md` |
| `ROUGH_EDIT` | `stages/03-build-rough-cut.md` |
| `FINISHING` | `stages/04-finish.md` |
| `FINAL_QA` | `stages/05-verify-timeline.md` |
| `EXPORT_AND_DELIVERY` | `stages/06-deliver.md` |

Portable review phrases stay exact: `台本OK`, `粗編集OK`, `完成・書き出しOK`.

A portable HOLD still wins over a craft pass. A craft fail still blocks the checkpoint even if the payload schema passes.
