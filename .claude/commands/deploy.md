---
description: ai-tips-collector を Cloud Run にデプロイする（Dockerビルド→プッシュ→Job更新）
---

以下の手順で ai-tips-collector を Cloud Run Jobs にデプロイしてください。

## 実行ステップ

1. **事前確認**
   - `git status` でコミット漏れがないか確認する
   - `uv run pytest tests/ -q` でテストが全通過することを確認する

2. **デプロイ実行**
   - プロジェクトディレクトリ `/Users/michika_maruyama/Desktop/claude_llm_input` で以下を実行する
   - `bash deploy.sh deploy`
   - Docker イメージのビルド → Artifact Registry へのプッシュ → Cloud Run Job の更新 が順に実行される

3. **デプロイ結果確認**
   - 出力の末尾に「デプロイ完了」が表示されることを確認する
   - エラーが発生した場合は原因を調査して報告する

4. **動作確認（任意）**
   - ユーザーから手動実行を求められた場合は `bash deploy.sh run` を実行する
   - Cloud Run Job の実行ログは `gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=ai-tips-collector" --project=keiba-prediction-1768734113 --limit=50 --format=json` で確認できる

## 補足情報

- プロジェクト: `keiba-prediction-1768734113`
- リージョン: `asia-northeast1`
- イメージ: `asia-northeast1-docker.pkg.dev/keiba-prediction-1768734113/ai-tips-collector/ai-tips-collector:latest`
- Job名: `ai-tips-collector`
- シークレット: `GOOGLE_API_KEY=google-api-key:latest`, `GITHUB_TOKEN=github-token:latest`
