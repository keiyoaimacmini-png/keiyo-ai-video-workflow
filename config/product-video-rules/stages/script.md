# Script-stage rules

## Gemini に渡す文面

Gemini に送るのは `.cursor/skills/produce-tiktok-product-video-portable/scripts/render_gemini_web_prompt.py` の出力だけである。

このファイル、`common.md`、lessons、製品例、禁止の追記、前回の台詞見本は足さない。プロンプト本文を手で書き換えない。案件で差し込むのは brief の `verified_facts` と内部の製品型番だけである。`usable_shots`、`observed_actions`、ファイル名、ハッシュ、開始終了秒は Gemini に渡さない。

送りは `scripts/send_gemini_cli_prompt.py`。Antigravity CLI（`agy --print`）で、モデルは **Gemini 3.8 Flash**。Gemini.app、Gemini API、Cursor の親モデル切替、Chrome.app、エージェント制御ブラウザは使わない。AI Credit の上振れは使わない。貼り付け文をオペレーターに渡して止めない。`agy` が失敗したら `HOLD_GEMINI_CLI_NOT_VERIFIED`。モデルが Gemini 3.8 Flash でなければ `HOLD_GEMINI_MODEL_NOT_VERIFIED`。

## エージェント側（Gemini には送らない）

Do not inventory, hash, or watch candidate media before the spoken draft exists. Labels and sidecars, when used later, are leads, not proof.

A model draft may propose spoken dialogue plus a per-line picture brief (`picture_must` = required on-screen action, `picture_ideal` = distance and camera only). That brief is a planned picture requirement, not a description of existing files. It must not name files or invent SHA-256 and source in/out. Those are bound from inspected frames after `台本OK`, and only for the ranges selected from `picture_must`. `picture_must` is the matching gate; `picture_ideal` ranks candidates and must not stall the edit.

The agent does not rewrite the six spoken lines as the first path. If the draft fails taste, glue, endings, or craft, re-send the same renderer output through `send_gemini_cli_prompt.py`. Use `apply_spoken_lines.py` only when the operator supplies exact wording.

Checkpoint 1 (`台本OK`) reviews the six spoken lines, six-stage order, and whether `problem_resolution` presents a solution to the same problem named in the hook. Do not make `台本OK` wait on a locked cut table, source path, in/out, or in/mid/out contact sheets. Picture assignment is Checkpoint 2 (`粗編集OK`).

After `台本OK`, match `picture_must` to files (use `.asset.md` interval tables when present), prove only those selected ranges, and import only those clips. A source-asset or in/out swap that keeps the frozen spoken lines, punctuation, line breaks, stage order, and claimed facts stays at rough-edit review. Do not reopen Checkpoint 1. Reopen `台本OK` only when dialogue, facts, or stage order change.

At Checkpoint 1, state the hook problem and the spoken solution explicitly. If they do not match, `HOLD_SCRIPT_INCOMPLETE` and do not ask `台本OK`.
