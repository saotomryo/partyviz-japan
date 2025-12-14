# 開発計画（MVP向け）

## 0. 前提
- 目的: 仕様書.md に基づき、公式一次情報から政党・政治家の立場をスコア化・可視化するMVPを構築する。
- スタック（暫定）: FastAPI + PostgreSQL + Redis（キャッシュ） + 生成AIは補助用途のみ。
- 品質方針: 根拠URL必須・監査可能性重視。バージョン管理（topic_version/calc_version）を表示。

## 1. マイルストーン（AIエージェント優先の再編）
1. 設計固め（週1）  
   - エージェント・キュー設計を優先してI/F確定（discovery/resolve/crawl/score）  
   - DBスキーマ確定（付録Aベース）とマイグレーション雛形作成  
2. データパイプラインPoC（週2-3）  
   - Discovery/Resolution エージェントを疑似実装し、DBへcandidate/verified登録  
   - クロールは allowlist 限定のダミー実装（到達確認・メタ記録のみ）  
   - スコアリングは固定レスポンスで「ルーブリックに沿うJSON」を生成  
3. スコアリング強化（週4-5）  
   - 根拠抽出と信頼度算出のロジックを実装（OpenAI/Geminiを補助利用）  
   - レンジ表示ロジック（P10-P90/中央値）を計算可能にする  
4. バックエンドAPI安定化（週6）  
   - Topics/Positions/Detail GETと管理APIを安定化、OpenAPI整備、pytest整備  
   - 認証（管理APIのAPIキー）と監査ログを追加  
5. フロント可視化PoC（週7）  
   - トピック選択と1軸/2軸の簡易表示、詳細パネルに根拠・抜粋・版本情報  
   - EChartsによる動的切替（mode/entity/レンジ/散布図）

## 2. タスク分解
- 設計
  - [x] API契約の確定（topics/positions/detail + admin）  
  - [ ] DBスキーマのDDLをAlembic/SQLAlchemy等でマイグレーション化  
  - [x] 固定JSONスキーマ（stance_label/score/confidence/evidence/meta）のバリデーション定義
- バックエンド基盤
  - [x] FastAPIプロジェクトセットアップ（settings, logging, dependency wiring）  
  - [x] ルータ分割（public/admin/internal）  
  - [x] モデル/スキーマ定義（Pydantic）  
  - [x] OpenAPIドキュメントとサンプルレスポンス（json_schema_extra で例示）
  - [x] SQLAlchemyモデル定義（party_registry / discovery_events / snapshots / change_history）
- データパイプライン（MVP版）
  - [ ] Discovery/Resolution/Change検知のスタブキュー（in-memory queue可）  
  - [ ] party_registry/party_discovery_events への書き込み処理スタブ  
  - [ ] クロール・採点のダミー処理（固定スコアを返す）
- 可視化UI（後続）
  - [ ] トピック一覧・検索・フィルタUI  
  - [ ] 1軸/2軸表示（散布図/区間）  
  - [ ] 詳細パネル（根拠・抜粋・版本情報）
- 運用・品質
  - [ ] needs_review フローの管理画面（最低限のCRUD）  
  - [ ] 監査ログ・バージョン表示  
  - [ ] CI導入（lint/test）と最低限のユニットテスト

## 3. 実装ガイド（暫定）
- ディレクトリ
  - `backend/src/main.py`: FastAPIエントリポイント
  - `backend/src/api/`: ルータ（public/admin）
  - `backend/src/schemas.py`: Pydanticスキーマ（固定JSON）
  - `backend/src/services/`: Discovery/Resolution/Crawl/Scoreのスタブ
- ルーティング（MVPスタブ）
  - GET `/topics`
  - GET `/topics/{topic_id}/positions`
  - GET `/entities/{entity_id}/topics/{topic_id}/detail`
  - POST `/admin/discovery/run`
  - POST `/admin/resolve/run`
  - POST `/admin/crawl/run`
  - POST `/admin/score/run`
- データ
  - 当面はメモリ内のスタブデータでAPIを疎通。DBは後続で接続。
  - evidenceはURL/quote/quote_start/quote_end/fetched_atを最低限返す。

## 4. リスク・留意点
- データソースは公式一次情報のみ。スクレイピング対象は allowlist 限定。
- 監査可能性: 根拠URL欠如のスコアは必ず「不明/言及なし」にフォールバック。
- 冪等性: discovery/resolveイベントは idempotency_key で重複防止。
- セキュリティ: 管理APIは必ず認証を要求する（MVPではAPIキー想定）。

## 5. 直近アクション（この雛形の次）
1) APIスキーマを確定し、Pydanticモデルを schemas.py に定義  
2) テスト用の固定レスポンスをルータに追加し、OpenAPIを確認  
3) DBマイグレーションツール（Alembic想定）を導入し、付録A DDLを移植  
4) 簡易CI（lint/test）を設定  
5) フロントエンドの技術選定とワイヤーフレーム作成
