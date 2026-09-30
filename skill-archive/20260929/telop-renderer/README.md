# Phase 1 最小AIテロップ

このフォルダは、Telop JSONを検査し、同じ入力をHTML/CSS方式とSVG方式で描画する小さな検証用実装です。出力は1080×1920（9:16）で、プレビューは灰色の仮背景、透明素材はRGBA PNGです。本文は変更・言い換えせず、改行だけをRendererが固定フレーム幅から決めます。

絵文字はJSONの`elements`内で本文と分けて指定します。実行時はMacにインストール済みの`Apple Color Emoji`、`Hiragino Maru Gothic ProN`、`Hiragino Kaku Gothic StdN`を参照します。フォントファイルは同梱していません。

## 非エンジニア向けの3コマンド

1. サンプルJSONを検査する。

```sh
python3 telop_validate.py samples/*.json
```

2. サンプル1件をHTML/CSSで灰色背景のプレビューにする。

```sh
python3 render_html.py samples/hook.json --out samples/output/html/hook-preview.png --background preview
```

3. 同じサンプルをSVGで透明PNGにする。

```sh
python3 render_svg.py samples/hook.json --out samples/output/svg/hook-transparent.png --background transparent
```

## 生成物

- `samples/output/html/` と `samples/output/svg/`：5サンプルのプレビューPNG・透明PNG。
- `frames/`：30fps、約0.4秒の透明PNG連番。
- `comparison/`：アルファ動画比較用のProRes 4444 MOVとVP9アルファWebM。
- `compare_report.md`：HTML/CSSとSVG、アルファ動画とPNG連番の比較記録。
- `QUESTIONS.md`：採用を確定していない論点。

ChatCut連携、Gemini CLIによる生成、映像解析による位置決めはこのPhaseでは実装していません。既存のChatCut字幕手順も変更していません。

## フォントの扱い

現状はMacシステムフォントを実行時参照するだけです。動画用途を含むシステムフォントのライセンス確認は未完了で、採用条件ではありません。将来の同梱候補として、Zen Maru Gothic / Noto Sans JP（いずれもOFL系の候補）を挙げますが、ここではダウンロードも同梱もしていません。
