# Cursor Desktop on the operator Mac (Ver2)

Ver2 production runs on the operator Mac Cursor Desktop Agent. Do not send product-video work to Cursor Cloud Agent or a Cloud VM. The v1 Cloud launch note remains in `docs/cursor-cloud-agent-product-video.md`. The v2 launch note is `docs/mac-desktop-agent-product-video.md`.

## Required workflow

- For full product-video production, invoke `/produce-tiktok-product-video-portable` from `.cursor/skills/produce-tiktok-product-video-portable/` and follow its `SKILL.md`.
- Human-readable flow through Drive 格納: `docs/product-video-to-drive.md`.
- Resolve `PROJECT_ROOT` to the repository root and `SKILL_ROOT` to `$PROJECT_ROOT/.cursor/skills/produce-tiktok-product-video-portable`.
- Resolve **this case's** product model, settings, and material root before creating a case. Do not reuse another product's settings, media, script, editor project, or Drive object.

```bash
python3 .cursor/skills/produce-tiktok-product-video-portable/scripts/resolve_product_inputs.py --project-root . --product-model <MODEL> --require-materials
python3 .cursor/scripts/verify_product_video_setup.py --product-model <MODEL> --require-materials
```

- Settings path is always `config/product_video_settings_<MODEL>.v1.json`. For AN-S182 that file is pinned by SHA-256; do not infer or replace it. For any other model, add that model's own file instead of copying AN-S182.
- Material root is `PRODUCT_VIDEO_MATERIAL_ROOT` when set, otherwise `.runtime/product-video-inputs/<MODEL>_コピー`.
- When `config/product-video-rules` exists, use it as `RULES_ROOT` for `build_rule_snapshot.py`.

## Approval and safety boundary

- Use only the exact routine approvals `台本OK`, `粗編集OK`, and `完成・書き出しOK`. `編集が完了した` or `格納して` does not replace `完成・書き出しOK`.
- Create a new case, task root, workflow state, and editor project. Do not modify or overwrite existing projects, exports, Drive objects, payloads, receipts, or source media.
- Keep product media, evidence frames, editable runtime artifacts, exports, credentials, cookies, tokens, account identifiers, and session identifiers out of Git, pull requests, and ordinary logs.
- Do not open a pull request, publish an artifact, post, send externally, purchase credit, retry an unknown export/upload, overwrite, or delete originals, Drive objects, receipts, or another case unless the user separately authorizes that exact action.
- Standing completion is Drive 格納: after exact `完成・書き出しOK` bound to the current final-QA receipt, export once and create one new file in the Drive folder titled with this product model. Create that file from local bytes; do not inline the completed video as base64. If local-path ingest is unavailable, one authenticated Drive UI upload into the proven parent plus adapter read-back is allowed. Require exact new-file read-back. Use `export_only` only when the original request explicitly required local-only export. Uncertain tab ownership does not block `COMPLETE` after that read-back.
- After stage `COMPLETE` and verified 格納 (Drive read-back, or an `export_only` destination-stored receipt proving a durable copy that is not a local working copy), purge this case's local working media **on this Mac**. Do not leave product materials or completed-video working copies on the production host. Keep receipts, settings, git-tracked files, originals that are still the source of record, and the Drive stored file. If the local file is the only remaining completed video, stop with `HOLD_LOCAL_WORKING_MEDIA_IS_SOLE_COPY`. If this host is not the operator Mac (for example a Cloud VM left over from v1), purge that host first, then stop with `HOLD_MAC_LOCAL_WORKING_MEDIA_PURGE_REQUIRED`. Tell the operator the stored original is the Drive model-titled folder; on the Mac check Finder Downloads for the exact completed filename first, then repo `outputs/<case-id>/` and `out/` only if those copies exist. Missing copies are not a failure. Default is dry-run; execute only through `scripts/purge_local_working_media.py`.

## 完了後のローカル削除

- `完成・書き出しOK` と格納が済んだ案件だけ、**この Mac** から素材の作業コピーと完成動画の作業コピーを消す。
- まず Finder のダウンロードに完成ファイル名があるかを見る。続けてリポジトリ内 `outputs/` や `out/` を確認する。無いコピーは失敗にしない。
- 原本、Drive上の格納ファイル、JSONのreceipt、設定、進行中の別案件は消さない。
- 格納前、またはローカルが唯一の完成コピーのときは消さない。進行中の本編ファイルは消さない。

## 一括ナレーションのシーン隙間

- 公式ホリデーツイストが案件の編集正本で出せないときは、CapCut 公式 Text to Speech で凍結行を空行区切りで1回生成し、音声だけ編集正本へ戻す。映像は CapCut に入れない。ChatCut 代替ボイスや新規 CapCut 案件は出さない。`粗編集OK` のあと、パス選択で止めない。
- CapCut公式のホリデーツイストで台本を一括生成するときは、凍結した各行のあいだに空行だけを入れて貼る。省略記号や余計な読み上げ用の句読点は入れない。
- ダウンロード後、行ごとの境界に測った無音（既定 600ms）を入れ、その無音で1シーン1クリップに切ってから尺を合わせる。結合した1本のままタイムラインに残さない。
- 画面の字幕と payload の TTS 文言は凍結行のまま。一括生成は、含まれた全カットの初回TTSとして数える。

## テロップ

- 最終テロップは画面中央。案件エディタの字幕プログラム（ChatCut Caption Cards または CapCut ネイティブ）を使う。モーションを視聴者向け字幕にしない。
- はみ出す行は句読点や意味の切れ目で見た目だけ改行する。文字の追加・削除・並べ替えはしない。
- 太字、太い縁取り、コントラスト帯で目立たせる。最終カットのホールドも同じ位置に合わせる。
- JSON の座標より、合成フレームの中央を正とする。字幕ホールド用トラックが mute のとき refresh しない。

## Cursor Desktop browser and human handoff

- Production host is this Mac's Cursor Desktop Agent. Do not use Cloud Agent for picture, captions, export, or Drive 格納.
- The agent-controlled browser is not Google Chrome.app. Do not assume CapCut or TikTok sessions saved in Chrome.app. Use the official CapCut Web origin in the agent-controlled browser only when that adapter exists. A host editor adapter (for example ChatCut) may run the same stages for this case only when it can create a new project, inspect frames, place captions, and export. Do not mix two picture timelines. Official Holiday Twist may be generated on CapCut Text to Speech and imported as audio when the editor of record cannot emit that preset; do not offer a substitute voice or a new CapCut case. Never put CapCut or TikTok passwords in repository files or prompts.
- When login, CAPTCHA, 2FA, account choice, recovery, or new consent is required, stop with `HOLD_CAPCUT_LOGIN_USER_ACTION_REQUIRED` so the user can operate on this Mac.
- If the Cursor Agent lacks the browser/editor, rendered-frame, or audio capability required by the host-adapter contract, stop with the matching HOLD instead of claiming the edit is complete.
- If the Agent cannot reliably hear the full timeline, keep auditory verification pending at Checkpoint 3 and ask the user to listen on the same desktop. Do not add a fourth checkpoint.
