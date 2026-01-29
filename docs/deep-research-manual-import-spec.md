# Deep Research（手作業）→ 政策インデックス取り込み 仕様（案A）

## 目的
クローラー（HTML/PDF）だけでは拾いきれない・拒否される・“最新ページがどれか”が曖昧、といったケースに対して、**ChatGPT / Gemini の Deep Research（UI）で人手収集した一次情報**を、既存の「政策インデックス（`policy_documents`/`policy_chunks`）」へ取り込み、**index_only のスコアリング精度と監査性**を上げる。

将来的に Deep Research API（自動収集）を追加しても、**同じ取り込みスキーマ**に正規化すれば差し替え可能とする。

## 基本方針（分離）
- **収集（Research）**: 人手 + Deep Research（UI）で一次情報を特定・抜粋・要約
- **取り込み（Index）**: 収集成果を `policy_documents`/`policy_chunks` に保存（案A）
- **スコアリング（Score）**: 既存の `index_only` を優先し、必要なら検索ベース（mixed）を併用

## スコープ
### すること
- Deep Research（UI）で作った成果物を、機械可読な「リサーチパック（JSON）」として保存する
- リサーチパックをDBへ取り込めるようにする（後続実装）
- 取り込んだテキストを `policy_chunks` 検索に載せ、スコアリングの根拠候補として利用する（既存機構を活用）
- “古い公約がサイトに残っている”問題を、**deprecated扱い**で混入を抑制する

### しないこと（当面）
- Deep Research API の直接呼び出し（後で追加）
- robots.txt/利用規約を無視した自動スクレイピング
- 著作物の大量再配布（引用の範囲に留める／運用で統制）

## 用語
- **リサーチパック**: Deep Research（UI）の結果を、取り込み用に整形したJSON
- **アイテム**: 1つの根拠（URL + 引用 + その意味）
- **ドキュメント**: DBの `policy_documents` 1レコード（案Aでは “deep_research由来の擬似文書” を作る）

## 期待する運用フロー（手作業）
1) 管理UIで政党を選び、`official_home_url` と `policy_base_urls` を最新に揃える（可能なら）
2) ChatGPT/Gemini の Deep Research（UI）で、各党について以下を収集
   - 最新の政策ページ（政策一覧、選挙公約、重点政策、マニフェストPDF等）
   - ページ更新日・版・選挙名が分かる要素
   - トピックごとの該当箇所（引用できる短い抜粋）
3) 収集結果を「リサーチパックJSON」として保存
4) 取り込み（後続実装）
   - 既存クローラー結果は残しつつ、deep_research由来ドキュメントを追加（または置換モード）
5) 管理UIで `index_only` をONにしてスコアリング実行

## Deep Research用プロンプト作成（機能/運用）
Deep Research（UI）に投げるプロンプトを「毎回手で書く」運用だと品質がぶれやすいので、アプリ側（将来の管理UI）で **プロンプト雛形を生成**できるようにする。

### 目的
- 収集の観点（最新・一次・根拠URL/引用必須）を強制する
- 出力を `リサーチパック（JSON）` に揃えて、後段の取り込み（案A）へそのまま流せるようにする
- 将来の Deep Research API 連携時に、同等の指示を“機械的に”発行できるようにする

### 入力（プロンプト生成に必要な情報）
- 政党情報（最低限）
  - `party_name_ja`
  - `official_home_url`（あれば）
  - `allowed_domains`（公式扱いのドメイン）
  - `policy_base_urls`（起点URL、あれば）
- トピック情報（任意だが推奨）
  - `topic_id` / `topic_name` / `topic_description`
  - ルーブリックの軸ラベル（任意）
- 出力方針
  - `strict_official_only`（true/false）
  - `include_deprecated`（true/false）
  - `max_items_per_topic`（例: 3）

### 出力（生成されるプロンプトの種類）
- **(P1) ソース特定プロンプト**: 「最新の公式ページ/PDFがどれか」を確定する
- **(P2) トピック別抽出プロンプト**: トピックごとに引用と主張を抽出する
- **(P3) JSON整形プロンプト**: リサーチパックJSONとして出力させる（または P2 と統合）

### プロンプト雛形（コピペ用）
#### (P1) 最新ソース特定（政党単位）
```text
あなたは日本の政党の公式一次情報を調査するリサーチャーです。
目的: 「最新の政策/公約」を示す公式ソースURLを特定して、根拠付きで列挙してください。

対象政党:
- name_ja: {{party_name_ja}}
- official_home_url: {{official_home_url}}
- allowed_domains: {{allowed_domains_csv}}
- policy_base_urls (if any): {{policy_base_urls_multiline}}

ルール:
- 可能な限り allowed_domains 内の公式一次情報を優先（HTML/PDF）。
- 最新版がどれか曖昧な場合は、候補を複数出し「なぜ最新と判断したか」を短く書く。
- 参照したURLを必ず列挙（推測でURLを作らない）。
- 古い選挙の公約が残っている場合は「deprecated候補」として分離して列挙。

出力形式（Markdown）:
1) Latest candidates（URL + タイトル + 更新/公開日の手がかり + 判定理由）
2) Deprecated candidates（URL + 理由）
3) Notes（制限・不明点）
```

#### (P2) トピック別の引用抽出（政党×トピック）
```text
あなたは日本の政党の公式一次情報から、指定トピックに関する記述を抽出します。
目的: 引用（短い抜粋）と、その引用が意味する主張（claim）を作り、URLとセットで提示してください。

対象政党:
- name_ja: {{party_name_ja}}
- allowed_domains: {{allowed_domains_csv}}

参照してよいURL（ここに限定）:
{{approved_source_urls_multiline}}

トピック:
- topic_id: {{topic_id}}
- topic_name: {{topic_name}}
- topic_description: {{topic_description}}

ルール:
- 可能なら1〜{{max_items_per_topic}}件に絞る（最重要→補足）。
- quote は短く（1〜3文程度）、必ず source_url を付ける。
- 引用が見つからない場合は「見つからない」と明示し、推測で埋めない。
- 古い公約だと判断したものは deprecated=true とし理由を書く。

出力（箇条書き）:
- source_url:
  source_title:
  quote:
  claim:
  fetched_at: （あなたが確認した日時、ISO8601）
  deprecated: true/false
  deprecated_reason: (optional)
```

#### (P3) リサーチパックJSON整形（最終出力）
```text
次の情報を、指定スキーマの「リサーチパックJSON」に整形して出力してください。
注意: JSON以外は出力しないでください。

スキーマ（必須フィールド）:
- format: "partyviz_research_pack"
- version: 1
- generated_at: ISO8601
- generator: "chatgpt_deep_research" または "gemini_deep_research"
- parties: [{ party_name_ja, party_id?, items:[{ source_url, source_title?, fetched_at?, source_type?, topic_ids?, quote?, claim?, deprecated?, deprecated_reason? }] }]

入力（itemsの材料）:
{{extracted_items_multiline}}
```

### UI整理との関係（推奨）
プロンプト生成とリサーチパック取り込みは「政党データ管理」に属するため、`admin_parties.html` 側にまとめる。
- 例: 「プロンプト生成（コピペ）」「リサーチパック貼り付け/アップロード」「取り込み（append）」を同一カードに配置

## リサーチパック仕様（JSON）
### ルート
- `format`: 固定文字列 `"partyviz_research_pack"`
- `version`: 整数（初版 `1`）
- `generated_at`: ISO8601（例: `"2026-01-28T12:34:56+09:00"`）
- `generator`: `"chatgpt_deep_research" | "gemini_deep_research" | "manual"`
- `notes`（任意）: 全体メモ
- `parties`: 配列

### parties[]
- `party_id`（推奨）: UUID（DBの `party_registry.party_id`）
  - 手作業でUUIDが分からない場合は `party_name_ja` を必須にし、取り込み時に名前マッチ（曖昧ならエラー）
- `party_name_ja`（必須）: 例 `"自由民主党"`
- `collected_at`（任意）: ISO8601
- `items`: 配列

### items[]
監査性のため、**URLと引用（quote）を最優先**に保存する。
- `source_url`（必須）: 取得元URL
- `source_title`（任意）: ページタイトル
- `source_published_at`（任意）: ページ側に明示がある場合（ISO8601推奨、日付だけでも可）
- `fetched_at`（任意）: 自分が確認した時刻（ISO8601）
- `source_type`（任意）: `"official_html" | "official_pdf" | "press_release" | "other"`
- `topic_ids`（任意）: 例 `["ai","fiscal_discipline"]`（既存 topic_id と対応）
  - 将来的に “トピック未確定でも一旦取り込む” を許すため、任意にする
- `quote`（推奨）: そのまま引用できる短い抜粋（出典URL必須）
- `quote_context`（任意）: 引用の前後要約（自分用）
- `claim`（推奨）: 引用が意味する主張（短文）
- `reliability`（任意）: `0.0〜1.0` の主観スコア（公式一次なら高め）
- `tags`（任意）: 例 `["latest_manifesto","election_2026"]`
- `deprecated`（任意）: boolean
  - 例: 「前回選挙の公約だがサイトに残っている」→ `deprecated=true`
- `deprecated_reason`（任意）: 例 `"old_election_promise_kept_on_site"`

### 例
```json
{
  "format": "partyviz_research_pack",
  "version": 1,
  "generated_at": "2026-01-28T12:34:56+09:00",
  "generator": "chatgpt_deep_research",
  "notes": "2026年選挙向けに更新",
  "parties": [
    {
      "party_name_ja": "自由民主党",
      "party_id": "8b1c718c-5018-4666-97b3-0ad28b0de223",
      "items": [
        {
          "source_url": "https://www.jimin.jp/policy/",
          "source_title": "政策",
          "fetched_at": "2026-01-28T10:00:00+09:00",
          "topic_ids": ["ai"],
          "quote": "（引用）…",
          "claim": "AI利活用を推進する",
          "source_type": "official_html",
          "reliability": 0.95,
          "deprecated": false
        }
      ]
    }
  ]
}
```

## DB取り込み仕様（案A）
### 書き込み先
既存の政策インデックスに統合する。
- `policy_documents`
  - `url`: `source_url` をそのまま保存（ユニーク）
  - `doc_type`: `"deep_research"`（既存は `"html"|"pdf"|...` だが文字列運用なので追加してOK）
  - `title`: `source_title` など
  - `content_text`: 検索に乗るテキスト（推奨: `claim` + `quote` + `quote_context` を連結）
  - `fetched_at`: `items[].fetched_at`（無ければ取り込み時刻）
  - `hash`: `content_text` のハッシュ（既存と同様）
- `policy_chunks`
  - `content`: チャンク化した `content_text`
  - `meta`: 少なくとも以下を持つ
    - `source_url`
    - `source_title`
    - `generator`
    - `topic_ids`（あれば）
    - `deprecated` / `deprecated_reason`（あれば）

### 取り込みモード
運用上は3モードを想定。
- `append`（既定）: 既存インデックスを残し、deep_research由来ドキュメントを追加
- `replace_party`（将来）: 党単位で、deep_research由来ドキュメント以外を削除して置換
- `replace_url`（将来）: 同一URLの文書のみ置換（ハッシュ差分更新）

### 重要なルール
- `deprecated=true` のアイテムは **スコアリング対象から外す**（将来の実装：Retriever側で除外）
  - ただし「履歴として残す」ためにDBへ保存自体は行う

## スコアリング統合（期待値）
- `index_only` をONにすると、検索ベースを使わず `policy_chunks` のみで根拠候補を引く
- deep_research由来の文書は `policy_chunks` に入るため、そのまま根拠候補になれる
- `topic_ids` が付いていれば、将来はトピックでフィルタする（精度向上）

## 管理UI 再整理案（推奨）
現状 `admin.html` に「トピック管理」と「政党管理」が混在しているため、運用・誤操作リスクが高い。

### 分割（推奨）
- `admin_topics.html`（トピック側）
  - topics CRUD
  - rubrics 生成/編集/activate
  - scoring 実行/確認（topic中心）
  - snapshot 出力（静的公開）
- `admin_parties.html`（政党側）
  - party_registry CRUD
  - policy_sources 登録/クロール
  - Deep Research 取り込み（リサーチパックのアップロード/プレビュー/適用）
  - メンテナンス（policy/scores purge など危険操作はここに隔離）

### 画面内タブ（代替）
HTMLを分けたくない場合は `admin.html` 内でタブ化し、危険操作やデータ取り込みを別タブに隔離する。

## 後続実装（TODO）
1) `backend/scripts/import_research_pack.py`（CLI）: JSON取り込み（append）
2) `POST /admin/parties/{party_id}/research/import`（管理API）: UIからアップロード取り込み
3) Retriever側で `deprecated=true` を除外
4) 取り込み時の重複検出（URL+hash）
