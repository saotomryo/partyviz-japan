# ローカル個別設定の管理方針

## 方針
- APIキーやDB接続情報などの個別設定はリポジトリ外で管理し、Gitには含めません。
- `.env.example` をテンプレートとし、各自が `.env` を作成します（`.env` は `.gitignore` 済み）。
- 必要に応じて環境ごとの `.env.*` を作成しても構いません（例: `.env.dev`）。`.env.*` も `.gitignore` 済みです。

## 必須項目（例）
- `OPENAI_API_KEY` : OpenAIのAPIキー
- `GEMINI_API_KEY` : Google GeminiのAPIキー
- `DATABASE_URL`   : PostgreSQL接続文字列（psycopg v3形式）  
  例) `postgresql+psycopg://partyviz:partyviz@localhost:5432/partyviz`
- `VITE_API_BASE`  : （将来用）フロントエンドが呼び出すバックエンドAPIのURL（開発時は `http://localhost:8000`）
- `ADMIN_API_KEY`  : 管理API用APIキー（開発時は未設定なら無認証、設定すると `X-API-Key` ヘッダ必須）
- `USE_DUMMY_AGENTS`: `true` ならダミーエージェントを使用。`false` で実処理（LLM検索 + HTTPフェッチ + LLMスコアリング）。
- `AGENT_SEARCH_PROVIDER` / `AGENT_SCORE_PROVIDER`: PoCで利用するプロバイダ選択（auto|gemini|openai）。
- `OPENAI_SEARCH_MODEL` / `OPENAI_SCORE_MODEL` / `GEMINI_SEARCH_MODEL` / `GEMINI_SCORE_MODEL`: PoCのモデル指定。

## 手順
1) ルートにある `.env.example` をコピーして `.env` を作成  
   `cp .env.example .env`
2) 上記必須項目に値を設定
3) バックエンド起動前に `.env` を読み込む（FastAPIは python-dotenv で自動読み込み）
4) Alembic実行時も同一の `.env` / `DATABASE_URL` を利用

## 管理UIの保存場所
- `admin.html` の API Base / API Key / モデル名などはブラウザの localStorage に保存されます（`.env` とは別）。
- 公開UIのテーマ選択（深夜/朝/昼）も localStorage に保存されます。

## Git管理の注意
- `.env`, `.env.*` はコミットしないでください（既に `.gitignore` に登録済み）。
- 個別設定を共有する場合は、このドキュメントに追記するか、別途セキュアな共有手段を使ってください。
