from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from broker_sakuma.api.deps import get_db, get_settings, require_api_key
from broker_sakuma.api.schemas import (
    AddWalletRequest,
    BotLoanSummary,
    GrowthResponse,
    OpportunitySummary,
    PaperTradeSummary,
    ProtocolSummary,
    ReserveSummary,
    ResearchReportSummary,
    AlertSummary,
    StrategySummary,
    WalletSummary,
)
from broker_sakuma.config import Settings
from broker_sakuma.core.enums import WalletKind, WalletType
from broker_sakuma.db import models
from broker_sakuma.engines.wallet_manager import DuplicateWalletError, WalletManager

router = APIRouter(tags=["misc"], dependencies=[Depends(require_api_key)])


def _limit_query(default: int = 200) -> int:
    """Bounds how many rows a list endpoint returns per call (spec: the
    server must stay light no matter how much history dead bots
    accumulate). Nothing is ever deleted to achieve this — every row
    stays in the database forever for post-mortems/collective memory
    (spec sections 13/47) — this only bounds a single response's size;
    pass a smaller/larger `limit` or `offset` to page through older rows.
    """

    return Query(default=default, ge=1, le=1000)


@router.get("/opportunities", response_model=list[OpportunitySummary])
def list_opportunities(
    db: Session = Depends(get_db), limit: int = _limit_query(), offset: int = Query(default=0, ge=0)
) -> list[models.Opportunity]:
    stmt = select(models.Opportunity).order_by(models.Opportunity.created_at.desc()).offset(offset).limit(limit)
    return list(db.execute(stmt).scalars())


@router.get("/trades", response_model=list[PaperTradeSummary])
def list_trades(
    db: Session = Depends(get_db), limit: int = _limit_query(), offset: int = Query(default=0, ge=0)
) -> list[models.PaperTrade]:
    stmt = select(models.PaperTrade).order_by(models.PaperTrade.executed_at.desc()).offset(offset).limit(limit)
    return list(db.execute(stmt).scalars())


@router.get("/strategies", response_model=list[StrategySummary])
def list_strategies(db: Session = Depends(get_db)) -> list[models.Strategy]:
    stmt = select(models.Strategy).order_by(models.Strategy.created_at.asc())
    return list(db.execute(stmt).scalars())


@router.get("/alerts", response_model=list[AlertSummary])
def list_alerts(
    db: Session = Depends(get_db), limit: int = _limit_query(), offset: int = Query(default=0, ge=0)
) -> list[models.Alert]:
    stmt = select(models.Alert).order_by(models.Alert.created_at.desc()).offset(offset).limit(limit)
    return list(db.execute(stmt).scalars())


@router.get("/research", response_model=list[ResearchReportSummary])
def list_research(
    db: Session = Depends(get_db), limit: int = _limit_query(), offset: int = Query(default=0, ge=0)
) -> list[models.ResearchReport]:
    stmt = select(models.ResearchReport).order_by(models.ResearchReport.created_at.desc()).offset(offset).limit(limit)
    return list(db.execute(stmt).scalars())


@router.get("/protocols", response_model=list[ProtocolSummary])
def list_protocols(db: Session = Depends(get_db)) -> list[models.Protocol]:
    """Research Lab board (spec section 25): every protocol
    ``ProtocolDiscoveryAgent`` has registered, grouped implicitly by
    ``status`` (RESEARCH_ONLY/PAPER_ELIGIBLE/REVIEW_REQUIRED/DISABLED) on
    the client side. Found missing during Phase 17 integration testing:
    ``/api/research`` only ever covers the still-unused ``research_reports``
    table, not the ``protocols`` table ``CryptoResearchLab`` actually
    operates on.
    """

    stmt = select(models.Protocol).order_by(models.Protocol.updated_at.desc())
    return list(db.execute(stmt).scalars())


@router.get("/loans", response_model=list[BotLoanSummary])
def list_loans(db: Session = Depends(get_db)) -> list[models.BotLoan]:
    stmt = select(models.BotLoan).order_by(models.BotLoan.created_at.desc())
    return list(db.execute(stmt).scalars())


@router.get("/reserves", response_model=list[ReserveSummary])
def list_reserves(db: Session = Depends(get_db)) -> list[models.Reserve]:
    stmt = select(models.Reserve).order_by(models.Reserve.updated_at.desc())
    return list(db.execute(stmt).scalars())


@router.get("/wallets", response_model=list[WalletSummary])
def list_wallets(db: Session = Depends(get_db)) -> list[models.Wallet]:
    stmt = select(models.Wallet).order_by(models.Wallet.created_at.asc())
    return list(db.execute(stmt).scalars())


@router.post("/wallets", response_model=WalletSummary, status_code=status.HTTP_201_CREATED)
def add_wallet(payload: AddWalletRequest, db: Session = Depends(get_db)) -> models.Wallet:
    """Always registers the wallet as WATCH_ONLY — this backend has no
    signer capable of anything else (spec section 33: no private key,
    seed phrase, or mnemonic is ever accepted here, and there is no field
    for one in ``AddWalletRequest``).
    """

    try:
        wallet_type = WalletType(payload.wallet_type)
    except ValueError as exc:
        valid = ", ".join(t.value for t in WalletType)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid wallet_type {payload.wallet_type!r}; must be one of: {valid}",
        ) from exc

    manager = WalletManager(db)
    try:
        return manager.add_wallet(
            name=payload.name,
            blockchain=payload.blockchain,
            wallet_type=wallet_type,
            kind=WalletKind.WATCH_ONLY,
            public_address=payload.public_address,
            purpose=payload.purpose,
        )
    except DuplicateWalletError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.get("/growth", response_model=GrowthResponse)
def get_growth(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> GrowthResponse:
    bots = list(db.execute(select(models.Bot)).scalars())
    bots_by_generation: dict[int, int] = {}
    for bot in bots:
        bots_by_generation[bot.generation] = bots_by_generation.get(bot.generation, 0) + 1

    return GrowthResponse(
        max_bots=settings.growth.max_bots,
        max_generations=settings.growth.max_generations,
        max_mother_exposure_pct=settings.growth.max_mother_exposure_pct,
        total_bots=len(bots),
        bots_by_generation=bots_by_generation,
    )
