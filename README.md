# 各政党の考え方を可視化するアプリケーション

仕様書に基づき、政党・政治家の立場を公式一次情報から可視化するアプリケーションの開発リポジトリです。現時点ではMVP実装に向けた計画とバックエンドの最小雛形を含みます。

- 仕様: 仕様書.md
- 開発計画: docs/development-plan.md
- バックエンド雛形: backend/

## セットアップ（開発想定）

```bash
cd backend
pip install -r requirements.txt  # グローバル/共有の仮想環境でも可
cp ../.env.example ../.env      # APIキーとDATABASE_URLを設定する
uvicorn src.main:app --reload
```

個別設定については `docs/local-config.md` を参照し、`.env` を各自で作成してください（Git管理外）。

### フロントエンド（静的Web UI）
```bash
# 別ターミナルで
cd frontend
python -m http.server 5173
# ブラウザで http://localhost:5173 にアクセス
```

バックエンドAPIが 8000 番で起動している前提です。ポートを変える場合は `frontend/app.js` の `API_BASE` を変更してください。

## DBマイグレーション（Alembic）
```bash
cd backend
export DATABASE_URL=postgresql+psycopg://partyviz:partyviz@localhost:5432/partyviz
alembic upgrade head
```

## 想定スタック（暫定）
- FastAPI / Uvicorn（APIサーバ）
- PostgreSQL（スコア・レジストリ管理）
- Redis もしくは DB キャッシュ（可視化API高速化）
- 生成AI: OpenAI API と Google Gemini を併用（`.env` に API キーを保存）
- ORM: SQLAlchemy（`backend/src/db/models.py` にparty系モデル定義済み、adminでCRUDスタブあり）
- 管理API: `ADMIN_API_KEY` を設定すると `X-API-Key` ヘッダで保護（未設定時は開発用として無認証）
- エージェントPoC: `backend/scripts/agent_poc.py` で Discovery→Resolution→Crawler→相対スコア算出を通し検証可能（OpenAI/Geminiキーがあれば実LLMで実行）
- 依存追加が必要な場合はネットワーク制約に注意（bs4は未使用化済み）

## 次ステップの例
- docs/development-plan.md に従い、APIのスキーマとDBマイグレーションを実装
- データパイプライン（Discovery/Resolution/Crawl/Score）の実装着手
- フロントエンドのUIプロトタイプ作成
