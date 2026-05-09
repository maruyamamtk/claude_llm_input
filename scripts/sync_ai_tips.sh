#!/usr/bin/env bash
# GCS → ローカル Obsidian ノート 一方向同期
set -euo pipefail

GCS_PATH="gs://ai-tips-obsidian-keiba-prediction-1768734113/08_AINews/"
LOCAL_PATH="$HOME/Desktop/obsidian_note/08_AINews/"

mkdir -p "${LOCAL_PATH}"

/opt/homebrew/bin/gsutil -o "GSUtil:parallel_process_count=1" -m rsync -r "${GCS_PATH}" "${LOCAL_PATH}"
echo "$(date '+%Y-%m-%d %H:%M:%S') 同期完了"
