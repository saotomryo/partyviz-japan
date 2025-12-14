from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import AdminJobResponse, PartyCreate, PartyResponse
from ..services import party_registry
from ..settings import settings


router = APIRouter()


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """管理API用の簡易APIキー認証。settings.admin_api_key が未設定なら無効化。"""
    if settings.admin_api_key is None:
        return  # 未設定なら認証スキップ（開発用）
    if x_api_key != settings.admin_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


@router.post("/discovery/run", response_model=AdminJobResponse, dependencies=[Depends(require_api_key)])
def run_discovery() -> AdminJobResponse:
    return AdminJobResponse(detail="discovery job enqueued (stub)")


@router.post("/resolve/run", response_model=AdminJobResponse, dependencies=[Depends(require_api_key)])
def run_resolution() -> AdminJobResponse:
    return AdminJobResponse(detail="resolution job enqueued (stub)")


@router.post("/crawl/run", response_model=AdminJobResponse, dependencies=[Depends(require_api_key)])
def run_crawl() -> AdminJobResponse:
    return AdminJobResponse(detail="crawl job enqueued (stub)")


@router.post("/score/run", response_model=AdminJobResponse, dependencies=[Depends(require_api_key)])
def run_score() -> AdminJobResponse:
    return AdminJobResponse(detail="score job enqueued (stub)")


@router.get("/parties", response_model=list[PartyResponse], dependencies=[Depends(require_api_key)])
def get_parties(db: Session = Depends(get_db)) -> list[PartyResponse]:
    return party_registry.list_parties(db)


@router.post("/parties", response_model=PartyResponse, dependencies=[Depends(require_api_key)])
def post_party(payload: PartyCreate, db: Session = Depends(get_db)) -> PartyResponse:
    return party_registry.create_party(db, payload)
