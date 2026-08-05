# KEIYO AI Video Workflow

別PC・別Codexアカウントへ、検証済みのTikTok商品動画作成スキルを同一ファイルで引き継ぐための非公開リポジトリです。

このリポジトリにはスキル、検証器、契約書だけを格納します。商品素材、動画、データベース、アカウント情報、認証情報、Google Driveの保存先、CapCutのプロジェクト状態は含めません。

## 引き継ぎの全体像

1. 両方のPCで同じGitHubアカウントへログインする。
2. `keiyoaimacmini-png/keiyo-ai-video-workflow`を**非公開**で作成し、`main`の検証済みcommitへ注釈付き`v1.0.0`タグを付ける。
3. 別PCでこのリポジトリをcloneし、`python3 scripts/verify_package.py`を実行する。
4. Sol Advisorを専用の別工程で公式リポジトリから導入する。
5. `scripts/bootstrap.sh`でこのmarketplaceとプラグインを導入する。
6. Codexで新しいタスクを開始してスキルを使う。

GitHubやCodexのパスワード、Personal Access Token、OAuthコードはCodexへ貼り付けないでください。ブラウザまたはGitHub CLIの対話画面で本人が認証します。

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
./scripts/verify-release.sh
python3 plugins/keiyo-product-video/skills/create-tiktok-product-video/scripts/validate_product_video_payload.py --self-test
python3 -m unittest discover -s tests -v
```

すべてPASSするまで、タグ作成・導入・共有を行いません。`MANIFEST.sha256`は配布ファイルの完全性を固定します。導入時はrelease、marketplace snapshot、installed sourceのplugin manifestとスキル4ファイルを同じmanifest hashへ照合します。
