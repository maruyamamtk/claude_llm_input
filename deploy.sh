#!/usr/bin/env bash
# Cloud Run Jobs デプロイスクリプト
# 使い方:
#   ./deploy.sh setup   — Artifact Registry + Cloud Run Job を初期作成
#   ./deploy.sh deploy  — イメージをビルド&プッシュして Job を更新
#   ./deploy.sh run     — Job を手動実行
set -euo pipefail

PROJECT_ID="keiba-prediction-1768734113"
REGION="asia-northeast1"
AR_REPO="ai-tips-collector"
IMAGE_NAME="ai-tips-collector"
JOB_NAME="ai-tips-collector"
GCS_BUCKET="ai-tips-obsidian-${PROJECT_ID}"

IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${IMAGE_NAME}:latest"

# ---- サブコマンド --------------------------------------------------------

cmd_setup() {
  echo "=== Artifact Registry リポジトリ作成 ==="
  gcloud artifacts repositories create "${AR_REPO}" \
    --repository-format=docker \
    --location="${REGION}" \
    --description="AI Tips Collector Docker images" \
    --project="${PROJECT_ID}" || echo "（既に存在する場合はスキップ）"

  echo "=== GCS バケット作成（Obsidian 出力先） ==="
  gcloud storage buckets create "gs://${GCS_BUCKET}" \
    --location="${REGION}" \
    --project="${PROJECT_ID}" || echo "（既に存在する場合はスキップ）"

  echo "=== 初回イメージビルド&プッシュ ==="
  cmd_build

  echo "=== Cloud Run Job 作成 ==="
  # 注意: --set-secrets は Issue #11（Secret Manager設定）完了後に有効化する
  # 現時点では credentials.json / token.json を手動で Secret Manager に登録してから
  # 下記フラグを追加すること:
  #   --set-secrets="/app/credentials.json=gmail-credentials:latest"
  #   --set-secrets="/app/token.json=gmail-token:latest"
  gcloud run jobs create "${JOB_NAME}" \
    --image="${IMAGE_URI}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --memory=1Gi \
    --task-timeout=600 \
    --max-retries=0 \
    --set-env-vars="OBSIDIAN_NOTES_DIR=/mnt/gcs/08_AINews" \
    --add-volume="name=gcs-obsidian,type=cloud-storage,bucket=${GCS_BUCKET}" \
    --add-volume-mount="volume=gcs-obsidian,mount-path=/mnt/gcs"

  echo ""
  echo "=== セットアップ完了 ==="
  echo "次のステップ:"
  echo "  1. Issue #11 の手順で Secret Manager に credentials.json / token.json を登録する"
  echo "  2. Cloud Run Job に --set-secrets フラグを追加して更新する"
  echo "  3. ./deploy.sh run で動作確認する"
}

cmd_build() {
  echo "=== Docker イメージ ビルド & プッシュ ==="
  gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
  docker build --platform linux/amd64 -t "${IMAGE_URI}" .
  docker push "${IMAGE_URI}"
  echo "プッシュ完了: ${IMAGE_URI}"
}

cmd_deploy() {
  cmd_build

  echo "=== Cloud Run Job イメージ更新 ==="
  gcloud run jobs update "${JOB_NAME}" \
    --image="${IMAGE_URI}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}"
  echo "デプロイ完了"
}

cmd_run() {
  echo "=== Cloud Run Job 手動実行 ==="
  gcloud run jobs execute "${JOB_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --wait
  echo "実行完了（Cloud Logging でログを確認してください）"
}

# ---- エントリポイント ----------------------------------------------------

case "${1:-}" in
  setup)  cmd_setup  ;;
  deploy) cmd_deploy ;;
  run)    cmd_run    ;;
  *)
    echo "使い方: $0 {setup|deploy|run}"
    exit 1
    ;;
esac
