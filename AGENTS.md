# Cursor Desktop on the operator Mac (Ver2)

Ver2 production runs on the operator Mac Cursor Desktop Agent. Do not send product-video work to Cursor Cloud Agent or a Cloud VM. The v1 Cloud launch note remains in `docs/cursor-cloud-agent-product-video.md`. The v2 launch note is `docs/mac-desktop-agent-product-video.md`.

## Required workflow

- For full product-video production, invoke `/product-video` from `.cursor/skills/product-video/` and follow its `SKILL.md`.
- Do not start a new case from `produce-tiktok-product-video-portable` or `produce-tiktok-product-video-v3`.
- Human-readable flow through Drive 格納: `docs/product-video-to-drive.md`.
- Resolve `PROJECT_ROOT` to the repository root and `SKILL_ROOT` to `$PROJECT_ROOT/.cursor/skills/product-video`.
- Resolve **this case's** product model, settings, and material root before creating a case. Do not reuse another product's settings, media, script, editor project, or Drive object.

```bash
python3 .cursor/skills/produce-tiktok-product-video-portable/scripts/resolve_product_inputs.py --project-root . --product-model <MODEL> --require-materials
python3 .cursor/skills/product-video/scripts/run_self_test.py
```

- Settings path is always `config/product_video_settings_<MODEL>.v1.json`. For AN-S182 that file is pinned by SHA-256; do not infer or replace it. For any other model, add that model's own file instead of copying AN-S182.
- Material root is `PRODUCT_VIDEO_MATERIAL_ROOT` when set, otherwise `.runtime/product-video-inputs/<MODEL>_コピー`.
- Stages chain automatically: PREPARE → SCRIPT → (wait for `案Nで台本OK`) → NARRATION → ASSEMBLY → ROUGH_EDIT → WAITING_FOR_OPERATOR → (wait for `完成・格納してください`) → DELIVERY → COMPLETE.
- Do not ask Continue / Proceed between automatic stages. Do not require `粗編集OK`. Do not run an AI final visual-quality review.

## Gemini 台本（Antigravity CLI。Cursor のモデルは切り替えない）

- 台本案は、この Mac のログイン済み **Antigravity CLI（`agy --print`）** に、**Gemini 3.8 Flash** で作らせる。Cursor の親モデル切替、外部モデル枠、Gemini API、`GEMINI_API_KEY`、Gemini.app、Google Chrome.app、エージェント制御ブラウザは使わない。AI Credit の上振れ課金は使わない。
- 使用モデルは **`gemini-3.8-flash`**。Auto / Pro / 別の Flash には落とさない。違うモデルなら `HOLD_GEMINI_MODEL_NOT_VERIFIED`。`agy` が無い、一発印刷が失敗する、枠が尽きた、ファイルを書き始めた場合は `HOLD_GEMINI_CLI_NOT_VERIFIED`。
- 送りは `product-video/scripts/render_script_prompt.py` の出力を `produce-tiktok-product-video-portable/scripts/send_gemini_cli_prompt.py` で送る。プロンプト本文を手で書き換えない。ヘルパーが HOLD したら探索に入らずその HOLD で止める。貼り付け文をオペレーターに渡して止めない。ログイン、CAPTCHA、2FA、アカウント選択だけ `HOLD_GEMINI_LOGIN_USER_ACTION_REQUIRED`。オペレーターは Terminal で `agy` を起動して Google ログインする。エージェントはログインを起動しない。
- 採用は exact `案Nで台本OK` のみ。別の言い回しを承認に変換しない。凍結後は SCRIPT LINE == NARRATION == TELOP。言い換え・短縮・句読点変更をしない。
- 素材の SHA と in/out は Gemini に作らせない。台本の前に全件ハッシュや全尺視聴はしない。選んだファイルの選んだ範囲だけ `prove_source_range.py` で証明する。
- 作業が止まったら同じターンで続けるか、該当 HOLD で止めてオペレーターが動けるようにする。一晩待たない。

## Google Drive（格納はローカルパス。デスクトップアプリは使わない）

- 完成動画の格納は、書き出し読戻しの**同じターン**で `scripts/upload_drive_local_file.py` を使う。ローカルファイルから HTTPS 再開始アップロードし、Drive 連携で読み戻す。格納に Chrome.app を開かない。親フォルダ名は型番と exact case。16–22MB なら数十秒が正常。完成動画をツール引数の base64 にしない。Cursor の Drive コネクタ秘密は読まない。
- ヘルパーが OAuth 不足で HOLD したら `HOLD_DRIVE_LOCAL_BYTES_UNAVAILABLE`。オペレーターが `.runtime/drive-oauth-client.json` を置き、**リポジトリのルート**で `--login` する。ホームディレクトリでは実行しない。エージェントは `--login` を起動しない。Chrome.app をスクショ・OCR・クリック探索しない。
- Drive の原本確認・素材取得が連携でできないときだけ、この Mac の **Google Chrome.app** で公式 Drive Web（`https://drive.google.com/`）を使う。
- Google Drive デスクトップアプリ、ローカル同期マウント、rclone は使わない。
- エージェント制御ブラウザは Chrome.app の Google ログインを共有しないので、Drive の代用にしない。
- 必要な Chrome Drive Web を開けないときは `HOLD_DRIVE_WEB_NOT_VERIFIED`。ログイン、CAPTCHA、2FA、アカウント選択は `HOLD_DRIVE_LOGIN_USER_ACTION_REQUIRED`。パスワードはチャットに書かない。
- フォルダ URL と生の Drive ID は Git に書かない。格納の親フォルダは型番名で特定する。

## Approval and safety boundary

- Routine stops are only exact `案Nで台本OK` and exact `完成・格納してください`. `粗編集OK` and `完成・書き出しOK` are not used. `編集が完了した` or `格納して` does not replace `完成・格納してください`.
- Create a new case, task root, workflow state, and editor project. Do not modify or overwrite existing projects, exports, Drive objects, payloads, receipts, or source media.
- Keep product media, evidence frames, editable runtime artifacts, exports, credentials, cookies, tokens, account identifiers, and session identifiers out of Git, pull requests, and ordinary logs.
- Do not open a pull request, publish an artifact, post, send externally, purchase credit, retry an unknown export/upload, overwrite, or delete originals, Drive objects, receipts, or another case unless the user separately authorizes that exact action.
- Standing completion is Drive 格納: after exact `完成・格納してください`, export once and, in that same turn, create one new file in the Drive folder titled with this product model in exact case. Create that file with `scripts/upload_drive_local_file.py` from local bytes; do not inline the completed video as base64. Do not open Chrome.app for 格納. Require exact new-file read-back. COMPLETE only after Drive verification.
- After stage `COMPLETE` and verified 格納, purge this case's local working media **on this Mac** through `scripts/purge_local_working_media.py`. Never purge before verified delivery. Default is dry-run; execute only with `--execute --i-confirm-destination-stored`.

## 完了後のローカル削除

- `完成・格納してください` と格納が済んだ案件だけ、**この Mac** から素材の作業コピーと完成動画の作業コピーを消す。
- まず Finder のダウンロードに完成ファイル名があるかを見る。続けてリポジトリ内 `outputs/` や `out/` を確認する。無いコピーは失敗にしない。
- 原本、Drive上の格納ファイル、Google Driveデスクトップの同期ミラー、JSONのreceipt、設定、進行中の別案件は消さない。同期ミラーを Finder から消すと Drive 上の原本も消える。
- 格納前、またはローカルが唯一の完成コピーのときは消さない。進行中の本編ファイルは消さない。

## ナレーション（1カットごと）

- 編集上の再生速度は常に **1.2倍速**。速度選択アルゴリズムは使わない。CapCut 生成時に 1.2 を要求しない。ChatCut の音声クリップ `playbackRate` に 1.2 を付ける。
- 公式ホリデーツイストが案件の編集正本で出せないときは、CapCut 公式 Text to Speech で凍結行を **1カット分のセリフごとに** 生成し、原音だけ編集正本へ戻す。映像は CapCut に入れない。ChatCut 代替ボイスや新規 CapCut 案件は出さない。
- 貼るのはそのカットの凍結行だけ。全行を空行区切りで一括貼りしない。
- 生成前にテキスト欄を全置換し、読み戻しが凍結行と完全一致してから生成する。結果カードの `video`/`audio` currentSrc を `scripts/capture_capcut_result_audio.py` で案件の TTS 作業ディレクトリへ直接保存する。原音の実再生時間を記録する。原音を 1.2 倍加工済みとは記録しない。
- 1カット1クリップとして編集正本へ戻し、ChatCut でクリップ速度 1.2 を付けたあとの区間に映像とテロップを合わせる。

## テロップ

- 最終テロップは画面中央。案件エディタの字幕プログラム（ChatCut Caption Cards または CapCut ネイティブ）を使う。モーションを視聴者向け字幕にしない。
- ChatCut では保存済みユーザープリセット `product-video-center` を一度 `preset_apply` する。案件ごとに太字・縁を作り直さない。背景帯は付けない。
- テロップ文言は凍結行と完全一致。はみ出す行は句読点や意味の切れ目で見た目だけ改行する。文字の追加・削除・並べ替えはしない。
- 太字の見出しフォント（Dela Gothic One）と白い文字、太い黒縁、ドロップシャドウで目立たせる。背景帯は付けない。

## Cursor Desktop browser and human handoff

- Production host is this Mac's Cursor Desktop Agent. Do not use Cloud Agent for picture, captions, export, or Drive 格納.
- Script drafts use this Mac's logged-in Antigravity CLI (`agy --print`) at Gemini 3.8 Flash. The agent sends the prompt and reads the dialogue in the same turn. Do not leave a paste for the operator. Do not use Gemini.app, the Gemini API, or `GEMINI_API_KEY`. Do not enable AI Credit overages. Completed-video 格納 uses `scripts/upload_drive_local_file.py` in the same turn as the export read-back. Do not open Chrome.app for 格納. Drive originals/materials may use Google Chrome.app at `https://drive.google.com/`. The agent-controlled browser is not Antigravity CLI and must not be used as a substitute for that logged-in Google session. Do not use Google Drive for desktop.
- Use the official CapCut Web origin in the agent-controlled browser only when that adapter exists. A host editor adapter (for example ChatCut) may run the same stages for this case only when it can create a new project, inspect frames, place captions, and export. Do not mix two picture timelines. Official Holiday Twist may be generated on CapCut Text to Speech and imported as audio when the editor of record cannot emit that preset; do not offer a substitute voice or a new CapCut case. Never put CapCut, TikTok, Google, or Gemini passwords in repository files or prompts.
- When CapCut or TikTok login, CAPTCHA, 2FA, account choice, recovery, or new consent is required, stop with `HOLD_CAPCUT_LOGIN_USER_ACTION_REQUIRED`. When Antigravity CLI needs the same user action, stop with `HOLD_GEMINI_LOGIN_USER_ACTION_REQUIRED`. When Drive Web on Chrome.app needs the same user action, stop with `HOLD_DRIVE_LOGIN_USER_ACTION_REQUIRED`.
- After a usable rough edit, stop for the operator. Do not add a third or fourth AI visual-quality checkpoint.
