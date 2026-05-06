# AI Tips Collector Agent — 仕様書

## 概要

生成AI活用・AIコーディングに関する最新情報・実践的Tipsを毎朝自動収集し、Obsidianノートへのファイル出力とメール通知を行うエージェント。加えて、収集したドキュメントに対してユーザーが質問できるQ&A機能を提供する。

---

## 1. 機能一覧

| ID  | 機能名               | 説明 |
|-----|----------------------|------|
| F01 | 情報収集             | 複数ソースから最新情報を収集・スクレイピング |
| F02 | 要約・整形           | Claude APIで日本語要約（5分以内で読めるボリューム） |
| F03 | Obsidianへの出力     | `~/Desktop/obsidian_note/08_AINews/` にMarkdownファイルを保存 |
| F04 | メール通知           | Gmail API経由で marumaru5922@gmail.com へ送信 |
| F05 | Q&A機能              | ドキュメントに対してユーザーが質問→Claude APIで回答 |
| F06 | スケジュール実行      | 毎朝8:30（JST）にCloud Schedulerが自動起動 |

---

## 2. 情報ソース一覧

### 2-1. 公式ブログ（RSS / HTML スクレイピング）

| ソース | URL |
|--------|-----|
| Anthropic News | https://www.anthropic.com/news |
| OpenAI News | https://openai.com/news/ |
| Google DeepMind Blog | https://deepmind.google/discover/blog/ |
| DeepLearning.AI The Batch | https://www.deeplearning.ai/the-batch/ |

### 2-2. GitHubリリースノート（GitHub API）

| リポジトリ | 用途 |
|-----------|------|
| `anthropics/anthropic-sdk-python` | Anthropic SDK更新 |
| `anthropics/claude-code` | Claude Code更新 |
| `openai/openai-python` | OpenAI SDK更新 |
| `openai/openai-cookbook` | OpenAI実践レシピ |
| `BerriAI/litellm` | LLMラッパー動向 |

### 2-3. テックブログ（RSS / Playwright スクレイピング）

| ソース | URL |
|--------|-----|
| Simon Willison's Weblog | https://simonwillison.net/ |
| Latent Space | https://www.latent.space/ |
| Zenn（AIタグ） | https://zenn.dev/topics/ai |
| note（AIタグ） | https://note.com/hashtag/AI |

### 2-4. X（Twitter）アカウント — Playwright スクレイピング

| アカウント | 属性 |
|-----------|------|
| @anthropic | Anthropic公式 |
| @alexalbert__ | Claude Code開発リード |
| @OpenAI | OpenAI公式 |
| @sama | Sam Altman（OpenAI CEO） |
| @karpathy | Andrej Karpathy（AI研究者） |
| @simonw | Simon Willison（OSS開発者） |
| @swyx | shawn（AI Engineer Weekly） |
| @emollick | Ethan Mollick（AI活用研究） |
| @mattshumer_ | Matt Shumer（AI実践家） |

> 初期リストとして設定。後から `config.yaml` を編集して追加・削除可能。

---

## 3. 出力仕様

### 3-1. Obsidianファイル

- **保存先**: `~/Desktop/obsidian_note/08_AINews/`
- **ファイル名**: `YYYY-MM-DD_ai_tips.md`
- **構成**:

```markdown
# AI Tips & News — YYYY-MM-DD

## 今日のハイライト（3行サマリー）
...

## トピック別まとめ

### Claude Code / Anthropic
#### [タイトル](URL)
> ソース: anthropic.com | 2026-05-06
概要・解説（300〜500字）

### OpenAI
...

### X（注目ツイート）
...

## 今日の実践Tips
箇条書きで3〜5項目

## Q&A ログ（当日分）
ユーザーが質問した内容と回答を自動追記
```

### 3-2. メール

- **件名**: `[AI Tips] YYYY-MM-DD の注目情報`
- **本文**: Obsidianファイルの内容をHTML変換して送信
- **送信元**: marumaru5922@gmail.com（Gmail API OAuth2）
- **送信先**: marumaru5922@gmail.com

---

## 4. Q&A 機能（F05）

### フロー

1. ユーザーが CLI で質問を入力:
   ```bash
   python qa.py "MCP の Tool と Resource の違いは何ですか？"
   ```
2. エージェントが以下を参照して回答を生成:
   - context7 MCP（公式ドキュメント検索）
   - 過去に収集したObsidianファイル（ローカル参照）
3. 回答をターミナルに表示 + 当日の `YYYY-MM-DD_ai_tips.md` の「Q&A ログ」セクションに追記

### 回答フォーマット（Markdown）

```markdown
**Q**: MCP の Tool と Resource の違いは何ですか？
**A**: ...（300字以内の解説）
**参照**: [公式ドキュメント URL]
```

---

## 5. システム構成

chapter6（arxiv-researcher）の **Chain / Agent / Service 3層構造** を採用する。

```
ai-tips-collector/
├── agent/
│   ├── collect_agent.py      # 収集〜評価〜レポート生成のLangGraphグラフ
│   └── qa_agent.py           # Q&A LangGraphグラフ
├── chains/
│   ├── blog_chain.py         # RSSフィード・HTMLスクレイピング
│   ├── github_chain.py       # GitHub Releases API取得
│   ├── twitter_chain.py      # Playwright経由のX取得
│   ├── filter_chain.py       # 実践的Tips関連度フィルタリング（LLM評価）
│   ├── summarizer_chain.py   # 個別記事の日本語要約
│   ├── reporter_chain.py     # 最終レポート統合生成
│   └── prompts/              # .promptファイル（LLMへの指示を外部化）
│       ├── filter.prompt
│       ├── summarize.prompt
│       └── reporter_system.prompt
├── models/
│   ├── article.py            # 収集記事のPydanticモデル
│   └── report.py             # レポートのPydanticモデル
├── service/
│   ├── obsidian_writer.py    # Markdownファイル書き出し
│   └── gmail_sender.py       # Gmail API メール送信
├── settings.py               # pydantic-settings による設定管理
├── config.yaml               # ソース・アカウントリスト（後から編集可能）
├── qa.py                     # Q&A CLIエントリーポイント
├── main.py                   # 定期実行エントリーポイント
├── pyproject.toml            # uv によるパッケージ管理
└── Dockerfile
```

### LangGraph エージェントフロー（collect_agent）

```
[blog_chain / github_chain / twitter_chain]
        ↓ 並列収集
[filter_chain]  ← 実践Tipsとして関連性をLLMで評価
        ↓
[summarizer_chain]  ← 個別記事を日本語要約
        ↓
[task_evaluator]  ← 「十分な情報が集まったか」を評価
        ↓（不足なら追加収集ループ、最大3回）
[reporter_chain]  ← 最終レポート生成
        ↓
[obsidian_writer / gmail_sender]
```

---

## 6. インフラ構成

| 項目 | 内容 |
|------|------|
| 実行環境 | Google Cloud Run Jobs |
| スケジューラ | Cloud Scheduler（毎日 8:30 JST = 23:30 UTC） |
| GCPプロジェクト | `keiba-prediction-1768734113` |
| コンテナ | Docker（Python 3.12-slim ベース） |
| シークレット管理 | Google Secret Manager（Gmail OAuth token, Claude API key） |
| ログ | Cloud Logging |

---

## 7. 使用技術・ライブラリ

| 用途 | 技術 | chapter6との対応 |
|------|------|----------------|
| エージェントオーケストレーション | **LangGraph** | `StateGraph` ベースのフロー管理 |
| LLMチェーン | **LangChain + langchain-anthropic** | `ChatAnthropic` + `ChatPromptTemplate` |
| LLMモデル | `claude-sonnet-4-6`（要約・評価・レポート） | chapter6の `reporter_llm` パターン |
| 設定管理 | **pydantic-settings** + `.env` | chapter6の `settings.py` をそのまま踏襲 |
| パッケージ管理 | **uv** + `pyproject.toml` | chapter6と同じ |
| RSS取得 | `feedparser` | chapter6 deps にすでに存在 |
| Webスクレイピング | `playwright`（ライブラリ直接利用） | X/動的サイト用 |
| GitHub API | `httpx` | リリースノート取得 |
| メール送信 | `google-auth` + `googleapiclient` | Gmail API OAuth2 |
| データモデル | `pydantic` | chapter6の `ReadingResult` と同パターン |
| リトライ制御 | `tenacity` | chapter6 deps にすでに存在 |
| ドキュメント検索（Q&A） | context7 MCP | Q&A機能での公式ドキュメント参照 |

---

## 8. セキュリティ考慮

- APIキー・OAuth tokenはすべて **Secret Manager** で管理し、コードにハードコードしない
- Xスクレイピングは利用規約の範囲内で実施（ログイン不要の公開投稿のみ）
- GCPサービスアカウントは最小権限原則（Cloud Run + Secret Manager アクセスのみ）

---

## 9. 未確定事項（実装時に決定）

- [ ] X監視アカウントの追加・除外（`config.yaml` で随時管理）
- [ ] メール本文のHTML/プレーンテキスト選択
- [ ] Q&A履歴の長期保存方法（ファイルのみ or Cloud Storageにバックアップ）

---

## 10. 開発フェーズ案

| Phase | 内容 |
|-------|------|
| Phase 1 | 公式ブログ + GitHub収集 → Obsidian出力（最小構成） |
| Phase 2 | Gmail通知追加 |
| Phase 3 | Xスクレイピング追加 |
| Phase 4 | Q&A CLI機能追加 |
| Phase 5 | Cloud Run + Cloud Schedulerデプロイ |
