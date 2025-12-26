# Backend (FastAPI)

## 概要
公開API（topics/positions/detail/rubric）と管理API（topics/parties/rubrics/score/policy-sources 等）を備えたFastAPIアプリです。PostgreSQLに接続し、ルーブリック・スコア・政党レジストリ・政策インデックスを保存します。

## ローカル実行
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn src.main:app --reload --port 8000
```

## ディレクトリ
- `src/main.py` : エントリポイント、ルータ登録
- `src/api/public.py` : 公開API（topics/positions/detail/rubric）
- `src/api/admin.py` : 管理API（topics/parties/rubrics/score/policy-sources）
- `src/schemas.py` : Pydanticスキーマ
- `src/services/` : スコアリング、ルーブリック、政策クロール/インデックス等

## 今後の拡張ポイント
- 検索/インデックスの精度改善（keyword/BM25/ベクトル）
- 画像PDFのOCR取り込み（将来）
- 公開APIのキャッシュ強化
