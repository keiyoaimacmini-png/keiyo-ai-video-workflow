# Cursor Desktop app / Cloud Agent product-video instructions

## Required workflow

- For full product-video production, invoke `/produce-tiktok-product-video-portable` from `.cursor/skills/produce-tiktok-product-video-portable/` and follow its `SKILL.md`.
- Resolve `PROJECT_ROOT` to the repository root and `SKILL_ROOT` to `$PROJECT_ROOT/.cursor/skills/produce-tiktok-product-video-portable`.
- Resolve **this case's** product model, settings, and material root before creating a case. Do not reuse another product's settings, media, script, editor project, or Drive object.

```bash
python3 .cursor/skills/produce-tiktok-product-video-portable/scripts/resolve_product_inputs.py --project-root . --product-model <MODEL> --require-materials
python3 .cursor/scripts/verify_product_video_setup.py --product-model <MODEL> --require-materials
```

- Settings path is always `config/product_video_settings_<MODEL>.v1.json`. For AN-S182 that file is pinned by SHA-256; do not infer or replace it. For any other model, add that model's own file instead of copying AN-S182.
- Material root is `PRODUCT_VIDEO_MATERIAL_ROOT` when set, otherwise `.runtime/product-video-inputs/<MODEL>_コピー`.
- When `config/product-video-rules` exists, use it as `RULES_ROOT` for `build_rule_snapshot.py`.
- Start a new case on **Gemini 3.8 Flash**. At Checkpoint 1, show the Grok 4.6 handoff card from `scripts/resolve_ai_model_lane.py --print-handoff-card`. After exact `台本OK`, continue only on **Grok 4.6**. A Cloud Agent parent model cannot be changed mid-run; start a new Grok 4.6 Cloud Agent with the printed continuation prompt, or switch the Desktop model picker before the next turn. Do not open CapCut on Gemini 3.8 Flash.

## Approval and safety boundary

- Use only the exact routine approvals `台本OK`, `粗編集OK`, and `完成・書き出しOK`. `編集が完了した` or `格納して` does not replace `完成・書き出しOK`.
- Create a new case, task root, workflow state, and editor project. Do not modify or overwrite existing projects, exports, Drive objects, payloads, receipts, or source media.
- Keep product media, evidence frames, editable runtime artifacts, exports, credentials, cookies, tokens, account identifiers, and session identifiers out of Git, pull requests, and ordinary logs.
- Do not open a pull request, publish an artifact, post, send externally, purchase credit, retry an unknown export/upload, overwrite, or delete originals, Drive objects, receipts, or another case unless the user separately authorizes that exact action.
- Standing completion is Drive 格納: after exact `完成・書き出しOK` bound to the current final-QA receipt, export once and create one new file in the Drive folder titled with this product model. Require exact new-file read-back. Use `export_only` only when the original request explicitly required local-only export.
- After stage `COMPLETE` and verified 格納 (Drive read-back, or an `export_only` destination-stored receipt proving a durable copy that is not a local working copy), purge this case's local working media on the Cloud VM, then run the same relative purge on the operator Mac. Do not leave product materials or completed-video working copies on either machine. Keep receipts, settings, git-tracked files, originals that are still the source of record, and the Drive stored file. If the local file is the only remaining completed video, stop with `HOLD_LOCAL_WORKING_MEDIA_IS_SOLE_COPY`. After a VM purge, if this host is not the Mac, stop with `HOLD_MAC_LOCAL_WORKING_MEDIA_PURGE_REQUIRED`. Default is dry-run; execute only through `scripts/purge_local_working_media.py`.

## 完了後のローカル削除

- `完成・書き出しOK` と格納が済んだ案件だけ、Cloud VM と操作Macから素材の作業コピーと完成動画の作業コピーを消す。
- 原本、Drive上の格納ファイル、JSONのreceipt、設定、進行中の別案件は消さない。
- 格納前、またはローカルが唯一の完成コピーのときは消さない。進行中の本編ファイルは消さない。

## 一括ナレーションのシーン隙間

- CapCut公式のホリデーツイストで台本を一括生成するときは、凍結した各行のあいだに空行だけを入れて貼る。省略記号や余計な読み上げ用の句読点は入れない。
- ダウンロード後、行ごとの境界に測った無音（既定 600ms）を入れ、その無音で1シーン1クリップに切ってから尺を合わせる。結合した1本のままタイムラインに残さない。
- 画面の字幕と payload の TTS 文言は凍結行のまま。一括生成は、含まれた全カットの初回TTSとして数える。

## テロップ

- 最終テロップは画面中央。はみ出す行は句読点や意味の切れ目で見た目だけ改行する。文字の追加・削除・並べ替えはしない。
- 太字、太い縁取り、コントラスト帯で目立たせる。最終カットのホールドも同じ位置に合わせる。

## Cursor Desktop browser and human handoff

- Use the official CapCut Web origin in Chrome only when the Cursor Agent has an actual browser/editor control adapter. A host editor adapter may run the same stages for this case only when it can create a new project, inspect frames, place captions/TTS, and export. Never mix two editors in one case. Never put CapCut or TikTok passwords in repository files or prompts.
- When login, CAPTCHA, 2FA, account choice, recovery, or new consent is required, stop with `HOLD_CAPCUT_LOGIN_USER_ACTION_REQUIRED` so the user can operate through Cursor Desktop.
- If the Cursor Agent lacks the browser/editor, rendered-frame, or audio capability required by the host-adapter contract, stop with the matching HOLD instead of claiming the edit is complete.
- If the Agent cannot reliably hear the full timeline, keep auditory verification pending at Checkpoint 3 and ask the user to listen on the same desktop. Do not add a fourth checkpoint.
