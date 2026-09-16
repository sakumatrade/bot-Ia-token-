from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from broker_sakuma.api.deps import get_db, require_api_key
from broker_sakuma.api.schemas import BotSummary
from broker_sakuma.db import models

router = APIRouter(tags=["bots"], dependencies=[Depends(require_api_key)])


@router.get("/bots", response_model=list[BotSummary])
def list_bots(db: Session = Depends(get_db)) -> list[models.Bot]:
    stmt = select(models.Bot).order_by(models.Bot.created_at.asc())
    return list(db.execute(stmt).scalars())
