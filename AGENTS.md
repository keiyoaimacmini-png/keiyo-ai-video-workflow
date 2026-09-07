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
- When `config/product-video-rules` exists, use it as `RULES_ROOT` for `build_rule_snapshot.py`. Those files are the standing first-pass rules. Portable stages run craft checks against them before `台本OK`, `粗編集OK`, and `完成・書き出しOK`. Do not wait for a correction to apply them.

## Gemini 台本（デスクトップアプリ。Cursor のモデルは切り替えない）

- Checkpoint 1 の台本案は、この Mac のログイン済み **Gemini.app** に作らせる。Cursor の親モデル切替、外部モデル枠、Gemini API、`GEMINI_API_KEY`、Google Chrome.app、エージェント制御ブラウザは使わない。
- 使用モデルはピッカーで **Gemini 3.8 Flash** と読み戻す。Auto / Pro / 別の Flash には落とさない。違う表示なら `HOLD_GEMINI_MODEL_NOT_VERIFIED`。
- Gemini.app はこちらが操作する。貼り付け文をオペレーターに渡して止めない。ログイン済み Gemini.app を前面に出してプロンプトを送り、返ってきた台詞を読む。今まで通っていた送り方が落ちたら、同じターンで直して台本まで終わらせる。ログイン、CAPTCHA、2FA、アカウント選択だけ `HOLD_GEMINI_LOGIN_USER_ACTION_REQUIRED`。
- ログイン、CAPTCHA、2FA、アカウント選択は `HOLD_GEMINI_LOGIN_USER_ACTION_REQUIRED`。パスワード、クッキー、トークン、API キーをリポジトリ、プロンプト、receipt、ログに置かない。
- 素材の SHA と in/out は Gemini に作らせない。台詞が決まってから、その行を支える範囲だけ実フレーム確認して payload に結ぶ。
- `台本OK` で止める対象は台詞・6段構成・フックの困りごとに対する解決案。素材6本のロックや in/mid/out のコンタクトシートでは止めない。絵の確定は `粗編集OK`。見た目や「日差しが入ってこない」だけでは暑さのフックを回収したことにしない。
- 台詞が変わらない素材差し替えでは `台本OK` を取り直さない。作業が止まったら同じターンで続けるか、該当 HOLD で止めてオペレーターが動けるようにする。一晩待たない。

## Google Drive（格納はローカルパス。デスクトップアプリは使わない）

- 完成動画の格納は、書き出し読戻しの**同じターン**で `scripts/upload_drive_local_file.py` を使う。ローカルファイルから HTTPS 再開始アップロードし、Drive 連携で読み戻す。格納に Chrome.app を開かない。親フォルダ名は型番と exact case。16–22MB なら数十秒が正常。完成動画をツール引数の base64 にしない。Cursor の Drive コネクタ秘密は読まない。
- ヘルパーが OAuth 不足で HOLD したら `HOLD_DRIVE_LOCAL_BYTES_UNAVAILABLE`。オペレーターが `.runtime/drive-oauth-client.json` を置き、**リポジトリのルート**で `--login` する。ホームディレクトリでは実行しない。エージェントは `--login` を起動しない。Chrome.app をスクショ・OCR・クリック探索しない。
- Drive の原本確認・素材取得が連携でできないときだけ、この Mac の **Google Chrome.app** で公式 Drive Web（`https://drive.google.com/`）を使う。
- Google Drive デスクトップアプリ、ローカル同期マウント、rclone は使わない。
- エージェント制御ブラウザは Chrome.app の Google ログインを共有しないので、Drive の代用にしない。
- 必要な Chrome Drive Web を開けないときは `HOLD_DRIVE_WEB_NOT_VERIFIED`。ログイン、CAPTCHA、2FA、アカウント選択は `HOLD_DRIVE_LOGIN_USER_ACTION_REQUIRED`。パスワードはチャットに書かない。
- フォルダ URL と生の Drive ID は Git に書かない。格納の親フォルダは型番名で特定する。

## Approval and safety boundary

- Use only the exact routine approvals `台本OK`, `粗編集OK`, and `完成・書き出しOK`. `編集が完了した` or `格納して` does not replace `完成・書き出しOK`.
- Create a new case, task root, workflow state, and editor project. Do not modify or overwrite existing projects, exports, Drive objects, payloads, receipts, or source media.
- Keep product media, evidence frames, editable runtime artifacts, exports, credentials, cookies, tokens, account identifiers, and session identifiers out of Git, pull requests, and ordinary logs.
- Do not open a pull request, publish an artifact, post, send externally, purchase credit, retry an unknown export/upload, overwrite, or delete originals, Drive objects, receipts, or another case unless the user separately authorizes that exact action.
- Standing completion is Drive 格納: after exact `完成・書き出しOK` bound to the current final-QA receipt, export once and, in that same turn, create one new file in the Drive folder titled with this product model in exact case. Create that file with `scripts/upload_drive_local_file.py` from local bytes; do not inline the completed video as base64. Do not open Chrome.app for 格納. A 16–22MB file should finish in tens of seconds. Do not use Google Drive for desktop. Require exact new-file read-back. Use `export_only` only when the original request explicitly required local-only export. Uncertain tab ownership does not block `COMPLETE` after that read-back.
- After stage `COMPLETE` and verified 格納 (Drive read-back, or an `export_only` destination-stored receipt proving a durable copy that is not a local working copy), purge this case's local working media **on this Mac**. Do not leave product materials or completed-video working copies on the production host. Keep receipts, settings, git-tracked files, originals that are still the source of record, and the Drive stored file. If the local file is the only remaining completed video, stop with `HOLD_LOCAL_WORKING_MEDIA_IS_SOLE_COPY`. If this host is not the operator Mac (for example a Cloud VM left over from v1), purge that host first, then stop with `HOLD_MAC_LOCAL_WORKING_MEDIA_PURGE_REQUIRED`. Tell the operator the stored original is the Drive model-titled folder; on the Mac check Finder Downloads for the exact completed filename first, then repo `outputs/<case-id>/` and `out/` only if those copies exist. Missing copies are not a failure. Default is dry-run; execute only through `scripts/purge_local_working_media.py`.

## 完了後のローカル削除

- `完成・書き出しOK` と格納が済んだ案件だけ、**この Mac** から素材の作業コピーと完成動画の作業コピーを消す。
- まず Finder のダウンロードに完成ファイル名があるかを見る。続けてリポジトリ内 `outputs/` や `out/` を確認する。無いコピーは失敗にしない。
- 原本、Drive上の格納ファイル、Google Driveデスクトップの同期ミラー、JSONのreceipt、設定、進行中の別案件は消さない。同期ミラーを Finder から消すと Drive 上の原本も消える。
- 格納前、またはローカルが唯一の完成コピーのときは消さない。進行中の本編ファイルは消さない。

## ナレーション（1カットごと）

- 公式ホリデーツイストが案件の編集正本で出せないときは、CapCut 公式 Text to Speech で凍結行を **1カット分のセリフごとに** 生成し、音声だけ編集正本へ戻す。映像は CapCut に入れない。ChatCut 代替ボイスや新規 CapCut 案件は出さない。`粗編集OK` のあと、パス選択で止めない。
- 貼るのはそのカットの凍結行だけ。全行を空行区切りで一括貼りしない。省略記号や余計な読み上げ用の句読点は入れない。
- 生成後の取得はオペレーターに頼まない。「オーディオのみ」は押さない。Finder / OS / 埋め込みブラウザの保存ダイアログは使わない。オペレーターに「保存」を押させない。`~/Downloads/CapCut_TTS_*` は取得経路にしない。結果カードの `video`/`audio` currentSrc（`mime_type=audio_mpeg` など）を `scripts/capture_capcut_result_audio.py` で案件の TTS 作業ディレクトリへ直接保存する。保存ダイアログが出ても閉じるか無視し、結果バイトを取る。成功したカットは再生成しない。CapCut の「さらに編集」は押さない。
- 1カット1クリップとして編集正本へ戻し、そのカットの聞き取れる発話終わりで尺を合わせる。結合した1本のままタイムラインに残さない。
- 画面の字幕と payload の TTS 文言は凍結行のまま。各カットの初回成功レンダーだけをそのカットの初回TTSとして数える。

## テロップ

- 最終テロップは画面中央。案件エディタの字幕プログラム（ChatCut Caption Cards または CapCut ネイティブ）を使う。モーションを視聴者向け字幕にしない。
- はみ出す行は句読点や意味の切れ目で見た目だけ改行する。文字の追加・削除・並べ替えはしない。
- 太字、太い縁取り、コントラスト帯で目立たせる。最終カットのホールドも同じ位置に合わせる。
- JSON の座標より、合成フレームの中央を正とする。字幕ホールド用トラックが mute のとき refresh しない。

## Cursor Desktop browser and human handoff

- Production host is this Mac's Cursor Desktop Agent. Do not use Cloud Agent for picture, captions, export, or Drive 格納.
- Checkpoint 1 dialogue is drafted in this Mac's logged-in Gemini.app with Gemini 3.8 Flash. The agent sends the prompt and reads the dialogue in the same turn. Do not leave a paste for the operator. Do not screenshot-hunt Gemini.app. Completed-video 格納 uses `scripts/upload_drive_local_file.py` in the same turn as the export read-back. Do not open Chrome.app for 格納. Drive originals/materials may use Google Chrome.app at `https://drive.google.com/`. The agent-controlled browser is not Gemini.app and must not be used as a substitute for those logged-in Google sessions. Do not use Google Drive for desktop.
- Use the official CapCut Web origin in the agent-controlled browser only when that adapter exists. A host editor adapter (for example ChatCut) may run the same stages for this case only when it can create a new project, inspect frames, place captions, and export. Do not mix two picture timelines. Official Holiday Twist may be generated on CapCut Text to Speech and imported as audio when the editor of record cannot emit that preset; do not offer a substitute voice or a new CapCut case. Never put CapCut, TikTok, Google, or Gemini passwords in repository files or prompts.
- When CapCut or TikTok login, CAPTCHA, 2FA, account choice, recovery, or new consent is required, stop with `HOLD_CAPCUT_LOGIN_USER_ACTION_REQUIRED`. When Gemini Web needs the same user action, stop with `HOLD_GEMINI_LOGIN_USER_ACTION_REQUIRED`. When Drive Web on Chrome.app needs the same user action, stop with `HOLD_DRIVE_LOGIN_USER_ACTION_REQUIRED`.
- If the Cursor Agent lacks the browser/editor, rendered-frame, or audio capability required by the host-adapter contract, stop with the matching HOLD instead of claiming the edit is complete.
- If the Agent cannot reliably hear the full timeline, keep auditory verification pending at Checkpoint 3 and ask the user to listen on the same desktop. Do not add a fourth checkpoint.
