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
python3 .cursor/skills/product-video/scripts/prove_material_videos.py --material-root <resolved material_root>
python3 .cursor/skills/product-video/scripts/run_self_test.py
```

- Settings path is always `config/product_video_settings_<MODEL>.v1.json`. For AN-S182 that file is pinned by SHA-256; do not infer or replace it. For any other model, add that model's own file instead of copying AN-S182.
- Material root is `PRODUCT_VIDEO_MATERIAL_ROOT` when set, otherwise `.runtime/product-video-inputs/<MODEL>_コピー`. A folder is not enough; PREPARE requires at least one regular non-zero video file under that root.
- Stages chain automatically: PREPARE → SCRIPT → (wait for `案Nで台本OK`) → NARRATION → ASSEMBLY → ROUGH_EDIT → WAITING_FOR_OPERATOR → (wait for `完成・格納してください`) → DELIVERY → COMPLETE.
- Usual operator input is only `/product-video`, exact `案Nで台本OK`, and exact `完成・格納してください`.
- Before a new case, and when resuming a held case, run `product-video/scripts/run_preflight.py` (materials, Gemini text-only one-shot, Chrome CDP + Playwright MCP, ChatCut; Drive OAuth/folder is deferred). Blocking failures HOLD start. Drive-only failure keeps start-time preflight `READY` with `delivery_ready: false`; Drive is required only at DELIVERY, before export. Do not write media, generate TTS, or spend credits in preflight. Transient connection failures retry up to 3 times without asking the operator. If several blocking checks fail, report them once as **開始前に直すこと**.
- Do not ask Continue / Proceed between automatic stages. Do not require `粗編集OK`. Do not run an AI final visual-quality review.

## Gemini 台本（Antigravity CLI。Cursor のモデルは切り替えない）

- 台本案は、この Mac のログイン済み **Antigravity CLI（`agy --print`）** に、**Gemini 3.8 Flash** で作らせる。Cursor の親モデル切替、外部モデル枠、Gemini API、`GEMINI_API_KEY`、Gemini.app、Google Chrome.app、エージェント制御ブラウザは使わない。AI Credit の上振れ課金は使わない。
- 使用モデルは **`gemini-3.8-flash`**。Auto / Pro / 別の Flash には落とさない。違うモデルなら `HOLD_GEMINI_MODEL_NOT_VERIFIED`。`agy` が無い、一発印刷が失敗する、枠が尽きた、ファイルを書き始めた場合は `HOLD_GEMINI_CLI_NOT_VERIFIED`。
- 送りは `product-video/scripts/render_script_prompt.py` の出力を `produce-tiktok-product-video-portable/scripts/send_gemini_cli_prompt.py` で送る。プロンプト本文を手で書き換えない。ヘルパーが HOLD したら探索に入らずその HOLD で止める。貼り付け文をオペレーターに渡して止めない。ログイン、CAPTCHA、2FA、アカウント選択だけ `HOLD_GEMINI_LOGIN_USER_ACTION_REQUIRED`。オペレーターは Terminal で `agy` を起動して Google ログインする。エージェントはログインを起動しない。
- 採用は exact `案Nで台本OK` のみ。別の言い回しを承認に変換しない。凍結後は SCRIPT LINE == NARRATION == TELOP。言い換え・短縮・句読点変更をしない。
- 素材の SHA と in/out は Gemini に作らせない。台本の前に全件ハッシュや全尺視聴はしない。選んだファイルの選んだ範囲だけ `prove_source_range.py` で証明する。ASSEMBLY は ChatCut へ置く前に、商品別 `.runtime/product-video-material-index/<MODEL>.v1.json` とナレーションの `target_duration_seconds`（playbackRate 1.2 後）で `available_duration >= target` を判定する。mtime/size が変わった素材 md / source だけ index を更新する。毎案件の全動画再視聴・再解析はしない。`source_in` / `source_out` がある候補はその range 尺。full clip 候補は md の source duration。足りない素材はランキング前に除外する。履歴でも尺不足なら採用しない。ChatCut 仮置きや案件ごとの再計測はしない。尺を通った候補だけを、セリフ意味 → 必要尺 → Gemini situation → approved-shot history → 前後の同じ絵面回避の順で選ぶ。セリフ意味は sidecar の situation 完全一致、sidecar tags、分類フォルダ名、商品単位の semantic aliases（`.runtime/product-video-material-index/<MODEL>.semantic-aliases.v1.json` / `config/product_video_material_aliases_<MODEL>.v1.json`）で判定する。日本語文全体の完全一致は要求しない。台本ごとに sidecar や aliases を書き換えない。全カットを `edit-plan.json` に書いてから ChatCut へ入る。テロップの表示改行も配置前に確定する。全素材の再解析や AI 画質採点はしない。
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
- Do not open a pull request, publish an artifact, post, send externally, start a Pro contract, buy extra CapCut credit, retry an unknown export/upload, overwrite, or delete originals, Drive objects, receipts, or another case unless the user separately authorizes that exact action. Confirming an existing-balance CapCut `Credits will be consumed` dialog (Got it) is not a new purchase.
- Standing completion is Drive 格納: after exact `完成・格納してください`, export once and, in that same turn, create one new file in the Drive folder titled with this product model in exact case. Create that file with `scripts/upload_drive_local_file.py` from local bytes; do not inline the completed video as base64. Do not open Chrome.app for 格納. Require exact new-file read-back. COMPLETE only after Drive verification.
- After stage `COMPLETE` and verified 格納, record this case's final timeline source/range into `.runtime/product-video-approved-shots/<MODEL>.v1.json`, then purge this case's local working media **on this Mac** through `scripts/purge_local_working_media.py`. Never purge before verified delivery. Default is dry-run; execute only with `--execute --i-confirm-destination-stored`. Do not delete `.runtime/product-video-inputs`, `.runtime/product-video-approved-shots`, `.runtime/product-video-material-metadata`, or `.runtime/product-video-material-index`.

## 完了後のローカル削除

- `完成・格納してください` と格納が済んだ案件だけ、**この Mac** からその案件の作業用 media（`outputs/<case>` の TTS・一時ファイル・ローカル完成動画の作業コピー）を消す。共有素材ライブラリ `.runtime/product-video-inputs` と採用ショット履歴 `.runtime/product-video-approved-shots` は消さない。
- まず Finder のダウンロードに完成ファイル名があるかを見る。続けてリポジトリ内 `outputs/` や `out/` を確認する。無いコピーは失敗にしない。
- 原本、Drive上の格納ファイル、Google Driveデスクトップの同期ミラー、JSONのreceipt、設定、進行中の別案件、`.runtime/product-video-inputs` 配下の再利用素材、`.runtime/product-video-approved-shots` の採用履歴は消さない。同期ミラーを Finder から消すと Drive 上の原本も消える。
- 格納前、またはローカルが唯一の完成コピーのときは消さない。進行中の本編ファイルは消さない。

## ナレーション（session 1回 + queue 連続生成）

- 編集上の再生速度は常に **1.2倍速**。速度選択アルゴリズムは使わない。CapCut 生成時に 1.2 を要求しない。ChatCut の音声クリップ `playbackRate` に 1.2 を付ける。
- 公式ホリデーツイストが案件の編集正本で出せないときは、CapCut 公式 Text to Speech で凍結行を **1カット分のセリフごとに** 生成し、原音だけ編集正本へ戻す。映像は CapCut に入れない。ChatCut 代替ボイスや新規 CapCut 案件は出さない。通常経路は起動済みの Google Chrome.app へ、このプロジェクトの Playwright MCP（`--cdp-endpoint=chrome`）で接続する。詳細は `.cursor/skills/product-video/references/capcut-chrome-mcp.md`。`cursor-ide-browser` や拡張機能方式へ自動で戻さない。
- NARRATION 開始時に Chrome / MCP / CapCut TTS ページ / Holiday Twist / 入力欄 / credit policy を **1回だけ** 確認する。`narration_queue.py` の残りカットを同じ session で連続処理する。成功したカットをチャット報告せず次へ進む。workflow dispatch へ戻らない。LLM で新しい計画を作らない。session が失われたときだけ接続復旧を最大3回。カットごとに MCP 再探索、Chrome preflight、ページ再探索、Holiday Twist 再選択、voice ID 再解決はしない。全カット完了後に一度だけ `narration-manifest.json` を書いて ASSEMBLY へ進む。
- 既存 CapCut 残高から今回の生成分を消費する確認（`Credits will be consumed`、必要クレジット数、Cancel / Got it、月額・年額料金なし、無料体験なし、決済フォームなし、追加購入なし）は Got it で続行してよい。本文に「Pro」とあることだけを理由に止めない。Pro 月額・年額契約、無料体験、追加クレジット購入、自動チャージ、新しい決済、契約変更は自動承認しない。区別できなければ HOLD。
- 貼るのはそのカットの凍結行だけ。全行を空行区切りで一括貼りしない。
- 生成前にテキスト欄を全置換し、読み戻しが凍結行と完全一致してから生成する。結果カードの `video`/`audio` currentSrc を `scripts/capture_capcut_result_audio.py` で案件の TTS 作業ディレクトリへ直接保存する。原音の実再生時間を記録する。原音を 1.2 倍加工済みとは記録しない。
- 1カット1クリップとして編集正本へ戻し、ChatCut でクリップ速度 1.2 を付けたあとの区間に映像とテロップを合わせる。

## テロップ

- 最終テロップは画面中央。案件エディタの字幕プログラム（ChatCut Caption Cards または CapCut ネイティブ）を使う。モーションを視聴者向け字幕にしない。
- ChatCut では保存済みユーザープリセット `product-video-center` を一度 `preset_apply` する。案件ごとに太字・縁を作り直さない。背景帯は付けない。
- テロップ文言は凍結行と完全一致。表示用改行は `edit-plan.json` の `caption_visual_wrap` を配置前に使う。単語途中、助詞だけ次行、数字と単位、UV / UPF / チタンシルバーなどの語分断、1文字だけの行を避ける。ChatCut へ置いてから改行位置を考えない。文字の追加・削除・並べ替えはしない。
- 太字の見出しフォント（Dela Gothic One）と白い文字、太い黒縁、ドロップシャドウで目立たせる。背景帯は付けない。

## 計測

案件の `timing.json` にだけ自動記録する。チャットへ途中報告しない。記録するのは SCRIPT 実処理時間、NARRATION 開始〜終了、カット数、平均 TTS 秒/cut、ASSEMBLY plan 作成時間、ChatCut 配置時間、人間の素材差し替え数、Export/Drive 時間。

## Cursor Desktop browser and human handoff

- Production host is this Mac's Cursor Desktop Agent. Do not use Cloud Agent for picture, captions, export, or Drive 格納.
- Script drafts use this Mac's logged-in Antigravity CLI (`agy --print`) at Gemini 3.8 Flash. The agent sends the prompt and reads the dialogue in the same turn. Do not leave a paste for the operator. Do not use Gemini.app, the Gemini API, or `GEMINI_API_KEY`. Do not enable AI Credit overages. Completed-video 格納 uses `scripts/upload_drive_local_file.py` in the same turn as the export read-back. Do not open Chrome.app for 格納. Drive originals/materials may use Google Chrome.app at `https://drive.google.com/`. The agent-controlled browser is not Antigravity CLI and must not be used as a substitute for that logged-in Google session. Do not use Google Drive for desktop.
- Official Holiday Twist TTS uses this Mac's already-running Google Chrome.app through the project's Playwright MCP (`--cdp-endpoint=chrome`). Follow `.cursor/skills/product-video/references/capcut-chrome-mcp.md`. Do not fall back to `cursor-ide-browser` or an extension adapter. If that MCP cannot attach, retry up to 3 times, then stop with `HOLD_CAPCUT_CHROME_MCP_UNAVAILABLE`. A host editor adapter (for example ChatCut) may run picture, captions, and export for this case only when it can create a new project, inspect frames, place captions, and export. Do not mix two picture timelines. Official Holiday Twist may be generated on CapCut Text to Speech and imported as audio when the editor of record cannot emit that preset; do not offer a substitute voice or a new CapCut case. Never put CapCut, TikTok, Google, or Gemini passwords in repository files or prompts.
- When CapCut or TikTok login, CAPTCHA, 2FA, account choice, recovery, or new consent is required, stop with `HOLD_CAPCUT_LOGIN_USER_ACTION_REQUIRED`. When Antigravity CLI needs the same user action, stop with `HOLD_GEMINI_LOGIN_USER_ACTION_REQUIRED`. When Drive Web on Chrome.app needs the same user action, stop with `HOLD_DRIVE_LOGIN_USER_ACTION_REQUIRED`.
- After a usable rough edit, stop for the operator. Do not add a third or fourth AI visual-quality checkpoint.
