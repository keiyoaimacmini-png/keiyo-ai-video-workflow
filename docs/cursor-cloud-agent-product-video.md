# CursorデスクトップアプリからCloud Agentを使う

このフォルダには、CursorデスクトップアプリのCloud Agentが認識する商品動画スキルと実行環境があります。製品型番と素材は案件ごとに変わります。AN-S182はその一例です。

台本から Drive 格納までの人向け通し手順は [product-video-to-drive.md](product-video-to-drive.md) です。

## 準備

1. このフォルダの変更をGitリポジトリへ反映する。Cloud AgentはMac上の未反映ファイルを直接読めない。
2. CursorデスクトップアプリでこのGitリポジトリを選ぶ。
3. Agent画面の実行先を`Cloud environment`にする。
4. **その製品**の設定ファイル `config/product_video_settings_<MODEL>.v1.json` があることを確認する。無いならAN-S182を複製して型番だけ変えない。その製品用に新規作成する。
5. 承認済み素材を `.runtime/product-video-inputs/<MODEL>_コピー` へ安全に用意する。別の場所を使う場合は `PRODUCT_VIDEO_MATERIAL_ROOT` を設定する。別製品の素材を流用しない。
6. Cloud Agent内で次を実行する。

```bash
python3 .cursor/skills/produce-tiktok-product-video-portable/scripts/resolve_product_inputs.py --project-root . --product-model <MODEL> --require-materials
python3 .cursor/scripts/verify_product_video_setup.py --product-model <MODEL> --require-materials
```

`READY`なら準備完了です。素材がない、8件未満、壊れている、またはmedia SHA-256が8種類未満なら、既存物を変更せずHOLDします。素材、認証情報、完成動画をGitへ含めてはいけません。

この Cursor Cloud 運用の台本下書きは公式 Gemini Web（`https://gemini.google.com/`）のチャットです。CapCut Web と同じく Chrome の既存ログインを使い、API キーは使いません。ログインや 2FA が必要なら `HOLD_GEMINI_LOGIN_USER_ACTION_REQUIRED` で止まり、Cursor Desktop から操作します。

`完成・書き出しOK` のあとの既定完了は、型番名のDriveフォルダへの新規格納です。格納が確認できた案件は、Cloud VM と操作Macに素材の作業コピーや完成動画の作業コピーを残しません。原本とDrive上の格納ファイルとreceiptは残します。格納前の進行中ファイルは消しません。`編集が完了した` だけでは書き出しもDriveも行いません。

一括のホリデーツイスト生成では、各台本行のあいだに測った無音を入れてから、その無音でシーンごとに切ります。結合した1本のナレーションのまま尺を合わせません。最終テロップは画面中央で、案件エディタの字幕プログラムを使い、はみ出す行は見た目だけ改行します。`粗編集OK` のあと Path 1 / Path 2 では止めません。Drive 格納は完成動画を base64 にせず、ローカルバイトまたはログイン済み画面アップロード 1 回です。

## CursorのAgentへ渡す依頼

型番・設定・素材を、その案件の値に置き換えて渡します。

```text
/produce-tiktok-product-video-portable

製品型番は<MODEL>です。
商品設定はconfig/product_video_settings_<MODEL>.v1.jsonです。
素材はPRODUCT_VIDEO_MATERIAL_ROOT、未設定なら.runtime/product-video-inputs/<MODEL>_コピーです。

新しいcase ID、task root、workflow state、別の新規エディタprojectを作成してください。
既存動画、既存project、過去export、Drive原本、過去payload、過去receiptを変更・上書きしないでください。

通常確認は台本OK、粗編集OK、完成・書き出しOKの3種類だけです。
完成・書き出しOKのあと、型番名のDriveフォルダへ新規ファイルとして格納してください。
まずCheckpoint 1の台本OKまで進めて停止してください。
```

AN-S182の例:

```text
製品型番はAN-S182です。
商品設定はconfig/product_video_settings_AN-S182.v1.jsonです。
素材は.runtime/product-video-inputs/AN-S182_コピーです。
```

## エディタ操作について

Cloud AgentがChromeまたはCapCut Webを実際に操作・確認できる連携を持つ場合、または同じ証拠契約を満たすホスト編集アダプタがある場合だけ、編集工程へ進みます。連携がない場合は、台本と検証済みhandoffまでは作れても、実編集を完了したとは扱いません。1案件の絵のタイムラインは1つです。公式ホリデーツイストがホスト編集器で出せないときは、CapCut公式Text to Speechで音声だけ生成して戻します。

ログイン、CAPTCHA、2FA、アカウント選択が必要になった場合はHOLDし、CursorデスクトップアプリのDesktop操作へユーザーが切り替えます。Agentが音声を確実に聴けない場合も、全編の聴感確認を保留したままにし、確認済みだと推測しません。Checkpoint 3ではエディタリンクと聴感チェックリストを同じ停止メッセージに載せ、`音声確認OK`は作りません。
