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

`READY` なら準備完了です。素材がない、8件未満、壊れている、または media SHA-256 が 8 種類未満なら、既存物を変更せず HOLD します。素材、認証情報、完成動画を Git へ含めてはいけません。

`完成・書き出しOK` のあとの既定完了は、型番名の Drive フォルダへの新規格納です。格納が確認できた案件は、**この Mac** に素材の作業コピーや完成動画の作業コピーを残しません。原本と Drive 上の格納ファイルと receipt は残します。格納前の進行中ファイルは消しません。`編集が完了した` だけでは書き出しも Drive も行いません。

一括のホリデーツイスト生成では、各台本行のあいだに測った無音を入れてから、その無音でシーンごとに切ります。結合した 1 本のナレーションのまま尺を合わせません。最終テロップは画面中央で、案件エディタの字幕プログラムを使い、はみ出す行は見た目だけ改行します。`粗編集OK` のあと Path 1 / Path 2 では止めません。Drive 格納は完成動画を base64 にせず、ローカルバイトまたはログイン済み画面アップロード 1 回です。

## ブラウザ

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
完成・書き出しOKのあと、型番名のDriveフォルダへ新規ファイルとして格納してください。
まずCheckpoint 1の台本OKまで進めて停止してください。
```

AN-S182 の例:

```text
製品型番はAN-S182です。
商品設定はconfig/product_video_settings_AN-S182.v1.jsonです。
素材は.runtime/product-video-inputs/AN-S182_コピーです。
```
