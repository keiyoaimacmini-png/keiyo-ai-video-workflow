# Cursor Desktop（このMac）で台本を作り直す

## 「このMac」が灰色で押せないとき

今見ている会話が雲（Cloud）で始まっていると、**このMacは選べません。壊れではありません。** 途中から切り替えられない、という仕組みです。緑の Set up Environment も押さなくて大丈夫です（雲の準備ボタンです）。

台本は作り直して構いません。やり方はこれだけです。

1. コードが見える、いつもの Cursor 画面を開く（この雲の会話ではなくてよい）
2. **新しい** Agent のチャットを始める
3. そこに下の文章を貼って送る

```text
/produce-tiktok-product-video-portable

このMacで、新しい台本から始めてください。
雲の会話は使わないでください。

製品はAN-S182です。
新しい案件として、台本OKまで進めて止めてください。
台本は、このMacのChromeのGeminiで作ってください。
```

新しい会話でも灰色なら、Agents（雲）の画面ではなく、フォルダが開いているエディタ側のチャットを使ってください。そちらがこのMacで動きます。

---

Cloud Agent の Chrome ログインは Mac へ移りません。続きは **このマシン** の Cursor Desktop で、新しい案件として動かします。

正本は `.cursor/skills/produce-tiktok-product-video-portable/SKILL.md` です。全体地図は [product-video-to-drive.md](product-video-to-drive.md) です。

## 使わないもの

- Cloud VM の Gemini / CapCut / Drive タブを「ログイン済み」の証拠にすること
- クッキー、トークン、ブラウザプロファイル、API キーのコピーやチャット貼り付け
- 完成済み案件、既存 payload、既存エディタ project の再開や上書き
- Gemini API（`GEMINI_API_KEY`）

## 開始手順

1. このリポジトリを Git で更新する。Cloud Agent の未プッシュ作業は Mac から読めない。
2. Cursor デスクトップアプリでこのリポジトリを開く。
3. Agent の実行先を **このマシン** にする。`Cloud environment` のままにしない。
4. 素材をこのMacへ用意する。既定は `.runtime/product-video-inputs/<MODEL>_コピー`。別場所なら `PRODUCT_VIDEO_MATERIAL_ROOT`。Git に入れない。
5. このMacで確認する。

```bash
python3 .cursor/skills/produce-tiktok-product-video-portable/scripts/resolve_product_inputs.py --project-root . --product-model <MODEL> --require-materials
python3 .cursor/scripts/verify_product_video_setup.py --product-model <MODEL> --require-materials
```

`READY` 以外なら案件を作らない。

## Agent へ渡す依頼

```text
/produce-tiktok-product-video-portable

この物理マシン（Cursor Desktop）で続けてください。
実行先は Cloud environment にしないでください。
Cloud VM の Chrome セッションは使わないでください。

製品型番は<MODEL>です。
商品設定はconfig/product_video_settings_<MODEL>.v1.jsonです。
素材はPRODUCT_VIDEO_MATERIAL_ROOT、未設定なら.runtime/product-video-inputs/<MODEL>_コピーです。

新しいcase ID、task root、workflow state、別の新規エディタprojectを作成してください。
既存動画、既存project、過去export、Drive原本、過去payload、過去receiptを変更・上書きしないでください。

Checkpoint 1 の台本は公式 Gemini Web（https://gemini.google.com/）をこのMacのChromeで開き、新規チャットで下書きしてください。
3.8 Flash が見えるときはそれを、無ければ表示中の Flash を選んでください。
素材の実フレーム確認のあと、scripts/render_gemini_web_prompt.py の出力だけを貼ってください。
Gemini API と API キーは使わないでください。
SHA と in/out は Gemini に作らせず、実フレーム確認のあとスキルが結んでください。

通常確認は台本OK、粗編集OK、完成・書き出しOKの3種類だけです。
まずCheckpoint 1の台本OKまで進めて停止してください。
```

AN-S182 の例:

```text
製品型番はAN-S182です。
商品設定はconfig/product_video_settings_AN-S182.v1.jsonです。
素材は.runtime/product-video-inputs/AN-S182_コピーです。
```

## Gemini Web

Agent がこのMacの Chrome を操作できるときは、公式オリジンだけを開く。操作できないときは `HOLD_GEMINI_WEB_NOT_VERIFIED` で止まり、task に残した貼り付け文をオペレーターがこのMacの Chrome へ貼る。ログインや 2FA は `HOLD_GEMINI_LOGIN_USER_ACTION_REQUIRED`。パスワードはチャットに書かない。

## 編集

1 案件の絵のタイムラインは 1 つ。このMacでブラウザまたはホスト編集アダプタが証拠契約を満たすときだけ、粗編集へ進む。満たさないときは台本と検証済み handoff までで止め、完了したとは扱わない。
