# Backend (FastAPI) 雛形

## 概要
仕様書に記載の公開API（topics/positions/detail）と管理API（discovery/resolve/crawl/score）のスタブ実装を提供するFastAPIベースの骨組みです。現時点ではメモリ内のダミーデータを返すのみで、DB接続や外部HTTPアクセスは行いません。

## ローカル実行
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.main:app --reload
```

## ディレクトリ
- `src/main.py` : エントリポイント、ルータ登録
- `src/api/public.py` : 公開API（topics/positions/detail）
- `src/api/admin.py` : 管理API（discovery/resolve/crawl/score）
- `src/schemas.py` : Pydanticスキーマ（固定JSONフォーマット）
- `src/services/stub_data.py` : テスト用のスタブデータ

## 今後の拡張ポイント
- DBマイグレーション（付録A DDLを Alembic 移植）
- Discovery/Resolution/Crawl/Score の実処理実装
- 認証（管理API用のAPIキー/Token認証）
