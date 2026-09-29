# 変更履歴・出典対応

作成日：2026-09-29

このファイルは、各ノートの内容がどの資料のどの行に対応するかを示す。行番号は読み取り時点の原文の行番号。ノート位置はこの出力内の行番号。

## AN-S176/00_製品ルール.md

### 10_AN-S176_台本ルールの3項目

- ノート `AN-S176/00_製品ルール.md:24`「缶タイプ芳香剤をセットできること、画にないあるあるは使わない」→ `zip/readable-video-skills-latest/10_AN-S176_台本ルール.md:11-12`、同JSON `:5-6`。
- ノート `AN-S176/00_製品ルール.md:25`「価格は共通ルール参照、台本では言わない」→ `zip/readable-video-skills-latest/10_AN-S176_台本ルール.md:13`、同JSON `:7`。セール例外は原文にあるが、今回の共通ルールを優先した。
- ノート `AN-S176/00_製品ルール.md:26`「CTAは『下からチェック！』系、完全一致」→ `zip/readable-video-skills-latest/10_AN-S176_台本ルール.md:14`、同JSON `:8`、`zip/readable-video-skills-latest/12_AN-S176_設定.json:5-7`。

### 11_AN-S176_商品事実.jsonの全キーと配列項目

- ノート `AN-S176/00_製品ルール.md:20` の `schema_version`、ノート `:17` の `product_model` → `zip/readable-video-skills-latest/11_AN-S176_商品事実.json:2-3`。
- ノート `AN-S176/00_製品ルール.md:32` の `verified_facts[1]` → `11_AN-S176_商品事実.json:5`。
- ノート `AN-S176/00_製品ルール.md:33` の `verified_facts[2]` → `11_AN-S176_商品事実.json:6`。
- ノート `AN-S176/00_製品ルール.md:34` の `verified_facts[3]` → `11_AN-S176_商品事実.json:7`。
- ノート `AN-S176/00_製品ルール.md:35` の `verified_facts[4]` → `11_AN-S176_商品事実.json:8`。
- ノート `AN-S176/00_製品ルール.md:36` の `verified_facts[5]` → `11_AN-S176_商品事実.json:9`。
- ノート `AN-S176/00_製品ルール.md:37` の `verified_facts[6]` → `11_AN-S176_商品事実.json:10`。
- ノート `AN-S176/00_製品ルール.md:38` の `verified_facts[7]` → `11_AN-S176_商品事実.json:11`。
- ノート `AN-S176/00_製品ルール.md:39` の `verified_facts[8]` → `11_AN-S176_商品事実.json:12`。
- ノート `AN-S176/00_製品ルール.md:40` の `verified_facts[9]` → `11_AN-S176_商品事実.json:13`。
- ノート `AN-S176/00_製品ルール.md:41` の `verified_facts[10]` → `11_AN-S176_商品事実.json:14`。
- ノート `AN-S176/00_製品ルール.md:42` の `verified_facts[11]` → `11_AN-S176_商品事実.json:15`。
- ノート `AN-S176/00_製品ルール.md:43` の `verified_facts[12]`、参考売価を事実として保持しつつ台本では言わない注記 → `11_AN-S176_商品事実.json:16`。
- ノート `AN-S176/00_製品ルール.md:47` の `appeal_points[1]` → `11_AN-S176_商品事実.json:19`。
- ノート `AN-S176/00_製品ルール.md:48` の `appeal_points[2]` → `11_AN-S176_商品事実.json:20`。
- ノート `AN-S176/00_製品ルール.md:49` の `appeal_points[3]` → `11_AN-S176_商品事実.json:21`。
- ノート `AN-S176/00_製品ルール.md:53` の `edit_rules[1]` → `11_AN-S176_商品事実.json:24`。
- ノート `AN-S176/00_製品ルール.md:54` の `edit_rules[2]` → `11_AN-S176_商品事実.json:25`。
- ノート `AN-S176/00_製品ルール.md:55` の `edit_rules[3]` → `11_AN-S176_商品事実.json:26`。

### 設定とライト判定

- ノート `AN-S176/00_製品ルール.md:68` のCTA → `zip/readable-video-skills-latest/12_AN-S176_設定.json:5-7`。
- ノート `AN-S176/00_製品ルール.md:69` の標準音声と共通速度参照 → `12_AN-S176_設定.json:9-14`。速度値は共通ルールの決定により重複記載していない。
- ノート `AN-S176/00_製品ルール.md:70-73` のタイムライン照合、開始位置、収まり → `12_AN-S176_設定.json:16-33`。
- ノート `AN-S176/00_製品ルール.md:59-64` の「色の単語だけでは一致としない」「HOLD_LAMP_COLOR_UNSTATED」「HOLD_LAMP_COLOR_FRAME_REQUIRED」「lamp-color-proof.json」の手順 → `zip/readable-video-skills-latest/04_工程_assembly.md:35`。色の具体的な対応と編集上の制限は `11_AN-S176_商品事実.json:11,24` も反映。
- ノート `AN-S176/00_製品ルール.md:75` のJSONを別に残し手で揃える方針 → `zip/readable-video-skills-latest/12_AN-S176_設定.json:1-33` と今回の決定事項。

### システムへの反映状況

- ノート `AN-S176/00_製品ルール.md:79` の `must` と `rules` の差分 → 入力 `10_AN-S176_台本ルール.json:2,5` と、対象ブランチの実ローダー `repo/.cursor/skills/product-video/scripts/render_script_prompt.py:24-43`。
- ノート `AN-S176/00_製品ルール.md:80` の「GitHub上に10番台ファイルなし、ローカルzip由来、元場所不明」→ 対象ブランチに対する `git ls-tree -r --name-only origin/cursor/ans152-placement-gates-7fd6` の該当パス検索結果と、今回の入力パス。
- ノート `AN-S176/00_製品ルール.md:81-82` の未反映・共通文書からの削除は別作業 → 上記のローダー調査結果、`04_工程_assembly.md:35`、今回の作業範囲。

## AN-S152/00_製品ルール.md

### 商品事実

- ノート `AN-S152/00_製品ルール.md:15-18` の商品モデル、商品名、JSON版 → 対象ブランチ `config/product_video_product_facts_AN-S152.v1.json:2-5`。
- ノート `AN-S152/00_製品ルール.md:38` の `verified_facts[1]` → `config/product_video_product_facts_AN-S152.v1.json:5`。
- ノート `AN-S152/00_製品ルール.md:39` の `verified_facts[2]` → 同 `:6`。
- ノート `AN-S152/00_製品ルール.md:40` の `verified_facts[3]` → 同 `:7`。
- ノート `AN-S152/00_製品ルール.md:41` の `verified_facts[4]` → 同 `:8`。
- ノート `AN-S152/00_製品ルール.md:42` の `verified_facts[5]` → 同 `:9`。
- ノート `AN-S152/00_製品ルール.md:43` の `verified_facts[6]` → 同 `:10`。
- ノート `AN-S152/00_製品ルール.md:44` の `verified_facts[7]` → 同 `:11`。
- ノート `AN-S152/00_製品ルール.md:45` の `verified_facts[8]` → 同 `:12`。
- ノート `AN-S152/00_製品ルール.md:46` の `verified_facts[9]` → 同 `:13`。
- ノート `AN-S152/00_製品ルール.md:47` の `verified_facts[10]` → 同 `:14`。
- ノート `AN-S152/00_製品ルール.md:48` の `verified_facts[11]` → 同 `:15`。
- ノート `AN-S152/00_製品ルール.md:49` の `verified_facts[12]` → 同 `:16`。
- ノート `AN-S152/00_製品ルール.md:50` の `verified_facts[13]` と価格は発話しない注記 → 同 `:17`。
- ノート `AN-S152/00_製品ルール.md:51` の `verified_facts[14]` → 同 `:18`。
- ノート `AN-S152/00_製品ルール.md:55-57` の `appeal_points[1-3]` → 同 `:21-23`。

### 台本ルール

- ノート `AN-S152/00_製品ルール.md:22-25` の4つのルール → 対象ブランチ `config/product_video_script_rules_AN-S152.v1.json:4-8`。速度に関する項目は今回の決定により数値を転記せず、共通ルール参照とした。
- ノート `AN-S152/00_製品ルール.md:29` のセリフ禁止文字 → 同 `:10-20`。
- ノート `AN-S152/00_製品ルール.md:30` のシチュエーション禁止文字 → 同 `:22-31`。
- ノート `AN-S152/00_製品ルール.md:31` の必須文字 → 同 `:33-35`。
- ノート `AN-S152/00_製品ルール.md:32` の前後関係と同一行 → 同 `:37-39`。
- ノート `AN-S152/00_製品ルール.md:61-63` の編集上の反映 → 同JSON `:4-8` と商品事実・共通ルール。

### 設定とTTS再開手順

- ノート `AN-S152/00_製品ルール.md:67` のCTA → 対象ブランチ `config/product_video_settings_AN-S152.v1.json:5-7`。
- ノート `AN-S152/00_製品ルール.md:68` の標準音声と共通速度参照 → 同 `:9-15`。速度値は今回の決定により重複記載していない。
- ノート `AN-S152/00_製品ルール.md:69-72` のタイムライン照合、開始位置、収まり → 同 `:17-34`。
- ノート `AN-S152/00_製品ルール.md:74` のJSONを別に残し手で揃える方針 → 同設定JSON全体と今回の決定事項。
- ノート `AN-S152/00_製品ルール.md:84-90` の再開手順要約 → 対象ブランチ `.cursor/skills/product-video/references/an-s152-tts-resume.md:3-18,20-90`。元のファイルパスはノートのfrontmatterと `:79` に残した。
- ノート `AN-S152/00_製品ルール.md:78-80,92-93` のシステム反映状況 → 対象ブランチ `AGENTS.md:5-33`、`config/product_video_script_rules_AN-S152.v1.json`、`config/product_video_settings_AN-S152.v1.json`、再開手順ファイル。

## 共通/失敗台帳.md

- ノート `共通/失敗台帳.md:9-23` の目的と登録形式 → 今回の決定事項。
- ノート `共通/失敗台帳.md:30-35` のF-001 → `zip/readable-video-skills-latest/02_共通_配置ゲート.md:3,7-38`、対象ブランチの再開手順 `:34-47`。
- ノート `共通/失敗台帳.md:40-45` のF-002 → `02_共通_配置ゲート.md:3,40-53`、`zip/readable-video-skills-latest/04_工程_assembly.md:35`、対象ブランチの再開手順 `:73-80`。
- ノート `共通/失敗台帳.md:50-55` のF-003 → `02_共通_配置ゲート.md:3,55-66`、対象ブランチの再開手順 `:49-71`。

## QUESTIONS.md

- ノート `QUESTIONS.md:5-10` のAN-S151TLE未作成 → 今回の対象範囲。
- ノート `QUESTIONS.md:12-18` の会社名を含む事実文 → `11_AN-S176_商品事実.json:5` と共通ルールの決定事項。
- ノート `QUESTIONS.md:20-26` の共通設定と製品設定の混在 → `12_AN-S176_設定.json:1-33`、対象ブランチ `config/product_video_settings_AN-S152.v1.json:1-34`。
- ノート `QUESTIONS.md:28-34` の10番台JSONのローダー差分 → `10_AN-S176_台本ルール.json:2,5`、対象ブランチ `render_script_prompt.py:24-43`、Git tree検索結果。
- ノート `QUESTIONS.md:36-42` のAN-S152速度設定の同期 → 対象ブランチ `config/product_video_script_rules_AN-S152.v1.json:8`、`config/product_video_settings_AN-S152.v1.json:9-15`、今回の共通ルール決定。

## 2026-09-29 追加編集

- `共通/失敗台帳.md`：書式に「対象工程」と「根拠」を追加し、F-001〜F-003へ適用工程と根拠を追記。目的に司令塔の確認範囲を追記。
- `AN-S176/00_製品ルール.md:64,82`：共通04aからのライト色ルール削除済みと停止コード名の共通側残置を反映。
