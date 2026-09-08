# この物理 Mac の Cursor Desktop で商品動画を作る（Ver2）

Ver2 の本番ホストは、Cursor Cloud Agent（VM）ではなく、**操作 Mac 上の Cursor Desktop Agent** です。Cloud Agent 向けの起動文は [cursor-cloud-agent-product-video.md](cursor-cloud-agent-product-video.md) に残しますが、この枝では使いません。

台本から Drive 格納までの人向け通し手順は [product-video-to-drive.md](product-video-to-drive.md) です。

## 準備

1. このリポジトリを操作 Mac で開き、枝 `v2/mac-local` を使う。
2. Cursor の実行先は **この Mac の Desktop Agent** にする。`Cloud environment` にはしない。
3. **その製品**の設定ファイル `config/product_video_settings_<MODEL>.v1.json` があることを確認する。無いなら AN-S182 を複製して型番だけ変えない。その製品用に新規作成する。
4. 承認済み素材を `.runtime/product-video-inputs/<MODEL>_コピー` へ安全に用意する。別の場所を使う場合は `PRODUCT_VIDEO_MATERIAL_ROOT` を設定する。別製品の素材を流用しない。Desktop Agent はローカル未コミットファイルを読める。素材を Git に入れない。
5. この Mac で次を実行する。

```bash
python3 .cursor/skills/produce-tiktok-product-video-portable/scripts/resolve_product_inputs.py --project-root . --product-model <MODEL> --require-materials
python3 .cursor/scripts/verify_product_video_setup.py --product-model <MODEL> --require-materials
```

`READY` なら準備完了です。素材フォルダが無いときだけ HOLD します。台本の前に全クリップの SHA や全尺視聴はしません。素材、認証情報、完成動画を Git へ含めてはいけません。

`完成・書き出しOK` のあとの既定完了は、型番名の Drive フォルダへの新規格納です。格納が確認できた案件は、**この Mac** に素材の作業コピーや完成動画の作業コピーを残しません。原本と Drive 上の格納ファイルと receipt は残します。格納前の進行中ファイルは消しません。`編集が完了した` だけでは書き出しも Drive も行いません。

ホリデーツイストは凍結行を 1 カットずつ生成します。結果カードの音声バイトを案件フォルダへ直接取り、1 カット 1 クリップで尺を合わせます。全行の一括貼りはしません。保存ダイアログは使わず、オペレーターに「保存」を押させません。結合した 1 本のナレーションのまま尺を合わせません。最終テロップは画面中央で、ChatCut では保存済みプリセット `product-video-center` を一度当てます（Dela Gothic One、白、太い黒縁、ドロップシャドウ）。はみ出す行は見た目だけ改行します。背景帯は付けません。欠けが残るカードだけサイズを下げ、TTS は再生成しません。最終カットの字幕は最後のフレームまで残します。同じ TTS を mute 複製して伸ばしません。`完成・書き出しOK` は final-QA のあとにだけ結びます。完成ファイル名の日付は**格納日**です。案件 ID やエディタ案件名の日付は使いません。`粗編集OK` のあと Path 1 / Path 2 では止めません。Drive 格納は完成動画を base64 にせず、`scripts/upload_drive_local_file.py` でローカルバイトから上げて連携で読み戻します。Chrome.app をスクショ探索しません。Google Drive デスクトップアプリは使いません。

## 台本（Gemini 3.8 Flash / Antigravity CLI）

Cursor の親モデルは切り替えない。台本は Gemini API でも Gemini.app でも Cursor 内蔵ブラウザでも Chrome でも作らない。AI Credit の上振れ課金は使わない。

1. 素材フォルダがあることだけ確認する。全件ハッシュや全尺視聴、6本ロックは台本の前にやらない。
2. キー無し brief から `render_gemini_web_prompt.py` の出力を出す。それが Gemini に渡す文面である。ルール md や lessons は足さない。

```bash
python3 .cursor/skills/produce-tiktok-product-video-portable/scripts/render_gemini_web_prompt.py --brief <task-root>/gemini-web-brief.v1.json
python3 .cursor/skills/produce-tiktok-product-video-portable/scripts/send_gemini_cli_prompt.py --prompt-file <task-root>/gemini-web-prompt.txt
```

3. この Mac の **Antigravity CLI（`agy`）** に、Google AI のサブスクと同じ Google アカウントでログインする。エージェントはログインを起動しない。
4. モデルは **Gemini 3.8 Flash**（`gemini-3.8-flash`）。別モデルなら止める。
5. 送りは `send_gemini_cli_prompt.py` だけ。空の作業ディレクトリで一発印刷する。ファイル編集はさせない。返ってきた `selected_concept`、台詞、`picture_must` / `picture_ideal` を台本パッケージへ写す。20案一覧はGeminiから取らない。オペレーターに貼らせて止めない。
6. SHA と in/out は Gemini に作らせない。`台本OK` のあと、`picture_must` で候補を絞り、選んだ範囲だけ `prove_source_range.py` で証明して取り込む。台詞差し替えは `apply_spoken_lines.py`。`台本OK` で見せるのは台詞と、フックの困りごとに対する解決案。絵の確定は `粗編集OK`。
7. `台本OK` まで止める。その後の粗編集も、同じこの Mac の Desktop Agent で続ける。

`agy` が未ログイン、または `send_gemini_cli_prompt.py` が失敗したときは探索に入らない。貼り付け文をオペレーターに渡して止めない。ログイン、CAPTCHA、2FA、資格確認だけ `HOLD_GEMINI_LOGIN_USER_ACTION_REQUIRED`。パスワードはチャットに書かない。

## Drive（格納はヘルパー。原本確認だけ Chrome Web）

Drive 格納は、書き出し読戻しの同じターンで `scripts/upload_drive_local_file.py` から行う。原本確認や素材の作業コピーが連携でできないときだけ、この Mac の **Google Chrome.app** で `https://drive.google.com/` にログインして行う。Google Drive デスクトップアプリ、ローカル同期マウント、rclone は使わない。Cursor 内蔵ブラウザは Chrome の Google ログインを共有しないので代用しない。格納に Chrome.app を開かない。16–22MB なら数十秒が正常。必要な Chrome Drive を開けないときは `HOLD_DRIVE_WEB_NOT_VERIFIED`。ログインや 2FA が必要なら `HOLD_DRIVE_LOGIN_USER_ACTION_REQUIRED`。フォルダ URL はリポジトリに書かない。Chrome をスクショ探索しない。

## ブラウザ（CapCut など）

エージェントが操作できるのは、ホストが渡す **エージェント制御ブラウザ**（Cursor 内蔵ブラウザ）です。この Mac の **Google Chrome.app** のウィンドウ、タブ、保存済みログインは使えません。CapCut / TikTok のログイン済みセッションは引き継がれません。

ログイン、CAPTCHA、2FA、アカウント選択が必要になった場合は `HOLD_CAPCUT_LOGIN_USER_ACTION_REQUIRED` で止め、ユーザーが同じデスクトップで操作します。パスワードやトークンはリポジトリにもプロンプトにも書きません。

## エディタ

1 案件の絵のタイムラインは 1 つです。CapCut Web、または同じ証拠契約を満たすホスト編集（例: ChatCut）のどちらかです。タイムラインを混ぜません。公式ホリデーツイストがホスト編集器で出せないときは、CapCut 公式 Text to Speech で音声だけ生成して戻します。映像は CapCut に入れません。

## Cursor の Agent へ渡す依頼

型番・設定・素材を、その案件の値に置き換えて渡します。

```text
/produce-tiktok-product-video-portable

本番ホストはこの物理 Mac の Cursor Desktop Agent です。Cloud Agent / Cloud VM では作らないでください。

製品型番は<MODEL>です。
商品設定はconfig/product_video_settings_<MODEL>.v1.jsonです。
素材はPRODUCT_VIDEO_MATERIAL_ROOT、未設定なら.runtime/product-video-inputs/<MODEL>_コピーです。

新しいcase ID、task root、workflow state、別の新規エディタprojectを作成してください。
既存動画、既存project、過去export、Drive原本、過去payload、過去receiptを変更・上書きしないでください。

通常確認は台本OK、粗編集OK、完成・書き出しOKの3種類だけです。
Checkpoint 1 の台本は、このMacのログイン済みAntigravity CLI（agy --print）で、Gemini 3.8 Flashに作らせてください。Gemini.appとGemini APIは使わないでください。
Cursorの親モデル切替とGemini APIは使わないでください。
完成動画の格納はscripts/upload_drive_local_file.pyを使ってください。Google Driveデスクトップアプリは使わないでください。
完成・書き出しOKのあと、型番名のDriveフォルダへ新規ファイルとして格納してください。
まずCheckpoint 1の台本OKまで進めて停止してください。
```

AN-S182 の例:

```text
製品型番はAN-S182です。
商品設定はconfig/product_video_settings_AN-S182.v1.jsonです。
素材は.runtime/product-video-inputs/AN-S182_コピーです。
```
