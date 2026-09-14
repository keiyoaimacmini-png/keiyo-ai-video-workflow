---
name: product-video-narration
description: Generate Holiday Twist source audio from the frozen approved script. Use only when /product-video dispatches NARRATION.
disable-model-invocation: true
---

# NARRATION

Read this file only when dispatch says `product-video-narration`.

Approved-script cuts are a **queue**. Stay in this Skill until every cut is recorded. Do not return to `/product-video` dispatch, do not make a new LLM plan, and do not chat after a successful cut.

Use only the approved script. Do not run a speed-selection algorithm.
CapCut generate is the **source audio**. ChatCut clip `playbackRate` 1.2 is applied later. Do not require CapCut generate speed to equal 1.2. Do not call unpublished CapCut speed setters. Do not record the source file as already 1.2x processed.
SCRIPT LINE == NARRATION == TELOP. Do not trim, strip, ignore newlines or zero-width characters, or treat visible/OCR/document-HTML text as a match.

Load this cut's `generation_count_for_cut` from `tts/generation-attempts.json`. Never reset it to 0 after a failed generate. If the previous outcome is `unknown`, do not submit again; observe the existing result.

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
6. Confirm the existing credit-dialog classifier is ready. Do not generate yet.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/tts_session.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --prove-setup --observation-json '<observation>'
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/narration_queue.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --mark-setup
```

Follow `${PROJECT_ROOT}/.cursor/skills/product-video/references/capcut-chrome-mcp.md`. Do not fall back to cursor-ide-browser or an extension adapter.

If that same session is later lost, recover it (re-attach, same page, Holiday Twist, field) at most 3 times:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/tts_session.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --may-reuse --observation-json '<observation>'
```

Do not ask the operator about a transient miss. If it still cannot attach, stop with `HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE`. Login, CAPTCHA, 2FA, or account choice still stop with `HOLD_CAPCUT_LOGIN_USER_ACTION_REQUIRED`.

Between successful cuts do **not**:

- re-resolve the MCP namespace
- rerun Chrome connection preflight
- re-search the CapCut page
- re-select Holiday Twist
- re-resolve the voice ID
- return to dispatch
- report the same environment status

Do not chat after a successful cut. Continue immediately to the next frozen line.

## Each cut (same session)

Ask the queue for the current cut (`--next`). For that frozen line only:

1. Completely empty the already-identified TTS field. Do not append.
2. Write that frozen line only.
3. Prove the text CapCut will submit. Priority:
   1. CapCut editor internal model / effective editor value
   2. TTS submission application state
   3. contenteditable DOM nodes, only when user-authored text nodes are distinguished from CapCut-owned independent structural sentinel nodes
4. Do not use document HTML, preview, OCR, or visible text as proof. Do not `trim` / `strip` / Unicode-normalize / `replace("\u200B", "")`. Exclude U+200B only as a proven independent CapCut sentinel node. If that distinction is impossible, stop with `HOLD_TTS_INPUT_FIELD_UNVERIFIED`.
5. `effective_tts_text` must raw-equal the frozen line. On mismatch, clear, rewrite, and re-read once. Input retries do not increment `generation_count_for_cut`.
6. Existing CapCut credit consumption is allowed. A dialog titled `Credits will be consumed` that shows the required credit count, offers Cancel / Got it, and has no monthly/annual price, free trial, payment form, or extra purchase is existing-balance consumption for this generate. Classify before clicking Got it:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/classify_capcut_credit.py" --record-json '<observation>'
```

Approve Got it only when that helper returns `approve_got_it: true`. The word `Pro` in the dialog body is not itself a HOLD. Do not auto-approve a Pro monthly/annual contract, free trial, extra credit purchase, auto-reload, new payment, or plan change. If existing-balance consumption and a new contract cannot be distinguished, HOLD.
7. Gate generation:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/resolve_tts_text.py" --frozen-json '<json string>' --observation-json '<observation>'
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/prepare_tts_field.py" --frozen-json '<json string>' --actual-json '<effective_tts_text json>' --attempt <1|2> --generation-count <n>
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/tts_attempts.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --cut-id <cut-id> --may-generate
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/prove_tts_textarea.py" --record-json '<record>'
```

Generate only when text exact-match, `prove_tts_textarea.py` returns `generate: true`, and `tts_attempts.py --may-generate` allows it. `MAX_GENERATIONS_PER_CUT` is 2. Do not click 生成 before those gates. ChatCut clip speed is proved later with `${PROJECT_ROOT}/.cursor/skills/product-video/scripts/prove_tts_speed.py` from `inspect_item` `playbackRate`.

8. After CapCut answers, record the attempt even when there is no audio:

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/tts_attempts.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --cut-id <cut-id> --record-outcome <success|failure|unknown>
```

A CapCut failure does not adopt audio. It still increments the cut's generation count.

9. On success, save audio with the existing capture helper into the case TTS directory. Do not use Downloads or a save dialog.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/produce-tiktok-product-video-portable/scripts/capture_capcut_result_audio.py" --url <result-src> --output <task-root>/tts/<cut-id>.mp3
```
10. Measure the **source file** duration. Record path + `source_duration_seconds` + planned ChatCut `editor_playback_rate` 1.2 + `planned_duration_seconds` (`source / 1.2`). Do not FFmpeg-accelerate the file. Do not judge voice quality. Stop only for wrong text, mixed leftover text, missing audio, or corrupt/truncated output.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/narration_queue.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --record-cut <cut-id> --line '<frozen>' --audio-path <path> --source-duration-seconds <sec>
```

If the queue still has remaining cuts, immediately run the same cut steps on the next frozen line. Do not write `narration-manifest.json` yet.

After every cut is recorded, write the manifest **once** and complete `NARRATION`. Then return to `/product-video`. Next stage is ASSEMBLY.

```bash
python3 "${PROJECT_ROOT}/.cursor/skills/product-video/scripts/narration_queue.py" --project-root <PROJECT_ROOT> --case-id <CASE_ID> --finish
```
