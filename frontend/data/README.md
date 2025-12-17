# 公開用スナップショット

静的ホスティングで公開する場合、バックエンドAPIの代わりに `snapshot.json` を参照します。

## 配置
- `frontend/data/snapshot.json`

## 生成方法（ローカル）
- 管理UI（`frontend/admin.html`）の「スナップショットをダウンロード」
- もしくはコマンド: `cd backend && python scripts/export_snapshot.py`

