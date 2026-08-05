# Sol Advisor導入手順

この工程は商品動画プラグインの導入とは別です。`scripts/bootstrap.sh`から自動実行されません。

## 実行前

- Codex CLIを最新版へ更新する。
- `jq`と`git`を用意する。
- Codexのモデル選択画面で、GPT-5.6 Sol / HighとTerra / Highが契約上利用できるか確認する。
- 認証やモデル契約の変更はユーザー本人が行う。

## 導入

```bash
./scripts/install-sol-advisor.sh
```

このスクリプトは、公式`DannyMac180/sol-advisor`の`main`だけを許可します。既存marketplaceの配布元が異なる場合は削除・上書きせずHOLDします。公式配布元が古い場合だけupgradeし、remote `main`とローカルsnapshotのcommit一致、cleanなGit状態、シンボリックリンク不在を確認します。

インストール元は`marketplace_root/plugins/sol-advisor`に固定し、plugin manifest、orchestration SKILL、installer、Terra/Solテンプレートの同一性を確認します。導入後は`sol-advisor-terra-implementer.toml`と`sol-advisor-sol-reviewer.toml`がテンプレートと完全一致し、内部name、モデル、reasoningがそれぞれ`sol_advisor_terra_implementer`／`gpt-5.6-terra`／`high`、`sol_advisor_sol_reviewer`／`gpt-5.6-sol`／`high`であることを確認します。

プラグイン、companion、`sol_advisor_terra_implementer`、`sol_advisor_sol_reviewer`を確認した後でも、シェルからUIのモデル利用可否を証明できないため、最後は`HOLD_MODEL_AVAILABILITY_UNVERIFIED`になります。これは導入失敗ではなく、ユーザーによるUI確認待ちです。

UI確認後は新しいCodexタスクを開始してください。通常のnative laneは、Sol / Highの親、Terra / Highのimplementer、新しいSol / High reviewerです。Luna task laneは明示的に許可した場合だけ使います。
