# Phase 1 比較レポート

## 範囲

同じ5件のTelop JSONを、HTML/CSS方式とSVG方式で1080×1920（9:16）へ描画した。両方式ともChrome headlessのスクリーンショットを使い、プレビューは灰色の仮背景、透明素材はCSS/SVGの背景を透明にした。本文、色、フォント、縁取り、要素順はJSONの指定を使い、Rendererが意味やデザインを推測しない。

Phase 1の比較用フレームは左108、上316、幅864、高さ287に固定した。JSONの`position`は検証対象として0〜1を確認するが、Phase 1 Rendererでは意図的に無視する。改行は共通のフレーム幅から決める。

## 実行環境

| 項目 | 実行時確認 |
|---|---|
| Python | 3.14（実行時の`python3 --version`結果を下記の実行記録に保存） |
| Chrome | Google Chrome 154.0.8037.58 |
| ffmpeg / ffprobe | 9.0.2 |
| 丸ゴシック | `Hiragino Maru Gothic ProN`（`fc-list`確認済み） |
| 角ゴシック | `Hiragino Kaku Gothic StdN`（W8 family、`fc-list`確認済み） |
| 絵文字 | `Apple Color Emoji`（`fc-list`確認済み） |

## HTML/CSSとSVGの比較

| 観点 | HTML/CSS | SVG |
|---|---|---|
| 日本語の概要 | ChromeのHTML文字組み。CSSのspanで部分色を付ける | `text` / `tspan`で文字と部分色を明示する |
| 部分色 | emphasisの文字範囲をspanへ反映 | emphasisの文字範囲をtspanへ反映 |
| 絵文字 | 独立span、Apple Color Emojiを指定 | 独立tspan、Apple Color Emojiを指定 |
| 透明背景 | bodyをtransparentにしてRGBA PNGへ | 背景rectを出さずRGBA PNGへ |
| モーション | CSS transformとopacityをフレーム時刻から算出。絵文字要素のanimationは`make_tokens`で拾うだけで描画には未使用（要素単位アニメは未実装） | SVG groupのtransformとopacityを同じ時刻計算で算出。絵文字要素のanimationは`make_tokens`で拾うだけで描画には未使用（要素単位アニメは未実装） |
| 再現性 | 同じ入力を2回レンダリングし、SHA-256を比較 | 同じ入力を2回レンダリングし、SHA-256を比較 |
| HTML/CSSとSVGの相互ハッシュ | 同じ見た目の入力でも描画経路が異なるため、同一ハッシュは採用条件にしない | 同左 |
| 処理時間 | 下記の実行記録に方式別の計測値を記載 | 下記の実行記録に方式別の計測値を記載 |

改行はChrome 154が対応する`word-break: auto-phrase`と`line-break: strict`をHTMLへ指定し、SVGとoverflow checkは共通の禁則・収まる範囲の日本語script runとASCII語を保持する折り返しを使う。サンプルでは「簡単」の語中分割と行頭の「！」は発生しない。Chromeの形態素分割をSVG側で完全再現するものではない。

### サンプル

| ファイル | 種別 | 確認対象 |
|---|---|---|
| `samples/hook.json` | HOOK | 全文強調、角ゴシック、pop |
| `samples/emphasis.json` | EMPHASIS | 部分色、独立絵文字、soft_slide |
| `samples/normal.json` | NORMAL | 丸ゴシック、強調なし |
| `samples/compare.json` | COMPARE | 部分色、比較向け角ゴシック |
| `samples/cta.json` | CTA | 全文強調、独立絵文字、fade_short |

## 透明アセット形式の比較

同じ30fps・約0.4秒のHTML方式PNG連番を入力にして、ffmpegでProRes 4444 MOVとVP9アルファWebMを試行した。PNG連番はHTML方式とSVG方式の両方を出力し、各フレームのPNG color typeと再レンダリング時のハッシュを比較した。

| 観点 | ProRes 4444 `.mov` | VP9 alpha `.webm` | PNG連番 |
|---|---|---|---|
| 透明性 | `yuva444p10le`を指定して試行。実際のffprobe結果は下記 | `yuva420p`を指定して試行。実際のffprobe結果は下記 | PNG IHDR color type 6（RGBA）を確認 |
| ファイル数 | 1 | 1 | 方式・フレーム数分 |
| ファイルサイズ | 下記の実測値 | 下記の実測値 | 下記の実測値（連番合計） |
| 再現性 | ffmpegの同一入力からの出力を比較対象にする | ffmpegの同一入力からの出力を比較対象にする | 同じ入力を再レンダリングし、フレーム列ハッシュを比較 |
| 互換性確認 | 取り込み先で確認が必要 | 取り込み先で確認が必要 | 連番を扱う工程で確認が必要 |

ここでは採用を決めない。容量、透明性、取り込み先の対応、フレーム単位の再現性を判断材料として残す。

## 実行記録

実行日：2026-09-29。出力先はすべてこのフォルダの下である。`python3 --version` は `Python 3.14.6`。`python3 --version` は `Python 3.14.6`。`python3 --version` は `Python 3.14.6`。

### Validator / unittest

実行コマンド：`python3 -m unittest -v`

```text
test_invalid_enum (test_telop.TelopValidatorTests.test_invalid_enum) ... ok
test_invalid_invariant (test_telop.TelopValidatorTests.test_invalid_invariant) ... ok
test_invalid_nonexistent_emphasis_phrase (test_telop.TelopValidatorTests.test_invalid_nonexistent_emphasis_phrase) ... ok
test_invalid_too_many_emoji (test_telop.TelopValidatorTests.test_invalid_too_many_emoji) ... ok
test_valid_case (test_telop.TelopValidatorTests.test_valid_case) ... ok
test_transparent_png_has_alpha (test_telop.TransparentRenderTests.test_transparent_png_has_alpha) ... ok

----------------------------------------------------------------------
Ran 6 tests in 1.614s

OK
```

サンプル5件は `python3 telop_validate.py samples/*.json` で全件 `VALID ... stage=render` になった。テストではenumエラー、絵文字過多、elements本文不変条件違反、存在しない強調語句、透明PNGのPNG color type 6を確認した。

### 5サンプル × 2方式の透明PNG

すべての透明PNGが1080×1920、PNG color type 6（RGBA）だった。

| 方式 | ファイル | サイズ（bytes） | color type |
|---|---|---:|---:|
| HTML/CSS | `samples/output/html/compare-transparent.png` | 61853 | 6 |
| HTML/CSS | `samples/output/html/cta-transparent.png` | 43257 | 6 |
| HTML/CSS | `samples/output/html/emphasis-transparent.png` | 74967 | 6 |
| HTML/CSS | `samples/output/html/hook-transparent.png` | 35512 | 6 |
| HTML/CSS | `samples/output/html/normal-transparent.png` | 53598 | 6 |
| SVG | `samples/output/svg/compare-transparent.png` | 66715 | 6 |
| SVG | `samples/output/svg/cta-transparent.png` | 49790 | 6 |
| SVG | `samples/output/svg/emphasis-transparent.png` | 80171 | 6 |
| SVG | `samples/output/svg/hook-transparent.png` | 37118 | 6 |
| SVG | `samples/output/svg/normal-transparent.png` | 64255 | 6 |

### 同一入力の2回レンダリング

入力は `samples/emphasis.json`、背景はtransparent、同じ時刻である。

| 方式 | 1回目SHA-256 | 2回目SHA-256 | 一致 |
|---|---|---|---|
| HTML/CSS | `99b0c4429d7666e7172496875f37f1e53d34e867a721f44f8421540d3549a421` | `99b0c4429d7666e7172496875f37f1e53d34e867a721f44f8421540d3549a421` | yes |
| SVG | `6a9426bd9527fc2a032b2baa1e90f1f38c950d67a874a47a69166b0b90e6efdc` | `6a9426bd9527fc2a032b2baa1e90f1f38c950d67a874a47a69166b0b90e6efdc` | yes |

方式をまたいだハッシュは一致しなかった。これは同一入力を異なる描画経路でPNG化した結果であり、方式間の採用判定には画素ハッシュだけを使わない。

Validatorの「約2色」は本文色と強調色の合計に適用し、必須の黒フチは構造色として数えていない。

Validatorの「約2色」は本文色と強調色の合計に適用し、必須の黒フチは構造色として数えていない。

Validatorの「約2色」は本文色と強調色の合計に適用し、必須の黒フチは構造色として数えていない。

1回のtransparent renderの計測値は、HTML/CSSがreal 1.63秒（user 0.93秒、sys 0.49秒）、SVGがreal 1.59秒（user 0.89秒、sys 0.46秒）だった。

### アニメーションPNG連番

`render_frames.py samples/hook.json --out frames/hook --method both --duration 0.4 --fps 30` を実行し、各方式12フレームを作成した。`emphasis`も同じ条件で作成し、soft_slideを確認した。

| 方式 | フレーム数 | 連番合計（bytes） | 連番SHA-256 | 再実行SHA-256 | 一致 |
|---|---:|---:|---|---|---|
| HTML/CSS | 12 | 419396 | `32553c3794df3c31ce66800ee346786de3e8b3f3362a1582a15a824d22767c63` | `32553c3794df3c31ce66800ee346786de3e8b3f3362a1582a15a824d22767c63` | yes |
| SVG | 12 | 437055 | `271d5635564bbd9bbe7d6989d6808addbc8d368f0ede038750dce58cb5705af7` | `271d5635564bbd9bbe7d6989d6808addbc8d368f0ede038750dce58cb5705af7` | yes |

24枚（両方式）のフレームについて、PNG color type 6と1080×1920を確認した。

### アルファ動画

入力は `frames/hook/html/frame-%03d.png`（30fps、12フレーム、0.40秒）である。

| 形式 | ffmpeg結果 | ffprobe `pix_fmt` | alpha plane probe | サイズ（bytes） |
|---|---|---|---|---:|
| ProRes 4444 `.mov` | 成功、12 frames | `yuva444p12le` | `alphaextract` 成功 | 1529455 |
| VP9 alpha `.webm` | 成功、12 frames、`alpha_mode=1`を付与 | `yuv420p` | `alphaextract` 失敗（exit 234） | 36038 |

実行した主なコマンドは次のとおり。

```text
ffmpeg -y -framerate 30 -i frames/hook/html/frame-%03d.png -c:v prores_ks -profile:v 4 -pix_fmt yuva444p10le comparison/hook-html-prores4444.mov
ffmpeg -y -framerate 30 -i frames/hook/html/frame-%03d.png -c:v libvpx-vp9 -pix_fmt yuva420p -auto-alt-ref 0 -b:v 0 -crf 30 -metadata:s:v:0 alpha_mode=1 comparison/hook-html-vp9-alpha.webm
```

ffmpegの出力ログではProResが `yuva444p10le` 指定から `yuva444p12le` として出力され、VP9は `yuva420p` と `alpha_mode=1` が表示された。一方、ffprobeのVP9 `pix_fmt` は `yuv420p` で、`ffmpeg -v error -i comparison/hook-html-vp9-alpha.webm -vf alphaextract -frames:v 1 -f null -` は `Requested planes not available` で終了コード234になった。VP9のアルファはメタデータだけでは確認済みとせず、実際の取り込み先でも確認が必要である。この差は採用を決めるためではなく、形式比較の材料として残す。

### フォント確認

`fc-list`で確認した実名をruntime CSS/SVGへ使用した。フォントファイルはコピーしていない。システムフォントの動画利用ライセンスは未確認であり、QUESTIONS.mdに保留した。

### Chrome headlessの環境メモ

通常のsandbox内では最小のdata URLに対して`--headless=new`と旧`--headless`がともに終了コード134になり、`--no-sandbox`でも改善しなかった。外側の実行環境で、同じ`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`に`--disable-software-rasterizer`、`--disable-dev-shm-usage`、`--disable-features=UseSkiaRenderer`を加えるとPNGを書き出せた。実装は代替ブラウザや別描画方式へ切り替えず、Chromeだけを使う。今回のChromeはprofileを指定するとPNG書き出し後に親プロセスが残るため、PNGの存在を確認した後にそのレンダー専用プロセスグループを終了する。

### Chrome headlessの環境メモ

通常のsandbox内では最小のdata URLに対して`--headless=new`と旧`--headless`がともに終了コード134になり、`--no-sandbox`でも改善しなかった。外側の実行環境で、同じ`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`に`--disable-software-rasterizer`、`--disable-dev-shm-usage`、`--disable-features=UseSkiaRenderer`を加えるとPNGを書き出せた。実装は代替ブラウザや別描画方式へ切り替えず、Chromeだけを使う。今回のChromeはprofileを指定するとPNG書き出し後に親プロセスが残るため、PNGの存在を確認した後にそのレンダー専用プロセスグループを終了する。

### Chrome headlessの環境メモ

通常のsandbox内では最小のdata URLに対して`--headless=new`と旧`--headless`がともに終了コード134になり、`--no-sandbox`でも改善しなかった。外側の実行環境で、同じ`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`に`--disable-software-rasterizer`、`--disable-dev-shm-usage`、`--disable-features=UseSkiaRenderer`を加えるとPNGを書き出せた。実装は代替ブラウザや別描画方式へ切り替えず、Chromeだけを使う。今回のChromeはprofileを指定するとPNG書き出し後に親プロセスが残るため、PNGの存在を確認した後にそのレンダー専用プロセスグループを終了する。
