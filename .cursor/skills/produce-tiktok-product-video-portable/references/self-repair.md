# Bounded self-repair

Use this playbook only after a real incident. A recoverable incident pauses the unsafe mutation, not the whole user workflow.

## Recovery loop

1. Freeze the affected `cut_id` and stop further mutations on that cut.
2. Read back current project, panel/category, timeline, TTS placement, credit state, and cloud-sync state without generating again.
3. Classify the incident using the table below.
4. Validate the actual payload and approved execution plan, then inspect the append-only event ledger for that cut's remaining reserve.
5. Append a generation-request event immediately after the credit-consuming request; an uncertain outcome still consumes the allowance.
6. Apply the smallest repair once.
7. Append the verified/failed outcome, read back, and replay the affected boundary.
8. Mark the cut verified and resume the interrupted state. Preserve unaffected verified cuts.

If the same repair fails or would exceed its cap, HOLD. Do not improvise a third attempt.

## Incident table

| Incident | Read-only diagnosis | Authorized repair | Verification |
|---|---|---|---|
| `ホリデーツイスト` not visible | Confirm official voice panel and current category | Select `TikTok`; if state is stale, close/reopen the panel. Reload only the task-owned editor tab after cloud-sync read-back, then reopen the same project | Preset name is read back before generation |
| Generation signal but clip missing | Inspect expected cut, narration track, credit change, and pending UI state | Wait/poll the existing action first. If definitively absent, use that cut's single same-text/same-preset repair generation | Exactly one correct clip exists for the cut |
| Silent, truncated, duplicated, or wrong clip | Play the affected cut and inspect exact task ownership | Keep the defective clip until a same-input replacement is generated and verified. Then disable or remove only that defective task-owned clip. If CapCut requires destructive removal before a verified replacement and no reversible restore is proven, HOLD | Clean beginning/end, audible text match, one correct clip, ledger closure |
| Overlap, gap, or non-final silent slack | Read the actual audible speech end, TTS clip end, video/caption end, and adjacent cut boundaries | Resynchronize timing deterministically; trim task-owned TTS trailing silence when present and adjust derived video speed/placement and video/caption boundaries without regenerating valid audio | For each non-final cut, video end = caption end = next cut start and audible-end slack is 0–1 frame, with no spill |
| TTS exceeds the provisional rough cut | First rule out a placement/range read-back error | Apply the settings-bounded common TTS speed first, then retime derived video playback and boundaries while preserving the frozen source asset/range and visible action. HOLD only if those frozen inputs must change | Every repaired non-final clip closes at its actual audible end within 0–1 frame; the canonical final tail remains full length |
| UI panel/editor stale | Confirm cloud-save/read-back and task-owned tab identity | Reopen the panel first; reload or reopen only the same task-owned project when saved state is verified | Exact intended project and timeline return |
| Export/upload appears stalled | Poll current operation and read back filesystem/Drive | No resubmission. Continue observation only | One unambiguous file/Drive record or HOLD unknown outcome |

## Always HOLD

- Login challenge, ambiguous account, CAPTCHA, 2FA, recovery, or new consent.
- Purchase prompt or exhausted disclosed credit/repair ceiling.
- Frozen text, claim, line break, source asset/range, visible action, speaker, preset, pitch, processing, destination, or user-visible outcome must change. A settings-bounded common TTS speed or derived live-timeline video timing adjustment is not a new-authority condition.
- Task ownership, project identity, export outcome, upload outcome, or collision state is uncertain.
- The only apparent fix touches an existing project, user asset, Drive original, unrelated tab, or another file.

Use the most specific code from [hold-registry.md](hold-registry.md). If none fits, use `HOLD_NEW_AUTHORITY_REQUIRED` and state the exact missing authority.
