# KEIYO AI Video Workflow

別PCへ、検証済みのTikTok商品動画作成スキルを同一ファイルで引き継ぐための非公開リポジトリです。

このリポジトリにはスキル、検証器、契約書、およびメディアを含まないゴールデン基準だけを格納します。商品素材、動画、データベース、アカウント情報、認証情報、Google Driveの保存先ID、CapCut / ChatCut のプロジェクト状態は含めません。製品型番と素材は案件ごとに変わります。AN-S182はその基準製品の一例です。

## Cursor の本流（台本 → Drive 格納）

枝 `v2/mac-local` の本番ホストは、**操作 Mac 上の Cursor Desktop Agent** です。Cloud Agent / Cloud VM では作りません。タグ `v1.0.0` と `main` の Cloud 手順は残します。

正本スキルは `.cursor/skills/produce-tiktok-product-video-portable/` です。起動は `/produce-tiktok-product-video-portable`。通常確認は `台本OK`、`粗編集OK`、`完成・書き出しOK` だけ。完成後の既定は、型番名の Drive フォルダへの新規格納です。

人向けの通し手順は [docs/product-video-to-drive.md](docs/product-video-to-drive.md) です。この Mac での起動文は [docs/mac-desktop-agent-product-video.md](docs/mac-desktop-agent-product-video.md) です。台本は Cursor のモデル切替ではなく、この Mac の Chrome でログイン済みの Gemini 3.8 Flash に作らせます。Cloud Agent 向けの旧起動文は [docs/cursor-cloud-agent-product-video.md](docs/cursor-cloud-agent-product-video.md) です。

## 別PCで同じスキルを使う（Cursor）

1. GitHubでこの**非公開**リポジトリをcloneする。パスワードやトークンをチャットへ貼らない。
2. そのPCで使う**製品型番**を決める。別製品なら `config/product_video_settings_<MODEL>.v1.json` をその製品用に新規作成する。AN-S182の設定をコピーして型番だけ変えない。
3. 素材は Git に入れず、`.runtime/product-video-inputs/<MODEL>_コピー` または `PRODUCT_VIDEO_MATERIAL_ROOT` に置く。
4. Driveの格納先は、型番と同じ名前のフォルダ1つ。フォルダIDはリポジトリに書かない。
5. 導入確認:

```bash
python3 .cursor/skills/produce-tiktok-product-video-portable/scripts/resolve_product_inputs.py --project-root . --product-model <MODEL> --require-materials
python3 .cursor/scripts/verify_product_video_setup.py --product-model <MODEL> --require-materials
```

6. Cursorでこのリポジトリの枝 `v2/mac-local` を開き、実行先をこの Mac の Desktop Agent にする。`/produce-tiktok-product-video-portable` で新規案件を開始する。まず `台本OK` まで進めて止める。

## 引き継ぎの全体像

1. 両方のPCで同じGitHubアカウントへログインする。
2. `keiyoaimacmini-png/keiyo-ai-video-workflow`を**非公開**で作成し、`main`の検証済みcommitへ注釈付き`v1.0.0`タグを付ける。
3. 別PCでこのリポジトリをcloneし、`python3 scripts/verify_package.py`を実行する。
4. Sol Advisorを専用の別工程で公式リポジトリから導入する。
5. `scripts/bootstrap.sh`でこのmarketplaceとプラグインを導入する。
6. Codexで新しいタスクを開始してスキルを使う。

GitHubやCodexのパスワード、Personal Access Token、OAuthコードはCodexへ貼り付けないでください。ブラウザまたはGitHub CLIの対話画面で本人が認証します。

## Windows 11での1コマンド導入

Windows側ではPowerShell 7（`pwsh`）、GitHub CLI、Git、Python 3.12を用意します。GitHubへのログイン、OAuth、MFA、Codexへのログインはユーザー本人が対話画面で完了してください。本スクリプトは認証情報を引数や独自の環境変数・設定ファイルとして受け取りません。

最初にユーザー本人が認証し、privateリポジトリをcloneします。

```powershell
gh auth login
gh auth status
gh auth setup-git
gh repo clone keiyoaimacmini-png/keiyo-ai-video-workflow
Set-Location keiyo-ai-video-workflow
```

clone後の導入と検証は、リポジトリのルートで次の1コマンドを実行します。`<承認済みbranch>`にはWindows自動化を含むGitHub上のbranch、`<承認済みcommit SHA>`にはそのbranchの検証済み40桁SHAを指定します。既存の`v1.0.0`はこのWindows自動化より前の版なので指定しません。

```powershell
pwsh -NoProfile -File .\scripts\bootstrap.ps1 -Repo "keiyoaimacmini-png/keiyo-ai-video-workflow" -Ref "<承認済みbranch>" -ExpectedCommit "<承認済みcommit SHA>"
```

このコマンドは配布元と固定refを確認してから商品動画プラグインを導入し、Windows検証を実行します。検証結果が1件でも不一致ならPASSにせず停止します。Sol Advisorは別の公式導入工程であり、このコマンドには含まれません。

導入済み環境の再検証だけを行う場合は、レポートをリポジトリ外へ指定して次の1コマンドを実行します。

```powershell
$report = Join-Path $env:TEMP "keiyo-windows-verification.json"; pwsh -NoProfile -File .\scripts\verify-windows.ps1 -ReportPath $report
```

`verify-windows.ps1`はWindows、PowerShell 7、Python 3.12を必須条件とし、package、AN-S182ゴールデン基準v2、payload self-test、Python unittestを読み取り専用で実行します。Pythonのキャッシュはリポジトリ外へ隔離し、リポジトリの変更、`__pycache__`、`.pyc`を検出した場合はfail closedで停止します。JSONレポートだけが指定先に残ります。

この自動化の対象はGitHub上のportable skillの導入と検証です。Google Driveの接続・素材取得・原素材操作、CapCutの導入・編集・書き出し、音声やフォントの主観確認、クラウド保存、公開、課金、外部送信は行いません。これらは従来どおりHOLDとし、それぞれユーザーの確認または別承認が必要です。

## 前提条件

- 現行のCodex DesktopまたはCodex CLI
- GitHub CLI（`gh`）
- Python 3
- Sol Advisorのcompanion確認に使う`jq`
- GitHubとCodexの認証操作はユーザー本人が行う

## GitHub認証と取得

```bash
gh auth login
gh auth status
gh auth setup-git
gh repo clone keiyoaimacmini-png/keiyo-ai-video-workflow
cd keiyo-ai-video-workflow
python3 scripts/verify_package.py
```

使用するGitHubアカウントは`keiyoaimacmini-png`で固定します。リポジトリはprivate、既定ブランチは`main`、originは公式HTTPS URLでなければ導入を停止します。

## 1. Sol Advisorを別に導入

Sol Advisorはこのリポジトリへ複製しません。詳細は[Sol Advisor導入手順](docs/INSTALL_SOL_ADVISOR_JA.md)を確認し、商品動画プラグインとは別に実行します。

```bash
./scripts/install-sol-advisor.sh
```

## 2. 商品動画プラグインを導入

GitHubへ`v1.0.0`タグを作成した場合の例です。非公開リポジトリをCodex側から取得できるよう、事前に`gh auth setup-git`を実行します。

```bash
./scripts/bootstrap.sh --repo keiyoaimacmini-png/keiyo-ai-video-workflow --ref v1.0.0
```

導入後はCodexで新しいタスクを開始し、次のように依頼します。

```text
$create-tiktok-product-video
商品ページURLと新規動画に使う素材を渡します。既存プロジェクトは変更せず、承認前の設計まで進めてください。
```

`OK`は編集だけの承認です。書き出し、クラウド保存、公開、課金、外部送信はそれぞれ別承認です。

## 検証

```bash
python3 scripts/verify_package.py
python3 scripts/verify_golden_baseline.py
python3 scripts/verify_golden_baseline_v2.py
./scripts/verify-release.sh
python3 plugins/keiyo-product-video/skills/create-tiktok-product-video/scripts/validate_product_video_payload.py --self-test
python3 -m unittest discover -s tests -v
```

すべてPASSするまで、タグ作成・導入・共有を行いません。`MANIFEST.sha256`は配布ファイルの完全性を固定します。導入時はrelease、marketplace snapshot、installed sourceのplugin manifestとスキル4ファイルを同じmanifest hashへ照合します。

`PASS_GOLDEN_BASELINE status=HOLD`は、既知のHOLDを含む基準データが改変されず、検証器がそのHOLDを正確に固定できたという完全性判定です。Mac版のゴールデン採用、Windowsでの同等品質、書き出し・公開の許可を意味しません。

## Mac版ゴールデン基準

`golden-baselines/an-s182/v1/`は旧プロジェクトを記録した履歴用HOLD基準です。`golden-baselines/an-s182/v2/`が、ユーザー受入済みの現行完成Mac版`AI作成_AN-S182_2026_08_06`をWindowsで再現するための基準です。v2ではC4を`IMG_3958.MOV`、C6を`IMG_3893.MOV`として固定し、全カットのsidecar照合が`verified`です。

どちらも素材ファイルやフレーム画像を格納せず、素材ID、ファイル名、使用範囲、sidecarのハッシュ、カットごとの意味要件だけを保持します。

これらの基準は既存プロジェクトを現行の新規動画payloadへ遡及変換するものではありません。Mac版を説明する独立した受入テストです。v2はMac正解見本として受入済みですが、Windows環境・音声・権利確認はHOLDであり、Windows同等品質や編集・書き出しの許可を自動的に意味しません。専用ブランチでの公開によって既存の`v1.0.0`が変更されることもありません。
