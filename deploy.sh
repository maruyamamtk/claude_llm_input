#!/usr/bin/env bash
# Cloud Run Jobs デプロイスクリプト
# 使い方:
#   ./deploy.sh setup     — Artifact Registry + Cloud Run Job を初期作成
#   ./deploy.sh secrets   — Secret Manager にシークレットを登録し、IAMロールを付与
#   ./deploy.sh deploy    — イメージをビルド&プッシュして Job を更新（Secrets設定込み）
#   ./deploy.sh schedule  — Cloud Scheduler ジョブを作成
#   ./deploy.sh run       — Job を手動実行
set -euo pipefail

PROJECT_ID="keiba-prediction-1768734113"
REGION="asia-northeast1"
AR_REPO="ai-tips-collector"
IMAGE_NAME="ai-tips-collector"
JOB_NAME="ai-tips-collector"
GCS_BUCKET="ai-tips-obsidian-${PROJECT_ID}"
SCHEDULER_JOB_NAME="ai-tips-collector-daily"
SCHEDULER_SCHEDULE="30 8 * * *"   # 08:30 JST (Asia/Tokyo タイムゾーン指定)
SERVICE_ACCOUNT="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')-compute@developer.gserviceaccount.com"

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
  gcloud run jobs create "${JOB_NAME}" \
    --image="${IMAGE_URI}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --memory=1Gi \
    --task-timeout=600 \
    --max-retries=0 \
    --set-env-vars="OBSIDIAN_NOTES_DIR=/mnt/gcs/08_AINews,GCP_PROJECT_ID=${PROJECT_ID}" \
    --add-volume="name=gcs-obsidian,type=cloud-storage,bucket=${GCS_BUCKET}" \
    --add-volume-mount="volume=gcs-obsidian,mount-path=/mnt/gcs"

  echo ""
  echo "=== セットアップ完了 ==="
  echo "次のステップ:"
  echo "  1. ./deploy.sh secrets で Secret Manager にシークレットを登録する"
  echo "  2. ./deploy.sh deploy で Cloud Run Job をシークレット設定込みで更新する"
  echo "  3. ./deploy.sh schedule で Cloud Scheduler を設定する"
  echo "  4. ./deploy.sh run で動作確認する"
}

cmd_secrets() {
  echo "=== Secret Manager: シークレット登録 ==="

  # anthropic-api-key
  if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "エラー: 環境変数 ANTHROPIC_API_KEY が設定されていません"
    exit 1
  fi
  echo -n "${ANTHROPIC_API_KEY}" | gcloud secrets create anthropic-api-key \
    --data-file=- \
    --project="${PROJECT_ID}" \
    --replication-policy=automatic 2>/dev/null || \
  echo -n "${ANTHROPIC_API_KEY}" | gcloud secrets versions add anthropic-api-key \
    --data-file=- \
    --project="${PROJECT_ID}"
  echo "  anthropic-api-key: 登録完了"

  # github-token（空でも登録可、レート制限緩和用）
  _github_token="${GITHUB_TOKEN:-}"
  echo -n "${_github_token}" | gcloud secrets create github-token \
    --data-file=- \
    --project="${PROJECT_ID}" \
    --replication-policy=automatic 2>/dev/null || \
  echo -n "${_github_token}" | gcloud secrets versions add github-token \
    --data-file=- \
    --project="${PROJECT_ID}"
  echo "  github-token: 登録完了"

  # gmail-token（token.json ファイルの内容を登録）
  _token_file="${GMAIL_TOKEN_FILE:-token.json}"
  if [ ! -f "${_token_file}" ]; then
    echo "警告: Gmail トークンファイルが見つかりません: ${_token_file}"
    echo "  初回Gmail認証後に再実行するか、GMAIL_TOKEN_FILE 環境変数でパスを指定してください"
  else
    gcloud secrets create gmail-token \
      --data-file="${_token_file}" \
      --project="${PROJECT_ID}" \
      --replication-policy=automatic 2>/dev/null || \
    gcloud secrets versions add gmail-token \
      --data-file="${_token_file}" \
      --project="${PROJECT_ID}"
    echo "  gmail-token: 登録完了"
  fi

  echo ""
  echo "=== Secret Manager: サービスアカウントに secretAccessor ロール付与 ==="
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/secretmanager.secretAccessor" \
    --condition=None
  echo "  ${SERVICE_ACCOUNT} に secretmanager.secretAccessor を付与しました"
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

  echo "=== Cloud Run Job イメージ更新（Secrets設定込み） ==="
  gcloud run jobs update "${JOB_NAME}" \
    --image="${IMAGE_URI}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --task-timeout=1800 \
    --set-env-vars="OBSIDIAN_NOTES_DIR=/mnt/gcs/08_AINews,GCP_PROJECT_ID=${PROJECT_ID}" \
    --set-secrets="ANTHROPIC_API_KEY=anthropic-api-key:latest,GITHUB_TOKEN=github-token:latest"
  echo "デプロイ完了"
}

cmd_schedule() {
  echo "=== Cloud Scheduler: ジョブ作成 ==="

  # Cloud Run Job 実行に必要な IAM ロールを Cloud Scheduler サービスアカウントに付与
  _scheduler_sa="service-$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')@gcp-sa-cloudscheduler.iam.gserviceaccount.com"
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${_scheduler_sa}" \
    --role="roles/run.invoker" \
    --condition=None || echo "（IAMバインディングが既に存在する場合はスキップ）"

  # Cloud Scheduler ジョブ作成
  JOB_URI="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run"
  gcloud scheduler jobs create http "${SCHEDULER_JOB_NAME}" \
    --location="${REGION}" \
    --schedule="${SCHEDULER_SCHEDULE}" \
    --time-zone="Asia/Tokyo" \
    --uri="${JOB_URI}" \
    --http-method=POST \
    --oauth-service-account-email="${SERVICE_ACCOUNT}" \
    --project="${PROJECT_ID}" 2>/dev/null || \
  gcloud scheduler jobs update http "${SCHEDULER_JOB_NAME}" \
    --location="${REGION}" \
    --schedule="${SCHEDULER_SCHEDULE}" \
    --time-zone="Asia/Tokyo" \
    --uri="${JOB_URI}" \
    --http-method=POST \
    --oauth-service-account-email="${SERVICE_ACCOUNT}" \
    --project="${PROJECT_ID}"

  echo ""
  echo "=== Cloud Scheduler 設定完了 ==="
  echo "  ジョブ名: ${SCHEDULER_JOB_NAME}"
  echo "  スケジュール: ${SCHEDULER_SCHEDULE} JST (毎日 08:30 JST / 23:30 UTC)"
  echo "  タイムゾーン: Asia/Tokyo"
  echo ""
  echo "  手動テスト実行: gcloud scheduler jobs run ${SCHEDULER_JOB_NAME} --location=${REGION} --project=${PROJECT_ID}"
}

cmd_run() {
  echo "=== Cloud Run Job 手動実行 ==="
  gcloud run jobs execute "${JOB_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --wait
  echo "実行完了（Cloud Logging でログを確認してください）"
}

cmd_sync_local() {
  echo "=== macOS 同期エージェント セットアップ ==="
  REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
  PLIST_SRC="${REPO_DIR}/scripts/com.ai-tips.sync.plist"
  PLIST_DEST="${HOME}/Library/LaunchAgents/com.ai-tips.sync.plist"

  sed "s|REPO_DIR|${REPO_DIR}|g; s|HOME_DIR|${HOME}|g" "${PLIST_SRC}" > "${PLIST_DEST}"

  launchctl unload "${PLIST_DEST}" 2>/dev/null || true
  launchctl load "${PLIST_DEST}"

  echo "  同期エージェント登録完了（毎時実行）"
  echo "  スクリプト: ${REPO_DIR}/scripts/sync_ai_tips.sh"
  echo "  ログ: ${HOME}/Library/Logs/ai-tips-sync.log"
}

# ---- エントリポイント ----------------------------------------------------

case "${1:-}" in
  setup)      cmd_setup      ;;
  secrets)    cmd_secrets    ;;
  deploy)     cmd_deploy     ;;
  schedule)   cmd_schedule   ;;
  run)        cmd_run        ;;
  sync-local) cmd_sync_local ;;
  *)
    echo "使い方: $0 {setup|secrets|deploy|schedule|run|sync-local}"
    exit 1
    ;;
esac
