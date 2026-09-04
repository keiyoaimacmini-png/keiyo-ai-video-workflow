# 商品動画スキル：台本から Drive 格納まで

Cursor で 1 本の TikTok 商品動画を新規に作り、型番名の Drive フォルダへ新規格納するまでの流れです。実行の正本は `.cursor/skills/produce-tiktok-product-video-portable/SKILL.md` です。この文書は人向けの地図です。

製品型番・設定・素材・Drive フォルダ名は案件ごとに変わります。AN-S182 はその一例です。

## 使わないもの

- OpusClip / Eddie 向けの別手順（リポジトリ未追跡の下書きを正本にしない）
- 既存案件の台本・payload・ChatCut/CapCut プロジェクト・書き出し・Drive 原本の再利用や上書き
- Git への素材・完成動画・Drive ID・認証情報の投入
- 投稿・公開・クレジット購入・結果不明な書き出し/アップロードの再実行

## 案件ごとの入力

| 入力 | 決め方 |
| --- | --- |
| 製品型番 | 依頼で指定した `AN-…`。別案件の型番を推測しない |
| 設定 | 必ず `config/product_video_settings_<MODEL>.v1.json` |
| 素材 | `PRODUCT_VIDEO_MATERIAL_ROOT`、未設定なら `.runtime/product-video-inputs/<MODEL>_コピー` |
| Drive 親フォルダ | タイトルが検証済み型番と一致するフォルダ 1 つ（完成動画の直下など、案件で確定した親） |
| 案件 | 新しい case ID、`outputs/<case-id>/`、新しいエディタ project |

開始前:

```bash
python3 .cursor/skills/produce-tiktok-product-video-portable/scripts/resolve_product_inputs.py --project-root . --product-model <MODEL> --require-materials
python3 .cursor/scripts/verify_product_video_setup.py --product-model <MODEL> --require-materials
```

`READY` 以外なら案件を作らず止まる。

この Cursor Cloud 運用では台本下書きに Gemini 3.8 Flash API（`gemini-3.8-flash`）を使う。キーは Cloud Agent 環境の `GEMINI_API_KEY` だけ。Google AI Studio 側にあるだけでは、この VM からは使えない。チャットや Git に貼らない。

## 通常確認は 3 つだけ

| 確認 | 許可すること | 許可しないこと |
| --- | --- | --- |
| `台本OK` | 新規エディタ project での粗視覚編集 | TTS、クレジット、仕上げ、書き出し、Drive |
| `粗編集OK` | 仕上げ、ホリデーツイスト TTS（計画どおりの初回） | 凍結した台詞・素材範囲の変更、クレジット購入 |
| `完成・書き出しOK` | 新規書き出し 1 回と、既定では Drive 新規格納 1 回 | 投稿、上書き、不明結果の再実行 |

`編集が完了した` や `格納して` は `完成・書き出しOK` の代わりにならない。

## 流れ

```text
準備
  → PREFLIGHT（素材点検・20案比較・台本パッケージ）
  → SCRIPT_PREPARED（payload 検証）
  → SCRIPT_REVIEW  …… 台本OK
  → ROUGH_EDIT（新規エディタ、1テロップ1素材、TTSなし）
  → ROUGH_REVIEW  …… 粗編集OK
  → FINISHING（中央テロップ、ホリデーツイスト、3レイヤ揃え）
  → FINAL_QA（全カット検証・再生・再読込）
  → FINAL_REVIEW  …… 完成・書き出しOK
  → EXPORT_AND_DELIVERY（書き出し1回 → Drive新規格納と読戻し）
  → COMPLETE
  → この案件のローカル作業コピー削除（第4の確認ではない）
```

1 案件の編集正本は 1 つ。CapCut Web か、フレーム確認・テロップ・書き出しができるホスト編集（例: ChatCut）のどちらか。タイムラインを混ぜない。公式ホリデーツイストが編集正本で出せないときは、CapCut 公式 Text to Speech で音声だけ作り、映像は入れずに編集正本へ戻す。代替ボイスや新規 CapCut 案件は作らない。公式 CapCut テロップテンプレは任意。

ナレーションは公式ホリデーツイスト。一括生成するときは凍結行のあいだに空行だけを入れ、ダウンロード後に測った無音で 1 シーン 1 クリップに切る。

最終テロップは画面中央。案件エディタの字幕プログラム（ChatCut Caption Cards または CapCut ネイティブ）を使う。モーションを視聴者向け字幕にしない。はみ出す行は句読点や意味の切れ目で見た目だけ改行し、文字は変えない。

## 時間を使わないこと

- `粗編集OK` のあと、代替ボイス（Path 1）や新規 CapCut 案件（Path 2）を出さない。ホリデーツイストは編集正本で出すか、CapCut 公式 TTS の音声だけを戻す。
- 映像を CapCut に入れ直さない。完成動画を Drive ツールの base64 にしない。書き出しを Downloads へコピーしない（ピッカーが `out/` を見られないときだけ）。
- Checkpoint 3 で `音声確認OK` を増やさない。聴けないときは同じ停止メッセージに聴感チェックリストを載せる。
- タブの所属が不明でも Drive 読戻し後の `COMPLETE` は止めない。Mac の作業コピー確認はまず Finder のダウンロード。

## Drive 格納

既定の完了は Drive 格納です。ローカル `out/` は格納ではない。

1. `完成・書き出しOK` が、いまの最終 QA レシートに結び付いていること。
2. その時点の JST 日付と型番の台帳を読んで序数を決める。①②は推測しない。
3. 書き出しファイル名は `YYYY_MMDD_<MODEL>_AI作成①.mp4` 形式。同じ名前があれば止める。
4. 書き出しは 1 回。受付や進捗だけでは成功としない。
5. 検証済み型番と同名の親フォルダを 1 つ特定し、ローカルバイトから新規ファイルだけ作る。完成動画をツール引数の base64 にしない。ローカルパスで渡せないときは、証明済み親へのログイン済み Drive 画面アップロード 1 回のあと、連携で読み戻す。同名の空ファイルは作らない。
6. 名前・MIME・バイト数・親スコープ・時刻を読み戻す。Drive ID は Git に書かない。
7. `COMPLETE` のあと、格納済みのこの案件だけ作業コピーを消す。Mac ではまず Finder のダウンロードに完成ファイル名があるかを見る。Cloud だけで作った案件ではリポジトリ内 `outputs/` や `out/` は無いことが多い。

```bash
python3 .cursor/skills/produce-tiktok-product-video-portable/scripts/purge_local_working_media.py --project-root . --task-root outputs/<case-id> --case-id <case-id>
python3 .cursor/skills/produce-tiktok-product-video-portable/scripts/purge_local_working_media.py --project-root . --task-root outputs/<case-id> --case-id <case-id> --execute --i-confirm-destination-stored
```

原本、Drive 上の格納ファイル、JSON receipt、設定、進行中の別案件は消さない。Cloud VM で消したあとは操作 Mac でも同じ相対パスを消す。

`export_only` は、依頼が明示的にローカルのみ／書き出しのみのときだけ。その場合も作業コピーを格納扱いにしない。

## Git に入れないもの

`.gitignore` のとおり、次はリポジトリに入れない。

- `.runtime/` の素材
- `outputs/` の案件作業（台本パッケージ、payload、evidence、書き出し、Drive receipt）
- `footage/` `voice/` `out/` `exports/` `downloads/`
- 認証、cookie、token、アカウント、生の Drive ID

Git に載せるのはスキル、検証器、契約、設定ファイル、メディアを含まないゴールデン基準です。

## 別 PC で同じ流れを使う

1. この非公開リポジトリを clone する。チャットにパスワードやトークンを貼らない。
2. その PC の製品型番用設定と素材コピーを用意する。
3. 上の `READY` 確認を通す。
4. Cursor で `/produce-tiktok-product-video-portable` を起動し、まず `台本OK` まで進めて止める。

依頼例:

```text
/produce-tiktok-product-video-portable

製品型番は AN-S182 です。
商品設定は config/product_video_settings_AN-S182.v1.json です。
素材は .runtime/product-video-inputs/AN-S182_コピー です。

新しい case ID、task root、workflow state、別の新規エディタ project を作成してください。
既存動画、既存 project、過去 export、Drive 原本、過去 payload、過去 receipt を変更・上書きしないでください。

通常確認は 台本OK、粗編集OK、完成・書き出しOK の 3 種類だけです。
完成・書き出しOK のあと、型番名の Drive フォルダへ新規ファイルとして格納してください。
まず Checkpoint 1 の台本OK まで進めて停止してください。
```

## スキル内の参照

| 役割 | 場所 |
| --- | --- |
| 入口 | `.cursor/skills/produce-tiktok-product-video-portable/SKILL.md` |
| 不変条件 | `references/core-invariants.md` |
| 状態機械 | `references/workflow-state-contract.md` |
| ホスト能力 | `references/host-adapter-contract.md` |
| 製品・素材・Drive | `references/product-and-material-contract.md` |
| 3 確認 | `references/checkpoint-contract.md` |
| 格納 | `stages/06-deliver.md` |
| Cloud Agent 起動 | [cursor-cloud-agent-product-video.md](cursor-cloud-agent-product-video.md) |
