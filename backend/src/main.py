from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .api import admin, public
from .db import engine


app = FastAPI(
    title="PartyViz API",
    version="0.1.0",
    description="政党の立場可視化アプリのMVP向けAPIスタブ",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(public.router, tags=["public"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])


@app.get("/healthz", tags=["health"])
def healthcheck() -> dict:
    """簡易ヘルスチェック"""
    return {"status": "ok"}


@app.get("/healthz/db", tags=["health"])
def healthcheck_db() -> dict:
    """DB接続確認"""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "db": "ok"}
