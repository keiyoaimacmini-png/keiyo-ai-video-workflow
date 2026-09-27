---
name: jev-mcp-20260923
description: >
  Use Jev only for semantic routing, candidate ranking,
  verification, review, and completion gates.
---

# Jev

Jev is a decision model. It does not write code, scripts, captions, or narration.
Call the `jev` MCP tools for semantic judgments only. Keep partner generation for actual writing.

When this Skill's behavior changes, rename the folder and frontmatter `name` date (`YYYYMMDD`) together. Do not keep the previous dated folder.

Do not send API keys, OAuth tokens, passwords, `.env` contents, cookies, or customer personal data to Jev. Send only the needed fragment.

## Use Jev

1. `jev_step` — next-step judgment when prepared tool calls already exist. Prefer one `jev_step` over `jev_coding_loop` + `jev_tool_route`.
2. `jev_rank` — choose among many semantic candidates (files, errors, symbols, skills). Use host code for string match or numeric sort.
3. `jev_coding_loop` — retry / stop / gather context / whether a generative model is needed, when no prepared call exists. Call a generative partner only if `partner_model.required` is true.
4. `jev_review` — meaning review of a diff that matters. Skip trivial edits.
5. `jev_verify` — a claim such as "this fix solved X" must match the evidence.
6. `jev_gate` — finish an important change with patch review + claim verification in one call.
7. `jev_screen` — untrusted external pages, issues, or pastes. Not first-party repo files.
8. `jev_evaluate` — atomic semantic judgment that fits none of the above. Rare.

Read `action`: `auto` accept, `review` inspect first, `escalate` do not auto-accept. Incomplete `coverage` is never automatic approval.

## Do not use Jev

- code generation, prose, or script drafts
- math, dates, schema checks, exact string compare, file existence
- known-path reads, known commands, simple git or Python
- browser clicks, CapCut TTS waits, ffprobe, queue or manifest writes
- any step that is already decided

`/product-video` stages PREPARE → SCRIPT → NARRATION → ASSEMBLY → ROUGH_EDIT → DELIVERY are already decided. Do not call Jev for that chain, except one case: during ASSEMBLY, call `jev_rank` once per cut when host code left two or more duration-qualified scenes and did not settle the meaning. Do not call Jev to read notes, compare durations, write the script, watch video, or run narration.

Never insert Jev into a NARRATION cut: clear → write → readback → Generate → result capture → record.

Do not slow a deterministic workflow by adding Jev.
