# 2026-09-29 スキル整理の記録

共通スキルと製品別ルールを分離した整理版の保管場所です（文書のみ。実行中のスキル・スクリプトは変更していません）。

- `common/` : 共通スキル 00〜04（製品名・価格・1.5倍速を排除。司令塔に「完了の受理条件」を追加）
- `product-notes/` : 製品別ルール（AN-S176, AN-S152）。正本は Obsidian の product-video-materials
- `failure-ledger/` : 失敗台帳（正本は Obsidian の product-video-materials/共通/）
- 各 CHANGES.md / QUESTIONS.md : 変更内容と判断の記録

注意: 受理条件の自動強制は未実装（コード側の対応項目は common/CHANGES.md 末尾）。
- `telop-design/` : AIテロップ生成システムの設計書（設計段階・未実装。正本は Obsidian の product-video-materials/共通/テロップ/）
- `telop-renderer/` : テロップ Phase 1 最小実装（正本は ~/Documents/AI/projects/telop-renderer。生成物と比較動画を含む）
