# CursorデスクトップアプリからCloud Agentを使う

このフォルダには、CursorデスクトップアプリのCloud Agentが認識する商品動画スキルと実行環境があります。

## 準備

1. このフォルダの変更をGitリポジトリへ反映する。Cloud AgentはMac上の未反映ファイルを直接読めない。
2. CursorデスクトップアプリでこのGitリポジトリを選ぶ。
3. Agent画面の実行先を`Cloud environment`にする。
4. 承認済み素材をCloud Agentの`.runtime/product-video-inputs/AN-S182_コピー`へ安全に用意する。別の場所を使う場合は`PRODUCT_VIDEO_MATERIAL_ROOT`を設定する。
5. Cloud Agent内で次を実行する。

```bash
python3 .cursor/scripts/verify_product_video_setup.py --require-materials
```

`READY`なら準備完了です。素材がない、8件未満、壊れている、またはmedia SHA-256が8種類未満なら、既存物を変更せずHOLDします。素材、認証情報、完成動画をGitへ含めてはいけません。

`完成・書き出しOK` と格納が確認できた案件は、Cloud VM と操作Macに素材の作業コピーや完成動画の作業コピーを残しません。原本とDrive上の格納ファイルとreceiptは残します。格納前の進行中ファイルは消しません。

## CursorのAgentへ渡す依頼

```text
/produce-tiktok-product-video-portable

製品型番はAN-S182です。
商品設定はconfig/product_video_settings_AN-S182.v1.jsonです。
素材はPRODUCT_VIDEO_MATERIAL_ROOTのAN-S182_コピーです。

新しいcase ID、task root、workflow state、別の新規CapCut Web projectを作成してください。
既存動画、既存CapCut project、過去export、Drive原本、過去payload、過去receiptを変更・上書きしないでください。

通常確認は台本OK、粗編集OK、完成・書き出しOKの3種類だけです。
まずCheckpoint 1の台本OKまで進めて停止してください。
```

## CapCut操作について

Cloud AgentがChromeまたはCapCut Webを実際に操作・確認できる連携を持つ場合だけ、編集工程へ進みます。連携がない場合は、台本と検証済みhandoffまでは作れても、実編集を完了したとは扱いません。

ログイン、CAPTCHA、2FA、アカウント選択が必要になった場合はHOLDし、CursorデスクトップアプリのDesktop操作へユーザーが切り替えます。Agentが音声を確実に聴けない場合も、全編の聴感確認を保留したままにし、確認済みだと推測しません。
