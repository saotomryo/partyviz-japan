# 低コスト/無料でのWeb公開（案）

このプロジェクトは「静的フロントエンド + Python(FastAPI) API + PostgreSQL」を前提にしています。  
特にDBは PostgreSQL 依存（例: `JSONB`、enum、DDL）なので、**まずはPostgreSQLを維持する構成**が現実的です。

> 重要: 運用コストの大半はサーバではなく **生成AI API の利用料**になりやすいです。サーバ側は無料枠でも十分に動くケースが多いです。

---

## 推奨（最小コストで現実的）

### 構成
- **フロント**: 静的ホスティング（無料）
  - GitHub Pages / Cloudflare Pages など
- **（任意）バックエンドAPI**: コンテナ実行（無料枠〜従量）
  - Google Cloud Run / Render / Fly.io など
- **（任意）DB**: マネージドPostgreSQL（無料枠あり）
  - Neon / Supabase など

### ねらい
- インフラ保守（OS更新、DBバックアップ、監視）を最小化
- アクセスが少ない間はほぼ無料、増えたら従量でスケール

---

## もっとも安い公開: 静的サイト + JSON（APIを公開しない）

スコアリング/データ生成はローカルで行い、公開は **HTML + `snapshot.json`** だけにします。

### 構成
- 公開: `frontend/`（静的ホスティング）
- データ: `frontend/data/snapshot.json`
- ローカル: FastAPI + PostgreSQL（データ作成用）

### 手順（ローカル→公開）
1. ローカルでバックエンドを起動し、管理UIでトピック/ルーブリック/政党/スコアを作成
2. 管理UIの「スナップショットをダウンロード」または `cd backend && python scripts/export_snapshot.py`
3. 出力された `snapshot.json` を `frontend/data/snapshot.json` に配置してコミット
4. 静的ホスティングへデプロイ（GitHub Pages / Cloudflare Pages 等）

### 公開UIの参照先
- `frontend/app.js` は `./data/snapshot.json` が読める場合は自動でスナップショットを使います
- 強制したい場合は `?source=snapshot`（または `?snapshot=...`）を付与できます
- ルーブリック表示（`rubric.html`）も `snapshot.json` を参照します

---

## 選択肢比較（ざっくり）

### A. Cloud Run + Neon（おすすめ）
- 目安コスト: 低トラフィックなら **ほぼ $0〜数$ /月**（無料枠・従量）
- 長所: スケールゼロ、リソース課金が細かい、運用が楽
- 注意: 初回アクセスでコールドスタート、コンテナ化が必要

### B. Render（お手軽）
- 目安コスト: 無料枠〜低価格（プラン次第）
- 長所: UIが簡単、学習コストが低い
- 注意: 無料枠はスリープ/遅延が出やすい、制限が変わることがある

### C. 1台VM（最小構成だが運用負荷あり）
- 目安コスト: 月数$〜（例: Lightsail/さくら/ConoHa/Hetzner 等）
- 長所: 構成はシンプル（1台でAPI+DB+静的配信も可能）
- 注意: セキュリティ更新、バックアップ、障害対応を自分でやる必要がある

---

## 「構成を小さくする」ための具体策

### 1) フロントとAPIを同一ドメインで配る
静的フロントを FastAPI で配信（または同一コンテナ内に同梱）すると、CORSや環境変数の説明が簡単になります。  
一方で、CDNの恩恵や静的ホスティングの無料枠を活かすなら分離も有効です。

### 2) 管理UIの公開を分ける（推奨）
管理UIは運用上強力な機能（削除/スコア実行/キー設定）を含みます。

- もっとも安全: **管理UIは公開しない（ローカル運用）**
- 公開するなら: 追加の保護（Basic認証 / アクセス制限 / Cloudflare Access など）を検討

※ 現状でも `ADMIN_API_KEY` による保護がありますが、**防御は多層**にしたほうが安全です。

### 3) DBをSQLiteに置き換える（非推奨・要改修）
構成は軽くなりますが、現状のマイグレーション/型がPostgreSQL依存のため、変更コストが高いです。

---

## 公開時に必要になる設定（共通）

- `.env` はコミットしない（ホスティング側の環境変数に設定）
- 少なくとも次を設定
  - `DATABASE_URL`
  - `ADMIN_API_KEY`（管理APIを有効化するなら）
  - `GEMINI_API_KEY` / `OPENAI_API_KEY`（利用する方）
- `PUBLIC_API_BASE`（フロントが参照するAPIのベースURL）

※ 静的サイト + JSON 方式（APIを公開しない）の場合、公開環境にAPIキーは不要です。

---

## まずのおすすめ手順（運用を軽くする）

1. DB: Neon/Supabase の無料枠で PostgreSQL を作成 → `DATABASE_URL` を取得
2. API: Cloud Run / Render で FastAPI を起動（環境変数に `DATABASE_URL` 等を登録）
3. 初期化: `alembic upgrade head` を実行（デプロイ時のジョブ、または初回だけ手動）
4. フロント: GitHub Pages/Cloudflare Pages で `frontend/` を公開し、`PUBLIC_API_BASE` をAPIのURLに設定

---

## 次に詰めたいこと（あなたに確認したい）

- 管理UIは「公開」しますか？（公開しない/限定公開/公開）
- 目標のアクセス規模（例: 1日100PV、1000PV など）
- 「独自ドメイン」を使いますか？
