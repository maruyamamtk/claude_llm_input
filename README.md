# AI Tips Collector

生成AI活用・AIコーディングに関する最新情報を毎朝 **08:30 JST** に自動収集し、Obsidianノートへの保存とメール通知を行うエージェント。

- **収集源**: 公式ブログ / RSS / GitHub Releases / X（Twitter）
- **要約**: Claude API（claude-sonnet-4-6）で日本語要約
- **通知**: Gmail API 経由でメール送信
- **Q&A**: 収集したドキュメントに対してCLIで質問可能
- **実行基盤**: Cloud Run Jobs + Cloud Scheduler（GCP）

---

## 目次

1. [前提条件](#前提条件)
2. [ローカル開発環境のセットアップ](#ローカル開発環境のセットアップ)
3. [Gmail OAuth2 初回認証](#gmail-oauth2-初回認証)
4. [ローカルでの動作確認](#ローカルでの動作確認)
5. [本番GCPデプロイ（初回）](#本番gcpデプロイ初回)
6. [運用手順](#運用手順)
7. [情報ソースのカスタマイズ](#情報ソースのカスタマイズ)
8. [トラブルシューティング](#トラブルシューティング)

---

## 前提条件

| ツール | バージョン |
|--------|-----------|
| Python | 3.12+ |
| [uv](https://docs.astral.sh/uv/) | 最新 |
| [Docker](https://www.docker.com/) | 本番デプロイ時のみ必要 |
| [gcloud CLI](https://cloud.google.com/sdk) | 本番デプロイ時のみ必要 |

**GCPリソース（本番デプロイ時）:**
- GCPプロジェクト（`keiba-prediction-1768734113`）
- 以下のAPIを有効化済み:
  - Cloud Run API
  - Cloud Scheduler API
  - Secret Manager API
  - Artifact Registry API
  - Cloud Storage API

---

## ローカル開発環境のセットアップ

### 1. 依存パッケージのインストール

```bash
uv sync
```

### 2. Playwrightブラウザのインストール

```bash
uv run playwright install chromium
```

### 3. 環境変数の設定

プロジェクトルートに `.env` ファイルを作成します。

```bash
cp .env.example .env   # .env.example が存在する場合
# または以下の内容で手動作成
```

**.env ファイルの内容:**

```dotenv
ANTHROPIC_API_KEY=sk-ant-...          # Anthropic APIキー（必須）
GITHUB_TOKEN=ghp_...                  # GitHub PAT（任意、レート制限緩和用）
GMAIL_CREDENTIALS_PATH=credentials.json
GMAIL_TOKEN_PATH=token.json
GMAIL_SENDER_ADDRESS=your-email@gmail.com
OBSIDIAN_NOTES_DIR=~/Desktop/obsidian_note/08_AINews
```

> `.env` はGitで管理されません。APIキーをコミットしないでください。

---

## Gmail OAuth2 初回認証

Gmail送信にはOAuth2認証が必要です。**初回のみ**、ブラウザが使えるローカル環境で実行してください。

### 1. GCPコンソールで認証情報を作成

1. [GCPコンソール](https://console.cloud.google.com/) → APIs & Services → Credentials
2. 「OAuth 2.0 クライアント ID」を作成（アプリケーション種類: **デスクトップアプリ**）
3. `credentials.json` をダウンロードしてプロジェクトルートに配置

### 2. OAuth2フローを実行してトークンを生成

```bash
ANTHROPIC_API_KEY=dummy uv run python -c "
from service.gmail_sender import GmailSender
GmailSender()._get_credentials()
print('token.json を生成しました')
"
```

ブラウザが開くので、対象のGoogleアカウントでログインして権限を許可してください。`token.json` が生成されれば完了です。

> `token.json` もGitで管理されません。Secret Managerに登録して本番環境で使用します（[本番GCPデプロイ](#本番gcpデプロイ初回) 参照）。

---

## ローカルでの動作確認

### メイン処理を手動実行

```bash
uv run python main.py
```

正常終了すると以下が実行されます:
- `OBSIDIAN_NOTES_DIR` に `YYYY-MM-DD_ai_tips.md` が保存される
- `GMAIL_SENDER_ADDRESS` 宛にメールが送信される

### Q&A機能を使用

```bash
uv run python qa.py "Claude Code の hooks 機能とは何ですか？"
```

### テストを実行

```bash
uv run pytest
```

---

## 本番GCPデプロイ（初回）

初回セットアップは以下の順序で実行します。

```
setup → secrets → deploy → schedule → run（動作確認）
```

### Step 1: GCPにログイン

```bash
gcloud auth login
gcloud config set project keiba-prediction-1768734113
```

### Step 2: Artifact Registry + Cloud Run Job を作成

```bash
./deploy.sh setup
```

実行されること:
- Artifact Registry リポジトリ作成
- GCS バケット作成（Obsidianファイルの保存先）
- Dockerイメージのビルド & プッシュ
- Cloud Run Job の作成

### Step 3: Secret Manager にシークレットを登録

```bash
export ANTHROPIC_API_KEY="sk-ant-..."   # Anthropic APIキー
export GITHUB_TOKEN="ghp_..."           # GitHub PAT（任意）
export GMAIL_TOKEN_FILE="token.json"    # ローカルで生成した token.json のパス

./deploy.sh secrets
```

登録されるシークレット:

| シークレット名 | 内容 |
|--------------|------|
| `anthropic-api-key` | Anthropic API キー |
| `github-token` | GitHub Personal Access Token |
| `gmail-token` | Gmail OAuth2 `token.json` の内容（JSON文字列） |

また、Cloud Run Jobのデフォルトコンピュートサービスアカウントに `secretmanager.secretAccessor` ロールが付与されます。

### Step 4: Secrets設定込みでジョブを更新

```bash
./deploy.sh deploy
```

実行されること:
- Dockerイメージの再ビルド & プッシュ
- Cloud Run Job を `--set-secrets` フラグ付きで更新（`ANTHROPIC_API_KEY`, `GITHUB_TOKEN`）
- 環境変数 `GCP_PROJECT_ID` の設定（起動時に `gmail-token` を Secret Manager から取得するために使用）

### Step 5: Cloud Scheduler を設定

```bash
./deploy.sh schedule
```

作成されるスケジューラ:

| 項目 | 値 |
|------|-----|
| ジョブ名 | `ai-tips-collector-daily` |
| スケジュール | `30 23 * * *`（UTC）= 毎日 **08:30 JST** |
| タイムゾーン | `Asia/Tokyo` |
| ターゲット | Cloud Run Job `ai-tips-collector` |

### Step 6: 手動実行でE2E確認

```bash
./deploy.sh run
```

正常終了後、以下を確認してください:
- メールが届くこと
- Cloud Logging にエラーがないこと

```bash
# Cloud Loggingでジョブのログを確認
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="ai-tips-collector"' \
  --project=keiba-prediction-1768734113 \
  --limit=50 \
  --format="table(timestamp, severity, textPayload)"
```

---

## 運用手順

### コードを変更して再デプロイ

```bash
./deploy.sh deploy
```

### Cloud Schedulerを手動でトリガー

```bash
gcloud scheduler jobs run ai-tips-collector-daily \
  --location=asia-northeast1 \
  --project=keiba-prediction-1768734113
```

### Gmailトークンを更新する

`token.json` の有効期限が切れた場合（通常はリフレッシュトークンで自動更新されますが、OAuth認証をやり直す場合）:

```bash
# 1. ローカルでトークンを再生成
rm token.json
uv run python -c "from service.gmail_sender import GmailSender; GmailSender()._get_credentials()"

# 2. Secret Manager に新しいトークンを登録
export GMAIL_TOKEN_FILE="token.json"
./deploy.sh secrets

# 3. ジョブを再デプロイ（不要な場合もあり）
./deploy.sh deploy
```

### シークレットを個別に更新する

```bash
# anthropic-api-key を更新
echo -n "新しいAPIキー" | gcloud secrets versions add anthropic-api-key \
  --data-file=- \
  --project=keiba-prediction-1768734113

# 更新後はジョブの次回実行から自動的に新しいバージョンが使われます
```

---

## 情報ソースのカスタマイズ

`config.yaml` を編集することで、収集対象を追加・変更できます。変更後は `./deploy.sh deploy` で反映されます。

```yaml
# ブログ/RSSソースを追加
blog_sources:
  - name: 新しいブログ
    url: https://example.com/blog
    type: html  # または rss

# GitHubリポジトリを追加
github_repos:
  - repo: owner/repo-name
    description: 説明

# Xアカウントを追加
twitter_accounts:
  - handle: username
    description: 説明
```

収集数や閾値は環境変数（または `.env`）で調整できます:

```dotenv
COLLECTOR__MAX_ARTICLES_PER_SOURCE=10   # ソースごとの最大収集件数
COLLECTOR__FILTER_MIN_SCORE=0.6         # 関連度フィルタの最低スコア（0.0〜1.0）
COLLECTOR__SUMMARY_MAX_CHARS=500        # 要約の最大文字数
```

---

## トラブルシューティング

### `credentials.json が見つかりません` エラー

Gmail初回認証が完了していません。[Gmail OAuth2 初回認証](#gmail-oauth2-初回認証)を実施してください。

### Cloud Run Job が失敗する

```bash
# 直近の実行ログを確認
gcloud logging read \
  'resource.type="cloud_run_job" AND severity>=ERROR' \
  --project=keiba-prediction-1768734113 \
  --limit=20
```

よくある原因:
- `Secret Manager からのロード失敗`: シークレット名のタイポ、またはサービスアカウントにロールが未付与 → `./deploy.sh secrets` を再実行
- `Gmail token expired`: [Gmailトークンを更新する](#gmailトークンを更新する)を参照

### Xスクレイピングがタイムアウトする

X（Twitter）はログインを要求する場合があります。収集はベストエフォートで、失敗しても他ソースの収集・メール送信は続行されます。

### ローカルで `ANTHROPIC_API_KEY` エラーが出る

`.env` ファイルが存在するか、`ANTHROPIC_API_KEY` が設定されているか確認してください。

```bash
grep ANTHROPIC_API_KEY .env
```
