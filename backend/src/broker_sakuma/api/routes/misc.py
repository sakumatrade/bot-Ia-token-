from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from broker_sakuma.api.deps import get_db, get_settings, require_api_key
from broker_sakuma.api.schemas import (
    BotLoanSummary,
    GrowthResponse,
    OpportunitySummary,
    PaperTradeSummary,
    ReserveSummary,
    ResearchReportSummary,
    AlertSummary,
    StrategySummary,
    WalletSummary,
)
from broker_sakuma.config import Settings
from broker_sakuma.db import models

router = APIRouter(tags=["misc"], dependencies=[Depends(require_api_key)])


@router.get("/opportunities", response_model=list[OpportunitySummary])
def list_opportunities(db: Session = Depends(get_db)) -> list[models.Opportunity]:
    stmt = select(models.Opportunity).order_by(models.Opportunity.created_at.desc())
    return list(db.execute(stmt).scalars())


@router.get("/trades", response_model=list[PaperTradeSummary])
def list_trades(db: Session = Depends(get_db)) -> list[models.PaperTrade]:
    stmt = select(models.PaperTrade).order_by(models.PaperTrade.executed_at.desc())
    return list(db.execute(stmt).scalars())


@router.get("/strategies", response_model=list[StrategySummary])
def list_strategies(db: Session = Depends(get_db)) -> list[models.Strategy]:
    stmt = select(models.Strategy).order_by(models.Strategy.created_at.asc())
    return list(db.execute(stmt).scalars())


@router.get("/alerts", response_model=list[AlertSummary])
def list_alerts(db: Session = Depends(get_db)) -> list[models.Alert]:
    stmt = select(models.Alert).order_by(models.Alert.created_at.desc())
    return list(db.execute(stmt).scalars())


@router.get("/research", response_model=list[ResearchReportSummary])
def list_research(db: Session = Depends(get_db)) -> list[models.ResearchReport]:
    stmt = select(models.ResearchReport).order_by(models.ResearchReport.created_at.desc())
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
