# CHANGES

入力の `zip/readable-video-skills-latest/` を読み取り専用で参照し、共通部分だけを `out/common/` に再構成した。元ファイル、Python、JSON、リポジトリは変更していない。

## 00_はじめに.md

- 製品名・案件ブランチ名を外し、共通スキルと Obsidian `product-video-materials/<型番>/` の製品ノートを読む順番へ一般化した。
- 製品ノートを「台本ルール・商品事実・設定」として扱い、共通ルールを追加で適用する関係を明記した。

## 01_共通_product-video司令塔.md

- `完了の受理条件（司令塔）` を新設した。stage status や完了報告だけで受理せず、失敗台帳の「確認する証拠」、再発防止条件、製品ノートが台本生成・検査へ反映された証拠を確認する仕組みにした。
- Gate A〜D の判定本文を削り、02 と `placement-gates.md` への参照だけにした。ゲートの正本を02へ一本化した。
- dated folder 命名を01の `Paths` に一本化した。各04にあった同じ説明は削った。
- Drive OAuth・ログイン・アップロード・読戻し・purgeの詳細を04_deliveryの正本へ寄せ、01には責務の参照だけを残した。
- preflight/dispatchの実行例は `${PROJECT_ROOT}/.cursor/skills/...` 形式に寄せ、重複していた補助パス例を削った。Drive-onlyの開始警告はREADYを維持し、DELIVERYで再確認する意味を残した。
- `PROJECT_ROOT` を使う既存のコマンドパス形式、`# /product-video`、frontmatterの `name: product-video`、承認フレーズは維持した。

## 02_共通_配置ゲート.md

- 過去の特定案件ID・案件固有の失敗説明を削除した。
- 代わりに、過去の失敗は `product-video-materials/共通/失敗台帳.md` へ登録し、再発防止条件を司令塔の受理条件にする共通ルールを追加した。
- Gate A〜Dの判定・停止・順序・heartbeatをこのファイルに集約した。音声デコード、visual match、音声先行配置、30秒超のheartbeatの意味は維持した。
- TTS再生成先の工程名を特定の論理名から共通の narration queue へ一般化した。

## 03_共通_Gemini台本テンプレ.md

- 速度を全製品共通の1.2倍速へ固定した。製品ノートや設定側の別倍率を台本へ持ち込まない。
- 価格・売価・金額をセリフ、テロップ、CTAへ含めない共通ルールを追加した。
- 会社名を書かない共通ルールは維持した。
- セリフ固定の正本を03に置き、`SCRIPT LINE == NARRATION == TELOP` をここだけに残した。後工程の同じ説明は参照へ置き換えた。

## 04_工程_prepare.md

- 製品ごとの事実をモデル別 profile から読む既存フローを維持し、dated folder の重複説明だけを01へ移した。

## 04_工程_script.md

- dated folder の重複説明を01へ移した。
- 会社名・価格などの共通禁止事項の修正先を03へ集約した。
- セリフ固定の重複本文を削り、03の固定ルールへの参照にした。
- 現行の `Gemini 3.8 Flash` 表記は判断保留として暫定維持した（QUESTIONS 3）。

## 04_工程_narration.md

- dated folderの重複説明と `Do not chat after a successful cut` の二重行を一本化した。
- SCRIPT LINEの重複本文を削り、03の固定ルールへの参照にした。
- `telop_only` カットをTTS生成しない既存の分岐は維持した。
- Gate AとGate Dの判定本文を02への参照へ置き換えた。音声生成・入力読み戻し・結果ID確認・失敗音声の再生成フローは維持した。
- fallback/debug、TTS helper、credit確認、契約停止条件の固定文字列は維持した。

## 04_工程_assembly.md

- dated folderの重複説明を01へ移した。
- Gate Bの正本本文と、特定製品のランプ色・画面状態の規則を削除した。代わりに製品ノートの `edit_rules` を読む共通接続点を残した。
- 製品ノートに定義された場合だけ返る停止コード名を1行で残した。
- 素材履歴、`approved_shots.py`、`visual_catalog.py`、`approved-shot history`、尺・意味・隣接画の選定順は維持した。
- 車載エイリアス例は判断保留のため現行文面を暫定維持した（QUESTIONS 1）。

## 04_工程_rough-edit.md

- dated folderの重複説明と特定案件向けの再開節を削除した。
- Gate A〜Dの判定本文を02への参照にし、実行順は `validate_tts` → `import_audio_batch` → 音声配置 → 固定1.2倍速 → `import_video_batch` → 映像・字幕 → `final_verify` として残した。
- 音声の `playbackRate` 更新を一括 `edit_item` として維持した。
- 字幕位置の出典名を削り、left=108, top=316, width=864, height=287 を「オペレーター調整済みの標準値」として維持した。
- 元製品名・中心座標の説明は削除したが、標準レイアウト値そのものは残した。
- Driveのログイン案内と読戻し案内は04_deliveryへ一本化した。
- 完了メッセージはdispatchから一度だけ送る共通本文に整理した。現行のDrive未準備時の別本文を復活させるかはQUESTIONS 2で保留した。

## 04_工程_delivery.md

- Drive readiness、`--login`、アップロード、読戻しをこのファイルの1箇所へ集約した。
- `approved_shots.py --record-final` と `product-video-approved-shots` の採用履歴記録を維持した。
- purge保護対象の列挙をこのファイルの1箇所へ集約した。
- 指定された `完成・格納してください` だけを完了トリガーとして維持した。

## 意味が変わるため明記した削除・一般化

- 特定案件のID・製品名・製品別倍率・価格例は共通文書から削除した。
- 製品専用のランプ色判定は共通ルールから削除し、製品ノートの `edit_rules` / 製品別ルールと、その証拠確認へ委ねた。
- ゲートの失敗対策を工程ごとの注意書きに増殖させず、失敗台帳と司令塔の受理条件へ移した。
- 文面の削除で曖昧になる4点は、現行文面をQUESTIONSへ写して保留した。

## コード側で作るべき項目（今回の文書変更では未実装）

1. 失敗台帳の各項目に `確認する証拠`、状態、対象stage、再発防止条件を持たせ、司令塔がstage完了前に全件を照合する。
2. stageの完了報告・receiptだけでは受理できないようにし、台帳証拠の参照IDがない完了を `pending` に戻す。
3. 失敗発生時に工程文書へ手動追記させず、失敗台帳への登録と受理条件への反映を自動または一箇所のコマンドで行う。
4. 製品ノートの `edit_rules` / 台本ルールから、Geminiへ渡したprompt、生成結果、edit-plan、選択範囲の検査証拠までのtraceを保存し、01が「有効」を判定できるようにする。
5. 02のGate A〜Dを、音声検証・visual match・音声先行配置・heartbeatの実行状態と結び付け、ゲート未通過のstage完了を拒否する。
6. 台本の会社名・価格禁止と1.2倍速固定、字幕標準値を生成・検査・edit-planの各write pathで検証する。
7. 製品ノートで追加された停止コードを、ノートだけでなく `edit_plan.py` 等の実行結果へ反映し、未証明のカットをChatCutへ渡さない。
8. Driveの新規ファイル読戻し、最終shot履歴、purge保護対象をdelivery receiptで相互照合する。

## 今回の追加修正

1. `04_工程_narration.md` に、SCRIPT LINE と NARRATION と TELOP の一致、および改行・ゼロ幅文字を無視しない元の固定文を復元した。
2. `01_共通_product-video司令塔.md` の Paths 付近に、behavior change では dated folder と frontmatter name を同時に変更し、旧 folder を残さず、entrypoint は日付なし、typo/comment-only edits は日付を変えないという Skill dates の3行を復元した。
3. `01_共通_product-video司令塔.md` の完了受理条件を、その工程を対象とする失敗台帳項目だけの照合へ限定した。各項目の「対象工程」と許可値を明記し、製品ノートの所有者が失敗台帳側を修正すること、および `dispatch.py` は検査せず司令塔が手で照合することを追記した。
4. `04_工程_delivery.md` に、`完成・書き出しOK` と `粗編集OK` は受け付けないという完了トリガーの制約を復元した。

## 今回の決定反映

1. `04_工程_rough-edit.md` の完了メッセージ本文を1つに統一し、送信回数を1回に維持した。Drive未準備時の `Drive格納準備` / `upload_drive_local_file.py --login` 本文は、`dispatch が同じメッセージへ差し込む。Drive の正本は 04_工程_delivery.md` という参照に置き換えた。`QUESTIONS.md` は `決定済み: 1=A残す, 2=B, 3=A, 4=A` として反映した。

## テロップ設計の取り込み（設計段階）

- `03_共通_Gemini台本テンプレ.md`: 末尾に新節を追加。テロップ設計用メタデータの要点を定義し、既存本体は不変。
- `01_共通_product-video司令塔.md`: `Retries` 前に短い節を追加。
- `04_工程_rough-edit.md`: 字幕手順8の直後に注記1行を、リスト内の継続行として挿入。
- `03_共通_Gemini台本テンプレ.md`: 追記節の先頭に「共通ビュー限定。gemini-script-instructions.md へ写さない（写すと注記ごとGeminiに届き、script_stage.py が解析できない行が混ざる）」を1行追加。
