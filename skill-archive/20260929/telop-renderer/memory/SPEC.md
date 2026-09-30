# 契約・仕様
<!-- ルール: 確定した仕様・制約・入出力・インターフェースのみ記載。「検討中」はQUESTIONS.mdへ -->

## 概要
商品動画向けAIテロップの Phase 1 最小実装。Telop JSON を検証し、同じ入力を HTML/CSS 方式と SVG 方式で描画（プレビューPNG／透明PNG／簡易アニメ連番）する。Renderer は JSON 通りに描くだけ。

## 確定仕様
- 出力は 1080×1920（9:16）。透明PNGはRGBA（color type 6）。
- 列挙値は大文字。タイプは NORMAL/HOOK/EMPHASIS/COMPARE/CTA。
- テロップ本文は変更・言い換えしない。type=text の elements の連結 == text。強調候補はセリフ本文に実在する語句のみ。
- 絵文字は独立要素。通常0〜1個、強調最大2個、同一連続禁止。絵文字要素のモーションは pop のみ。
- 枠(高さ287)からはみ出す場合は ValidationError。
- 設計書の正本: Obsidian `product-video-materials/共通/テロップ/00〜05`。

## 制約
- 追加依存なし（Python3標準＋Chrome＋ffmpeg）。ネットワーク取得・フォント同梱なし。
