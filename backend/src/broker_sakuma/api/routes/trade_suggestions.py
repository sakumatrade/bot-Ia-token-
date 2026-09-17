"""Trade suggestion endpoints (spec sections 33, 61): a plain-language
idea the system proposes, never an instruction it acts on. See
``engines/trade_suggestion_engine.py`` for why there is no execute
endpoint here, and never will be — acting on a suggestion, if the user
chooses to, happens entirely in their own wallet software.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from broker_sakuma.api.deps import get_db, require_api_key
from broker_sakuma.api.schemas import TradeSuggestionSummary
from broker_sakuma.core.enums import TradeSuggestionStatus
from broker_sakuma.db import models
from broker_sakuma.engines.trade_suggestion_engine import TradeSuggestionEngine

router = APIRouter(tags=["trade-suggestions"], dependencies=[Depends(require_api_key)])


@router.get("/trade-suggestions", response_model=list[TradeSuggestionSummary])
def list_trade_suggestions(
    db: Session = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
) -> list[models.TradeSuggestion]:
    stmt = select(models.TradeSuggestion).order_by(models.TradeSuggestion.created_at.desc())
    if status_filter:
        try:
            stmt = stmt.where(models.TradeSuggestion.status == TradeSuggestionStatus(status_filter))
        except ValueError as exc:
            valid = ", ".join(s.value for s in TradeSuggestionStatus)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"invalid status {status_filter!r}; must be one of: {valid}",
            ) from exc
    stmt = stmt.offset(offset).limit(limit)
    return list(db.execute(stmt).scalars())


def _update_status(suggestion_id: str, new_status: TradeSuggestionStatus, db: Session) -> models.TradeSuggestion:
    suggestion = db.get(models.TradeSuggestion, suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"trade suggestion {suggestion_id} not found")
    return TradeSuggestionEngine(db).set_status(suggestion, new_status)


@router.post("/trade-suggestions/{suggestion_id}/dismiss", response_model=TradeSuggestionSummary)
def dismiss_trade_suggestion(suggestion_id: str, db: Session = Depends(get_db)) -> models.TradeSuggestion:
    return _update_status(suggestion_id, TradeSuggestionStatus.DISMISSED, db)


@router.post("/trade-suggestions/{suggestion_id}/mark-done", response_model=TradeSuggestionSummary)
def mark_trade_suggestion_done(suggestion_id: str, db: Session = Depends(get_db)) -> models.TradeSuggestion:
    """The user acted on this manually, in their own wallet — this is
    just their own tracking; it never triggers anything in this system."""

    return _update_status(suggestion_id, TradeSuggestionStatus.DONE_MANUALLY, db)
