# 政策ページ起点クロール + PDF/HTMLインデックス化 仕様（案）

## 目的
- 公式一次情報（政策ページ/公式PDF）を安定的に取得し、検索ベースの揺れを補正する。
- 公式のみスコア（official）を基準にしつつ、公式ページ外も含むスコア（mixed）を併用可能にする。
- 既存の検索ベース処理は維持し、並走・比較できる構成にする。

## 前提/範囲
- 公式サイト内の「政策起点URL」を人手で登録する（複数URL）。
- 取得対象は **HTML本文** と **PDF**。動画（YouTube）は現時点で対象外（後回し）。
- robots.txt と利用規約を尊重し、レート制限/エラーを考慮する。
- 更新は管理UIから手動実行する（現行運用と同様）。

## ユースケース
- 管理UIで政党ごとに「政策起点URL」を登録。
- バックエンドで起点URL配下をクロールし、本文/PDFを取得。
- 取得した文書をチャンク化・ベクトル化してRAGに利用。
- スコアリング時にRAGから根拠を取り出し、URLが実在する根拠のみ採用。
- 公式のみ/公式+外部のスコアを公開UIで上下並び比較。

## 要件
### 機能要件
- 政党ごとの「政策起点URL」登録（複数）
- クロール対象の制約
  - 同一公式ドメイン内のみ
  - 起点URL配下（パスプレフィックス）を優先
  - HTMLとPDFのみ保存
- 文書取得・解析
  - HTML本文抽出
  - PDFテキスト抽出
  - 取得失敗理由の記録（404/403/timeout/robots）
- インデックス化
  - 文書をチャンク化
  - ベクトル化（pgvector等、複数Retrieval戦略を試せる実装）
  - 文書/チャンクにURL/タイトル/取得日時/政党IDを付与
- RAG参照
  - トピックごとに上位チャンクを取得
  - LLMに根拠文とURLを渡す
  - URL実在チェック済みのものだけ採用
- index_only
  - 公式インデックスのみで評価（検索ベースは使わない）
- 既存の検索ベース処理は維持・選択可能

### 非機能要件
- 再実行可能（同一URLは再取得せず更新）
- コスト最小化（差分更新、最大URL数の制限）
- 監査可能性（取得元URL/取得日時/抽出方法を保存）

## 管理UI仕様
- 政党編集に「policy_base_urls（複数）」を追加
  - 例: `https://o-ishin.jp/policy/`
  - 政党ドメイン外は登録不可
- 取得ステータス表示
  - 直近クロール日時
  - HTML/PDFの件数
  - エラー件数
- 更新実行ボタン（手動）

## 公開UI仕様
- トピック詳細に「情報の更新日（クロール日時）」を表示する

## データモデル（案）
- `party_policy_sources`
  - `source_id` (uuid)
  - `party_id` (uuid, FK)
  - `base_url` (text)
  - `status` (active/paused)
  - `created_at`, `updated_at`
- `policy_documents`
  - `doc_id` (uuid)
  - `party_id` (uuid, FK)
  - `url` (text, unique)
  - `doc_type` (html/pdf)
  - `title` (text)
  - `content_text` (text)
  - `fetched_at` (timestamptz)
  - `hash` (text)
- `policy_chunks`
  - `chunk_id` (uuid)
  - `doc_id` (uuid, FK)
  - `party_id` (uuid, FK)
  - `chunk_index` (int)
  - `content` (text)
  - `embedding` (vector)
  - `meta` (jsonb: source_url/title/score)

## クロール仕様（案）
- 収集対象
  - base_url配下のHTML
  - HTML内のPDFリンク
- 正規化
  - 末尾スラッシュの正規化
  - リダイレクトの追従（最大2回）
- 制限
  - 1党あたり最大URL数（例: 200）
  - PDFサイズ上限（例: 15MB）
- 取得結果ログ
  - 取得成功/失敗理由をJSONで保存

## RAG参照仕様（案）
- 入力: トピック名 + 党名 + チャンク数N
- 出力: 根拠URL付きの抜粋リスト
- 初期Retrieval戦略: キーワード（BM25等）
- official/mixed:
  - official: 公式ドメインのインデックスのみ
  - mixed: official + 外部（検索ベース）を統合

## 既存検索ベースとの併用方針
- スコアリング時に「検索ベース」「インデックスベース」を切替可能
- 公式のみはインデックスベースを優先、検索は補助
- mixedは検索ベースを併用
- index_onlyは検索を完全無効化

## ログ/監査
- 取得URL/理由/HTTPステータスを保存
- スコアリングの採用根拠URLとチャンクIDを保存

## 検討事項（Open Questions）
- ベクトルDBは pgvector or 外部（FAISS等）か
- PDF抽出の品質改善（レイアウト/表）
- YouTube文字起こしの扱い（話者識別含む）
- 画像PDFは将来的に生成AIの画像認識で読み取り（高コスト/品質検証が必要）
