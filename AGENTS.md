# Cursor Desktop app / Cloud Agent product-video instructions

## Required workflow

- For full product-video production, invoke `/produce-tiktok-product-video-portable` from `.cursor/skills/produce-tiktok-product-video-portable/` and follow its `SKILL.md`.
- Resolve `PROJECT_ROOT` to the repository root and `SKILL_ROOT` to `$PROJECT_ROOT/.cursor/skills/produce-tiktok-product-video-portable`.
- Before creating a case, run `python3 .cursor/scripts/verify_product_video_setup.py --require-materials`. Do not continue past its HOLD status.
- The canonical AN-S182 settings file is `config/product_video_settings_AN-S182.v1.json`. Do not infer or replace it.
- The material root is `PRODUCT_VIDEO_MATERIAL_ROOT` when set, otherwise `.runtime/product-video-inputs/AN-S182_コピー`.
- When `config/product-video-rules` exists, use it as `RULES_ROOT` for `build_rule_snapshot.py`.

## Approval and safety boundary

- Use only the exact routine approvals `台本OK`, `粗編集OK`, and `完成・書き出しOK`.
- Create a new case, task root, workflow state, and CapCut Web project. Do not modify or overwrite existing projects, exports, Drive objects, payloads, receipts, or source media.
- Keep product media, evidence frames, editable runtime artifacts, exports, credentials, cookies, tokens, account identifiers, and session identifiers out of Git, pull requests, and ordinary logs.
- Do not open a pull request, publish an artifact, post, send externally, purchase credit, retry an unknown export/upload, overwrite, or delete originals, Drive objects, receipts, or another case unless the user separately authorizes that exact action.
- Drive creation is allowed only when the original request fixed the exact scope and `完成・書き出しOK` is bound to the current final-QA receipt. Require exact new-file read-back.
- After stage `COMPLETE` and verified 格納 (Drive read-back, or an `export_only` destination-stored receipt proving a durable copy that is not a local working copy), purge this case's local working media on the Cloud VM, then run the same relative purge on the operator Mac. Do not leave product materials or completed-video working copies on either machine. Keep receipts, settings, git-tracked files, originals that are still the source of record, and the Drive stored file. If the local file is the only remaining completed video, stop with `HOLD_LOCAL_WORKING_MEDIA_IS_SOLE_COPY`. After a VM purge, if this host is not the Mac, stop with `HOLD_MAC_LOCAL_WORKING_MEDIA_PURGE_REQUIRED`. Default is dry-run; execute only through `scripts/purge_local_working_media.py`.

## 完了後のローカル削除

- `完成・書き出しOK` と格納が済んだ案件だけ、Cloud VM と操作Macから素材の作業コピーと完成動画の作業コピーを消す。
- 原本、Drive上の格納ファイル、JSONのreceipt、設定、進行中の別案件は消さない。
- 格納前、またはローカルが唯一の完成コピーのときは消さない。進行中の本編ファイルは消さない。

## 一括ナレーションのシーン隙間

- CapCut公式のホリデーツイストで台本を一括生成するときは、凍結した各行のあいだに空行だけを入れて貼る。省略記号や余計な読み上げ用の句読点は入れない。
- ダウンロード後、行ごとの境界に測った無音（既定 600ms）を入れ、その無音で1シーン1クリップに切ってから尺を合わせる。結合した1本のままタイムラインに残さない。
- 画面の字幕と payload の TTS 文言は凍結行のまま。一括生成は、含まれた全カットの初回TTSとして数える。

## Cursor Desktop browser and human handoff

- Use the official CapCut Web origin in Chrome only when the Cursor Agent has an actual browser/editor control adapter. Never put CapCut or TikTok passwords in repository files or prompts.
- When login, CAPTCHA, 2FA, account choice, recovery, or new consent is required, stop with `HOLD_CAPCUT_LOGIN_USER_ACTION_REQUIRED` so the user can operate through Cursor Desktop.
- If the Cursor Agent lacks the browser/editor, rendered-frame, or audio capability required by the host-adapter contract, stop with the matching HOLD instead of claiming the edit is complete.
- If the Agent cannot reliably hear the full timeline, keep auditory verification pending at Checkpoint 3 and ask the user to listen on the same desktop. Do not add a fourth checkpoint.
