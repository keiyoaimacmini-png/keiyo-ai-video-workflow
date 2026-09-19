---
name: product-video-narration-20260919
description: Generate Holiday Twist source audio from the frozen approved script. Use only when /product-video dispatches NARRATION.
disable-model-invocation: true
---

# NARRATION

Read this file only when dispatch says `product-video-narration`.
When this Skill's flow, rules, or execution change, rename the folder and frontmatter `name` date (`YYYYMMDD`) together. Keep the logical dispatch id. Do not keep the previous dated folder.

Approved-script cuts are a **queue**. Stay in this Skill until every cut is recorded. Do not return to `/product-video` dispatch, do not make a new LLM plan, and do not chat after a successful cut.
Do not chat after a successful cut.

Use only the approved script. CapCut generate is the **source audio**. ChatCut clip `playbackRate` 1.2 is applied later (`${PROJECT_ROOT}/.cursor/skills/product-video/scripts/prove_tts_speed.py` on `inspect_item`). Do not require CapCut generate speed 1.2. Do not FFmpeg-accelerate. Do not record the source as already 1.2x.
SCRIPT LINE == NARRATION == TELOP. Do not trim, strip, ignore newlines or zero-width characters, or treat visible/OCR/document-HTML text as a match.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/narration_queue.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --start
```

## Session setup (once)

If the queue says `setup_session: true`, do this **once**. Keep the same Chrome tab, CapCut Text to Speech page, Holiday Twist voice, and TTS input field for every cut.

1. Resolve the project Playwright MCP (`--cdp-endpoint=chrome`). Do not hard-code a namespace.
2. Attach to the already-running Google Chrome.app.
3. Confirm CapCut official Text to Speech. Do not click Generate during setup.
4. Confirm Holiday Twist is selected.
5. Identify the TTS input field once.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/tts_session.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --prove-setup --observation-json '<observation>'
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/narration_queue.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --mark-setup
```

Follow `${PROJECT_ROOT}/.cursor/skills/product-video/references/capcut-chrome-mcp.md`. Do not fall back to cursor-ide-browser or an extension adapter.

If that same session is later lost, recover it at most 3 times with `tts_session.py --may-reuse`. Do not ask about a transient miss. If it still cannot attach, `HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE`. Login, CAPTCHA, 2FA, or account choice: `HOLD_CAPCUT_LOGIN_USER_ACTION_REQUIRED`.

Between successful cuts do **not** re-resolve MCP, rerun Chrome preflight, re-search the CapCut page, re-select Holiday Twist, re-resolve the voice ID, return to dispatch, or report status.

## CUT ATOMIC FLOW

Ask the queue for the current cut (`--next`). Fix `cut_id` + `frozen_line`. Then, without dispatch / chat / LLM / extra helpers:

1. Completely empty the already-identified field. Write that frozen line only.
2. Immediately read the **same CapCut field** once through Playwright MCP. That live value is `actual`.
3. Compare with one worker. Do not pass `inner_text` / `textarea_readback` copied from `frozen_line`.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/narration_cut.py" --prove-input --project-root <PROJECT_ROOT> --case-id <CASE_ID> --cut-id <cut-id> --frozen-json '<json string>' --actual-json '<live field json>' --attempt <1|2>
```

`frozen_line` is expected only. The only actual is the value just read from the CapCut field. Do not build `{"inner_text": frozen_line}` or `{"textarea_readback": frozen_line}` as proof.

- exact match → Generate in the same breath. No other helper, page search, or voice check in between. `${PROJECT_ROOT}/.cursor/skills/product-video/scripts/tts_attempts.py` generation cap is applied inside `narration_cut.py`.
- mismatch → clear + write + one more live read (`--attempt 2`)
- second mismatch → `HOLD_TTS_INPUT_FIELD_UNVERIFIED`

4. Before Generate, note the current result identity (`result-src` / `currentSrc` / result card id).
5. Generate. Existing-balance `Credits will be consumed` with Cancel / Got it: click Got it. Do not run `classify_capcut_credit.py`. Do not require `approve_got_it` from a helper. HOLD only when a Pro monthly/annual contract, free trial, extra credit purchase, auto-reload, payment form, new payment, or plan change is explicit.
6. Wait until a **new** result appears. If it is the same as the pre-Generate identity, do not capture.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/narration_cut.py" --prove-result --before-id '<pre>' --after-id '<post>'
```

7. Save that new result only. Use the helper's `duration_seconds`. Do not probe duration again.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/capture_capcut_result_audio.py" --url <new-result-src> --output <task-root>/tts/<cut-id>.mp3
```

8. Record the cut with that capture duration. `narration_cut.py --finish-cut` also rejects leftover-length audio (about 11s+ and far above one-line Holiday Twist history). No transcript. No LLM review.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/narration_cut.py" --finish-cut --project-root <PROJECT_ROOT> --case-id <CASE_ID> --cut-id <cut-id> --line '<frozen>' --audio-path <path> --capture-json '<capture stdout>' --before-id '<pre>' --after-id '<post>' --timing-json '<monotonic steps>'
```

Mark monotonic timestamps around the existing steps only (`clear_write_readback`, `generate_submit`, `generate_wait`, `result_capture`, `record_cut`, `cut_total`). No extra MCP/LLM call for timing.

If the queue still has cuts, go to the next frozen line immediately.

`resolve_tts_text.py`, `prepare_tts_field.py`, and `prove_tts_textarea.py` are fallback/debug only. Do not run them on the happy path.

After every cut is recorded, write the manifest **once** and complete `NARRATION`. Then return to `/product-video`. Next stage is ASSEMBLY.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/narration_queue.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --finish
```
